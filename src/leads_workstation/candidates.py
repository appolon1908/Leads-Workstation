from __future__ import annotations

import hashlib
import json
import posixpath
import re
import uuid
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .db import db_connection, init_db, now_utc
from .normalize import normalize_phone, normalize_text

NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def _col_index(ref: str) -> int:
    letters = "".join(c for c in ref if c.isalpha())
    n = 0
    for c in letters:
        n = n * 26 + ord(c.upper()) - 64
    return n - 1


def read_first_sheet(path: str | Path) -> list[tuple[int, list[str]]]:
    src = Path(path)
    with zipfile.ZipFile(src) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("a:si", NS):
                shared.append("".join(t.text or "" for t in si.iterfind(".//a:t", NS)))

        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        relmap = {r.attrib["Id"]: r.attrib["Target"] for r in rels}
        sheet = wb.find("a:sheets/a:sheet", NS)
        if sheet is None:
            return []
        target = relmap[sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
        sheet_path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
        root = ET.fromstring(z.read(sheet_path))

        rows: list[tuple[int, list[str]]] = []
        for row in root.findall(".//a:sheetData/a:row", NS):
            vals: dict[int, str] = {}
            for cell in row.findall("a:c", NS):
                idx = _col_index(cell.attrib.get("r", "A1"))
                kind = cell.attrib.get("t")
                if kind == "inlineStr":
                    val = "".join(x.text or "" for x in cell.iterfind(".//a:t", NS))
                else:
                    node = cell.find("a:v", NS)
                    raw = "" if node is None else (node.text or "")
                    if kind == "s" and raw:
                        try:
                            val = shared[int(raw)]
                        except Exception:
                            val = raw
                    else:
                        val = raw
                vals[idx] = str(val).strip()
            if vals:
                rows.append((int(row.attrib.get("r", "0")), [vals.get(i, "") for i in range(max(vals) + 1)]))
        return rows


def _norm_header(value: str) -> str:
    ascii_value = "".join(ch for ch in unicodedata.normalize("NFKD", str(value)) if not unicodedata.combining(ch))
    return normalize_text(ascii_value)


def parse_appraiser_candidates(path: str | Path) -> list[dict[str, Any]]:
    rows = read_first_sheet(path)
    header_idx = None
    headers: list[str] = []
    for i, (_, vals) in enumerate(rows):
        normalized = [_norm_header(v) for v in vals]
        if "nombre" in normalized and any("telefono" in h for h in normalized):
            header_idx = i
            headers = normalized
            break
    if header_idx is None:
        raise ValueError("could not locate appraiser header row")

    def col(name: str) -> int | None:
        for i, h in enumerate(headers):
            if h == name or h.startswith(name):
                return i
        return None

    name_i = col("nombre")
    work_i = col("zona usual de trabajo")
    page_i = col("pagina")
    date_i = col("fecha de fuente")
    phone_is = [i for i, h in enumerate(headers) if h.startswith("telefono")]

    out: list[dict[str, Any]] = []
    for row_num, vals in rows[header_idx + 1 :]:
        name = vals[name_i] if name_i is not None and name_i < len(vals) else ""
        if not name:
            continue
        phones = []
        for i in phone_is:
            if i < len(vals):
                p = normalize_phone(vals[i])
                if p and p not in phones:
                    phones.append(p)
        area = vals[work_i] if work_i is not None and work_i < len(vals) else ""
        page = vals[page_i] if page_i is not None and page_i < len(vals) else ""
        source_date = vals[date_i] if date_i is not None and date_i < len(vals) else ""
        out.append(
            {
                "contact_name": name.strip(),
                "business_name": name.strip(),
                "country": "Dominican Republic",
                "business_category": "Independent Property Appraisers",
                "phones": phones,
                "notes": f"Historical external appraiser. Work area: {area}. Source page: {page}. Source date serial: {source_date}.",
                "source_row": row_num,
                "raw": vals,
            }
        )
    return out


def stage_appraiser_batch(db_path: str | Path, xlsx_path: str | Path, batch_id: str = "appraisers-2019") -> dict[str, Any]:
    init_db(db_path)
    src = Path(xlsx_path).resolve()
    candidates = parse_appraiser_candidates(src)

    with db_connection(db_path) as conn:
        existing = conn.execute(
            "SELECT lead_id,business_name,contact_name,normalized_phone FROM leads"
        ).fetchall()

        by_name: dict[str, str] = {}
        by_phone: dict[str, str] = {}
        for row in existing:
            for value in (row["contact_name"], row["business_name"]):
                key = normalize_text(value)
                if key:
                    by_name.setdefault(key, row["lead_id"])
            p = row["normalized_phone"]
            if p:
                by_phone.setdefault(str(p), row["lead_id"])

        inserted = possible_matches = new_count = 0
        for c in candidates:
            match_id = None
            match_reason = None
            for p in c["phones"]:
                if p in by_phone:
                    match_id = by_phone[p]
                    match_reason = f"phone:{p}"
                    break
            if not match_id:
                name_key = normalize_text(c["contact_name"])
                if name_key in by_name:
                    match_id = by_name[name_key]
                    match_reason = "normalized_name"

            disposition = "possible_match" if match_id else "new"
            if match_id:
                possible_matches += 1
            else:
                new_count += 1

            raw_key = json.dumps(
                {"name": c["contact_name"], "phones": c["phones"], "row": c["source_row"]},
                ensure_ascii=False,
                sort_keys=True,
            )
            source_fingerprint = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
            candidate_id = "cand_" + source_fingerprint[:24]

            cur = conn.execute(
                """
                INSERT OR IGNORE INTO candidate_leads(
                    candidate_id,batch_id,contact_name,business_name,country,business_category,
                    phones_json,email,notes,source_file,source_row,source_fingerprint,
                    match_lead_id,match_reason,disposition,source_payload,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    candidate_id,
                    batch_id,
                    c["contact_name"],
                    c["business_name"],
                    c["country"],
                    c["business_category"],
                    json.dumps(c["phones"]),
                    None,
                    c["notes"],
                    str(src),
                    c["source_row"],
                    source_fingerprint,
                    match_id,
                    match_reason,
                    disposition,
                    json.dumps(c["raw"], ensure_ascii=False),
                    now_utc(),
                ),
            )
            inserted += max(cur.rowcount, 0)

        summary = {
            "batch_id": batch_id,
            "source": str(src),
            "parsed_candidates": len(candidates),
            "inserted_candidates": inserted,
            "possible_matches": possible_matches,
            "new_candidates": new_count,
        }
        return summary


def candidate_summary(db_path: str | Path, batch_id: str | None = None) -> dict[str, Any]:
    init_db(db_path)
    with db_connection(db_path) as conn:
        params: tuple[Any, ...] = ()
        where = ""
        if batch_id:
            where = " WHERE batch_id=?"
            params = (batch_id,)
        counts = {
            row["disposition"]: row["count"]
            for row in conn.execute(
                "SELECT disposition,COUNT(*) count FROM candidate_leads" + where + " GROUP BY disposition",
                params,
            )
        }
        total = conn.execute("SELECT COUNT(*) FROM candidate_leads" + where, params).fetchone()[0]
        return {"batch_id": batch_id, "total": total, "by_disposition": counts}


def promote_new_candidates(db_path: str | Path, batch_id: str, actor: str = "candidate-promoter") -> dict[str, int]:
    from .db import create_lead

    init_db(db_path)
    with db_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM candidate_leads WHERE batch_id=? AND disposition='new' ORDER BY source_row",
            (batch_id,),
        ).fetchall()

    promoted = failed = 0
    for row in rows:
        phones = json.loads(row["phones_json"] or "[]")
        payload = {
            "business_name": row["business_name"],
            "contact_name": row["contact_name"],
            "country": row["country"],
            "business_category": row["business_category"],
            "phone": phones[0] if phones else None,
            "notes": row["notes"],
            "status": "Needs Verification",
            "verification_status": "Historical source - unverified",
        }
        try:
            lead = create_lead(db_path, payload, actor=actor)
            with db_connection(db_path) as conn:
                conn.execute(
                    "UPDATE candidate_leads SET disposition='promoted', match_lead_id=?, match_reason='promoted_new', promoted_at=? WHERE candidate_id=?",
                    (lead["lead_id"], now_utc(), row["candidate_id"]),
                )
            promoted += 1
        except Exception:
            failed += 1
    return {"promoted": promoted, "failed": failed}


def list_candidates(
    db_path: str | Path,
    batch_id: str | None = None,
    disposition: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    init_db(db_path)
    where = []
    params: list[Any] = []
    if batch_id:
        where.append("batch_id=?")
        params.append(batch_id)
    if disposition:
        where.append("disposition=?")
        params.append(disposition)
    sql = """
        SELECT candidate_id,batch_id,contact_name,business_name,country,business_category,
               phones_json,email,notes,source_file,source_row,match_lead_id,match_reason,
               disposition,created_at,promoted_at
        FROM candidate_leads
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY batch_id, source_row LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    with db_connection(db_path) as conn:
        rows = []
        for row in conn.execute(sql, params):
            item = dict(row)
            item["phones"] = json.loads(item.pop("phones_json") or "[]")
            rows.append(item)
        return rows

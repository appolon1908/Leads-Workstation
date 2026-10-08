from __future__ import annotations

import time

from .db import init_db
from .storage import db_connection

_START = time.monotonic()


def prometheus_metrics(db_path) -> str:
    init_db(db_path)
    with db_connection(db_path) as conn:
        rows = {
            "leads_total": conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0],
            "leads_suppressed_total": conn.execute(
                "SELECT COUNT(*) FROM leads WHERE suppressed=1"
            ).fetchone()[0],
            "leads_dnc_total": conn.execute(
                "SELECT COUNT(*) FROM leads WHERE do_not_contact=1"
            ).fetchone()[0],
            "leads_campaigns_total": conn.execute(
                "SELECT COUNT(*) FROM campaigns"
            ).fetchone()[0],
            "leads_outbox_pending_total": conn.execute(
                "SELECT COUNT(*) FROM outbox_events WHERE status='pending'"
            ).fetchone()[0],
            "leads_candidates_pending_total": conn.execute(
                "SELECT COUNT(*) FROM candidate_leads "
                "WHERE disposition IN ('new','possible_match')"
            ).fetchone()[0],
        }
        by_status = [
            (str(r["status"]), int(r["count"]))
            for r in conn.execute(
                "SELECT status,COUNT(*) count FROM leads GROUP BY status ORDER BY status"
            )
        ]

    lines = [
        "# HELP leads_total Canonical lead records.",
        "# TYPE leads_total gauge",
        f"leads_total {rows['leads_total']}",
        "# HELP leads_suppressed_total Fully suppressed leads.",
        "# TYPE leads_suppressed_total gauge",
        f"leads_suppressed_total {rows['leads_suppressed_total']}",
        "# HELP leads_dnc_total Do-not-contact leads.",
        "# TYPE leads_dnc_total gauge",
        f"leads_dnc_total {rows['leads_dnc_total']}",
        "# HELP leads_campaigns_total Campaign definitions.",
        "# TYPE leads_campaigns_total gauge",
        f"leads_campaigns_total {rows['leads_campaigns_total']}",
        "# HELP leads_outbox_pending_total Pending outbox events.",
        "# TYPE leads_outbox_pending_total gauge",
        f"leads_outbox_pending_total {rows['leads_outbox_pending_total']}",
        "# HELP leads_candidates_pending_total Candidate rows requiring disposition.",
        "# TYPE leads_candidates_pending_total gauge",
        f"leads_candidates_pending_total {rows['leads_candidates_pending_total']}",
        "# HELP leads_process_uptime_seconds Leads Workstation process uptime.",
        "# TYPE leads_process_uptime_seconds gauge",
        f"leads_process_uptime_seconds {time.monotonic() - _START:.3f}",
        "# HELP leads_status_total Leads grouped by lifecycle status.",
        "# TYPE leads_status_total gauge",
    ]
    for status, count in by_status:
        safe = status.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
        lines.append(f'leads_status_total{{status="{safe}"}} {count}')
    return "\n".join(lines) + "\n"

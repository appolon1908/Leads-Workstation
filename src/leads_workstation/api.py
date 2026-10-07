from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .candidates import candidate_summary, list_candidates
from .db import (
    DuplicateLeadError,
    create_lead,
    get_lead,
    lead_events,
    list_leads,
    stats,
    update_lead,
)

INDEX = """<!doctype html><html><head><meta charset="utf-8"><title>Codestra Leads Workstation</title>
<style>body{font-family:system-ui;margin:2rem;max-width:1400px}table{width:100%;border-collapse:collapse}th,td{padding:.5rem;border-bottom:1px solid #ddd;text-align:left}input{padding:.6rem;width:420px}button{padding:.6rem}</style></head>
<body><h1>Codestra Leads Workstation</h1><p>Local-only lead operations runtime.</p>
<p>JSON endpoints: /api/stats, /api/leads?q=search, /api/candidates, /api/candidates/summary, POST /api/leads, PATCH /api/leads/{id}</p></body></html>"""

MAX_BODY_BYTES = 1024 * 1024


def make_handler(db_path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CodestraLeads/0.1"

        def log_message(self, fmt, *args):
            return

        def send_json(self, value, status=HTTPStatus.OK):
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def read_json(self):
            raw_length = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_length)
            except ValueError:
                raise ValueError("invalid Content-Length")
            if length <= 0:
                raise ValueError("request body required")
            if length > MAX_BODY_BYTES:
                raise ValueError("request body too large")
            body = self.rfile.read(length)
            value = json.loads(body.decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError("JSON body must be an object")
            return value

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/":
                body = INDEX.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/health":
                self.send_json({"ok": True, "service": "leads-workstation"})
                return

            if parsed.path == "/api/stats":
                self.send_json(stats(db_path))
                return

            if parsed.path == "/api/candidates/summary":
                q = parse_qs(parsed.query)
                self.send_json(candidate_summary(db_path, q.get("batch_id", [None])[0]))
                return

            if parsed.path == "/api/candidates":
                q = parse_qs(parsed.query)
                items = list_candidates(
                    db_path,
                    batch_id=q.get("batch_id", [None])[0],
                    disposition=q.get("disposition", [None])[0],
                    limit=int(q.get("limit", ["100"])[0]),
                )
                self.send_json({"items": items, "count": len(items)})
                return

            if parsed.path == "/api/leads":
                q = parse_qs(parsed.query)
                items = list_leads(
                    db_path,
                    int(q.get("limit", ["50"])[0]),
                    int(q.get("offset", ["0"])[0]),
                    q.get("country", [None])[0],
                    q.get("category", [None])[0],
                    q.get("status", [None])[0],
                    q.get("q", [None])[0],
                )
                self.send_json({"items": items, "count": len(items)})
                return

            if parsed.path.startswith("/api/leads/") and parsed.path.endswith("/events"):
                parts = parsed.path.strip("/").split("/")
                if len(parts) == 4:
                    self.send_json({"items": lead_events(db_path, parts[2])})
                    return

            if parsed.path.startswith("/api/leads/"):
                lead_id = parsed.path.split("/", 3)[-1]
                lead = get_lead(db_path, lead_id)
                self.send_json(lead if lead else {"error": "not_found"}, 200 if lead else 404)
                return

            self.send_json({"error": "not_found"}, 404)

        def do_POST(self):
            parsed = urlparse(self.path)
            if parsed.path != "/api/leads":
                self.send_json({"error": "not_found"}, 404)
                return
            try:
                payload = self.read_json()
                lead = create_lead(db_path, payload, actor="local-api")
                self.send_json(lead, 201)
            except DuplicateLeadError as exc:
                self.send_json({"error": "duplicate", "detail": str(exc)}, 409)
            except (ValueError, json.JSONDecodeError) as exc:
                self.send_json({"error": "bad_request", "detail": str(exc)}, 400)

        def do_PATCH(self):
            parsed = urlparse(self.path)
            if not parsed.path.startswith("/api/leads/"):
                self.send_json({"error": "not_found"}, 404)
                return
            lead_id = parsed.path.split("/", 3)[-1]
            try:
                payload = self.read_json()
                lead = update_lead(db_path, lead_id, payload, actor="local-api")
                if lead is None:
                    self.send_json({"error": "not_found"}, 404)
                else:
                    self.send_json(lead)
            except (ValueError, json.JSONDecodeError) as exc:
                self.send_json({"error": "bad_request", "detail": str(exc)}, 400)

    return Handler


def serve(db_path, host="127.0.0.1", port=8765, allow_network=False):
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise SystemExit("Refusing non-loopback bind without --allow-network")
    print("Leads Workstation: http://" + host + ":" + str(port))
    ThreadingHTTPServer((host, port), make_handler(db_path)).serve_forever()

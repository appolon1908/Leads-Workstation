import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from leads_workstation.api import make_handler


class V2HttpApiTests(unittest.TestCase):
    def setUp(self):
        self._old_auth = os.environ.get("LEADS_AUTH_MODE")
        self._old_v1 = os.environ.get("LEADS_ENABLE_V1")
        os.environ["LEADS_AUTH_MODE"] = "dev"
        os.environ.pop("LEADS_ENABLE_V1", None)
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "api.db"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.db))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temp.cleanup()
        if self._old_auth is None:
            os.environ.pop("LEADS_AUTH_MODE", None)
        else:
            os.environ["LEADS_AUTH_MODE"] = self._old_auth
        if self._old_v1 is None:
            os.environ.pop("LEADS_ENABLE_V1", None)
        else:
            os.environ["LEADS_ENABLE_V1"] = self._old_v1

    def request(self, method, path, *, payload=None, headers=None):
        body = None
        req_headers = dict(headers or {})
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            self.base + path,
            data=body,
            method=method,
            headers=req_headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                raw = response.read().decode("utf-8")
                return response.status, dict(response.headers), json.loads(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            return exc.code, dict(exc.headers), json.loads(raw)

    def admin_headers(self):
        return {
            "X-Dev-User": "admin-1",
            "X-Dev-Roles": "admin",
        }

    def agent_headers(self, subject, campaign_id):
        return {
            "X-Dev-User": subject,
            "X-Dev-Roles": "agent",
            "X-Dev-Campaigns": campaign_id,
        }

    def test_health_public_v2_authenticated_and_v1_closed(self):
        status, _, body = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])

        status, _, body = self.request("GET", "/api/v2/me")
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "unauthorized")

        status, _, body = self.request(
            "GET",
            "/api/v2/me",
            headers=self.admin_headers(),
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["subject"], "admin-1")

        status, _, body = self.request("GET", "/api/stats")
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "forbidden")

    def test_campaign_scoped_agent_and_optimistic_patch(self):
        status, _, campaign = self.request(
            "POST",
            "/api/v2/campaigns",
            payload={
                "campaign_code": "API-TEST",
                "name": "API Test Campaign",
                "campaign_type": "outbound",
                "state": "active",
            },
            headers=self.admin_headers(),
        )
        self.assertEqual(status, 201)
        campaign_id = campaign["campaign_id"]

        for agent in ("agent-a", "agent-b"):
            status, _, _ = self.request(
                "POST",
                f"/api/v2/campaigns/{campaign_id}/members",
                payload={"user_id": agent, "member_role": "agent"},
                headers=self.admin_headers(),
            )
            self.assertEqual(status, 201)

        status, headers, lead = self.request(
            "POST",
            "/api/v2/leads",
            payload={
                "business_name": "Scoped Lead",
                "country": "Dominican Republic",
                "business_category": "Services",
                "email": "scoped@example.com",
                "campaign_id": campaign_id,
            },
            headers=self.agent_headers("agent-a", campaign_id),
        )
        self.assertEqual(status, 201)
        self.assertEqual(lead["assigned_agent"], "agent-a")
        self.assertEqual(headers["ETag"], '"1"')

        status, _, body = self.request(
            "GET",
            f"/api/v2/leads/{lead['lead_id']}",
            headers=self.agent_headers("agent-b", campaign_id),
        )
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "forbidden")

        patch_headers = self.agent_headers("agent-a", campaign_id)
        patch_headers["If-Match"] = '"1"'
        status, headers, changed = self.request(
            "PATCH",
            f"/api/v2/leads/{lead['lead_id']}",
            payload={"notes": "first edit"},
            headers=patch_headers,
        )
        self.assertEqual(status, 200)
        self.assertEqual(changed["version"], 2)
        self.assertEqual(headers["ETag"], '"2"')

        status, _, body = self.request(
            "PATCH",
            f"/api/v2/leads/{lead['lead_id']}",
            payload={"notes": "stale edit"},
            headers=patch_headers,
        )
        self.assertEqual(status, 409)
        self.assertEqual(body["error"], "conflict")


if __name__ == "__main__":
    unittest.main()

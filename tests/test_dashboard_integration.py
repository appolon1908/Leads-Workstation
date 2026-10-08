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
from leads_workstation.db import init_db, now_utc
from leads_workstation.storage import db_connection


class DashboardIntegrationTests(unittest.TestCase):
    def setUp(self):
        self._old_auth = os.environ.get("LEADS_AUTH_MODE")
        os.environ["LEADS_AUTH_MODE"] = "dev"
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "dashboard.db"
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

    def headers(self):
        return {
            "X-Dev-User": "dashboard-admin",
            "X-Dev-Roles": "admin",
        }

    def request(self, method, path, *, payload=None, headers=None, raw=False):
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
                content = response.read()
                if raw:
                    return response.status, dict(response.headers), content.decode("utf-8")
                return response.status, dict(response.headers), json.loads(content.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            content = exc.read()
            if raw:
                return exc.code, dict(exc.headers), content.decode("utf-8")
            return exc.code, dict(exc.headers), json.loads(content.decode("utf-8"))

    def test_dashboard_assets_and_policy_options_are_available(self):
        status, _, html = self.request("GET", "/", raw=True)
        self.assertEqual(status, 200)
        self.assertIn("Leads Workstation", html)
        self.assertIn("Campaigns", html)
        self.assertIn("Candidates", html)
        self.assertIn('id="drawer"', html)
        self.assertIn('id="modal"', html)

        status, _, js = self.request("GET", "/assets/dashboard.js", raw=True)
        self.assertEqual(status, 200)
        for action in (
            "openCreateLead",
            "openAssign",
            "openTransition",
            "openAddContact",
            "openConsent",
            "openSuppress",
            "openUnsuppress",
            "openCreateCampaign",
            "openPromoteCandidates",
        ):
            self.assertIn(action, js)

        status, _, options = self.request(
            "GET", "/api/v2/options", headers=self.headers()
        )
        self.assertEqual(status, 200)
        self.assertEqual(options["permissions"], ["*"])
        self.assertIn("Assigned", options["lifecycle_transitions"])
        self.assertIn("valid", options["contact_verification_states"])
        self.assertIn("agent", options["member_roles"])

        status, _, me = self.request("GET", "/api/v2/me", headers=self.headers())
        self.assertEqual(status, 200)
        self.assertEqual(me["permissions"], ["*"])

        supervisor_headers = {
            "X-Dev-User": "dashboard-supervisor",
            "X-Dev-Roles": "supervisor",
            "X-Dev-Campaigns": "cmp-ui",
        }
        status, _, supervisor_options = self.request(
            "GET", "/api/v2/options", headers=supervisor_headers
        )
        self.assertEqual(status, 200)
        self.assertIn("lead:create", supervisor_options["permissions"])
        self.assertNotIn("campaign:create", supervisor_options["permissions"])

    def test_complete_dashboard_operator_journey(self):
        h = self.headers()

        status, _, campaign = self.request(
            "POST",
            "/api/v2/campaigns",
            headers=h,
            payload={
                "campaign_code": "UI-FLOW",
                "name": "UI Flow Campaign",
                "campaign_type": "outbound",
                "state": "active",
                "primary_supervisor": "supervisor-ui",
            },
        )
        self.assertEqual(status, 201)
        campaign_id = campaign["campaign_id"]

        status, _, member = self.request(
            "POST",
            f"/api/v2/campaigns/{campaign_id}/members",
            headers=h,
            payload={"user_id": "agent-ui", "member_role": "agent", "active": True},
        )
        self.assertEqual(status, 201)
        self.assertEqual(member["user_id"], "agent-ui")

        status, headers, lead = self.request(
            "POST",
            "/api/v2/leads",
            headers=h,
            payload={
                "business_name": "Interactive Lead",
                "contact_name": "UI Tester",
                "country": "Dominican Republic",
                "business_category": "Certification",
                "email": "interactive@example.com",
                "phone": "809-555-9191",
                "campaign_id": campaign_id,
                "notes": "created from dashboard journey",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(headers["ETag"], '"1"')
        lead_id = lead["lead_id"]

        patch_headers = {**h, "If-Match": '"1"'}
        status, headers, lead = self.request(
            "PATCH",
            f"/api/v2/leads/{lead_id}",
            headers=patch_headers,
            payload={"notes": "edited interactively", "priority": "high"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(lead["version"], 2)
        self.assertEqual(headers["ETag"], '"2"')

        status, _, lead = self.request(
            "POST",
            f"/api/v2/leads/{lead_id}/assign",
            headers=h,
            payload={
                "campaign_id": campaign_id,
                "strategy": "round_robin",
                "reason": "dashboard assignment",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(lead["assigned_agent"], "agent-ui")
        self.assertEqual(lead["status"], "Assigned")

        status, _, lead = self.request(
            "POST",
            f"/api/v2/leads/{lead_id}/transition",
            headers=h,
            payload={
                "to_status": "Attempted",
                "reason": "dashboard lifecycle action",
                "expected_version": lead["version"],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(lead["status"], "Attempted")

        status, _, contact = self.request(
            "POST",
            f"/api/v2/leads/{lead_id}/contacts",
            headers=h,
            payload={
                "kind": "email",
                "value": "verified-ui@example.com",
                "label": "work",
                "primary": False,
                "verification_status": "unverified",
                "source": "dashboard",
            },
        )
        self.assertEqual(status, 201)

        status, _, verified = self.request(
            "POST",
            f"/api/v2/contact-points/{contact['contact_point_id']}/verify",
            headers=h,
            payload={
                "verification_status": "valid",
                "source": "dashboard-verification",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(verified["verification_status"], "valid")

        status, _, lead = self.request(
            "POST",
            f"/api/v2/leads/{lead_id}/consent",
            headers=h,
            payload={
                "status": "opted_in",
                "source": "dashboard",
                "jurisdiction": "DO",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(lead["consent_status"], "opted_in")

        status, _, lead = self.request(
            "POST",
            f"/api/v2/leads/{lead_id}/suppress",
            headers=h,
            payload={
                "channel": "call",
                "reason": "customer request",
                "jurisdiction": "DO",
                "source": "dashboard",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(lead["do_not_contact"], 1)
        self.assertEqual(lead["status"], "DNC")

        status, _, suppressions = self.request(
            "GET",
            f"/api/v2/leads/{lead_id}/suppressions",
            headers=h,
        )
        self.assertEqual(status, 200)
        active = [s for s in suppressions["items"] if s["active"]]
        self.assertEqual(len(active), 1)

        status, _, lead = self.request(
            "POST",
            f"/api/v2/leads/{lead_id}/unsuppress",
            headers=h,
            payload={
                "suppression_id": active[0]["suppression_id"],
                "reason": "reviewed and approved",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(lead["do_not_contact"], 0)
        self.assertEqual(lead["status"], "New")

        status, _, filtered = self.request(
            "GET",
            "/api/v2/leads?suppressed=false&limit=50",
            headers=h,
        )
        self.assertEqual(status, 200)
        self.assertIn(lead_id, {item["lead_id"] for item in filtered["items"]})

        status, _, campaign_members = self.request(
            "GET",
            f"/api/v2/campaigns/{campaign_id}/members",
            headers=h,
        )
        self.assertEqual(status, 200)
        self.assertEqual(campaign_members["items"][0]["user_id"], "agent-ui")

        for suffix in ("contacts", "assignments", "transitions", "events"):
            status, _, body = self.request(
                "GET",
                f"/api/v2/leads/{lead_id}/{suffix}",
                headers=h,
            )
            self.assertEqual(status, 200)
            self.assertIn("items", body)

    def test_candidate_summary_and_promote_action(self):
        init_db(self.db)
        with db_connection(self.db) as conn:
            conn.execute(
                """
                INSERT INTO candidate_leads(
                    candidate_id,batch_id,contact_name,business_name,country,
                    business_category,phones_json,email,notes,source_file,
                    source_row,source_fingerprint,disposition,source_payload,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    "cand-ui-1",
                    "ui-batch",
                    "Candidate UI",
                    "Candidate UI",
                    "Dominican Republic",
                    "Certification",
                    json.dumps(["8095559292"]),
                    None,
                    "dashboard candidate",
                    "unit-test.xlsx",
                    1,
                    "fingerprint-ui-1",
                    "new",
                    "{}",
                    now_utc(),
                ),
            )

        status, _, summary = self.request(
            "GET",
            "/api/v2/candidates/summary?batch_id=ui-batch",
            headers=self.headers(),
        )
        self.assertEqual(status, 200)
        self.assertEqual(summary["by_disposition"]["new"], 1)

        status, _, result = self.request(
            "POST",
            "/api/v2/candidates/promote",
            headers=self.headers(),
            payload={"batch_id": "ui-batch"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["promoted"], 1)

        status, _, summary = self.request(
            "GET",
            "/api/v2/candidates/summary?batch_id=ui-batch",
            headers=self.headers(),
        )
        self.assertEqual(status, 200)
        self.assertEqual(summary["by_disposition"]["promoted"], 1)


if __name__ == "__main__":
    unittest.main()

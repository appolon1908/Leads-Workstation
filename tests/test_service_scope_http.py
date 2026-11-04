import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from leads_workstation.api import make_handler
from leads_workstation.db import create_lead, get_lead
from leads_workstation.platform import (
    add_campaign_member,
    add_contact_point,
    create_campaign,
)


class ServiceCampaignHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "service.db"
        for campaign in ("campaign-a", "campaign-b", "campaign-other"):
            create_campaign(
                self.db,
                {
                    "campaign_id": campaign,
                    "campaign_code": campaign,
                    "name": campaign,
                    "campaign_type": "outbound",
                    "state": "active",
                },
                actor="synthetic-fixture",
            )
            add_campaign_member(self.db, campaign, "agent-fixture", "agent")
        self.leads = {}
        for campaign in ("campaign-a", "campaign-other", None):
            self.leads[campaign] = create_lead(
                self.db,
                {
                    "business_name": f"Synthetic {campaign}",
                    "country": "Test",
                    "business_category": "Test",
                    "campaign_id": campaign,
                },
                actor="synthetic-fixture",
            )
        self.env = patch.dict(
            os.environ,
            {
                "LEADS_AUTH_MODE": "service",
                "LEADS_SERVICE_TOKEN": "synthetic-service-token",
                "LEADS_SERVICE_ALLOWED_CIDRS": "127.0.0.0/8",
                "LEADS_SERVICE_CAMPAIGNS": "campaign-a,campaign-b",
            },
            clear=True,
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.db))
        self.addCleanup(self.server.server_close)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 5)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def request(self, path, method="GET", payload=None):
        headers = {"Authorization": "Bearer synthetic-service-token", "If-Match": '"1"'}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            self.base + path,
            method=method,
            headers=headers,
            data=json.dumps(payload).encode() if payload is not None else None,
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            return exc.code, json.load(exc)

    def test_finite_scope_filters_lead_and_campaign_lists(self):
        status, body = self.request("/api/v2/leads")
        self.assertEqual(status, 200)
        self.assertEqual(
            [lead["lead_id"] for lead in body["items"]],
            [self.leads["campaign-a"]["lead_id"]],
        )
        status, body = self.request("/api/v2/campaigns")
        self.assertEqual(status, 200)
        self.assertEqual(
            {c["campaign_id"] for c in body["items"]}, {"campaign-a", "campaign-b"}
        )

    def test_finite_scope_rejects_outside_lead_reads_and_mutations(self):
        for campaign in ("campaign-other", None):
            lead_id = self.leads[campaign]["lead_id"]
            for suffix in (
                "",
                "/contacts",
                "/events",
                "/assignments",
                "/transitions",
                "/suppressions",
            ):
                with self.subTest(campaign=campaign, suffix=suffix):
                    self.assertEqual(
                        self.request(f"/api/v2/leads/{lead_id}{suffix}")[0], 403
                    )
            self.assertEqual(
                self.request(f"/api/v2/leads/{lead_id}", "PATCH", {"notes": "blocked"})[
                    0
                ],
                403,
            )
            for action, payload in (
                ("transition", {"to_status": "Qualified"}),
                ("contacts", {"kind": "email", "value": "synthetic@example.com"}),
                ("suppress", {"channel": "all", "reason": "synthetic"}),
                ("unsuppress", {"reason": "synthetic"}),
                ("consent", {"status": "opted_in", "source": "synthetic"}),
            ):
                with self.subTest(campaign=campaign, action=action):
                    self.assertEqual(
                        self.request(
                            f"/api/v2/leads/{lead_id}/{action}", "POST", payload
                        )[0],
                        403,
                    )
            contact = add_contact_point(
                self.db,
                lead_id,
                "email",
                "synthetic@example.com",
                actor="synthetic-fixture",
            )
            self.assertEqual(
                self.request(
                    f"/api/v2/contact-points/{contact['contact_point_id']}/verify",
                    "POST",
                    {"verification_status": "verified"},
                )[0],
                403,
            )
            self.assertEqual(get_lead(self.db, lead_id)["version"], 1)

    def test_finite_scope_allows_authorized_read_update_and_create(self):
        lead_id = self.leads["campaign-a"]["lead_id"]
        self.assertEqual(self.request(f"/api/v2/leads/{lead_id}")[0], 200)
        status, changed = self.request(
            f"/api/v2/leads/{lead_id}", "PATCH", {"notes": "allowed"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(changed["notes"], "allowed")
        status, created = self.request(
            "/api/v2/leads",
            "POST",
            {
                "business_name": "Synthetic allowed creation",
                "country": "Test",
                "business_category": "Test",
                "campaign_id": "campaign-b",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(created["campaign_id"], "campaign-b")

    def test_finite_scope_rejects_outside_or_unassigned_creation_and_patch(self):
        lead_id = self.leads["campaign-a"]["lead_id"]
        for campaign in ("campaign-other", None, ""):
            with self.subTest(campaign=campaign):
                self.assertEqual(
                    self.request(
                        "/api/v2/leads",
                        "POST",
                        {
                            "business_name": "Synthetic blocked creation",
                            "country": "Test",
                            "business_category": "Test",
                            "campaign_id": campaign,
                        },
                    )[0],
                    403,
                )
                self.assertEqual(
                    self.request(
                        f"/api/v2/leads/{lead_id}", "PATCH", {"campaign_id": campaign}
                    )[0],
                    403,
                )
                self.assertEqual(
                    get_lead(self.db, lead_id)["campaign_id"], "campaign-a"
                )
                self.assertEqual(get_lead(self.db, lead_id)["version"], 1)

    def test_finite_scope_checks_assignment_source_and_destination(self):
        allowed = self.leads["campaign-a"]["lead_id"]
        outside = self.leads["campaign-other"]["lead_id"]
        for lead_id, destination in (
            (allowed, "campaign-other"),
            (outside, "campaign-a"),
        ):
            for strategy in ("manual", "round_robin"):
                with self.subTest(lead_id=lead_id, strategy=strategy):
                    self.assertEqual(
                        self.request(
                            f"/api/v2/leads/{lead_id}/assign",
                            "POST",
                            {
                                "campaign_id": destination,
                                "to_agent": "agent-fixture",
                                "strategy": strategy,
                            },
                        )[0],
                        403,
                    )
                    self.assertEqual(get_lead(self.db, lead_id)["version"], 1)
        status, changed = self.request(
            f"/api/v2/leads/{allowed}/assign",
            "POST",
            {
                "campaign_id": "campaign-b",
                "to_agent": "agent-fixture",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(changed["campaign_id"], "campaign-b")

    def test_network_metrics_requires_global_service_scope(self):
        # A distinct loopback source exercises the non-local socket-peer branch.
        for scope, expected in (("campaign-a", 403), ("*", 200)):
            with (
                self.subTest(scope=scope),
                patch.dict(os.environ, {"LEADS_SERVICE_CAMPAIGNS": scope}),
            ):
                connection = HTTPConnection(
                    "127.0.0.1",
                    self.server.server_port,
                    timeout=5,
                    source_address=("127.0.0.2", 0),
                )
                try:
                    connection.request(
                        "GET",
                        "/metrics",
                        headers={
                            "Authorization": "Bearer synthetic-service-token",
                        },
                    )
                    response = connection.getresponse()
                    self.assertEqual(response.status, expected)
                    response.read()
                finally:
                    connection.close()

    def test_finite_scope_checks_campaign_members_and_global_read_endpoints(self):
        self.assertEqual(self.request("/api/v2/campaigns/campaign-a/members")[0], 200)
        self.assertEqual(
            self.request("/api/v2/campaigns/campaign-other/members")[0], 403
        )
        for path in (
            "/api/v2/stats",
            "/api/v2/outbox",
            "/api/v2/candidates",
            "/api/v2/candidates/summary",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 403)
        self.assertEqual(
            self.request(
                "/api/v2/dedupe/preview", "POST", {"business_name": "Synthetic"}
            )[0],
            403,
        )

    def test_explicit_wildcard_preserves_global_reads_and_writes(self):
        with patch.dict(os.environ, {"LEADS_SERVICE_CAMPAIGNS": "*"}):
            status, body = self.request("/api/v2/leads")
            self.assertEqual(status, 200)
            self.assertEqual(len(body["items"]), 3)
            status, body = self.request("/api/v2/campaigns")
            self.assertEqual(status, 200)
            self.assertEqual(len(body["items"]), 3)
            for campaign in ("campaign-other", None):
                lead_id = self.leads[campaign]["lead_id"]
                self.assertEqual(self.request(f"/api/v2/leads/{lead_id}")[0], 200)
                self.assertEqual(
                    self.request(
                        f"/api/v2/leads/{lead_id}", "PATCH", {"notes": "global allowed"}
                    )[0],
                    200,
                )
            self.assertEqual(
                self.request(
                    "/api/v2/leads",
                    "POST",
                    {
                        "business_name": "Synthetic global creation",
                        "country": "Test",
                        "business_category": "Test",
                    },
                )[0],
                201,
            )
            for path in (
                "/api/v2/stats",
                "/api/v2/outbox",
                "/api/v2/candidates",
                "/api/v2/candidates/summary",
            ):
                with self.subTest(path=path):
                    self.assertEqual(self.request(path)[0], 200)
            self.assertEqual(
                self.request(
                    "/api/v2/dedupe/preview", "POST", {"business_name": "Synthetic"}
                )[0],
                200,
            )


if __name__ == "__main__":
    unittest.main()

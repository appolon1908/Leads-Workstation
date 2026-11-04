import tempfile
import unittest
from pathlib import Path

from leads_workstation.auth import (
    AuthorizationError,
    context_from_claims,
    require_permission,
)
from leads_workstation.db import (
    ConcurrencyError,
    DuplicateLeadError,
    create_lead,
    update_lead,
)
from leads_workstation.dedupe import find_duplicate_candidates
from leads_workstation.metrics import prometheus_metrics
from leads_workstation.platform import (
    SuppressedLeadError,
    add_campaign_member,
    add_contact_point,
    assign_round_robin,
    create_campaign,
    lift_suppression,
    list_assignments,
    list_contact_points,
    list_outbox,
    register_webhook_subscription,
    suppress_lead,
    transition_lead,
    update_campaign,
)
from leads_workstation.worker import process_outbox_once


class V2PlatformTests(unittest.TestCase):
    def test_api_supplied_lead_id_cannot_bypass_dedupe(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "leads.db"
            create_lead(
                db,
                {
                    "lead_id": "lead_custom_a",
                    "business_name": "Alpha",
                    "country": "Dominican Republic",
                    "business_category": "Services",
                    "email": "same@example.com",
                },
            )
            with self.assertRaises(DuplicateLeadError):
                create_lead(
                    db,
                    {
                        "lead_id": "lead_custom_b",
                        "business_name": "Different Name",
                        "country": "Dominican Republic",
                        "business_category": "Services",
                        "email": "same@example.com",
                    },
                )

    def test_optimistic_lock_and_identity_refresh(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "leads.db"
            lead = create_lead(
                db,
                {
                    "business_name": "Versioned",
                    "country": "Dominican Republic",
                    "business_category": "Services",
                    "email": "versioned@example.com",
                },
            )
            changed = update_lead(
                db,
                lead["lead_id"],
                {"phone": "809-555-0101"},
                expected_version=1,
            )
            self.assertEqual(changed["version"], 2)
            self.assertTrue(changed["identity_fingerprint"])
            with self.assertRaises(ConcurrencyError):
                update_lead(
                    db,
                    lead["lead_id"],
                    {"city": "Santo Domingo"},
                    expected_version=1,
                )

    def test_campaign_round_robin_lifecycle_and_suppression(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "leads.db"
            campaign = create_campaign(
                db,
                {
                    "campaign_code": "TEST-OUT",
                    "name": "Test Outbound",
                    "campaign_type": "outbound",
                    "state": "active",
                    "primary_supervisor": "sup-1",
                },
                actor="admin",
            )
            add_campaign_member(db, campaign["campaign_id"], "agent-a", "agent")
            add_campaign_member(db, campaign["campaign_id"], "agent-b", "agent")

            leads = []
            for idx in range(2):
                leads.append(
                    create_lead(
                        db,
                        {
                            "business_name": f"Lead {idx}",
                            "country": "Dominican Republic",
                            "business_category": "Services",
                            "email": f"lead{idx}@example.com",
                        },
                    )
                )

            first = assign_round_robin(
                db,
                leads[0]["lead_id"],
                campaign["campaign_id"],
                assigned_by="sup-1",
            )
            second = assign_round_robin(
                db,
                leads[1]["lead_id"],
                campaign["campaign_id"],
                assigned_by="sup-1",
            )
            self.assertNotEqual(first["assigned_agent"], second["assigned_agent"])
            self.assertEqual(len(list_assignments(db, leads[0]["lead_id"])), 1)

            attempted = transition_lead(
                db,
                leads[0]["lead_id"],
                "Attempted",
                actor=first["assigned_agent"],
                expected_version=first["version"],
            )
            self.assertEqual(attempted["status"], "Attempted")

            suppressed = suppress_lead(
                db,
                leads[0]["lead_id"],
                channel="call",
                reason="customer request",
                actor="sup-1",
                jurisdiction="DO",
            )
            self.assertEqual(suppressed["do_not_contact"], 1)
            self.assertEqual(suppressed["status"], "DNC")
            with self.assertRaises(SuppressedLeadError):
                # Directly force a status that would be an outreach state by
                # creating a fresh lead and suppressing before assignment.
                assign_round_robin(
                    db,
                    leads[0]["lead_id"],
                    campaign["campaign_id"],
                    assigned_by="sup-1",
                )

    def test_multi_contact_points_and_outbox_worker(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "leads.db"
            lead = create_lead(
                db,
                {
                    "business_name": "Contacts",
                    "country": "Dominican Republic",
                    "business_category": "Services",
                    "phone": "809-555-1000",
                },
            )
            add_contact_point(
                db,
                lead["lead_id"],
                "phone",
                "829-555-2000",
                label="mobile",
                source="unit-test",
            )
            contacts = list_contact_points(db, lead["lead_id"])
            phones = {c["normalized_value"] for c in contacts if c["kind"] == "phone"}
            self.assertEqual(phones, {"8095551000", "8295552000"})

            pending = list_outbox(db, status="pending")
            self.assertGreaterEqual(len(pending), 2)
            result = process_outbox_once(db)
            self.assertGreaterEqual(result["published"], 2)
            self.assertEqual(len(list_outbox(db, status="pending")), 0)

    def test_rbac_claims_and_permissions(self):
        ctx = context_from_claims(
            {
                "sub": "agent-1",
                "iss": "https://keycloak.example/realms/codestra",
                "realm_access": {"roles": ["agent"]},
                "campaigns": ["cmp-a"],
            },
            "leads-workstation",
        )
        require_permission(ctx, "lead:read")
        with self.assertRaises(AuthorizationError):
            require_permission(ctx, "lead:assign")
        self.assertEqual(ctx.campaign_ids, frozenset({"cmp-a"}))

    def test_metrics_include_v2_gauges(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "leads.db"
            create_lead(
                db,
                {
                    "business_name": "Metrics",
                    "country": "Dominican Republic",
                    "business_category": "Services",
                    "email": "metrics@example.com",
                },
            )
            output = prometheus_metrics(db)
            self.assertIn("leads_total 1", output)
            self.assertIn("leads_outbox_pending_total", output)

    def test_campaign_update_suppression_lift_and_alternate_contact_dedupe(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "leads.db"
            campaign = create_campaign(
                db,
                {
                    "campaign_code": "UPDATE-TEST",
                    "name": "Original",
                    "campaign_type": "outbound",
                    "state": "draft",
                },
                actor="admin",
            )
            changed_campaign = update_campaign(
                db,
                campaign["campaign_id"],
                {"name": "Updated", "state": "active"},
                actor="admin",
            )
            self.assertEqual(changed_campaign["name"], "Updated")
            self.assertEqual(changed_campaign["state"], "active")

            lead = create_lead(
                db,
                {
                    "business_name": "Alternate Contact",
                    "country": "Dominican Republic",
                    "business_category": "Services",
                    "email": "primary@example.com",
                    "phone": "809-555-3000",
                },
            )
            add_contact_point(
                db,
                lead["lead_id"],
                "email",
                "alternate@example.com",
                label="alternate",
                source="unit-test",
            )
            matches = find_duplicate_candidates(
                db,
                {
                    "business_name": "Completely Different",
                    "country": "Dominican Republic",
                    "business_category": "Services",
                    "email": "alternate@example.com",
                },
            )
            self.assertEqual(matches[0]["lead_id"], lead["lead_id"])
            self.assertEqual(matches[0]["classification"], "duplicate")

            suppressed = suppress_lead(
                db,
                lead["lead_id"],
                channel="call",
                reason="temporary request",
                actor="admin",
            )
            self.assertEqual(suppressed["status"], "DNC")
            lifted = lift_suppression(
                db,
                lead["lead_id"],
                actor="admin",
                channel="call",
                reason="customer re-authorized",
            )
            self.assertEqual(lifted["do_not_contact"], 0)
            self.assertEqual(lifted["status"], "New")

    def test_webhook_registration_rejects_private_ip_without_opt_in(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "leads.db"
            with self.assertRaises(ValueError):
                register_webhook_subscription(
                    db,
                    name="blocked",
                    url="https://169.254.169.254/hook",
                    secret_ref="env://TEST_WEBHOOK_SECRET",
                    event_types=["lead.created"],
                )
            item = register_webhook_subscription(
                db,
                name="loopback",
                url="http://127.0.0.1:9999/hook",
                secret_ref="env://TEST_WEBHOOK_SECRET",
                event_types=["lead.created"],
            )
            self.assertEqual(item["name"], "loopback")


if __name__ == "__main__":
    unittest.main()

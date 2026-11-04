import tempfile
import unittest
from pathlib import Path

from leads_workstation.db import (
    create_lead,
    init_db,
    lead_events,
    list_leads,
    stats,
    update_lead,
)


class ApiFoundationTests(unittest.TestCase):
    def test_empty_stats(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "empty.db"
            init_db(db)
            self.assertEqual(stats(db)["total_leads"], 0)

    def test_create_update_and_audit(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "leads.db"
            lead = create_lead(
                db,
                {
                    "business_name": "Codestra Test",
                    "contact_name": "Test Contact",
                    "country": "Dominican Republic",
                    "business_category": "Test",
                    "email": "test@example.com",
                    "status": "New",
                },
                actor="unit-test",
            )
            self.assertEqual(lead["normalized_email"], "test@example.com")
            changed = update_lead(db, lead["lead_id"], {"status": "Qualified"}, actor="unit-test")
            self.assertEqual(changed["status"], "Qualified")
            events = lead_events(db, lead["lead_id"])
            self.assertEqual([e["event_type"] for e in events], ["updated", "created"])

    def test_list_leads_campaign_scope_is_parameterized_and_empty_scope_denies_all(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "scope.db"
            leads = []
            for name, campaign in (("Alpha", "campaign-a"), ("Bravo", "campaign-b"), ("Charlie", None)):
                leads.append(create_lead(db, {
                    "business_name": name, "country": "Test", "business_category": "Test",
                    "campaign_id": campaign,
                }, actor="synthetic-fixture"))
            for scope, expected in (
                (None, [lead["lead_id"] for lead in leads]),
                ([], []),
                (["campaign-a"], [leads[0]["lead_id"]]),
                (["campaign-a", "campaign-b"], [leads[0]["lead_id"], leads[1]["lead_id"]]),
                (["campaign-a') OR 1=1 --"], []),
            ):
                with self.subTest(scope=scope):
                    self.assertEqual([lead["lead_id"] for lead in list_leads(db, campaign_ids=scope)], expected)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from leads_workstation.db import create_lead, init_db, lead_events, stats, update_lead


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


if __name__ == "__main__":
    unittest.main()

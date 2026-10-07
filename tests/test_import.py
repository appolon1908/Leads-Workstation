import csv
import tempfile
import unittest
from pathlib import Path
from leads_workstation.db import import_csv, stats

class ImportTests(unittest.TestCase):
    def test_import_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); src = root / "leads.csv"; db = root / "leads.db"
            with src.open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=["lead_id","company","full_name","country","lead_category","email_primary","mobile"])
                w.writeheader()
                w.writerow({"lead_id":"l1","company":"Acme","full_name":"Ana Doe","country":"Dominican Republic","lead_category":"Hardware Stores","email_primary":"ana@example.com","mobile":"8095550100"})
            first = import_csv(db, src, "batch-1")
            second = import_csv(db, src, "batch-1")
            s = stats(db)
            self.assertEqual(first["rows_inserted"], 1)
            self.assertEqual(second["rows_inserted"], 1)
            self.assertEqual(s["total_leads"], 1)
            self.assertEqual(s["countries"][0]["country"], "Dominican Republic")
            self.assertEqual(s["categories"][0]["business_category"], "Hardware Stores")
if __name__ == "__main__":
    unittest.main()

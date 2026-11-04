import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from leads_workstation.candidates import (
    candidate_summary,
    list_candidates,
    promote_new_candidates,
)
from leads_workstation.db import db_connection, get_lead, init_db, now_utc, stats


class CandidateTests(unittest.TestCase):
    def test_candidate_promotion(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "leads.db"
            init_db(db)
            fp = hashlib.sha256(b"candidate-1").hexdigest()
            with db_connection(db) as conn:
                conn.execute(
                    """
                    INSERT INTO candidate_leads(
                        candidate_id,batch_id,contact_name,business_name,country,business_category,
                        phones_json,email,notes,source_file,source_row,source_fingerprint,
                        disposition,source_payload,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        "cand_test",
                        "batch-test",
                        "Test Appraiser",
                        "Test Appraiser",
                        "Dominican Republic",
                        "Independent Property Appraisers",
                        json.dumps(["8095550101"]),
                        None,
                        "Historical test source",
                        "test.xlsx",
                        6,
                        fp,
                        "new",
                        "[]",
                        now_utc(),
                    ),
                )

            before = candidate_summary(db, "batch-test")
            self.assertEqual(before["by_disposition"]["new"], 1)

            result = promote_new_candidates(db, "batch-test", actor="unit-test")
            self.assertEqual(result, {"promoted": 1, "failed": 0})

            after = candidate_summary(db, "batch-test")
            self.assertEqual(after["by_disposition"]["promoted"], 1)
            rows = list_candidates(db, "batch-test")
            self.assertEqual(rows[0]["disposition"], "promoted")
            self.assertEqual(rows[0]["phones"], ["8095550101"])

            lead_id = rows[0]["match_lead_id"]
            lead = get_lead(db, lead_id)
            self.assertEqual(lead["status"], "Needs Verification")
            self.assertEqual(lead["verification_status"], "Historical source - unverified")
            self.assertEqual(stats(db)["total_leads"], 1)


if __name__ == "__main__":
    unittest.main()

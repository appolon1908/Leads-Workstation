import os
import tempfile
import unittest
from pathlib import Path

from leads_workstation.backup import create_encrypted_backup, decrypt_file
from leads_workstation.db import create_lead, stats


class V2BackupTests(unittest.TestCase):
    def test_encrypted_sqlite_backup_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.db"
            encrypted = root / "source.clwv2"
            restored = root / "restored.db"
            create_lead(
                source,
                {
                    "business_name": "Backup Lead",
                    "country": "Dominican Republic",
                    "business_category": "Certification",
                    "email": "backup@example.com",
                },
            )
            old = os.environ.get("LEADS_TEST_BACKUP_KEY")
            os.environ["LEADS_TEST_BACKUP_KEY"] = "certification-key-not-production"
            try:
                result = create_encrypted_backup(
                    source,
                    encrypted,
                    "env://LEADS_TEST_BACKUP_KEY",
                )
                self.assertTrue(result["encrypted"])
                self.assertTrue(encrypted.read_bytes().startswith(b"CLWV2ENC1"))
                decrypt_file(
                    encrypted,
                    restored,
                    "env://LEADS_TEST_BACKUP_KEY",
                )
                self.assertEqual(stats(restored)["total_leads"], 1)
            finally:
                if old is None:
                    os.environ.pop("LEADS_TEST_BACKUP_KEY", None)
                else:
                    os.environ["LEADS_TEST_BACKUP_KEY"] = old


if __name__ == "__main__":
    unittest.main()

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from leads_workstation.backup import create_encrypted_backup, decrypt_file
from leads_workstation.db import create_lead, get_lead, init_db, stats
from leads_workstation.platform import add_contact_point, verify_contact_point

try:
    import cryptography  # noqa: F401
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


class V2UpgradeTests(unittest.TestCase):
    def test_v1_sqlite_is_upgraded_in_place(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "v1.db"
            conn = sqlite3.connect(db)
            conn.executescript(
                """
                PRAGMA foreign_keys=ON;
                CREATE TABLE workstation_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                INSERT INTO workstation_meta(key,value)
                VALUES('schema_version','1');

                CREATE TABLE leads (
                    lead_id TEXT PRIMARY KEY,
                    business_name TEXT NOT NULL,
                    contact_name TEXT,
                    country TEXT NOT NULL,
                    state_province TEXT,
                    city TEXT,
                    business_category TEXT NOT NULL,
                    campaign_source TEXT,
                    email TEXT,
                    normalized_email TEXT,
                    phone TEXT,
                    normalized_phone TEXT,
                    website TEXT,
                    status TEXT NOT NULL,
                    owner TEXT,
                    priority TEXT,
                    notes TEXT,
                    source_file TEXT,
                    import_batch_id TEXT,
                    duplicate_fingerprint TEXT NOT NULL UNIQUE,
                    verification_status TEXT,
                    verification_score REAL,
                    data_quality_status TEXT,
                    source_payload TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE lead_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    event_at TEXT NOT NULL,
                    payload_json TEXT
                );
                INSERT INTO leads(
                    lead_id,business_name,contact_name,country,city,business_category,
                    email,normalized_email,phone,normalized_phone,status,
                    duplicate_fingerprint,created_at,updated_at
                ) VALUES(
                    'legacy-1','Legacy Company','Legacy Contact','Dominican Republic',
                    'Santo Domingo','Legacy','legacy@example.com','legacy@example.com',
                    '8095551234','8095551234','New','legacy-fingerprint',
                    '2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00'
                );
                """
            )
            conn.commit()
            conn.close()

            init_db(db)
            result = stats(db)
            self.assertEqual(result["schema_version"], 2)
            lead = get_lead(db, "legacy-1")
            self.assertIsNotNone(lead["identity_fingerprint"])
            self.assertEqual(lead["version"], 1)
            self.assertEqual(lead["suppressed"], 0)

    def test_contact_verification_updates_primary_lead(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "verify.db"
            lead = create_lead(
                db,
                {
                    "business_name": "Verify Contact",
                    "country": "Dominican Republic",
                    "business_category": "Verification",
                    "email": "verify@example.com",
                },
            )
            # create_lead creates the primary email point; fetch it through SQL-free
            # public operations by adding the same normalized value.
            contact = add_contact_point(
                db,
                lead["lead_id"],
                "email",
                "verify@example.com",
                primary=True,
                source="unit-test",
            )
            verified = verify_contact_point(
                db,
                contact["contact_point_id"],
                verification_status="valid",
                actor="qa-user",
                source="qa-check",
            )
            self.assertEqual(verified["verification_status"], "valid")
            self.assertEqual(
                get_lead(db, lead["lead_id"])["verification_status"], "valid"
            )

    @unittest.skipUnless(HAS_CRYPTOGRAPHY, "cryptography dependency not installed")
    def test_encrypted_sqlite_backup_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "source.db"
            encrypted = root / "source.db.enc"
            restored = root / "restored.db"
            lead = create_lead(
                db,
                {
                    "business_name": "Backup Test",
                    "country": "Dominican Republic",
                    "business_category": "Backup",
                    "email": "backup@example.com",
                },
            )
            os.environ["LW_TEST_BACKUP_KEY"] = "test-only-backup-key-material"
            try:
                result = create_encrypted_backup(
                    db,
                    encrypted,
                    "env://LW_TEST_BACKUP_KEY",
                )
                self.assertTrue(result["encrypted"])
                self.assertNotIn(b"backup@example.com", encrypted.read_bytes())
                decrypt_file(
                    encrypted,
                    restored,
                    "env://LW_TEST_BACKUP_KEY",
                )
                restored_lead = get_lead(restored, lead["lead_id"])
                self.assertEqual(
                    restored_lead["normalized_email"], "backup@example.com"
                )
            finally:
                os.environ.pop("LW_TEST_BACKUP_KEY", None)


if __name__ == "__main__":
    unittest.main()

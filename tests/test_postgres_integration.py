import os
import tempfile
import time
import unittest
from pathlib import Path

from leads_workstation.db import create_lead, init_db, stats
from leads_workstation.migrate import (
    compare_database_counts,
    migrate_sqlite_to_postgres,
)
from leads_workstation.platform import (
    add_campaign_member,
    assign_lead,
    create_campaign,
    list_contact_points,
    transition_lead,
)

POSTGRES_DSN = os.getenv("LEADS_POSTGRES_TEST_DSN", "")
REDIS_URL = os.getenv("REDIS_TEST_URL", "")


@unittest.skipUnless(
    POSTGRES_DSN and os.getenv("LEADS_ALLOW_TEST_RESET") == "1",
    "PostgreSQL integration test DSN/reset flag not configured",
)
class PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if "test" not in POSTGRES_DSN.lower() and "cert" not in POSTGRES_DSN.lower():
            raise RuntimeError(
                "Refusing PostgreSQL integration reset: DSN must contain test or cert"
            )
        try:
            import psycopg
        except ImportError as exc:
            raise unittest.SkipTest("psycopg is not installed") from exc
        cls.psycopg = psycopg

    def setUp(self):
        with self.psycopg.connect(POSTGRES_DSN, autocommit=True) as conn:
            conn.execute("DROP SCHEMA public CASCADE")
            conn.execute("CREATE SCHEMA public")

    def test_postgres_schema_and_domain_operations(self):
        init_db(POSTGRES_DSN)
        self.assertEqual(stats(POSTGRES_DSN)["backend"], "postgres")
        self.assertEqual(stats(POSTGRES_DSN)["schema_version"], 2)

        campaign = create_campaign(
            POSTGRES_DSN,
            {
                "campaign_code": "PG-CERT",
                "name": "PostgreSQL Certification",
                "campaign_type": "outbound",
                "state": "active",
                "primary_supervisor": "supervisor-pg",
            },
            actor="certifier",
        )
        add_campaign_member(
            POSTGRES_DSN, campaign["campaign_id"], "agent-pg", "agent"
        )
        lead = create_lead(
            POSTGRES_DSN,
            {
                "business_name": "Postgres Lead",
                "contact_name": "Integration Test",
                "country": "Dominican Republic",
                "business_category": "Certification",
                "email": "pg-cert@example.com",
                "phone": "809-555-7711",
            },
            actor="certifier",
        )
        assigned = assign_lead(
            POSTGRES_DSN,
            lead["lead_id"],
            campaign["campaign_id"],
            "agent-pg",
            assigned_by="supervisor-pg",
            expected_version=lead["version"],
        )
        attempted = transition_lead(
            POSTGRES_DSN,
            lead["lead_id"],
            "Attempted",
            actor="agent-pg",
            expected_version=assigned["version"],
        )
        self.assertEqual(attempted["status"], "Attempted")
        self.assertEqual(attempted["assigned_agent"], "agent-pg")
        self.assertEqual(len(list_contact_points(POSTGRES_DSN, lead["lead_id"])), 2)

    def test_sqlite_to_postgres_migration_count_parity(self):
        with tempfile.TemporaryDirectory() as td:
            sqlite_db = Path(td) / "source.db"
            for idx in range(5):
                create_lead(
                    sqlite_db,
                    {
                        "business_name": f"Migrated {idx}",
                        "country": "Dominican Republic",
                        "business_category": "Migration Test",
                        "email": f"migrate-{idx}@example.com",
                    },
                )
            result = migrate_sqlite_to_postgres(
                sqlite_db, POSTGRES_DSN, batch_size=2
            )
            self.assertEqual(result["tables"]["leads"]["selected"], 5)
            comparison = compare_database_counts(sqlite_db, POSTGRES_DSN)
            self.assertTrue(comparison["all_match"], comparison)

    def test_redis_connectivity_when_configured(self):
        if not REDIS_URL:
            self.skipTest("REDIS_TEST_URL not configured")
        try:
            import redis
        except ImportError as exc:
            self.skipTest(f"redis client unavailable: {exc}")
        client = redis.Redis.from_url(
            REDIS_URL, socket_timeout=2, decode_responses=True
        )
        try:
            last_error = None
            for attempt in range(5):
                try:
                    self.assertTrue(client.ping())
                    client.set("codestra:leads:v2:cert", "ok", ex=30)
                    self.assertEqual(client.get("codestra:leads:v2:cert"), "ok")
                    last_error = None
                    break
                except redis.RedisError as exc:
                    last_error = exc
                    if attempt == 4:
                        break
                    time.sleep(1)
            if last_error is not None:
                raise last_error
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()

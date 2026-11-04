from contextlib import contextmanager
from uuid import UUID

from fastapi.testclient import TestClient

from app import main


def test_timestamp_candidate_retry_is_idempotent(monkeypatch):
    candidate_id = UUID("00000000-0000-4000-8000-000000000001")
    payload = {
        "import_batch_id": "00000000-0000-4000-8000-000000000002",
        "source_row": 1,
        "source_fingerprint": "synthetic-row",
        "lead": {
            "business_name": "Synthetic Test Company",
            "country": "DO",
            "business_category": "Testing",
            "last_contact_at": "2026-11-03T12:00:00+00:00",
        },
    }
    stored = {
        "candidate_id": candidate_id,
        "normalized_payload": {**payload["lead"], "status": "new"},
    }

    class Cursor:
        def __init__(self, responses):
            self.responses = iter(responses)
            self.writes = []

        def execute(self, sql, params):
            if sql.strip().lower().startswith(("insert", "update", "delete")):
                self.writes.append((sql, params))

        def fetchone(self):
            return next(self.responses)

    created = Cursor([{"status": "completed"}, {"exists": 1}, None, stored])
    retried = Cursor([{"status": "completed"}, {"exists": 1}, stored])
    changed = Cursor([{"status": "completed"}, {"exists": 1}, stored])
    cursors = iter([created, retried, changed])

    @contextmanager
    def fake_db():
        yield object(), next(cursors)

    monkeypatch.setattr(main, "db", fake_db)
    client = TestClient(main.app)
    first = client.post("/api/promotion-candidates", json=payload)
    assert first.status_code == 201
    assert first.json()["created"] is True
    assert len(created.writes) == 2  # Candidate and audit only.
    assert created.writes[0][1][3].obj == stored["normalized_payload"]

    second = client.post("/api/promotion-candidates", json=payload)
    assert second.status_code == 201
    assert second.json()["created"] is False
    assert second.json()["canonical_writes_performed"] == 0
    assert retried.writes == []

    payload["lead"]["last_contact_at"] = "2026-11-03T13:00:00+00:00"
    conflict = client.post("/api/promotion-candidates", json=payload)
    assert conflict.status_code == 409
    assert changed.writes == []

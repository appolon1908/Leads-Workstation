from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def paginated_client(monkeypatch):
    records = [{"lead_id": str(i), "country": "DO", "business_category": "Testing"}
               for i in range(603)]
    calls = []

    class Cursor:
        def execute(self, sql, params):
            calls.append((sql, params.copy()))
            self.sql, self.params = sql, params

        def fetchall(self):
            limit, offset = self.params[-2:] if "offset %s" in self.sql else (self.params[-1], 0)
            return records[offset:offset + limit]

        def fetchone(self):
            return {"total": len(records)}

    @contextmanager
    def fake_db():
        yield object(), Cursor()

    monkeypatch.setattr(main, "db", fake_db)
    return TestClient(main.app), calls


def test_pages_reach_records_beyond_original_500_limit(paginated_client):
    client, calls = paginated_client
    seen = []
    for offset in range(0, 603, 100):
        response = client.get("/api/leads", params={
            "paginated": "true", "limit": 100, "offset": offset,
            "country": "DO", "business_category": "Testing", "status": "qualified",
        })
        assert response.status_code == 200
        page = response.json()
        assert page["total"] == 603
        assert page["offset"] == offset
        assert page["limit"] == 100
        assert page["has_more"] == (offset + len(page["items"]) < 603)
        seen.extend(item["lead_id"] for item in page["items"])
    assert seen == [str(i) for i in range(603)]
    for sql, params in calls:
        assert "country=%s" in sql and "business_category=%s" in sql and "status=%s" in sql
        assert params[:3] == ["DO", "Testing", "qualified"]
        if sql.startswith("select *"):
            assert "order by updated_at desc, lead_id desc limit %s offset %s" in sql


def test_existing_list_shape_and_empty_page_total(paginated_client):
    client, _ = paginated_client
    legacy = client.get("/api/leads").json()
    assert isinstance(legacy, list) and len(legacy) == 500
    page = client.get("/api/leads?paginated=true&offset=1000&limit=100").json()
    assert page == {"items": [], "total": 603, "limit": 100, "offset": 1000, "has_more": False}


@pytest.mark.parametrize("query", ["offset=-1", "limit=0", "limit=5001"])
def test_invalid_pagination_is_rejected_before_database(paginated_client, query):
    client, calls = paginated_client
    assert client.get("/api/leads?" + query).status_code == 422
    assert calls == []

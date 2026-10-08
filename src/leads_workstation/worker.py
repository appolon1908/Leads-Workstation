from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any

from .db import init_db, now_utc
from .secrets import resolve_secret
from .storage import db_connection


def _signature(secret: str, timestamp: str, body: bytes) -> str:
    message = timestamp.encode("utf-8") + b"." + body
    return "sha256=" + hmac.new(
        secret.encode("utf-8"), message, hashlib.sha256
    ).hexdigest()


def _subscriptions(conn, event_type: str) -> list[dict[str, Any]]:
    rows = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM webhook_subscriptions WHERE active=1 ORDER BY name"
        )
    ]
    selected = []
    for row in rows:
        try:
            types = set(json.loads(row["event_types_json"] or "[]"))
        except (json.JSONDecodeError, TypeError):
            types = set()
        if "*" in types or event_type in types:
            selected.append(row)
    return selected


def _redis_notify(event_id: str) -> None:
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return
    try:
        import redis
    except ImportError:
        return
    client = redis.Redis.from_url(url, socket_timeout=2, decode_responses=True)
    try:
        client.publish("codestra:leads:outbox", event_id)
    finally:
        client.close()


def _post(subscription: dict[str, Any], event: dict[str, Any], timeout: int) -> None:
    body = event["payload_json"].encode("utf-8")
    timestamp = str(int(time.time()))
    secret = resolve_secret(subscription["secret_ref"])
    req = urllib.request.Request(
        subscription["url"],
        method="POST",
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Codestra-Leads-Workstation/2.0",
            "Idempotency-Key": event["idempotency_key"],
            "X-Codestra-Event-Id": event["event_id"],
            "X-Codestra-Event-Type": event["event_type"],
            "X-Codestra-Timestamp": timestamp,
            "X-Codestra-Signature": _signature(secret, timestamp, body),
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"webhook HTTP {response.status}")


def process_outbox_once(
    db_path,
    *,
    limit: int = 50,
    timeout: int = 10,
    max_attempts: int = 8,
) -> dict[str, int]:
    init_db(db_path)
    delivered = failed = skipped = 0

    with db_connection(db_path) as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM outbox_events "
                "WHERE status IN ('pending','retry') AND available_at<=? "
                "ORDER BY created_at LIMIT ?",
                (now_utc(), max(1, min(int(limit), 500))),
            )
        ]

    for event in rows:
        try:
            with db_connection(db_path) as conn:
                subscriptions = _subscriptions(conn, event["event_type"])
            if not subscriptions:
                skipped += 1
                with db_connection(db_path) as conn:
                    conn.execute(
                        "UPDATE outbox_events SET status='published',published_at=?,"
                        "last_error=? WHERE event_id=?",
                        (now_utc(), "no active subscriptions", event["event_id"]),
                    )
                _redis_notify(event["event_id"])
                continue

            for subscription in subscriptions:
                _post(subscription, event, timeout)

            delivered += 1
            with db_connection(db_path) as conn:
                conn.execute(
                    "UPDATE outbox_events SET status='published',published_at=?,"
                    "last_error=NULL WHERE event_id=?",
                    (now_utc(), event["event_id"]),
                )
            _redis_notify(event["event_id"])
        except Exception as exc:  # noqa: BLE001 - delivery boundary must convert provider failures into retry state
            failed += 1
            attempts = int(event.get("attempt_count") or 0) + 1
            status = "failed" if attempts >= max_attempts else "retry"
            delay = min(3600, 2 ** min(attempts, 10))
            available = (
                datetime.now(UTC) + timedelta(seconds=delay)
            ).replace(microsecond=0).isoformat()
            with db_connection(db_path) as conn:
                conn.execute(
                    "UPDATE outbox_events SET status=?,attempt_count=?,available_at=?,"
                    "last_error=? WHERE event_id=?",
                    (status, attempts, available, repr(exc)[:2000], event["event_id"]),
                )

    published = delivered + skipped
    return {
        "selected": len(rows),
        "processed": len(rows),
        "delivered": delivered,
        "published": published,
        "failed": failed,
        "skipped": skipped,
        "retried": failed,
    }


def run_worker(db_path, *, poll_seconds: float = 2.0) -> None:
    while True:
        process_outbox_once(db_path)
        time.sleep(max(0.2, float(poll_seconds)))

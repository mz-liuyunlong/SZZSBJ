"""Opt-in local-only Decodo testing without the PostgreSQL 0048 migration.

Only enabled with APP_ENV=local AND DECODO_LOCAL_TEST_MODE=1. Secrets live in
process environment and are never written to SQLite; usage and normalized
product snapshots are stored in a user-private SQLite database on this Mac.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.modules.decodo.schemas import DecodoConfigRead, DecodoUsageRead, DecodoUsageRow

US_ZONE = ZoneInfo("America/New_York")


def is_enabled() -> bool:
    if os.getenv("DECODO_LOCAL_TEST_MODE", "").strip() != "1":
        return False
    if os.getenv("APP_ENV", "").lower().strip() != "local":
        raise RuntimeError("DECODO_LOCAL_TEST_MODE requires APP_ENV=local")
    return True


def _zip_code() -> str:
    value = (os.getenv("DECODO_LOCAL_US_ZIP") or "10001").strip()
    if len(value) != 5 or not value.isascii() or not value.isdigit():
        raise ValueError("DECODO_LOCAL_US_ZIP must be exactly five ASCII digits")
    return value


def config_read() -> DecodoConfigRead:
    authorization = (os.getenv("DECODO_LOCAL_BASIC_AUTH") or "").strip()
    enabled = os.getenv("DECODO_LOCAL_TEST_ENABLE_REAL_CALLS", "") == "1"
    return DecodoConfigRead(
        configured=bool(authorization),
        enabled=enabled and bool(authorization),
        us_zip=_zip_code(),
        updated_at=None,
        updated_by=None,
        mode="local_test",
    )


def load_settings() -> tuple[str, str]:
    if os.getenv("DECODO_LOCAL_TEST_ENABLE_REAL_CALLS", "") != "1":
        raise ValueError("DECODO_LOCAL_REAL_CALLS_DISABLED")
    auth = (os.getenv("DECODO_LOCAL_BASIC_AUTH") or "").strip()
    if not auth:
        raise ValueError("DECODO_LOCAL_AUTH_MISSING")
    return auth, _zip_code()


def _database_path() -> Path:
    folder = Path.home() / ".szzsbj"
    if folder.is_symlink():
        raise RuntimeError("Local Decodo data directory must not be a symlink")
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    path = folder / "decodo-local-test.sqlite3"
    if path.is_symlink():
        raise RuntimeError("Local Decodo database must not be a symlink")
    return path


def _db() -> sqlite3.Connection:
    path = _database_path()
    conn = sqlite3.connect(path, timeout=30)
    try:
        os.chmod(path, 0o600)
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY, target TEXT NOT NULL,
                identifier TEXT NOT NULL, actor_ref TEXT NOT NULL,
                request_date_us TEXT NOT NULL, status TEXT NOT NULL,
                started_at TEXT NOT NULL, finished_at TEXT,
                duration_ms INTEGER, http_status INTEGER, error_code TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id TEXT PRIMARY KEY, target TEXT NOT NULL,
                sku_id TEXT NOT NULL, identifier TEXT NOT NULL,
                payload TEXT NOT NULL, fetched_at TEXT NOT NULL,
                actor_ref TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_decodo_local_usage
            ON requests(request_date_us, target, status)
        """)
        conn.commit()
    except BaseException:
        conn.close()
        raise
    return conn


def start_log(target: str, identifier: str, actor: str) -> str:
    event_id = str(uuid4())
    now = datetime.now(UTC)
    with _db() as conn:
        conn.execute(
            """INSERT INTO requests
               (id,target,identifier,actor_ref,request_date_us,status,started_at)
               VALUES (?,?,?,?,?,'pending',?)""",
            (
                event_id,
                target,
                identifier,
                actor,
                now.astimezone(US_ZONE).date().isoformat(),
                now.isoformat(),
            ),
        )
    return event_id


def finish_log(
    event_id: str,
    status: str,
    duration_ms: int,
    http_status: int | None,
    error_code: str | None,
) -> None:
    with _db() as conn:
        conn.execute(
            """UPDATE requests SET status=?, duration_ms=?, http_status=?,
               error_code=?, finished_at=? WHERE id=?""",
            (
                status,
                duration_ms,
                http_status,
                error_code,
                datetime.now(UTC).isoformat(),
                event_id,
            ),
        )


def usage_read(days: int) -> DecodoUsageRead:
    if not 1 <= days <= 31:
        raise ValueError("days must be 1..31")
    today = datetime.now(US_ZONE).date()
    first = today - timedelta(days=days - 1)
    result = {
        first + timedelta(days=i): DecodoUsageRow(date=first + timedelta(days=i))
        for i in range(days)
    }
    with _db() as conn:
        records = conn.execute(
            """SELECT request_date_us,target,status,COUNT(*) FROM requests
               WHERE request_date_us BETWEEN ? AND ?
               GROUP BY request_date_us,target,status""",
            (first.isoformat(), today.isoformat()),
        ).fetchall()
    for day, target, status, n in records:
        item = result[datetime.strptime(day, "%Y-%m-%d").date()]
        item.total += n
        if target == "amazon_product":
            item.amazon_requests += n
        else:
            item.walmart_requests += n
        if status == "success":
            item.success += n
        elif status == "failed":
            item.failed += n
        else:
            item.pending += n
    return DecodoUsageRead(today=today, days=list(reversed(result.values())))


def save_snapshot(
    *,
    target: str,
    sku_id: str,
    identifier: str,
    data: dict,
    actor: str,
) -> str:
    snapshot_id = str(uuid4())
    with _db() as conn:
        conn.execute(
            """INSERT INTO snapshots
               (id,target,sku_id,identifier,payload,fetched_at,actor_ref)
               VALUES (?,?,?,?,?,?,?)""",
            (
                snapshot_id,
                target,
                sku_id,
                identifier,
                json.dumps(data, ensure_ascii=False),
                datetime.now(UTC).isoformat(),
                actor,
            ),
        )
    return snapshot_id

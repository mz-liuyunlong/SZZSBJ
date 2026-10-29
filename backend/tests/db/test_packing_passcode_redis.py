"""Shared multi-worker confirmation budget on the explicitly enabled CI Redis."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from redis import Redis

from app.core.api import ApiError
from app.modules.pmc_domestic import packing_passcode as module
from tests.db.domestic_postgresql_support import admin_url


def test_atomic_attempt_budget_is_shared_between_workers(monkeypatch):
    admin_url()  # Same fail-closed, explicit opt-in as the disposable PostgreSQL job.
    client = Redis.from_url("redis://127.0.0.1:6379/15", socket_timeout=2)
    client.ping()
    actor = "synthetic-" + uuid4().hex
    fixed = 1700000000
    key = f"pmc:packing:passcode:{hashlib.sha256(actor.encode()).hexdigest()}:{fixed // 600}"
    digest = hashlib.sha256(b"synthetic-confirmation").hexdigest()
    monkeypatch.setattr(module.time, "time", lambda: fixed)
    monkeypatch.setenv("PMC_DOMESTIC_PASSCODE_SHA256", digest)
    # Each call uses a distinct client, as independent API workers would.
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/15")

    def attempt(_):
        try:
            module.verify_domestic_passcode(None, "wrong", actor)
        except ApiError as error:
            return error.code
        raise AssertionError("Incorrect passphrase accepted")

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(attempt, range(20)))
        assert outcomes.count("PASSCODE_REJECTED") == 10
        assert outcomes.count("PASSCODE_LOCKED") == 10
        assert int(client.get(key)) == 10
        assert 0 < client.ttl(key) <= 1200
    finally:
        client.delete(key)
        client.close()

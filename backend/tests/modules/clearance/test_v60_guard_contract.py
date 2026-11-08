"""P0/P1 clearance-only targeted guards; all tests use mocks, not business databases."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules.clearance import local_store_v28, service, tasks

BACKEND = Path(__file__).resolve().parents[3]


def test_automatic_jobs_default_off_and_do_not_open_database(monkeypatch):
    monkeypatch.delenv("SZZSBJ_CLEARANCE_AUTO_ENABLED", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(tasks, "get_engine", lambda: pytest.fail("unexpected DB access"))
    assert tasks.auto_enabled() is False
    assert tasks.recalculate() == {"examined": 0, "disabled": True}
    assert tasks.recalculate_scope("HK2613") == {"examined": 0, "disabled": True}
    assert tasks.scheduler_tick() is None


def test_local_automatic_jobs_remain_disabled_even_if_flag_is_set(monkeypatch):
    monkeypatch.setenv("SZZSBJ_CLEARANCE_AUTO_ENABLED", "1")
    monkeypatch.setenv("APP_ENV", "local")
    assert tasks.auto_enabled() is False


def test_local_clearance_write_scope_is_allowlisted_not_global(monkeypatch):
    monkeypatch.setattr(local_store_v28, "is_local", lambda: True)
    monkeypatch.setattr(local_store_v28, "checked_local_db_url", lambda: object())
    assert local_store_v28.is_clearance_write_route("PUT", "/api/clearance/rules")
    assert local_store_v28.is_clearance_write_route("POST", "/api/clearance/recalculate")
    assert not local_store_v28.is_clearance_write_route("PUT", "/api/finance/anything")
    assert not local_store_v28.is_clearance_write_route("POST", "/api/integration-sync/retry")


def test_separate_read_and_risk_write_session_never_commits_business_source(monkeypatch):
    class Query:
        def order_by(self, *args):
            return self

        def limit(self, *args):
            return self

        def where(self, *args):
            return self

    class Read:
        calls = 0

        def scalars(self, query):
            self.calls += 1
            values = [SimpleNamespace(id=10)] if self.calls == 1 else []
            return SimpleNamespace(all=lambda: values)

        def commit(self):
            pytest.fail("15432 read session committed")

    class Store:
        commits = 0

        def commit(self):
            self.commits += 1

    source, store = Read(), Store()
    checked = []
    written = []
    monkeypatch.setattr(service, "select", lambda model: Query())
    monkeypatch.setattr(
        service,
        "rule_version",
        lambda session, *, require_persisted=False: (
            checked.append((session, require_persisted)) or 2,
            object(),
        ),
    )
    monkeypatch.setattr(
        service,
        "evaluate_and_store",
        lambda read, listing, version, rules, *, risk_session=None: written.append(
            (read, listing.id, version, risk_session)
        ),
    )
    result = service.recalculate_all(source, risk_session=store)
    assert result == {"examined": 1, "rule_version": 2, "superseded": False}
    assert store.commits == 1
    assert written == [(source, 10, 2, store)]
    assert checked and all(session is store and required for session, required in checked)


def test_sql_and_permissions_are_not_replaced_by_local_guards():
    router = (BACKEND / "app/modules/clearance/router.py").read_text()
    local = (BACKEND / "app/core/local_scoped_writes.py").read_text()
    sync = (BACKEND / "app/modules/integration_sync/tasks.py").read_text()
    assert "principal: authenticated" in router
    assert "principal: review" in router
    assert 'method in ("POST", "PUT")' in local
    assert "enqueue_scope_recalculation" not in sync

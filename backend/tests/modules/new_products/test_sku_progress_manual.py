"""Isolated business tests; fake DB, no provider and no real database."""

from uuid import uuid4

import pytest

from app.modules.new_products.sku_progress_manual import save_progress


class Result:
    def __init__(self, value=None, rowcount=1):
        self.value = value
        self.rowcount = rowcount

    def mappings(self):
        return self

    def one(self):
        return self.value

    def one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value


class DB:
    def __init__(self, *, old_status="in_progress", created=False, pending=False, eligible=True):
        self.trace = []
        self.created = created
        self.pending = pending
        self.eligible = eligible
        self.old = dict(
            id=uuid4(),
            version=3,
            progress_status=old_status,
            reason_type=None,
            remark="old",
            manual_locked=False,
            exited_at=None,
        )
        if created:
            self.old["version"] = 1

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self.trace.append((sql, params))
        if "SELECT e.*" in sql:
            return Result({"sku": "SKU1"} if self.eligible else None)
        if "INSERT INTO biz_new_product_sku_progress\n" in sql:
            return Result(rowcount=int(self.created))
        if "FOR UPDATE" in sql:
            return Result(self.old)
        if "RETURNING version" in sql:
            return Result(self.old["version"] + 1)
        return Result()

    def scalar(self, *_):
        return self.pending

    def commit(self):
        self.trace.append(("COMMIT", None))


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.delenv("NEW_PRODUCTS_READ_DATABASE_URL", raising=False)


def call(db, **overrides):
    params = dict(
        account="A",
        sku_id=uuid4(),
        version=3,
        status="paused",
        reason="其他原因",
        remark="  note  ",
    )
    params.update(overrides)
    return save_progress(db, frozenset({"A"}), "1", **params)


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"account": "B"}, "SKU_PROGRESS_SCOPE_DENIED"),
        ({"remark": "  "}, "SKU_PROGRESS_MANUAL_INVALID"),
        ({"reason": None}, "SKU_PROGRESS_REASON_REQUIRED"),
        ({"version": 2}, "SKU_PROGRESS_VERSION_CONFLICT"),
        ({"status": "fake"}, "SKU_PROGRESS_MANUAL_INVALID"),
    ],
)
def test_reject(overrides, code):
    db = DB()
    with pytest.raises(Exception) as e:
        call(db, **overrides)
    assert e.value.code == code
    assert not any(sql == "COMMIT" for sql, _ in db.trace)


def test_pause_and_audit_atomic():
    db = DB()
    r = call(db)
    assert r["progress_status"] == "paused" and r["remark"] == "note" and r["version"] == 4
    assert db.trace[-1][0] == "COMMIT"
    event = [
        params
        for sql, params in db.trace
        if "INSERT INTO biz_new_product_sku_progress_events" in sql
    ][0]
    assert (
        event["event_key"] == "manual:4" and "old" in event["before"] and "note" in event["after"]
    )


def test_initial_version_zero():
    assert call(DB(created=True), version=0)["version"] == 2


def test_resume():
    db = DB(old_status="paused")
    r = call(db, status="in_progress")
    assert r["reason_type"] is None and r["progress_status"] == "in_progress"


def test_terminal_reopen_rejected():
    with pytest.raises(Exception) as e:
        call(DB(old_status="terminated"), status="in_progress")
    assert e.value.code == "SKU_PROGRESS_TERMINAL"


def test_uncertain_purchase_blocks_state_change():
    with pytest.raises(Exception) as e:
        call(DB(pending=True))
    assert e.value.code == "SKU_PROGRESS_PURCHASE_PENDING"


def test_split_source_fails_closed(monkeypatch):
    monkeypatch.setenv("NEW_PRODUCTS_READ_DATABASE_URL", "configured")
    db = DB()
    with pytest.raises(Exception) as e:
        call(db)
    assert e.value.code == "SKU_PROGRESS_SPLIT_SOURCE_DENIED" and not db.trace


def test_ineligible():
    with pytest.raises(Exception) as e:
        call(DB(eligible=False))
    assert e.value.code == "SKU_PROGRESS_NOT_ELIGIBLE"


def test_complete():
    assert call(DB(), status="completed")["progress_status"] == "completed"

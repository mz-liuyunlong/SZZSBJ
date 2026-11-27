"""Isolated contracts: no credentials, external POST, or database connection."""

import sys
from types import ModuleType
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.core.api import ApiError
from app.modules.new_products import sku_progress_projection as listing
from app.modules.new_products import sku_progress_purchase as purchase


def error_code(e):
    return getattr(e.value, "code", None)


@pytest.mark.parametrize("value", [0, 19, 21, True, 20.0, "20"])
def test_fixed_quantity_rejects(value):
    with pytest.raises(Exception) as e:
        purchase.enforce_qty(value)
    assert error_code(e) == "SKU_PURCHASE_FIXED_QUANTITY"


def test_fixed_quantity_default():
    assert purchase.enforce_qty(None) == purchase.enforce_qty(20) == 20


def evidence():
    return {
        "evaluation_grade_confirmation_v1": {
            "status": "confirmed",
            "effective_grade": "A",
            "rule_version": 1,
        },
        "operator_assessment_v1": {"decision": "passed"},
        "evaluation_final_snapshot": {
            "grade": "A",
            "rule_version": 1,
            "risk_evaluation": {"recommend_not_pass": False},
        },
    }


@pytest.mark.parametrize(
    "grade,coverage",
    [
        ("D", evidence()),
        ("A", {}),
        (
            "A",
            {"evaluation_grade_confirmation_v1": {"status": "confirmed", "effective_grade": "A"}},
        ),
    ],
)
def test_grade_fail_closed(grade, coverage):
    with pytest.raises(ApiError):
        purchase.confirmed_grade(grade, coverage)


def test_valid_grade():
    assert purchase.confirmed_grade("A", evidence()) == "A"


def test_mart_statements_only_write_new_read_model():
    for stmt in (listing.REFRESH, listing.EXIT):
        sql = str(stmt.compile(dialect=postgresql.dialect())).lower()
        assert "mart_new_product_sku_progress_current" in sql
        for old in (
            "dim_walmart_listings",
            "biz_new_product_sku_progress",
            "mart_listing_management_current",
        ):
            assert f"update {old} " not in sql and f"insert into {old} " not in sql
    assert "is distinct from" in str(listing.REFRESH).lower()
    assert "mart_listing_ad_status_current" in str(listing.REFRESH)
    assert "小批量测品" in str(listing.REFRESH)


class Result:
    def __init__(self, row=None):
        self.row = row
        self.rowcount = 1

    def mappings(self):
        return self

    def one_or_none(self):
        return self.row

    def one(self):
        assert self.row is not None
        return self.row


class FakeDB:
    def __init__(self, *, existing=None, no_listing=False, fail_commit=False):
        self.pid = uuid4()
        self.trace = []
        self.existing = existing
        self.no_listing = no_listing
        self.fail_commit = fail_commit

    def scalar(self, stmt, *args, **kw):
        return False if "biz_new_product_purchase_applications" in str(stmt) else 1

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self.trace.append(sql)
        if stmt is purchase.ELIGIBILITY:
            return Result({"sku": "SKU-001"})
        if stmt is purchase.LISTING:
            return Result(
                None
                if self.no_listing
                else {"item_id": "12345678901", "local_sku": "SKU-001", "gtin": "012345678901"}
            )
        if stmt is purchase.GRADE:
            return Result({"grade": "A", "data_coverage_json": evidence()})
        if "SELECT id,progress_status,exited_at" in sql:
            return Result({"id": self.pid, "progress_status": "in_progress", "exited_at": None})
        if "SELECT id,submission_status,lingxing_plan_sn,quantity" in sql:
            return Result(self.existing)
        return Result()

    def commit(self):
        self.trace.append("COMMIT")
        if self.fail_commit:
            raise RuntimeError("commit failed")

    def rollback(self):
        self.trace.append("ROLLBACK")


@pytest.fixture
def fake_transport(monkeypatch):
    monkeypatch.setenv("SZZSBJ_SKU_PROGRESS_PURCHASE_ENABLED", "YES")
    monkeypatch.delenv("NEW_PRODUCTS_READ_DATABASE_URL", raising=False)
    adapter = ModuleType("app.modules.new_products.purchase_plan_service")
    adapter._local_settings = lambda *_: object()
    adapter._build_verified_payload = lambda *args: {"data": [{"quantity_plan": args[-1]}]}
    adapter._preflight_purchase_auth = lambda *_: None
    transport = ModuleType("app.integrations.lingxing.new_product_purchase_plan")

    class ResponseError(Exception):
        code = "TEST_TIMEOUT"
        request_id = None

    transport.PurchasePlanResponseError = ResponseError
    transport.validate_transport = lambda *_: None
    transport.create_purchase_plan = lambda *_: pytest.fail("unconfigured provider mock")
    monkeypatch.setitem(sys.modules, adapter.__name__, adapter)
    monkeypatch.setitem(sys.modules, transport.__name__, transport)
    return transport


def submit(db):
    return purchase.submit_purchase(
        db, frozenset({"A"}), "actor", account="A", sku_id=uuid4(), store="S", item="12345678901"
    )


def test_unlisted_never_calls_provider(fake_transport):
    with pytest.raises(Exception) as e:
        submit(FakeDB(no_listing=True))
    assert error_code(e) == "SKU_PURCHASE_LISTING_REQUIRED"


def test_unknown_attempt_never_calls_provider(fake_transport):
    with pytest.raises(Exception) as e:
        submit(FakeDB(existing={"submission_status": "unknown"}))
    assert error_code(e) == "SKU_PURCHASE_ALREADY_ATTEMPTED"


def test_confirmed_duplicate_returns_receipt_without_post(fake_transport):
    r = submit(
        FakeDB(
            existing={
                "id": uuid4(),
                "submission_status": "submitted",
                "lingxing_plan_sn": "PP1",
                "quantity": 20,
            }
        )
    )
    assert r["duplicate"] and r["quantity"] == 20


def test_claim_commit_before_post_and_receipt(fake_transport):
    db = FakeDB()

    def post(settings, payload):
        assert db.trace[-1] == "COMMIT" and any(
            "'submitting'" in s and "INSERT" in s for s in db.trace
        )
        assert payload["data"][0]["quantity_plan"] == 20
        db.trace.append("POST")
        return {"plan_sn": "PP1", "ppg_sn": "B1", "request_id": "R1"}

    fake_transport.create_purchase_plan = post
    r = submit(db)
    assert (
        r["lingxing_plan_sn"] == "PP1"
        and db.trace.count("POST") == 1
        and db.trace.count("COMMIT") == 2
    )


def test_timeout_remains_unknown(fake_transport):
    db = FakeDB()

    def post(*_):
        raise fake_transport.PurchasePlanResponseError()

    fake_transport.create_purchase_plan = post
    with pytest.raises(Exception) as e:
        submit(db)
    assert error_code(e) == "SKU_PURCHASE_RESULT_UNCERTAIN"
    assert any("submission_status='unknown'" in s for s in db.trace)
    assert db.trace.count("COMMIT") == 2


def test_claim_commit_failure_never_posts(fake_transport):
    with pytest.raises(RuntimeError, match="commit failed"):
        submit(FakeDB(fail_commit=True))


def test_claim_key_store_and_account_isolation():
    sku = uuid4()
    k = purchase.claim_key("A", sku, "S")
    assert k == purchase.claim_key("A", sku, "S")
    assert k != purchase.claim_key("B", sku, "S") != purchase.claim_key("A", sku, "T")

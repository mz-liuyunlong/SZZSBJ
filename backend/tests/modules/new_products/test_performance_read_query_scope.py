"""Query-scope regression: exact counts without per-item approval queries."""

import json
from datetime import UTC, date

import pytest

from app.modules.new_products import performance_list_scope as scope
from app.modules.new_products.workflow_read import needs_purchase_store_projection


class BatchDB:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params):
        sql = str(statement)
        self.calls.append((sql, params))
        assert "DISTINCT ON" in sql
        if "biz_new_product_purchase_applications" in sql:
            keys = json.loads(params["wants"])
            return Result(
                [
                    dict(k, status={"p1": "approved", "p2": "submitted", "p3": "rejected"}[k["i"]])
                    for k in keys
                    if k["i"] != "p4"
                ]
            )
        assert "app_approval_requests" in sql
        refs = json.loads(params["refs"])
        return Result(
            [
                {
                    "business_ref": r,
                    "status": {"r1": "submitted", "r2": "approved", "r3": "rejected"}[r],
                }
                for r in refs
                if r != "r4"
            ]
        )


class Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


def projection():
    rows = []
    for i in range(944):
        rows.append(make_row(f"active{i}", "测评中"))
    for i in range(43):
        rows.append(make_row(f"pending{i}", "待等级确认"))
    for i in range(1, 5):
        rows.append(make_row(f"p{i}", "测评通过"))
        rows.append(make_row(f"f{i}", "测评未通过", f"r{i}", i == 2))
    rows.extend([make_row("waiting", "测评中", wfs=None), make_row("old", "待到货", wfs=None)])
    return rows


def make_row(item, status, ref=None, recheck=False, wfs=date(2026, 11, 1)):
    return {
        "identity": ("a", "store", item),
        "status": status,
        "first_wfs": wfs,
        "flow_status": scope.flow_status(status, first_wfs=wfs),
        "grade": "A",
        "owner": "A",
        "_registry_ref": ref,
        "_recheck_required": recheck,
    }


@pytest.fixture
def batch(monkeypatch):
    owner_flags = []

    def read(*args, include_owners=True, **kwargs):
        owner_flags.append(include_owners)
        return projection()

    monkeypatch.setattr(scope, "scoped_projection", read)
    return BatchDB(), owner_flags


def test_summary_batches_only_terminal_products(batch):
    db, owner_flags = batch
    result = scope.summary(None, db, frozenset({"a"}))
    assert result["stage_counts"] == {
        "all": 997,
        "evaluating": 944,
        "pending": 43,
        "passed": 4,
        "failed": 4,
    }
    counts = {r["value"]: r["count"] for r in result["flow_status_options"]}
    assert counts["待到货"] == 2
    assert all(counts[s] == 1 for s in scope._FLOW_GROUPS["passed"] + scope._FLOW_GROUPS["failed"])
    assert sum(counts.values()) == 997
    assert len(db.calls) == 2
    assert len(json.loads(db.calls[0][1]["wants"])) == 4
    assert len(json.loads(db.calls[1][1]["refs"])) == 4
    assert owner_flags == [True]


def test_card_filters_skip_both_workflow_reads(batch):
    db, flags = batch
    for group, count in [("evaluating", 944), ("pending", 43), ("passed", 4), ("failed", 4)]:
        statuses = ",".join("flow:" + s for s in scope._FLOW_GROUPS[group])
        assert (
            len(scope.matching_identities(None, db, frozenset({"a"}), statuses=statuses)) == count
        )
    assert len(scope.matching_identities(None, db, frozenset({"a"}), statuses="flow:待到货")) == 2
    assert not db.calls
    assert flags == [False] * 5


def test_specific_filters_read_only_required_stage(batch):
    db, flags = batch
    assert scope.matching_identities(None, db, frozenset({"a"}), statuses="flow:采购已驳回") == [
        ("a", "store", "p3")
    ]
    assert len(db.calls) == 1 and "wants" in db.calls[0][1]
    db.calls.clear()
    assert scope.matching_identities(
        None, db, frozenset({"a"}), statuses="flow:待重新核算", owners="A"
    ) == [("a", "store", "f2")]
    assert len(db.calls) == 1 and "refs" in db.calls[0][1]
    assert flags == [False, True]
    db.calls.clear()
    assert (
        scope.matching_identities(
            None, db, frozenset({"a"}), statuses="flow:采购已批准", owners="other"
        )
        == []
    )
    assert not db.calls


def test_store_enrichment_only_for_purchase_status_selection():
    assert needs_purchase_store_projection("测评通过")
    assert needs_purchase_store_projection("flow:采购已批准")
    assert needs_purchase_store_projection(
        ",".join("flow:" + s for s in scope._FLOW_GROUPS["passed"])
    )
    assert not needs_purchase_store_projection("")
    assert not needs_purchase_store_projection("flow:测评中")
    assert not needs_purchase_store_projection("flow:采购已批准,flow:测评未通过")


def test_page_workflow_reuses_preloaded_purchase_and_decision(monkeypatch):
    from types import SimpleNamespace

    from app.modules.new_products import workflow_read as read

    class PageSession:
        def __init__(self):
            self.calls = []

        def scalars(self, stmt):
            self.calls.append(str(stmt))
            return []

    key = ("a", "store", "item")
    purchase = SimpleNamespace(
        id="app",
        status="approved",
        version=1,
        requested_qty=200,
        request_reason="apply",
        approved_qty=150,
        suggested_qty=200,
        store_id="store",
        review_reason="approved",
    )
    decision = SimpleNamespace(decision="未判定", version=2)
    db = PageSession()
    rows = [{"listing": dict(zip(("source_account_ref", "store_id", "item_id"), key, strict=True))}]

    def fail(*args, **kwargs):
        raise AssertionError("non-purchase page queried approval store evidence")

    monkeypatch.setattr(read, "_approved_purchase_stores", fail)
    read.attach_workflow_fields(
        db, rows, include_approved_stores=False, preloaded=({key: purchase}, {key: decision})
    )
    assert len(db.calls) == 1 and "biz_new_product_registry" in db.calls[0]
    assert rows[0]["approved_qty"] == 150 and rows[0]["purchase_review_reason"] == "approved"
    assert rows[0]["tracking_version"] == 2 and rows[0]["approved_purchase_store_id"] is None
    db.calls.clear()
    monkeypatch.setattr(
        read, "_approved_purchase_stores", lambda *args: {(*key, "app"): ("new", "2603")}
    )
    read.attach_workflow_fields(
        db, rows, include_approved_stores=True, preloaded=({key: purchase}, {key: decision})
    )
    assert rows[0]["approved_purchase_store_id"] == "new"
    assert rows[0]["approved_purchase_store_name"] == "2603"


def test_lean_projection_keeps_identity_status_but_omits_board_enrichment(monkeypatch):
    from datetime import datetime
    from types import SimpleNamespace

    from sqlalchemy import String, column, table
    from sqlalchemy.dialects.postgresql import JSONB, dialect

    mart = table(
        "test_mart",
        *[
            column(k, String)
            for k in (
                "source_account_ref",
                "store_id",
                "item_id",
                "local_sku",
                "local_name",
                "title",
                "category",
                "listing_start_at_utc",
            )
        ],
        column("product_tags_json", JSONB),
    )
    monitor = table(
        "test_monitor",
        *[column(k, String) for k in ("source_account_ref", "store_id", "item_id", "category")],
    )
    monkeypatch.setattr(scope, "ListingManagementCurrentMart", SimpleNamespace(**dict(mart.c)))
    for key, value in monitor.c.items():
        setattr(monitor, key, value)
    monkeypatch.setattr(scope, "WalmartMonitorListingCurrent", monitor)

    class Source:
        def __init__(self):
            self.sql = []

        def scalar(self, _stmt):
            return None

        def execute(self, stmt):
            self.sql.append(str(stmt.compile(dialect=dialect())))
            return Result(
                [
                    {
                        "source_account_ref": "a",
                        "store_id": "s",
                        "item_id": "i",
                        "local_sku": "sku",
                        "listing_start_at_utc": datetime(2026, 11, 1, tzinfo=UTC),
                        "local_name": "product",
                        "title": "title",
                        "category_raw": "category",
                    }
                ]
            )

    class Decision:
        def __init__(self):
            self.sql = []

        def execute(self, stmt, params):
            self.sql.append(str(stmt))
            assert json.loads(params["wants"]) == [{"a": "a", "s": "s", "i": "i"}]
            return Result(
                [
                    {
                        "a": "a",
                        "s": "s",
                        "i": "i",
                        "registry_ref": "r",
                        "grade": "A",
                        "score": "8",
                        "first_wfs_available_date_la": date(2026, 11, 1),
                        "operator_assessment": {"decision": "passed"},
                    }
                ]
            )

    source, db = Source(), Decision()
    lean = scope.scoped_projection(
        source, db, frozenset({"a"}), include_owners=False, include_board_details=False
    )
    full = scope.scoped_projection(source, db, frozenset({"a"}), include_owners=False)
    for key in ("identity", "status", "flow_status", "grade", "first_wfs", "total"):
        assert lean[0][key] == full[0][key]
    assert "test_monitor" not in source.sql[0] and "test_monitor" in source.sql[1]
    assert " AS dimensions" not in db.sql[0] and " AS dimensions" in db.sql[1]
    assert " AS market_score" not in db.sql[0] and " AS market_score" in db.sql[1]

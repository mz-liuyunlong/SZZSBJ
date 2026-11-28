"""Isolated contracts. No database, credentials or provider calls."""

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.modules.new_products import sku_progress_query as q
from app.modules.new_products.sku_progress_router import query_filters


@pytest.mark.parametrize("key", tuple(q.SORTS))
@pytest.mark.parametrize("direction", ("asc", "desc"))
def test_sort_is_allowlisted_and_stable(key, direction):
    sql = str(q.list_statement(key, direction).compile(dialect=postgresql.dialect()))
    assert (
        f"{q.SORTS[key]} {direction.upper()} NULLS LAST,source_account_ref,sku_identity_id" in sql
    )
    assert "LIMIT" in sql and "OFFSET" in sql
    assert "source_account_ref IN" in sql
    assert "INSERT INTO" not in sql and "UPDATE " not in sql
    assert "raw_walmart_monitor_events" not in sql


def test_sort_injection_rejected():
    with pytest.raises(KeyError):
        q.list_statement("sku; drop table products", "asc")
    with pytest.raises(KeyError):
        q.list_statement("date", "desc; drop table products")


def test_summary_ignores_only_card_not_other_progress_filters():
    stmt = q.summary_statement().compile(dialect=postgresql.dialect())
    assert "card" not in stmt.params
    assert "f_progress" in stmt.params
    assert all("f_" + k in stmt.params for k in q.FACETS)


def test_facet_self_exclusion_distinct_sku_and_date_bounds():
    stmt = q.facet_statement().compile(dialect=postgresql.dialect())
    sql = str(stmt)
    assert "count(DISTINCT (r.source_account_ref,r.sku_identity_id))" in sql
    for k in q.FACETS:
        assert f"r.mismatches=1 AND NOT r.match_{k}" in sql
        assert "f_" + k in stmt.params
    assert "keyword_match AND card_match AND mismatches=0" in sql
    assert "min(development_date)" in sql and "max(development_date)" in sql
    assert "x.sku=s.sku" in sql
    assert "48 hours" in sql
    assert "'ship','[\"待确认\"]'" in sql
    assert "raw_walmart_monitor_events" not in sql


def test_multiselect_params_dedup_and_scope():
    result = q.params(
        frozenset({"B", "A"}),
        {
            "store": ["a", "b", "a"],
            "ad": ["待确认"],
            "card": "done",
            "keyword": "  SKU  ",
            "start": date(2026, 1, 1),
        },
    )
    assert result["accounts"] == ["A", "B"]
    assert result["f_store"] == ["a", "b"] and result["f_ad"] == ["待确认"]
    assert result["card"] == "completed" and result["keyword"] == "SKU"
    assert result["f_owner"] == []


def test_invalid_date_and_enum_rejected():
    with pytest.raises(Exception) as e:
        query_filters(start=date(2026, 2, 1), end=date(2026, 1, 1))
    assert e.value.code == "SKU_PROGRESS_DATE_RANGE_INVALID"
    with pytest.raises(Exception) as e:
        query_filters(ad=["invented"])
    assert e.value.code == "SKU_PROGRESS_FILTER_INVALID"


class Result:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def one(self):
        return self.row

    def __iter__(self):
        return iter(self.row)


class DB:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((statement, params))
        return Result(self.result)


def test_list_paginates_in_sql_and_keeps_sku_groups():
    rows = [{"sku_identity_id": str(uuid4()), "listings": [{"item_id": "1"}, {"item_id": "2"}]}]
    db = DB({"items": rows, "total": 81, "listing_count": 92})
    result = q.list_page(
        db, frozenset({"A"}), {}, page=3, page_size=20, sort_by="date", sort_order="desc"
    )
    assert len(db.calls) == 1 and db.calls[0][1]["offset"] == 40
    assert result == {"items": rows, "total": 81, "listing_count": 92, "page": 3, "page_size": 20}


def test_facet_envelope_static_zero_and_unknown_only():
    db = DB(
        {
            "options": [
                {"key": "store", "value": '["A", "s"]', "label": "CN2601", "count": 3},
                {"key": "ship", "value": "待确认", "label": "待确认", "count": 3},
            ],
            "min_date": date(2026, 1, 1),
            "max_date": date(2026, 2, 1),
        }
    )
    result = q.facets(db, frozenset({"A"}), {})
    assert result["facets"]["store"][0]["count"] == 3
    assert result["date_range"]["min"] == date(2026, 1, 1)
    assert {r["value"]: r["count"] for r in result["facets"]["ship"]} == {
        "已发货": 0,
        "未发货": 0,
        "待确认": 3,
    }
    assert result["unknown_sources"] == ["ship"]


def test_empty_scope_does_not_query():
    db = DB(None)
    assert (
        q.list_page(db, frozenset(), {}, page=1, page_size=20, sort_by="date", sort_order="desc")[
            "total"
        ]
        == 0
    )
    assert q.summary(db, frozenset(), {})["total"] == 0
    assert q.facets(db, frozenset(), {})["date_range"] == {"min": None, "max": None}
    assert not db.calls


def candidate_data(plans=None):
    return {
        "items": [
            {
                "source_account_ref": "A",
                "identity_verified": True,
                "progress_status": "in_progress",
                "purchase_plans": plans or [],
                "listings": [{"store_id": "S", "item_id": "12345678901", "gtin": "012345678901"}],
            }
        ]
    }


def test_purchase_options_disabled_without_permission_or_with_claim(monkeypatch):
    monkeypatch.setenv("SZZSBJ_SKU_PROGRESS_PURCHASE_ENABLED", "YES")
    monkeypatch.delenv("NEW_PRODUCTS_READ_DATABASE_URL", raising=False)
    db = DB(None)
    data = candidate_data()
    q.attach_purchase_options(db, data, False)
    assert data["items"][0]["listings"][0]["purchase_candidate"] is False
    data = candidate_data([{"store_id": "S"}])
    q.attach_purchase_options(db, data, True)
    assert data["items"][0]["listings"][0]["purchase_candidate"] is False
    assert not db.calls


def test_purchase_options_only_saved_grade_evidence(monkeypatch):
    monkeypatch.setenv("SZZSBJ_SKU_PROGRESS_PURCHASE_ENABLED", "YES")
    monkeypatch.delenv("NEW_PRODUCTS_READ_DATABASE_URL", raising=False)
    coverage = {
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
    evidence = {
        "account": "A",
        "store_id": "S",
        "item_id": "12345678901",
        "grade": "A",
        "data_coverage_json": coverage,
        "existing_approval": False,
    }
    data = candidate_data()
    db = DB([evidence])
    q.attach_purchase_options(db, data, True)
    assert data["items"][0]["listings"][0]["purchase_candidate"] is True
    for change in ({"grade": "D"}, {"existing_approval": True}, {"data_coverage_json": {}}):
        data = candidate_data()
        q.attach_purchase_options(DB([{**evidence, **change}]), data, True)
        assert data["items"][0]["listings"][0]["purchase_candidate"] is False


def test_owner_source_is_scoped_and_shared_by_all_three_queries():
    for statement in (
        q.list_statement("date", "desc"),
        q.summary_statement(),
        q.facet_statement(),
    ):
        sql = str(statement.compile(dialect=postgresql.dialect()))
        assert "oi.id=s.sku_identity_id" in sql
        assert "oi.source_account_ref=s.source_account_ref" in sql
        assert "oi.provider='lingxing' AND oi.is_active" in sql
        assert "o.identity_id=oi.id" in sql
        assert "o.source_account_ref=oi.source_account_ref" in sql
        assert "o.lingxing_sku_id=oi.lingxing_sku_id" in sql
        assert "o.lingxing_sku_code=s.sku" in sql
        assert "ON s.identity_verified" in sql
        assert "'owner_display',owner_display" in sql
        assert "'value',owner_filter,'label',owner_display" in sql
        assert "'store_filter',store_filter,'owner_filter',owner_filter" in sql
        assert "raw_walmart_monitor_events" not in sql
        assert "INSERT INTO" not in sql and "UPDATE " not in sql


@pytest.mark.parametrize(
    "listing_ref,sku_uid,sku_name,expected_display,expected_key",
    [
        (None, "U1", "Alice", "Alice", "U1"),
        ("  ", "U1", "Alice", "Alice", "U1"),
        ("U1", "U1", "Alice", "Alice", "U1"),
        ("Alice", "U1", "Alice", "Alice", "U1"),
        ("Bob", "U1", "Alice", "Bob", "Bob"),
        ("U2", "U1", "Alice", "U2", "U2"),
        (None, None, "Alice", "Alice", "Alice"),
        (None, "U1", None, "U1", "U1"),
        ("Bob", None, None, "Bob", "Bob"),
        (None, None, None, None, None),
        (" ", " ", " ", None, None),
    ],
)
def test_owner_resolution_expression(
    listing_ref, sku_uid, sku_name, expected_display, expected_key
):
    # Exercise the actual SQL CASE expressions using only synthetic values.
    # SQLite's JSON ->> operator, CASE, COALESCE and NULLIF have the required
    # semantics here; btrim is a local compatibility function. No app DB.
    import json
    import sqlite3

    with sqlite3.connect(":memory:") as conn:
        conn.create_function("btrim", 1, lambda x: x.strip(" ") if x is not None else None)
        sql = (
            f"SELECT {q.OWNER_DISPLAY_SQL}, {q.OWNER_KEY_SQL} "
            "FROM (SELECT ? AS j) "
            "CROSS JOIN (SELECT ? AS owner_uid, ? AS owner_name) o"
        )
        actual = conn.execute(
            sql, (json.dumps({"owner_ref": listing_ref}), sku_uid, sku_name)
        ).fetchone()
    assert actual == (expected_display, expected_key)


def test_listing_claim_does_not_block_sibling_listing(monkeypatch):
    monkeypatch.setenv("SZZSBJ_SKU_PROGRESS_PURCHASE_ENABLED", "YES")
    monkeypatch.delenv("NEW_PRODUCTS_READ_DATABASE_URL", raising=False)
    data = candidate_data([{"store_id": "S", "item_id": "12345678901"}])
    row = data["items"][0]
    sibling = {**row["listings"][0], "item_id": "22345678901"}
    row["listings"].append(sibling)
    coverage = {
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
    evidence = {
        "account": "A",
        "store_id": "S",
        "item_id": sibling["item_id"],
        "grade": "A",
        "data_coverage_json": coverage,
        "existing_approval": False,
    }
    db = DB([evidence])
    q.attach_purchase_options(db, data, True)
    assert not row["listings"][0]["purchase_candidate"]
    assert sibling["purchase_candidate"]
    assert len(db.calls) == 1
    data = candidate_data([{"store_id": "S", "item_id": None}])
    data["items"][0]["listings"].append(dict(sibling))
    db = DB([])
    q.attach_purchase_options(db, data, True)
    assert not any(listing["purchase_candidate"] for listing in data["items"][0]["listings"])
    assert not db.calls


def test_listing_purchase_status_and_facets_use_exact_item():
    for stmt in (q.list_statement("date", "desc"), q.summary_statement(), q.facet_statement()):
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "x.item_id=claim_item.item_id" in sql
        assert "x.item_id IS DISTINCT FROM claim_item.item_id" in sql
        assert "GROUP BY sku_progress_id,store_id,item_id" in sql
        assert "lp.item_id=j->>'item_id'" in sql
        assert "legacy.item_id IS NULL" in sql
        assert "'plan',plan_values,'proc',proc_values" in sql
        assert "owner_display" in sql
        assert "'domestic_shipping_status',NULL::text" in sql


def test_listing_read_does_not_require_new_physical_item_column():
    # All three read paths must parse against the old purchase table shape.
    for stmt in (q.list_statement("date", "desc"), q.summary_statement(), q.facet_statement()):
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "to_jsonb(q)->>'item_id' AS item_id" in sql
        assert "q.item_id" not in sql
        assert "claim_item.item_id" in sql
        assert "legacy.item_id IS NULL" in sql
    # Eligibility stays closed without the 0102 protections. No extra read query.
    sql = str(q.PURCHASE_EVIDENCE.compile(dialect=postgresql.dialect()))
    assert "pg_catalog.pg_attribute" in sql
    assert "uq_sku_purchase_active_listing" in sql
    assert "uq_sku_purchase_active_legacy_store" in sql
    assert "ck_sku_purchase_listing_identity" in sql

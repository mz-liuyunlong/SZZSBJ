"""V23 WFS dropdown filters: read-only, account-scoped, pre-pagination."""
from __future__ import annotations

from app.modules.clearance.filters_v23 import (
    WFS_PREDICATE, list_filter_options, scoped_parts, search_risk_filtered,
)


class FacetSession:
    def __init__(self, owner_table=True):
        self.owner_table = owner_table
        self.statements = []

    def scalar(self, statement, params=None):
        self.statements.append((str(statement), params))
        return "dwd_lingxing_sku_product_info_current" if self.owner_table else None

    def execute(self, statement, params=None):
        self.statements.append((str(statement), params))
        # The query simulates the entire scoped WFS population, not a page.
        rows = [
            ("primary", "111", "Walmart Store A", "Lucy"),
            ("primary", "111", "Walmart Store A", "Helen"),
            ("primary", "222", "Walmart Store B", "未分配"),
        ]
        return type("Result", (), {"all": lambda _self: rows})()


def test_scoped_filter_is_account_protected_and_parameterized():
    session = FacetSession()
    clause, params = scoped_parts(
        session, frozenset({"primary"}), "microwave",
        store_refs=("primary::111", "primary::222"), owner_names=("Helen", "Lucy"),
    )
    assert "l.source_account_ref = ANY(:accounts)" in clause
    assert WFS_PREDICATE in clause
    assert "l.store_id" in clause and "ANY(:store_refs)" in clause
    assert "owner_match.owner_name" in clause
    assert "ANY(:owner_names)" in clause
    assert "LATERAL" in clause
    assert "Helen" not in clause and "microwave" not in clause
    assert params == {"accounts": ["primary"], "keyword": "%microwave%",
                      "store_refs": ["primary::111", "primary::222"],
                      "owner_names": ["Helen", "Lucy"]}


def test_filter_options_are_from_full_wfs_scope_not_page():
    session = FacetSession()
    result = list_filter_options(session, frozenset({"primary"}))
    assert [x["value"] for x in result["stores"]] == ["primary::111", "primary::222"]
    assert [x["value"] for x in result["owners"]] == ["Helen", "Lucy", "未分配"]
    assert [x["value"] for x in result["risks"]] == [
        "high", "medium", "low", "none", "unknown",
    ]
    sql, params = session.statements[-1]
    assert WFS_PREDICATE in sql
    assert "LIMIT" not in sql.upper()
    assert params == {"accounts": ["primary"]}


def test_missing_owner_master_uses_existing_listing_owner_reference():
    session = FacetSession(owner_table=False)
    clause, _ = scoped_parts(session, frozenset({"primary"}), owner_names=("未分配",))
    assert "LATERAL" not in clause
    assert "l.owner_ref" in clause
    assert "owner_match" not in clause


def test_global_risk_filter_uses_whole_population_not_first_page(monkeypatch):
    import sys
    from types import ModuleType, SimpleNamespace
    from datetime import date
    from sqlalchemy import Column, Date, Integer, String
    from sqlalchemy.orm import declarative_base

    base = declarative_base()

    class Listing(base):
        __tablename__ = "v23_test_listing"
        id = Column(Integer, primary_key=True)
        source_account_ref = Column(String)
        store_id = Column(String)
        item_id = Column(String)
        local_sku = Column(String)
        wfs_available_quantity = Column(Integer)

    class Daily(base):
        __tablename__ = "v23_test_daily"
        id = Column(Integer, primary_key=True)
        source_account_ref = Column(String)
        store_id = Column(String)
        item_id = Column(String)
        business_date_la = Column(Date)

    model_module = ModuleType("app.modules.data_pages.models")
    model_module.ListingManagementCurrentMart = Listing
    model_module.DailySalesItemDayMart = Daily
    monkeypatch.setitem(sys.modules, model_module.__name__, model_module)

    cost_module = ModuleType("app.modules.product_management.daily_sales_costs")
    cost_module.load_daily_sales_costs = lambda *_args, **_kwargs: {}
    cost_module.normalize_sku_key = lambda value: value
    monkeypatch.setitem(sys.modules, cost_module.__name__, cost_module)

    reader = ModuleType("app.modules.clearance.read_only_listings")
    reader._commission_for_listings = lambda *_args: {}
    reader._owner_names_for_listings = lambda *_args: {}
    reader._page_first_wfs_dates = lambda *_args: {}
    reader._product_data_for_listings = lambda *_args: {}
    seen = []
    def fake_snapshot(_session, item, **_kwargs):
        seen.append(item.id)
        return {"item_id": item.item_id, "risk": {1: "high", 2: "none", 3: "medium", 4: "unknown"}[item.id]}
    reader.read_business_snapshot = fake_snapshot
    monkeypatch.setitem(sys.modules, reader.__name__, reader)

    repo = ModuleType("app.modules.clearance.repository")
    repo.la_today = lambda: date(2026, 11, 8)
    monkeypatch.setitem(sys.modules, repo.__name__, repo)

    listings = [Listing(id=n, source_account_ref="primary", store_id="111",
                        item_id=f"ITEM-{n}", local_sku=f"SKU-{n}",
                        wfs_available_quantity=10) for n in (1, 2, 3, 4)]

    class Session:
        def scalar(self, _statement, _params=None):
            return None
        def execute(self, sql, params):
            assert "l.source_account_ref = ANY(:accounts)" in str(sql)
            assert params["store_refs"] == ["primary::111"]
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [1, 2, 3, 4]))
        def scalars(self, sql):
            if "v23_test_listing" in str(sql):
                return SimpleNamespace(all=lambda: listings)
            return SimpleNamespace(all=lambda: [])

    result = search_risk_filtered(Session(), frozenset({"primary"}), "", 2, 1,
                                  ("primary::111",), (), ("high", "medium"))
    assert seen == [1, 2, 3, 4]
    assert result["total"] == 2
    assert result["items"] == [{"item_id": "ITEM-3", "risk": "medium"}]
    assert result["total_scope"] == "filtered_wfs_stock_eligible"
    assert result["risk_filter_applied"] is True

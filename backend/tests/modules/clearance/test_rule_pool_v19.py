"""Risk-only pool must not mean the entire WFS stocked population."""
from decimal import Decimal
from types import SimpleNamespace

from app.modules.clearance import rule_pool_v19 as pool


def test_rule_admission_is_only_high_or_medium():
    assert pool.rule_qualified("high")
    assert pool.rule_qualified("medium")
    assert not pool.rule_qualified("low")
    assert not pool.rule_qualified("unknown")
    assert not pool.rule_qualified("unreviewed")


def test_rule_pool_scans_all_stock_before_paging(monkeypatch):
    rows = [SimpleNamespace(
        id=n, source_account_ref="HK2613", store_id="STORE-1",
        item_id=name, local_sku=f"SKU-{name}",
        wfs_available_quantity=Decimal("12"),
    ) for n, name in enumerate(["LOW", "MED", "UNKNOWN", "HIGH"], 1)]
    levels = {"LOW": "low", "MED": "medium", "UNKNOWN": "unknown", "HIGH": "high"}

    class ReadSession:
        def __init__(self):
            self.calls = 0
        def scalars(self, statement):
            self.calls += 1
            return SimpleNamespace(all=lambda: rows if self.calls == 1 else [])

    monkeypatch.setattr(pool, "la_today", lambda: __import__("datetime").date(2026, 11, 7))
    monkeypatch.setattr(pool, "_page_first_wfs_dates", lambda session, listings: {})
    monkeypatch.setattr(pool, "_assess_read_only", lambda row, *_: (levels[row.item_id], [], [], [], {}))
    monkeypatch.setattr(pool, "_product_data_for_listings", lambda session, listings: {})
    monkeypatch.setattr(pool, "_commission_for_listings", lambda session, listings, cutoff: {})
    monkeypatch.setattr(pool, "_owner_names_for_listings", lambda session, listings: {})
    monkeypatch.setattr(pool, "load_daily_sales_costs", lambda session, source_account_ref: {})
    monkeypatch.setattr(pool, "read_business_snapshot", lambda session, row, **kwargs:
                        {"item_id": row.item_id, "risk": levels[row.item_id]})

    result = pool.search_rule_pool(ReadSession(), frozenset({"HK2613"}), "", 2, 1,
                                   exact_total=True)
    assert result["total"] == 2
    assert result["risk_filter_applied"] is True
    assert result["total_scope"] == "clearance_rule_candidates"
    assert result["items"] == [{"item_id": "MED", "risk": "medium"}]
    assert result["has_more"] is False

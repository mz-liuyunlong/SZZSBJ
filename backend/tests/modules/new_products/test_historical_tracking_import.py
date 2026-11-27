from datetime import date
from unittest.mock import Mock

from sqlalchemy.dialects import postgresql

from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.new_products import historical_tracking as hist
from app.modules.new_products import tracking_read as reader


def test_scope_never_widens_by_store_or_sku():
    default = hist.listing_scope(ListingManagementCurrentMart)
    extended = hist.listing_scope(ListingManagementCurrentMart, {("account", "store", "item")})
    s0 = str(default.compile(dialect=postgresql.dialect()))
    s1 = str(extended.compile(dialect=postgresql.dialect()))
    assert " OR " not in s0 and " OR " in s1
    assert all(x in s1 for x in ("source_account_ref", "store_id", "item_id"))


def test_empty_scope_never_queries():
    db = Mock()
    assert hist.snapshots(db, frozenset()) == {}
    assert hist.snapshots(db, frozenset({"a"}), []) == {}
    db.execute.assert_not_called()


def test_overlay_keeps_historical_grade_and_raw_scores():
    snapshot = {
        "grade": "C",
        "total": 8.65,
        "source": hist.HISTORY_SOURCE,
        "dimensions": {"market": 9, "speed": 10, "ad": 10, "profit": 4, "risk_supply": 10},
    }
    row = {
        "evaluation": {"grade": "A", "total": "9"},
        "facts": {"profit_usd": "5"},
        "suggested_qty": 100,
    }
    hist.overlay(row, snapshot)
    assert row["evaluation"]["grade"] == "C" and row["evaluation"]["total"] == "8.65"
    assert row["evaluation"]["dimensions"]["trust"] is None
    assert row["facts"][hist.HISTORY_BLOCK]["dimensions"]["risk_supply"] == 10
    assert row["facts"]["profit_usd"] == "5" and row["suggested_qty"] is None


def test_tracking_admits_only_enrolled_without_fake_purchase(monkeypatch):
    h = ("a", "s", "h")
    u = ("a", "s", "u")
    n = ("a", "s", "n")
    rows = [
        dict(
            identity=k,
            grade="pending",
            sku=k[2],
            name=k[2],
            first_wfs=date(2026, 1, 1),
            launch_day=date(2026, 1, 1),
        )
        for k in (h, u, n)
    ]
    monkeypatch.setattr(reader, "historical_snapshots", lambda *a: {h: {"grade": "D"}})
    monkeypatch.setattr(reader, "scoped_projection", lambda *a, **kw: rows)
    monkeypatch.setattr(reader, "local_preview_item_ids", lambda: None)
    monkeypatch.setattr(
        reader,
        "_saved_decisions",
        lambda *a: {
            h: {"initial_grade": "D"},
            n: {"purchase_status": "approved", "initial_grade": "A"},
        },
    )
    out = reader._projection(None, None, frozenset({"a"}))
    assert [r["identity"] for r in out] == [h, n]
    assert out[0]["tracking"] == "未判定" and out[0]["grade"] == "D"

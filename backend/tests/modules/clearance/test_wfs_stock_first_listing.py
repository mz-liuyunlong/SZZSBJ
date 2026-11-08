"""Clearance WFS-stock-first listing regression, no database writes."""

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.modules.clearance import service


class _Scalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _Session:
    def __init__(self, listing):
        self.listing = listing
        self.queries = []

    def scalar(self, statement, params=None):
        sql = str(statement)
        self.queries.append((sql, params))
        assert sql.startswith("SELECT COUNT(*)")
        assert "l.wfs_available_quantity > 0" in sql
        assert "l.wfs_available_quantity = trunc(l.wfs_available_quantity)" in sql
        assert "JOIN biz_clearance_risk_current" not in sql
        return 738

    def execute(self, statement, params=None):
        sql = str(statement)
        self.queries.append((sql, params))
        assert "l.wfs_available_quantity > 0" in sql
        assert "l.wfs_available_quantity = trunc(l.wfs_available_quantity)" in sql
        assert "JOIN biz_clearance_risk_current" not in sql
        assert sql.index("l.wfs_available_quantity > 0") < sql.index("LIMIT :limit")
        assert params["accounts"] == ["primary"]
        assert params["limit"] == 51
        assert params["offset"] == 0
        return _Scalars([self.listing.id])

    def scalars(self, statement):
        return _Scalars([self.listing])


def test_all_stocked_items_not_gated_on_risk_pool(monkeypatch):
    listing = SimpleNamespace(
        id=uuid4(),
        source_account_ref="primary",
        store_id="store",
        item_id="item",
        wfs_available_quantity=Decimal("12"),
        picture_url=None,
        sale_price_amount=None,
    )
    monkeypatch.setattr(service, "risk_read_model_ready", lambda _s: True)
    monkeypatch.setattr(service, "rule_version", lambda _s: (1, object()))
    monkeypatch.setattr(service, "current_available", lambda _s, _l: 12)
    monkeypatch.setattr(
        service,
        "_snapshot_row",
        lambda _s, _listing, _version, _rules: {"item_id": "item", "risk": "unknown"},
    )
    session = _Session(listing)
    response = service.search_listings(
        session, frozenset({"primary"}), "", 1, 50, risk_only=False, exact_total=True
    )
    assert response["items"][0]["item_id"] == "item"
    assert response["items"][0]["available"] == 12
    assert response["total"] == 738
    assert response["total_scope"] == "all_wfs_stock_eligible"
    assert response["risk_filter_applied"] is False
    assert all(sql.lstrip().startswith("SELECT") for sql, _ in session.queries)

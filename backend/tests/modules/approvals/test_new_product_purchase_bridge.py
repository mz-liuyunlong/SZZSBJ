from types import SimpleNamespace

from app.modules.approvals.new_product_purchase_bridge import (
    NewProductPurchaseBridge,
    _details,
)


def test_authoritative_snapshot_does_not_invent_purchase_amount():
    row = SimpleNamespace(
        item_id="20874953767",
        requested_qty=120,
        suggested_qty=100,
        score_snapshot={
            "listing": {"local_name": "真实新品", "local_sku": "SKU-X", "sale_price_amount": 29.99},
            "facts": {"roi": "1.20"},
            "evaluation": {"grade": "A", "total": "8.50"},
        },
    )
    data = _details(row)
    assert data["sku"] == "SKU-X"
    assert data["score_total"] == 8.5
    assert data["initial_grade"] == "A"
    assert data["suggested_qty"] == 100
    assert data["requested_qty"] == 120
    assert data["amount"] is None
    assert data["analysis"]["roi"] == 1.2
    assert data["analysis"]["sellingPrice"] == 29.99


def test_requester_cannot_approve_own_purchase():
    from datetime import UTC, datetime
    from uuid import uuid4

    row = SimpleNamespace(
        id=uuid4(),
        version=1,
        item_id="20874953767",
        score_snapshot={"evaluation": {"total": "8.2", "grade": "A"}},
        suggested_qty=100,
        requested_qty=100,
        applicant_id="alice",
        source_account_ref="account-1",
        status="submitted",
        created_at=datetime.now(UTC),
        reviewed_at=None,
        reviewed_by=None,
        request_reason="new product request",
    )
    item = NewProductPurchaseBridge._item(row, "alice", True)
    assert item.can_review is False
    item2 = NewProductPurchaseBridge._item(row, "bob", True)
    assert item2.can_review is True
    assert item2.risk_level == "unknown"
    assert item2.purchase_details["amount"] is None

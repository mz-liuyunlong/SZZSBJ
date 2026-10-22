"""M2 integration tests run inside the existing guarded, rollback-only PG fixture."""

import pytest
import test_packing_approval as m1
from sqlalchemy import select

from app.core.api import ApiError
from app.modules.pmc_domestic.packing_models import PackingAllocation
from app.modules.pmc_domestic.packing_schemas import PackingQuery
from app.modules.pmc_domestic.packing_service import PackingService

db = m1.db
seeded = m1.seeded
command = m1.command


def test_edit_final_identity_and_default_customs(db, seeded):
    account, _, _ = seeded
    svc = PackingService(db)
    scope = frozenset({account})
    rows = svc.pending(PackingQuery(), scope).items
    options = svc.edit_options(rows[0].id, account, scope)
    target = next(x for x in options.listings if x.item_id != rows[0].item_id)
    cmd = command(
        rows[0],
        target_store_id=target.store_id,
        target_item_id=target.item_id,
        listing_version=target.listing_version,
        edit_reason="业务链接调整",
    )
    result = svc.decide(rows[0].id, cmd, "approve", "fixture", scope)
    assert result.snapshot.item_id == target.item_id
    assert result.source_snapshot.item_id == rows[0].item_id
    assert result.snapshot.sku == rows[0].sku
    assert result.customs_value is False and result.customs_src == "default"
    assert svc.pending(PackingQuery(), scope).total == 0


def test_edit_requires_reason_and_current_listing(db, seeded):
    account, _, _ = seeded
    svc = PackingService(db)
    scope = frozenset({account})
    row = svc.pending(PackingQuery(), scope).items[0]
    target = next(
        x for x in svc.edit_options(row.id, account, scope).listings if x.item_id != row.item_id
    )
    db.commit()
    with pytest.raises(ApiError) as err:
        svc.decide(row.id, command(row, target_item_id=target.item_id), "approve", "fixture", scope)
    assert err.value.details["reason"] == "EDIT_REASON_REQUIRED"
    with pytest.raises(ApiError) as err:
        svc.decide(
            row.id,
            command(
                row, target_item_id=target.item_id, listing_version="f" * 64, edit_reason="身份变化"
            ),
            "approve",
            "fixture",
            scope,
        )
    assert err.value.details["reason"] == "LISTING_CHANGED"


def test_cross_store_uses_published_inbound_and_same_sku(db, seeded):
    from datetime import UTC, datetime

    from app.modules.data_pages.models import WalmartListingDimension as Listing

    account, board, _ = seeded
    db.add(
        Listing(
            source_system="lingxing",
            source_account_ref=account,
            platform_code="walmart",
            store_id="target-store",
            item_id="200000",
            local_sku=board.sku,
            gtin="00000000000001",
            msku="TARGET-SKU",
            standard_status="PUBLISHED",
            raw_status="PUBLISHED",
            fulfillment_type="0",
            business_hash="c" * 64,
            source_observed_at=datetime.now(UTC),
            synced_at=datetime.now(UTC),
        )
    )
    db.flush()
    svc = PackingService(db)
    scope = frozenset({account})
    row = svc.pending(PackingQuery(), scope).items[0]
    options = svc.edit_options(row.id, account, scope)
    assert options.cross_store_proof_available
    target = next(x for x in options.listings if x.store_id == "target-store")
    result = svc.decide(
        row.id,
        command(
            row,
            target_store_id=target.store_id,
            target_item_id=target.item_id,
            listing_version=target.listing_version,
            edit_reason="以原入库单调整销售去向",
        ),
        "approve",
        "fixture",
        scope,
    )
    assert result.snapshot.store_id == "target-store"
    assert result.snapshot.gtin == "00000000000001"
    assert result.source_snapshot.store_id == row.store_id
    assert result.snapshot.board_id == result.source_snapshot.board_id == board.id
    assert result.snapshot.sku == result.source_snapshot.sku == board.sku
    allocation = db.scalar(select(PackingAllocation).where(PackingAllocation.order_id == result.id))
    assert allocation.source_board_id == board.id

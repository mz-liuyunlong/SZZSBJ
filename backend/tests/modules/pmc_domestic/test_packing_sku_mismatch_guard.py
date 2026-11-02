"""Approve path hard-stops a target Listing whose local SKU is another SKU (SKU_MISMATCH).

Owner decision 2026-11-02 (Rocky): a Listing brought in by the remark ItemID whose own local
SKU differs from the row SKU may be shown, but can never become the packing target. No
database: the listing lookup and store names are stubbed, ``final_candidate`` is real.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.api import ApiError
from app.modules.pmc_domestic.packing_rules import listing_version
from app.modules.pmc_domestic.packing_schemas import Candidate
from app.modules.pmc_domestic.packing_service import PackingService, listing_choice


def _candidate() -> Candidate:
    return Candidate(
        id=uuid4(),
        candidate_version="d" * 64,
        source_account_ref="synthetic",
        warehouse_id="16168",
        publication_id=uuid4(),
        board_id=uuid4(),
        inbound_order_sn="RK-1",
        sku="YC1",
        product_name=None,
        store_id="S1",
        store_name=None,
        item_id="33333333333",
        gtin="00000000000000",
        msku="SYN-MSKU",
        purchase_order_sns=[],
        arrival_purchased=10,
        candidate_created_on=None,
        overdue=False,
        stock_balance=10,
        available_quantity=10,
        default_quantity=10,
        can_approve=True,
        blocked_reasons=[],
        source_observed_at=datetime.now(UTC),
    )


def _listing(item_id: str, local_sku: str | None):
    return SimpleNamespace(
        id=uuid4(),
        source_account_ref="synthetic",
        store_id="S1",
        local_sku=local_sku,
        item_id=item_id,
        gtin="00000000000000",
        msku=f"MSKU-{item_id}",
        standard_status="PUBLISHED",
        item_url="https://www.walmart.com/ip/synthetic",
        fulfillment_type="1",
        business_hash="b" * 64,
    )


def _service(listings):
    service = PackingService.__new__(PackingService)
    service.session = None
    service._store_names = lambda account: {"S1": "店铺一"}
    service._listings_by_identity = lambda account, store, item: [
        row for row in listings if row.store_id == store and row.item_id == item
    ]
    return service


def _cmd(listing):
    return SimpleNamespace(
        target_store_id=listing.store_id,
        target_item_id=listing.item_id,
        listing_version=listing_version(listing),
        edit_reason="换到备注的 ItemID",
    )


def test_approve_refuses_a_remark_item_id_whose_listing_local_sku_is_another_sku():
    candidate = _candidate()
    same = _listing("33333333333", "YC1")
    other_sku = _listing("66666666666", "YC9")  # remark ItemID, listing says it is SKU YC9
    service = _service([same, other_sku])

    with pytest.raises(ApiError) as err:
        service.final_candidate(candidate, _cmd(other_sku))
    assert err.value.status_code == 409
    assert err.value.details["reason"] == "SKU_MISMATCH"

    # The same Listing is offered to the dialog flagged, never silently dropped.
    choice = listing_choice(other_sku, candidate, {"S1": "店铺一"})
    assert (choice.sku_mismatch, choice.local_sku) == (True, "YC9")


def test_approve_accepts_the_same_sku_and_a_blank_local_sku_listing():
    candidate = _candidate()
    same = _listing("33333333333", "YC1")
    blank = _listing("44444444444", "")  # by ItemID only: no opinion on the SKU
    service = _service([same, blank])

    assert service.final_candidate(candidate, _cmd(same)).can_approve is True
    final = service.final_candidate(candidate, _cmd(blank))
    assert (final.item_id, final.can_approve) == ("44444444444", True)

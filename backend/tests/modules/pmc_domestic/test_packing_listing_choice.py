"""Edit-dialog Listing options flag a local SKU that differs from the row SKU (#288 P2-2)."""

from types import SimpleNamespace

from app.modules.pmc_domestic.packing_service import listing_choice


def _listing(item_id: str, local_sku: str | None, store_id: str = "S1"):
    return SimpleNamespace(
        id=item_id,
        source_account_ref="primary",
        store_id=store_id,
        local_sku=local_sku,
        item_id=item_id,
        gtin="00012345678905",
        msku="M-1",
        standard_status="PUBLISHED",
        fulfillment_type="1",
        business_hash="h",
    )


def test_listing_found_by_the_attributed_item_id_with_another_local_sku_is_flagged():
    candidate = SimpleNamespace(sku="YC1", store_id="S1")
    stores = {"S1": "Store One"}

    same = listing_choice(_listing("11111111111", "YC1"), candidate, stores)
    blank = listing_choice(_listing("22222222222", None), candidate, stores)
    other = listing_choice(_listing("33333333333", " YC9 "), candidate, stores)

    assert (same.sku_mismatch, same.local_sku) == (False, "YC1")
    assert (blank.sku_mismatch, blank.local_sku) == (False, None)
    assert (other.sku_mismatch, other.local_sku) == (True, "YC9")
    assert other.store_name == "Store One" and other.cross_store is False


def test_cross_store_flag_is_unchanged():
    candidate = SimpleNamespace(sku="YC1", store_id="S1")
    choice = listing_choice(_listing("11111111111", "YC1", store_id="S2"), candidate, {})
    assert choice.cross_store is True and choice.store_name is None

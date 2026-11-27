"""The shared ItemID rule (purchase board + domestic boards), owner decision 2026-10-31."""

from app.modules.pmc_purchase.item_id_resolution import (
    RULE_VERSION,
    ListingCandidate,
    resolve_item_identities,
)

STORE = "110711149541688320"
L_BLANK = ListingCandidate(STORE, "21139862520", None, "00046001636422", "YC01291-1A", "1")
L_SAME = ListingCandidate(STORE, "19051502014", "YC01291", "00012345678905", "YC01291-1Z", "0")
L_OTHER = ListingCandidate(STORE, "55555555555", "OTHER", "00012345678920", "OTHER-1A", "1")
L_ELSEWHERE = ListingCandidate("999", "77777777777", "YC01291", "00012345678937", "X", "1")
ALL = [L_BLANK, L_SAME, L_OTHER, L_ELSEWHERE]


def test_remark_id_is_verified_by_store_even_with_blank_listing_sku():
    found = resolve_item_identities(
        store_id=STORE,
        sku="YC01291",
        remark_texts=["10.14已分配采购", "21139862520"],
        listings=ALL,
    )
    assert found.source == "remark" and found.item_ids == ["21139862520"]
    assert found.identities[0].msku == "YC01291-1A" and found.identities[0].gtin == "00046001636422"
    assert found.identities[0].sku_mismatch is False and found.sku_mismatch_ids == []
    assert RULE_VERSION == "purchase.remark.store.v2"


def test_remark_id_with_other_local_sku_is_kept_and_flagged_and_all_verified_ids_stay():
    found = resolve_item_identities(
        store_id=STORE,
        sku="YC01291",
        remark_texts=["ITEMID:55555555555 19051502014 00012345678905"],
        listings=ALL,
    )
    assert found.item_ids == ["55555555555", "19051502014"]  # GTIN digits ignored
    assert found.sku_mismatch_ids == ["55555555555"]
    assert [i.sku_mismatch for i in found.identities] == [True, False]


def test_remark_id_not_listed_on_this_store_is_only_evidence():
    found = resolve_item_identities(
        store_id=STORE, sku="YC01291", remark_texts=["77777777777"], listings=ALL
    )
    # 77777777777 belongs to another store -> unverified; fall back to the same-SKU listing.
    assert found.unverified_remark_ids == ("77777777777",)
    assert found.source == "listing" and found.item_ids == ["19051502014"]


def test_listing_fallback_keeps_every_same_sku_listing_then_uses_msku_for_blank_ones():
    two = [L_SAME, ListingCandidate(STORE, "20425456045", "YC01291", None, "YC01291-1B", "1")]
    found = resolve_item_identities(store_id=STORE, sku="YC01291", remark_texts=[], listings=two)
    assert found.item_ids == ["19051502014", "20425456045"]  # callers show "multiple"
    by_msku = resolve_item_identities(
        store_id=STORE,
        sku="YC01291",
        remark_texts=[None],
        line_mskus=["YC01291-1A"],
        listings=[L_BLANK, L_OTHER],
    )
    assert by_msku.source == "listing" and by_msku.item_ids == ["21139862520"]
    nothing = resolve_item_identities(
        store_id=STORE, sku="YC01291", remark_texts=[], listings=[L_BLANK, L_OTHER]
    )
    assert nothing.identities == () and nothing.source is None


def test_without_a_store_nothing_is_attributed_here():
    found = resolve_item_identities(
        store_id=None, sku="YC01291", remark_texts=["21139862520"], listings=ALL
    )
    assert found.identities == () and found.unverified_remark_ids == ("21139862520",)

"""288-01: the purchase board pre-attribution (``_ListingIndex.for_line``) applies the
shared ItemID rule, so it cannot drift from the final attribution.

MSKU fallback is allowed only for listings whose local SKU is blank (owner decision
2026-10-31, rule ``purchase.remark.store.v2``).
"""

from app.modules.pmc_purchase.item_id_resolution import ListingCandidate, resolve_item_identities
from app.modules.pmc_purchase.refresh import _Listing, _ListingIndex

A, B = "110711149541688320", "110711149920800256"


def _index(rows):
    """rows: (store, item_id, local_sku, msku)."""
    by_item = {}
    by_store: dict[str, list[ListingCandidate]] = {}
    for store, item_id, local_sku, msku in rows:
        by_item[(store, item_id)] = _Listing(item_id, msku, None, "1", local_sku)
        by_store.setdefault(store, []).append(
            ListingCandidate(store, item_id, local_sku, None, msku, "1")
        )
    grouped: dict[tuple[str, str], set[str]] = {}
    for store, item_id, local_sku, _msku in rows:
        if local_sku:
            grouped.setdefault((store, local_sku), set()).add(item_id)
    by_store_sku = {
        key: by_item[(key[0], next(iter(ids)))] for key, ids in grouped.items() if len(ids) == 1
    }
    return _ListingIndex(by_item, by_store_sku, by_store)


def _final(index, store, sku, msku):
    return resolve_item_identities(
        store_id=store,
        sku=sku,
        remark_texts=(),
        line_mskus=[msku] if msku else (),
        listings=index.candidates_for(store),
    ).item_ids


def test_same_msku_with_a_different_local_sku_is_not_a_fallback_match():
    index = _index([(A, "20000000001", "OTHER", "YC1-1A")])
    assert index.for_line(A, "YC1", "YC1-1A") is None
    assert _final(index, A, "YC1", "YC1-1A") == []


def test_blank_local_sku_is_found_by_the_purchase_line_msku():
    index = _index([(A, "20000000002", None, "YC1-1A"), (A, "20000000003", "  ", "YC1-1B")])
    found = index.for_line(A, "YC1", "YC1-1A")
    assert found is not None and found.item_id == "20000000002"
    assert _final(index, A, "YC1", "YC1-1A") == ["20000000002"]
    assert index.for_line(A, "YC1", None) is None  # no MSKU, nothing to go on


def test_local_sku_match_wins_over_the_msku_fallback():
    index = _index([(A, "20000000004", "YC1", "YC1-1Z"), (A, "20000000005", None, "YC1-1A")])
    found = index.for_line(A, "YC1", "YC1-1A")
    assert found is not None and found.item_id == "20000000004"
    assert _final(index, A, "YC1", "YC1-1A") == ["20000000004"]


def test_same_msku_on_two_stores_stays_with_the_row_store():
    index = _index([(A, "20000000006", None, "YC1-1A"), (B, "20000000007", None, "YC1-1A")])
    assert index.for_line(A, "YC1", "YC1-1A").item_id == "20000000006"
    assert index.for_line(B, "YC1", "YC1-1A").item_id == "20000000007"
    assert _final(index, A, "YC1", "YC1-1A") == ["20000000006"]


def test_several_item_ids_on_one_store_are_never_reduced_to_one():
    index = _index([(A, "20000000008", "YC1", "YC1-1A"), (A, "20000000009", "YC1", "YC1-1B")])
    assert index.for_line(A, "YC1", None) is None
    assert sorted(_final(index, A, "YC1", None)) == ["20000000008", "20000000009"]
    blank = _index([(A, "20000000010", None, "YC1-1A"), (A, "20000000011", None, "YC1-1A")])
    assert blank.for_line(A, "YC1", "YC1-1A") is None
    assert sorted(_final(blank, A, "YC1", "YC1-1A")) == ["20000000010", "20000000011"]


def test_remark_item_id_with_another_listing_sku_is_kept_and_only_flagged():
    index = _index([(A, "20000000012", "OTHER", "OTHER-1A"), (A, "20000000013", "YC1", "YC1-1A")])
    found = resolve_item_identities(
        store_id=A,
        sku="YC1",
        remark_texts=["ITEMID:20000000012"],
        listings=index.candidates_for(A),
    )
    assert found.item_ids == ["20000000012"] and found.sku_mismatch_ids == ["20000000012"]


def test_without_a_store_the_pre_attribution_does_nothing():
    index = _index([(A, "20000000014", "YC1", "YC1-1A")])
    assert index.for_line(None, "YC1", "YC1-1A") is None
    assert index.candidates_for(None) == []

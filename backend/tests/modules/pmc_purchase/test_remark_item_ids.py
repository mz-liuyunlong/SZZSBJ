"""Shared purchase / inbound remark ItemID rules."""

from app.modules.pmc_purchase.remark_item_ids import (
    extract_remark_item_ids,
    item_ids_plan_then_line,
    resolve_purchase_board_item_id,
    validated_remark_item_ids,
)


def test_both_remarks_are_kept_in_legacy_line_first_order() -> None:
    assert item_ids_plan_then_line(["ITEMID:11111111111"], ["ITEMID:22222222222"]) == [
        "22222222222",
        "11111111111",
    ]


def test_line_remark_is_used_when_plan_has_no_eleven_digit_id() -> None:
    assert item_ids_plan_then_line(["00465313943732"], ["ITEMID:20347351964"]) == ["20347351964"]


def test_multiple_remark_ids_are_a_conflict_on_the_purchase_board() -> None:
    attribution = resolve_purchase_board_item_id(
        plan_texts=["ITEMID:20403609913 20347351964"],
        line_texts=[],
        listing_item_id="19051502014",
        packing_slip_item_id=None,
        packing_slip_pending=False,
    )
    assert (attribution.item_id, attribution.source) == (None, "unresolved")


def test_listing_is_used_after_remarks_and_before_packing_slip() -> None:
    attribution = resolve_purchase_board_item_id(
        plan_texts=[],
        line_texts=[],
        listing_item_id="19051502014",
        packing_slip_item_id="44444444444",
        packing_slip_pending=True,
    )
    assert (attribution.item_id, attribution.source) == ("19051502014", "from_listing")


def test_extract_keeps_every_eleven_digits_and_skips_gtin() -> None:
    assert extract_remark_item_ids(
        ["ITEMID:20403609913 | 草稿:CG261017-039 20347351964", "00465313943732"]
    ) == ["20403609913", "20347351964"]


def test_legacy_merge_validates_sku_candidates_and_keeps_source_order() -> None:
    assert validated_remark_item_ids(
        ["ITEMID:11111111111 99999999999"],
        ["22222222222 00465313943732 11111111111"],
        ["11111111111", "22222222222"],
    ) == ["22222222222", "11111111111"]

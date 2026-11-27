"""Tests for the local-only, read-only monitor RAW field adapter."""

from app.modules.data_pages.monitor_raw_fields import parse_monitor_raw_fields


def test_decodo_known_raw_fields() -> None:
    result = parse_monitor_raw_fields(
        {
            "hasStrikethrough": True,
            "strikethroughSource": "WAS_TEXT",
            "otherSellersPresent": False,
            "sellerNames": ["Ritonbr"],
            "sellerOfferCount": 1,
            "productImageUrls": ["https://example.invalid/a.jpg"],
            "productImageCount": 1,
            "keyFeatures": ["Feature A", "Feature B"],
            "ratingSummary": {"reviewFetchStatus": "OK"},
        }
    )
    assert result.has_strikethrough is True
    assert result.other_sellers_present is False
    assert result.seller_offer_count == 1
    assert result.seller_names == ("Ritonbr",)
    assert result.image_count == 1
    assert result.key_features == ("Feature A", "Feature B")
    assert result.review_fetch_status == "OK"


def test_explicit_false_and_zero_are_not_missing() -> None:
    result = parse_monitor_raw_fields(
        {
            "hasStrikethrough": False,
            "otherSellersPresent": False,
            "sellerOfferCount": 0,
            "productImageUrls": [],
            "productImageCount": 0,
        }
    )
    assert result.has_strikethrough is False
    assert result.other_sellers_present is False
    assert result.seller_offer_count == 0
    assert result.image_urls_observed is True
    assert result.image_count == 0


def test_incomplete_result_stays_unknown_not_normal() -> None:
    result = parse_monitor_raw_fields({"sellerOfferCount": None})
    assert result.has_strikethrough is None
    assert result.other_sellers_present is None
    assert result.seller_offer_count is None
    assert result.image_count is None
    assert result.review_fetch_status is None

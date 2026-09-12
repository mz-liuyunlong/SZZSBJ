from decimal import Decimal

import pytest

from app.modules.integration_sync.parsers.lingxing_product_info import (
    ProductInfoParseError,
    parse_product_info_fixture,
)
from app.modules.integration_sync.parsers.lingxing_product_list import (
    ProductListParseError,
    parse_productlist_sku_ids,
)
from app.modules.sku_detail.calculations import calculate_sku_profile


def _detail_fixture() -> dict[str, object]:
    return {
        "data": {
            "product_name": "Synthetic Product",
            "sku": "SYNTHETIC-SKU",
            "pic_url": "https://example.invalid/main.jpg",
            "product_developer": "Synthetic Developer",
            "product_developer_uid": "developer-1",
            "cg_delivery": "7",
            "cg_price": "12.3400",
            "cg_product_material": "Synthetic Material",
            "bg_customs_export_name": "Synthetic CN",
            "bg_customs_import_name": "Synthetic EN",
            "bg_customs_import_price": "3.2100",
            "bg_export_hs_code": "001234",
            "permission_user_info": {
                "permission_uid": "owner-1",
                "permission_user_name": "Synthetic Owner",
            },
            "clearance": {
                "customs_clearance_material": "Synthetic CN Material",
                "customs_clearance_usage": "Synthetic Usage",
                "customs_clearance_en_material": "Synthetic EN Material",
            },
            "product_logistics_relation": {
                "US_cg_transport_costs": "8.0000",
                "US_currency": "usd",
            },
            "cg_product_length": "10",
            "cg_product_width": "5",
            "cg_product_height": "2",
            "cg_product_net_weight": "500",
            "cg_product_gross_weight": "600",
            "cg_package_length": "11",
            "cg_package_width": "6",
            "cg_package_height": "3",
            "cg_box_length": "40",
            "cg_box_width": "30",
            "cg_box_height": "20",
            "cg_box_pcs": "4",
            "cg_box_weight": "8",
            "picture_list": [
                {
                    "pic_url": "https://example.invalid/one.jpg",
                    "is_primary": True,
                }
            ],
            "global_tags": [{"id": "tag-1", "name": "Synthetic Tag", "color": "blue"}],
        }
    }


def test_productlist_parser_uses_data_id_only_and_rejects_duplicates() -> None:
    assert parse_productlist_sku_ids({"data": [{"id": "synthetic-2"}, {"id": 1}]}) == [
        "synthetic-2",
        "1",
    ]
    with pytest.raises(ProductListParseError, match="DUPLICATE"):
        parse_productlist_sku_ids({"data": [{"id": "same"}, {"id": "same"}]})


def test_product_info_fixture_maps_approved_fields_and_children() -> None:
    parsed = parse_product_info_fixture(_detail_fixture())
    assert parsed.product_name == "Synthetic Product"
    assert parsed.lingxing_sku_code == "SYNTHETIC-SKU"
    assert parsed.purchase_cost_cny == Decimal("12.3400")
    assert parsed.purchase_cost_currency_code == "CNY"
    assert parsed.customs_declared_unit_price == Decimal("3.2100")
    assert parsed.customs_declared_currency is None
    assert parsed.china_hs_code == "001234"
    assert parsed.us_first_leg_currency == "USD"
    assert parsed.product_length_cm == Decimal(10)
    assert parsed.package_height_cm == Decimal(3)
    assert parsed.box_pcs == 4
    assert len(parsed.images) == 1
    assert len(parsed.tags) == 1


def test_parser_rejects_ambiguous_owner_and_logistics_cardinality() -> None:
    fixture = _detail_fixture()
    fixture["data"]["permission_user_info"] = [{}, {}]  # type: ignore[index]
    with pytest.raises(ProductInfoParseError, match="OWNER_CARDINALITY"):
        parse_product_info_fixture(fixture)

    fixture = _detail_fixture()
    fixture["data"]["product_logistics_relation"] = [  # type: ignore[index]
        {"US_currency": "USD", "US_cg_transport_costs": "1"},
        {"US_currency": "USD", "US_cg_transport_costs": "2"},
    ]
    with pytest.raises(ProductInfoParseError, match="LOGISTICS_CARDINALITY"):
        parse_product_info_fixture(fixture)


def test_dws_calculations_use_decimal_half_up_and_23_checks() -> None:
    parsed = parse_product_info_fixture(_detail_fixture())
    result = calculate_sku_profile(parsed)
    assert result.product_volume_cm3 == Decimal("100.0000")
    assert result.box_volume_cbm == Decimal("0.0240")
    assert result.product_net_weight_kg == Decimal("0.5000")
    assert result.unit_box_weight_kg == Decimal("2.0000")
    assert result.unit_first_leg_cost == Decimal("2.0000")
    assert result.data_quality_score == Decimal("100.00")
    assert result.missing_fields_json == []


def test_dws_zero_box_pieces_does_not_divide() -> None:
    fixture = _detail_fixture()
    fixture["data"]["cg_box_pcs"] = "0"  # type: ignore[index]
    result = calculate_sku_profile(parse_product_info_fixture(fixture))
    assert result.unit_box_weight_kg is None
    assert result.unit_first_leg_cost is None


def test_dws_calculation_rejects_numeric_overflow() -> None:
    fixture = _detail_fixture()
    fixture["data"]["cg_product_length"] = "99999999"  # type: ignore[index]
    fixture["data"]["cg_product_width"] = "99999999"  # type: ignore[index]

    with pytest.raises(ArithmeticError, match="NUMERIC_OUT_OF_RANGE"):
        calculate_sku_profile(parse_product_info_fixture(fixture))

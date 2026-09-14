from decimal import Decimal, InvalidOperation
from typing import cast

from pydantic import BaseModel, ConfigDict

CONTRACT_FIELD_MISMATCH = "CONTRACT_FIELD_MISMATCH"


class ProductInfoParseError(ValueError):
    """Safe parser error that never embeds the rejected source value."""


class ParsedImage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int
    pic_url: str
    is_primary: bool | None


class ParsedTag(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int
    global_tag_id: str | None
    tag_name: str | None
    color: str | None


class ParsedSkuDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    product_name: str | None
    lingxing_sku_code: str | None
    main_image_url: str | None
    product_developer_name: str | None
    product_developer_uid: str | None
    purchase_delivery_days: int | None
    purchase_cost_cny: Decimal | None
    purchase_cost_currency_code: str | None
    purchase_material: str | None
    customs_export_name_cn: str | None
    customs_import_name_en: str | None
    customs_declared_unit_price: Decimal | None
    customs_declared_currency: str | None
    china_hs_code: str | None
    owner_uid: str | None
    owner_name: str | None
    clearance_material_cn: str | None
    clearance_usage_cn: str | None
    clearance_material_en: str | None
    us_first_leg_cost: Decimal | None
    us_first_leg_currency: str | None
    product_length_cm: Decimal | None
    product_width_cm: Decimal | None
    product_height_cm: Decimal | None
    product_net_weight_g: Decimal | None
    package_length_cm: Decimal | None
    package_width_cm: Decimal | None
    package_height_cm: Decimal | None
    box_length_cm: Decimal | None
    box_width_cm: Decimal | None
    box_height_cm: Decimal | None
    box_pcs: int | None
    product_gross_weight_g: Decimal | None
    box_weight_kg: Decimal | None
    images: tuple[ParsedImage, ...]
    tags: tuple[ParsedTag, ...]


class ParsedBatchProductInfoItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    lingxing_sku_id: str
    detail: ParsedSkuDetail


def parse_product_info_fixture(payload: object) -> ParsedSkuDetail:
    data = _contract_data(payload, list_expected=False)
    assert isinstance(data, dict)
    return _parse_detail(data)


def parse_batch_product_info_fixture(
    payload: object,
    *,
    expected_lingxing_sku_ids: tuple[str, ...],
) -> tuple[ParsedBatchProductInfoItem, ...]:
    data = _contract_data(payload, list_expected=True)
    assert isinstance(data, list)
    expected = tuple(_required_identifier(value) for value in expected_lingxing_sku_ids)
    if not expected or len(set(expected)) != len(expected):
        raise ProductInfoParseError(CONTRACT_FIELD_MISMATCH)
    parsed_by_id: dict[str, ParsedSkuDetail] = {}
    for item in data:
        if not isinstance(item, dict):
            raise ProductInfoParseError(CONTRACT_FIELD_MISMATCH)
        lingxing_sku_id = _required_identifier(item.get("id"))
        if lingxing_sku_id in parsed_by_id:
            raise ProductInfoParseError(CONTRACT_FIELD_MISMATCH)
        parsed_by_id[lingxing_sku_id] = _parse_detail(item)
    if set(parsed_by_id) != set(expected):
        raise ProductInfoParseError(CONTRACT_FIELD_MISMATCH)
    return tuple(
        ParsedBatchProductInfoItem(
            lingxing_sku_id=lingxing_sku_id,
            detail=parsed_by_id[lingxing_sku_id],
        )
        for lingxing_sku_id in expected
    )


def _contract_data(payload: object, *, list_expected: bool) -> dict[str, object] | list[object]:
    if not isinstance(payload, dict):
        raise ProductInfoParseError(CONTRACT_FIELD_MISMATCH)
    code = payload.get("code")
    if isinstance(code, bool) or not isinstance(code, int):
        raise ProductInfoParseError(CONTRACT_FIELD_MISMATCH)
    data = payload.get("data")
    if (list_expected and not isinstance(data, list)) or (
        not list_expected and not isinstance(data, dict)
    ):
        raise ProductInfoParseError(CONTRACT_FIELD_MISMATCH)
    return cast(dict[str, object] | list[object], data)


def _parse_detail(data: dict[str, object]) -> ParsedSkuDetail:
    owner = _one_mapping(data.get("permission_user_info"), "PRODUCT_INFO_OWNER_CARDINALITY")
    logistics = _one_us_logistics(data.get("product_logistics_relation"))
    purchase_cost = _decimal(data.get("cg_price"))
    first_leg_cost = _decimal(logistics.get("US_cg_transport_costs"))
    first_leg_currency = _currency(logistics.get("US_currency"))
    if (first_leg_cost is None) != (first_leg_currency is None):
        raise ProductInfoParseError("PRODUCT_INFO_FIRST_LEG_CURRENCY_PAIR_INVALID")
    return ParsedSkuDetail(
        product_name=_text(data.get("product_name")),
        lingxing_sku_code=_text(data.get("sku")),
        main_image_url=_https_url(data.get("pic_url")),
        product_developer_name=_text(data.get("product_developer")),
        product_developer_uid=_identifier(data.get("product_developer_uid")),
        purchase_delivery_days=_integer(data.get("cg_delivery")),
        purchase_cost_cny=purchase_cost,
        purchase_cost_currency_code="CNY" if purchase_cost is not None else None,
        purchase_material=_text(data.get("cg_product_material")),
        customs_export_name_cn=_text(data.get("bg_customs_export_name")),
        customs_import_name_en=_text(data.get("bg_customs_import_name")),
        customs_declared_unit_price=_decimal(data.get("bg_customs_import_price")),
        customs_declared_currency=None,
        china_hs_code=_identifier(data.get("bg_export_hs_code")),
        owner_uid=_identifier(owner.get("permission_uid")),
        owner_name=_text(owner.get("permission_user_name")),
        clearance_material_cn=_nested_text(data, "clearance", "customs_clearance_material"),
        clearance_usage_cn=_nested_text(data, "clearance", "customs_clearance_usage"),
        clearance_material_en=_nested_text(data, "clearance", "customs_clearance_en_material"),
        us_first_leg_cost=first_leg_cost,
        us_first_leg_currency=first_leg_currency,
        product_length_cm=_decimal(data.get("cg_product_length")),
        product_width_cm=_decimal(data.get("cg_product_width")),
        product_height_cm=_decimal(data.get("cg_product_height")),
        product_net_weight_g=_decimal(data.get("cg_product_net_weight")),
        package_length_cm=_decimal(data.get("cg_package_length")),
        package_width_cm=_decimal(data.get("cg_package_width")),
        package_height_cm=_decimal(data.get("cg_package_height")),
        box_length_cm=_decimal(data.get("cg_box_length")),
        box_width_cm=_decimal(data.get("cg_box_width")),
        box_height_cm=_decimal(data.get("cg_box_height")),
        box_pcs=_integer(data.get("cg_box_pcs")),
        product_gross_weight_g=_decimal(data.get("cg_product_gross_weight")),
        box_weight_kg=_decimal(data.get("cg_box_weight")),
        images=_images(data.get("picture_list")),
        tags=_tags(data.get("global_tags")),
    )


def _text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProductInfoParseError("PRODUCT_INFO_TEXT_INVALID")
    normalized = value.strip()
    return normalized or None


def _identifier(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ProductInfoParseError("PRODUCT_INFO_IDENTIFIER_INVALID")
    normalized = str(value).strip()
    return normalized or None


def _required_identifier(value: object) -> str:
    result = _identifier(value)
    if result is None:
        raise ProductInfoParseError(CONTRACT_FIELD_MISMATCH)
    return result


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ProductInfoParseError("PRODUCT_INFO_DECIMAL_INVALID")
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ProductInfoParseError("PRODUCT_INFO_DECIMAL_INVALID") from None
    if not result.is_finite() or result < 0:
        raise ProductInfoParseError("PRODUCT_INFO_DECIMAL_INVALID")
    return result


def _integer(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ProductInfoParseError("PRODUCT_INFO_INTEGER_INVALID")
    try:
        result = int(value)
    except ValueError:
        raise ProductInfoParseError("PRODUCT_INFO_INTEGER_INVALID") from None
    if str(result) != str(value).strip() or result < 0:
        raise ProductInfoParseError("PRODUCT_INFO_INTEGER_INVALID")
    return result


def _currency(value: object) -> str | None:
    result = _text(value)
    if result is None:
        return None
    result = result.upper()
    if len(result) != 3 or not result.isalpha():
        raise ProductInfoParseError("PRODUCT_INFO_CURRENCY_INVALID")
    return result


def _https_url(value: object) -> str | None:
    result = _text(value)
    if result is not None and not result.startswith("https://"):
        raise ProductInfoParseError("PRODUCT_INFO_URL_INVALID")
    return result


def _one_mapping(value: object, error: str) -> dict[str, object]:
    if value is None:
        return {}
    if isinstance(value, list):
        if len(value) > 1 or (value and not isinstance(value[0], dict)):
            raise ProductInfoParseError(error)
        return {} if not value else value[0]
    raise ProductInfoParseError(CONTRACT_FIELD_MISMATCH)


def _one_us_logistics(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ProductInfoParseError(CONTRACT_FIELD_MISMATCH)
    us_candidates = [
        item for item in value if "US_cg_transport_costs" in item or "US_currency" in item
    ]
    if len(us_candidates) > 1:
        raise ProductInfoParseError("PRODUCT_INFO_LOGISTICS_CARDINALITY")
    return {} if not us_candidates else us_candidates[0]


def _nested_text(data: dict[str, object], parent: str, child: str) -> str | None:
    value = data.get(parent)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ProductInfoParseError("PRODUCT_INFO_NESTING_INVALID")
    return _text(value.get(child))


def _images(value: object) -> tuple[ParsedImage, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ProductInfoParseError("PRODUCT_INFO_IMAGES_INVALID")
    result: list[ParsedImage] = []
    primary_count = 0
    for ordinal, item in enumerate(value):
        if not isinstance(item, dict):
            raise ProductInfoParseError("PRODUCT_INFO_IMAGES_INVALID")
        url = _https_url(item.get("pic_url"))
        if url is None:
            raise ProductInfoParseError("PRODUCT_INFO_IMAGES_INVALID")
        primary_value = item.get("is_primary")
        if isinstance(primary_value, bool) or primary_value not in (None, 0, 1):
            raise ProductInfoParseError(CONTRACT_FIELD_MISMATCH)
        primary = None if primary_value is None else bool(primary_value)
        primary_count += primary is True
        result.append(ParsedImage(ordinal=ordinal, pic_url=url, is_primary=primary))
    if primary_count > 1:
        raise ProductInfoParseError("PRODUCT_INFO_IMAGES_PRIMARY_INVALID")
    return tuple(result)


def _tags(value: object) -> tuple[ParsedTag, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ProductInfoParseError("PRODUCT_INFO_TAGS_INVALID")
    result: list[ParsedTag] = []
    seen_ids: set[str] = set()
    for ordinal, item in enumerate(value):
        if not isinstance(item, dict):
            raise ProductInfoParseError("PRODUCT_INFO_TAGS_INVALID")
        tag_id = _identifier(item.get("global_tag_id"))
        if tag_id is not None and tag_id in seen_ids:
            raise ProductInfoParseError("PRODUCT_INFO_TAGS_DUPLICATE")
        if tag_id is not None:
            seen_ids.add(tag_id)
        result.append(
            ParsedTag(
                ordinal=ordinal,
                global_tag_id=tag_id,
                tag_name=_text(item.get("tag_name")),
                color=_text(item.get("color")),
            )
        )
    return tuple(result)

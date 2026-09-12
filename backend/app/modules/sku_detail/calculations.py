from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

FOUR_PLACES = Decimal("0.0001")
MAX_NUMERIC = Decimal("99999999999999.9999")


class SnapshotValues(Protocol):
    product_name: str | None
    lingxing_sku_code: str | None
    purchase_delivery_days: int | None
    purchase_cost_cny: Decimal | None
    purchase_cost_currency_code: str | None
    purchase_material: str | None
    customs_export_name_cn: str | None
    customs_import_name_en: str | None
    customs_declared_unit_price: Decimal | None
    china_hs_code: str | None
    product_length_cm: Decimal | None
    product_width_cm: Decimal | None
    product_height_cm: Decimal | None
    product_net_weight_g: Decimal | None
    product_gross_weight_g: Decimal | None
    package_length_cm: Decimal | None
    package_width_cm: Decimal | None
    package_height_cm: Decimal | None
    box_length_cm: Decimal | None
    box_width_cm: Decimal | None
    box_height_cm: Decimal | None
    box_pcs: int | None
    box_weight_kg: Decimal | None
    us_first_leg_cost: Decimal | None
    us_first_leg_currency: str | None
    clearance_material_cn: str | None
    clearance_usage_cn: str | None
    clearance_material_en: str | None


@dataclass(frozen=True, slots=True)
class CalculatedSkuProfile:
    product_volume_cm3: Decimal | None
    package_volume_cm3: Decimal | None
    box_volume_cm3: Decimal | None
    box_volume_cbm: Decimal | None
    product_net_weight_kg: Decimal | None
    product_gross_weight_kg: Decimal | None
    unit_box_weight_kg: Decimal | None
    purchase_cost_cny: Decimal | None
    purchase_cost_currency_code: str | None
    us_first_leg_cost: Decimal | None
    us_first_leg_currency: str | None
    unit_first_leg_cost: Decimal | None
    unit_first_leg_currency: str | None
    has_customs_info: bool
    has_package_info: bool
    has_logistics_info: bool
    missing_fields_json: list[str]
    data_quality_score: Decimal


def calculate_sku_profile(value: SnapshotValues) -> CalculatedSkuProfile:
    checks = {
        "product_name": value.product_name is not None,
        "lingxing_sku_code": value.lingxing_sku_code is not None,
        "purchase_delivery_days": value.purchase_delivery_days is not None,
        "purchase_cost_cny": value.purchase_cost_cny is not None
        and value.purchase_cost_currency_code == "CNY",
        "purchase_material": value.purchase_material is not None,
        "customs_export_name_cn": value.customs_export_name_cn is not None,
        "customs_import_name_en": value.customs_import_name_en is not None,
        "customs_declared_unit_price": value.customs_declared_unit_price is not None,
        "china_hs_code": value.china_hs_code is not None,
        "product_length_cm": value.product_length_cm is not None,
        "product_width_cm": value.product_width_cm is not None,
        "product_height_cm": value.product_height_cm is not None,
        "product_net_weight_g": value.product_net_weight_g is not None,
        "product_gross_weight_g": value.product_gross_weight_g is not None,
        "package_length_cm": value.package_length_cm is not None,
        "package_width_cm": value.package_width_cm is not None,
        "package_height_cm": value.package_height_cm is not None,
        "box_length_cm": value.box_length_cm is not None,
        "box_width_cm": value.box_width_cm is not None,
        "box_height_cm": value.box_height_cm is not None,
        "box_pcs": value.box_pcs is not None,
        "box_weight_kg": value.box_weight_kg is not None,
        "us_first_leg_cost": value.us_first_leg_cost is not None
        and value.us_first_leg_currency is not None,
    }
    missing = sorted(name for name, present in checks.items() if not present)
    product_volume = _volume(
        value.product_length_cm, value.product_width_cm, value.product_height_cm
    )
    package_volume = _volume(
        value.package_length_cm, value.package_width_cm, value.package_height_cm
    )
    box_volume = _volume(value.box_length_cm, value.box_width_cm, value.box_height_cm)
    box_pcs = Decimal(value.box_pcs) if value.box_pcs and value.box_pcs > 0 else None
    return CalculatedSkuProfile(
        product_volume_cm3=product_volume,
        package_volume_cm3=package_volume,
        box_volume_cm3=box_volume,
        box_volume_cbm=_divide(box_volume, Decimal(1_000_000)),
        product_net_weight_kg=_divide(value.product_net_weight_g, Decimal(1_000)),
        product_gross_weight_kg=_divide(value.product_gross_weight_g, Decimal(1_000)),
        unit_box_weight_kg=_divide(value.box_weight_kg, box_pcs),
        purchase_cost_cny=_quantize(value.purchase_cost_cny),
        purchase_cost_currency_code=value.purchase_cost_currency_code,
        us_first_leg_cost=_quantize(value.us_first_leg_cost),
        us_first_leg_currency=value.us_first_leg_currency,
        unit_first_leg_cost=_divide(value.us_first_leg_cost, box_pcs),
        unit_first_leg_currency=(value.us_first_leg_currency if box_pcs is not None else None),
        has_customs_info=any(
            field is not None
            for field in (
                value.customs_export_name_cn,
                value.customs_import_name_en,
                value.customs_declared_unit_price,
                value.china_hs_code,
                value.clearance_material_cn,
                value.clearance_usage_cn,
                value.clearance_material_en,
            )
        ),
        has_package_info=all(
            field is not None and field > 0
            for field in (
                value.package_length_cm,
                value.package_width_cm,
                value.package_height_cm,
            )
        ),
        has_logistics_info=value.us_first_leg_cost is not None
        and value.us_first_leg_currency is not None,
        missing_fields_json=missing,
        data_quality_score=(
            Decimal(100) * Decimal(len(checks) - len(missing)) / Decimal(len(checks))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
    )


def _volume(
    length: Decimal | None, width: Decimal | None, height: Decimal | None
) -> Decimal | None:
    if length is None or width is None or height is None:
        return None
    return _quantize(length * width * height)


def _divide(value: Decimal | None, divisor: Decimal | None) -> Decimal | None:
    if value is None or divisor is None or divisor <= 0:
        return None
    return _quantize(value / divisor)


def _quantize(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if value < 0 or value > MAX_NUMERIC:
        raise ArithmeticError("SKU_CALCULATION_NUMERIC_OUT_OF_RANGE")
    return value.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)

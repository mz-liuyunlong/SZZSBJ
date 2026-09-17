# ruff: noqa: E501
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.product_management.calculations import calculate_sku_pricing
from app.modules.product_management.repository import ProductManagementRepository
from app.modules.product_management.service import ProductManagementService


@dataclass(frozen=True, slots=True)
class DailySalesCostResolution:
    """Product Management cost projection reused by Daily Sales and Order Profit."""

    owner_ref: str | None
    purchase_cost_unit_cny: Decimal | None
    first_leg_cost_unit_cny: Decimal | None
    wfs_fee_unit_usd: Decimal | None
    storage_fee_unit_usd: Decimal | None
    exchange_rate: Decimal | None
    fx_date: object | None
    fx_source: str | None
    rule_version: str
    calculation_status: str
    root_missing_codes: tuple[str, ...]


def normalize_sku_key(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().casefold()
    return normalized or None


def load_daily_sales_costs(
    session: Session,
    *,
    source_account_ref: str,
    at: datetime | None = None,
) -> dict[str, DailySalesCostResolution]:
    """Resolve SKU costs with the exact Product Management pricing formula and defaults.

    Product Management calculates costs dynamically even when no persisted pricing projection or
    pricing-rule row exists. Daily Sales must follow that behavior instead of depending on the
    optional pricing projection tables.
    """

    effective_at = at or datetime.now(UTC)
    repository = ProductManagementRepository(session)
    effective_rule = repository.get_effective_rule(effective_at, source_account_ref)
    pricing_rule = ProductManagementService._sku_pricing_rule(effective_rule)
    rule_version = (
        effective_rule.version if effective_rule is not None else "sku-pricing-defaults-v1"
    )
    fx_date = effective_rule.fx_date if effective_rule is not None else None
    fx_source = (
        effective_rule.fx_source
        if effective_rule is not None and effective_rule.fx_source
        else "sku-pricing-defaults-v1"
    )

    rows = (
        session.execute(
            text(
                "select i.id identity_id,i.mapping_status,i.updated_at identity_updated_at,"
                "p.sku product_sku,i.lingxing_sku_code identity_sku,c.lingxing_sku_code current_sku,"
                "coalesce(nullif(trim(c.owner_name),''),nullif(trim(c.owner_uid),'')) owner_ref,"
                "coalesce(b.purchase_cost_cny,c.purchase_cost_cny) purchase_cost_cny,"
                "c.product_gross_weight_g,c.package_length_cm,c.package_width_cm,c.package_height_cm,"
                "c.source_observed_at,coalesce(img.image_count,0) image_count "
                "from dwd_lingxing_sku_identity_index i "
                "left join products p on p.id=i.product_id and p.deleted_at is null "
                "left join dwd_lingxing_sku_product_info_current c on c.identity_id=i.id "
                "left join dws_sku_base_profile_current b on b.identity_id=i.id "
                "left join lateral (select count(*) image_count from dwd_lingxing_sku_product_images x "
                "where c.source_snapshot_id is not null and x.source_snapshot_id=c.source_snapshot_id) img on true "
                "where i.source_account_ref=:account and i.is_active=true "
                "order by case when i.mapping_status='confirmed' then 0 else 1 end,"
                "c.source_observed_at desc nulls last,i.updated_at desc"
            ),
            {"account": source_account_ref},
        )
        .mappings()
        .all()
    )

    resolved: dict[str, DailySalesCostResolution] = {}
    for row in rows:
        calculation = calculate_sku_pricing(
            purchase_cost_cny=row["purchase_cost_cny"],
            product_gross_weight_g=row["product_gross_weight_g"],
            dimensions_cm=(
                row["package_length_cm"],
                row["package_width_cm"],
                row["package_height_cm"],
            ),
            image_count=int(row["image_count"] or 0),
            rule=pricing_rule,
        )
        value = DailySalesCostResolution(
            owner_ref=row["owner_ref"],
            purchase_cost_unit_cny=calculation.purchase_cost_cny,
            first_leg_cost_unit_cny=calculation.first_leg_fee_cny,
            wfs_fee_unit_usd=calculation.wfs_fulfillment_fee_usd,
            storage_fee_unit_usd=calculation.daily_storage_fee_per_unit_usd,
            exchange_rate=pricing_rule.usd_cny_rate,
            fx_date=fx_date,
            fx_source=fx_source,
            rule_version=rule_version,
            calculation_status=calculation.calculation_status,
            root_missing_codes=tuple(calculation.root_missing_codes),
        )
        aliases = (
            normalize_sku_key(row["product_sku"]),
            normalize_sku_key(row["identity_sku"]),
            normalize_sku_key(row["current_sku"]),
        )
        for alias in aliases:
            if alias is not None and alias not in resolved:
                resolved[alias] = value

    return resolved

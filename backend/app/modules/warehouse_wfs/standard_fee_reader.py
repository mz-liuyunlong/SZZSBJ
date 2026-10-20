"""Read the current Product Management WFS fee without writing data."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.data_pages.models import WalmartListingDimension
from app.modules.product_management.repository import ProductManagementRepository
from app.modules.product_management.service import ProductManagementService
from app.modules.products.models import Product
from app.modules.sku_detail.models import (
    LingxingSkuIdentity,
    LingxingSkuProductInfoCurrent,
    SkuBaseProfileCurrent,
)
from app.modules.warehouse_wfs.anomaly_detection import WfsStandardFee


class WfsStandardFeeError(ValueError):
    """Ambiguous identity: never select an arbitrary product."""


def read_product_management_wfs_fee(
    session: Session,
    *,
    source_account_ref: str,
    store_id: str,
    item_id: str,
    msku: str,
) -> WfsStandardFee | None:
    """Resolve an exact listing and reuse Product Management's live formula.

    local_sku -> products.sku is accepted only when uniquely linked to
    one confirmed, active Lingxing SKU identity in the same account.
    Missing or unconfirmed mapping returns None, not a fabricated fee.
    """
    if not all((source_account_ref, store_id, item_id, msku)):
        raise WfsStandardFeeError("WFS_INVALID_STANDARD_IDENTITY")

    listings = session.scalars(
        select(WalmartListingDimension).where(
            WalmartListingDimension.source_account_ref == source_account_ref,
            WalmartListingDimension.store_id == store_id,
            WalmartListingDimension.item_id == item_id,
            WalmartListingDimension.msku == msku,
        )
    ).all()

    if len(listings) != 1:
        return None

    local_sku = (listings[0].local_sku or "").strip()
    if not local_sku:
        return None

    products = session.scalars(
        select(Product).where(
            Product.sku == local_sku,
            Product.deleted_at.is_(None),
        )
    ).all()

    if len(products) != 1:
        return None

    identities = session.scalars(
        select(LingxingSkuIdentity).where(
            LingxingSkuIdentity.source_account_ref == source_account_ref,
            LingxingSkuIdentity.product_id == products[0].id,
            LingxingSkuIdentity.is_active.is_(True),
            LingxingSkuIdentity.mapping_status == "confirmed",
        )
    ).all()

    if len(identities) != 1:
        return None

    identity = identities[0]

    current = session.scalar(
        select(LingxingSkuProductInfoCurrent).where(
            LingxingSkuProductInfoCurrent.identity_id == identity.id
        )
    )
    profile = session.scalar(
        select(SkuBaseProfileCurrent).where(SkuBaseProfileCurrent.identity_id == identity.id)
    )

    effective_rules = ProductManagementRepository(session).list_effective_rules(
        datetime.now(UTC),
        frozenset({source_account_ref}),
    )
    active_rule = effective_rules.get(source_account_ref)

    rule = ProductManagementService._sku_pricing_rule(active_rule)
    calculation = ProductManagementService._sku_pricing_calculation(current, profile, 0, rule)

    fee = calculation.wfs_fulfillment_fee_usd
    if calculation.wfs_calc_status != "ok" or fee is None or not fee.is_finite() or fee <= 0:
        return None

    return WfsStandardFee(
        source_account_ref=source_account_ref,
        store_id=store_id,
        msku=msku,
        unit_fee=fee,
        source="product_management_live",
        rule_version=(
            active_rule.version if active_rule is not None else "sku-pricing-defaults-v1"
        ),
    )

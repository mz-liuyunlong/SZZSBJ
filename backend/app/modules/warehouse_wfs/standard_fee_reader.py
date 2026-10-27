"""Read the current Product Management WFS fee without writing data."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, tuple_
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


WfsStandardIdentity = tuple[str, str, str, str]


def read_product_management_wfs_fees(
    session: Session,
    *,
    identities: frozenset[WfsStandardIdentity],
) -> dict[WfsStandardIdentity, WfsStandardFee]:
    """Resolve WFS standards in bounded batch queries.

    Ambiguous or incomplete identities are omitted. The caller must treat every
    omitted identity as unresolved and must not fabricate a default fee.
    """

    if not identities:
        return {}
    if any(
        not all(value and value == value.strip() for value in identity) for identity in identities
    ):
        raise WfsStandardFeeError("WFS_INVALID_STANDARD_IDENTITY")

    listing_rows = session.execute(
        select(
            WalmartListingDimension.source_account_ref,
            WalmartListingDimension.store_id,
            WalmartListingDimension.item_id,
            WalmartListingDimension.msku,
            WalmartListingDimension.local_sku,
        ).where(
            tuple_(
                WalmartListingDimension.source_account_ref,
                WalmartListingDimension.store_id,
                WalmartListingDimension.item_id,
                WalmartListingDimension.msku,
            ).in_(identities)
        )
    ).all()
    listings_by_identity: dict[WfsStandardIdentity, list[str]] = {}
    for account_ref, store_id, item_id, msku, local_sku in listing_rows:
        normalized = (local_sku or "").strip()
        if normalized:
            listings_by_identity.setdefault((account_ref, store_id, item_id, msku), []).append(
                normalized
            )

    local_skus = {values[0] for values in listings_by_identity.values() if len(values) == 1}
    product_rows = session.execute(
        select(Product.sku, Product.id).where(
            Product.sku.in_(local_skus),
            Product.deleted_at.is_(None),
        )
    ).all()
    products_by_sku: dict[str, list[UUID]] = {}
    for sku, product_id in product_rows:
        products_by_sku.setdefault(sku, []).append(product_id)

    account_refs = frozenset(identity[0] for identity in identities)
    product_ids: set[UUID] = set()
    for sku in local_skus:
        matches = products_by_sku.get(sku, [])
        if len(matches) == 1:
            product_ids.add(matches[0])
    identity_rows = session.execute(
        select(
            LingxingSkuIdentity.source_account_ref,
            LingxingSkuIdentity.product_id,
            LingxingSkuIdentity.id,
        ).where(
            LingxingSkuIdentity.source_account_ref.in_(account_refs),
            LingxingSkuIdentity.product_id.in_(product_ids),
            LingxingSkuIdentity.is_active.is_(True),
            LingxingSkuIdentity.mapping_status == "confirmed",
        )
    ).all()
    sku_identities: dict[tuple[str, UUID], list[UUID]] = {}
    for account_ref, product_id, identity_id in identity_rows:
        sku_identities.setdefault((account_ref, product_id), []).append(identity_id)

    resolved_identity_ids = {ids[0] for ids in sku_identities.values() if len(ids) == 1}
    current_by_identity = {
        row.identity_id: row
        for row in session.scalars(
            select(LingxingSkuProductInfoCurrent).where(
                LingxingSkuProductInfoCurrent.identity_id.in_(resolved_identity_ids)
            )
        ).all()
    }
    profile_by_identity = {
        row.identity_id: row
        for row in session.scalars(
            select(SkuBaseProfileCurrent).where(
                SkuBaseProfileCurrent.identity_id.in_(resolved_identity_ids)
            )
        ).all()
    }

    now = datetime.now(UTC)
    effective_rules = ProductManagementRepository(session).list_effective_rules(
        now,
        account_refs,
    )
    result: dict[WfsStandardIdentity, WfsStandardFee] = {}
    for identity in identities:
        account_ref, store_id, _item_id, msku = identity
        listing_skus = listings_by_identity.get(identity, [])
        if len(listing_skus) != 1:
            continue
        product_ids_for_sku = products_by_sku.get(listing_skus[0], [])
        if len(product_ids_for_sku) != 1:
            continue
        matched_identity_ids = sku_identities.get((account_ref, product_ids_for_sku[0]), [])
        if len(matched_identity_ids) != 1:
            continue
        sku_identity_id = matched_identity_ids[0]
        active_rule = effective_rules.get(account_ref)
        rule = ProductManagementService._sku_pricing_rule(active_rule)
        calculation = ProductManagementService._sku_pricing_calculation(
            current_by_identity.get(sku_identity_id),
            profile_by_identity.get(sku_identity_id),
            0,
            rule,
        )
        fee = calculation.wfs_fulfillment_fee_usd
        if calculation.wfs_calc_status != "ok" or fee is None or not fee.is_finite() or fee <= 0:
            continue
        result[identity] = WfsStandardFee(
            source_account_ref=account_ref,
            store_id=store_id,
            msku=msku,
            unit_fee=fee,
            source=(
                "product_management_rule"
                if active_rule is not None
                else "product_management_default_unconfirmed"
            ),
            rule_version=(
                active_rule.version if active_rule is not None else "sku-pricing-defaults-v1"
            ),
            calculation_status=calculation.wfs_calc_status,
            calculated_at=now,
            historical_applicability="current_only",
        )
    return result


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
    identity = (source_account_ref, store_id, item_id, msku)
    return read_product_management_wfs_fees(
        session,
        identities=frozenset({identity}),
    ).get(identity)

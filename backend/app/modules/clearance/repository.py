"""Read-only, scoped Walmart Item-ID facts reused from existing business MARTs."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.data_pages.models import (
    DailySalesItemDayMart,
    ListingManagementCurrentMart,
    WalmartListingInventoryDailyFact,
)

from .evaluator import ProductFacts, SalesWindow

LA = ZoneInfo("America/Los_Angeles")


def la_today() -> date:
    return datetime.now(UTC).astimezone(LA).date()


def find_listing(
    session: Session, account: str, store: str, item: str, *, lock: bool = False
) -> ListingManagementCurrentMart | None:
    q = select(ListingManagementCurrentMart).where(
        ListingManagementCurrentMart.source_account_ref == account,
        ListingManagementCurrentMart.store_id == store,
        ListingManagementCurrentMart.item_id == item,
    )
    if lock:
        q = q.with_for_update()
    return session.scalar(q)


def current_available(session: Session, listing: ListingManagementCurrentMart) -> int | None:
    """Most recently captured authoritative WFS quantity, never unknown=zero."""
    observation = session.scalar(
        select(WalmartListingInventoryDailyFact)
        .where(
            WalmartListingInventoryDailyFact.source_account_ref == listing.source_account_ref,
            WalmartListingInventoryDailyFact.store_id == listing.store_id,
            WalmartListingInventoryDailyFact.item_id == listing.item_id,
        )
        .order_by(
            WalmartListingInventoryDailyFact.captured_at.desc(),
            WalmartListingInventoryDailyFact.snapshot_date_la.desc(),
        )
        .limit(1)
    )
    snapshot_at = observation.captured_at if observation else None
    mart_at = listing.calculated_at
    if snapshot_at and snapshot_at.tzinfo is None:
        snapshot_at = snapshot_at.replace(tzinfo=UTC)
    if mart_at and mart_at.tzinfo is None:
        mart_at = mart_at.replace(tzinfo=UTC)
    if observation is not None and (
        mart_at is None or (snapshot_at is not None and snapshot_at >= mart_at)
    ):
        value = observation.wfs_available_quantity
    else:
        value = listing.wfs_available_quantity
    if value is None or value < 0 or value != value.to_integral_value():
        return None
    return int(value)


def first_stock_date(session: Session, listing: ListingManagementCurrentMart) -> date | None:
    return session.scalar(
        text("""
        SELECT first_wfs_available_date_la FROM listing_wfs_first_stock_la_locked
        WHERE source_account_ref=:account AND store_id=:store AND item_id=:item
    """),
        {"account": listing.source_account_ref, "store": listing.store_id, "item": listing.item_id},
    )


def commission_rule(
    session: Session, listing: ListingManagementCurrentMart, price: Decimal | None, cutoff: date
) -> Decimal | None:
    """Current effective store/item/range rate; no invented 15% default."""
    row = session.execute(
        text("""
        SELECT commission_rate FROM ref_store_commission_rule_versions
        WHERE source_account_ref=:account AND store_id=:store
          AND platform_code='walmart' AND is_active=TRUE
          AND effective_from <= :cutoff AND (effective_to IS NULL OR effective_to > :cutoff)
          AND (rule_scope='store'
            OR (rule_scope='item' AND item_id=:item)
            OR (rule_scope='price_range' AND :price IS NOT NULL
                AND (price_min_amount IS NULL OR :price >= price_min_amount)
                AND (price_max_amount IS NULL OR :price <= price_max_amount)))
        ORDER BY CASE rule_scope WHEN 'item' THEN 0 WHEN 'price_range' THEN 1 ELSE 2 END,
                 priority ASC NULLS LAST, effective_from DESC, rule_version DESC
        LIMIT 1
    """),
        {
            "account": listing.source_account_ref,
            "store": listing.store_id,
            "item": listing.item_id,
            "price": price,
            "cutoff": cutoff,
        },
    ).first()
    if not row:
        return None
    rate = Decimal(str(row[0]))
    return rate if 0 <= rate < 1 else None


def facts_for_listing(
    session: Session, listing: ListingManagementCurrentMart, *, cutoff: date | None = None
) -> ProductFacts:
    cutoff = cutoff or la_today()
    available = current_available(session, listing)
    first = first_stock_date(session, listing)
    days = (cutoff - first).days + 1 if first is not None and first <= cutoff else None
    start = cutoff - timedelta(days=29)
    rows = list(
        session.scalars(
            select(DailySalesItemDayMart)
            .where(
                DailySalesItemDayMart.source_account_ref == listing.source_account_ref,
                DailySalesItemDayMart.store_id == listing.store_id,
                DailySalesItemDayMart.item_id == listing.item_id,
                DailySalesItemDayMart.business_date_la.between(start, cutoff),
            )
            .order_by(DailySalesItemDayMart.business_date_la)
        ).all()
    )
    by_date = defaultdict(list)
    for row in rows:
        by_date[row.business_date_la].append(row)

    windows: dict[int, SalesWindow] = {}
    for n in (7, 14, 30):
        window_start = cutoff - timedelta(days=n - 1)
        if first is not None and first > window_start:
            window_start = first
        expected = max(0, (cutoff - window_start).days + 1)
        daily_groups = [by_date[window_start + timedelta(days=i)] for i in range(expected)]
        complete = expected > 0 and all(daily_groups)
        # Multiple non-null distinct MSKUs can represent separate sales. Ambiguous
        # duplicated or null identities among multiple records cannot be summed.
        for group in daily_groups:
            if len(group) > 1:
                msuks = [str(row.msku or "").strip() for row in group]
                if not all(msuks) or len(set(msuks)) != len(msuks):
                    complete = False
        flat = [row for group in daily_groups for row in group]
        units = (
            sum((row.sales_qty for row in flat), Decimal(0))
            if complete and all(row.sales_qty is not None and row.sales_qty >= 0 for row in flat)
            else None
        )
        revenue = (
            sum((row.sales_amount for row in flat), Decimal(0))
            if complete
            and all(
                row.sales_amount is not None and row.sales_currency_code == "USD" for row in flat
            )
            else None
        )
        ads = (
            sum((row.ad_spend_amount for row in flat), Decimal(0))
            if complete
            and all(
                row.ad_spend_amount is not None and row.ad_spend_currency_code == "USD"
                for row in flat
            )
            else None
        )
        profit = (
            sum((row.gross_profit_amount for row in flat), Decimal(0))
            if complete
            and all(
                row.gross_profit_amount is not None
                and row.gross_profit_currency_code == "USD"
                and row.cost_status == "complete"
                for row in flat
            )
            else None
        )
        returns = (
            sum((row.return_qty for row in flat), Decimal(0))
            if complete and all(row.return_qty is not None for row in flat)
            else None
        )
        active = (
            sum(
                1
                for group in daily_groups
                if group
                and all(row.sales_qty is not None for row in group)
                and sum(row.sales_qty for row in group) > 0
            )
            if complete
            else None
        )
        net = units - returns if units is not None and returns is not None else None
        windows[n] = SalesWindow(
            units=units,
            revenue=revenue,
            ads=ads,
            profit=profit,
            returns=returns,
            observed_days=sum(bool(group) for group in daily_groups),
            effective_days=expected,
            complete=complete,
            active_sales_days=active,
            net_units=net,
        )

    sale_date = session.scalar(
        text("""
        SELECT MAX(business_date_la) FROM mart_daily_sales_item_day
        WHERE source_account_ref=:account AND store_id=:store AND item_id=:item
          AND business_date_la<=:cutoff AND sales_qty>0
    """),
        {
            "account": listing.source_account_ref,
            "store": listing.store_id,
            "item": listing.item_id,
            "cutoff": cutoff,
        },
    )
    last_sale_days = (cutoff - sale_date).days if sale_date is not None else None

    # Unit cost from verified USD sales cost facts only; never convert CNY by
    # assuming an FX rate or use a blanket commission percentage.
    unit_cost = None
    fulfillment_fee = None
    for row in reversed(rows):
        if (
            unit_cost is None
            and row.cost_quantity
            and row.cost_quantity > 0
            and row.purchase_cost_total_usd is not None
            and row.first_leg_cost_total_usd is not None
            and row.cost_status == "complete"
        ):
            unit_cost = (
                row.purchase_cost_total_usd + row.first_leg_cost_total_usd
            ) / row.cost_quantity
        if (
            fulfillment_fee is None
            and row.wfs_fee_unit_amount is not None
            and row.wfs_fee_currency_code == "USD"
        ):
            fulfillment_fee = row.wfs_fee_unit_amount
        if unit_cost is not None and fulfillment_fee is not None:
            break
    price = listing.sale_price_amount if listing.sale_price_currency_code == "USD" else None
    if price is None and listing.strike_price_currency_code == "USD":
        price = listing.strike_price_amount
    commission = commission_rule(session, listing, price, cutoff)
    buybox = None
    if isinstance(listing.buybox_status, str):
        label = listing.buybox_status.strip().lower()
        if label in {"yes", "true", "1", "owned", "winning", "active"}:
            buybox = True
        elif label in {"no", "false", "0", "lost", "not_winning"}:
            buybox = False
    return ProductFacts(
        source_account_ref=listing.source_account_ref,
        store_id=listing.store_id,
        item_id=listing.item_id,
        available=available,
        first_wfs_days=days,
        windows=windows,
        rating=listing.average_rating,
        review_count=listing.review_count,
        buybox=buybox,
        inbound_qty=int(listing.inbound_quantity)
        if listing.inbound_quantity is not None
        and listing.inbound_quantity >= 0
        and listing.inbound_quantity == listing.inbound_quantity.to_integral_value()
        else None,
        last_sale_days=last_sale_days,
        unit_inventory_cost_usd=unit_cost,
        fulfillment_fee_usd=fulfillment_fee,
        commission_rate=commission,
        current_price_usd=price,
    )

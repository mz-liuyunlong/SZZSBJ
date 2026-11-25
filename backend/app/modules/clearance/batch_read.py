"""Bounded exact-identity reads for clearance presentation, never workflow writes."""

# ruff: noqa: E501
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select, text, tuple_
from sqlalchemy.orm import Session

from app.modules.data_pages.models import (
    ListingManagementCurrentMart,
    WalmartListingInventoryDailyFact,
)

from .read_only_listings import (
    _owner_names_for_listings,
    _page_first_wfs_dates,
    _product_data_for_listings,
    read_business_snapshot,
)
from .repository import la_today

logger = logging.getLogger(__name__)

DAILY_FIELDS = (
    "source_account_ref",
    "store_id",
    "item_id",
    "business_date_la",
    "msku",
    "sales_qty",
    "sales_amount",
    "sales_currency_code",
    "gross_profit_amount",
    "gross_profit_currency_code",
    "cost_status",
    "ad_spend_amount",
    "ad_spend_currency_code",
    "sem_ad_spend_amount",
    "return_qty",
    "cost_quantity",
    "purchase_cost_total_usd",
    "first_leg_cost_total_usd",
    "wfs_fee_unit_amount",
    "wfs_fee_currency_code",
    "storage_fee_unit_amount",
    "storage_fee_currency_code",
    "commission_rate",
)


def identity(row):
    return (row.source_account_ref, row.store_id, row.item_id)


def application_identity(row):
    account, store, item = (str(row[k]) for k in ("source_account_ref", "store_id", "item_id"))
    parts = item.split("::")
    if len(parts) == 3 and parts[:2] == [account, store] and parts[2].isdigit():
        item = parts[2]
    return account, store, item


def find_listings(session: Session, keys, accounts: frozenset[str]):
    keys = sorted({key for key in keys if key[0] in accounts and all(key)})
    if not keys:
        return {}
    model = ListingManagementCurrentMart
    result = {}
    ambiguous = set()
    for start in range(0, len(keys), 150):
        rows = session.scalars(
            select(model).where(
                tuple_(
                    model.source_account_ref,
                    model.store_id,
                    model.item_id,
                ).in_(keys[start : start + 150])
            )
        ).all()
        for row in rows:
            key = identity(row)
            if key in result:
                ambiguous.add(key)
            result[key] = row
    for key in ambiguous:
        result.pop(key, None)
    return result


def read_daily_rows(session: Session, keys, cutoff):
    """One parameterized exact-identity read; no repeated 150-key round trips."""
    keys = sorted(set(keys))
    result = defaultdict(list)
    if not keys:
        return result
    # Parallel arrays preserve the account/store/Item triple; never use a
    # Cartesian product of independent IN filters. Fixed column allowlist only.
    columns = ", ".join("m." + name for name in DAILY_FIELDS)
    if len(keys) >= 150:
        # Keep exact Item/date index probes available for the full risk population.
        # OFFSET 0 is a PostgreSQL optimization fence for the correlated subquery;
        # no LIMIT, no deduplication, and no change to the actual row projection.
        statement = text(f"""
            SELECT {columns}
            FROM unnest(CAST(:accounts AS text[]), CAST(:stores AS text[]),
                        CAST(:items AS text[])) AS k(account_ref, store_id, item_id)
            CROSS JOIN LATERAL (
                SELECT {columns} FROM mart_daily_sales_item_day AS m
                WHERE m.item_id = k.item_id AND m.store_id = k.store_id
                  AND m.source_account_ref = k.account_ref
                  AND m.business_date_la BETWEEN :start_day AND :end_day
                OFFSET 0
            ) AS m
        """)
    else:
        statement = text(f"""
            SELECT {columns}
            FROM mart_daily_sales_item_day AS m
            JOIN unnest(CAST(:accounts AS text[]), CAST(:stores AS text[]),
                        CAST(:items AS text[])) AS k(account_ref, store_id, item_id)
              ON m.source_account_ref = k.account_ref
             AND m.store_id = k.store_id AND m.item_id = k.item_id
            WHERE m.business_date_la BETWEEN :start_day AND :end_day
        """)
    rows = session.execute(
        statement,
        {
            "accounts": [a for a, _, _ in keys],
            "stores": [s for _, s, _ in keys],
            "items": [i for _, _, i in keys],
            "start_day": cutoff - timedelta(days=29),
            "end_day": cutoff,
        },
    ).all()
    for row in rows:
        result[identity(row)].append(row)
    return result


def _available(listing, observation):
    """Same snapshot-vs-MART freshness and whole-unit checks as current_available."""
    at = observation.captured_at if observation is not None else None
    mart_at = listing.calculated_at
    if at and at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    if mart_at and mart_at.tzinfo is None:
        mart_at = mart_at.replace(tzinfo=UTC)
    value = (
        observation.wfs_available_quantity
        if observation is not None and (mart_at is None or (at is not None and at >= mart_at))
        else listing.wfs_available_quantity
    )
    return (
        int(value)
        if value is not None and value >= 0 and value == value.to_integral_value()
        else None
    )


def current_available_many(session: Session, listings):
    model = WalmartListingInventoryDailyFact
    keys = sorted({identity(row) for row in listings})
    observations = {}
    key_cols = (model.source_account_ref, model.store_id, model.item_id)
    for start in range(0, len(keys), 150):
        rows = session.execute(
            select(
                *key_cols,
                model.captured_at,
                model.wfs_available_quantity,
            )
            .where(tuple_(*key_cols).in_(keys[start : start + 150]))
            .distinct(*key_cols)
            .order_by(*key_cols, model.captured_at.desc(), model.snapshot_date_la.desc())
        ).all()
        observations.update({identity(row): row for row in rows})
    return {identity(row): _available(row, observations.get(identity(row))) for row in listings}


def _nonblank_name(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def management_product_name(product_name, local_name, platform_title, source_name, saved_name):
    """Verified business names only; never use the marketing title as fallback."""
    title = _nonblank_name(platform_title)
    for value in (product_name, source_name):
        name = _nonblank_name(value)
        if name:
            return name
    name = _nonblank_name(local_name)
    if name and name != title:
        return name
    return _nonblank_name(saved_name)


def _source_product_names(session, listings):
    """Same account/SKU source as Product Management, without ambiguous names."""
    from sqlalchemy import text

    keys = {(r.source_account_ref, r.local_sku) for r in listings if r.local_sku}
    if (
        not keys
        or session.scalar(
            text("SELECT to_regclass('public.dwd_lingxing_sku_product_info_current')")
        )
        is None
    ):
        return {}
    rows = session.execute(
        text("""
        SELECT source_account_ref, lingxing_sku_code,
               max(nullif(btrim(product_name), '')) AS product_name
        FROM dwd_lingxing_sku_product_info_current
        WHERE source_account_ref = ANY(:accounts)
          AND lingxing_sku_code = ANY(:skus)
        GROUP BY source_account_ref, lingxing_sku_code
        HAVING count(distinct nullif(btrim(product_name), '')) = 1
    """),
        {"accounts": sorted({a for a, _ in keys}), "skus": sorted({sku for _, sku in keys})},
    ).all()
    return {(a, sku): name for a, sku, name in rows if (a, sku) in keys and name}


def _plan_sales_dates(row, today):
    """Match the existing planned-start display: submission LA date + one day."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    la = ZoneInfo("America/Los_Angeles")

    def as_la_day(value):
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                return None
        if not isinstance(value, datetime) or value.tzinfo is None:
            return None
        return value.astimezone(la).date()

    submitted = as_la_day(row.get("submitted_at"))
    if submitted is None:
        return None, None
    start = submitted + timedelta(days=1)
    if row.get("status") == "running":
        end = today
    elif row.get("status") == "done":
        finished = as_la_day(row.get("finished_at"))
        end = min(today, finished) if finished is not None else None
    else:
        end = None
    return start, end if end is not None and end >= start else None


def read_plan_sales(session: Session, items, accounts, today):
    """Aggregate the observed MART rows per authorized application/date interval.

    A missing interval is unknown, not a synthetic zero. Distinct tasks for the
    same item keep their own windows. Duplicate/ambiguous MSKUs invalidate both
    metrics; non-USD or missing amounts invalidate revenue only. No writes.
    """
    result = {}
    requested = []
    for row in items:
        account, store, item = application_identity(row)
        app_id = str(row["id"])
        start, end = _plan_sales_dates(row, today)
        result[app_id] = {
            "plan_start_date_la": start.isoformat() if start is not None else None,
            "plan_sales_through_la": end.isoformat() if end is not None else None,
            "plan_sold_qty": None,
            "plan_sales_amount_usd": None,
        }
        if account in accounts and all((account, store, item)) and end is not None:
            requested.append((app_id, account, store, item, start, end))
    if not requested:
        return result
    rows = (
        session.execute(
            text("""
        WITH requested AS (
            SELECT * FROM unnest(
                CAST(:application_ids AS text[]), CAST(:accounts AS text[]),
                CAST(:stores AS text[]), CAST(:items AS text[]),
                CAST(:starts AS date[]), CAST(:ends AS date[])
            ) AS k(application_id, account_ref, store_id, item_id, start_day, end_day)
        ), daily AS (
            SELECT k.application_id, m.business_date_la,
                   COUNT(*) AS records,
                   COUNT(DISTINCT NULLIF(BTRIM(m.msku), '')) AS distinct_mskus,
                   BOOL_AND(m.sales_qty IS NOT NULL AND m.sales_qty >= 0) AS qty_valid,
                   BOOL_AND(m.sales_amount IS NOT NULL
                       AND m.sales_currency_code IS NOT DISTINCT FROM 'USD') AS amount_valid,
                   SUM(m.sales_qty) AS sold, SUM(m.sales_amount) AS amount
            FROM requested AS k
            JOIN mart_daily_sales_item_day AS m
              ON m.source_account_ref = k.account_ref AND m.store_id = k.store_id
             AND m.item_id = k.item_id
             AND m.business_date_la BETWEEN k.start_day AND k.end_day
            GROUP BY k.application_id, m.business_date_la
        )
        SELECT application_id,
               CASE WHEN BOOL_AND(qty_valid AND (records = 1 OR records = distinct_mskus))
                    THEN SUM(sold) END AS sold,
               CASE WHEN BOOL_AND(amount_valid AND (records = 1 OR records = distinct_mskus))
                    THEN SUM(amount) END AS amount
        FROM daily GROUP BY application_id
    """),
            {
                name: [row[index] for row in requested]
                for index, name in enumerate(
                    ("application_ids", "accounts", "stores", "items", "starts", "ends")
                )
            },
        )
        .mappings()
        .all()
    )
    for row in rows:
        entry = result[row["application_id"]]
        entry["plan_sold_qty"] = float(row["sold"]) if row["sold"] is not None else None
        entry["plan_sales_amount_usd"] = float(row["amount"]) if row["amount"] is not None else None
    return result


def enrich_application_rows(session: Session, items, accounts, rules, version):
    """One batched read per source; missing history keeps the persisted snapshot."""
    plan_sales = read_plan_sales(session, items, accounts, la_today())
    items = [{**row, **plan_sales[str(row["id"])]} for row in items]
    by_key = find_listings(session, (application_identity(row) for row in items), accounts)
    listings = list(by_key.values())
    if not listings:
        return items
    cutoff = la_today() - timedelta(days=1)
    daily = read_daily_rows(session, by_key, cutoff)
    first = _page_first_wfs_dates(session, listings)
    products = _product_data_for_listings(session, listings)
    names = _source_product_names(
        session,
        [
            r
            for r in listings
            if not _nonblank_name(
                products.get((r.store_name, r.msku, r.local_sku), {}).get("product_name")
            )
        ],
    )
    owners = _owner_names_for_listings(session, listings)
    available = current_available_many(session, listings)
    live = {}
    for key, listing in by_key.items():
        # All inputs are already batched; only malformed individual numeric
        # facts may degrade to the saved application snapshot, never SQL errors.
        try:
            live[key] = read_business_snapshot(
                session,
                listing,
                page_daily_rows=daily.get(key, []),
                page_available=available.get(key),
                availability_batched=True,
                first_date_for_page=first.get(key),
                first_dates_batched=True,
                product_data=products,
                rules=rules,
                rule_version=version,
                include_evidence=False,
            )
        except (ArithmeticError, ValueError, TypeError) as exc:
            logger.warning("clearance_application_live_fact_invalid type=%s", type(exc).__name__)
    result = []
    for row in items:
        key = application_identity(row)
        snap = live.get(key)
        data = {**row, "item_id": key[2]}
        listing = by_key.get(key)
        if listing is not None:
            product = products.get((listing.store_name, listing.msku, listing.local_sku), {})
            name = management_product_name(
                product.get("product_name"),
                listing.local_name,
                listing.title,
                names.get((key[0], listing.local_sku)),
                row.get("display_product_name"),
            )
            if name:
                data["display_product_name"] = name
            owner = owners.get((key[0], listing.local_sku))
            if owner:
                data["display_owner_name"] = owner
        if snap is not None:
            metrics = snap["metrics"]
            stock = snap.get("available")
            unit = metrics.get("inventory_unit_cost_usd")
            capital = metrics.get("capital_purchase_first_leg_usd")
            qty = (
                row.get("approved_qty")
                if row.get("approved_qty") is not None
                else row.get("requested_qty")
            )
            data["current_risk"] = snap["risk"]
            if stock is not None and stock >= 0:
                data["wfs_available_quantity"] = stock
            if metrics.get("listing_days") is not None:
                data["listing_days"] = metrics["listing_days"]
            if capital is not None and capital >= 0:
                data["inventory_cost_usd"] = capital
            if unit is not None and unit >= 0 and qty is not None:
                count = Decimal(str(qty))
                if count.is_finite() and count > 0 and count == count.to_integral_value():
                    data["v44_current_target_cost_usd"] = float(
                        (Decimal(str(unit)) * count).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                    )
        result.append(data)
    return result

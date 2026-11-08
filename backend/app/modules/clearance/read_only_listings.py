"""Read-only WFS Listing preview without the optional clearance risk tables.

Uses the same existing business marts as Listing and sales pages. There are no
writes and no invented inventory, cost, exchange rate, or clearance risk values.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal

from sqlalchemy import select, text, tuple_
from sqlalchemy.orm import Session

from app.modules.data_pages.models import DailySalesItemDayMart, ListingManagementCurrentMart
from app.modules.products.models import Product, ProductPlatformListing
from .repository import current_available, la_today
from .evaluator import ProductFacts, SalesWindow, evaluate
from .rules import ClearanceRules


_OPTIONAL_TABLES = (
    "public.biz_clearance_rule_versions",
    "public.biz_clearance_risk_current",
)


def risk_read_model_ready(session: Session) -> bool:
    """Do not catch unrelated database, permission or SQL errors."""
    return all(
        session.scalar(text("SELECT to_regclass(:relation)"), {"relation": table}) is not None
        for table in _OPTIONAL_TABLES
    )


def _number(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _window_stats(rows_by_day: dict[date, list], cutoff: date, days: int, first_date: date | None = None, allow_partial: bool = False) -> dict:
    """Only complete observed windows yield revenue/profit; missing != zero."""
    # Verify each effective LA business day, starting from genuine first WFS stock
    # if that source exists. Missing daily rows are unknown, never zero sales.
    start = cutoff - timedelta(days=days - 1)
    if first_date is not None and first_date > start:
        start = first_date
    effective_days = max(0, (cutoff - start).days + 1)
    daily = [rows_by_day.get(start + timedelta(days=n), []) for n in range(effective_days)]
    complete = bool(daily) and (any(daily) if allow_partial else all(daily))
    if complete:
        for group in daily:
            if len(group) > 1:
                msuks = [str(row.msku or "").strip() for row in group]
                if not all(msuks) or len(set(msuks)) != len(msuks):
                    complete = False
                    break
    records = [item for group in daily for item in group]

    def total(field: str, currency_field: str | None = None, cost_required: bool = False) -> Decimal | None:
        if not complete:
            return None
        result = Decimal(0)
        for row in records:
            value = getattr(row, field)
            if value is None or (currency_field is not None and getattr(row, currency_field) != "USD"):
                return None
            if cost_required and row.cost_status != "complete":
                return None
            result += value
        return result

    revenue = total("sales_amount", "sales_currency_code")
    profit = total("gross_profit_amount", "gross_profit_currency_code", cost_required=True)
    ads = total("ad_spend_amount", "ad_spend_currency_code")
    sem = [getattr(row, "sem_ad_spend_amount", Decimal(0)) for row in records]
    sem_total = sum(sem, Decimal(0)) if all(x is not None for x in sem) else None
    if ads is not None and sem_total is not None:
        ads += sem_total
    elif allow_partial and sem_total is not None and sem_total > 0:
        ads = sem_total
    returns = total("return_qty")
    units = total("sales_qty")
    active_days = (sum(
        1 for group in daily if sum(row.sales_qty for row in group) > 0
    ) if complete and all(row.sales_qty is not None and row.sales_qty >= 0 for row in records) else None)
    return {
        "complete": complete,
        "effective_days": effective_days,
        "observed_days": sum(bool(group) for group in daily),
        "units": units,
        "revenue": revenue,
        "ads": ads,
        "profit": profit,
        "returns": returns,
        "active_sales_days": active_days,
        "ad_ratio": ads / revenue * 100 if ads is not None and revenue is not None and revenue > 0 else None,
        "margin": profit / revenue * 100 if profit is not None and revenue is not None and revenue > 0 else None,
    }


def _first_wfs_date(session: Session, listing: ListingManagementCurrentMart) -> date | None:
    """Use the existing verified first-stock source if deployed; never infer from listing age."""
    relation = session.scalar(text("SELECT to_regclass(:relation)"), {
        "relation": "public.listing_wfs_first_stock_la_locked"
    })
    if relation is None:
        return None
    value = session.scalar(text("""
        SELECT first_wfs_available_date_la FROM public.listing_wfs_first_stock_la_locked
        WHERE source_account_ref=:account AND store_id=:store AND item_id=:item
    """), {"account": listing.source_account_ref, "store": listing.store_id,
           "item": listing.item_id})
    return value if isinstance(value, date) and not isinstance(value, datetime) else None



def _page_first_wfs_dates(session: Session, listings: list[ListingManagementCurrentMart]) -> dict:
    keys = {(x.source_account_ref, x.store_id, x.item_id) for x in listings}
    if not keys or session.scalar(text("SELECT to_regclass('public.listing_wfs_first_stock_la_locked')")) is None:
        return {}
    rows = session.execute(text("""
        SELECT source_account_ref, store_id, item_id, first_wfs_available_date_la
        FROM listing_wfs_first_stock_la_locked
        WHERE source_account_ref = ANY(:accounts) AND store_id = ANY(:stores)
          AND item_id = ANY(:items)
    """), {"accounts": sorted({a for a,_,_ in keys}),
             "stores": sorted({s for _,s,_ in keys}),
             "items": sorted({i for _,_,i in keys})}).all()
    return {(a,s,i):day for a,s,i,day in rows
            if (a,s,i) in keys and isinstance(day,date) and not isinstance(day,datetime)}

def _assess_read_only(listing: ListingManagementCurrentMart, available: int | None,
                      windows: dict[int, dict], first_days: int | None,
                      unit_cost: Decimal | None) -> tuple[str, list[str], list[dict], list[str], dict]:
    """Run the original pure rule engine without reading or writing clearance state tables."""
    rules = ClearanceRules()  # Code defaults, NOT an imaginary persisted rule version.
    # No reliable new/old WFS inventory lot identification: old-stock rules
    # are retired even if an older saved configuration enabled them.
    retired_flags = {name: False for name in
                     ("enableAged", "enableAverageAge", "enableAgedRatio", "enableNearFee")
                     if hasattr(rules, name)}
    if retired_flags:
        from dataclasses import is_dataclass, replace
        if is_dataclass(rules):
            rules = replace(rules, **retired_flags)
        elif hasattr(rules, "model_copy"):
            rules = rules.model_copy(update=retired_flags)
        else:
            for name, setting in retired_flags.items():
                setattr(rules, name, setting)

    factual_windows = {days: SalesWindow(
        units=values["units"], revenue=values["revenue"], ads=values["ads"],
        profit=values["profit"], returns=values["returns"],
        complete=values["complete"], observed_days=values["observed_days"],
        effective_days=values["effective_days"],
        active_sales_days=values["active_sales_days"],
        net_units=(values["units"]-values["returns"] if values["units"] is not None and values["returns"] is not None else None),
    ) for days, values in windows.items()}
    inbound = getattr(listing, "inbound_quantity", None)
    inbound_qty = (int(inbound) if inbound is not None and inbound >= 0 and
                   inbound == inbound.to_integral_value() else None)
    result = evaluate(ProductFacts(
        source_account_ref=listing.source_account_ref,
        store_id=listing.store_id, item_id=listing.item_id,
        available=available, first_wfs_days=first_days,
        windows=factual_windows, rating=listing.average_rating,
        review_count=listing.review_count, inbound_qty=inbound_qty,
        unit_inventory_cost_usd=unit_cost,
        current_price_usd=(listing.sale_price_amount if listing.sale_price_currency_code == "USD" else None),
    ), rules)
    level, reasons, gaps = result.level, list(result.reasons), list(result.gaps)
    # Without first WFS stock evidence the 60-day new-product protection cannot
    # be verified. Do not mislabel an ordinary medium risk as confirmed.
    if first_days is None:
        if level == "medium" and rules.enableNewProductProtection:
            level = "unknown"
            reasons = ["首次WFS有货日期缺失，无法确认新品保护", *reasons]
        elif level == "low" and rules.enableZero and factual_windows[30].complete and factual_windows[30].units == 0:
            level = "unknown"
            reasons = ["经核实销量为零，但缺少首次WFS有货日期，无法判断零销量风险", *reasons]
        gaps = sorted(set([*gaps, "first_wfs_available_date_la"]))
    return level, reasons, result.signals, gaps, result.metrics


def _listing_age_days(listing: ListingManagementCurrentMart, today: date) -> int | None:
    """Days since the Listing start time, not WFS inbound inventory aging."""
    start = getattr(listing, "listing_start_at_utc", None)
    if start is None or not isinstance(start, datetime) or start.tzinfo is None:
        return None
    start_la = start.astimezone(ZoneInfo("America/Los_Angeles")).date()
    return (today - start_la).days if start_la <= today else None


def _safe_per_unit(total: Decimal | None, quantity: Decimal | None) -> Decimal | None:
    return total / quantity if total is not None and quantity is not None and quantity > 0 else None


def _owner_names_for_listings(
    session: Session, listings: list[ListingManagementCurrentMart],
) -> dict[tuple[str, str], str]:
    """Same owner source/key as Listing Management, page-batched and account scoped.

    It is important not to use Listing.owner_ref alone: Listing Management joins
    dwd_lingxing_sku_product_info_current by (account, local SKU) to get owner_name.
    """
    keys = {
        (row.source_account_ref, row.local_sku)
        for row in listings if row.source_account_ref and row.local_sku
    }
    if not keys:
        return {}
    if session.scalar(text("SELECT to_regclass(:name)"), {
        "name": "public.dwd_lingxing_sku_product_info_current",
    }) is None:
        return {}
    rows = session.execute(text("""
        SELECT source_account_ref, lingxing_sku_code,
               MAX(NULLIF(BTRIM(owner_name), '')) AS owner_name
        FROM dwd_lingxing_sku_product_info_current
        WHERE source_account_ref = ANY(:accounts)
          AND lingxing_sku_code = ANY(:skus)
        GROUP BY source_account_ref, lingxing_sku_code
    """), {
        "accounts": sorted({account for account, _ in keys}),
        "skus": sorted({sku for _, sku in keys}),
    }).all()
    return {
        (account, sku): name for account, sku, name in rows
        if (account, sku) in keys and name
    }


def _product_data_for_listings(session: Session, listings: list[ListingManagementCurrentMart]) -> dict:
    """Read only, exact (store name, MSKU, local SKU) product mapping; no guess joins."""
    candidates = [x for x in listings if x.store_name and x.msku and x.local_sku]
    if not candidates:
        return {}
    eligible = {(x.store_name, x.msku, x.local_sku) for x in candidates}
    rows = session.execute(select(
        ProductPlatformListing.store_name, ProductPlatformListing.msku, Product.sku,
        Product.product_name, Product.purchase_price, Product.currency_code, ProductPlatformListing.wfs_fee,
        ProductPlatformListing.currency_code,
    ).join(Product, Product.id == ProductPlatformListing.product_id).where(
        ProductPlatformListing.platform == "walmart",
        ProductPlatformListing.deleted_at.is_(None), Product.deleted_at.is_(None),
        ProductPlatformListing.store_name.in_([x[0] for x in eligible]),
        ProductPlatformListing.msku.in_([x[1] for x in eligible]),
        Product.sku.in_([x[2] for x in eligible]),
    )).all()
    out = {}
    duplicate = set()
    for store, msku, sku, product_name, purchase, currency, fee, fee_currency in rows:
        key = (store, msku, sku)
        if key not in eligible:
            continue
        if key in out:
            duplicate.add(key)
            continue
        out[key] = {
            "product_name": product_name.strip() if isinstance(product_name, str) and product_name.strip() else None,
            "purchase": purchase if currency == "USD" else None,
            "wfs_fee": fee if fee_currency == "USD" else None,
            "purchase_currency": currency,
        }
    for key in duplicate:
        out.pop(key, None)

    # Product Management names are linked by the unique local SKU.
    # Store-specific WFS fees retain their stricter original mapping.
    if isinstance(session, Session):
        sku_rows = session.execute(select(
            Product.sku, Product.product_name,
            Product.purchase_price, Product.currency_code,
        ).where(
            Product.sku.in_({x.local_sku for x in listings if x.local_sku}),
            Product.deleted_at.is_(None),
        )).all()

        by_sku = {
            sku: (name, price, currency)
            for sku, name, price, currency in sku_rows
        }
        for listing in listings:
            found = by_sku.get(listing.local_sku)
            if found is None:
                continue
            name, price, currency = found
            key = (listing.store_name, listing.msku, listing.local_sku)
            fields = out.setdefault(key, {})
            if not fields.get("product_name") and isinstance(name, str) and name.strip():
                fields["product_name"] = name.strip()
            if fields.get("purchase") is None and currency == "USD":
                fields["purchase"] = price
            if "purchase_currency" not in fields:
                fields["purchase_currency"] = currency

    return out


def _commission_for_listings(session: Session, listings: list[ListingManagementCurrentMart],
                             cutoff: date) -> dict:
    """Active store rule at the LA cut-off; no global rate assumption."""
    accounts = sorted({x.source_account_ref for x in listings})
    if not accounts:
        return {}
    # Existing business rules may be absent in a partial local DB.
    if session.scalar(text("SELECT to_regclass(:name)"), {
        "name": "public.ref_store_commission_rule_versions"}) is None:
        return {}
    result = session.execute(text("""
        SELECT DISTINCT ON (source_account_ref, platform_code, store_id)
               source_account_ref, platform_code, store_id, commission_rate
        FROM ref_store_commission_rule_versions
        WHERE source_account_ref = ANY(:accounts) AND is_active = true
          AND effective_from <= :cutoff
          AND (effective_to IS NULL OR effective_to > :cutoff)
        ORDER BY source_account_ref, platform_code, store_id,
                 effective_from DESC, approved_at DESC
    """), {"accounts": accounts, "cutoff": cutoff}).all()
    return {(a, p, store): rate for a, p, store, rate in result}


def read_business_snapshot(session: Session, listing: ListingManagementCurrentMart,
                           *, page_daily_rows: list | None = None,
                           page_available: int | None = None,
                           first_wfs_exists: bool | None = None,
                           product_data: dict | None = None,
                           store_commissions: dict | None = None,
                           first_date_for_page: date | None = None,
                           first_dates_batched: bool = False,
                           page_cost: object | None = None) -> dict:
    """Real Item-ID facts, all read-only. Optional batch inputs avoid per-row queries."""
    available = page_available if page_available is not None else current_available(session, listing)
    cutoff = la_today() - timedelta(days=1)
    first = (first_date_for_page if first_dates_batched else
             (None if first_wfs_exists is False else _first_wfs_date(session, listing)))
    first_days = ((cutoff - first).days + 1 if first is not None and first <= cutoff else None)
    rows = (page_daily_rows if page_daily_rows is not None else
            session.scalars(select(DailySalesItemDayMart).where(
                DailySalesItemDayMart.source_account_ref == listing.source_account_ref,
                DailySalesItemDayMart.store_id == listing.store_id,
                DailySalesItemDayMart.item_id == listing.item_id,
                DailySalesItemDayMart.business_date_la.between(cutoff - timedelta(days=29), cutoff),
            )).all())
    by_day: dict[date, list] = defaultdict(list)
    for row in rows:
        by_day[row.business_date_la].append(row)
    w = {days: _window_stats(by_day, cutoff, days, first if first_days is not None else None) for days in (7, 14, 30)}
    display = {days: _window_stats(by_day, cutoff, days, allow_partial=True) for days in (7, 14, 30)}

    # Product Management is the master for purchase/WFS fees. Costed daily
    # facts are a fallback when USD conversion was already verified there.
    lookup_key = (listing.store_name, listing.msku, listing.local_sku)
    product = ((product_data if product_data is not None else
                (_product_data_for_listings(session, [listing]) if isinstance(session, Session) else {}))
               .get(lookup_key, {}))
    purchase = product.get("purchase")
    first_leg = None
    wfs_fee = product.get("wfs_fee")
    storage_allocated = None
    daily_storage = None
    # Product Management pricing is independent of sales history.
    if page_cost is not None:
        fx = page_cost.exchange_rate
        if fx is not None and fx > 0:
            if page_cost.purchase_cost_unit_cny is not None:
                purchase = page_cost.purchase_cost_unit_cny / fx
            if page_cost.first_leg_cost_unit_cny is not None:
                first_leg = page_cost.first_leg_cost_unit_cny / fx
        if page_cost.wfs_fee_unit_usd is not None:
            wfs_fee = page_cost.wfs_fee_unit_usd
        daily_storage = page_cost.storage_fee_unit_usd
    commission_rate = ((store_commissions or {}).get((listing.source_account_ref,
                       getattr(listing, "platform_code", None), listing.store_id)))
    for cost_row in sorted(rows, key=lambda row: row.business_date_la, reverse=True):
        if purchase is None:
            purchase = _safe_per_unit(cost_row.purchase_cost_total_usd, cost_row.cost_quantity)
        if first_leg is None:
            first_leg = _safe_per_unit(cost_row.first_leg_cost_total_usd, cost_row.cost_quantity)
        if wfs_fee is None and getattr(cost_row, "wfs_fee_currency_code", None) == "USD":
            wfs_fee = getattr(cost_row, "wfs_fee_unit_amount", None)
        if storage_allocated is None and getattr(cost_row, "storage_fee_currency_code", None) == "USD":
            storage_allocated = getattr(cost_row, "storage_fee_unit_amount", None)
        if commission_rate is None:
            commission_rate = getattr(cost_row, "commission_rate", None)
    if wfs_fee is None and getattr(listing, "wfs_fee_currency_code", None) == "USD":
        wfs_fee = getattr(listing, "wfs_fee_amount", None)
    unit_cost = purchase + first_leg if purchase is not None and first_leg is not None else None
    # Allocated storage is not proof of a single-day storage rate. Do not claim
    # a full-sale cost without the requested verified daily rate.
    price = listing.sale_price_amount if listing.sale_price_currency_code == "USD" else None
    commission_unit = (price * commission_rate if price is not None and
                       commission_rate is not None and 0 <= commission_rate < 1 else None)
    known_sale_unit_ex_storage = (
        unit_cost + wfs_fee + commission_unit
        if unit_cost is not None and wfs_fee is not None and commission_unit is not None
        else None
    )
    full_sale_unit_cost = (known_sale_unit_ex_storage + daily_storage
                           if known_sale_unit_ex_storage is not None and daily_storage is not None
                           else None)
    level, reasons, signals, gaps, assessed = _assess_read_only(
        listing, available, w, first_days, unit_cost,
    )
    display_sellout = assessed["sellout_days"]
    sellout_source = "verified_daily_sales" if display_sellout is not None else None
    if display_sellout is None and available is not None and listing.sales_30d is not None and listing.sales_30d > 0:
        from decimal import ROUND_CEILING
        display_sellout = int((Decimal(available) * 30 / listing.sales_30d).to_integral_value(rounding=ROUND_CEILING))
        sellout_source = "listing_30d_estimate_only"
    if display_sellout is None and available is not None and listing.sales_30d == 0:
        sellout_source = "listing_30d_zero_sales"
    # Listing MART sales are informational; evaluator only uses verified daily
    # windows. No inference that a missing zero-sales day means zero orders.
    metrics = {
        "wfs_available": available,
        "listing_days": _listing_age_days(listing, la_today()),
        "first_wfs_days": first_days,
        "sellout_days": display_sellout,
        "sellout_source": sellout_source,
        "sellout_is_infinite": sellout_source == "listing_30d_zero_sales",
        "sales_7d": _number(listing.sales_7d),
        "sales_14d": _number(listing.sales_14d),
        "sales_30d": _number(listing.sales_30d),
        **{f"revenue_{days}d_usd": _number(display[days]["revenue"]) for days in (7,14,30)},
        **{f"ad_spend_{days}d_usd": _number(display[days]["ads"]) for days in (7,14,30)},
        **{f"profit_{days}d_usd": _number(display[days]["profit"]) for days in (7,14,30)},
        **{f"margin_{days}d_percent": _number(display[days]["margin"]) for days in (7,14,30)},
        **{f"ad_ratio_{days}d_percent": _number(display[days]["ad_ratio"]) for days in (7,14,30)},
        "return_rate_30d_percent": (
            _number(display[30]["returns"] / display[30]["units"] * 100)
            if display[30]["returns"] is not None and display[30]["units"] is not None and display[30]["units"] > 0
            else None
        ),
        "returns_30d": _number(display[30]["returns"]),
        **{f"observed_days_{n}d": display[n]["observed_days"] for n in (7,14,30)},
        **{f"incomplete_{n}d": not w[n]["complete"] for n in (7,14,30)},
        "purchase_unit_cost_usd": _number(purchase),
        "first_leg_unit_cost_usd": _number(first_leg),
        "wfs_fee_unit_usd": _number(wfs_fee),
        "storage_fee_allocated_unit_usd": _number(storage_allocated),
        "store_commission_rate": _number(commission_rate),
        "commission_unit_usd": _number(commission_unit),
        "full_sale_unit_cost_usd": _number(full_sale_unit_cost),
        "known_sale_unit_cost_ex_storage_usd": _number(known_sale_unit_ex_storage),
        "daily_storage_unit_fee_usd": _number(daily_storage),
        "inventory_unit_cost_usd": _number(unit_cost),
        "capital_purchase_first_leg_usd": _number(unit_cost * available) if unit_cost is not None and available is not None else None,
        "capital_at_cost_usd": _number(full_sale_unit_cost * available) if full_sale_unit_cost is not None and available is not None else None,
        **{f"complete_{n}d_window": bool(w[n]["complete"]) for n in (7,14,30)},
        "rating": _number(listing.average_rating),
        "review_count": listing.review_count,
        "suggested_clearance_qty": assessed["suggested_clearance_qty"],
        "suggested_floor_price_usd": assessed["suggested_floor_price_usd"],
    }
    # Direct single-Item detail has no batched page; resolve the same owner
    # name used by Listing Management. The 50-row path uses one batched query.
    owner_name = None
    if page_daily_rows is None and isinstance(session, Session):
        owner_name = _owner_names_for_listings(session, [listing]).get(
            (listing.source_account_ref, listing.local_sku))
    snapshot = {
        "source_account_ref": listing.source_account_ref,
        "store_id": listing.store_id,
        "item_id": listing.item_id,
        "msku": listing.msku,
        "sku": listing.local_sku,
        "title": listing.title or listing.local_name,
        "local_name": listing.local_name,
        "product_name": product.get("product_name"),
        "store_name": listing.store_name,
        "owner_name": owner_name,
        "owner": owner_name or listing.owner_ref,
        "currency_code": listing.sale_price_currency_code,
        "rule_version": 0,
        "risk": level,
        "reasons": reasons,
        "signals": signals,
        "data_gaps": gaps,
        "metrics": metrics,
        "available": available,
        "listing_id": str(listing.id),
        "picture_url": listing.picture_url,
        "price_amount": str(listing.sale_price_amount) if listing.sale_price_amount is not None and listing.sale_price_currency_code == "USD" else None,
    }
    # Detailed rule evidence is read-only and cannot submit clearance tasks.
    from .risk_evidence_v20 import evidence_for_snapshot
    report = evidence_for_snapshot(
        snapshot, ClearanceRules(), listing=listing, first_wfs_date=first,
        as_of=cutoff,
    )
    snapshot.update(report)
    return snapshot


# Same observation freshness as current_available() in the existing business reader.
_LATEST_WFS = "l.wfs_available_quantity"


def search_unassessed_listings(
    session: Session, accounts: frozenset[str], keyword: str,
    page: int, page_size: int, *, exact_total: bool = False,
    risk_only_requested: bool = False,
    store_refs: tuple[str, ...] = (), owner_names: tuple[str, ...] = (),
    risk_levels: tuple[str, ...] = (), count_override: bool | None = None,
) -> dict:
    """Stable SQL-side keyword and WFS stock filtering before pagination."""
    # V21: Count the complete scoped WFS population for real DB sessions.
    # Preserve existing fake-session test contracts and risk-only behavior.
    if count_override is not None:
        exact_total = count_override
    elif isinstance(session, Session) and not risk_only_requested:
        exact_total = True
    if risk_levels and isinstance(session, Session):
        from .filters_v23 import search_risk_filtered
        return search_risk_filtered(session, accounts, keyword, page, page_size,
                                    store_refs, owner_names, risk_levels)
    if risk_only_requested and isinstance(session, Session):
        # Real high/medium candidates only. Keep the original non-risk path
        # available for unrestricted manual Item-ID applications.
        from .rule_pool_v19 import search_rule_pool
        return search_rule_pool(session, accounts, keyword, page, page_size,
                                exact_total=exact_total)
    params: dict[str, object] = {
        "accounts": sorted(accounts),
        "limit": page_size + 1,
        "offset": (page - 1) * page_size,
    }
    where = ["l.source_account_ref = ANY(:accounts)"]
    if keyword.strip():
        where.append("(l.item_id ILIKE :keyword OR l.msku ILIKE :keyword OR l.local_sku ILIKE :keyword OR l.title ILIKE :keyword)")
        params["keyword"] = "%" + keyword.strip() + "%"
    where.append(f"({_LATEST_WFS}) > 0")
    where.append(f"({_LATEST_WFS}) = trunc(({_LATEST_WFS}))")
    # COUNT and page use exactly the same scoped eligibility predicate. The
    # exact count is opt-in because a full WFS count can be expensive.
    if store_refs or owner_names:
        from .filters_v23 import scoped_parts
        from_and_where, filtered_params = scoped_parts(
            session, accounts, keyword, store_refs, owner_names)
        params.update(filtered_params)
    else:
        from_and_where = f"""
            FROM mart_listing_management_current AS l
            WHERE {' AND '.join(where)}
        """
    ids = session.execute(text(f"""
        SELECT l.id {from_and_where}
        ORDER BY l.store_id, l.item_id, l.source_account_ref, l.id
        LIMIT :limit OFFSET :offset
    """), params).scalars().all()
    total = None
    if exact_total:
        scoped_params = {key: value for key, value in params.items()
                         if key not in ('limit', 'offset')}
        total = int(session.scalar(text('SELECT COUNT(*) ' + from_and_where), scoped_params) or 0)
    has_more = len(ids) > page_size
    selected = list(ids[:page_size])
    if not selected:
        return {"items": [], "page": page, "page_size": page_size,
                "has_more": False, "total": total,
                "total_scope": ("filtered_wfs_stock_eligible" if (store_refs or owner_names)
                                else "all_wfs_stock_eligible"), "risk_filter_applied": False,
                "rule_version": 0, "risk_model_ready": False,
                "risk_calculated_in_memory": True}
    records = session.scalars(
        select(ListingManagementCurrentMart).where(ListingManagementCurrentMart.id.in_(selected))
    ).all()
    by_id = {record.id: record for record in records}
    items = []
    page_rows = [by_id[row_id] for row_id in selected if row_id in by_id]
    # Single-record calls use their unchanged query path, including existing
    # regression fake-session contracts. Real 50-row pages batch expensive facts.
    batch = isinstance(session, Session) and bool(page_rows)
    daily = {}
    product_map = {}
    commission_map = {}
    first_exists = None
    first_map = {}
    costs_by_key = {}
    if batch:
        cutoff = la_today() - timedelta(days=1)
        keys = {(r.source_account_ref, r.store_id, r.item_id) for r in page_rows}
        daily_rows = session.scalars(select(DailySalesItemDayMart).where(
            tuple_(DailySalesItemDayMart.source_account_ref,
                   DailySalesItemDayMart.store_id, DailySalesItemDayMart.item_id).in_(keys),
            DailySalesItemDayMart.business_date_la.between(cutoff - timedelta(days=29), cutoff),
        )).all()
        for fact in daily_rows:
            daily.setdefault((fact.source_account_ref, fact.store_id, fact.item_id), []).append(fact)
        product_map = _product_data_for_listings(session, page_rows)
        commission_map = _commission_for_listings(session, page_rows, cutoff)
        first_map = _page_first_wfs_dates(session, page_rows)
        from app.modules.product_management.daily_sales_costs import (
            load_daily_sales_costs, normalize_sku_key,
        )
        for account in sorted({r.source_account_ref for r in page_rows}):
            account_costs = load_daily_sales_costs(session, source_account_ref=account)
            for row in page_rows:
                if row.source_account_ref == account and row.local_sku:
                    costs_by_key[(account, row.local_sku)] = account_costs.get(normalize_sku_key(row.local_sku))
        first_exists = session.scalar(text("SELECT to_regclass(:relation)"), {
            "relation": "public.listing_wfs_first_stock_la_locked"}) is not None
    # One owner-name query for an entire real page; no per-Item SQL loop.
    # Fake sessions used by the existing unit tests retain their old contract.
    owner_map = (_owner_names_for_listings(session, page_rows)
                 if batch and isinstance(session, Session) else {})
    for row_id in selected:
        listing = by_id.get(row_id)
        if listing is None:
            continue
        available = (int(listing.wfs_available_quantity)
                     if listing.wfs_available_quantity is not None else None)
        if available is None or available <= 0:
            continue
        if batch:
            item = read_business_snapshot(
                session, listing,
                page_daily_rows=daily.get((listing.source_account_ref, listing.store_id, listing.item_id), []),
                page_available=available, first_wfs_exists=first_exists,
                first_date_for_page=first_map.get((listing.source_account_ref,listing.store_id,listing.item_id)),
                first_dates_batched=True,
                page_cost=costs_by_key.get((listing.source_account_ref,listing.local_sku)),
                product_data=product_map, store_commissions=commission_map)
        else:
            item = read_business_snapshot(session, listing)
        owner_name = owner_map.get((listing.source_account_ref, listing.local_sku))
        if owner_name:
            item["owner_name"] = owner_name
            item["owner"] = owner_name
        items.append(item)
    return {"items": items, "page": page, "page_size": page_size,
            "has_more": has_more, "total": total,
            "total_scope": ("filtered_wfs_stock_eligible" if (store_refs or owner_names)
                                else "all_wfs_stock_eligible"), "risk_filter_applied": False,
            "rule_version": 0, "risk_model_ready": False,
            "risk_calculated_in_memory": True}

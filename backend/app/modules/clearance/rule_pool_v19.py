"""Read-only, rule-verified automatic WFS clearance candidate pool.

Never infers a missing day as zero and never creates an application.  All
identities are (source account, store ID, Walmart Item ID), never local SKU.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.modules.data_pages.models import DailySalesItemDayMart, ListingManagementCurrentMart
from app.modules.product_management.daily_sales_costs import load_daily_sales_costs, normalize_sku_key
from .read_only_listings import (
    _assess_read_only, _commission_for_listings,
    _owner_names_for_listings, _page_first_wfs_dates, _product_data_for_listings,
    _window_stats, la_today, read_business_snapshot,
)


def _identity(row: ListingManagementCurrentMart) -> tuple[str, str, str]:
    return row.source_account_ref, row.store_id, row.item_id


def _chunks(rows: list, length: int = 100):
    for start in range(0, len(rows), length):
        yield rows[start:start + length]


def rule_qualified(level: str) -> bool:
    """Only positive, evidence-backed outcomes enter automatically."""
    return level in {"high", "medium"}


def search_rule_pool(
    session: Session,
    accounts: frozenset[str],
    keyword: str,
    page: int,
    page_size: int,
    *,
    exact_total: bool = False,
) -> dict:
    # Scope all data before calculating. No production rule/state-table writes.
    if not accounts:
        return {"items": [], "page": page, "page_size": page_size,
                "has_more": False, "total": 0,
                "total_scope": "clearance_rule_candidates", "risk_filter_applied": True,
                "rule_version": 0, "risk_model_ready": False,
                "risk_calculated_in_memory": True}

    model = ListingManagementCurrentMart
    query = select(model).where(
        model.source_account_ref.in_(sorted(accounts)),
        model.wfs_available_quantity > 0,
        model.wfs_available_quantity == func.trunc(model.wfs_available_quantity),
    )
    if keyword.strip():
        pattern = "%" + keyword.strip() + "%"
        query = query.where(or_(model.item_id.ilike(pattern), model.msku.ilike(pattern),
                                model.local_sku.ilike(pattern), model.title.ilike(pattern)))
    listings = session.scalars(query.order_by(model.store_id, model.item_id,
                                              model.source_account_ref, model.id)).all()
    candidates: dict[tuple[str, str, str], tuple[ListingManagementCurrentMart, str]] = {}
    cutoff = la_today() - timedelta(days=1)

    # Only lightweight facts are loaded for the full stock pool. Expensive
    # Product Management/owner/commission reads happen after risk pagination.
    for batch in _chunks(list(listings)):
        keys = {_identity(row) for row in batch}
        facts = session.scalars(select(DailySalesItemDayMart).where(
            tuple_(DailySalesItemDayMart.source_account_ref,
                   DailySalesItemDayMart.store_id,
                   DailySalesItemDayMart.item_id).in_(keys),
            DailySalesItemDayMart.business_date_la.between(
                cutoff - timedelta(days=29), cutoff),
        )).all()
        daily: dict[tuple[str, str, str], dict[date, list]] = defaultdict(lambda: defaultdict(list))
        for fact in facts:
            daily[(fact.source_account_ref, fact.store_id, fact.item_id)][fact.business_date_la].append(fact)
        first_dates = _page_first_wfs_dates(session, batch)
        for row in batch:
            key = _identity(row)
            available = int(row.wfs_available_quantity)
            first = first_dates.get(key)
            first_days = (cutoff - first).days + 1 if first is not None and first <= cutoff else None
            windows = {days: _window_stats(daily[key], cutoff, days, first)
                       for days in (7, 14, 30)}
            level, _reasons, _signals, _gaps, _metrics = _assess_read_only(
                row, available, windows, first_days, None,
            )
            if not rule_qualified(level):
                continue
            previous = candidates.get(key)
            if previous is None or (level == "high" and previous[1] != "high"):
                candidates[key] = (row, level)

    qualified = sorted(candidates.values(), key=lambda pair: (
        0 if pair[1] == "high" else 1,
        pair[0].store_id, pair[0].item_id, pair[0].source_account_ref,
    ))
    total = len(qualified)
    start = (page - 1) * page_size
    selected = [listing for listing, _level in qualified[start:start + page_size]]
    items: list[dict] = []
    if selected:
        keys = {_identity(row) for row in selected}
        facts = session.scalars(select(DailySalesItemDayMart).where(
            tuple_(DailySalesItemDayMart.source_account_ref,
                   DailySalesItemDayMart.store_id,
                   DailySalesItemDayMart.item_id).in_(keys),
            DailySalesItemDayMart.business_date_la.between(cutoff - timedelta(days=29), cutoff),
        )).all()
        by_key: dict[tuple[str, str, str], list] = defaultdict(list)
        for fact in facts:
            by_key[(fact.source_account_ref, fact.store_id, fact.item_id)].append(fact)
        first_dates = _page_first_wfs_dates(session, selected)
        products = _product_data_for_listings(session, selected)
        commissions = _commission_for_listings(session, selected, cutoff)
        owners = _owner_names_for_listings(session, selected)
        cost_by_account: dict[str, dict] = {
            account: load_daily_sales_costs(session, source_account_ref=account)
            for account in sorted({row.source_account_ref for row in selected})
        }
        for listing in selected:
            account = listing.source_account_ref
            snapshot = read_business_snapshot(
                session, listing,
                page_daily_rows=by_key.get(_identity(listing), []),
                page_available=int(listing.wfs_available_quantity),
                first_date_for_page=first_dates.get(_identity(listing)),
                first_dates_batched=True,
                page_cost=cost_by_account.get(account, {}).get(normalize_sku_key(listing.local_sku)),
                product_data=products, store_commissions=commissions,
            )
            owner = owners.get((account, listing.local_sku))
            if owner:
                snapshot["owner_name"] = owner
                snapshot["owner"] = owner
            if rule_qualified(snapshot["risk"]):
                items.append(snapshot)

    return {"items": items, "page": page, "page_size": page_size,
            "has_more": total > start + len(items), "total": total,
            "total_scope": "clearance_rule_candidates", "risk_filter_applied": True,
            "rule_version": 0, "risk_model_ready": False,
            "risk_calculated_in_memory": True}

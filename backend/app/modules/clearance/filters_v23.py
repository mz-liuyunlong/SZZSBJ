"""Scoped read-only WFS facets and complete-population risk filtering.

Filters are applied to the same WFS-eligible Listing population BEFORE paging.
No writes, no extra database schema and no synthetic owner/risk values.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

STORE_SEPARATOR = "::"
RISK_LEVELS = frozenset({"high", "medium", "low", "none", "unknown"})
WFS_PREDICATE = (
    "l.wfs_available_quantity > 0 AND l.wfs_available_quantity = trunc(l.wfs_available_quantity)"
)


def owner_parts(session: Session) -> tuple[str, str]:
    """Resolve owners using the same SKU/account master as Listing Management."""
    relation = session.scalar(
        text("SELECT to_regclass(:relation)"),
        {
            "relation": "public.dwd_lingxing_sku_product_info_current",
        },
    )
    if relation is None:
        return "", "COALESCE(NULLIF(BTRIM(l.owner_ref), ''), '未分配')"
    join = """
        LEFT JOIN LATERAL (
            SELECT MAX(NULLIF(BTRIM(d.owner_name), '')) AS owner_name
            FROM dwd_lingxing_sku_product_info_current AS d
            WHERE d.source_account_ref = l.source_account_ref
              AND d.lingxing_sku_code = l.local_sku
        ) AS owner_match ON TRUE
    """
    return join, "COALESCE(owner_match.owner_name, NULLIF(BTRIM(l.owner_ref), ''), '未分配')"


def scoped_parts(
    session: Session,
    accounts: frozenset[str],
    keyword: str = "",
    store_refs: tuple[str, ...] = (),
    owner_names: tuple[str, ...] = (),
    *,
    owner_needed: bool = False,
) -> tuple[str, dict[str, object]]:
    """Shared SQL source for both paginated data and facets; account-scoped."""
    join, owner_expr = owner_parts(session) if (owner_needed or owner_names) else ("", "")
    parts = ["l.source_account_ref = ANY(:accounts)", WFS_PREDICATE]
    params: dict[str, object] = {"accounts": sorted(accounts)}
    if keyword.strip():
        parts.append(
            "(l.item_id ILIKE :keyword OR l.msku ILIKE :keyword "
            "OR l.local_sku ILIKE :keyword OR l.title ILIKE :keyword)"
        )
        params["keyword"] = "%" + keyword.strip() + "%"
    if store_refs:
        parts.append("(l.source_account_ref || '::' || l.store_id) = ANY(:store_refs)")
        params["store_refs"] = list(store_refs)
    if owner_names:
        parts.append(f"{owner_expr} = ANY(:owner_names)")
        params["owner_names"] = list(owner_names)
    return f"FROM mart_listing_management_current AS l {join} WHERE {' AND '.join(parts)}", params


def list_filter_options(session: Session, accounts: frozenset[str]) -> dict:
    """Full authorized WFS population, not current table page."""
    # Use one owner-source check and the same owner expression in both facets.
    join, owner_expr = owner_parts(session)
    clause = (
        "FROM mart_listing_management_current AS l "
        + join
        + " WHERE l.source_account_ref = ANY(:accounts) AND "
        + WFS_PREDICATE
    )
    params = {"accounts": sorted(accounts)}
    rows = session.execute(
        text(f"""
        SELECT DISTINCT l.source_account_ref, l.store_id,
               COALESCE(NULLIF(BTRIM(l.store_name), ''), l.store_id) AS display_store,
               {owner_expr} AS display_owner
        {clause}
    """),
        params,
    ).all()
    stores: dict[str, str] = {}
    owners: set[str] = set()
    for account, store_id, name, owner in rows:
        if account is None or store_id is None:
            continue
        ref = str(account) + STORE_SEPARATOR + str(store_id)
        stores[ref] = str(name or store_id)
        owners.add(str(owner or "未分配"))
    return {
        "stores": [
            {"value": ref, "label": label, "source_account_ref": ref.split(STORE_SEPARATOR, 1)[0]}
            for ref, label in sorted(stores.items(), key=lambda pair: (pair[1], pair[0]))
        ],
        "owners": [{"value": name, "label": name} for name in sorted(owners)],
        "risks": [
            {"value": value, "label": label}
            for value, label in (
                ("high", "高风险"),
                ("medium", "中风险"),
                ("low", "低风险"),
                ("none", "无风险"),
                ("unknown", "待评估"),
            )
        ],
    }


def search_risk_filtered(
    session: Session,
    accounts: frozenset[str],
    keyword: str,
    page: int,
    page_size: int,
    store_refs: tuple[str, ...],
    owner_names: tuple[str, ...],
    risk_levels: tuple[str, ...],
    *,
    rules=None,
    rule_version: int = 0,
) -> dict:
    """Evaluate the whole scoped population with one set of batched source reads.

    No risk-index tables are available on the protected 0076 data source.
    Filtering before pagination therefore requires full evidence evaluation,
    never an approximate Listing-only predicate or fake risk.
    """
    from collections import defaultdict
    from datetime import timedelta

    from sqlalchemy import select, text, tuple_

    from app.modules.data_pages.models import DailySalesItemDayMart, ListingManagementCurrentMart
    from app.modules.product_management.daily_sales_costs import (
        load_daily_sales_costs,
        normalize_sku_key,
    )

    from .read_only_listings import (
        _commission_for_listings,
        _owner_names_for_listings,
        _page_first_wfs_dates,
        _product_data_for_listings,
        read_business_snapshot,
    )
    from .repository import la_today

    clause, params = scoped_parts(session, accounts, keyword, store_refs, owner_names)
    ids = (
        session.execute(
            text(
                "SELECT l.id "
                + clause
                + " ORDER BY l.store_id, l.item_id, l.source_account_ref, l.id"
            ),
            params,
        )
        .scalars()
        .all()
    )
    if not ids:
        return {
            "items": [],
            "page": page,
            "page_size": page_size,
            "has_more": False,
            "total": 0,
            "total_scope": "filtered_wfs_stock_eligible",
            "risk_filter_applied": True,
            "rule_version": rule_version,
            "risk_summary": {
                "counts": {k: 0 for k in ("high", "medium", "low", "none", "unknown")},
                "risk_inventory_cost_usd": 0.0,
                "risk_cost_missing": False,
            },
            "risk_model_ready": False,
            "risk_calculated_in_memory": True,
        }
    found = session.scalars(
        select(ListingManagementCurrentMart).where(ListingManagementCurrentMart.id.in_(ids))
    ).all()
    by_id = {row.id: row for row in found}
    listings = [by_id[row_id] for row_id in ids if row_id in by_id]
    cutoff = la_today() - timedelta(days=1)
    first_map = _page_first_wfs_dates(session, listings)
    product_map = _product_data_for_listings(session, listings)
    commission_map = _commission_for_listings(session, listings, cutoff)
    owner_map = _owner_names_for_listings(session, listings)
    costs_by_key = {}
    for account in sorted({row.source_account_ref for row in listings}):
        costs = load_daily_sales_costs(session, source_account_ref=account)
        for row in listings:
            if row.source_account_ref == account and row.local_sku:
                costs_by_key[(account, row.local_sku)] = costs.get(normalize_sku_key(row.local_sku))

    # Chunk tuple-IN requests to keep SQL parameter and memory pressure bounded.
    daily = defaultdict(list)
    keys = sorted({(row.source_account_ref, row.store_id, row.item_id) for row in listings})
    for start in range(0, len(keys), 150):
        batch = keys[start : start + 150]
        facts = session.scalars(
            select(DailySalesItemDayMart).where(
                tuple_(
                    DailySalesItemDayMart.source_account_ref,
                    DailySalesItemDayMart.store_id,
                    DailySalesItemDayMart.item_id,
                ).in_(batch),
                DailySalesItemDayMart.business_date_la.between(cutoff - timedelta(days=29), cutoff),
            )
        ).all()
        for fact in facts:
            daily[(fact.source_account_ref, fact.store_id, fact.item_id)].append(fact)

    matched = []
    counts = {k: 0 for k in ("high", "medium", "low", "none", "unknown")}
    risk_capital = 0.0
    missing_capital = False
    for listing in listings:
        available = listing.wfs_available_quantity
        if available is None or available <= 0:
            continue
        stock = int(available)
        key = (listing.source_account_ref, listing.store_id, listing.item_id)
        row = read_business_snapshot(
            session,
            listing,
            page_available=stock,
            page_daily_rows=daily.get(key, []),
            first_dates_batched=True,
            first_date_for_page=first_map.get(key),
            page_cost=costs_by_key.get((listing.source_account_ref, listing.local_sku)),
            product_data=product_map,
            store_commissions=commission_map,
            rules=rules,
            rule_version=rule_version,
        )
        level = row.get("risk", "unknown")
        if level not in counts:
            level = "unknown"
        counts[level] += 1
        if level in ("high", "medium"):
            capital = row.get("metrics", {}).get("capital_purchase_first_leg_usd")
            if capital is None:
                missing_capital = True
            else:
                risk_capital += float(capital)
        if risk_levels and level not in risk_levels:
            continue
        owner = owner_map.get((listing.source_account_ref, listing.local_sku))
        if owner:
            row["owner"] = owner
            row["owner_name"] = owner
        matched.append(row)
    rank = {"high": 0, "medium": 1, "low": 2, "none": 3, "unknown": 4}
    matched.sort(key=lambda row: (
        rank.get(row.get("risk", "unknown"), 4),
        row.get("store_id") or "",
        row.get("item_id") or "",
    ))
    start = (page - 1) * page_size
    return {
        "items": matched[start : start + page_size],
        "page": page,
        "page_size": page_size,
        "has_more": start + page_size < len(matched),
        "total": len(matched),
        "total_scope": (
            "filtered_wfs_stock_eligible"
            if (store_refs or owner_names or risk_levels or keyword.strip())
            else "all_wfs_stock_eligible"
        ),
        "risk_filter_applied": bool(risk_levels),
        "rule_version": rule_version,
        "risk_summary": {
            "counts": counts,
            "risk_inventory_cost_usd": (
                None if missing_capital else round(risk_capital, 2)
            ),
            "risk_cost_missing": missing_capital,
        },
        "risk_model_ready": False,
        "risk_calculated_in_memory": True,
    }

"""Read Order Profit ranges using compact PostgreSQL group aggregates.

Single-day and noncanonical-identity fallbacks retain the original reader.
No persisted data or summary permission handling is changed.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import case, distinct, func, select, tuple_
from sqlalchemy.dialects.postgresql import JSONB, aggregate_order_by, array_agg

from app.modules.data_pages import order_profit_range_aggregation as legacy
from app.modules.data_pages.models import DailySalesItemDayMart as Mart
from app.modules.data_pages.sales_report_sort import profit_value, sort_values
from app.modules.data_pages.schemas import OrderProfitListData

_SUMMARY_SUMS = (
    "sales_qty",
    "order_count",
    "sales_amount",
    "return_qty",
    "refund_amount",
    "gross_profit_amount",
    "ad_spend_amount",
    "sem_ad_spend_amount",
)
_SUMMARY_FIRST = (
    "sales_currency_code",
    "refund_currency_code",
    "gross_profit_currency_code",
    "ad_spend_currency_code",
)
_DETAIL_SUMS = (
    "sample_qty",
    "sample_amount",
    "commission_fee_amount",
    "wfs_fee_total_amount",
    "wfs_low_price_surcharge_amount",
    "purchase_cost_total_usd",
    "first_leg_cost_total_usd",
    "storage_fee_total_amount",
)
_DETAIL_FIRST = ("business_timezone", "local_sku", "local_name", "title", "calc_version")
_LISTS = ("store_id", "store_name", "owner_ref", "msku")
_WEIGHTED = {
    "return_rate_30d": "sales_qty",
    "wfs_fee_unit_amount": "sales_qty",
    "purchase_cost_unit_cny": "cost_quantity",
    "first_leg_cost_unit_cny": "cost_quantity",
    "storage_fee_unit_amount": "cost_quantity",
}
# Equivalent to Python str.strip() for text fields, including Unicode whitespace.
_TRIM_CHARS = "".join(chr(i) for i in range(0x3001) if chr(i).isspace())


def _first_expression(name):
    col = getattr(Mart, name)
    return (
        array_agg(aggregate_order_by(col, Mart.business_date_la.asc()))
        .filter(func.btrim(col, _TRIM_CHARS) != "")[1]
        .label(name)
    )


def _grouped_statement(service, query, account_refs, *, summary_only):
    statement = service.daily_sales_repository._filtered_statement(
        account_refs=account_refs,
        start_date=query.start_date,
        end_date=query.end_date,
        platform=query.platform,
        store_id=query.store_id,
        owner_ref=query.owner_ref,
        search_field=query.search_field,
        keyword=query.keyword,
        batch_values="",
    )
    fields = [
        Mart.source_account_ref,
        Mart.item_id,
        func.max(Mart.business_date_la).label("business_date_la"),
        func.max(Mart.calculated_at).label("calculated_at"),
        func.sum(
            func.greatest(
                func.coalesce(Mart.refund_amount, 0) * (1 - func.coalesce(Mart.commission_rate, 0)),
                0,
            )
        ).label("refund_loss_sum"),
    ]
    sums = _SUMMARY_SUMS if summary_only else _SUMMARY_SUMS + _DETAIL_SUMS
    firsts = _SUMMARY_FIRST if summary_only else _SUMMARY_FIRST + _DETAIL_FIRST
    fields.extend(func.sum(getattr(Mart, name)).label(name) for name in sums)
    fields.extend(_first_expression(name) for name in firsts)
    if not summary_only:
        fields.append(func.min(Mart.business_date_la).label("first_date"))
        for name in _LISTS:
            fields.append(
                array_agg(
                    aggregate_order_by(
                        getattr(Mart, name),
                        Mart.business_date_la.asc(),
                    )
                ).label(name + "_values")
            )
        fields.extend(
            [
                array_agg(distinct(Mart.cost_status)).label("statuses"),
                func.jsonb_agg(
                    aggregate_order_by(
                        Mart.missing_cost_codes_json,
                        Mart.business_date_la.asc(),
                    ),
                    type_=JSONB(),
                ).label("cost_codes"),
            ]
        )
        for name, weight_name in _WEIGHTED.items():
            value, weight = getattr(Mart, name), getattr(Mart, weight_name)
            eligible = (value.is_not(None)) & (weight > 0)
            fields.extend(
                [
                    func.sum(case((eligible, value * weight), else_=0)).label(name + "_num"),
                    func.sum(case((eligible, weight), else_=0)).label(name + "_den"),
                    func.sum(value).label(name + "_sum"),
                    func.count(value).label(name + "_count"),
                ]
            )
    # The same account/date/store/owner/search restrictions as the original reader.
    return (
        statement.with_only_columns(*fields, maintain_column_froms=True)
        .order_by(None)
        .group_by(
            Mart.source_account_ref,
            Mart.item_id,
        )
        .order_by(Mart.source_account_ref.asc(), Mart.item_id.asc())
    )


def _weighted_from_group(row, name):
    den = legacy._coerce_decimal(row[name + "_den"])
    if den > 0:
        return (legacy._coerce_decimal(row[name + "_num"]) / den).quantize(legacy.RATIO_SCALE)
    count = row[name + "_count"]
    if count:
        return (legacy._coerce_decimal(row[name + "_sum"]) / Decimal(count)).quantize(
            legacy.RATIO_SCALE
        )
    return None


def _compact_row(group, *, summary_only):
    row = SimpleNamespace(**dict(group))
    # Summary and projection refund loss are replaced with the sum of per-row losses;
    # computing the loss on an aggregated refund amount would be incorrect.
    row.commission_rate = None
    if not summary_only:
        for name in _WEIGHTED:
            setattr(row, name, _weighted_from_group(group, name))
        # Values above are already weighted; one synthetic row cannot reweight them.
        row.cost_quantity = Decimal(1)
        for name in _LISTS:
            values = legacy._distinct_values(
                (SimpleNamespace(value=v) for v in (group[name + "_values"] or [])),
                "value",
            )
            setattr(row, name + "_distinct", values)
            setattr(row, name, values[0] if values else None)
        statuses = [SimpleNamespace(cost_status=v) for v in (group["statuses"] or [])]
        row.cost_status = legacy._cost_status(statuses)
        row.missing_cost_codes_json = legacy._missing_cost_codes(
            [
                SimpleNamespace(cost_status=row.cost_status, missing_cost_codes_json=v)
                for v in (group["cost_codes"] or [None])
            ]
        )
    return row


def _compact_projection(row, inventory):
    result = legacy._projection_for_item(row.source_account_ref, row.item_id, [row], inventory)
    return replace(
        result,
        id=legacy._range_id(
            source_account_ref=row.source_account_ref,
            item_id=row.item_id,
            start_date=row.first_date,
            end_date=row.business_date_la,
        ),
        store_ids_json=row.store_id_distinct,
        store_names_json=row.store_name_distinct,
        owner_refs_json=row.owner_ref_distinct,
        mskus_json=row.msku_distinct,
        store_count=len(row.store_id_distinct),
        refund_loss_amount=legacy._coerce_decimal(row.refund_loss_sum),
    )


def _compact_summary(rows):
    return legacy._summary_from_daily_rows(rows).model_copy(
        update={
            "refund_loss_amount": sum(
                (legacy._coerce_decimal(row.refund_loss_sum) for row in rows), legacy.ZERO
            ),
        }
    )


def _default_page_statement(service, query, account_refs):
    """Rank all products using narrow metrics, detail only selected page keys.

    Both aggregates are evaluated in a single statement/snapshot. The narrow
    groups retain the existing summary semantics, including blank identity rows.
    """
    groups = (
        _grouped_statement(
            service,
            query,
            account_refs,
            summary_only=True,
        )
        .add_columns(_first_expression("local_sku"))
        .cte("profit_summary_groups")
    )
    page_keys = (
        select(groups.c.source_account_ref, groups.c.item_id)
        .where(
            groups.c.source_account_ref != "",
            groups.c.item_id != "",
        )
        .order_by(
            func.coalesce(groups.c.sales_qty, 0).desc(),
            func.coalesce(groups.c.sales_amount, 0).desc(),
            func.coalesce(groups.c.local_sku, groups.c.item_id).collate("C").asc(),
            groups.c.source_account_ref.asc(),
            groups.c.item_id.asc(),
        )
        .offset((query.page - 1) * query.page_size)
        .limit(query.page_size)
        .cte("profit_page_keys")
    )
    details = (
        _grouped_statement(
            service,
            query,
            account_refs,
            summary_only=False,
        )
        .where(
            tuple_(Mart.source_account_ref, Mart.item_id).in_(
                select(page_keys.c.source_account_ref, page_keys.c.item_id),
            )
        )
        .order_by(None)
        .cte("profit_page_details")
    )
    return (
        select(
            *groups.c,
            *(column.label("detail_" + column.key) for column in details.c),
        )
        .select_from(
            groups.outerjoin(
                details,
                (groups.c.source_account_ref == details.c.source_account_ref)
                & (groups.c.item_id == details.c.item_id),
            )
        )
        .order_by(
            groups.c.source_account_ref.asc(),
            groups.c.item_id.asc(),
        )
    )


def _read_default_page(service, query, account_refs):
    groups = (
        service.daily_sales_repository.session.execute(
            _default_page_statement(service, query, account_refs),
        )
        .mappings()
        .all()
    )
    if any(
        str(g[k] or "") != str(g[k] or "").strip()
        for g in groups
        for k in ("source_account_ref", "item_id")
    ):
        return None
    summary_rows = [_compact_row(g, summary_only=True) for g in groups]
    page_rows = [
        _compact_row(
            {
                **{k.removeprefix("detail_"): v for k, v in g.items() if k.startswith("detail_")},
                "local_sku": g["local_sku"],
            },
            summary_only=False,
        )
        for g in groups
        if g["detail_source_account_ref"] is not None
    ]
    inventory = legacy._current_wfs_inventory_map(service, page_rows, query.store_id)
    projections = [_compact_projection(row, inventory) for row in page_rows]
    projections.sort(key=legacy._order_profit_sort_key)
    return (
        OrderProfitListData(
            items=[service._to_read(row) for row in projections],
            summary=_compact_summary(summary_rows),
        ),
        sum(legacy._order_profit_group_key(row) is not None for row in summary_rows),
        legacy._latest_calculated_at(summary_rows),
    )


def read_grouped_order_profit(service, query, account_refs):
    """Return a compact range result, or None to preserve legacy edge cases."""
    summary_only = bool(getattr(query, "summary_only", False))
    if not summary_only and not getattr(query, "sort_field", None):
        return _read_default_page(service, query, account_refs)
    groups = (
        service.daily_sales_repository.session.execute(
            _grouped_statement(service, query, account_refs, summary_only=summary_only),
        )
        .mappings()
        .all()
    )
    # The old Python grouper trims IDs. If a stored ID contains surrounding
    # whitespace, SQL grouping by raw IDs could change the business identity.
    # Keep the original reader for that rare data condition instead.
    if any(
        str(g[k] or "") != str(g[k] or "").strip()
        for g in groups
        for k in ("source_account_ref", "item_id")
    ):
        return None
    rows = [_compact_row(g, summary_only=summary_only) for g in groups]
    valid = [row for row in rows if legacy._order_profit_group_key(row) is not None]
    summary = _compact_summary(rows)
    latest = legacy._latest_calculated_at(rows)
    if summary_only:
        return OrderProfitListData(items=[], summary=summary), len(valid), latest

    inventory = legacy._current_wfs_inventory_map(service, valid, query.store_id)
    projections = [_compact_projection(row, inventory) for row in valid]
    projections.sort(key=legacy._order_profit_sort_key)
    if getattr(query, "sort_field", None):
        projections = sort_values(
            projections,
            lambda row: profit_value(service._to_read(row), query.sort_field),
            query.sort_direction,
            lambda row: (legacy._order_profit_sort_key(row), str(row.id)),
        )
    offset = (query.page - 1) * query.page_size
    return (
        OrderProfitListData(
            items=[service._to_read(row) for row in projections[offset : offset + query.page_size]],
            summary=summary,
        ),
        len(projections),
        latest,
    )

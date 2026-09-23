from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.after_sales.schemas import RefundBaseQuery, RefundItemQuery

_OWNER_CTE = """
owner_map as (
    select distinct on (source_account_ref, store_id, item_id, msku)
        source_account_ref,
        store_id,
        item_id,
        msku,
        owner_ref
    from mart_daily_sales_item_day
    where source_account_ref = any(:accounts)
      and owner_ref is not null
      and btrim(owner_ref) <> ''
    order by source_account_ref, store_id, item_id, msku, business_date_la desc, updated_at desc
)
"""

_REASON_EXPR = (
    "coalesce(nullif(r.return_reason_category,''), "
    "nullif(r.return_reason_code,''), 'UNCLASSIFIED')"
)
_SKU_EXPR = "coalesce(nullif(r.local_sku,''), nullif(r.msku,''), nullif(r.item_id,''), 'UNKNOWN')"
_PRODUCT_KEY_EXPR = (
    "json_build_array(coalesce(r.store_id,''), coalesce(r.item_id,''), "
    "coalesce(r.msku,''))::text"
)
_SALES_PRODUCT_KEY_EXPR = (
    "json_build_array(coalesce(m.store_id,''), coalesce(m.item_id,''), "
    "coalesce(m.msku,''))::text"
)
_REFUND_PRODUCT_IDENTITY_READY = (
    "nullif(r.store_id,'') is not null and nullif(r.item_id,'') is not null "
    "and nullif(r.msku,'') is not null"
)
_SALES_PRODUCT_IDENTITY_READY = (
    "nullif(m.store_id,'') is not null and nullif(m.item_id,'') is not null "
    "and nullif(m.msku,'') is not null"
)

_STORE_NAME_EXPR = """
coalesce(
    (
        select nullif(s.store_name,'')
        from dim_lingxing_stores s
        where s.source_account_ref = r.source_account_ref
          and s.store_id = r.store_id
          and s.platform_code = 'walmart'
          and nullif(s.store_name,'') is not null
        order by s.source_observed_at desc nulls last, s.updated_at desc
        limit 1
    ),
    nullif(r.store_name,''),
    nullif(r.raw_store_name,'')
)
""".strip()

_PRODUCT_NAME_EXPR = """
(
    select coalesce(nullif(p.product_name,''), nullif(pic.product_name,''))
    from dwd_lingxing_sku_identity_index i
    left join products p
      on p.id = i.product_id
     and p.deleted_at is null
    left join dwd_lingxing_sku_product_info_current pic
      on pic.identity_id = i.id
    where i.source_account_ref = r.source_account_ref
      and i.is_active = true
      and nullif(i.lingxing_sku_code,'') = nullif(r.local_sku,'')
    order by
        case when nullif(p.product_name,'') is not null then 0 else 1 end,
        i.updated_at desc
    limit 1
)
""".strip()

_SALES_PRODUCT_NAME_EXPR = """
(
    select coalesce(nullif(p.product_name,''), nullif(pic.product_name,''))
    from dwd_lingxing_sku_identity_index i
    left join products p
      on p.id = i.product_id
     and p.deleted_at is null
    left join dwd_lingxing_sku_product_info_current pic
      on pic.identity_id = i.id
    where i.source_account_ref = m.source_account_ref
      and i.is_active = true
      and nullif(i.lingxing_sku_code,'') = nullif(m.local_sku,'')
    order by
        case when nullif(p.product_name,'') is not null then 0 else 1 end,
        i.updated_at desc
    limit 1
)
""".strip()

_SEARCH_COLUMNS = {
    "sku": _SKU_EXPR,
    "msku": "r.msku",
    "item_id": "r.item_id",
    "product_name": _PRODUCT_NAME_EXPR,
    "order_id": (
        "coalesce(nullif(r.purchase_order_id,''), nullif(r.customer_order_id,''), "
        "r.return_order_id)"
    ),
}

_SALES_SEARCH_COLUMNS = {
    "sku": "coalesce(nullif(m.local_sku,''), nullif(m.msku,''), nullif(m.item_id,''), 'UNKNOWN')",
    "msku": "m.msku",
    "item_id": "m.item_id",
    "product_name": _SALES_PRODUCT_NAME_EXPR,
}

_SORT_COLUMNS = {
    "refund_time": "r.return_order_at",
    "purchase_time": "r.purchase_time_at",
    "refund_qty": "r.return_qty",
    "refund_amount": "r.refund_amount",
    "refund_loss": "r.refund_loss_amount",
}


def split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


class AfterSalesRefundRepository:
    """Read-only SQL access for the after-sales refund management page."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def refund_stats(
        self,
        query: RefundBaseQuery,
        account_refs: frozenset[str],
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        where, params = self._refund_where(
            query,
            account_refs,
            start_date=start_date,
            end_date=end_date,
        )
        sql = f"""
            with {_OWNER_CTE}
            select
                count(*)::int as refund_item_rows,
                count(distinct r.return_order_id)::int as refund_orders,
                coalesce(sum(r.return_qty),0) as refund_qty,
                coalesce(sum(r.refund_amount),0) as refund_amount,
                case when count(distinct r.refund_currency_code) = 1
                     then max(r.refund_currency_code) end as refund_currency_code,
                coalesce(sum(r.refund_loss_amount) filter (
                    where r.refund_loss_effective = true
                ),0) as refund_loss_amount,
                max(r.updated_at) as latest_updated_at
            from after_sales_refund_items r
            left join owner_map om
              on om.source_account_ref = r.source_account_ref
             and om.store_id = r.store_id
             and om.item_id = r.item_id
             and om.msku = r.msku
            where {" and ".join(where)}
        """
        row = self.session.execute(text(sql), params).mappings().one()
        return dict(row)

    def sales_qty(
        self,
        query: RefundBaseQuery,
        account_refs: frozenset[str],
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        product_key: str | None = None,
    ) -> Decimal:
        where, params = self._sales_where(
            query,
            account_refs,
            start_date=start_date,
            end_date=end_date,
            product_key=product_key,
        )
        value = self.session.execute(
            text(
                "select coalesce(sum(m.sales_qty),0) "
                "from mart_daily_sales_item_day m where " + " and ".join(where)
            ),
            params,
        ).scalar_one()
        return value or Decimal("0")

    def refund_trend(
        self,
        query: RefundBaseQuery,
        account_refs: frozenset[str],
        *,
        product_key: str | None = None,
    ) -> list[dict[str, Any]]:
        where, params = self._refund_where(query, account_refs)
        if product_key:
            where.append(f"{_PRODUCT_KEY_EXPR} = :product_key")
            params["product_key"] = product_key
        rows = (
            self.session.execute(
                text(
                    f"""
                    with {_OWNER_CTE}
                    select
                        r.return_order_at::date as day,
                        count(distinct r.return_order_id)::int as refund_orders,
                        coalesce(sum(r.return_qty),0) as refund_qty,
                        coalesce(sum(r.refund_amount),0) as refund_amount,
                        coalesce(sum(r.refund_loss_amount) filter (
                            where r.refund_loss_effective = true
                        ),0) as refund_loss_amount
                    from after_sales_refund_items r
                    left join owner_map om
                      on om.source_account_ref = r.source_account_ref
                     and om.store_id = r.store_id
                     and om.item_id = r.item_id
                     and om.msku = r.msku
                    where {" and ".join(where)}
                    group by r.return_order_at::date
                    order by day
                    """
                ),
                params,
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def sales_trend(
        self,
        query: RefundBaseQuery,
        account_refs: frozenset[str],
        *,
        product_key: str | None = None,
    ) -> list[dict[str, Any]]:
        where, params = self._sales_where(query, account_refs, product_key=product_key)
        rows = (
            self.session.execute(
                text(
                    "select m.business_date_la as day, coalesce(sum(m.sales_qty),0) as sales_qty "
                    "from mart_daily_sales_item_day m where "
                    + " and ".join(where)
                    + " group by m.business_date_la order by m.business_date_la"
                ),
                params,
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def reason_breakdown(
        self,
        query: RefundBaseQuery,
        account_refs: frozenset[str],
        *,
        product_key: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        where, params = self._refund_where(query, account_refs)
        if product_key:
            where.append(f"{_PRODUCT_KEY_EXPR} = :product_key")
            params["product_key"] = product_key
        params["limit"] = limit
        rows = (
            self.session.execute(
                text(
                    f"""
                    with {_OWNER_CTE}
                    select
                        {_REASON_EXPR} as reason,
                        count(distinct r.return_order_id)::int as refund_orders,
                        coalesce(sum(r.return_qty),0) as refund_qty,
                        coalesce(sum(r.refund_amount),0) as refund_amount,
                        coalesce(sum(r.refund_loss_amount) filter (
                            where r.refund_loss_effective = true
                        ),0) as refund_loss_amount
                    from after_sales_refund_items r
                    left join owner_map om
                      on om.source_account_ref = r.source_account_ref
                     and om.store_id = r.store_id
                     and om.item_id = r.item_id
                     and om.msku = r.msku
                    where {" and ".join(where)}
                    group by {_REASON_EXPR}
                    order by refund_qty desc, refund_orders desc, reason
                    limit :limit
                    """
                ),
                params,
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def facets(
        self,
        query: RefundBaseQuery,
        account_refs: frozenset[str],
    ) -> dict[str, list[dict[str, str]]]:
        base_where, params = self._refund_where(
            query,
            account_refs,
            include_facets=False,
            include_search=False,
        )
        base_sql = " and ".join(base_where)
        rows = self.session.execute(
            text(
                f"""
                with {_OWNER_CTE}
                select distinct r.store_id as value,
                       coalesce({_STORE_NAME_EXPR}, '未匹配店铺') as label
                from after_sales_refund_items r
                left join owner_map om
                  on om.source_account_ref = r.source_account_ref
                 and om.store_id = r.store_id
                 and om.item_id = r.item_id
                 and om.msku = r.msku
                where {base_sql}
                order by label
                """
            ),
            params,
        ).mappings().all()
        stores = [dict(row) for row in rows]

        rows = self.session.execute(
            text(
                f"""
                with {_OWNER_CTE}
                select distinct om.owner_ref as value, om.owner_ref as label
                from after_sales_refund_items r
                join owner_map om
                  on om.source_account_ref = r.source_account_ref
                 and om.store_id = r.store_id
                 and om.item_id = r.item_id
                 and om.msku = r.msku
                where {base_sql}
                  and om.owner_ref is not null
                  and btrim(om.owner_ref) <> ''
                order by label
                """
            ),
            params,
        ).mappings().all()
        owners = [dict(row) for row in rows]

        rows = self.session.execute(
            text(
                f"""
                with {_OWNER_CTE}
                select distinct {_REASON_EXPR} as value, {_REASON_EXPR} as label
                from after_sales_refund_items r
                left join owner_map om
                  on om.source_account_ref = r.source_account_ref
                 and om.store_id = r.store_id
                 and om.item_id = r.item_id
                 and om.msku = r.msku
                where {base_sql}
                order by label
                """
            ),
            params,
        ).mappings().all()
        reasons = [dict(row) for row in rows]
        return {
            "stores": stores,
            "owners": owners,
            "reasons": reasons,
            "responsibilities": [{"value": "pending", "label": "pending"}],
        }

    def product_summary(
        self,
        query: RefundBaseQuery,
        account_refs: frozenset[str],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Aggregate refund risk at store_id + item_id + MSKU grain.

        Refund and sales quantities use the exact same user-selected date window.
        SKU remains descriptive metadata and is not used as the sales/refund join key.
        """
        refund_where, params = self._refund_where(query, account_refs)
        refund_where.append(_REFUND_PRODUCT_IDENTITY_READY)
        sales_where, sales_params = self._sales_where(query, account_refs)
        sales_where.append(_SALES_PRODUCT_IDENTITY_READY)
        params.update(
            {
                f"sales_{key}": value
                for key, value in sales_params.items()
                if key != "accounts"
            }
        )
        params["limit"] = limit

        sales_where_sql = []
        for clause in sales_where:
            if clause == "m.source_account_ref = any(:accounts)":
                sales_where_sql.append(clause)
            else:
                sales_where_sql.append(self._prefix_params(clause, "sales_"))

        rows = (
            self.session.execute(
                text(
                    f"""
                    with {_OWNER_CTE},
                    refund_agg as (
                        select
                            {_PRODUCT_KEY_EXPR} as product_key,
                            r.store_id,
                            max({_STORE_NAME_EXPR}) as store_name,
                            r.item_id,
                            r.msku,
                            max(r.local_sku) as local_sku,
                            max({_PRODUCT_NAME_EXPR}) as product_name,
                            max(om.owner_ref) as owner_ref,
                            count(distinct r.return_order_id)::int as refund_orders,
                            coalesce(sum(r.return_qty),0) as refund_qty,
                            coalesce(sum(r.refund_amount),0) as refund_amount,
                            coalesce(sum(r.refund_loss_amount) filter (
                                where r.refund_loss_effective = true
                            ),0) as refund_loss_amount,
                            mode() within group (order by {_REASON_EXPR}) as top_reason
                        from after_sales_refund_items r
                        left join owner_map om
                          on om.source_account_ref = r.source_account_ref
                         and om.store_id = r.store_id
                         and om.item_id = r.item_id
                         and om.msku = r.msku
                        where {" and ".join(refund_where)}
                        group by {_PRODUCT_KEY_EXPR}, r.store_id, r.item_id, r.msku
                    ),
                    sales_agg as (
                        select
                            m.store_id,
                            m.item_id,
                            m.msku,
                            coalesce(sum(m.sales_qty),0) as sales_qty
                        from mart_daily_sales_item_day m
                        where {" and ".join(sales_where_sql)}
                        group by m.store_id, m.item_id, m.msku
                    )
                    select
                        r.*,
                        coalesce(s.sales_qty,0) as sales_qty,
                        case when coalesce(s.sales_qty,0) > 0
                             then r.refund_qty / s.sales_qty * 100 end as refund_rate
                    from refund_agg r
                    left join sales_agg s
                      on s.store_id = r.store_id
                     and s.item_id = r.item_id
                     and s.msku = r.msku
                    order by refund_rate desc nulls last, r.refund_loss_amount desc,
                             r.refund_qty desc, r.item_id, r.msku
                    limit :limit
                    """
                ),
                params,
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def heat_rows(
        self,
        query: RefundBaseQuery,
        account_refs: frozenset[str],
        product_keys: list[str],
    ) -> list[dict[str, Any]]:
        if not product_keys:
            return []
        where, params = self._refund_where(query, account_refs)
        where.append(f"{_PRODUCT_KEY_EXPR} = any(:product_keys)")
        params["product_keys"] = product_keys
        rows = (
            self.session.execute(
                text(
                    f"""
                    with {_OWNER_CTE}
                    select
                        {_PRODUCT_KEY_EXPR} as product_key,
                        r.return_order_at::date as day,
                        coalesce(sum(r.return_qty),0) as refund_qty
                    from after_sales_refund_items r
                    left join owner_map om
                      on om.source_account_ref = r.source_account_ref
                     and om.store_id = r.store_id
                     and om.item_id = r.item_id
                     and om.msku = r.msku
                    where {" and ".join(where)}
                    group by {_PRODUCT_KEY_EXPR}, r.return_order_at::date
                    order by product_key, day
                    """
                ),
                params,
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def lag_analysis(
        self,
        query: RefundBaseQuery,
        account_refs: frozenset[str],
        product_key: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        where, params = self._refund_where(query, account_refs)
        where.append(f"{_PRODUCT_KEY_EXPR} = :product_key")
        params["product_key"] = product_key
        where_sql = " and ".join(where)
        common = f"""
            with {_OWNER_CTE},
            scoped as (
                select
                    r.*,
                    case
                        when r.purchase_time_at is not null
                         and r.return_order_at is not null
                         and r.return_order_at >= r.purchase_time_at
                        then extract(epoch from (r.return_order_at - r.purchase_time_at)) / 86400.0
                    end as lag_days
                from after_sales_refund_items r
                left join owner_map om
                  on om.source_account_ref = r.source_account_ref
                 and om.store_id = r.store_id
                 and om.item_id = r.item_id
                 and om.msku = r.msku
                where {where_sql}
            )
        """
        summary = self.session.execute(
            text(
                common
                + """
                select
                    avg(lag_days) filter (where lag_days is not null) as average_days,
                    percentile_cont(0.5) within group (order by lag_days)
                        filter (where lag_days is not null) as median_days,
                    count(*) filter (where lag_days is not null)::int as eligible_item_rows,
                    count(*) filter (where lag_days is null)::int as missing_time_rows
                from scoped
                """
            ),
            params,
        ).mappings().one()

        buckets = (
            self.session.execute(
                text(
                    common
                    + """
                    select
                        case
                            when lag_days < 4 then '0_3'
                            when lag_days < 8 then '4_7'
                            when lag_days < 15 then '8_14'
                            when lag_days < 31 then '15_30'
                            else '31_plus'
                        end as bucket_key,
                        count(distinct return_order_id)::int as refund_orders,
                        coalesce(sum(return_qty),0) as refund_qty,
                        coalesce(sum(refund_amount),0) as refund_amount,
                        coalesce(sum(refund_loss_amount) filter (
                            where refund_loss_effective = true
                        ),0) as refund_loss_amount
                    from scoped
                    where lag_days is not null
                    group by bucket_key
                    """
                ),
                params,
            )
            .mappings()
            .all()
        )
        return dict(summary), [dict(row) for row in buckets]

    def list_items(
        self,
        query: RefundItemQuery,
        account_refs: frozenset[str],
    ) -> tuple[list[dict[str, Any]], int, Any]:
        where, params = self._refund_where(query, account_refs)
        where_sql = " and ".join(where)
        total = int(
            self.session.execute(
                text(
                    f"""
                    with {_OWNER_CTE}
                    select count(*)
                    from after_sales_refund_items r
                    left join owner_map om
                      on om.source_account_ref = r.source_account_ref
                     and om.store_id = r.store_id
                     and om.item_id = r.item_id
                     and om.msku = r.msku
                    where {where_sql}
                    """
                ),
                params,
            ).scalar_one()
        )
        sort_col = _SORT_COLUMNS[query.sort_by]
        sort_dir = "asc" if query.sort_order == "asc" else "desc"
        params.update({"limit": query.page_size, "offset": (query.page - 1) * query.page_size})
        rows = (
            self.session.execute(
                text(
                    f"""
                    with {_OWNER_CTE}
                    select
                        r.id::text as id,
                        r.store_id,
                        {_STORE_NAME_EXPR} as store_name,
                        om.owner_ref,
                        r.item_id,
                        {_PRODUCT_NAME_EXPR} as product_name,
                        r.local_sku,
                        r.msku,
                        r.return_order_id,
                        r.customer_order_id,
                        r.purchase_order_id,
                        coalesce(nullif(r.purchase_order_id,''),
                                 nullif(r.customer_order_id,''),
                                 r.return_order_id) as platform_order_id,
                        r.purchase_time_at,
                        r.return_order_at as refund_time_at,
                        case
                            when r.purchase_time_at is not null
                             and r.return_order_at is not null
                             and r.return_order_at >= r.purchase_time_at
                            then extract(epoch from (r.return_order_at-r.purchase_time_at))/86400.0
                        end as refund_lag_days,
                        r.return_qty,
                        r.refund_amount,
                        r.refund_currency_code,
                        r.refund_loss_amount,
                        r.return_reason_code,
                        r.return_description,
                        {_REASON_EXPR} as return_reason,
                        null::text as responsibility,
                        r.current_refund_status,
                        r.refund_completed
                    from after_sales_refund_items r
                    left join owner_map om
                      on om.source_account_ref = r.source_account_ref
                     and om.store_id = r.store_id
                     and om.item_id = r.item_id
                     and om.msku = r.msku
                    where {where_sql}
                    order by {sort_col} {sort_dir} nulls last, r.id
                    limit :limit offset :offset
                    """
                ),
                params,
            )
            .mappings()
            .all()
        )
        latest = self.latest_updated_at(
            query,
            account_refs,
        )
        return [dict(row) for row in rows], total, latest

    def latest_updated_at(
        self,
        query: RefundBaseQuery,
        account_refs: frozenset[str],
    ) -> Any:
        where, params = self._refund_where(query, account_refs)
        return self.session.execute(
            text(
                f"""
                with {_OWNER_CTE}
                select max(r.updated_at)
                from after_sales_refund_items r
                left join owner_map om
                  on om.source_account_ref = r.source_account_ref
                 and om.store_id = r.store_id
                 and om.item_id = r.item_id
                 and om.msku = r.msku
                where {" and ".join(where)}
                """
            ),
            params,
        ).scalar_one()

    def _refund_where(
        self,
        query: RefundBaseQuery,
        account_refs: frozenset[str],
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        include_facets: bool = True,
        include_search: bool = True,
    ) -> tuple[list[str], dict[str, object]]:
        start = start_date or query.start_date
        end = end_date or query.end_date
        where = [
            "r.source_account_ref = any(:accounts)",
            "r.platform_code = 'walmart'",
            "r.return_order_at is not null",
            "r.return_order_at::date between :start_date and :end_date",
        ]
        params: dict[str, object] = {
            "accounts": list(account_refs),
            "start_date": start,
            "end_date": end,
        }
        if include_facets:
            stores = split_csv(query.store_id)
            if stores:
                where.append("r.store_id = any(:store_ids)")
                params["store_ids"] = stores
            owners = split_csv(query.owner_ref)
            if owners:
                where.append("om.owner_ref = any(:owner_refs)")
                params["owner_refs"] = owners
            reasons = split_csv(query.reason)
            if reasons:
                where.append(f"{_REASON_EXPR} = any(:reasons)")
                params["reasons"] = reasons
            responsibilities = split_csv(query.responsibility)
            if responsibilities and "pending" not in responsibilities:
                where.append("false")
        if query.product_key:
            where.append(f"{_PRODUCT_KEY_EXPR} = :product_key")
            params["product_key"] = query.product_key
        if include_search:
            self._append_refund_search(where, params, query)
        return where, params

    def _sales_where(
        self,
        query: RefundBaseQuery,
        account_refs: frozenset[str],
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        product_key: str | None = None,
    ) -> tuple[list[str], dict[str, object]]:
        start = start_date or query.start_date
        end = end_date or query.end_date
        where = [
            "m.source_account_ref = any(:accounts)",
            "m.business_date_la between :start_date and :end_date",
        ]
        params: dict[str, object] = {
            "accounts": list(account_refs),
            "start_date": start,
            "end_date": end,
        }
        stores = split_csv(query.store_id)
        if stores:
            where.append("m.store_id = any(:store_ids)")
            params["store_ids"] = stores
        owners = split_csv(query.owner_ref)
        if owners:
            where.append("m.owner_ref = any(:owner_refs)")
            params["owner_refs"] = owners
        if product_key:
            where.append(f"{_SALES_PRODUCT_KEY_EXPR} = :product_key")
            params["product_key"] = product_key
        elif query.product_key:
            where.append(f"{_SALES_PRODUCT_KEY_EXPR} = :product_key")
            params["product_key"] = query.product_key
        elif query.search_field in _SALES_SEARCH_COLUMNS:
            column = _SALES_SEARCH_COLUMNS[query.search_field]
            if query.keyword:
                where.append(f"coalesce({column},'') ilike :keyword")
                params["keyword"] = f"%{query.keyword}%"
            batch_values = split_csv(query.batch_values)
            if batch_values:
                where.append(f"lower(coalesce({column},'')) = any(:batch_values)")
                params["batch_values"] = [value.lower() for value in batch_values]
        return where, params

    def _append_refund_search(
        self,
        where: list[str],
        params: dict[str, object],
        query: RefundBaseQuery,
    ) -> None:
        column = _SEARCH_COLUMNS[query.search_field]
        if query.keyword:
            where.append(f"coalesce({column},'') ilike :keyword")
            params["keyword"] = f"%{query.keyword}%"
        batch_values = split_csv(query.batch_values)
        if batch_values:
            where.append(f"lower(coalesce({column},'')) = any(:batch_values)")
            params["batch_values"] = [value.lower() for value in batch_values]

    @staticmethod
    def _prefix_params(clause: str, prefix: str) -> str:
        for name in (
            "start_date",
            "end_date",
            "store_ids",
            "owner_refs",
            "keyword",
            "batch_values",
            "product_key",
        ):
            clause = clause.replace(f":{name}", f":{prefix}{name}")
        return clause

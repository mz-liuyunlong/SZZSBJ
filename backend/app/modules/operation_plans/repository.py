from __future__ import annotations

# ruff: noqa: E501
import json
from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from app.modules.operation_plans.schemas import OperationPlanProductQuery

LISTING_TABLE = "mart_listing_management_current"
DAILY_SALES_TABLE = "mart_daily_sales_item_day"
INVENTORY_TABLE = "fact_walmart_listing_inventory_daily"


class OperationPlanRepository:
    """SQL repository for operation plan writes and BFF reads.

    The module uses SQLAlchemy Core statements because the page joins several MART/DIM
    objects whose schemas can evolve. Explicit SQL keeps the page contract stable and
    makes import validation fail closed when Listing Management cannot provide identity.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def table_exists(self, table_name: str) -> bool:
        result = self.session.execute(
            text("select to_regclass(:table_name) is not null"), {"table_name": table_name}
        ).scalar_one()
        return bool(result)

    def table_columns(self, table_name: str) -> set[str]:
        rows = self.session.execute(
            text(
                """
                select column_name
                from information_schema.columns
                where table_schema = current_schema()
                  and table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).scalars()
        return {str(row) for row in rows}

    def get_or_create_period(
        self,
        *,
        period_id: UUID,
        platform_code: str,
        period_type: str,
        period_key: str,
        start_date: date,
        end_date: date,
        actor_ref: str,
    ) -> UUID:
        existing = self.session.execute(
            text(
                """
                select id
                from ops_operation_plan_periods
                where platform_code = :platform_code
                  and period_type = :period_type
                  and period_key = :period_key
                """
            ),
            {
                "platform_code": platform_code,
                "period_type": period_type,
                "period_key": period_key,
            },
        ).scalar_one_or_none()
        if existing is not None:
            return UUID(str(existing))

        self.session.execute(
            text(
                """
                insert into ops_operation_plan_periods (
                    id, platform_code, period_type, period_key,
                    period_start_date, period_end_date, status, created_by
                ) values (
                    :id, :platform_code, :period_type, :period_key,
                    :start_date, :end_date, 'active', :actor_ref
                )
                """
            ),
            {
                "id": period_id,
                "platform_code": platform_code,
                "period_type": period_type,
                "period_key": period_key,
                "start_date": start_date,
                "end_date": end_date,
                "actor_ref": actor_ref,
            },
        )
        return period_id

    def find_period_id(
        self, *, platform_code: str, period_type: str, period_key: str
    ) -> UUID | None:
        value = self.session.execute(
            text(
                """
                select id
                from ops_operation_plan_periods
                where platform_code = :platform_code
                  and period_type = :period_type
                  and period_key = :period_key
                """
            ),
            {"platform_code": platform_code, "period_type": period_type, "period_key": period_key},
        ).scalar_one_or_none()
        return UUID(str(value)) if value is not None else None

    def create_import_batch(
        self,
        *,
        batch_id: UUID,
        period_id: UUID,
        file_name: str,
        file_sha256: str,
        file_size: int,
        conflict_policy: str,
        actor_ref: str,
    ) -> None:
        self.session.execute(
            text(
                """
                insert into ops_operation_plan_import_batches (
                    id, period_id, file_name, file_sha256, file_size,
                    status, conflict_policy, created_by
                ) values (
                    :id, :period_id, :file_name, :file_sha256, :file_size,
                    'processing', :conflict_policy, :actor_ref
                )
                """
            ),
            {
                "id": batch_id,
                "period_id": period_id,
                "file_name": file_name,
                "file_sha256": file_sha256,
                "file_size": file_size,
                "conflict_policy": conflict_policy,
                "actor_ref": actor_ref,
            },
        )

    def update_import_batch_counts(
        self,
        *,
        batch_id: UUID,
        status: str,
        row_count: int,
        success_count: int,
        failed_count: int,
        warning_count: int,
        existing_count: int,
        created_plan_count: int,
        updated_plan_count: int,
        skipped_count: int,
    ) -> None:
        self.session.execute(
            text(
                """
                update ops_operation_plan_import_batches
                set status = :status,
                    row_count = :row_count,
                    success_count = :success_count,
                    failed_count = :failed_count,
                    warning_count = :warning_count,
                    existing_count = :existing_count,
                    created_plan_count = :created_plan_count,
                    updated_plan_count = :updated_plan_count,
                    skipped_count = :skipped_count,
                    validated_at = now(),
                    imported_at = now()
                where id = :batch_id
                """
            ),
            {
                "batch_id": batch_id,
                "status": status,
                "row_count": row_count,
                "success_count": success_count,
                "failed_count": failed_count,
                "warning_count": warning_count,
                "existing_count": existing_count,
                "created_plan_count": created_plan_count,
                "updated_plan_count": updated_plan_count,
                "skipped_count": skipped_count,
            },
        )

    def resolve_listing_by_item_msku(
        self,
        *,
        item_id: str,
        msku: str,
        account_refs: frozenset[str],
    ) -> list[RowMapping]:
        if not self.table_exists(LISTING_TABLE):
            return []
        columns = self.table_columns(LISTING_TABLE)
        required = {"item_id", "msku"}
        if not required.issubset(columns):
            return []

        def column_or_null(column: str, alias: str, candidates: Iterable[str] | None = None) -> str:
            names = [column, *(candidates or [])]
            for name in names:
                if name in columns:
                    return f"{name} as {alias}"
            return f"null as {alias}"

        source_account_clause = ""
        params: dict[str, Any] = {"item_id": item_id, "msku": msku}
        if "source_account_ref" in columns:
            source_account_clause = "and source_account_ref in :account_refs"
            params["account_refs"] = tuple(sorted(account_refs))
        else:
            params["account_refs"] = tuple(sorted(account_refs))

        statement = text(
            f"""
            select
                {column_or_null("platform_code", "platform_code")} ,
                {column_or_null("source_account_ref", "source_account_ref")} ,
                {column_or_null("store_id", "store_id")} ,
                {column_or_null("store_name", "store_name")} ,
                item_id as item_id,
                {column_or_null("sku", "sku", ["local_sku"])} ,
                msku as msku,
                {column_or_null("product_name", "product_name", ["local_name", "title", "product_title", "product_name_snapshot", "item_name", "name"])} ,
                {column_or_null("owner_ref", "owner_ref", ["owner_uid"])} ,
                {column_or_null("owner_name", "owner_name", ["owner_name_snapshot"])}
            from {LISTING_TABLE}
            where trim(item_id::text) = :item_id
              and trim(msku::text) = :msku
              {source_account_clause}
            limit 3
            """
        )
        if source_account_clause:
            statement = statement.bindparams(bindparam("account_refs", expanding=True))
        return list(self.session.execute(statement, params).mappings())

    def get_existing_plan(
        self,
        *,
        period_id: UUID,
        platform_code: str,
        source_account_ref: str,
        item_id: str,
        msku: str,
    ) -> RowMapping | None:
        return (
            self.session.execute(
                text(
                    """
                select *
                from ops_operation_product_plans
                where period_id = :period_id
                  and platform_code = :platform_code
                  and source_account_ref = :source_account_ref
                  and item_id = :item_id
                  and msku = :msku
                """
                ),
                {
                    "period_id": period_id,
                    "platform_code": platform_code,
                    "source_account_ref": source_account_ref,
                    "item_id": item_id,
                    "msku": msku,
                },
            )
            .mappings()
            .first()
        )

    def insert_plan(
        self,
        *,
        plan_id: UUID,
        period_id: UUID,
        listing: Mapping[str, Any],
        target_sales_amount: Decimal,
        target_gross_profit_amount: Decimal,
        remark: str | None,
        import_batch_id: UUID | None,
        actor_ref: str,
    ) -> None:
        self.session.execute(
            text(
                """
                insert into ops_operation_product_plans (
                    id, period_id, platform_code, source_account_ref, store_id,
                    store_name_snapshot, item_id, sku, msku, product_name_snapshot,
                    owner_ref, owner_name_snapshot, target_sales_amount,
                    target_gross_profit_amount, currency_code, operation_status,
                    plan_status, stock_status, remark, source_type, import_batch_id,
                    adjusted, created_by, updated_by
                ) values (
                    :id, :period_id, :platform_code, :source_account_ref, :store_id,
                    :store_name_snapshot, :item_id, :sku, :msku, :product_name_snapshot,
                    :owner_ref, :owner_name_snapshot, :target_sales_amount,
                    :target_gross_profit_amount, 'USD', 'normal', 'normal', 'normal',
                    :remark, 'import', :import_batch_id, false, :actor_ref, :actor_ref
                )
                """
            ),
            self._plan_params(
                plan_id=plan_id,
                period_id=period_id,
                listing=listing,
                target_sales_amount=target_sales_amount,
                target_gross_profit_amount=target_gross_profit_amount,
                remark=remark,
                import_batch_id=import_batch_id,
                actor_ref=actor_ref,
            ),
        )

    def update_plan_targets(
        self,
        *,
        plan_id: UUID,
        target_sales_amount: Decimal,
        target_gross_profit_amount: Decimal,
        remark: str | None,
        actor_ref: str,
    ) -> None:
        self.session.execute(
            text(
                """
                update ops_operation_product_plans
                set target_sales_amount = :target_sales_amount,
                    target_gross_profit_amount = :target_gross_profit_amount,
                    remark = coalesce(:remark, remark),
                    adjusted = true,
                    plan_status = case when operation_status = 'clearance' then 'clearance' else 'normal' end,
                    updated_by = :actor_ref,
                    updated_at = now()
                where id = :plan_id
                """
            ),
            {
                "plan_id": plan_id,
                "target_sales_amount": target_sales_amount,
                "target_gross_profit_amount": target_gross_profit_amount,
                "remark": remark,
                "actor_ref": actor_ref,
            },
        )

    def mark_plan_clearance(self, *, plan_id: UUID, actor_ref: str) -> None:
        self.session.execute(
            text(
                """
                update ops_operation_product_plans
                set operation_status = 'clearance',
                    plan_status = 'clearance',
                    adjusted = true,
                    updated_by = :actor_ref,
                    updated_at = now()
                where id = :plan_id
                """
            ),
            {"plan_id": plan_id, "actor_ref": actor_ref},
        )

    def _plan_params(
        self,
        *,
        plan_id: UUID,
        period_id: UUID,
        listing: Mapping[str, Any],
        target_sales_amount: Decimal,
        target_gross_profit_amount: Decimal,
        remark: str | None,
        import_batch_id: UUID | None,
        actor_ref: str,
    ) -> dict[str, Any]:
        return {
            "id": plan_id,
            "period_id": period_id,
            "platform_code": str(listing.get("platform_code") or "walmart"),
            "source_account_ref": str(listing.get("source_account_ref") or "unknown"),
            "store_id": listing.get("store_id"),
            "store_name_snapshot": listing.get("store_name"),
            "item_id": str(listing.get("item_id") or ""),
            "sku": listing.get("sku"),
            "msku": str(listing.get("msku") or ""),
            "product_name_snapshot": listing.get("product_name"),
            "owner_ref": listing.get("owner_ref"),
            "owner_name_snapshot": listing.get("owner_name"),
            "target_sales_amount": target_sales_amount,
            "target_gross_profit_amount": target_gross_profit_amount,
            "remark": remark,
            "import_batch_id": import_batch_id,
            "actor_ref": actor_ref,
        }

    def insert_import_row(
        self,
        *,
        row_id: UUID,
        batch_id: UUID,
        row_number: int,
        raw: Mapping[str, str],
        target_sales_amount: Decimal | None,
        target_gross_profit_amount: Decimal | None,
        import_status: str,
        listing: Mapping[str, Any] | None,
        imported_plan_id: UUID | None,
        error_code: str | None,
        error_message: str | None,
        suggestion: str | None,
        validation_errors: list[str],
        validation_warnings: list[str],
    ) -> None:
        self.session.execute(
            text(
                """
                insert into ops_operation_plan_import_rows (
                    id, batch_id, row_number, item_id_raw, msku_raw,
                    target_sales_raw, target_gross_profit_raw, remark_raw,
                    resolved_source_account_ref, resolved_store_id, resolved_store_name,
                    resolved_item_id, resolved_sku, resolved_msku, resolved_product_name,
                    resolved_owner_ref, resolved_owner_name, target_sales_amount,
                    target_gross_profit_amount, import_status, imported_plan_id,
                    error_code, error_message, suggestion,
                    validation_errors, validation_warnings
                ) values (
                    :id, :batch_id, :row_number, :item_id_raw, :msku_raw,
                    :target_sales_raw, :target_gross_profit_raw, :remark_raw,
                    :resolved_source_account_ref, :resolved_store_id, :resolved_store_name,
                    :resolved_item_id, :resolved_sku, :resolved_msku, :resolved_product_name,
                    :resolved_owner_ref, :resolved_owner_name, :target_sales_amount,
                    :target_gross_profit_amount, :import_status, :imported_plan_id,
                    :error_code, :error_message, :suggestion,
                    cast(:validation_errors as jsonb), cast(:validation_warnings as jsonb)
                )
                """
            ),
            {
                "id": row_id,
                "batch_id": batch_id,
                "row_number": row_number,
                "item_id_raw": raw.get("item_id"),
                "msku_raw": raw.get("msku"),
                "target_sales_raw": raw.get("sales"),
                "target_gross_profit_raw": raw.get("profit"),
                "remark_raw": raw.get("remark"),
                "resolved_source_account_ref": listing.get("source_account_ref")
                if listing
                else None,
                "resolved_store_id": listing.get("store_id") if listing else None,
                "resolved_store_name": listing.get("store_name") if listing else None,
                "resolved_item_id": listing.get("item_id") if listing else None,
                "resolved_sku": listing.get("sku") if listing else None,
                "resolved_msku": listing.get("msku") if listing else None,
                "resolved_product_name": listing.get("product_name") if listing else None,
                "resolved_owner_ref": listing.get("owner_ref") if listing else None,
                "resolved_owner_name": listing.get("owner_name") if listing else None,
                "target_sales_amount": target_sales_amount,
                "target_gross_profit_amount": target_gross_profit_amount,
                "import_status": import_status,
                "imported_plan_id": imported_plan_id,
                "error_code": error_code,
                "error_message": error_message,
                "suggestion": suggestion,
                "validation_errors": _json_dumps(validation_errors),
                "validation_warnings": _json_dumps(validation_warnings),
            },
        )

    def insert_event(
        self,
        *,
        event_id: UUID,
        plan_id: UUID,
        event_type: str,
        before_data: Mapping[str, Any] | None,
        after_data: Mapping[str, Any] | None,
        reason: str | None,
        actor_ref: str,
        request_id: str | None,
    ) -> None:
        self.session.execute(
            text(
                """
                insert into ops_operation_plan_events (
                    id, product_plan_id, event_type, before_data, after_data,
                    reason, actor_ref, request_id
                ) values (
                    :id, :plan_id, :event_type, cast(:before_data as jsonb), cast(:after_data as jsonb),
                    :reason, :actor_ref, :request_id
                )
                """
            ),
            {
                "id": event_id,
                "plan_id": plan_id,
                "event_type": event_type,
                "before_data": _json_dumps(before_data) if before_data is not None else None,
                "after_data": _json_dumps(after_data) if after_data is not None else None,
                "reason": reason,
                "actor_ref": actor_ref,
                "request_id": request_id,
            },
        )

    def get_plan(self, plan_id: UUID) -> RowMapping | None:
        return (
            self.session.execute(
                text("select * from ops_operation_product_plans where id = :plan_id"),
                {"plan_id": plan_id},
            )
            .mappings()
            .first()
        )

    def list_products(
        self,
        *,
        period_id: UUID,
        query: OperationPlanProductQuery,
        account_refs: frozenset[str],
    ) -> tuple[list[RowMapping], int]:
        clauses = ["p.period_id = :period_id", "p.source_account_ref in :account_refs"]
        params: dict[str, Any] = {
            "period_id": period_id,
            "account_refs": tuple(sorted(account_refs)),
            "limit": query.page_size,
            "offset": (query.page - 1) * query.page_size,
        }
        owner_expr = (
            "coalesce("
            "nullif(p.owner_ref, ''), "
            "nullif(p.owner_name_snapshot, ''), "
            "nullif(a.actual_owner_ref, ''), "
            "''"
            ")"
        )

        if query.owner_ref:
            clauses.append(f"{owner_expr} = :owner_ref")
            params["owner_ref"] = query.owner_ref
        if query.store_id:
            clauses.append("p.store_id = :store_id")
            params["store_id"] = query.store_id
        if query.operation_status:
            clauses.append("p.operation_status = :operation_status")
            params["operation_status"] = query.operation_status
        if query.plan_status:
            clauses.append("p.plan_status = :plan_status")
            params["plan_status"] = query.plan_status
        if query.stock_status:
            if query.stock_status == "risk":
                clauses.append(
                    """
                    (
                        p.stock_status = :stock_status
                        or (
                            coalesce(p.target_sales_amount, 0)
                                > coalesce(a.sales_actual_amount, 0)
                            and coalesce(a.sales_actual_amount, 0) > 0
                            and coalesce(a.sales_actual_qty, 0) > 0
                            and (
                                coalesce(a.wfs_available_qty, 0)
                                / greatest(
                                    (
                                        coalesce(p.target_sales_amount, 0)
                                        - coalesce(a.sales_actual_amount, 0)
                                    )
                                    / greatest(
                                        coalesce(a.sales_actual_amount, 0)
                                        / greatest(coalesce(a.sales_actual_qty, 0), 1),
                                        0.01
                                    ),
                                    1
                                )
                                * 100
                            ) < 100
                        )
                    )
                    """
                )
            else:
                clauses.append("p.stock_status = :stock_status")
            params["stock_status"] = query.stock_status
        if query.keyword:
            column_map = {
                "item_id": "p.item_id",
                "sku": "p.sku",
                "msku": "p.msku",
                "product_name": "p.product_name_snapshot",
            }
            clauses.append(f"coalesce({column_map[query.search_field]}, '') ilike :keyword")
            params["keyword"] = f"%{query.keyword.strip()}%"
        if query.batch_values:
            column_map = {
                "item_id": "p.item_id",
                "sku": "p.sku",
                "msku": "p.msku",
                "product_name": "p.product_name_snapshot",
            }
            clauses.append(f"coalesce({column_map[query.search_field]}, '') in :batch_values")
            params["batch_values"] = tuple(query.batch_values)

        where_sql = " and ".join(clauses)

        actuals_cte = """
            with period_bounds as (
                select
                    period_start_date,
                    period_end_date,
                    (
                        select max(d.business_date_la)
                        from mart_daily_sales_item_day d
                        where d.source_account_ref in :account_refs
                          and d.business_date_la >= p0.period_start_date
                          and d.business_date_la <= p0.period_end_date
                    ) as data_end_date
                from ops_operation_plan_periods p0
                where p0.id = :period_id
            ),
            actuals as (
                select
                    p.id as plan_id,
                    sum(coalesce(d.sales_amount, 0)) as sales_actual_amount,
                    sum(coalesce(d.sales_qty, 0)) as sales_actual_qty,
                    sum(coalesce(d.gross_profit_amount, 0)) as gross_profit_actual_amount,
                    sum(coalesce(d.sales_amount, 0)) filter (
                        where d.business_date_la >= greatest(
                            b.period_start_date,
                            b.data_end_date - 6
                        )
                    ) as recent7_sales_amount,
                    sum(coalesce(d.gross_profit_amount, 0)) filter (
                        where d.business_date_la >= greatest(
                            b.period_start_date,
                            b.data_end_date - 6
                        )
                    ) as recent7_gross_profit_amount,
                    sum(coalesce(d.sales_amount, 0)) filter (
                        where d.business_date_la >= greatest(
                            b.period_start_date,
                            b.data_end_date - 13
                        )
                    ) as recent14_sales_amount,
                    sum(coalesce(d.gross_profit_amount, 0)) filter (
                        where d.business_date_la >= greatest(
                            b.period_start_date,
                            b.data_end_date - 13
                        )
                    ) as recent14_gross_profit_amount,
                    max(b.period_start_date) as period_start_date,
                    max(b.period_end_date) as period_end_date,
                    max(b.data_end_date) as data_end_date,
                    max(nullif(d.owner_ref, '')) as actual_owner_ref,
                    max(nullif(d.local_name, '')) as actual_local_name,
                    max(nullif(d.title, '')) as actual_title,
                    max(coalesce(d.wfs_available_quantity, 0)) as wfs_available_qty
                from ops_operation_product_plans p
                join period_bounds b on true
                left join mart_daily_sales_item_day d
                  on trim(d.item_id::text) = trim(p.item_id::text)
                 and trim(d.msku::text) = trim(p.msku::text)
                 and d.source_account_ref = p.source_account_ref
                 and d.business_date_la >= b.period_start_date
                 and d.business_date_la <= b.period_end_date
                where p.period_id = :period_id
                  and p.source_account_ref in :account_refs
                group by p.id
            ),
            last_actuals as (
                select
                    p.id as plan_id,
                    sum(coalesce(d.sales_amount, 0)) as last_sales_amount,
                    sum(coalesce(d.gross_profit_amount, 0)) as last_gross_profit_amount
                from ops_operation_product_plans p
                join period_bounds b on true
                left join mart_daily_sales_item_day d
                  on trim(d.item_id::text) = trim(p.item_id::text)
                 and trim(d.msku::text) = trim(p.msku::text)
                 and d.source_account_ref = p.source_account_ref
                 and d.business_date_la >= (
                     b.period_start_date - (b.period_end_date - b.period_start_date + 1)
                 )
                 and d.business_date_la < b.period_start_date
                where p.period_id = :period_id
                  and p.source_account_ref in :account_refs
                group by p.id
            )
        """

        base_from = """
            from ops_operation_product_plans p
            left join actuals a on a.plan_id = p.id
            left join last_actuals la on la.plan_id = p.id
        """
        where_clause = f"where {where_sql}"

        count_statement = text(
            f"{actuals_cte} select count(*) {base_from} {where_clause}"
        ).bindparams(bindparam("account_refs", expanding=True))
        if query.batch_values:
            count_statement = count_statement.bindparams(bindparam("batch_values", expanding=True))

        total = int(self.session.execute(count_statement, params).scalar_one())

        forecast_sales_sql = """
            coalesce(
                case
                    when a.data_end_date is not null then
                        coalesce(a.sales_actual_amount, 0)
                        + (
                            (
                                coalesce(a.recent7_sales_amount, 0)
                                / greatest(
                                    a.data_end_date
                                    - greatest(a.period_start_date, a.data_end_date - 6)
                                    + 1,
                                    1
                                )
                                * 0.7
                            )
                            + (
                                coalesce(a.recent14_sales_amount, 0)
                                / greatest(
                                    a.data_end_date
                                    - greatest(a.period_start_date, a.data_end_date - 13)
                                    + 1,
                                    1
                                )
                                * 0.3
                            )
                        )
                        * greatest((a.period_end_date - a.data_end_date), 0)
                    else coalesce(a.sales_actual_amount, 0)
                end,
                0
            )::numeric
        """

        forecast_profit_sql = """
            coalesce(
                case
                    when a.data_end_date is not null then
                        coalesce(a.gross_profit_actual_amount, 0)
                        + (
                            (
                                coalesce(a.recent7_gross_profit_amount, 0)
                                / greatest(
                                    a.data_end_date
                                    - greatest(a.period_start_date, a.data_end_date - 6)
                                    + 1,
                                    1
                                )
                                * 0.7
                            )
                            + (
                                coalesce(a.recent14_gross_profit_amount, 0)
                                / greatest(
                                    a.data_end_date
                                    - greatest(a.period_start_date, a.data_end_date - 13)
                                    + 1,
                                    1
                                )
                                * 0.3
                            )
                        )
                        * greatest((a.period_end_date - a.data_end_date), 0)
                    else coalesce(a.gross_profit_actual_amount, 0)
                end,
                0
            )::numeric
        """

        data_statement = text(
            f"""
            {actuals_cte}
            select
                p.*,
                coalesce(
                    p.product_name_snapshot,
                    a.actual_local_name,
                    a.actual_title
                ) as resolved_product_name,
                coalesce(
                    nullif(p.owner_ref, ''),
                    nullif(p.owner_name_snapshot, ''),
                    nullif(a.actual_owner_ref, '')
                ) as resolved_owner_ref,
                coalesce(
                    nullif(p.owner_name_snapshot, ''),
                    nullif(p.owner_ref, ''),
                    nullif(a.actual_owner_ref, '')
                ) as resolved_owner_name,
                coalesce(la.last_sales_amount, 0)::numeric as last_sales_amount,
                coalesce(la.last_gross_profit_amount, 0)::numeric
                    as last_gross_profit_amount,
                coalesce(a.sales_actual_amount, 0)::numeric as sales_actual_amount,
                coalesce(a.sales_actual_qty, 0)::numeric as sales_actual_qty,
                coalesce(a.gross_profit_actual_amount, 0)::numeric
                    as gross_profit_actual_amount,
                {forecast_sales_sql} as sales_forecast_amount,
                {forecast_profit_sql} as gross_profit_forecast_amount,
                coalesce(a.wfs_available_qty, 0)::numeric as wfs_available_qty,
                0::numeric as inbound_qty,
                0::numeric as arriving_qty,
                coalesce(e.event_count, 0) as event_count
            {base_from}
            left join (
                select product_plan_id, count(*)::int as event_count
                from ops_operation_plan_events
                group by product_plan_id
            ) e on e.product_plan_id = p.id
            {where_clause}
            order by p.updated_at desc, p.created_at desc
            limit :limit offset :offset
            """
        ).bindparams(bindparam("account_refs", expanding=True))

        if query.batch_values:
            data_statement = data_statement.bindparams(bindparam("batch_values", expanding=True))

        rows = list(self.session.execute(data_statement, params).mappings())
        return rows, total

    def summary(self, *, period_id: UUID, account_refs: frozenset[str]) -> RowMapping:
        statement = text(
            """
            with period_bounds as (
                select
                    period_start_date,
                    period_end_date,
                    (
                        select max(d.business_date_la)
                        from mart_daily_sales_item_day d
                        where d.source_account_ref in :account_refs
                          and d.business_date_la >= p0.period_start_date
                          and d.business_date_la <= p0.period_end_date
                    ) as data_end_date
                from ops_operation_plan_periods p0
                where p0.id = :period_id
            ),
            plan_actuals as (
                select
                    p.id as plan_id,
                    sum(coalesce(d.sales_amount, 0)) as sales_actual_amount,
                    sum(coalesce(d.gross_profit_amount, 0)) as gross_profit_actual_amount,
                    sum(coalesce(d.sales_amount, 0)) filter (
                        where d.business_date_la >= greatest(
                            b.period_start_date,
                            b.data_end_date - 6
                        )
                    ) as recent7_sales_amount,
                    sum(coalesce(d.gross_profit_amount, 0)) filter (
                        where d.business_date_la >= greatest(
                            b.period_start_date,
                            b.data_end_date - 6
                        )
                    ) as recent7_gross_profit_amount,
                    sum(coalesce(d.sales_amount, 0)) filter (
                        where d.business_date_la >= greatest(
                            b.period_start_date,
                            b.data_end_date - 13
                        )
                    ) as recent14_sales_amount,
                    sum(coalesce(d.gross_profit_amount, 0)) filter (
                        where d.business_date_la >= greatest(
                            b.period_start_date,
                            b.data_end_date - 13
                        )
                    ) as recent14_gross_profit_amount,
                    max(b.period_start_date) as period_start_date,
                    max(b.period_end_date) as period_end_date,
                    max(b.data_end_date) as data_end_date
                from ops_operation_product_plans p
                join period_bounds b on true
                left join mart_daily_sales_item_day d
                  on trim(d.item_id::text) = trim(p.item_id::text)
                 and trim(d.msku::text) = trim(p.msku::text)
                 and d.source_account_ref = p.source_account_ref
                 and d.business_date_la >= b.period_start_date
                 and d.business_date_la <= b.period_end_date
                where p.period_id = :period_id
                  and p.source_account_ref in :account_refs
                group by p.id
            ),
            plan_forecast as (
                select
                    plan_id,
                    sales_actual_amount,
                    gross_profit_actual_amount,
                    coalesce(
                        case
                            when data_end_date is not null then
                                coalesce(sales_actual_amount, 0)
                                + (
                                    (
                                        coalesce(recent7_sales_amount, 0)
                                        / greatest(
                                            data_end_date
                                            - greatest(period_start_date, data_end_date - 6)
                                            + 1,
                                            1
                                        )
                                        * 0.7
                                    )
                                    + (
                                        coalesce(recent14_sales_amount, 0)
                                        / greatest(
                                            data_end_date
                                            - greatest(period_start_date, data_end_date - 13)
                                            + 1,
                                            1
                                        )
                                        * 0.3
                                    )
                                )
                                * greatest((period_end_date - data_end_date), 0)
                            else coalesce(sales_actual_amount, 0)
                        end,
                        0
                    )::numeric as sales_forecast_amount,
                    coalesce(
                        case
                            when data_end_date is not null then
                                coalesce(gross_profit_actual_amount, 0)
                                + (
                                    (
                                        coalesce(recent7_gross_profit_amount, 0)
                                        / greatest(
                                            data_end_date
                                            - greatest(period_start_date, data_end_date - 6)
                                            + 1,
                                            1
                                        )
                                        * 0.7
                                    )
                                    + (
                                        coalesce(recent14_gross_profit_amount, 0)
                                        / greatest(
                                            data_end_date
                                            - greatest(period_start_date, data_end_date - 13)
                                            + 1,
                                            1
                                        )
                                        * 0.3
                                    )
                                )
                                * greatest((period_end_date - data_end_date), 0)
                            else coalesce(gross_profit_actual_amount, 0)
                        end,
                        0
                    )::numeric as gross_profit_forecast_amount
                from plan_actuals
            )
            select
                coalesce(sum(p.target_sales_amount), 0) as sales_target_amount,
                coalesce(sum(a.sales_actual_amount), 0) as sales_actual_amount,
                coalesce(sum(a.sales_forecast_amount), 0) as sales_forecast_amount,
                coalesce(sum(p.target_gross_profit_amount), 0)
                    as gross_profit_target_amount,
                coalesce(sum(a.gross_profit_actual_amount), 0)
                    as gross_profit_actual_amount,
                coalesce(sum(a.gross_profit_forecast_amount), 0)
                    as gross_profit_forecast_amount,
                coalesce(
                    greatest((max(b.data_end_date) - max(b.period_start_date) + 1), 0),
                    0
                )::int as period_elapsed_days,
                greatest((max(b.period_end_date) - max(b.period_start_date) + 1), 1)::int
                    as period_total_days,
                count(*)::int as product_count,
                count(*) filter (where p.plan_status = 'unplanned')::int
                    as unplanned_count,
                count(*) filter (where p.plan_status = 'lagging')::int
                    as lagging_count,
                count(*) filter (where p.plan_status = 'severe_lagging')::int
                    as severe_lagging_count,
                count(*) filter (where p.adjusted)::int as adjusted_product_count,
                0::numeric as sales_target_adjust_amount,
                0::numeric as gross_profit_target_adjust_amount,
                count(*) filter (where p.operation_status = 'clearance')::int
                    as clearance_count
            from ops_operation_product_plans p
            cross join period_bounds b
            left join plan_forecast a on a.plan_id = p.id
            where p.period_id = :period_id
              and p.source_account_ref in :account_refs
            """
        ).bindparams(bindparam("account_refs", expanding=True))
        return (
            self.session.execute(
                statement,
                {"period_id": period_id, "account_refs": tuple(sorted(account_refs))},
            )
            .mappings()
            .one()
        )

    def owner_summary(self, *, period_id: UUID, account_refs: frozenset[str]) -> list[RowMapping]:
        statement = text(
            """
            with period_bounds as (
                select period_start_date, period_end_date
                from ops_operation_plan_periods
                where id = :period_id
            ),
            plan_actuals as (
                select
                    p.id as plan_id,
                    sum(coalesce(d.sales_amount, 0)) as sales_actual_amount,
                    sum(coalesce(d.gross_profit_amount, 0)) as gross_profit_actual_amount,
                    sum(coalesce(d.sales_qty, 0)) as sales_actual_qty,
                    max(coalesce(d.wfs_available_quantity, 0)) as wfs_available_qty,
                    max(nullif(d.owner_ref, '')) as actual_owner_ref
                from ops_operation_product_plans p
                join period_bounds b on true
                left join mart_daily_sales_item_day d
                  on trim(d.item_id::text) = trim(p.item_id::text)
                 and trim(d.msku::text) = trim(p.msku::text)
                 and d.source_account_ref = p.source_account_ref
                 and d.business_date_la >= b.period_start_date
                 and d.business_date_la <= b.period_end_date
                where p.period_id = :period_id
                  and p.source_account_ref in :account_refs
                group by p.id
            )
            select
                coalesce(nullif(p.owner_ref, ''), nullif(p.owner_name_snapshot, ''), nullif(a.actual_owner_ref, ''), 'unassigned') as owner_ref,
                coalesce(nullif(p.owner_name_snapshot, ''), nullif(p.owner_ref, ''), nullif(a.actual_owner_ref, ''), '未分配') as owner_name,
                count(*)::int as product_count,
                coalesce(sum(p.target_sales_amount), 0) as sales_target_amount,
                coalesce(sum(a.sales_actual_amount), 0) as sales_actual_amount,
                coalesce(sum(p.target_gross_profit_amount), 0) as gross_profit_target_amount,
                coalesce(sum(a.gross_profit_actual_amount), 0) as gross_profit_actual_amount,
                count(*) filter (where p.plan_status = 'lagging')::int as lagging_count,
                count(*) filter (where p.plan_status = 'severe_lagging')::int as severe_lagging_count,
                count(*) filter (
                    where p.stock_status = 'risk'
                       or (
                           coalesce(p.target_sales_amount, 0)
                               > coalesce(a.sales_actual_amount, 0)
                           and coalesce(a.sales_actual_amount, 0) > 0
                           and coalesce(a.sales_actual_qty, 0) > 0
                           and (
                               coalesce(a.wfs_available_qty, 0)
                               / greatest(
                                   (
                                       coalesce(p.target_sales_amount, 0)
                                       - coalesce(a.sales_actual_amount, 0)
                                   )
                                   / greatest(
                                       coalesce(a.sales_actual_amount, 0)
                                       / greatest(coalesce(a.sales_actual_qty, 0), 1),
                                       0.01
                                   ),
                                   1
                               )
                               * 100
                           ) < 100
                       )
                )::int as stock_risk_count
            from ops_operation_product_plans p
            left join plan_actuals a on a.plan_id = p.id
            where p.period_id = :period_id
              and p.source_account_ref in :account_refs
            group by
                coalesce(nullif(p.owner_ref, ''), nullif(p.owner_name_snapshot, ''), nullif(a.actual_owner_ref, ''), 'unassigned'),
                coalesce(nullif(p.owner_name_snapshot, ''), nullif(p.owner_ref, ''), nullif(a.actual_owner_ref, ''), '未分配')
            order by sales_target_amount desc
            """
        ).bindparams(bindparam("account_refs", expanding=True))
        return list(
            self.session.execute(
                statement,
                {"period_id": period_id, "account_refs": tuple(sorted(account_refs))},
            ).mappings()
        )

    def list_options(
        self, *, period_id: UUID, account_refs: frozenset[str]
    ) -> dict[str, list[RowMapping]]:
        params = {"period_id": period_id, "account_refs": tuple(sorted(account_refs))}
        bind = bindparam("account_refs", expanding=True)
        owners = list(
            self.session.execute(
                text(
                    """
            with period_bounds as (
                select period_start_date, period_end_date
                from ops_operation_plan_periods
                where id = :period_id
            ),
            owner_actuals as (
                select
                    p.id as plan_id,
                    max(nullif(d.owner_ref, '')) as actual_owner_ref
                from ops_operation_product_plans p
                join period_bounds b on true
                left join mart_daily_sales_item_day d
                  on trim(d.item_id::text) = trim(p.item_id::text)
                 and trim(d.msku::text) = trim(p.msku::text)
                 and d.source_account_ref = p.source_account_ref
                 and d.business_date_la >= b.period_start_date
                 and d.business_date_la <= b.period_end_date
                where p.period_id = :period_id
                  and p.source_account_ref in :account_refs
                group by p.id
            )
            select distinct
                   coalesce(nullif(p.owner_ref, ''), nullif(p.owner_name_snapshot, ''), nullif(a.actual_owner_ref, '')) as value,
                   coalesce(nullif(p.owner_name_snapshot, ''), nullif(p.owner_ref, ''), nullif(a.actual_owner_ref, '')) as label
            from ops_operation_product_plans p
            left join owner_actuals a on a.plan_id = p.id
            where p.period_id = :period_id and p.source_account_ref in :account_refs
              and coalesce(nullif(p.owner_ref, ''), nullif(p.owner_name_snapshot, ''), nullif(a.actual_owner_ref, '')) is not null
            order by label
            """
                ).bindparams(bind),
                params,
            ).mappings()
        )

        stores = list(
            self.session.execute(
                text(
                    """
            select distinct coalesce(store_id, '') as value,
                   coalesce(store_name_snapshot, store_id, '未知店铺') as label
            from ops_operation_product_plans
            where period_id = :period_id and source_account_ref in :account_refs
              and coalesce(store_id, '') <> ''
            order by label
            """
                ).bindparams(bindparam("account_refs", expanding=True)),
                params,
            ).mappings()
        )

        return {"owners": owners, "stores": stores}

    def list_events(self, plan_id: UUID) -> list[RowMapping]:
        return list(
            self.session.execute(
                text(
                    """
                select id, event_type, after_data, reason, actor_ref, created_at
                from ops_operation_plan_events
                where product_plan_id = :plan_id
                order by created_at desc
                """
                ),
                {"plan_id": plan_id},
            ).mappings()
        )

    def list_failed_import_rows(self, batch_id: UUID) -> list[RowMapping]:
        return list(
            self.session.execute(
                text(
                    """
                select *
                from ops_operation_plan_import_rows
                where batch_id = :batch_id
                  and import_status = 'failed'
                order by row_number asc
                """
                ),
                {"batch_id": batch_id},
            ).mappings()
        )


def _json_dumps(value: object) -> str:
    def fallback(item: object) -> str:
        return str(item)

    return json.dumps(value, ensure_ascii=False, default=fallback)

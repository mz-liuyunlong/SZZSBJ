# ruff: noqa: E501
from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

DEFAULT_COMMISSION_RATE = Decimal("0.15")
ALL_DATES_EFFECTIVE_FROM = date(1900, 1, 1)


class BusinessRulesRepository:
    """Repository for configurable commission rules used by MART calculations."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_active_operations(self, *, account_refs: frozenset[str]) -> list[Mapping[str, Any]]:
        statement = text(
            """
            select
                cast(id as text) id,
                source_account_ref,
                platform_code,
                operation_type,
                status,
                store_id,
                rule_scope,
                coalesce(item_ids,array[]::text[]) item_ids,
                price_min_amount,
                price_max_amount,
                start_date,
                end_date,
                days_recalculated,
                daily_sales_rows,
                order_profit_rows,
                actor_ref,
                request_id,
                message,
                error_message,
                created_at,
                started_at,
                finished_at,
                updated_at
            from business_rule_operation_logs
            where source_account_ref in :account_refs
              and operation_type='commission_recalculate'
              and status in ('queued','running')
            order by created_at desc
            """
        ).bindparams(bindparam("account_refs", expanding=True))
        return list(
            self.session.execute(
                statement,
                {"account_refs": tuple(account_refs)},
            ).mappings()
        )

    def list_operation_logs(
        self,
        *,
        account_refs: frozenset[str],
        limit: int = 80,
    ) -> list[Mapping[str, Any]]:
        statement = text(
            """
            select
                cast(id as text) id,
                source_account_ref,
                platform_code,
                operation_type,
                status,
                store_id,
                rule_scope,
                coalesce(item_ids,array[]::text[]) item_ids,
                price_min_amount,
                price_max_amount,
                start_date,
                end_date,
                days_recalculated,
                daily_sales_rows,
                order_profit_rows,
                actor_ref,
                request_id,
                message,
                error_message,
                created_at,
                started_at,
                finished_at,
                updated_at
            from business_rule_operation_logs
            where source_account_ref in :account_refs
            order by created_at desc
            limit :limit
            """
        ).bindparams(bindparam("account_refs", expanding=True))
        return list(
            self.session.execute(
                statement,
                {"account_refs": tuple(account_refs), "limit": limit},
            ).mappings()
        )

    def list_store_rules(self, account_refs: frozenset[str]) -> list[Mapping[str, Any]]:
        statement = text(
            """
            with stores as (
                select source_account_ref,'walmart' platform_code,store_id,max(store_name) store_name
                from (
                    select source_account_ref,coalesce(platform_code,'walmart') platform_code,store_id,store_name
                    from dim_lingxing_stores
                    where source_account_ref in :account_refs
                      and store_id is not null
                      and trim(store_id) <> ''

                    union all

                    select source_account_ref,coalesce(platform_code,'walmart') platform_code,store_id,store_name
                    from dim_walmart_listings
                    where source_account_ref in :account_refs
                      and store_id is not null
                      and trim(store_id) <> ''

                    union all

                    select source_account_ref,coalesce(platform_code,'walmart') platform_code,store_id,store_name
                    from fact_walmart_sales_item_daily
                    where source_account_ref in :account_refs
                      and store_id is not null
                      and trim(store_id) <> ''

                    union all

                    select source_account_ref,platform_code,store_id,null::text store_name
                    from ref_store_commission_rule_versions
                    where source_account_ref in :account_refs
                      and platform_code='walmart'
                      and store_id is not null
                      and trim(store_id) <> ''
                ) s
                where lower(coalesce(platform_code,'walmart')) in ('walmart','10008')
                group by 1,2,3
            ),
            active_rule as (
                select distinct on (source_account_ref,platform_code,store_id)
                    id,
                    source_account_ref,
                    platform_code,
                    store_id,
                    rule_scope,
                    item_id,
                    price_min_amount,
                    price_max_amount,
                    priority,
                    commission_rate,
                    effective_from,
                    effective_to,
                    is_active,
                    rule_version,
                    change_reason,
                    approved_by,
                    approved_at
                from ref_store_commission_rule_versions
                where source_account_ref in :account_refs
                  and platform_code='walmart'
                  and rule_scope='store'
                  and is_active=true
                  and effective_from <= current_date
                  and (effective_to is null or effective_to > current_date)
                order by source_account_ref,platform_code,store_id,effective_from desc,created_at desc
            ),
            active_ops as (
                select distinct on (source_account_ref,platform_code,store_id)
                    id,
                    source_account_ref,
                    platform_code,
                    store_id,
                    status,
                    actor_ref,
                    created_at
                from business_rule_operation_logs
                where source_account_ref in :account_refs
                  and operation_type='commission_recalculate'
                  and status in ('queued','running')
                order by source_account_ref,platform_code,store_id,created_at desc
            )
            select
                cast(active_rule.id as text) id,
                stores.source_account_ref,
                stores.platform_code,
                stores.store_id,
                stores.store_name,
                coalesce(active_rule.rule_scope,'store') rule_scope,
                active_rule.item_id,
                active_rule.price_min_amount,
                active_rule.price_max_amount,
                coalesce(active_rule.priority,100) priority,
                coalesce(active_rule.commission_rate,:default_rate) commission_rate,
                case when active_rule.id is null then 'default_15_percent' else 'store_rule' end source,
                active_rule.effective_from,
                active_rule.effective_to,
                coalesce(active_rule.is_active,true) is_active,
                active_rule.rule_version,
                active_rule.change_reason,
                active_rule.approved_by,
                active_rule.approved_at,
                exists (
                    select 1
                    from mart_daily_sales_item_day m
                    where m.source_account_ref=stores.source_account_ref
                      and m.store_id=stores.store_id
                      and abs(coalesce(m.commission_rate,0)-coalesce(active_rule.commission_rate,:default_rate)) > 0.000001
                    limit 1
                ) needs_recalculate,
                cast(active_ops.id as text) active_operation_id,
                active_ops.status active_operation_status,
                active_ops.actor_ref active_operation_actor,
                active_ops.created_at active_operation_created_at
            from stores
            left join active_rule on active_rule.source_account_ref=stores.source_account_ref
              and active_rule.platform_code=stores.platform_code
              and active_rule.store_id=stores.store_id
            left join active_ops on active_ops.source_account_ref=stores.source_account_ref
              and active_ops.platform_code=stores.platform_code
              and active_ops.store_id=stores.store_id
            order by stores.store_name nulls last,stores.store_id
            """
        ).bindparams(bindparam("account_refs", expanding=True))
        return list(
            self.session.execute(
                statement,
                {
                    "account_refs": tuple(account_refs),
                    "default_rate": DEFAULT_COMMISSION_RATE,
                },
            ).mappings()
        )

    def list_special_rules(self, account_refs: frozenset[str]) -> list[Mapping[str, Any]]:
        statement = text(
            """
            with stores as (
                select source_account_ref,store_id,max(store_name) store_name
                from (
                    select source_account_ref,store_id,store_name from dim_lingxing_stores
                    union all
                    select source_account_ref,store_id,store_name from dim_walmart_listings
                    union all
                    select source_account_ref,store_id,store_name from fact_walmart_sales_item_daily
                ) s
                where source_account_ref in :account_refs
                  and store_id is not null
                  and trim(store_id) <> ''
                group by 1,2
            ),
            active_ops as (
                select distinct on (source_account_ref,platform_code,store_id)
                    id,
                    source_account_ref,
                    platform_code,
                    store_id,
                    status,
                    actor_ref,
                    created_at
                from business_rule_operation_logs
                where source_account_ref in :account_refs
                  and operation_type='commission_recalculate'
                  and status in ('queued','running')
                order by source_account_ref,platform_code,store_id,created_at desc
            )
            select
                cast(rule.id as text) id,
                rule.source_account_ref,
                rule.platform_code,
                rule.store_id,
                stores.store_name,
                rule.rule_scope,
                rule.item_id,
                rule.price_min_amount,
                rule.price_max_amount,
                rule.priority,
                rule.commission_rate,
                'store_rule' source,
                rule.effective_from,
                rule.effective_to,
                rule.is_active,
                rule.rule_version,
                rule.change_reason,
                rule.approved_by,
                rule.approved_at,
                true needs_recalculate,
                cast(active_ops.id as text) active_operation_id,
                active_ops.status active_operation_status,
                active_ops.actor_ref active_operation_actor,
                active_ops.created_at active_operation_created_at
            from ref_store_commission_rule_versions rule
            left join stores on stores.source_account_ref=rule.source_account_ref
              and stores.store_id=rule.store_id
            left join active_ops on active_ops.source_account_ref=rule.source_account_ref
              and active_ops.platform_code=rule.platform_code
              and active_ops.store_id=rule.store_id
            where rule.source_account_ref in :account_refs
              and rule.platform_code='walmart'
              and rule.rule_scope in ('item','price_range')
              and rule.is_active=true
            order by rule.store_id,
              case rule.rule_scope when 'item' then 1 when 'price_range' then 2 else 99 end,
              rule.priority,
              rule.effective_from desc,
              rule.created_at desc
            """
        ).bindparams(bindparam("account_refs", expanding=True))
        return list(
            self.session.execute(
                statement,
                {"account_refs": tuple(account_refs)},
            ).mappings()
        )

    def find_active_recalculate_job(
        self,
        *,
        source_account_ref: str,
        platform_code: str,
        store_id: str,
    ) -> Mapping[str, Any] | None:
        return (
            self.session.execute(
                text(
                    """
                    select
                        cast(id as text) id,
                        source_account_ref,
                        platform_code,
                        operation_type,
                        status,
                        store_id,
                        rule_scope,
                        coalesce(item_ids,array[]::text[]) item_ids,
                        price_min_amount,
                        price_max_amount,
                        start_date,
                        end_date,
                        days_recalculated,
                        daily_sales_rows,
                        order_profit_rows,
                        actor_ref,
                        request_id,
                        message,
                        error_message,
                        created_at,
                        started_at,
                        finished_at,
                        updated_at
                    from business_rule_operation_logs
                    where source_account_ref=:source_account_ref
                      and platform_code=:platform_code
                      and store_id=:store_id
                      and operation_type='commission_recalculate'
                      and status in ('queued','running')
                    order by created_at desc
                    limit 1
                    """
                ),
                {
                    "source_account_ref": source_account_ref,
                    "platform_code": platform_code,
                    "store_id": store_id,
                },
            )
            .mappings()
            .first()
        )

    def create_recalculate_job(
        self,
        *,
        source_account_ref: str,
        platform_code: str,
        store_id: str,
        rule_scope: str,
        item_ids: list[str],
        price_min_amount: Decimal | None,
        price_max_amount: Decimal | None,
        start_date: date | None,
        end_date: date | None,
        actor_ref: str,
        request_id: str,
    ) -> Mapping[str, Any]:
        return (
            self.session.execute(
                text(
                    """
                    insert into business_rule_operation_logs (
                        source_account_ref,
                        platform_code,
                        operation_type,
                        status,
                        store_id,
                        rule_scope,
                        item_ids,
                        price_min_amount,
                        price_max_amount,
                        start_date,
                        end_date,
                        actor_ref,
                        request_id,
                        message
                    )
                    values (
                        :source_account_ref,
                        :platform_code,
                        'commission_recalculate',
                        'queued',
                        :store_id,
                        :rule_scope,
                        :item_ids,
                        :price_min_amount,
                        :price_max_amount,
                        :start_date,
                        :end_date,
                        :actor_ref,
                        :request_id,
                        '重算任务已创建'
                    )
                    returning
                        cast(id as text) id,
                        source_account_ref,
                        platform_code,
                        operation_type,
                        status,
                        store_id,
                        rule_scope,
                        coalesce(item_ids,array[]::text[]) item_ids,
                        price_min_amount,
                        price_max_amount,
                        start_date,
                        end_date,
                        days_recalculated,
                        daily_sales_rows,
                        order_profit_rows,
                        actor_ref,
                        request_id,
                        message,
                        error_message,
                        created_at,
                        started_at,
                        finished_at,
                        updated_at
                    """
                ),
                {
                    "source_account_ref": source_account_ref,
                    "platform_code": platform_code,
                    "store_id": store_id,
                    "rule_scope": rule_scope,
                    "item_ids": item_ids,
                    "price_min_amount": price_min_amount,
                    "price_max_amount": price_max_amount,
                    "start_date": start_date,
                    "end_date": end_date,
                    "actor_ref": actor_ref,
                    "request_id": request_id,
                },
            )
            .mappings()
            .one()
        )

    def get_operation_job(self, *, job_id: str) -> Mapping[str, Any] | None:
        return (
            self.session.execute(
                text(
                    """
                    select
                        cast(id as text) id,
                        source_account_ref,
                        platform_code,
                        operation_type,
                        status,
                        store_id,
                        rule_scope,
                        coalesce(item_ids,array[]::text[]) item_ids,
                        price_min_amount,
                        price_max_amount,
                        start_date,
                        end_date,
                        days_recalculated,
                        daily_sales_rows,
                        order_profit_rows,
                        actor_ref,
                        request_id,
                        message,
                        error_message,
                        created_at,
                        started_at,
                        finished_at,
                        updated_at
                    from business_rule_operation_logs
                    where cast(id as text)=:job_id
                    """
                ),
                {"job_id": job_id},
            )
            .mappings()
            .first()
        )

    def mark_job_running(self, *, job_id: str) -> None:
        self.session.execute(
            text(
                """
                update business_rule_operation_logs
                set status='running',
                    started_at=coalesce(started_at,now()),
                    updated_at=now(),
                    message='重算中'
                where cast(id as text)=:job_id
                  and status in ('queued','running')
                """
            ),
            {"job_id": job_id},
        )

    def mark_job_succeeded(
        self,
        *,
        job_id: str,
        start_date: date | None,
        end_date: date | None,
        days_recalculated: int,
        daily_sales_rows: int,
        order_profit_rows: int,
    ) -> None:
        self.session.execute(
            text(
                """
                update business_rule_operation_logs
                set status='succeeded',
                    start_date=:start_date,
                    end_date=:end_date,
                    days_recalculated=:days_recalculated,
                    daily_sales_rows=:daily_sales_rows,
                    order_profit_rows=:order_profit_rows,
                    finished_at=now(),
                    updated_at=now(),
                    message='重算完成'
                where cast(id as text)=:job_id
                """
            ),
            {
                "job_id": job_id,
                "start_date": start_date,
                "end_date": end_date,
                "days_recalculated": days_recalculated,
                "daily_sales_rows": daily_sales_rows,
                "order_profit_rows": order_profit_rows,
            },
        )

    def mark_job_failed(self, *, job_id: str, error_message: str) -> None:
        self.session.execute(
            text(
                """
                update business_rule_operation_logs
                set status='failed',
                    finished_at=now(),
                    updated_at=now(),
                    message='重算失败',
                    error_message=:error_message
                where cast(id as text)=:job_id
                """
            ),
            {"job_id": job_id, "error_message": error_message[:2000]},
        )

    def close_existing_rules_for_target(
        self,
        *,
        source_account_ref: str,
        platform_code: str,
        store_id: str,
        rule_scope: str,
        effective_from: date,
        all_dates: bool,
        item_id: str | None = None,
    ) -> None:
        base = """
            source_account_ref=:source_account_ref
            and platform_code=:platform_code
            and store_id=:store_id
            and rule_scope=:rule_scope
            and is_active=true
        """
        params: dict[str, object] = {
            "source_account_ref": source_account_ref,
            "platform_code": platform_code,
            "store_id": store_id,
            "rule_scope": rule_scope,
            "effective_from": effective_from,
            "item_id": item_id,
        }

        if rule_scope == "item":
            base += " and item_id=:item_id"

        if all_dates:
            self.session.execute(
                text(
                    f"""
                    update ref_store_commission_rule_versions
                    set is_active=false, updated_at=now()
                    where {base}
                    """
                ),
                params,
            )
            return

        self.session.execute(
            text(
                f"""
                update ref_store_commission_rule_versions
                set effective_to=:effective_from, updated_at=now()
                where {base}
                  and effective_from < :effective_from
                  and (effective_to is null or effective_to > :effective_from)
                """
            ),
            params,
        )
        self.session.execute(
            text(
                f"""
                update ref_store_commission_rule_versions
                set is_active=false, updated_at=now()
                where {base}
                  and effective_from >= :effective_from
                """
            ),
            params,
        )

    def deactivate_rule(
        self,
        *,
        source_account_ref: str,
        rule_id: str,
    ) -> int:
        result = self.session.execute(
            text(
                """
                update ref_store_commission_rule_versions
                set is_active=false, updated_at=now()
                where source_account_ref=:source_account_ref
                  and cast(id as text)=:rule_id
                  and is_active=true
                """
            ),
            {
                "source_account_ref": source_account_ref,
                "rule_id": rule_id,
            },
        )
        return int(result.rowcount or 0)

    def insert_commission_rule(
        self,
        *,
        source_account_ref: str,
        platform_code: str,
        store_id: str,
        rule_scope: str,
        item_id: str | None,
        price_min_amount: Decimal | None,
        price_max_amount: Decimal | None,
        priority: int,
        commission_rate: Decimal,
        effective_from: date,
        effective_to: date | None,
        rule_version: str,
        change_reason: str,
        approved_by: str,
        request_id: str,
    ) -> Mapping[str, Any]:
        return (
            self.session.execute(
                text(
                    """
                    insert into ref_store_commission_rule_versions (
                        id,
                        source_account_ref,
                        platform_code,
                        store_id,
                        rule_scope,
                        item_id,
                        price_min_amount,
                        price_max_amount,
                        priority,
                        commission_rate,
                        effective_from,
                        effective_to,
                        is_active,
                        rule_version,
                        change_reason,
                        approved_by,
                        approved_at,
                        request_id,
                        created_at,
                        updated_at
                    )
                    values (
                        gen_random_uuid(),
                        :source_account_ref,
                        :platform_code,
                        :store_id,
                        :rule_scope,
                        :item_id,
                        :price_min_amount,
                        :price_max_amount,
                        :priority,
                        :commission_rate,
                        :effective_from,
                        :effective_to,
                        true,
                        :rule_version,
                        :change_reason,
                        :approved_by,
                        now(),
                        :request_id,
                        now(),
                        now()
                    )
                    returning
                        cast(id as text) id,
                        source_account_ref,
                        platform_code,
                        store_id,
                        null::text store_name,
                        rule_scope,
                        item_id,
                        price_min_amount,
                        price_max_amount,
                        priority,
                        commission_rate,
                        'store_rule' source,
                        effective_from,
                        effective_to,
                        is_active,
                        rule_version,
                        change_reason,
                        approved_by,
                        approved_at,
                        true needs_recalculate,
                        null::text active_operation_id,
                        null::text active_operation_status,
                        null::text active_operation_actor,
                        null::timestamptz active_operation_created_at
                    """
                ),
                {
                    "source_account_ref": source_account_ref,
                    "platform_code": platform_code,
                    "store_id": store_id,
                    "rule_scope": rule_scope,
                    "item_id": item_id,
                    "price_min_amount": price_min_amount,
                    "price_max_amount": price_max_amount,
                    "priority": priority,
                    "commission_rate": commission_rate,
                    "effective_from": effective_from,
                    "effective_to": effective_to,
                    "rule_version": rule_version,
                    "change_reason": change_reason,
                    "approved_by": approved_by,
                    "request_id": request_id,
                },
            )
            .mappings()
            .one()
        )

    def date_bounds_for_recalculate(
        self,
        *,
        source_account_ref: str,
        store_id: str,
        item_ids: list[str],
    ) -> tuple[date | None, date | None]:
        item_filter = "and item_id in :item_ids" if item_ids else ""
        statement = text(
            f"""
            select min(business_date_la) start_date,max(business_date_la) end_date
            from (
                select business_date_la
                from fact_walmart_sales_item_daily
                where source_account_ref=:source_account_ref
                  and store_id=:store_id
                  {item_filter}

                union

                select business_date_la
                from mart_daily_sales_item_day
                where source_account_ref=:source_account_ref
                  and store_id=:store_id
                  {item_filter}
            ) d
            """
        )
        if item_ids:
            statement = statement.bindparams(bindparam("item_ids", expanding=True))
        row = self.session.execute(
            statement,
            {
                "source_account_ref": source_account_ref,
                "store_id": store_id,
                "item_ids": tuple(item_ids),
            },
        ).one()
        return row[0], row[1]

    def business_dates_for_recalculate(
        self,
        *,
        source_account_ref: str,
        store_id: str,
        item_ids: list[str],
        start_date: date,
        end_date: date,
    ) -> list[date]:
        item_filter = "and item_id in :item_ids" if item_ids else ""
        statement = text(
            f"""
            select distinct business_date_la
            from (
                select business_date_la
                from fact_walmart_sales_item_daily
                where source_account_ref=:source_account_ref
                  and store_id=:store_id
                  and business_date_la between :start_date and :end_date
                  {item_filter}

                union

                select business_date_la
                from mart_daily_sales_item_day
                where source_account_ref=:source_account_ref
                  and store_id=:store_id
                  and business_date_la between :start_date and :end_date
                  {item_filter}
            ) d
            order by business_date_la
            """
        )
        if item_ids:
            statement = statement.bindparams(bindparam("item_ids", expanding=True))
        return [
            row[0]
            for row in self.session.execute(
                statement,
                {
                    "source_account_ref": source_account_ref,
                    "store_id": store_id,
                    "item_ids": tuple(item_ids),
                    "start_date": start_date,
                    "end_date": end_date,
                },
            )
        ]

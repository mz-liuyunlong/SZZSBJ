from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.modules.business_rules.repository import (
    ALL_DATES_EFFECTIVE_FROM,
    BusinessRulesRepository,
)
from app.modules.business_rules.schemas import (
    StoreCommissionDeactivateRequest,
    StoreCommissionListData,
    StoreCommissionMutationData,
    StoreCommissionRead,
    StoreCommissionRecalculateData,
    StoreCommissionRecalculateRequest,
    StoreCommissionUpsertRequest,
)

DEFAULT_PAGE_SIZE = 100
DEFAULT_CAMPAIGN_TYPE = "SP"
DEFAULT_MAX_ADVERTISERS = 20


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _rate_to_percent(value: Decimal) -> Decimal:
    return (value * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _safe_token(value: str | None, fallback: str = "rule") -> str:
    if not value:
        return fallback
    token = re.sub(r"[^a-zA-Z0-9]+", "_", value)[:32].strip("_").lower()
    return token or fallback


def _store_commission_read(row: Mapping[str, Any]) -> StoreCommissionRead:
    rate = _decimal(row["commission_rate"])
    return StoreCommissionRead(
        id=row.get("id"),
        source_account_ref=str(row["source_account_ref"]),
        platform_code=str(row["platform_code"]),
        store_id=str(row["store_id"]),
        store_name=row.get("store_name"),
        rule_scope=row.get("rule_scope") or "store",
        item_id=row.get("item_id"),
        price_min_amount=row.get("price_min_amount"),
        price_max_amount=row.get("price_max_amount"),
        priority=int(row.get("priority") or 100),
        commission_rate=rate,
        commission_percent=_rate_to_percent(rate),
        source=row["source"],
        effective_from=row.get("effective_from"),
        effective_to=row.get("effective_to"),
        is_active=bool(row["is_active"]),
        rule_version=row.get("rule_version"),
        change_reason=row.get("change_reason"),
        approved_by=row.get("approved_by"),
        approved_at=row.get("approved_at"),
        needs_recalculate=bool(row.get("needs_recalculate")),
    )


class BusinessRulesService:
    """Business rules that feed MART calculation instead of frontend-only formulas."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = BusinessRulesRepository(session)

    def list_store_commissions(
        self,
        account_refs: frozenset[str],
    ) -> StoreCommissionListData:
        return StoreCommissionListData(
            store_rules=[
                _store_commission_read(row)
                for row in self.repository.list_store_rules(account_refs)
            ],
            special_rules=[
                _store_commission_read(row)
                for row in self.repository.list_special_rules(account_refs)
            ],
            operation_logs=[
                _operation_read(row)
                for row in self.repository.list_operation_logs(account_refs=account_refs)
            ],
        )

    def upsert_store_commission(
        self,
        *,
        payload: StoreCommissionUpsertRequest,
        account_refs: frozenset[str],
        actor_ref: str,
        request_id: str,
    ) -> StoreCommissionMutationData:
        if payload.source_account_ref not in account_refs:
            raise ValueError("SOURCE_ACCOUNT_SCOPE_DENIED")

        effective_from = (
            ALL_DATES_EFFECTIVE_FROM
            if payload.apply_scope == "all_dates"
            else payload.effective_from
        )
        if effective_from is None:
            raise ValueError("EFFECTIVE_FROM_REQUIRED")

        if payload.replace_rule_id:
            self.repository.deactivate_rule(
                source_account_ref=payload.source_account_ref,
                rule_id=payload.replace_rule_id,
            )

        inserted: list[StoreCommissionRead] = []
        item_ids = payload.normalized_item_ids()

        targets: list[tuple[str | None, Decimal | None, Decimal | None]]
        if payload.rule_scope == "item":
            targets = [(item_id, None, None) for item_id in item_ids]
        elif payload.rule_scope == "price_range":
            targets = [(None, payload.price_min_amount, payload.price_max_amount)]
        else:
            targets = [(None, None, None)]

        basis_points = int((payload.commission_rate * Decimal("10000")).to_integral_value())
        safe_request = request_id.replace("-", "")[:10] or "manual"

        for index, (item_id, price_min, price_max) in enumerate(targets, 1):
            if payload.rule_scope in {"store", "item"}:
                self.repository.close_existing_rules_for_target(
                    source_account_ref=payload.source_account_ref,
                    platform_code=payload.platform_code,
                    store_id=payload.store_id,
                    rule_scope=payload.rule_scope,
                    item_id=item_id,
                    effective_from=effective_from,
                    all_dates=payload.apply_scope == "all_dates",
                )

            if payload.rule_scope == "item":
                target_token = _safe_token(item_id, f"item_{index}")
            elif payload.rule_scope == "price_range":
                min_token = "min" if price_min is None else str(price_min).replace(".", "_")
                max_token = "max" if price_max is None else str(price_max).replace(".", "_")
                target_token = f"price_{min_token}_{max_token}"
            else:
                target_token = "store"

            rule_version = (
                f"commission_{payload.rule_scope}_{basis_points}bp_"
                f"{effective_from.strftime('%Y%m%d')}_{target_token}_{safe_request}"
            )

            row = self.repository.insert_commission_rule(
                source_account_ref=payload.source_account_ref,
                platform_code=payload.platform_code,
                store_id=payload.store_id,
                rule_scope=payload.rule_scope,
                item_id=item_id,
                price_min_amount=price_min,
                price_max_amount=price_max,
                priority=payload.priority,
                commission_rate=payload.commission_rate,
                effective_from=effective_from,
                effective_to=payload.effective_to,
                rule_version=rule_version,
                change_reason=payload.change_reason,
                approved_by=actor_ref,
                request_id=request_id,
            )
            inserted.append(_store_commission_read(row))

        self.session.commit()
        return StoreCommissionMutationData(items=inserted)

    def deactivate_store_commission(
        self,
        *,
        payload: StoreCommissionDeactivateRequest,
        account_refs: frozenset[str],
    ) -> StoreCommissionMutationData:
        if payload.source_account_ref not in account_refs:
            raise ValueError("SOURCE_ACCOUNT_SCOPE_DENIED")
        count = self.repository.deactivate_rule(
            source_account_ref=payload.source_account_ref,
            rule_id=payload.rule_id,
        )
        if count <= 0:
            raise ValueError("RULE_NOT_FOUND_OR_ALREADY_INACTIVE")
        self.session.commit()
        return StoreCommissionMutationData(items=[])

    def recalculate_store_commissions(
        self,
        *,
        payload: StoreCommissionRecalculateRequest,
        account_refs: frozenset[str],
        actor_ref: str,
        request_id: str,
    ) -> StoreCommissionRecalculateData:
        if payload.source_account_ref not in account_refs:
            raise ValueError("SOURCE_ACCOUNT_SCOPE_DENIED")

        existing = self.repository.find_active_recalculate_job(
            source_account_ref=payload.source_account_ref,
            platform_code="walmart",
            store_id=payload.store_id,
        )
        if existing is not None:
            return StoreCommissionRecalculateData(
                operation_id=str(existing["id"]),
                source_account_ref=payload.source_account_ref,
                store_id=payload.store_id,
                rule_scope=existing.get("rule_scope") or payload.rule_scope,
                item_ids=list(existing.get("item_ids") or []),
                status=existing["status"],
                message="该店铺已有重算任务正在执行",
            )

        item_ids = payload.item_ids if payload.rule_scope == "item" else []
        row = self.repository.create_recalculate_job(
            source_account_ref=payload.source_account_ref,
            platform_code="walmart",
            store_id=payload.store_id,
            rule_scope=payload.rule_scope,
            item_ids=item_ids,
            price_min_amount=payload.price_min_amount,
            price_max_amount=payload.price_max_amount,
            start_date=payload.start_date,
            end_date=payload.end_date,
            actor_ref=actor_ref,
            request_id=request_id,
        )
        self.session.commit()

        return StoreCommissionRecalculateData(
            operation_id=str(row["id"]),
            source_account_ref=payload.source_account_ref,
            store_id=payload.store_id,
            rule_scope=payload.rule_scope,
            item_ids=item_ids,
            status=row["status"],
            message="重算任务已创建",
        )

    def list_store_commission_operation_logs(
        self,
        account_refs: frozenset[str],
    ):
        from app.modules.business_rules.schemas import StoreCommissionOperationLogData

        return StoreCommissionOperationLogData(
            items=[
                _operation_read(row)
                for row in self.repository.list_operation_logs(account_refs=account_refs)
            ]
        )

    def execute_recalculate_job(self, job_id: str) -> None:
        job = self.repository.get_operation_job(job_id=job_id)
        if job is None:
            return

        self.repository.mark_job_running(job_id=job_id)
        self.session.commit()

        try:
            item_ids = list(job.get("item_ids") or []) if job.get("rule_scope") == "item" else []
            start_date = job.get("start_date")
            end_date = job.get("end_date")

            if start_date is None or end_date is None:
                start_date, end_date = self.repository.date_bounds_for_recalculate(
                    source_account_ref=job["source_account_ref"],
                    store_id=job["store_id"],
                    item_ids=item_ids,
                )

            if start_date is None or end_date is None:
                self.repository.mark_job_succeeded(
                    job_id=job_id,
                    start_date=start_date,
                    end_date=end_date,
                    days_recalculated=0,
                    daily_sales_rows=0,
                    order_profit_rows=0,
                )
                self.session.commit()
                return

            dates = self.repository.business_dates_for_recalculate(
                source_account_ref=job["source_account_ref"],
                store_id=job["store_id"],
                item_ids=item_ids,
                start_date=start_date,
                end_date=end_date,
            )

            from app.modules.integration_sync.data_pages_business_rules_v2 import (
                DataPagesRealSyncRunner as DataPagesBusinessRulesV2Runner,
            )

            daily_sales_rows = 0
            order_profit_rows = 0

            for business_date in dates:
                runner = DataPagesBusinessRulesV2Runner(
                    session=self.session,
                    client=None,
                    source_account_ref=job["source_account_ref"],
                    business_date=business_date,
                    page_size=DEFAULT_PAGE_SIZE,
                    campaign_type=DEFAULT_CAMPAIGN_TYPE,
                    max_advertisers=DEFAULT_MAX_ADVERTISERS,
                )
                daily_sales_rows += runner._refresh_daily_sales_mart()
                order_profit_rows += runner._refresh_order_profit_mart()

            self.repository.mark_job_succeeded(
                job_id=job_id,
                start_date=start_date,
                end_date=end_date,
                days_recalculated=len(dates),
                daily_sales_rows=daily_sales_rows,
                order_profit_rows=order_profit_rows,
            )
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            self.repository.mark_job_failed(job_id=job_id, error_message=str(exc))
            self.session.commit()
            raise


def _operation_read(row: Mapping[str, Any]):
    from app.modules.business_rules.schemas import BusinessRuleOperationRead

    return BusinessRuleOperationRead(
        id=str(row["id"]),
        source_account_ref=str(row["source_account_ref"]),
        platform_code=str(row["platform_code"]),
        operation_type=str(row["operation_type"]),
        status=row["status"],
        store_id=row.get("store_id"),
        rule_scope=row.get("rule_scope"),
        item_ids=list(row.get("item_ids") or []),
        price_min_amount=row.get("price_min_amount"),
        price_max_amount=row.get("price_max_amount"),
        start_date=row.get("start_date"),
        end_date=row.get("end_date"),
        days_recalculated=int(row.get("days_recalculated") or 0),
        daily_sales_rows=int(row.get("daily_sales_rows") or 0),
        order_profit_rows=int(row.get("order_profit_rows") or 0),
        actor_ref=str(row["actor_ref"]),
        request_id=str(row["request_id"]),
        message=row.get("message"),
        error_message=row.get("error_message"),
        created_at=row["created_at"],
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
        updated_at=row["updated_at"],
    )


def run_store_commission_recalculate_job(job_id: str) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import get_database_url, get_settings

    engine = create_engine(get_database_url(get_settings()))
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        service = BusinessRulesService(session)
        service.execute_recalculate_job(job_id)

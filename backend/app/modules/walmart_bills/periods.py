"""把明细汇总成「店铺 × 一期账单」：只算没被删除、最近一次重拉还在的明细。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.modules.walmart_bills.models import WalmartBillLine, WalmartBillPeriod

ZERO = Decimal("0")


def _valid() -> object:
    return and_(WalmartBillLine.delete_flag == 0, WalmartBillLine.missing_since.is_(None))


def period_status(*, valid_lines: int, payable: Decimal) -> str:
    """一期都被删 / 作废 = voided；应付 ≤ 0 = 本期不打款；其余 normal。"""
    if valid_lines == 0:
        return "voided"
    if payable <= ZERO:
        return "not_payable"
    return "normal"


def refresh_periods(
    session: Session,
    *,
    source_account_ref: str,
    keys: Iterable[tuple[str, str]],
    store_names: dict[str, str],
    run_id: UUID | None,
) -> int:
    """重算给定的 (店铺, reportKey)；返回写入的期数。调用方负责提交。"""
    wanted = sorted(set(keys))
    if not wanted:
        return 0
    valid = _valid()
    written = 0
    now = datetime.now(UTC)
    for start in range(0, len(wanted), 500):
        chunk = wanted[start : start + 500]
        scope = and_(
            WalmartBillLine.source_account_ref == source_account_ref,
            tuple_(WalmartBillLine.store_id, WalmartBillLine.report_key).in_(chunk),
        )
        totals = session.execute(
            select(
                WalmartBillLine.store_id,
                WalmartBillLine.report_key,
                func.max(WalmartBillLine.report_id),
                func.max(WalmartBillLine.report_date),
                func.min(WalmartBillLine.period_start_date).filter(valid),
                func.max(WalmartBillLine.period_end_date).filter(valid),
                func.min(WalmartBillLine.posted_date).filter(valid),
                func.max(WalmartBillLine.posted_date).filter(valid),
                func.max(WalmartBillLine.currency_code).filter(valid),
                func.count().filter(valid),
                func.count().filter(
                    or_(
                        WalmartBillLine.delete_flag != 0, WalmartBillLine.missing_since.is_not(None)
                    )
                ),
                func.coalesce(func.sum(WalmartBillLine.amount).filter(valid), ZERO),
                func.count(func.distinct(WalmartBillLine.total_payable)).filter(
                    and_(valid, WalmartBillLine.total_payable.is_not(None))
                ),
                func.max(WalmartBillLine.total_payable).filter(valid),
            )
            .where(scope)
            .group_by(WalmartBillLine.store_id, WalmartBillLine.report_key)
        ).all()
        by_type: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
        for store_id, report_key, amount_type, amount in session.execute(
            select(
                WalmartBillLine.store_id,
                WalmartBillLine.report_key,
                WalmartBillLine.amount_type,
                func.sum(WalmartBillLine.amount),
            )
            .where(scope, valid)
            .group_by(
                WalmartBillLine.store_id, WalmartBillLine.report_key, WalmartBillLine.amount_type
            )
        ).all():
            by_type[(store_id, report_key)][amount_type or "（空）"] = str(amount)
        for (
            store_id,
            report_key,
            report_id,
            report_date,
            period_start,
            period_end,
            first_posted,
            last_posted,
            currency,
            valid_count,
            excluded_count,
            amount_sum,
            payable_kinds,
            total_payable,
        ) in totals:
            # 领星「账单总额」目前都是空的；只有全期一致地给了一个值才用它，否则用明细合计。
            stated = total_payable if payable_kinds == 1 else None
            payable = stated if stated is not None else amount_sum
            values = {
                "source_account_ref": source_account_ref,
                "store_id": store_id,
                "report_key": report_key,
                "store_name": store_names.get(store_id),
                "report_id": report_id,
                "report_date": report_date,
                "period_start_date": period_start or first_posted,
                "period_end_date": period_end or last_posted,
                "first_posted_date": first_posted,
                "last_posted_date": last_posted,
                "currency_code": currency,
                "line_count": valid_count,
                "excluded_line_count": excluded_count,
                "amount_sum": amount_sum,
                "total_payable": stated,
                "payable_amount": payable,
                "amounts_by_type": dict(sorted(by_type[(store_id, report_key)].items())),
                "status": period_status(valid_lines=valid_count, payable=payable),
                "source_run_id": run_id,
                "refreshed_at": now,
            }
            statement = pg_insert(WalmartBillPeriod).values(**values)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=["source_account_ref", "store_id", "report_key"],
                    set_={
                        key: statement.excluded[key]
                        for key in values
                        if key not in {"source_account_ref", "store_id", "report_key"}
                    },
                )
            )
            written += 1
    return written

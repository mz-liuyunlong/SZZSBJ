"""读「店铺 × 每期」沃尔玛账单汇总。回款对账页面（PR-2）、现金利润、结算利润共用。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.walmart_bills.models import WalmartBillPeriod

MAX_ROWS = 2000


def list_periods(
    session: Session,
    *,
    store_id: str | None = None,
    report_date_from: date | None = None,
    report_date_to: date | None = None,
) -> list[WalmartBillPeriod]:
    """新到旧；同一天按店铺排。"""
    query = select(WalmartBillPeriod)
    if store_id is not None:
        query = query.where(WalmartBillPeriod.store_id == store_id)
    if report_date_from is not None:
        query = query.where(WalmartBillPeriod.report_date >= report_date_from)
    if report_date_to is not None:
        query = query.where(WalmartBillPeriod.report_date <= report_date_to)
    query = query.order_by(WalmartBillPeriod.report_date.desc(), WalmartBillPeriod.store_id).limit(
        MAX_ROWS
    )
    return list(session.scalars(query))

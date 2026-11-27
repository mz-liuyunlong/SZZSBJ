"""全系统读汇率的唯一入口。只读领星「我的汇率」my_rate；调用方不要自己查表。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.fx_rates.models import LingxingFxRate


def list_usd_cny_rates(session: Session) -> list[LingxingFxRate]:
    """美元汇率明细，新月份在前；领星没给汇率的月份也列出来。"""
    return list(
        session.scalars(
            select(LingxingFxRate)
            .where(LingxingFxRate.currency_code == "USD")
            .order_by(LingxingFxRate.rate_month.desc())
        ).all()
    )


def month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def load_usd_cny_rates(session: Session) -> dict[str, Decimal]:
    """每个月的美元汇率。没有汇率的月份不在结果里，这里不兜底。"""
    rows = session.execute(
        select(LingxingFxRate.rate_month, LingxingFxRate.my_rate).where(
            LingxingFxRate.currency_code == "USD",
            LingxingFxRate.my_rate.is_not(None),
        )
    ).all()
    return {month: rate for month, rate in rows if rate is not None}


def usd_cny_rate_for(rates: dict[str, Decimal], day: date) -> Decimal | None:
    return rates.get(month_key(day))

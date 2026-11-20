"""Scope-bound, read-only diagnosis for existing integration sync anomalies.

The original order and SaleStat facts remain independent sources. This module
may explain a discrepancy but must never invent an Item ID, override the
provider's data, or calculate payable profit from a disputed sample.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.integration_sync.models import IntegrationSyncAnomaly

SAMPLE_EXCEEDANCE_CODE = "DATA_PAGES_CONFIRMED_SAMPLE_EXCEEDS_SALESTAT"


@dataclass(frozen=True)
class AnomalyDiagnosis:
    status: str
    explanation: str
    next_action: str
    recognized_zero_paid_orders: int | None = None
    recognized_zero_paid_qty: str | None = None
    approved_sample_qty: str | None = None
    approved_sample_amount: str | None = None
    salestat_qty: str | None = None
    salestat_amount: str | None = None
    mart_sample_qty: str | None = None
    mart_gross_qty: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "explanation": self.explanation,
            "next_action": self.next_action,
            "recognized_zero_paid_orders": self.recognized_zero_paid_orders,
            "recognized_zero_paid_qty": self.recognized_zero_paid_qty,
            "approved_sample_qty": self.approved_sample_qty,
            "approved_sample_amount": self.approved_sample_amount,
            "salestat_qty": self.salestat_qty,
            "salestat_amount": self.salestat_amount,
            "mart_sample_qty": self.mart_sample_qty,
            "mart_gross_qty": self.mart_gross_qty,
        }


def _number(value: Any) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal("0")


def _sample_values(
    session: Session,
    account: str,
    day: date,
    store: str,
    item: str,
    msku: str,
) -> tuple[Any, Any, Any]:
    params = {
        "account": account,
        "day": day,
        "store": store,
        "item": item,
        "msku": msku,
    }
    samples = (
        session.execute(
            text(
                "select count(distinct platform_order_no) filter ("
                "where order_total_amount=0 and is_cancelled=false) as zero_orders,"
                "coalesce(sum(quantity) filter ("
                "where order_total_amount=0 and is_cancelled=false),0) zero_qty,"
                "coalesce(sum(quantity) filter ("
                "where is_valid_sample=true and is_cancelled=false),0) approved_qty,"
                "coalesce(sum(quantity*unit_price_amount) filter ("
                "where is_valid_sample=true and is_cancelled=false),0) approved_amount "
                "from fact_walmart_sample_order_items "
                "where source_account_ref=:account and business_date_utc_minus_7=:day "
                "and store_id=:store and item_id=:item and trim(msku)=:msku"
            ),
            params,
        ).mappings().one()
    )
    salestat = (
        session.execute(
            text(
                "select count(*) facts,coalesce(sum(sales_qty),0) qty,"
                "coalesce(sum(sales_amount),0) amount "
                "from fact_walmart_sales_item_daily "
                "where source_account_ref=:account and business_date_la=:day "
                "and store_id=:store and item_id=:item and trim(msku)=:msku "
                "and allocation_status='direct'"
            ),
            params,
        ).mappings().one()
    )
    mart = (
        session.execute(
            text(
                "select sample_qty,gross_sales_qty,calculation_warnings_json "
                "from mart_daily_sales_item_day where source_account_ref=:account "
                "and business_date_la=:day and store_id=:store and item_id=:item "
                "and trim(msku)=:msku limit 1"
            ),
            params,
        ).mappings().first()
    )
    return samples, salestat, mart


def diagnose_sync_anomaly(
    session: Session,
    anomaly: IntegrationSyncAnomaly,
) -> AnomalyDiagnosis:
    """Re-evaluate a row from current FACT and MART, not stale details JSON."""
    if anomaly.error_code != SAMPLE_EXCEEDANCE_CODE:
        return AnomalyDiagnosis(
            "manual_review",
            "该类异常需要核对来源报表及商品归属，不能仅靠点击重算修正金额。",
            "按照页面的中文指引核对原始报表；提交证据并标记待修复。",
        )
    if not all((anomaly.store_id, anomaly.item_id, anomaly.msku)):
        return AnomalyDiagnosis(
            "manual_review",
            "这是一条日期级汇总异常，没有足够的商品身份，不能当成新的送样订单。",
            "先查看同一业务日的商品明细异常，不要重复补录送样。",
        )
    samples, sale, mart = _sample_values(
        session,
        anomaly.source_account_ref,
        anomaly.business_date,
        str(anomaly.store_id),
        str(anomaly.item_id),
        str(anomaly.msku).strip(),
    )
    recognized = _number(samples["zero_qty"])
    approved = _number(samples["approved_qty"])
    approved_amount = _number(samples["approved_amount"])
    gross = _number(sale["qty"])
    gross_amount = _number(sale["amount"])
    fields = {
        "recognized_zero_paid_orders": int(samples["zero_orders"]),
        "recognized_zero_paid_qty": str(recognized),
        "approved_sample_qty": str(approved),
        "approved_sample_amount": str(approved_amount),
        "salestat_qty": str(gross),
        "salestat_amount": str(gross_amount),
        "mart_sample_qty": str(mart["sample_qty"]) if mart is not None else None,
        "mart_gross_qty": str(mart["gross_sales_qty"]) if mart is not None else None,
    }

    # Do not lose real zero-dollar orders merely because only a subset has
    # passed attribution/accounting checks.
    if recognized > approved:
        return AnomalyDiagnosis(
            "needs_identity",
            "已发现0美元且未取消的送样，但还有部分未完成商品归属或安全核算。",
            "保留零元送样记录，核对 Item ID、订单日期和 SaleStat；暂不扣减差额。",
            **fields,
        )
    if approved > gross or approved_amount > gross_amount:
        return AnomalyDiagnosis(
            "blocked_by_salestat",
            "送样已经确认，但数量或参考金额超过同日 SaleStat。可能是统计口径或日期差异，不能直接把销售扣成负数。",
            "请先确认 SaleStat 是否包含零元送样，提供订单和 SaleStat 凭据；不要删减已确认送样。",
            **fields,
        )
    if int(sale["facts"]) == 0:
        return AnomalyDiagnosis(
            "source_missing",
            "当前没有对应的 SaleStat 商品数据，暂时无法安全计算收入。",
            "核对商品、店铺和美国业务日期；待来源数据正确后重新核对。",
            **fields,
        )
    if mart is None:
        return AnomalyDiagnosis(
            "ready_for_replay",
            "来源数据已经对齐，但每日销售还没有对应的计算结果。",
            "可走受控的指定日期重算；历史锁账日期不得自动改账。",
            **fields,
        )
    warnings = mart["calculation_warnings_json"] or []
    if isinstance(warnings, list) and "sample_exceeds_salestat_pending_review" in warnings:
        return AnomalyDiagnosis(
            "ready_for_replay",
            "来源数据现在已对齐，但每日销售仍保留以前的财务异常标记。",
            "可在审核重算范围后重新计算，并再次核对结果。",
            **fields,
        )
    if _number(mart["sample_qty"]) != approved or _number(mart["gross_sales_qty"]) != gross:
        return AnomalyDiagnosis(
            "ready_for_replay",
            "每日销售记录与当前来源事实不一致，需要重算才能完成修复。",
            "走受控的指定日期重算；重算后自动复验，再关闭异常。",
            **fields,
        )
    return AnomalyDiagnosis(
        "verified",
        "当前送样、SaleStat 与每日销售结果已经一致，无须补录或重算。",
        "可以自动关闭这条已解决的明细异常，保留原始操作历史。",
        **fields,
    )

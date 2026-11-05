"""手工录入流水：现金账户，或者银行 / 平台流水里没有的那笔（比如另外扣的手续费）。

每录一笔，后台记成一次「手工导入」（一个批次 + 一个虚拟文件），流水本身和导入的流水
放在同一张表里，所以分类、初审终审、剔除、配对、导出都照常走，不另做一套。
录错了用剔除；还没审核的也可以在导入记录里作废这一批。

手工账户（平台 = manual）没有银行给的余额，读的时候从第一笔往下累计（剔除的部分不算）。
现金的期初就录成第一笔「期初余额」。
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.finance_cashflow.account_schemas import ManualLineCreate, ManualLineCreated
from app.modules.finance_cashflow.accounts import PROVIDER_MANUAL
from app.modules.finance_cashflow.models import (
    FinanceCashAccount,
    FinanceCashCategory,
    FinanceCashImport,
    FinanceCashImportQuality,
    FinanceCashLine,
    FinanceCashLineEvent,
    FinanceCashLineOccurrence,
    FinanceCashLineState,
    FinanceCashRawFile,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
KIND_MANUAL_CREATE = "manual_create"
MANUAL_FILE_NAME = "手工录入"
MANUAL_PARSER_VERSION = "manual/1"
MANUAL_SOURCE_REF = "手工"
STATUS_PARSED = "parsed"
STATUS_VOIDED = "voided"


class ManualLineRejectedError(ValueError):
    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _today() -> date:
    return datetime.now(SHANGHAI).date()


def _replay(session: Session, key: str | None) -> ManualLineCreated | None:
    if not key:
        return None
    seen = session.scalars(
        select(FinanceCashLineEvent).where(FinanceCashLineEvent.idempotency_key == key)
    ).first()
    if seen is None:
        return None
    if seen.kind != KIND_MANUAL_CREATE:
        raise ManualLineRejectedError("这个幂等键已经用在别的操作上", status_code=409)
    line = session.get(FinanceCashLine, seen.line_uid)
    return ManualLineCreated(
        line_uid=seen.line_uid, account_key=line.account_key if line else "", replayed=True
    )


def create_manual_line(
    session: Session, payload: ManualLineCreate, *, actor: str, request_id: str | None
) -> ManualLineCreated:
    replayed = _replay(session, payload.idempotency_key)
    if replayed is not None:
        return replayed
    account = session.get(FinanceCashAccount, payload.account_key)
    if account is None:
        raise ManualLineRejectedError("账户不存在", status_code=404)
    if not account.is_active:
        raise ManualLineRejectedError("这个账户已停用，不能再录")
    if account.currency_code != "CNY":
        raise ManualLineRejectedError("手工录入只记人民币")
    if payload.business_date > _today():
        raise ManualLineRejectedError("日期不能晚于今天")
    if payload.category_code is not None and (
        session.get(FinanceCashCategory, payload.category_code) is None
    ):
        raise ManualLineRejectedError("类别不存在")
    description = payload.description.strip()
    if not description:
        raise ManualLineRejectedError("要写摘要")
    amount = payload.amount if payload.direction == "in" else -payload.amount

    line_uid = "M" + uuid4().hex[:15]
    batch = FinanceCashImport(
        import_id=uuid4(), uploader=actor, status=STATUS_PARSED, request_id=request_id
    )
    session.add(batch)
    session.flush()
    raw = FinanceCashRawFile(
        import_id=batch.import_id,
        file_name=MANUAL_FILE_NAME,
        sha256=hashlib.sha256(line_uid.encode()).hexdigest(),
        size_bytes=0,
        storage_path="",
        provider=PROVIDER_MANUAL,
        account_keys=[account.account_key],
        parser_version=MANUAL_PARSER_VERSION,
        status=STATUS_PARSED,
    )
    session.add(raw)
    session.flush()
    # 同一天里排在已有流水后面（手工账户的余额按这个顺序累计）。
    order = (
        session.scalar(
            select(func.max(FinanceCashLine.file_row_order)).where(
                FinanceCashLine.account_key == account.account_key,
                FinanceCashLine.business_date == payload.business_date,
            )
        )
        or 0
    ) + 1
    session.add(
        FinanceCashLine(
            line_uid=line_uid,
            account_key=account.account_key,
            business_date=payload.business_date,
            source_time=None,
            source_timezone="Asia/Shanghai",
            source_time_raw=payload.business_date.isoformat(),
            amount=amount,
            currency_code=account.currency_code,
            balance_after=None,
            counterparty_name=payload.counterparty_name.strip(),
            counterparty_account_last4="",
            description=description,
            memo=payload.memo.strip(),
            source_ref=MANUAL_SOURCE_REF,
            dup_ordinal=1,
            statement_row_no=1,
            file_row_order=order,
            first_import_id=batch.import_id,
            first_raw_file_id=raw.file_id,
            last_import_id=batch.import_id,
            last_raw_file_id=raw.file_id,
            parser_version=MANUAL_PARSER_VERSION,
        )
    )
    session.flush()
    session.add(
        FinanceCashLineOccurrence(
            line_uid=line_uid,
            raw_file_id=raw.file_id,
            import_id=batch.import_id,
            statement_row_no=1,
            file_row_order=order,
        )
    )
    session.add(
        FinanceCashImportQuality(
            file_id=raw.file_id,
            rows_parsed=1,
            rows_new=1,
            rows_duplicate=0,
            balance_chain_ok=None,
            warnings=[],
        )
    )
    if payload.category_code:
        session.add(FinanceCashLineState(line_uid=line_uid, manual_category=payload.category_code))
    session.add(
        FinanceCashLineEvent(
            line_uid=line_uid,
            kind=KIND_MANUAL_CREATE,
            payload={
                "account_key": account.account_key,
                "business_date": payload.business_date.isoformat(),
                "amount": format(amount, "f"),
                "category_code": payload.category_code,
            },
            actor=actor,
            request_id=request_id,
            idempotency_key=payload.idempotency_key,
        )
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        replayed = _replay(session, payload.idempotency_key)
        if replayed is None:
            raise
        return replayed
    return ManualLineCreated(line_uid=line_uid, account_key=account.account_key)


def running_balances(session: Session) -> dict[str, Decimal]:
    """手工账户每笔之后的余额：按日期、同日录入顺序累计；剔除的金额不算进余额。"""
    rows = session.execute(
        select(
            FinanceCashLine.line_uid,
            FinanceCashLine.account_key,
            FinanceCashLine.business_date,
            FinanceCashLine.file_row_order,
            FinanceCashLine.created_at,
            FinanceCashLine.amount,
            FinanceCashLineState.exclude_amount,
        )
        .join(FinanceCashAccount, FinanceCashAccount.account_key == FinanceCashLine.account_key)
        .outerjoin(FinanceCashLineState, FinanceCashLineState.line_uid == FinanceCashLine.line_uid)
        .where(
            FinanceCashAccount.provider == PROVIDER_MANUAL,
            FinanceCashLine.voided_at.is_(None),
        )
    ).all()
    return accumulate(rows)


def apply_running_balances(session: Session, items: Iterable[Any]) -> None:
    """把手工账户的累计余额填到日记账返回的行上（导入的银行流水不动）。"""
    rows = list(items)
    if not rows:
        return
    running = running_balances(session)
    for row in rows:
        if row.line_uid in running:
            row.balance_after = running[row.line_uid]


def accumulate(rows: Iterable[Any]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    totals: dict[str, Decimal] = {}
    ordered = sorted(
        rows,
        key=lambda r: (
            r.account_key,
            r.business_date,
            r.file_row_order,
            r.created_at or datetime.min.replace(tzinfo=UTC),
            r.line_uid,
        ),
    )
    for row in ordered:
        amount = Decimal(row.amount)
        excluded = Decimal(row.exclude_amount or 0)
        effective = amount - excluded if amount > 0 else amount + excluded
        totals[row.account_key] = totals.get(row.account_key, Decimal(0)) + effective
        out[row.line_uid] = totals[row.account_key]
    return out


__all__ = [
    "KIND_MANUAL_CREATE",
    "ManualLineRejectedError",
    "apply_running_balances",
    "create_manual_line",
    "running_balances",
]

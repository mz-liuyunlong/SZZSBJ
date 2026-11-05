"""账户管理：财务在页面上新增 / 修改 / 停用账户（dim_finance_cash_accounts）。

- 识别值（完整账号、用户号）只写不读：返回里只说填了哪几项，列表只显示尾号。
- 已经有流水的账户不能改平台和币种，也不能删除，只能停用。
- 停用后导入时不再认这个账户，已有流水照常显示。
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.finance_cashflow.account_schemas import (
    CashAccountAdminRead,
    CashAccountCreate,
    CashAccountUpdate,
)
from app.modules.finance_cashflow.deploy_load import CURRENCIES, PROVIDERS
from app.modules.finance_cashflow.models import FinanceCashAccount, FinanceCashLine
from app.modules.finance_cashflow.parsing.seed import cmb_key

PROVIDER_MANUAL = "manual"
KEY_PREFIX = {
    "boc": "BOC",
    "shenzhen_rural_bank": "YZ",
    "payoneer": "PAYONEER",
    "worldfirst": "WORLDFIRST",
    "pingpong": "PINGPONG",
    "cmb": "CMB",
    "manual": "MANUAL",
}
DIGIT_FIELDS = ("inquiry_account", "account_no", "user_no")
PAYONEER_FEATURES = frozenset({"seller", "collector"})


class AccountRejectedError(ValueError):
    """填写不合格。消息给财务看，不带识别值。"""

    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AccountNotFoundError(Exception):
    pass


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def clean_identity(provider: str, currency: str, raw: dict[str, Any]) -> dict[str, Any]:
    """按平台挑出导入时认账户要用的字段，其他一律丢掉。"""
    if provider == "boc":
        inquiry = _digits(raw.get("inquiry_account"))
        if len(inquiry) < 6:
            raise AccountRejectedError("中行账户要填查询账号（交易明细表头里的那个）")
        return {"inquiry_account": inquiry, "currency": currency}
    if provider in ("shenzhen_rural_bank", "cmb"):
        account_no = _digits(raw.get("account_no"))
        if len(account_no) < 8:
            raise AccountRejectedError("要填完整银行账号")
        return {"account_no": account_no}
    if provider == "payoneer":
        feature = str(raw.get("feature") or "")
        if feature not in PAYONEER_FEATURES:
            raise AccountRejectedError("派安盈要选是卖家收款户还是归集户")
        return {"feature": feature}
    if provider == "pingpong":
        user_no = _digits(raw.get("user_no"))
        if not user_no:
            raise AccountRejectedError("PingPong 要填用户编号")
        if raw.get("main"):
            return {"user_no": user_no, "main": True}
        account_id = str(raw.get("account_id") or "").strip()
        if not account_id:
            raise AccountRejectedError("PingPong 店铺子账户要填子账户 ID")
        return {"user_no": user_no, "account_id": account_id}
    return {}  # worldfirst / manual：不用识别值


def _last4(provider: str, identity: dict[str, Any], given: str | None) -> str:
    if given and given.strip():
        digits = _digits(given)
        if not digits:
            raise AccountRejectedError("尾号只能填数字")
        return digits[-4:]
    for field in DIGIT_FIELDS:
        if identity.get(field) and field != "user_no":
            return str(identity[field])[-4:]
    return ""


class AccountAdminService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _line_counts(self) -> dict[str, int]:
        return {
            key: count
            for key, count in self.session.execute(
                select(FinanceCashLine.account_key, func.count())
                .where(FinanceCashLine.voided_at.is_(None))
                .group_by(FinanceCashLine.account_key)
            )
        }

    @staticmethod
    def _read(row: FinanceCashAccount, line_count: int) -> CashAccountAdminRead:
        identity = dict(row.identity_hint or {})
        return CashAccountAdminRead(
            account_key=row.account_key,
            display_name=row.display_name,
            entity=row.entity,
            currency_code=row.currency_code,
            kind=row.kind,
            provider=row.provider,
            account_no_last4=row.account_no_last4,
            is_active=row.is_active,
            sort_order=row.sort_order,
            identity_fields=sorted(key for key, value in identity.items() if value),
            pingpong_main=bool(identity.get("main")) if row.provider == "pingpong" else None,
            payoneer_feature=identity.get("feature") if row.provider == "payoneer" else None,
            line_count=line_count,
        )

    def list_accounts(self) -> list[CashAccountAdminRead]:
        counts = self._line_counts()
        rows = self.session.scalars(
            select(FinanceCashAccount).order_by(
                FinanceCashAccount.sort_order, FinanceCashAccount.account_key
            )
        ).all()
        return [self._read(row, counts.get(row.account_key, 0)) for row in rows]

    @staticmethod
    def _check_basic(provider: str, currency: str) -> None:
        if provider not in PROVIDERS:
            raise AccountRejectedError("平台不认识")
        if currency not in CURRENCIES:
            raise AccountRejectedError("币种只能是 CNY、USD、CNH")

    def _check_conflict(
        self, provider: str, currency: str, identity: dict[str, Any], skip_key: str | None
    ) -> None:
        """同一份流水不能同时认成两个启用中的账户。"""
        others = [
            row
            for row in self.session.scalars(
                select(FinanceCashAccount).where(
                    FinanceCashAccount.provider == provider,
                    FinanceCashAccount.is_active.is_(True),
                )
            )
            if row.account_key != skip_key
        ]
        for row in others:
            other = dict(row.identity_hint or {})
            same = False
            if provider == "worldfirst":
                same = True
            elif provider == "boc":
                same = other.get("inquiry_account") == identity.get("inquiry_account") and (
                    other.get("currency") == currency
                )
            elif provider == "shenzhen_rural_bank":
                same = other.get("account_no") == identity.get("account_no")
            elif provider == "cmb":
                same = (
                    cmb_key(other.get("account_no", "")) == cmb_key(identity["account_no"])
                    and row.currency_code == currency
                )
            elif provider == "payoneer":
                same = other.get("feature") == identity.get("feature")
            elif provider == "pingpong":
                if identity.get("main"):
                    same = (
                        bool(other.get("main"))
                        and other.get("user_no") == identity.get("user_no")
                        and row.currency_code == currency
                    )
                else:
                    same = bool(identity.get("account_id")) and other.get(
                        "account_id"
                    ) == identity.get("account_id")
            if same:
                raise AccountRejectedError(
                    f"已经有启用中的账户用同样的账号：{row.display_name}", status_code=409
                )

    def _new_key(self, provider: str, currency: str, last4: str) -> str:
        base = "_".join(part for part in (KEY_PREFIX[provider], currency, last4) if part)
        taken = set(self.session.scalars(select(FinanceCashAccount.account_key)))
        if base not in taken:
            return base
        index = 2
        while f"{base}_{index}" in taken:
            index += 1
        return f"{base}_{index}"

    def create(self, payload: CashAccountCreate) -> CashAccountAdminRead:
        provider, currency = payload.provider, payload.currency_code
        self._check_basic(provider, currency)
        identity = clean_identity(provider, currency, payload.identity)
        self._check_conflict(provider, currency, identity, None)
        last4 = _last4(provider, identity, payload.account_no_last4)
        sort_order = payload.sort_order
        if sort_order is None:
            sort_order = (
                self.session.scalar(select(func.max(FinanceCashAccount.sort_order))) or 0
            ) + 1
        row = FinanceCashAccount(
            account_key=self._new_key(provider, currency, last4),
            display_name=payload.display_name.strip(),
            entity=payload.entity.strip(),
            currency_code=currency,
            kind=payload.kind.strip(),
            provider=provider,
            account_no_last4=last4,
            identity_hint=identity,
            is_active=True,
            sort_order=sort_order,
        )
        self.session.add(row)
        self.session.flush()
        result = self._read(row, 0)
        self.session.commit()
        return result

    def update(self, account_key: str, payload: CashAccountUpdate) -> CashAccountAdminRead:
        row = self.session.get(FinanceCashAccount, account_key, with_for_update=True)
        if row is None:
            raise AccountNotFoundError
        line_count = self._line_counts().get(account_key, 0)
        provider = payload.provider or row.provider
        currency = payload.currency_code or row.currency_code
        if line_count and (provider != row.provider or currency != row.currency_code):
            raise AccountRejectedError("这个账户已经有流水，不能改平台或币种", status_code=409)
        self._check_basic(provider, currency)
        if payload.identity is not None:
            identity = clean_identity(provider, currency, payload.identity)
        elif provider != row.provider:
            raise AccountRejectedError("换了平台要重新填识别值")
        else:
            identity = dict(row.identity_hint or {})
            if provider == "boc":
                identity["currency"] = currency
        active = row.is_active if payload.is_active is None else payload.is_active
        if active:
            self._check_conflict(provider, currency, identity, account_key)
        if payload.display_name is not None:
            row.display_name = payload.display_name.strip()
        if payload.entity is not None:
            row.entity = payload.entity.strip()
        if payload.kind is not None:
            row.kind = payload.kind.strip()
        if payload.sort_order is not None:
            row.sort_order = payload.sort_order
        if payload.account_no_last4 is not None or payload.identity is not None:
            row.account_no_last4 = _last4(provider, identity, payload.account_no_last4)
        row.provider, row.currency_code = provider, currency
        row.identity_hint = identity
        row.is_active = active
        self.session.flush()
        result = self._read(row, line_count)
        self.session.commit()
        return result


CASH_ACCOUNT_NAME = "现金"


def ensure_cash_account(session: Session, *, apply: bool) -> str:
    """补「现金」账户。已经有（包括被停用的）就不动，返回 exists；否则 created / would_create。"""
    existing = session.scalar(
        select(FinanceCashAccount).where(
            FinanceCashAccount.provider == PROVIDER_MANUAL,
            FinanceCashAccount.currency_code == "CNY",
            FinanceCashAccount.display_name == CASH_ACCOUNT_NAME,
        )
    )
    if existing is not None:
        return "exists"
    if not apply:
        return "would_create"
    AccountAdminService(session).create(
        CashAccountCreate(
            display_name=CASH_ACCOUNT_NAME,
            entity=CASH_ACCOUNT_NAME,
            currency_code="CNY",
            kind=CASH_ACCOUNT_NAME,
            provider=PROVIDER_MANUAL,
        )
    )
    return "created"

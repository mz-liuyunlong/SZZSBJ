"""上线时导入不进仓库的配置：账户（含银行账号）、带名字的分类规则、剔除清单。

可重复执行：账户按 account_key 更新；source=deploy 的规则整组替换；清单按 entry_key 更新。
只输出条数，不输出账号、名字、金额。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.modules.finance_cashflow.models import (
    FinanceCashAccount,
    FinanceCashCategory,
    FinanceCashClassifyRule,
    FinanceCashExclusion,
)

PROVIDERS = frozenset({"boc", "shenzhen_rural_bank", "payoneer", "worldfirst", "pingpong"})
CURRENCIES = frozenset({"CNY", "USD", "CNH"})
RULE_TYPES = frozenset({"party", "text"})
ACCOUNT_REQUIRED = ("account_key", "display_name", "entity", "currency_code", "kind", "provider")


class DeployFileError(ValueError):
    """文件内容不合格。消息只写第几条和哪个字段，不带值。"""


@dataclass(frozen=True)
class LoadCounts:
    accounts: int
    rules: int
    exclusions: int


def _accounts(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(raw, start=1):
        for key in ACCOUNT_REQUIRED:
            if not str(row.get(key) or "").strip():
                raise DeployFileError(f"accounts 第 {index} 条缺 {key}")
        if row["provider"] not in PROVIDERS:
            raise DeployFileError(f"accounts 第 {index} 条 provider 不认识")
        if row["currency_code"] not in CURRENCIES:
            raise DeployFileError(f"accounts 第 {index} 条 currency_code 不认识")
        if row["account_key"] in seen:
            raise DeployFileError(f"accounts 第 {index} 条 account_key 重复")
        seen.add(row["account_key"])
        identity = row.get("identity") or {}
        if not isinstance(identity, dict):
            raise DeployFileError(f"accounts 第 {index} 条 identity 必须是对象")
        out.append(
            {
                "account_key": row["account_key"],
                "display_name": row["display_name"],
                "entity": row["entity"],
                "currency_code": row["currency_code"],
                "kind": row["kind"],
                "provider": row["provider"],
                "account_no_last4": str(row.get("account_no_last4") or "")[-4:],
                "identity_hint": identity,
                "is_active": bool(row.get("is_active", True)),
                "sort_order": int(row.get("sort_order") or index),
            }
        )
    return out


def _rules(raw: list[dict[str, Any]], categories: frozenset[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, row in enumerate(raw, start=1):
        if row.get("rule_type") not in RULE_TYPES:
            raise DeployFileError(f"rules 第 {index} 条 rule_type 只能是 party 或 text")
        if row.get("category_code") not in categories:
            raise DeployFileError(f"rules 第 {index} 条 category_code 不存在")
        pattern = str(row.get("pattern") or "")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise DeployFileError(f"rules 第 {index} 条 pattern 不是合法正则") from exc
        if not pattern:
            raise DeployFileError(f"rules 第 {index} 条缺 pattern")
        out.append(
            {
                "rule_type": row["rule_type"],
                "pattern": pattern,
                "category_code": row["category_code"],
                "sort_order": int(row["sort_order"]),
                "source": "deploy",
            }
        )
    return out


def _exclusions(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, row in enumerate(raw, start=1):
        if not str(row.get("entry_key") or "").strip():
            raise DeployFileError(f"exclusions 第 {index} 条缺 entry_key")
        ref = str(row.get("ref") or "").strip() or None
        txn_date = date.fromisoformat(row["txn_date"]) if row.get("txn_date") else None
        if not ref and txn_date is None:
            raise DeployFileError(f"exclusions 第 {index} 条要有 ref，或者 txn_date")
        try:
            amount = Decimal(str(row.get("amount_cny")))
        except InvalidOperation as exc:
            raise DeployFileError(f"exclusions 第 {index} 条 amount_cny 不是数字") from exc
        if not amount.is_finite() or amount <= 0:
            raise DeployFileError(f"exclusions 第 {index} 条 amount_cny 要大于 0")
        if not str(row.get("reason") or "").strip():
            raise DeployFileError(f"exclusions 第 {index} 条缺 reason")
        out.append(
            {
                "entry_key": row["entry_key"],
                "ref": ref,
                "txn_date": txn_date,
                "account_key": row.get("account_key") or None,
                "summary_contains": row.get("summary_contains") or None,
                "amount_cny": amount,
                "reason": row["reason"],
                "registered_by": str(row.get("registered_by") or "导入脚本"),
                "registered_on": (
                    date.fromisoformat(row["registered_on"]) if row.get("registered_on") else None
                ),
            }
        )
    return out


def load_deploy_data(session: Session, data: dict[str, Any]) -> LoadCounts:
    """校验并写入，不提交；由调用方决定提交还是回滚（演练）。"""
    categories = frozenset(session.scalars(select(FinanceCashCategory.code)))
    accounts = _accounts(data.get("accounts") or [])
    rules = _rules(data.get("rules") or [], categories)
    exclusions = _exclusions(data.get("exclusions") or [])
    for row in accounts:
        statement = pg_insert(FinanceCashAccount).values(**row)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=["account_key"],
                set_={key: statement.excluded[key] for key in row if key != "account_key"},
            )
        )
    if "rules" in data:
        session.execute(
            delete(FinanceCashClassifyRule).where(FinanceCashClassifyRule.source == "deploy")
        )
        session.add_all(FinanceCashClassifyRule(**row) for row in rules)
    for row in exclusions:
        statement = pg_insert(FinanceCashExclusion).values(**row)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=["entry_key"],
                set_={key: statement.excluded[key] for key in row if key != "entry_key"},
            )
        )
    session.flush()
    return LoadCounts(accounts=len(accounts), rules=len(rules), exclusions=len(exclusions))

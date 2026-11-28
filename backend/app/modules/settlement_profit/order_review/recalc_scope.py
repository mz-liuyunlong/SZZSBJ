"""订单审核：成本数据同步之后，算出真正受影响的 (店铺, 账期)，只重算这些期（#377 终审）。

同步处理器只记"内容真的变了"的行（新行、行 hash 变了、被删掉的行），按两种键记：
- (店铺, MSKU)：发货单明细、成本计价流水、出库单明细里的 MSKU；发货单抬头按它当前的明细取 MSKU。
- (店铺, 平台订单号)：成本计价流水的订单号、出库单的平台订单号（自发货订单行按订单号找出库单）。
店铺为空（成本计价流水没认出店铺）= 任何店铺。MSKU 比较一律 lower(btrim())，
和 Listing 匹配口径一致。两种键都拿不到的行记进 unresolved：不投递、不退回全量，
由执行层记日志和运行事件，财务在页面「重算」补。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from app.modules.settlement_profit.models import SettlementOrderLine

CHUNK = 500


def norm_msku(value: object) -> str | None:
    """MSKU 归一：去首尾空格、转小写（数据库侧用 lower(btrim())，同一口径）。"""
    if not isinstance(value, str):
        return None
    text = value.strip(" ").lower()
    return text or None


def norm_order(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip(" ")
    return text or None


@dataclass(slots=True)
class AffectedKeys:
    """一次同步里内容真的变了的行，换算成订单行能对上的键。"""

    mskus: set[tuple[str | None, str]] = field(default_factory=set)
    orders: set[tuple[str | None, str]] = field(default_factory=set)
    unresolved: int = 0

    def add(
        self,
        store_id: str | None,
        *,
        mskus: Iterable[object] = (),
        orders: Iterable[object] = (),
    ) -> None:
        """记一行；这一行 MSKU 和订单号都拿不到就算 unresolved。"""
        store = store_id or None
        found = False
        for raw in mskus:
            msku = norm_msku(raw)
            if msku is not None:
                self.mskus.add((store, msku))
                found = True
        for raw in orders:
            order = norm_order(raw)
            if order is not None:
                self.orders.add((store, order))
                found = True
        if not found:
            self.unresolved += 1

    def merge(self, other: AffectedKeys) -> None:
        self.mskus |= other.mskus
        self.orders |= other.orders
        self.unresolved += other.unresolved

    def clear(self) -> None:
        self.mskus.clear()
        self.orders.clear()
        self.unresolved = 0

    def is_empty(self) -> bool:
        return not self.mskus and not self.orders and not self.unresolved

    def summary(self) -> dict[str, object]:
        """只给条数，不带 MSKU / 订单号原文（运行事件和日志用）。"""
        return {
            "msku_keys": len(self.mskus),
            "order_keys": len(self.orders),
            "unresolved_rows": self.unresolved,
        }


def _chunks(values: Sequence[Any]) -> Iterable[Sequence[Any]]:
    for start in range(0, len(values), CHUNK):
        yield values[start : start + CHUNK]


def affected_periods(
    session: Session, *, source_account_ref: str, keys: AffectedKeys
) -> list[tuple[str, str]]:
    """当前版本订单行里对得上这些键的 (店铺, 账期)；没对上的键不产生任何重算。"""
    line = SettlementOrderLine
    msku = func.lower(func.btrim(line.msku))
    order = func.btrim(line.platform_order_no)
    base = (
        select(line.store_id, line.period_key)
        .where(line.source_account_ref == source_account_ref, line.is_current.is_(True))
        .distinct()
    )
    found: set[tuple[str, str]] = set()

    def collect(condition: Any) -> None:
        for store_id, period_key in session.execute(base.where(condition)).all():
            found.add((store_id, period_key))

    store_mskus = sorted((s, m) for s, m in keys.mskus if s is not None)
    any_mskus = sorted({m for s, m in keys.mskus if s is None})
    store_orders = sorted((s, o) for s, o in keys.orders if s is not None)
    any_orders = sorted({o for s, o in keys.orders if s is None})
    for part in _chunks(store_mskus):
        collect(tuple_(line.store_id, msku).in_(list(part)))
    for part in _chunks(any_mskus):
        collect(msku.in_(list(part)))
    for part in _chunks(store_orders):
        collect(tuple_(line.store_id, order).in_(list(part)))
    for part in _chunks(any_orders):
        collect(order.in_(list(part)))
    return sorted(found)

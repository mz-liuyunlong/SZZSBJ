"""回款对账的纯规则（不碰数据库，方便单测）。口径：Rocky 2026-11-10 批准。

自动配对：到账日期在账单日之后 0–7 天、到账账户是这家店（账单日当天生效）的收款账户、
付款方信息里带这家店的收款账户识别（填了才比）、币种一致、金额差不超过 0.01，就配上。
合并打款：一笔到账等于同一收款账户下几期应付相加（2–4 期），也自动配给这几期。
一笔到账能配出不止一种结果、或一期被几笔到账同时争抢，都不自动配，留给财务手动配。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from itertools import combinations
from typing import Final

TOLERANCE: Final = Decimal("0.01")
ARRIVAL_WINDOW_DAYS: Final = 7
MAX_MERGED_PERIODS: Final = 4
MAX_COMBO_CANDIDATES: Final = 12

# 一期账单的回款状态
STATE_VOIDED: Final = "voided"  # 账单作废
STATE_NO_PAY: Final = "no_pay"  # 不需打款（不可付 / 应付 ≤ 0）
STATE_NOT_DUE: Final = "not_due"  # 还没到账单日
STATE_WAITING: Final = "waiting"  # 账单日后 7 天内，等到账
STATE_PAID: Final = "paid"  # 已到账，金额对上
STATE_MISMATCH: Final = "mismatch"  # 已到账，金额对不上（打款异常）
STATE_UNPAID: Final = "unpaid"  # 账单日过了 7 天还没到账（打款异常）
ANOMALY_STATES: Final = frozenset({STATE_VOIDED, STATE_MISMATCH, STATE_UNPAID})
MATCHED_STATES: Final = frozenset({STATE_PAID, STATE_MISMATCH})

# 审核阶段（照日记账）：待初审 → 待终审 → 已终审；终审驳回回到「驳回 · 待初审」。
STAGE_TODO: Final = "todo"
STAGE_OK1: Final = "ok1"
STAGE_REJ2: Final = "rej2"
STAGE_OK2: Final = "ok2"
FIRST_PENDING: Final = frozenset({STAGE_TODO, STAGE_REJ2})

KIND_REVIEW1_PASS: Final = "review1_pass"
KIND_REVIEW2_PASS: Final = "review2_pass"
KIND_REVIEW2_REJECT: Final = "review2_reject"
KIND_RESET: Final = "reset"
REVIEW_KINDS: Final = frozenset({KIND_REVIEW1_PASS, KIND_REVIEW2_PASS, KIND_REVIEW2_REJECT})


@dataclass(frozen=True)
class PeriodIn:
    store_id: str
    report_key: str
    report_date: date
    currency_code: str | None
    payable: Decimal
    status: str  # normal / not_payable / voided

    @property
    def key(self) -> tuple[str, str]:
        return (self.store_id, self.report_key)

    @property
    def needs_payment(self) -> bool:
        return self.status == "normal" and self.payable > 0


@dataclass(frozen=True)
class LineIn:
    line_uid: str
    account_key: str
    business_date: date
    amount: Decimal
    currency_code: str
    # 付款方 + 摘要 + 备注（原文），用来比收款账户识别（邮箱 / 公司名）
    text: str


@dataclass(frozen=True)
class AccountIn:
    store_id: str
    account_key: str
    payee: str
    effective_from: date
    effective_to: date | None

    def covers(self, day: date) -> bool:
        if day < self.effective_from:
            return False
        return self.effective_to is None or day <= self.effective_to


@dataclass(frozen=True)
class AutoMatch:
    line_uid: str
    periods: tuple[tuple[str, str], ...]


def account_for(accounts: Iterable[AccountIn], store_id: str, day: date) -> AccountIn | None:
    """这家店在 day 当天生效的收款账户；有几条同时生效取生效日最晚的一条。"""
    hits = [row for row in accounts if row.store_id == store_id and row.covers(day)]
    return max(hits, key=lambda row: row.effective_from) if hits else None


def payee_hit(payee: str, text: str) -> bool:
    """没填收款账户识别 = 只比账户；填了就要在付款方 / 摘要 / 备注里出现（不分大小写）。"""
    wanted = payee.strip().lower()
    return not wanted or wanted in text.lower()


def _candidates(
    line: LineIn, periods: Sequence[PeriodIn], accounts: Sequence[AccountIn]
) -> list[PeriodIn]:
    out = []
    for period in periods:
        days = (line.business_date - period.report_date).days
        if not 0 <= days <= ARRIVAL_WINDOW_DAYS:
            continue
        if period.currency_code and period.currency_code != line.currency_code:
            continue
        account = account_for(accounts, period.store_id, period.report_date)
        if account is None or account.account_key != line.account_key:
            continue
        if not payee_hit(account.payee, line.text):
            continue
        out.append(period)
    return out


def _solutions(line: LineIn, candidates: Sequence[PeriodIn]) -> list[tuple[PeriodIn, ...]]:
    singles = [(p,) for p in candidates if abs(line.amount - p.payable) <= TOLERANCE]
    if singles:
        return singles
    pool = sorted(candidates, key=lambda p: (p.report_date, p.store_id, p.report_key))
    if len(pool) > MAX_COMBO_CANDIDATES:
        return []
    found: list[tuple[PeriodIn, ...]] = []
    for size in range(2, min(MAX_MERGED_PERIODS, len(pool)) + 1):
        for combo in combinations(pool, size):
            if abs(line.amount - sum((p.payable for p in combo), Decimal(0))) <= TOLERANCE:
                found.append(combo)
                if len(found) > 1:
                    return found
    return found


def find_auto_matches(
    periods: Sequence[PeriodIn],
    lines: Sequence[LineIn],
    accounts: Sequence[AccountIn],
) -> list[AutoMatch]:
    """periods / lines 只传还没配对的。返回能唯一确定的配对。"""
    open_periods = [p for p in periods if p.needs_payment]
    proposals: list[AutoMatch] = []
    for line in sorted(lines, key=lambda x: (x.business_date, x.line_uid)):
        if line.amount <= 0:
            continue
        solutions = _solutions(line, _candidates(line, open_periods, accounts))
        if len(solutions) != 1:
            continue
        keys = tuple(p.key for p in solutions[0])
        proposals.append(AutoMatch(line_uid=line.line_uid, periods=keys))
    claims: dict[tuple[str, str], int] = defaultdict(int)
    for proposal in proposals:
        for key in proposal.periods:
            claims[key] += 1
    return [p for p in proposals if all(claims[key] == 1 for key in p.periods)]


def split_arrival(
    amount: Decimal, payables: Sequence[tuple[tuple[str, str], date, Decimal]]
) -> dict[tuple[str, str], Decimal]:
    """一笔到账分到几期：每期按应付记到账，差额全落在账单日最晚的那一期。"""
    ordered = sorted(payables, key=lambda item: (item[1], item[0]))
    out = {key: payable for key, _, payable in ordered}
    if ordered:
        last = ordered[-1][0]
        out[last] = amount - sum((payable for key, _, payable in ordered[:-1]), Decimal(0))
    return out


def pay_state(period: PeriodIn, arrived: Decimal | None, today: date) -> tuple[str, Decimal | None]:
    """返回（回款状态，差额 = 到账 − 应付）。"""
    if period.status == "voided":
        return STATE_VOIDED, None
    if arrived is not None:
        diff = arrived - period.payable
        return (STATE_PAID if abs(diff) <= TOLERANCE else STATE_MISMATCH), diff
    if not period.needs_payment:
        return STATE_NO_PAY, None
    if today < period.report_date:
        return STATE_NOT_DUE, None
    if today <= period.report_date + timedelta(days=ARRIVAL_WINDOW_DAYS):
        return STATE_WAITING, None
    return STATE_UNPAID, None


def stage_of(kinds: Iterable[str]) -> str:
    """按时间顺序重放审核记录得出当前阶段。"""
    stage = STAGE_TODO
    for kind in kinds:
        if kind == KIND_REVIEW1_PASS:
            stage = STAGE_OK1
        elif kind == KIND_REVIEW2_PASS:
            stage = STAGE_OK2
        elif kind == KIND_REVIEW2_REJECT:
            stage = STAGE_REJ2
        elif kind == KIND_RESET:
            stage = STAGE_TODO
    return stage


def review_allowed(kind: str, stage: str, matched: bool) -> bool:
    """初审要先配上到账；终审只在初审通过后。"""
    if not matched:
        return False
    if kind == KIND_REVIEW1_PASS:
        return stage in FIRST_PENDING
    if kind in {KIND_REVIEW2_PASS, KIND_REVIEW2_REJECT}:
        return stage == STAGE_OK1
    return False


def journal_tag(code: str, report_dates: Sequence[date]) -> str:
    """配上之后日记账备注：「平台回款 · 店铺 · 期次」，合并打款列出几期账单日。"""
    days = "、".join(day.isoformat() for day in sorted(set(report_dates)))
    return f"平台回款 · {code} · {days}"

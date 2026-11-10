"""日记账计算（纯函数）：分类、内部转账配对、折人民币、剔除、异常、审核状态流转。

规则类别、配对、剔除清单命中、异常都在读取时算，同一份输入永远得到同一个结果。
"""

from __future__ import annotations

import hashlib
import itertools
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

PAIR_DAYS = 15
ROUND_TOL = Decimal("1")
EXACT_TOL = Decimal("0.011")
BALANCE_TOL = Decimal("0.01")
Q4 = Decimal("0.0001")
ZERO = Decimal("0")
EXCLUDE_CATEGORY = "X01"
MAX_COMBO_POOL = 30
APPROVAL_REF = re.compile(r"^\d{12}$")
USD_IN_MEMO = re.compile(r"USD\s*([\d,]+(?:\.\d+)?)")
NOT_IN_JOURNAL = re.compile(r"忽略")
SOURCE_MANUAL = "人工"
SOURCE_RULE = "规则"
SOURCE_APPROVAL = "审批单"
SOURCE_APPROVAL_RULE = "审批单(规则)"

ALERT_BALANCE = "余额不连续"
ALERT_UNPAIRED = "内部转账未配对"
ALERT_EXCLUSION = "剔除未命中"  # 页面显示名是「要剔除的款没找到」
HINT_NOT_IN_JOURNAL = "对方账户不在日记账"
# 派安盈月结补充（rocky 11-05）：人民币以派安盈为准；差额只进异常，点「确认记为手续费」才拆。
ALERT_PAYONEER_FEE = "派安盈提现到账差额"
ALERT_PAYONEER_MISSING = "缺派安盈实际汇率"
ALERT_STATEMENT_UNMATCHED = "月结单有、流水没有"
ALERT_STATEMENT_AMBIGUOUS = "月结单匹配到多笔"
ALERT_STATEMENT_CONFLICT = "月结单前后不一致"
FEE_LAYER_PAYONEER = "payoneer"
FX_SOURCE_PAYONEER = "payoneer"
FX_SOURCE_LINGXING = "lingxing"
FX_SOURCE_PENDING = "pending"
PAYONEER_WITHDRAWAL = re.compile(r"^Payment to\b")
STATEMENT_TIME_TOL_SECONDS = 120
STATEMENT_DAY_TOL = 1

# 配上了但两边金额差一点（银行在中间扣了费）：差额挂在付出那笔上，等人点「确认记为手续费」。
ALERT_PAIR_GAP = "转账到账差额"
FEE_CATEGORY = "F01"
FEE_LAYER_DEFAULT = "fee"
# 带差额的自动配对（rocky 11-05）：对方尾号 = 另一个账户尾号，5 天内，差额不超过 0.5% 且不超过上限。
GAP_PAIR_DAYS = 5
GAP_PAIR_RATIO = Decimal("0.005")
GAP_PAIR_CAP = {"USD": Decimal("50"), "CNY": Decimal("300"), "CNH": Decimal("300")}
# 规则剔除只用于对冲行（目前是万里汇子账号归集到主账号的那笔，rocky 11-05 定的原因文字）。
AUTO_EXCLUDE_REASON = "已在主账号记录"

STAGE_TODO = "todo"
STAGE_REJ1 = "rej1"
STAGE_OK1 = "ok1"
STAGE_REJ2 = "rej2"
STAGE_OK2 = "ok2"
FIRST_PENDING = frozenset({STAGE_TODO, STAGE_REJ1, STAGE_REJ2})

KIND_REVIEW1_PASS = "review1_pass"
KIND_REVIEW1_REJECT = "review1_reject"
KIND_REVIEW2_PASS = "review2_pass"
KIND_REVIEW2_REJECT = "review2_reject"
KIND_SET_CATEGORY = "set_category"
KIND_ATTACH_REF = "attach_ref"
KIND_DETACH_REF = "detach_ref"
KIND_EXCLUDE = "exclude"
KIND_UNEXCLUDE = "unexclude"
KIND_REVIEW1_UNDO = "review1_undo"
KIND_REVIEW2_UNDO = "review2_undo"
KIND_SET_TEXT = "set_text"
KIND_SPLIT = "split"
KIND_SET_PART_CATEGORY = "set_part_category"
KIND_SET_PART_TEXT = "set_part_text"
KIND_UNSPLIT = "unsplit"
KIND_CONFIRM_FEE = "confirm_fee"
KIND_PAIR = "pair"
KIND_UNPAIR = "unpair"
PAIR_ID_MAX = 40
TEXT_MAX = 500
MAX_PARTS = 20
KIND_AUTO_RESET = "auto_reset"
# 拆分行挂审批单（Rocky 11-10：一笔付款对多张单，拆开后各行挂自己的单，类别跟着审批单走）。
KIND_ATTACH_PART_REF = "attach_part_ref"
KIND_DETACH_PART_REF = "detach_part_ref"
KIND_AUTO_ATTACH_REF = "auto_attach_ref"


@dataclass(frozen=True)
class Rule:
    rule_type: str  # party / text
    pattern: str
    category_code: str
    sort_order: int


class Classifier:
    """对方户名规则优先，其次摘要备注规则；同类按顺序取第一个命中。"""

    def __init__(self, rules: Iterable[Rule]) -> None:
        ordered = sorted(rules, key=lambda rule: rule.sort_order)
        self._party = [
            (re.compile(rule.pattern), rule.category_code)
            for rule in ordered
            if rule.rule_type == "party"
        ]
        self._text = [
            (re.compile(rule.pattern, re.IGNORECASE), rule.category_code)
            for rule in ordered
            if rule.rule_type == "text"
        ]

    def classify(self, text: str, party: str) -> str | None:
        if party:
            for pattern, code in self._party:
                if pattern.search(party):
                    return code
        for pattern, code in self._text:
            if pattern.search(text or ""):
                return code
        return None


@dataclass
class LineInput:
    line_uid: str
    account_key: str
    provider: str
    currency_code: str
    business_date: date
    amount: Decimal
    balance_after: Decimal | None
    description: str
    memo: str
    counterparty_name: str
    file_row_order: int
    manual_category: str | None = None
    refs: list[str] = field(default_factory=list)
    exclude_amount: Decimal | None = None
    # 挂的审批单带来的类别：表单写明的类别压过规则；按事由跑规则得来的只补空白。
    approval_category: str | None = None
    approval_rule_category: str | None = None
    # 拆分行（含手续费行，带 fee_layer）、手动配对号、对方账号尾号 / 本账户尾号（带差额配对用）。
    parts: list[dict[str, Any]] | None = None
    manual_pair: str | None = None
    counterparty_last4: str = ""
    account_last4: str = ""
    # 交易时间（UTC）：派安盈月结补充按它和金额对到这笔。
    source_time: datetime | None = None


@dataclass(frozen=True)
class StatementRow:
    """派安盈月结明细的一行（已去重前）；row_key 在全部批次里唯一。"""

    row_key: str
    account_key: str
    txn_id: str
    txn_time: datetime
    business_date: date
    description: str
    amount: Decimal
    currency_code: str
    transfer_amount: Decimal | None
    transfer_currency: str


@dataclass(frozen=True)
class StatementMatch:
    txn_id: str
    transfer_amount: Decimal | None
    transfer_currency: str


@dataclass(frozen=True)
class ExclusionEntry:
    entry_no: int
    ref: str | None
    txn_date: date | None
    account_key: str | None
    summary_contains: str | None
    amount_cny: Decimal
    reason: str
    registered_on: date | None = None


@dataclass
class ComputedLine:
    source: LineInput
    category_code: str | None
    category_source: str
    amount_cny: Decimal | None
    pair_id: str | None = None
    list_excluded_cny: Decimal = ZERO
    flags: list[str] = field(default_factory=list)
    auto_exclude_reason: str | None = None
    # 折人民币用的汇率和来源：payoneer = 派安盈实际到账；
    # lingxing = 领星当月汇率；pending = 等月结单。
    fx_rate: Decimal | None = None
    fx_source: str = ""
    statement: StatementMatch | None = None
    # 配对用的金额和币种（pair_value 算）：派安盈提现用派安盈写的到账金额；拆分过的不算手续费行。
    pair_amount: Decimal = ZERO
    pair_currency: str = ""


@dataclass(frozen=True)
class Alert:
    type: str
    account_key: str
    date: str
    message: str
    amount: Decimal | None
    # 金额的币种：剔除清单异常按人民币算，填 CNY；其他填这笔流水的币种。
    currency_code: str
    line_uid: str | None = None


@dataclass
class JournalResult:
    lines: list[ComputedLine]
    alerts: list[Alert]


def to_cny(amount: Decimal, currency_code: str, usd_rate: Decimal | None) -> Decimal | None:
    """CNY 原值；CNH 按 1:1（rocky 2026-11-05：现阶段汇率一样）；USD 用当月汇率，没有就空。"""
    if currency_code in {"CNY", "CNH"}:
        return amount
    if currency_code == "USD" and usd_rate is not None:
        return (amount * usd_rate).quantize(Q4, rounding=ROUND_HALF_UP)
    return None


def compute_journal(
    lines: Sequence[LineInput],
    classifier: Classifier,
    internal_categories: frozenset[str],
    usd_rate_of: Callable[[date], Decimal | None],
    exclusions: Sequence[ExclusionEntry] = (),
    statement_rows: Sequence[StatementRow] = (),
    today: date | None = None,
) -> JournalResult:
    matches, alerts = match_statement(lines, statement_rows, today)
    computed = [
        _classify_line(line, classifier, usd_rate_of, matches.get(line.line_uid)) for line in lines
    ]
    alerts.extend(_balance_alerts(lines))
    alerts.extend(_payoneer_fee_alerts(computed))
    alerts.extend(_pair_lines(computed, internal_categories))
    alerts.extend(_apply_exclusions(computed, exclusions))
    for item in computed:
        _add_exclude_flag(item)
    return JournalResult(lines=computed, alerts=alerts)


def is_payoneer_withdrawal(line: LineInput) -> bool:
    """派安盈提现（Payment to 银行 / 个人）：人民币要等月结单，用派安盈自己的汇率。"""
    return (
        line.provider == "payoneer"
        and line.amount < 0
        and PAYONEER_WITHDRAWAL.match(line.description or "") is not None
    )


def _fx(
    line: LineInput,
    usd_rate_of: Callable[[date], Decimal | None],
    match: StatementMatch | None,
) -> tuple[Decimal | None, Decimal | None, str]:
    """(折人民币, 汇率, 来源)。派安盈到账是人民币的用派安盈的数；提现还没对上月结单的留空。"""
    if match and match.transfer_amount and match.transfer_currency == "CNY" and line.amount:
        cny = match.transfer_amount if line.amount > 0 else -match.transfer_amount
        rate = (match.transfer_amount / abs(line.amount)).quantize(Q4, rounding=ROUND_HALF_UP)
        return cny, rate, FX_SOURCE_PAYONEER
    if match is None and is_payoneer_withdrawal(line):
        return None, None, FX_SOURCE_PENDING
    usd_rate = usd_rate_of(line.business_date) if line.currency_code == "USD" else None
    value = to_cny(line.amount, line.currency_code, usd_rate)
    if usd_rate is None or value is None:
        return value, None, ""
    return value, usd_rate, FX_SOURCE_LINGXING


def _classify_line(
    line: LineInput,
    classifier: Classifier,
    usd_rate_of: Callable[[date], Decimal | None],
    match: StatementMatch | None = None,
) -> ComputedLine:
    amount_cny, fx_rate, fx_source = _fx(line, usd_rate_of, match)
    code: str | None
    if line.exclude_amount is not None and line.exclude_amount == abs(line.amount):
        code, source = EXCLUDE_CATEGORY, SOURCE_MANUAL
    elif line.manual_category:
        code, source = line.manual_category, SOURCE_MANUAL
    elif line.approval_category:
        code, source = line.approval_category, SOURCE_APPROVAL
    else:
        code = classifier.classify(f"{line.description} {line.memo}", line.counterparty_name)
        source = SOURCE_RULE if code else ""
        if not code and line.approval_rule_category:
            code, source = line.approval_rule_category, SOURCE_APPROVAL_RULE
    computed = ComputedLine(
        source=line,
        category_code=code,
        category_source=source,
        amount_cny=amount_cny,
        fx_rate=fx_rate,
        fx_source=fx_source,
        statement=match,
    )
    if code == EXCLUDE_CATEGORY and source == SOURCE_RULE:
        # 规则剔除（对冲行）：不用写原因，人工改类别就撤销了。
        computed.auto_exclude_reason = AUTO_EXCLUDE_REASON
        computed.flags.append("已剔除")
    return computed


# ---------------------------------------------------------------- 派安盈月结补充


def _statement_key(row: StatementRow) -> tuple[str, str]:
    return (row.account_key, row.txn_id or row.row_key)


def _statement_values(row: StatementRow) -> tuple[object, ...]:
    return (
        row.txn_time,
        row.amount,
        row.currency_code,
        row.transfer_amount,
        row.transfer_currency,
    )


def _statement_alert(kind: str, row: StatementRow, message: str) -> Alert:
    return Alert(
        type=kind,
        account_key=row.account_key,
        date=row.business_date.isoformat(),
        message=message,
        amount=row.amount,
        currency_code=row.currency_code,
    )


def _dedupe_statement(rows: Sequence[StatementRow]) -> tuple[list[StatementRow], list[Alert]]:
    """同一交易号导过多次：内容一样只算一次；不一样就不补，进异常让人确认，不悄悄覆盖。"""
    groups: dict[tuple[str, str], list[StatementRow]] = defaultdict(list)
    for row in rows:
        groups[_statement_key(row)].append(row)
    kept: list[StatementRow] = []
    alerts: list[Alert] = []
    for group in groups.values():
        if len({_statement_values(row) for row in group}) == 1:
            kept.append(group[0])
            continue
        first = group[0]
        alerts.append(
            _statement_alert(
                ALERT_STATEMENT_CONFLICT,
                first,
                f"交易号 {first.txn_id} 前后导入的金额或到账不一样，这笔先不补；"
                "请核对后把错的那次导入作废",
            )
        )
    return kept, alerts


def _time_close(line: LineInput, row: StatementRow) -> bool:
    if line.source_time is None:
        return False
    gap = abs((line.source_time - row.txn_time).total_seconds())
    return gap <= STATEMENT_TIME_TOL_SECONDS


def _statement_candidates(row: StatementRow, withdrawals: Sequence[LineInput]) -> list[LineInput]:
    same = [
        line
        for line in withdrawals
        if line.account_key == row.account_key
        and line.currency_code == row.currency_code
        and line.amount == row.amount
    ]
    exact = [line for line in same if _time_close(line, row)]
    if exact:
        return exact
    return [
        line
        for line in same
        if _days_between(line.business_date, row.business_date) <= STATEMENT_DAY_TOL
    ]


def _month_ended(day: date, today: date | None) -> bool:
    return today is not None and (day.year, day.month) < (today.year, today.month)


def match_statement(
    lines: Sequence[LineInput], rows: Sequence[StatementRow], today: date | None
) -> tuple[dict[str, StatementMatch], list[Alert]]:
    """月结明细的提现对到已有流水：同账户、金额分毫不差、交易时间相同（没有时间就日期前后一天）。

    对上唯一一笔才补；一对多不猜，进异常。只看提现（Payment to），别的行只是对账用。
    """
    kept, alerts = _dedupe_statement(rows)
    withdrawals = [line for line in lines if is_payoneer_withdrawal(line)]
    matches: dict[str, StatementMatch] = {}
    claimed: dict[str, str] = {}
    covered: set[tuple[str, int, int]] = set()
    for row in sorted(kept, key=lambda item: (item.txn_time, item.row_key)):
        covered.add((row.account_key, row.business_date.year, row.business_date.month))
        if row.amount >= 0 or not PAYONEER_WITHDRAWAL.match(row.description or ""):
            continue
        found = [
            line for line in _statement_candidates(row, withdrawals) if line.line_uid not in claimed
        ]
        if not found:
            alerts.append(
                _statement_alert(
                    ALERT_STATEMENT_UNMATCHED,
                    row,
                    f"月结单交易号 {row.txn_id} 提现 {abs(row.amount):.2f} {row.currency_code}，"
                    "日记账里没有对应流水：请补导这一周的交易报告",
                )
            )
            continue
        if len(found) > 1:
            alerts.append(
                _statement_alert(
                    ALERT_STATEMENT_AMBIGUOUS,
                    row,
                    f"月结单交易号 {row.txn_id} 提现 {abs(row.amount):.2f} {row.currency_code}，"
                    f"日记账里有 {len(found)} 笔金额、日期都一样，系统不猜，请人工核对",
                )
            )
            continue
        claimed[found[0].line_uid] = row.txn_id
        matches[found[0].line_uid] = StatementMatch(
            txn_id=row.txn_id,
            transfer_amount=row.transfer_amount,
            transfer_currency=row.transfer_currency,
        )
    for line in withdrawals:
        if line.line_uid in matches:
            continue
        month_covered = (
            line.account_key,
            line.business_date.year,
            line.business_date.month,
        ) in covered
        if not month_covered and not _month_ended(line.business_date, today):
            continue
        reason = (
            "这个月的派安盈月结单里没找到这笔"
            if month_covered
            else "这个月已结束，还没导派安盈月结单"
        )
        alerts.append(
            Alert(
                type=ALERT_PAYONEER_MISSING,
                account_key=line.account_key,
                date=line.business_date.isoformat(),
                message=(
                    f"提现 {abs(line.amount):.2f} {line.currency_code}：{reason}，折人民币先空着"
                ),
                amount=line.amount,
                currency_code=line.currency_code,
                line_uid=line.line_uid,
            )
        )
    return matches, alerts


def fee_parts_total(parts: Sequence[dict[str, Any]] | None, layer: str) -> Decimal:
    return sum(
        (Decimal(str(part["amount"])) for part in parts or [] if part.get("fee_layer") == layer),
        ZERO,
    )


def payoneer_fee_gap(line: ComputedLine) -> Decimal | None:
    """派安盈那层：扣款 − 派安盈写的到账（同币种才算）；已确认记手续费的不再报。"""
    match = line.statement
    source = line.source
    if (
        match is None
        or match.transfer_amount is None
        or match.transfer_currency != source.currency_code
    ):
        return None
    gap = abs(source.amount) - match.transfer_amount
    if gap <= EXACT_TOL:
        return None
    left = gap - fee_parts_total(source.parts, FEE_LAYER_PAYONEER)
    return gap if left > EXACT_TOL else None


def _payoneer_fee_alerts(lines: Sequence[ComputedLine]) -> list[Alert]:
    alerts: list[Alert] = []
    for line in lines:
        gap = payoneer_fee_gap(line)
        if gap is None or line.statement is None:
            continue
        source = line.source
        cur = source.currency_code
        received = line.statement.transfer_amount or ZERO
        line.flags.append("派安盈到账差额待确认")
        alerts.append(
            Alert(
                type=ALERT_PAYONEER_FEE,
                account_key=source.account_key,
                date=source.business_date.isoformat(),
                message=(
                    f"扣款 {abs(source.amount):.2f} {cur}，派安盈写到账 {received:.2f} {cur}，"
                    f"差 {gap:.2f} {cur}（疑似派安盈手续费），交易号 {line.statement.txn_id}"
                ),
                amount=gap,
                currency_code=cur,
                line_uid=source.line_uid,
            )
        )
    return alerts


def _balance_alerts(lines: Sequence[LineInput]) -> list[Alert]:
    """本笔余额 − 本笔金额，在该账户找不到相同余额就算漏行；每个账户最早一笔没有上一行，不算。"""
    by_account: dict[str, list[LineInput]] = defaultdict(list)
    for line in lines:
        if line.balance_after is not None and line.provider != "pingpong":
            by_account[line.account_key].append(line)
    alerts: list[Alert] = []
    for account_key, group in by_account.items():
        ordered = sorted(group, key=lambda x: (x.business_date, x.file_row_order, x.line_uid))
        balances = [line.balance_after for line in ordered if line.balance_after is not None]
        for line in ordered[1:]:
            balance_after = line.balance_after
            if balance_after is None:
                continue
            previous = balance_after - line.amount
            if any(abs(previous - balance) <= BALANCE_TOL for balance in balances):
                continue
            alerts.append(
                Alert(
                    type=ALERT_BALANCE,
                    account_key=account_key,
                    date=line.business_date.isoformat(),
                    message=(
                        f"本笔余额 {balance_after:.2f} − 本笔 {line.amount:.2f} = {previous:.2f}，"
                        "账内没有这个余额的上一行，中间可能漏行"
                    ),
                    amount=previous,
                    currency_code=line.currency_code,
                    line_uid=line.line_uid,
                )
            )
    return alerts


def _days_between(first: date, second: date) -> int:
    return abs((first - second).days)


def _usd_in_memo(line: LineInput) -> Decimal | None:
    match = USD_IN_MEMO.search(f"{line.description} {line.memo}")
    return Decimal(match.group(1).replace(",", "")) if match else None


def _pair_match(first: ComputedLine, second: ComputedLine) -> bool:
    a, b = first.source, second.source
    if first.pair_amount * second.pair_amount >= 0 or a.account_key == b.account_key:
        return False
    if _days_between(a.business_date, b.business_date) > PAIR_DAYS:
        return False
    outgoing, incoming = (first, second) if first.pair_amount < 0 else (second, first)
    if outgoing.pair_currency == incoming.pair_currency:
        return abs(abs(outgoing.pair_amount) - incoming.pair_amount) <= ROUND_TOL
    usd_leg = outgoing if outgoing.pair_currency == "USD" else incoming
    other_leg = incoming if usd_leg is outgoing else outgoing
    wanted = _usd_in_memo(other_leg.source)
    return wanted is not None and abs(abs(usd_leg.pair_amount) - wanted) <= EXACT_TOL


def _pair_id(members: Iterable[ComputedLine]) -> str:
    joined = "|".join(sorted(member.source.line_uid for member in members))
    return "P" + hashlib.sha1(joined.encode("utf-8")).hexdigest()[:6].upper()


def _mark_pair(members: Sequence[ComputedLine], used: set[str]) -> None:
    pair = _pair_id(members)
    for member in members:
        member.pair_id = pair
        used.add(member.source.line_uid)


def _pair_currency(code: str) -> str:
    """配对时 CNH 和 CNY 算同一币种（rocky 2026-11-05：现阶段汇率一样）。"""
    return "CNY" if code == "CNH" else code


def pair_value(line: ComputedLine) -> tuple[Decimal, str]:
    """配对比较用的金额（带符号）和币种；带差额配对、手动配对、一对一 / 一对多都走这里。

    派安盈提现对上月结单的：用派安盈写的到账金额和币种（人民币提现按实际人民币配），
    同币种时再减去确认过的非派安盈层手续费行；拆过的按非手续费行合计；否则整笔。
    """
    source = line.source
    sign = Decimal(1) if source.amount > 0 else Decimal(-1)
    match = line.statement
    if match is not None and match.transfer_amount:
        value = match.transfer_amount
        if match.transfer_currency == source.currency_code:
            value -= sum(
                (
                    Decimal(str(part["amount"]))
                    for part in source.parts or []
                    if part.get("fee_layer") and part.get("fee_layer") != FEE_LAYER_PAYONEER
                ),
                ZERO,
            )
        return sign * value, _pair_currency(match.transfer_currency)
    if source.parts:
        kept = [part for part in source.parts if not part.get("fee_layer")]
        if len(kept) != len(source.parts):
            total = sum((Decimal(str(part["amount"])) for part in kept), ZERO)
            return sign * total, _pair_currency(source.currency_code)
    return source.amount, _pair_currency(source.currency_code)


def _gap_alert(out: ComputedLine, gap: Decimal, other: ComputedLine) -> Alert:
    source = out.source
    return Alert(
        type=ALERT_PAIR_GAP,
        account_key=source.account_key,
        date=source.business_date.isoformat(),
        message=(
            f"扣款 {source.currency_code} {abs(source.amount):.2f}，"
            f"到账 {other.source.amount:.2f}（{other.source.account_key} "
            f"{other.source.business_date.isoformat()}），差额 {gap:.2f}"
        ),
        amount=gap,
        currency_code=source.currency_code,
        line_uid=source.line_uid,
    )


def _pair_gap(first: ComputedLine, second: ComputedLine) -> Decimal | None:
    """两笔是一出一进、同币种时返回差额（扣款 − 到账，可能为 0），否则 None。"""
    (a, a_cur), (b, b_cur) = pair_value(first), pair_value(second)
    if a * b >= 0 or a_cur != b_cur:
        return None
    out, into = (a, b) if a < 0 else (b, a)
    return abs(out) - into


def _pair_manual(lines: Sequence[ComputedLine], used: set[str]) -> list[Alert]:
    """人工点的配对：同一个配对号的几笔算一组；一出一进、有差额的也提示差额。"""
    groups: dict[str, list[ComputedLine]] = defaultdict(list)
    for line in lines:
        if line.source.manual_pair:
            groups[line.source.manual_pair].append(line)
    alerts: list[Alert] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        _mark_pair(members, used)
        for member in members:
            member.flags.append("人工配对")
        if len(members) == 2:
            gap = _pair_gap(members[0], members[1])
            if gap is not None and gap > EXACT_TOL:
                out, into = sorted(members, key=lambda item: item.source.amount)
                alerts.append(_gap_alert(out, gap, into))
        else:
            group_alert = _group_gap_alert(members)
            if group_alert is not None:
                alerts.append(group_alert)
    return alerts


def _group_gap_alert(members: Sequence[ComputedLine]) -> Alert | None:
    """一笔对几笔（Rocky 11-10：例如两笔付出、一笔退回）。

    同币种时按合计算差额（付出合计 − 收到合计）。
    差额挂在付出最大的那笔上，可以点「确认记为手续费」。"""
    values = [(member, *pair_value(member)) for member in members]
    if len({currency for _member, _value, currency in values}) != 1:
        return None
    outs = [(member, value) for member, value, _cur in values if value < 0]
    ins = [(member, value) for member, value, _cur in values if value > 0]
    if not outs or not ins:
        return None
    paid = sum((abs(value) for _member, value in outs), ZERO)
    received = sum((value for _member, value in ins), ZERO)
    gap = paid - received
    if gap <= EXACT_TOL:
        return None
    out = max(outs, key=lambda item: abs(item[1]))[0]
    source = out.source
    return Alert(
        type=ALERT_PAIR_GAP,
        account_key=source.account_key,
        date=source.business_date.isoformat(),
        message=(
            f"一组 {len(members)} 笔：付出合计 {source.currency_code} {paid:.2f}，"
            f"收到合计 {received:.2f}，差额 {gap:.2f}"
        ),
        amount=gap,
        currency_code=source.currency_code,
        line_uid=source.line_uid,
    )


def _gap_pair_ok(out: ComputedLine, into: ComputedLine, gap: Decimal) -> bool:
    cap = GAP_PAIR_CAP.get(out.source.currency_code)
    if cap is None or gap < 0:
        return False
    return gap <= cap and gap <= abs(pair_value(out)[0]) * GAP_PAIR_RATIO


def _tail_match(out: ComputedLine, into: ComputedLine) -> bool:
    a, b = out.source, into.source
    return bool(
        (a.counterparty_last4 and a.counterparty_last4 == b.account_last4)
        or (b.counterparty_last4 and b.counterparty_last4 == a.account_last4)
    )


def _pair_with_gap(candidates: Sequence[ComputedLine], used: set[str]) -> list[Alert]:
    """前面几轮都没配上的：对方尾号对得上、5 天内、差额在容差内，就配上并把差额挂成异常。
    已经确认过手续费的（拆出手续费行后差额为 0），配上但不再提示。"""
    left = [line for line in candidates if line.source.line_uid not in used]
    outgoing = [line for line in left if line.source.amount < 0]
    incoming = [line for line in left if line.source.amount > 0]
    alerts: list[Alert] = []
    for out in outgoing:
        best: tuple[Decimal, int, ComputedLine] | None = None
        for into in incoming:
            if into.source.line_uid in used or into.source.account_key == out.source.account_key:
                continue
            days = _days_between(out.source.business_date, into.source.business_date)
            if days > GAP_PAIR_DAYS or not _tail_match(out, into):
                continue
            gap = _pair_gap(out, into)
            if gap is None or not _gap_pair_ok(out, into, gap):
                continue
            if best is None or (gap, days) < (best[0], best[1]):
                best = (gap, days, into)
        if best is None:
            continue
        gap, _, into = best
        _mark_pair([out, into], used)
        if gap > EXACT_TOL:
            alerts.append(_gap_alert(out, gap, into))
    return alerts


def _pair_lines(lines: Sequence[ComputedLine], internal: frozenset[str]) -> list[Alert]:
    for line in lines:
        line.pair_amount, line.pair_currency = pair_value(line)
    used: set[str] = set()
    alerts = _pair_manual(lines, used)
    candidates = sorted(
        (
            line
            for line in lines
            if line.category_code in internal and line.source.line_uid not in used
        ),
        key=lambda x: (
            x.source.business_date,
            x.source.account_key,
            x.source.file_row_order,
            x.source.line_uid,
        ),
    )
    _pair_one_to_one(candidates, used)
    _pair_one_to_many(candidates, used)
    _pair_fx_range(candidates, used)
    alerts.extend(_pair_with_gap(candidates, used))
    for line in candidates:
        if line.source.line_uid in used:
            continue
        text = f"{line.source.description} {line.source.memo}".strip()
        not_in_journal = NOT_IN_JOURNAL.search(text) is not None
        line.flags.append("对方账不在日记账" if not_in_journal else "未配对")
        alerts.append(
            Alert(
                type=HINT_NOT_IN_JOURNAL if not_in_journal else ALERT_UNPAIRED,
                account_key=line.source.account_key,
                date=line.source.business_date.isoformat(),
                message=f"{line.source.currency_code} {line.source.amount:.2f} {text[:40]}",
                amount=line.source.amount,
                currency_code=line.source.currency_code,
                line_uid=line.source.line_uid,
            )
        )
    return alerts


def _pair_one_to_one(candidates: Sequence[ComputedLine], used: set[str]) -> None:
    for index, first in enumerate(candidates):
        if first.source.line_uid in used:
            continue
        for second in candidates[index + 1 :]:
            if _days_between(first.source.business_date, second.source.business_date) > PAIR_DAYS:
                break
            if second.source.line_uid not in used and _pair_match(first, second):
                _mark_pair([first, second], used)
                break


def _pair_one_to_many(candidates: Sequence[ComputedLine], used: set[str]) -> None:
    left = [line for line in candidates if line.source.line_uid not in used]
    outgoing = [line for line in left if line.pair_amount < 0]
    incoming = [line for line in left if line.pair_amount > 0]
    for out in outgoing:
        pool = [
            line
            for line in incoming
            if line.source.line_uid not in used
            and line.source.account_key != out.source.account_key
            and _days_between(out.source.business_date, line.source.business_date) <= PAIR_DAYS
        ][:MAX_COMBO_POOL]
        combo = _find_combo(out, pool)
        if combo:
            _mark_pair([out, *combo], used)


def _pair_fx_range(candidates: Sequence[ComputedLine], used: set[str]) -> None:
    """同一平台多笔 USD 换一笔 CNH：按汇率区间配，标待核。"""
    usd_out = [
        line
        for line in candidates
        if line.source.line_uid not in used
        and line.source.provider == "pingpong"
        and line.source.amount < 0
        and line.source.currency_code == "USD"
    ]
    cnh_in = [
        line
        for line in candidates
        if line.source.line_uid not in used
        and line.source.provider == "pingpong"
        and line.source.amount > 0
        and line.source.currency_code in {"CNH", "CNY"}
    ]
    for into in cnh_in:
        pool = [
            line
            for line in usd_out
            if line.source.line_uid not in used
            and _days_between(line.source.business_date, into.source.business_date) <= PAIR_DAYS
        ][:MAX_COMBO_POOL]
        combo = _find_fx_range_combo(into, pool)
        if combo:
            _mark_pair([into, *combo], used)
            into.flags.append("汇率区间配对待核")


def _find_combo(out: ComputedLine, pool: Sequence[ComputedLine]) -> tuple[ComputedLine, ...] | None:
    for size in (1, 2, 3):
        for combo in itertools.combinations(pool, size):
            if all(item.pair_currency == out.pair_currency for item in combo):
                total = sum((item.pair_amount for item in combo), ZERO)
                if abs(abs(out.pair_amount) - total) <= ROUND_TOL:
                    return combo
                continue
            if out.amount_cny is None or any(item.amount_cny is None for item in combo):
                continue
            total_cny = sum((abs(item.amount_cny or ZERO) for item in combo), ZERO)
            if abs(abs(out.amount_cny) - total_cny) <= ROUND_TOL:
                return combo
    return None


def _find_fx_range_combo(
    into: ComputedLine, pool: Sequence[ComputedLine]
) -> tuple[ComputedLine, ...] | None:
    for size in (1, 2, 3):
        for combo in itertools.combinations(pool, size):
            usd = sum((abs(item.source.amount) for item in combo), ZERO)
            if usd and Decimal("6.3") <= into.source.amount / usd <= Decimal("7.6"):
                return combo
    return None


def _manual_excluded_cny(line: ComputedLine) -> Decimal:
    excluded = line.source.exclude_amount
    if not excluded or line.amount_cny is None or not line.source.amount:
        return ZERO
    return abs(line.amount_cny) * excluded / abs(line.source.amount)


def _apply_exclusions(
    lines: Sequence[ComputedLine], exclusions: Sequence[ExclusionEntry]
) -> list[Alert]:
    """按日期顺序在命中流水上按人民币扣，扣完为止；没有人民币金额的流水不扣。"""
    alerts: list[Alert] = []
    for entry in exclusions:
        left = abs(entry.amount_cny)
        hits = sorted(
            (line for line in lines if line.amount_cny is not None and _hits(entry, line)),
            key=lambda x: (x.source.business_date, x.source.line_uid),
        )
        for line in hits:
            if left <= 0:
                break
            room = abs(line.amount_cny or ZERO) - _manual_excluded_cny(line)
            take = min(room - line.list_excluded_cny, left)
            if take <= 0:
                continue
            line.list_excluded_cny += take
            left -= take
        if left > EXACT_TOL:
            label = entry.ref or entry.summary_contains or ""
            alerts.append(
                Alert(
                    type=ALERT_EXCLUSION,
                    account_key=entry.account_key or "",
                    date=_exclusion_date(entry),
                    message=(
                        f"剔除清单第 {entry.entry_no} 条（{label} {entry.reason} "
                        f"¥{abs(entry.amount_cny):.2f}）没找到对应付款或金额不够扣"
                    ),
                    amount=left,
                    currency_code="CNY",
                )
            )
    return alerts


def _exclusion_date(entry: ExclusionEntry) -> str:
    """异常的日期：流水日期优先，按审批单号登记的没有流水日期，用登记日（页面按它筛月份）。"""
    day = entry.txn_date or entry.registered_on
    return day.isoformat() if day else ""


def _hits(entry: ExclusionEntry, line: ComputedLine) -> bool:
    source = line.source
    if entry.ref:
        return entry.ref in source.refs
    if entry.txn_date is None or entry.txn_date != source.business_date:
        return False
    if entry.account_key and entry.account_key != source.account_key:
        return False
    return (entry.summary_contains or "") in f"{source.description} {source.memo}"


def _add_exclude_flag(line: ComputedLine) -> None:
    excluded = line.source.exclude_amount or ZERO
    if line.list_excluded_cny <= 0 and not excluded:
        return
    whole = excluded == abs(line.source.amount)
    if line.amount_cny is not None:
        total = _manual_excluded_cny(line) + line.list_excluded_cny
        whole = whole or abs(abs(line.amount_cny) - total) <= EXACT_TOL
    line.flags.append("已剔除" if whole else "部分剔除")


# ---------------------------------------------------------------- 审核状态流转


ERR_STAGE_NOT_ALLOWED = "CASHFLOW_STAGE_NOT_ALLOWED"
ERR_INVALID_EVENT = "CASHFLOW_INVALID_EVENT"
ERR_VERSION_CONFLICT = "CASHFLOW_VERSION_CONFLICT"
ERR_IDEMPOTENCY_KEY_REUSED = "CASHFLOW_IDEMPOTENCY_KEY_REUSED"
ERR_PAIR_CONFLICT = "CASHFLOW_PAIR_CONFLICT"


class EventRejectedError(Exception):
    """人工动作被拒：status_code 和固定错误码 code 一起交给接口层。"""

    def __init__(self, status_code: int, message: str, code: str = ERR_INVALID_EVENT) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code


@dataclass
class ReviewState:
    manual_category: str | None = None
    refs: list[str] = field(default_factory=list)
    exclude_amount: Decimal | None = None
    exclude_reason: str | None = None
    stage: str = STAGE_TODO
    stage_reason: str | None = None
    review_note: str | None = None
    manual_description: str | None = None
    manual_memo: str | None = None
    # 拆分：[{"amount": "100.0000", "category_code": "G02" 或 None}]，金额合计 = 流水金额绝对值。
    parts: list[dict[str, Any]] | None = None
    manual_pair: str | None = None


def _required_reason(reason: str | None, label: str) -> str:
    text = (reason or "").strip()
    if not text:
        raise EventRejectedError(422, f"{label}必须填原因")
    return text


def _require_stage(state: ReviewState, allowed: frozenset[str], message: str) -> None:
    if state.stage not in allowed:
        raise EventRejectedError(409, message, ERR_STAGE_NOT_ALLOWED)


def apply_event(
    state: ReviewState,
    *,
    kind: str,
    payload: dict[str, Any],
    reason: str | None,
    line_amount: Decimal,
    valid_categories: frozenset[str],
) -> bool:
    """就地更新 state，返回这次改动是否把已审核的流水退回了待初审。"""
    first_message = "这笔不在待初审，不能初审"
    final_message = "这笔还没初审通过，轮不到终审"
    if kind == KIND_REVIEW1_PASS:
        _require_stage(state, FIRST_PENDING, first_message)
        state.stage, state.stage_reason = STAGE_OK1, None
        note = str(payload.get("note") or "").strip()
        state.review_note = note or state.review_note
        return False
    if kind == KIND_REVIEW1_REJECT:
        _require_stage(state, FIRST_PENDING, first_message)
        state.stage, state.stage_reason = STAGE_REJ1, _required_reason(reason, "初审不通过")
        return False
    if kind == KIND_REVIEW2_PASS:
        _require_stage(state, frozenset({STAGE_OK1}), final_message)
        state.stage, state.stage_reason = STAGE_OK2, None
        return False
    if kind == KIND_REVIEW2_REJECT:
        _require_stage(state, frozenset({STAGE_OK1}), final_message)
        state.stage, state.stage_reason = STAGE_REJ2, _required_reason(reason, "终审不通过")
        return False
    if kind == KIND_REVIEW1_UNDO:
        # 初审通过 / 不通过都能撤，回到待初审；已经终审过的要先撤终审。
        _require_stage(
            state, frozenset({STAGE_OK1, STAGE_REJ1}), "这笔不是初审后的状态，不能撤销初审"
        )
        state.stage, state.stage_reason = STAGE_TODO, None
        return False
    if kind == KIND_REVIEW2_UNDO:
        # 终审通过 / 驳回都能撤，回到待终审。
        _require_stage(
            state, frozenset({STAGE_OK2, STAGE_REJ2}), "这笔不是终审后的状态，不能撤销终审"
        )
        state.stage, state.stage_reason = STAGE_OK1, None
        return False
    if kind == KIND_SET_TEXT:
        # 改摘要 / 备注只是显示用，银行原文保留、分类规则照原文算，不退回审核。
        if not {"description", "memo"} & payload.keys():
            raise EventRejectedError(422, "没有要改的摘要或备注")
        if "description" in payload:
            state.manual_description = _text(payload["description"])
        if "memo" in payload:
            state.manual_memo = _text(payload["memo"])
        return False
    if kind == KIND_SET_PART_TEXT:
        # 拆分行自己的摘要 / 备注（rocky 11-05）：和整笔改摘要一样只改显示，不退回审核。
        index = _part_index(state, payload)
        if not {"description", "memo"} & payload.keys():
            raise EventRejectedError(422, "没有要改的摘要或备注")
        parts = [dict(part) for part in state.parts or []]
        for field in ("description", "memo"):
            if field in payload:
                value = _text(payload[field])
                if value is None:
                    parts[index].pop(field, None)
                else:
                    parts[index][field] = value
        state.parts = parts
        return False
    if kind in {KIND_PAIR, KIND_UNPAIR}:
        _require_stage(
            state,
            frozenset({STAGE_TODO, STAGE_REJ1, STAGE_OK1, STAGE_REJ2}),
            "这笔已终审，先撤销终审再改配对",
        )
    if kind == KIND_PAIR:
        # 配对只是把两笔认成同一笔内部转账，不动金额和类别，不退回审核；两边各发一次。
        pair_id = str(payload.get("pair_id") or "").strip()
        if not pair_id or len(pair_id) > PAIR_ID_MAX:
            raise EventRejectedError(422, "配对号无效")
        state.manual_pair = pair_id
        return False
    if kind == KIND_UNPAIR:
        if not state.manual_pair:
            raise EventRejectedError(409, "这笔没有人工配对")
        # 取消配对必须写原因（rocky 11-05），原因记在事件里，操作记录能看到。
        _required_reason(reason, "取消配对")
        state.manual_pair = None
        return False
    if kind == KIND_SET_CATEGORY:
        if state.parts:
            raise EventRejectedError(409, "这笔已拆分，请在拆分行上选类别")
        state.manual_category = _category(payload, valid_categories)
    elif kind == KIND_SPLIT:
        state.parts = _split_parts(payload, line_amount)
    elif kind == KIND_CONFIRM_FEE:
        state.parts = _fee_parts(state.parts, payload, line_amount, valid_categories)
    elif kind == KIND_SET_PART_CATEGORY:
        index = _part_index(state, payload)
        parts = [dict(part) for part in state.parts or []]
        parts[index]["category_code"] = _category(payload, valid_categories)
        state.parts = parts
    elif kind == KIND_UNSPLIT:
        if not state.parts:
            raise EventRejectedError(409, "这笔没有拆分")
        # 拆分行挂过的审批单不丢：收回到整笔上。
        moved = [ref for part in state.parts for ref in part.get("refs") or []]
        state.refs = list(dict.fromkeys([*state.refs, *moved]))
        state.parts = None
    elif kind == KIND_ATTACH_REF:
        ref = _approval_ref(payload)
        if ref in all_refs(state):
            raise EventRejectedError(409, "这笔已经挂了这个审批单号")
        state.refs = [*state.refs, ref]
    elif kind == KIND_ATTACH_PART_REF:
        index = _part_index(state, payload)
        ref = _approval_ref(payload)
        if ref in all_refs(state):
            raise EventRejectedError(409, "这笔已经挂了这个审批单号")
        parts = [dict(part) for part in state.parts or []]
        parts[index]["refs"] = [*(parts[index].get("refs") or []), ref]
        state.parts = parts
    elif kind == KIND_DETACH_PART_REF:
        index = _part_index(state, payload)
        ref = _approval_ref(payload)
        parts = [dict(part) for part in state.parts or []]
        current = list(parts[index].get("refs") or [])
        if ref not in current:
            raise EventRejectedError(409, "这一行没有挂这个审批单号")
        remaining = [item for item in current if item != ref]
        if remaining:
            parts[index]["refs"] = remaining
        else:
            parts[index].pop("refs", None)
        state.parts = parts
    elif kind == KIND_DETACH_REF:
        ref = _approval_ref(payload)
        if ref not in state.refs:
            raise EventRejectedError(409, "这笔没有挂这个审批单号")
        state.refs = [item for item in state.refs if item != ref]
    elif kind == KIND_EXCLUDE:
        state.exclude_reason = _required_reason(reason, "剔除")
        state.exclude_amount = _exclude_amount(payload, line_amount)
    elif kind == KIND_UNEXCLUDE:
        if state.exclude_amount is None:
            raise EventRejectedError(409, "这笔没有剔除")
        state.exclude_amount = None
        state.exclude_reason = None
    else:
        raise EventRejectedError(422, "不支持的操作")
    if state.stage in {STAGE_OK1, STAGE_OK2}:
        state.stage, state.stage_reason = STAGE_TODO, None
        return True
    return False


def all_refs(state: ReviewState) -> list[str]:
    """整笔挂的审批单 + 各拆分行挂的审批单（去重、保持顺序）。"""
    return list(
        dict.fromkeys(
            [*state.refs, *(ref for part in state.parts or [] for ref in part.get("refs") or [])]
        )
    )


def part_refs(parts: Sequence[dict[str, Any]] | None) -> list[str]:
    return [ref for part in parts or [] for ref in part.get("refs") or []]


def part_cny(
    amount_cny: Decimal | None, amount: Decimal, parts: Sequence[dict[str, Any]]
) -> list[Decimal | None]:
    """拆分行各自的折人民币（绝对值）：按金额比例分整笔的折人民币，精确到分，尾差落最后一行。"""
    if amount_cny is None or not amount or not parts:
        return [None] * len(parts)
    total = abs(amount_cny).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole = abs(amount)
    out: list[Decimal | None] = []
    used = ZERO
    for index, part in enumerate(parts):
        if index == len(parts) - 1:
            out.append(total - used)
            continue
        share = (total * Decimal(str(part["amount"])) / whole).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        used += share
        out.append(share)
    return out


def _part_index(state: ReviewState, payload: dict[str, Any]) -> int:
    if not state.parts:
        raise EventRejectedError(409, "这笔没有拆分")
    index = payload.get("index")
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(state.parts):
        raise EventRejectedError(422, "拆分行不存在")
    return index


def _category(payload: dict[str, Any], valid_categories: frozenset[str]) -> str | None:
    code = payload.get("category_code")
    if code is None or code == "":
        return None
    if code == EXCLUDE_CATEGORY:
        raise EventRejectedError(422, "X01 不能在这里选，请用剔除")
    if not isinstance(code, str) or code not in valid_categories:
        raise EventRejectedError(422, "类别不存在")
    return code


def _text(raw: Any) -> str | None:
    """None 或空字符串 = 恢复银行原文。"""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise EventRejectedError(422, "摘要 / 备注要是文字")
    text = raw.strip()
    if len(text) > TEXT_MAX:
        raise EventRejectedError(422, f"摘要 / 备注最多 {TEXT_MAX} 个字")
    return text or None


def _split_parts(payload: dict[str, Any], line_amount: Decimal) -> list[dict[str, Any]]:
    """先拆金额，类别拆完后逐行再选（rocky 11-05），所以每行类别先空着。"""
    raw = payload.get("amounts")
    if not isinstance(raw, list) or not 2 <= len(raw) <= MAX_PARTS:
        raise EventRejectedError(422, f"拆分要 2 到 {MAX_PARTS} 行")
    amounts: list[Decimal] = []
    for item in raw:
        try:
            amount = Decimal(str(item))
        except InvalidOperation as exc:
            raise EventRejectedError(422, "拆分金额无效") from exc
        if not amount.is_finite() or amount <= 0:
            raise EventRejectedError(422, "拆分的每一行金额都要大于 0")
        amounts.append(amount.quantize(Q4, rounding=ROUND_HALF_UP))
    if sum(amounts, ZERO) != abs(line_amount).quantize(Q4, rounding=ROUND_HALF_UP):
        raise EventRejectedError(422, "拆分金额合计要等于这笔流水的金额")
    return [{"amount": str(amount), "category_code": None} for amount in amounts]


def _fee_parts(
    parts: list[dict[str, Any]] | None,
    payload: dict[str, Any],
    line_amount: Decimal,
    valid_categories: frozenset[str],
) -> list[dict[str, Any]]:
    """「确认记为手续费」：从这笔里切出一行手续费（F01，带 fee_layer），其余留作转账行。
    没拆过的拆成两行（转账行沿用传来的类别）；拆过的从最大的非手续费行里扣。
    同一层手续费（fee_layer）只能确认一次；取消用「取消拆分」。"""
    try:
        fee = Decimal(str(payload.get("fee_amount")))
    except InvalidOperation as exc:
        raise EventRejectedError(422, "手续费金额无效") from exc
    if not fee.is_finite() or fee <= 0:
        raise EventRejectedError(422, "手续费金额要大于 0")
    fee = fee.quantize(Q4, rounding=ROUND_HALF_UP)
    layer = str(payload.get("fee_layer") or FEE_LAYER_DEFAULT).strip()[:32]
    if FEE_CATEGORY not in valid_categories:
        raise EventRejectedError(422, "类别不存在")
    current = [dict(part) for part in parts] if parts else None
    if current is None:
        transfer_cat = _category(
            {"category_code": payload.get("transfer_category")}, valid_categories
        )
        current = [
            {
                "amount": str(abs(line_amount).quantize(Q4, rounding=ROUND_HALF_UP)),
                "category_code": transfer_cat,
            }
        ]
    if any(part.get("fee_layer") == layer for part in current):
        raise EventRejectedError(409, "这笔的这层手续费已经确认过了")
    if len(current) >= MAX_PARTS:
        raise EventRejectedError(422, f"拆分最多 {MAX_PARTS} 行")
    kept = [index for index, part in enumerate(current) if not part.get("fee_layer")]
    if not kept:
        raise EventRejectedError(409, "这笔没有可以扣手续费的行")
    target = max(kept, key=lambda index: Decimal(str(current[index]["amount"])))
    rest = Decimal(str(current[target]["amount"])) - fee
    if rest <= 0:
        raise EventRejectedError(422, "手续费不能大于等于这笔的金额")
    current[target]["amount"] = str(rest.quantize(Q4, rounding=ROUND_HALF_UP))
    current.append({"amount": str(fee), "category_code": FEE_CATEGORY, "fee_layer": layer})
    return current


def _approval_ref(payload: dict[str, Any]) -> str:
    ref = str(payload.get("ref") or "").strip()
    if not APPROVAL_REF.match(ref):
        raise EventRejectedError(422, "审批单号是 12 位数字")
    return ref


def _exclude_amount(payload: dict[str, Any], line_amount: Decimal) -> Decimal:
    full = abs(line_amount)
    raw = payload.get("amount")
    if raw is None or raw == "":
        return full
    try:
        amount = Decimal(str(raw))
    except InvalidOperation as exc:
        raise EventRejectedError(422, "剔除金额无效") from exc
    if not amount.is_finite():
        raise EventRejectedError(422, "剔除金额无效")
    amount = amount.quantize(Q4, rounding=ROUND_HALF_UP)
    if amount <= 0 or amount > full:
        raise EventRejectedError(422, "剔除金额要大于 0，且不能超过这笔流水的金额")
    return amount

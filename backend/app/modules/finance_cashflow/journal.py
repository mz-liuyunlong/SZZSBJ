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
from datetime import date
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
KIND_UNSPLIT = "unsplit"
TEXT_MAX = 500
MAX_PARTS = 20
KIND_AUTO_RESET = "auto_reset"
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
    """CNY 原值；USD 用当月生效汇率，没有就空；CNH 也空。不兜底。"""
    if currency_code == "CNY":
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
) -> JournalResult:
    computed = [_classify_line(line, classifier, usd_rate_of) for line in lines]
    alerts = _balance_alerts(lines)
    alerts.extend(_pair_lines(computed, internal_categories))
    alerts.extend(_apply_exclusions(computed, exclusions))
    for item in computed:
        _add_exclude_flag(item)
    return JournalResult(lines=computed, alerts=alerts)


def _classify_line(
    line: LineInput,
    classifier: Classifier,
    usd_rate_of: Callable[[date], Decimal | None],
) -> ComputedLine:
    amount_cny = to_cny(line.amount, line.currency_code, usd_rate_of(line.business_date))
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
    return ComputedLine(
        source=line, category_code=code, category_source=source, amount_cny=amount_cny
    )


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
    if a.amount * b.amount >= 0 or a.account_key == b.account_key:
        return False
    if _days_between(a.business_date, b.business_date) > PAIR_DAYS:
        return False
    outgoing, incoming = (a, b) if a.amount < 0 else (b, a)
    if outgoing.currency_code == incoming.currency_code:
        return abs(abs(outgoing.amount) - incoming.amount) <= ROUND_TOL
    usd_leg = outgoing if outgoing.currency_code == "USD" else incoming
    other_leg = incoming if usd_leg is outgoing else outgoing
    wanted = _usd_in_memo(other_leg)
    return wanted is not None and abs(abs(usd_leg.amount) - wanted) <= EXACT_TOL


def _pair_id(members: Iterable[ComputedLine]) -> str:
    joined = "|".join(sorted(member.source.line_uid for member in members))
    return "P" + hashlib.sha1(joined.encode("utf-8")).hexdigest()[:6].upper()


def _mark_pair(members: Sequence[ComputedLine], used: set[str]) -> None:
    pair = _pair_id(members)
    for member in members:
        member.pair_id = pair
        used.add(member.source.line_uid)


def _pair_lines(lines: Sequence[ComputedLine], internal: frozenset[str]) -> list[Alert]:
    candidates = sorted(
        (line for line in lines if line.category_code in internal),
        key=lambda x: (
            x.source.business_date,
            x.source.account_key,
            x.source.file_row_order,
            x.source.line_uid,
        ),
    )
    used: set[str] = set()
    _pair_one_to_one(candidates, used)
    _pair_one_to_many(candidates, used)
    _pair_fx_range(candidates, used)
    alerts: list[Alert] = []
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
    outgoing = [line for line in left if line.source.amount < 0]
    incoming = [line for line in left if line.source.amount > 0]
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
            if all(item.source.currency_code == out.source.currency_code for item in combo):
                total = sum((item.source.amount for item in combo), ZERO)
                if abs(abs(out.source.amount) - total) <= ROUND_TOL:
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
    if kind == KIND_SET_CATEGORY:
        if state.parts:
            raise EventRejectedError(409, "这笔已拆分，请在拆分行上选类别")
        state.manual_category = _category(payload, valid_categories)
    elif kind == KIND_SPLIT:
        state.parts = _split_parts(payload, line_amount)
    elif kind == KIND_SET_PART_CATEGORY:
        if not state.parts:
            raise EventRejectedError(409, "这笔没有拆分")
        index = payload.get("index")
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or not 0 <= index < len(state.parts)
        ):
            raise EventRejectedError(422, "拆分行不存在")
        parts = [dict(part) for part in state.parts]
        parts[index]["category_code"] = _category(payload, valid_categories)
        state.parts = parts
    elif kind == KIND_UNSPLIT:
        if not state.parts:
            raise EventRejectedError(409, "这笔没有拆分")
        state.parts = None
    elif kind == KIND_ATTACH_REF:
        ref = _approval_ref(payload)
        if ref in state.refs:
            raise EventRejectedError(409, "这笔已经挂了这个审批单号")
        state.refs = [*state.refs, ref]
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

"""飞书审批单：解析实例详情、算付款状态、和流水匹配（纯函数，不碰数据库和网络）。

只留账号尾号，不落完整银行账号；附件只留元数据，不留飞书的临时下载链接。
"""

from __future__ import annotations

import itertools
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from app.modules.finance_cashflow.approval_orgs import ORG_MAIN, ORG_YC, org_serial

SHANGHAI = ZoneInfo("Asia/Shanghai")

STATUS_APPROVED = "APPROVED"
STATUS_PENDING = "PENDING"
STATUS_REVERTED = "REVERTED"
CANCELLED_STATUSES = frozenset({"REJECTED", "CANCELED", "DELETED", STATUS_REVERTED})
TERMINAL_STATUSES = CANCELLED_STATUSES | {STATUS_APPROVED}
STATUS_TEXT = {
    STATUS_APPROVED: "已同意",
    STATUS_PENDING: "审批中",
    "REJECTED": "已拒绝",
    "CANCELED": "已撤回",
    "DELETED": "已删除",
    STATUS_REVERTED: "已撤销",
}

REASON_WIDGETS = ("付款事由", "报销事由", "申请事由", "费用说明")
AMOUNT_WIDGETS = ("付款金额", "费用汇总", "申请金额", "核销金额（元）")
PAY_WIDGETS = ("付款方式", "收款方式")
CATEGORY_MARKS = ("费用大类", "明细项", "费用类别")
RELATION_MARKS = ("关联单号", "关联备用金")
FILE_TYPES = frozenset({"image", "imageV2", "attachment", "attachmentV2"})
IMAGE_TYPES = frozenset({"image", "imageV2"})
TIMELINE_ACT = {
    "START": "发起",
    "PASS": "通过",
    "AUTO_PASS": "自动通过",
    "REJECT": "拒绝",
    "AUTO_REJECT": "自动拒绝",
    "ROLLBACK": "退回",
    "ROLLBACK_SELECTED_NODE": "退回",
    "TRANSFER": "转交",
    "CC": "抄送",
    "CANCEL": "撤回",
    "DELETE": "删除",
    "REMOVE_REPEAT": "去重通过",
}

# 匹配口径（照 Demo）：金额相等、审批通过前 3 天到通过后 45 天、人民币。
MATCH_DAYS_BEFORE = 3
MATCH_DAYS_AFTER = 45
AMOUNT_TOL = Decimal("0.011")
PAID_TOL = Decimal("1")
SERIAL_IN_TEXT = re.compile(r"(?<!\d)20\d{10}(?!\d)")
# 摘要 / 备注里的单号，带或不带第二家公司的前缀：
# YC- / yc- / YC 空格 / YC 紧挨着都算，YC 前面不能紧挨着字母
SERIAL_IN_TEXT_ORG = re.compile(r"((?<![a-z])YC[-\s]?)?(?<!\d)(20\d{10})(?!\d)", re.I)
PAYEE_NOISE = re.compile(r"有限公司|股份|科技|贸易|商贸|网络|实业|集团|\(.*?\)|（.*?）|\s")


class ApprovalParseError(ValueError):
    """实例详情结构不认识：错误信息不带任何业务内容。"""


@dataclass
class ParsedApproval:
    instance_code: str
    serial_number: str
    approval_code: str
    kind: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    handled_at: datetime | None
    applicant_user_id: str
    department_id: str
    reason: str
    amount: Decimal | None
    currency_code: str
    pay_method: str
    invoice: str
    payee: str
    payee_bank: str
    payee_account_last4: str
    fee_category: str
    related_serial: str
    items: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    records: list[dict[str, Any]] = field(default_factory=list)
    comments: list[dict[str, Any]] = field(default_factory=list)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ",".join(_text(item) for item in value if item is not None)
    return " ".join(str(value).split())


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _from_ms(value: Any) -> datetime | None:
    try:
        millis = int(value)
    except (TypeError, ValueError):
        return None
    if millis <= 0:
        return None
    return datetime.fromtimestamp(millis / 1000, UTC)


def _iso_local(value: datetime | None) -> str:
    return value.astimezone(SHANGHAI).strftime("%Y-%m-%d %H:%M") if value else ""


def _form_widgets(detail: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = detail.get("form")
    try:
        form = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError as exc:
        raise ApprovalParseError("form_not_json") from exc
    if form is None:
        return []
    if not isinstance(form, list):
        raise ApprovalParseError("form_not_list")
    return [widget for widget in form if isinstance(widget, dict)]


def _first(widgets: Mapping[str, dict[str, Any]], names: Sequence[str]) -> dict[str, Any] | None:
    for name in names:
        if name in widgets:
            return widgets[name]
    return None


def _currency(widget: Mapping[str, Any] | None) -> str:
    ext = widget.get("ext") if widget else None
    return str(ext.get("currency") or "") if isinstance(ext, dict) else ""


def _account_fields(widget: Mapping[str, Any] | None) -> tuple[str, str, str]:
    """收款账户控件 → (户名, 银行, 账号尾号)；完整账号在这里就丢掉。"""
    value = widget.get("value") if widget else None
    if isinstance(value, list):
        value = value[0] if value else None
    if not isinstance(value, dict):
        return "", "", ""
    bank_widget = value.get("widgetAccountBankName")
    bank_text = bank_widget.get("text") if isinstance(bank_widget, dict) else None
    bank = ""
    if bank_text:
        try:
            bank = _text(json.loads(bank_text).get("bankNameZh"))
        except (ValueError, AttributeError):
            bank = ""
    number = value.get("widgetAccountBankNumber") or value.get("widgetAccountNumber") or ""
    if isinstance(number, dict):
        number = number.get("value") or ""
    digits = re.sub(r"\D", "", str(number))
    return _text(value.get("widgetAccountName")), bank, digits[-4:]


def _files_of(widget: Mapping[str, Any], item: int) -> list[dict[str, Any]]:
    value = widget.get("value")
    if widget.get("type") not in FILE_TYPES or not isinstance(value, list):
        return []
    ext = widget.get("ext")
    titles = [part.strip() for part in ext.split(",")] if isinstance(ext, str) and ext else []
    return [
        {
            "source": "form",
            "what": _text(widget.get("name")),
            "item": item,
            "is_image": widget.get("type") in IMAGE_TYPES,
            "title": titles[index] if index < len(titles) else "",
        }
        for index in range(len(value))
    ]


def _parse_items(
    widget: Mapping[str, Any] | None,
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    currency = ""
    files: list[dict[str, Any]] = []
    groups = widget.get("value") if widget else None
    if not isinstance(groups, list):
        return items, currency, files
    for number, group in enumerate(groups, start=1):
        content, amount, category = "", None, ""
        for cell in group if isinstance(group, list) else []:
            if not isinstance(cell, dict):
                continue
            name = str(cell.get("name") or "")
            if name == "内容":
                content = _text(cell.get("value"))
            elif name == "金额":
                amount = _decimal(cell.get("value"))
                currency = currency or _currency(cell)
            elif "类别" in name or "明细项" in name:
                category = _text(cell.get("value"))
            files.extend(_files_of(cell, number))
        items.append(
            {
                "content": content,
                "amount": str(amount) if amount is not None else None,
                "category": category,
            }
        )
    return items, currency, files


def _uploaded(entries: Iterable[Any], source: str, what: str) -> list[dict[str, Any]]:
    return [
        {
            "source": source,
            "what": what,
            "item": 0,
            "is_image": str(entry.get("type") or "").lower() == "image",
            "title": _text(entry.get("title")),
        }
        for entry in entries
        if isinstance(entry, dict)
    ]


def _parse_records(
    detail: Mapping[str, Any], names: Mapping[str, str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], datetime | None, list[dict[str, Any]]]:
    tasks = {
        str(task.get("id")): str(task.get("node_name") or "")
        for task in detail.get("task_list") or []
        if isinstance(task, dict)
    }
    records: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    handled: datetime | None = None
    for entry in detail.get("timeline") or []:
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("type") or "")
        node = tasks.get(str(entry.get("task_id")), "")
        when = _from_ms(entry.get("create_time"))
        people = [entry.get("user_id"), *(entry.get("user_id_list") or [])]
        who = "、".join(names.get(str(uid)) or str(uid) for uid in people if uid)
        uploaded = _uploaded(entry.get("files") or [], "timeline", f"{node or '审批节点'}上传")
        files.extend(uploaded)
        records.append(
            {
                "node": node,
                "act": TIMELINE_ACT.get(kind, kind),
                "who": who,
                "time": _iso_local(when),
                "note": _text(entry.get("comment")),
                "files": len(uploaded),
            }
        )
        if "办理" in node and kind in {"PASS", "AUTO_PASS"} and when:
            handled = max(handled, when) if handled else when
    comments: list[dict[str, Any]] = []
    for row in detail.get("comment_list") or []:
        if not isinstance(row, dict):
            continue
        files.extend(_uploaded(row.get("files") or [], "comment", "评论附件"))
        comments.append(
            {
                "who": names.get(str(row.get("user_id"))) or _text(row.get("user_id")),
                "time": _iso_local(_from_ms(row.get("create_time"))),
                "note": _text(row.get("comment")),
            }
        )
    return records, comments, handled, files


def people_of(detail: Mapping[str, Any]) -> set[str]:
    """详情里出现的人（申请人、处理人、评论人），用来换姓名。"""
    found = {detail.get("user_id")}
    for entry in detail.get("timeline") or []:
        if isinstance(entry, dict):
            found.add(entry.get("user_id"))
            found.update(entry.get("user_id_list") or [])
    for row in detail.get("comment_list") or []:
        if isinstance(row, dict):
            found.add(row.get("user_id"))
    return {str(item) for item in found if item}


def _relation_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def parse_instance(
    detail: Mapping[str, Any],
    *,
    approval_code: str,
    kind: str,
    instance_code: str,
    names: Mapping[str, str] | None = None,
) -> ParsedApproval:
    names = names or {}
    serial = _text(detail.get("serial_number"))
    if not serial:
        raise ApprovalParseError("serial_missing")
    all_widgets = _form_widgets(detail)
    widgets = {str(widget.get("name") or ""): widget for widget in all_widgets}
    amount_widget = _first(widgets, AMOUNT_WIDGETS)
    items, item_currency, item_files = _parse_items(widgets.get("费用明细"))
    account_name, bank, last4 = _account_fields(widgets.get("收款账户"))
    pay_widget = _first(widgets, PAY_WIDGETS)
    reason_widget = _first(widgets, REASON_WIDGETS)
    payee = _text((widgets.get("收款人") or {}).get("value")) or account_name
    category = " ".join(
        _text(widget.get("value"))
        for name, widget in widgets.items()
        if any(mark in name for mark in CATEGORY_MARKS) and widget.get("value")
    )
    relation = ""
    for name, widget in widgets.items():
        if any(mark in name for mark in RELATION_MARKS) and widget.get("value"):
            found = SERIAL_IN_TEXT.findall(_relation_text(widget.get("value")))
            relation = ",".join(dict.fromkeys(found))
    records, comments, handled, timeline_files = _parse_records(detail, names)
    form_files = [file for widget in all_widgets for file in _files_of(widget, 0)]
    status = str(detail.get("status") or "")
    if status == STATUS_APPROVED and detail.get("reverted") is True:
        status = STATUS_REVERTED
    applicant = _text(detail.get("user_id"))
    return ParsedApproval(
        instance_code=instance_code,
        serial_number=serial,
        approval_code=approval_code,
        kind=kind,
        status=status,
        started_at=_from_ms(detail.get("start_time")),
        completed_at=_from_ms(detail.get("end_time")),
        handled_at=handled,
        applicant_user_id=applicant,
        department_id=_text(detail.get("department_id")),
        reason=_text((reason_widget or {}).get("value")),
        amount=_decimal((amount_widget or {}).get("value")),
        currency_code=_currency(amount_widget) or item_currency or "CNY",
        pay_method=_text((pay_widget or {}).get("value")),
        invoice=_text((widgets.get("是否开票") or {}).get("value")),
        payee=payee,
        payee_bank=bank,
        payee_account_last4=last4,
        fee_category=category,
        related_serial=relation,
        items=items,
        attachments=[*form_files, *item_files, *timeline_files],
        records=records,
        comments=comments,
    )


def rename_people(who: str, names: Mapping[str, str]) -> str:
    """把「、」连起来的编号换成姓名；员工表里没有的保留编号。"""
    return "、".join(names.get(part) or part for part in who.split("、")) if who else ""


# ---------------------------------------------------------------- 类别


def form_category_code(fee_category: str, names_to_code: Mapping[str, str]) -> str | None:
    """表单上的费用类别文字 → 类别编码；类别名是文字的子串才算。"""
    if not fee_category:
        return None
    for name, code in names_to_code.items():
        if name and name in fee_category:
            return code
    return None


def single_value(values: Iterable[str | None]) -> str | None:
    """一笔挂多张单时，类别要一致才用；不一致就不算。"""
    distinct = {value for value in values if value}
    return distinct.pop() if len(distinct) == 1 else None


# ---------------------------------------------------------------- 匹配


@dataclass(frozen=True)
class MatchApproval:
    serial: str
    status: str
    amount: Decimal | None
    currency_code: str
    payee: str
    anchor_day: date | None  # 通过日期，没有时用发起日期
    org: str = ORG_MAIN  # 哪家公司的飞书；只和同一家公司账户的流水配对


@dataclass(frozen=True)
class MatchLine:
    line_uid: str
    business_date: date
    amount: Decimal
    currency_code: str
    counterparty_name: str
    text: str
    refs: tuple[str, ...]
    stage: str
    # 折人民币；cny_exact = 派安盈月结单上的实际到账人民币（不是月汇率估的），可以按分对单。
    amount_cny: Decimal | None = None
    cny_exact: bool = False
    org: str = ORG_MAIN  # 流水所在账户属于哪家公司（账户主体，见 approval_orgs）


# Rocky 11-10：PingPong 专用户的离岸人民币（CNH）和人民币一起比；
# 美元付款只认派安盈实际汇率折出来的人民币。
RMB_CODES = frozenset({"CNY", "CNH"})
COMBO_MAX = 4
COMBO_POOL = 12


def line_rmb(line: MatchLine) -> Decimal | None:
    """这笔付款按人民币算是多少（绝对值）；算不准的返回 None。"""
    if line.currency_code in RMB_CODES:
        return abs(line.amount)
    if line.cny_exact and line.amount_cny is not None:
        return abs(line.amount_cny)
    return None


def norm_payee(value: str) -> str:
    return PAYEE_NOISE.sub("", value or "").lower()


def payee_matches(payee: str, party: str) -> bool:
    left, right = norm_payee(payee), norm_payee(party)
    return len(left) >= 2 and bool(right) and (left in right or right in left)


def _in_window(line: MatchLine, approval: MatchApproval) -> bool:
    if approval.anchor_day is None:
        return False
    earliest = approval.anchor_day - timedelta(days=MATCH_DAYS_BEFORE)
    latest = approval.anchor_day + timedelta(days=MATCH_DAYS_AFTER)
    return earliest <= line.business_date <= latest


def _approval_open(line: MatchLine, approval: MatchApproval) -> bool:
    return (
        approval.org == line.org
        and line.amount < 0
        and approval.currency_code == "CNY"
        and approval.status not in CANCELLED_STATUSES
        and approval.amount is not None
        and approval.amount != 0
        and _in_window(line, approval)
    )


def is_candidate(line: MatchLine, approval: MatchApproval) -> bool:
    rmb = line_rmb(line)
    return (
        rmb is not None
        and _approval_open(line, approval)
        and approval.amount is not None
        and abs(rmb - abs(approval.amount)) <= AMOUNT_TOL
    )


def combo_candidates(line: MatchLine, approvals: Sequence[MatchApproval]) -> list[str]:
    """一笔付款付了几张单（Rocky 11-10，例如同一个人的两张报销一起打）：
    同一收款人、窗口内的 2–4 张单金额加起来等于这笔（按人民币，差 ≤ 0.01）。
    派安盈提现的对方是收款银行、不是人名，所以只要求这几张单是同一个收款人。
    只在恰好一种组合对得上时给出这几张单；对不上或不止一种组合都不给。"""
    rmb = line_rmb(line)
    if rmb is None:
        return []
    pool = [
        item
        for item in approvals
        if _approval_open(line, item)
        and item.amount is not None
        and abs(item.amount) < rmb
        and norm_payee(item.payee)
    ]
    by_payee: dict[str, list[MatchApproval]] = defaultdict(list)
    for item in pool:
        by_payee[norm_payee(item.payee)].append(item)
    found: list[tuple[str, ...]] = []
    for group in by_payee.values():
        group = sorted(group, key=lambda item: item.serial)[:COMBO_POOL]
        for size in range(2, min(COMBO_MAX, len(group)) + 1):
            for combo in itertools.combinations(group, size):
                total = sum((abs(item.amount or 0) for item in combo), Decimal("0"))
                if abs(total - rmb) <= AMOUNT_TOL:
                    found.append(tuple(item.serial for item in combo))
                    if len(found) > 1:
                        return []
    return list(found[0]) if found else []


def _taken(lines: Iterable[MatchLine]) -> set[str]:
    return {ref for line in lines for ref in line.refs}


def candidates_by_line(
    lines: Sequence[MatchLine], approvals: Sequence[MatchApproval]
) -> dict[str, list[str]]:
    """没挂单的流水各自有哪些候选：收款人对得上的排前面，其次按单号从新到旧。"""
    taken = _taken(lines)
    free = [item for item in approvals if item.serial not in taken]
    out: dict[str, list[str]] = {}
    for line in lines:
        if line.refs:
            continue
        hits = [item for item in free if is_candidate(line, item)]
        if hits:
            hits.sort(key=lambda item: item.serial, reverse=True)
            hits.sort(key=lambda item: not payee_matches(item.payee, line.counterparty_name))
            out[line.line_uid] = [item.serial for item in hits]
            continue
        combo = combo_candidates(line, free)
        if combo:
            out[line.line_uid] = combo
    return out


def find_auto_matches(
    lines: Sequence[MatchLine],
    approvals: Sequence[MatchApproval],
    *,
    locked_stages: frozenset[str],
    refused: frozenset[tuple[str, str]] = frozenset(),
) -> list[tuple[str, str, str]]:
    """返回要自动挂的 (流水, 单号, 依据)。

    依据 text：流水摘要或备注里写了单号。依据 match：金额 + 日期 + 收款人唯一对上，
    这笔流水只对得上这一张已同意的单，这张单也只对得上这一笔。
    已审核的流水和财务手动摘掉过的组合都不动。
    """
    known = {item.serial: item for item in approvals}
    result: list[tuple[str, str, str]] = []
    claimed: set[str] = set()
    open_lines = [line for line in lines if line.stage not in locked_stages]
    for line in open_lines:
        found = [(prefix, raw) for prefix, raw in SERIAL_IN_TEXT_ORG.findall(line.text)]
        for prefix, raw in dict.fromkeys(found):
            # 摘要里写的是飞书上的原单号：第二家公司账户的流水按它的单号（加 YC-）找；
            # 原号前面紧挨着 YC- 的就是第二家的单，不当主公司单号。
            serial = org_serial(ORG_YC if prefix else line.org, raw)
            approval = known.get(serial)
            if (
                approval is not None
                and approval.org == line.org
                and approval.status not in CANCELLED_STATUSES
                and serial not in line.refs
                and (line.line_uid, serial) not in refused
            ):
                result.append((line.line_uid, serial, "text"))
                claimed.add(serial)
    with_text = {line_uid for line_uid, _serial, _how in result}
    taken = _taken(lines) | claimed
    free = [
        item for item in approvals if item.serial not in taken and item.status == STATUS_APPROVED
    ]
    line_hits: dict[str, list[MatchApproval]] = defaultdict(list)
    approval_hits: dict[str, list[str]] = defaultdict(list)
    for line in lines:
        if line.refs or line.line_uid in with_text:
            continue
        for approval in free:
            if is_candidate(line, approval):
                line_hits[line.line_uid].append(approval)
                approval_hits[approval.serial].append(line.line_uid)
    by_uid = {line.line_uid: line for line in open_lines}
    for line_uid, hits in line_hits.items():
        open_line = by_uid.get(line_uid)
        if open_line is None or len(hits) != 1:
            continue
        approval = hits[0]
        if len(approval_hits[approval.serial]) != 1 or (line_uid, approval.serial) in refused:
            continue
        named = payee_matches(approval.payee, open_line.counterparty_name)
        if named or not norm_payee(approval.payee):
            result.append((line_uid, approval.serial, "match"))
    return result


# ---------------------------------------------------------------- 付款状态


PAID_STATE_PENDING = "待定"


def paid_state(
    *,
    status: str,
    wanted_cny: Decimal | None,
    paid_cny: Decimal,
    has_paid_lines: bool,
    paid_unknown: bool = False,
) -> str:
    """Demo 的报销闭环状态。paid_unknown：有付款流水算不出人民币，不能当成已付 0。"""
    if status in CANCELLED_STATUSES:
        return "已取消"
    if status == STATUS_PENDING:
        return "审批中"
    if paid_unknown:
        return PAID_STATE_PENDING
    if not wanted_cny:
        return "金额缺失"
    if not has_paid_lines:
        return "未付"
    if abs(paid_cny - wanted_cny) <= PAID_TOL:
        return "已付"
    if 0 < paid_cny < wanted_cny:
        return "部分已付"
    return "金额不符"

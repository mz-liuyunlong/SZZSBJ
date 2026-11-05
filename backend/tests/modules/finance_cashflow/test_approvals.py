# ruff: noqa: E501
"""审批单解析和匹配（纯函数，不用数据库）。全部合成数据。"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

import httpx
import pytest

from app.core.config import Settings
from app.integrations.feishu_approval import FeishuApprovalError, HttpFeishuApprovalClient
from app.modules.finance_cashflow import approvals as A
from app.modules.finance_cashflow import journal as J
from app.modules.integration_sync.finance_approval_catalog import (
    FinanceApprovalCodesError,
    parse_finance_approval_codes,
)
from app.modules.integration_sync.handlers.feishu_finance_approval_sync import month_slices

SERIAL = "202610010001"
OTHER = "202610010002"
LOCKED = frozenset({J.STAGE_OK1, J.STAGE_OK2})


def widget(name, kind, value, ext=None):
    return {"id": name, "name": name, "type": kind, "value": value, "ext": ext}


def account(number="9999000011112222"):
    return {
        "widgetAccountName": "测试户名",
        "widgetAccountNumber": number,
        "widgetAccountBankName": {"text": json.dumps({"bankNameZh": "测试银行"}), "value": "T"},
    }


def expense_detail(**over):
    form = [
        widget("是否开票", "radioV2", "是"),
        widget("报销事由", "textarea", "合成事由"),
        widget("费用汇总", "formula", 123.45),
        widget(
            "费用明细",
            "fieldList",
            [
                [
                    widget("内容", "input", "打车"),
                    widget("金额", "amount", 100, {"currency": "CNY"}),
                    widget("付款截图/交易记录", "image", ["https://example.invalid/a"], "a.png"),
                ],
                [widget("内容", "input", "午饭"), widget("金额", "amount", 23.45)],
            ],
        ),
        widget("收款方式", "checkboxV2", ["银行转账"]),
        widget("收款人", "input", "张三"),
        widget("收款账户", "account", account()),
        widget("附件", "attachmentV2", ["https://example.invalid/b"], "b.pdf"),
    ]
    base = {
        "serial_number": SERIAL,
        "status": "APPROVED",
        "start_time": "1790000000000",
        "end_time": "1790003600000",
        "user_id": "u1",
        "department_id": "d1",
        "form": json.dumps(form, ensure_ascii=False),
        "task_list": [{"id": "t1", "node_name": "财务办理"}],
        "timeline": [
            {"type": "START", "create_time": "1790000000000", "user_id": "u1"},
            {
                "type": "PASS",
                "task_id": "t1",
                "create_time": "1790003000000",
                "user_id": "u2",
                "comment": "已付",
                "files": [
                    {"title": "凭证.png", "type": "image", "url": "https://example.invalid/c"}
                ],
            },
        ],
        "comment_list": [
            {
                "comment": "看下",
                "create_time": "1790003100000",
                "user_id": "u2",
                "files": [{"title": "说明.pdf", "url": "https://example.invalid/d"}],
            }
        ],
    }
    base.update(over)
    return base


def parse(detail, kind="费用报销"):
    return A.parse_instance(
        detail, approval_code="CODE", kind=kind, instance_code="INST", names={"u1": "李四"}
    )


def test_parse_expense_keeps_only_last4_and_no_links():
    parsed = parse(expense_detail())
    assert parsed.serial_number == SERIAL
    assert parsed.amount == Decimal("123.45")
    assert parsed.currency_code == "CNY"
    assert parsed.payee == "张三"
    assert parsed.payee_bank == "测试银行"
    assert parsed.payee_account_last4 == "2222"
    assert parsed.applicant_user_id == "u1"
    assert parsed.reason == "合成事由"
    assert parsed.pay_method == "银行转账"
    assert [item["content"] for item in parsed.items] == ["打车", "午饭"]
    dumped = json.dumps(
        [parsed.items, parsed.attachments, parsed.records, parsed.comments], ensure_ascii=False
    )
    assert "9999000011112222" not in dumped
    assert "example.invalid" not in dumped


def test_parse_attachments_cover_form_items_timeline_and_comments():
    files = parse(expense_detail()).attachments
    assert {file["source"] for file in files} == {"form", "timeline", "comment"}
    by_title = {file["title"]: file for file in files}
    assert by_title["a.png"]["item"] == 1 and by_title["a.png"]["is_image"]
    assert by_title["b.pdf"]["item"] == 0 and not by_title["b.pdf"]["is_image"]
    assert by_title["凭证.png"]["source"] == "timeline"
    assert by_title["说明.pdf"]["source"] == "comment"


def test_parse_handled_time_comes_from_handling_node():
    parsed = parse(expense_detail())
    assert parsed.handled_at == datetime.fromtimestamp(1790003000, A.SHANGHAI)
    assert parsed.records[1]["act"] == "通过"
    assert parsed.records[1]["node"] == "财务办理"
    assert parsed.records[1]["files"] == 1


@pytest.mark.parametrize(
    ("kind", "widgets", "amount", "reason"),
    [
        ("付款申请", [widget("付款事由", "textarea", "货款"), widget("付款金额", "amount", 8.5, {"currency": "USD"})], "8.5", "货款"),
        ("备用金申请", [widget("申请事由", "textarea", "备用"), widget("申请金额", "amount", 500)], "500", "备用"),
        ("备用金核销", [widget("费用说明", "textarea", "核销"), widget("核销金额（元）", "amount", 40)], "40", "核销"),
    ],
)  # fmt: skip
def test_parse_each_kind_amount_and_reason(kind, widgets, amount, reason):
    parsed = parse(expense_detail(form=json.dumps(widgets, ensure_ascii=False)), kind)
    assert parsed.amount == Decimal(amount)
    assert parsed.reason == reason


def test_parse_usd_currency_payee_falls_back_to_account_and_relation():
    form = [
        widget("付款金额", "amount", 8.5, {"currency": "USD"}),
        widget("收款账户", "account", account()),
        widget("关联备用金", "connect", [{"title": f"备用金 {OTHER}"}]),
    ]
    parsed = parse(expense_detail(form=json.dumps(form, ensure_ascii=False)))
    assert parsed.currency_code == "USD"
    assert parsed.payee == "测试户名"
    assert parsed.related_serial == OTHER


def test_parse_reverted_counts_as_cancelled():
    assert parse(expense_detail(reverted=True)).status == A.STATUS_REVERTED
    assert A.STATUS_REVERTED in A.CANCELLED_STATUSES


def test_parse_rejects_bad_structure():
    with pytest.raises(A.ApprovalParseError):
        parse(expense_detail(form="not json"))
    with pytest.raises(A.ApprovalParseError):
        parse(expense_detail(serial_number=""))


def test_people_of_collects_everyone():
    assert A.people_of(expense_detail()) == {"u1", "u2"}


# ---------------------------------------------------------------- 匹配


def approval(serial=SERIAL, *, amount="100", payee="张三", status="APPROVED", day=date(2026, 10, 1), cur="CNY"):  # fmt: skip
    return A.MatchApproval(serial, status, Decimal(amount), cur, payee, day)


def line(uid="L1", *, amount="-100", party="张三", day=date(2026, 10, 2), refs=(), stage="todo", text="", cur="CNY"):  # fmt: skip
    return A.MatchLine(uid, day, Decimal(amount), cur, party, text, tuple(refs), stage)


def auto(lines, approvals, **kw):
    return A.find_auto_matches(lines, approvals, locked_stages=LOCKED, **kw)


def test_unique_match_is_attached():
    assert auto([line()], [approval()]) == [("L1", SERIAL, "match")]


@pytest.mark.parametrize(
    "kw",
    [
        {"amount": "-100.02"},
        {"day": date(2026, 9, 27)},
        {"day": date(2026, 11, 16)},
        {"party": "王五"},
        {"party": ""},
        {"cur": "USD"},
        {"amount": "100"},
    ],
)
def test_not_auto_attached_when_something_differs(kw):
    assert auto([line(**kw)], [approval()]) == []


def test_window_edges_are_inclusive():
    assert auto([line(day=date(2026, 9, 28))], [approval()])
    assert auto([line(day=date(2026, 11, 15))], [approval()])


def test_two_approvals_for_one_line_goes_to_candidates():
    pair = [approval(), approval(OTHER)]
    assert auto([line()], pair) == []
    assert A.candidates_by_line([line()], pair) == {"L1": [OTHER, SERIAL]}


def test_two_lines_for_one_approval_goes_to_candidates():
    lines = [line("L1"), line("L2")]
    assert auto(lines, [approval()]) == []
    assert A.candidates_by_line(lines, [approval()]) == {"L1": [SERIAL], "L2": [SERIAL]}


def test_candidates_put_payee_match_first():
    pair = [approval(payee="张三"), approval(OTHER, payee="王五")]
    assert A.candidates_by_line([line()], pair)["L1"] == [SERIAL, OTHER]


def test_candidates_skip_linked_lines_and_taken_approvals():
    lines = [line("L1", refs=[SERIAL]), line("L2")]
    assert A.candidates_by_line(lines, [approval()]) == {}


def test_approval_without_payee_can_match_when_unique():
    assert auto([line()], [approval(payee="")]) == [("L1", SERIAL, "match")]


def test_pending_is_candidate_but_never_auto_attached():
    pending = approval(status="PENDING")
    assert auto([line()], [pending]) == []
    assert A.candidates_by_line([line()], [pending]) == {"L1": [SERIAL]}


@pytest.mark.parametrize("status", ["REJECTED", "CANCELED", "DELETED", "REVERTED"])
def test_cancelled_is_neither_candidate_nor_attached(status):
    gone = approval(status=status)
    assert auto([line()], [gone]) == []
    assert A.candidates_by_line([line()], [gone]) == {}


@pytest.mark.parametrize("stage", [J.STAGE_OK1, J.STAGE_OK2])
def test_reviewed_lines_are_left_alone(stage):
    assert auto([line(stage=stage)], [approval()]) == []
    assert auto([line(stage=stage, text=f"付款 {SERIAL}")], [approval()]) == []


def test_refused_pair_is_not_attached_again():
    assert auto([line()], [approval()], refused=frozenset({("L1", SERIAL)})) == []
    text_line = line(text=f"付款 {SERIAL}")
    assert auto([text_line], [approval()], refused=frozenset({("L1", SERIAL)})) == []


def test_serial_written_on_the_line_wins_regardless_of_amount():
    hit = line(amount="-1", party="", text=f"摘要 {SERIAL} 备注")
    assert auto([hit], [approval()]) == [("L1", SERIAL, "text")]


def test_serial_in_text_ignores_unknown_and_longer_digit_runs():
    assert auto([line(amount="-1", text="202699999999")], [approval()]) == []
    assert auto([line(amount="-1", text=f"9{SERIAL}")], [approval()]) == []


def test_payee_noise_words_do_not_block_match():
    assert A.payee_matches("甲乙科技有限公司", "甲乙")
    assert not A.payee_matches("甲", "甲乙")


# ---------------------------------------------------------------- 分类优先级


def journal_line(**over):
    base = {
        "line_uid": "L1",
        "account_key": "A",
        "provider": "boc",
        "currency_code": "CNY",
        "business_date": date(2026, 10, 2),
        "amount": Decimal("-100"),
        "balance_after": None,
        "description": "规则词",
        "memo": "",
        "counterparty_name": "",
        "file_row_order": 1,
    }
    base.update(over)
    return J.LineInput(**base)


def classify(**over):
    classifier = J.Classifier([J.Rule("text", "规则词", "G01", 1)])
    result = J.compute_journal([journal_line(**over)], classifier, frozenset(), lambda _d: None)
    item = result.lines[0]
    return item.category_code, item.category_source


def test_category_priority_manual_over_approval_over_rule():
    assert classify() == ("G01", J.SOURCE_RULE)
    assert classify(approval_category="G02") == ("G02", J.SOURCE_APPROVAL)
    assert classify(approval_category="G02", manual_category="G03") == ("G03", J.SOURCE_MANUAL)


def test_rule_based_approval_category_only_fills_blanks():
    assert classify(approval_rule_category="G02") == ("G01", J.SOURCE_RULE)
    assert classify(description="别的", approval_rule_category="G02") == (
        "G02",
        J.SOURCE_APPROVAL_RULE,
    )


def test_form_category_code_and_single_value():
    names = {"办公费": "G02"}
    assert A.form_category_code("管理费用 办公费", names) == "G02"
    assert A.form_category_code("别的", names) is None
    assert A.form_category_code("", names) is None
    assert A.single_value(["G01", "G01", None]) == "G01"
    assert A.single_value(["G01", "G02"]) is None


# ---------------------------------------------------------------- 付款状态


@pytest.mark.parametrize(
    ("status", "wanted", "paid", "has", "expected"),
    [
        ("CANCELED", "100", "0", False, "已取消"),
        ("PENDING", "100", "0", False, "审批中"),
        ("APPROVED", None, "0", False, "金额缺失"),
        ("APPROVED", "100", "0", False, "未付"),
        ("APPROVED", "100", "100.5", True, "已付"),
        ("APPROVED", "100", "40", True, "部分已付"),
        ("APPROVED", "100", "130", True, "金额不符"),
    ],
)
def test_paid_state(status, wanted, paid, has, expected):
    state = A.paid_state(
        status=status,
        wanted_cny=Decimal(wanted) if wanted else None,
        paid_cny=Decimal(paid),
        has_paid_lines=has,
    )
    assert state == expected


# ---------------------------------------------------------------- 飞书客户端和时间窗口


def test_codes_parse_all_four_kinds():
    raw = "费用报销=TEST-0001, 付款申请=TEST-0002,备用金申请=TEST-0003,备用金核销=TEST-0004,"
    assert parse_finance_approval_codes(raw) == {
        "费用报销": "TEST-0001",
        "付款申请": "TEST-0002",
        "备用金申请": "TEST-0003",
        "备用金核销": "TEST-0004",
    }


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "费用报销=TEST-0001",
        "费用报销=TEST-0001,付款申请=TEST-0002,备用金申请=TEST-0003,备用金核销=",
        "费用报销=TEST-0001,付款申请=TEST-0002,备用金申请=TEST-0003,别的=TEST-0004",
        "费用报销=TEST-0001,费用报销=TEST-0002,备用金申请=TEST-0003,备用金核销=TEST-0004",
        "费用报销",
    ],
)
def test_codes_missing_or_incomplete_raise_fixed_code_without_values(raw):
    with pytest.raises(FinanceApprovalCodesError) as caught:
        parse_finance_approval_codes(raw)
    assert str(caught.value) == "SYNC_FEISHU_APPROVAL_CODES_NOT_CONFIGURED"
    assert "TEST-" not in str(caught.value)


def test_month_slices_never_exceed_30_days_and_cover_window():
    start = datetime(2026, 7, 1, tzinfo=A.SHANGHAI)
    end = datetime(2026, 10, 15, tzinfo=A.SHANGHAI)
    slices = month_slices(start, end)
    assert slices[0][0] == int(start.timestamp() * 1000)
    assert slices[-1][1] == int(end.timestamp() * 1000)
    for first, second in zip(slices, slices[1:], strict=False):
        assert second[0] == first[1] + 1
    assert all(stop - begin < 30 * 86_400_000 for begin, stop in slices)


def make_client(handler):
    settings = Settings.model_construct(
        feishu_app_id="synthetic-id",
        feishu_app_secret=None,
        feishu_base_url="https://feishu.invalid",
        feishu_request_timeout_ms=1000,
    )
    from pydantic import SecretStr

    settings.feishu_app_secret = SecretStr("synthetic-secret")
    return HttpFeishuApprovalClient(
        settings,
        http_client=httpx.Client(
            base_url="https://feishu.invalid", transport=httpx.MockTransport(handler)
        ),
    )


def token_ok(request):
    if request.url.path.endswith("/internal"):
        return httpx.Response(200, json={"code": 0, "tenant_access_token": "tok"})
    return None


def test_client_sends_required_list_params_in_milliseconds():
    seen = {}

    def handler(request):
        if (reply := token_ok(request)) is not None:
            return reply
        seen.update(request.url.params)
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={"code": 0, "data": {"instance_code_list": ["i1"], "has_more": False}},
        )

    page = make_client(handler).list_instances(
        approval_code="CODE", start_ms=1790000000000, end_ms=1790000000999, page_size=100, page_token=""
    )  # fmt: skip
    assert page.instance_codes == ["i1"]
    assert seen["approval_code"] == "CODE"
    assert seen["start_time"] == "1790000000000"
    assert seen["end_time"] == "1790000000999"
    assert seen["page_size"] == "100"
    assert seen["auth"] == "Bearer tok"


def test_client_error_carries_status_and_provider_code_but_no_secret():
    def handler(request):
        if (reply := token_ok(request)) is not None:
            return reply
        return httpx.Response(400, json={"code": 1390001, "msg": "bad"})

    with pytest.raises(FeishuApprovalError) as caught:
        make_client(handler).list_instances(
            approval_code="CODE", start_ms=1, end_ms=2, page_size=100, page_token=""
        )
    assert caught.value.code == "FEISHU_APPROVAL_LIST_HTTP_400_CODE_1390001"
    assert "synthetic-secret" not in str(caught.value)


def test_rename_people_keeps_id_when_employee_is_unknown():
    assert A.rename_people("u1、u9", {"u1": "李四"}) == "李四、u9"
    assert A.rename_people("", {"u1": "李四"}) == ""


def test_client_requires_credentials():
    settings = Settings.model_construct(feishu_app_id=None, feishu_app_secret=None)
    with pytest.raises(FeishuApprovalError):
        HttpFeishuApprovalClient(settings)

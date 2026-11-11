# ruff: noqa: E501
"""日记账计算（纯函数，全部合成数据）：不需要数据库。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.modules.finance_cashflow import journal as J
from app.modules.fx_rates.reader import usd_cny_rate_for

CATEGORIES = frozenset({"G01", "F01", "T02", "X01"})
INTERNAL = frozenset({"T02"})
CLASSIFIER = J.Classifier(
    [
        J.Rule("party", "公积金中心", "G01", 10),
        J.Rule("text", "手续费", "F01", 20),
        J.Rule("text", "内部调拨|往来款", "T02", 30),
    ]
)


def line(uid, amount, *, account="A", cur="CNY", day="2026-10-10", desc="", party="", **extra):
    return J.LineInput(
        line_uid=uid,
        account_key=account,
        provider=extra.pop("provider", "boc"),
        currency_code=cur,
        business_date=date.fromisoformat(day),
        amount=Decimal(str(amount)),
        balance_after=extra.pop("balance", None),
        description=desc,
        memo="",
        counterparty_name=party,
        file_row_order=extra.pop("order", 1),
        **extra,
    )


def compute(lines, rate=None, exclusions=()):
    return J.compute_journal(lines, CLASSIFIER, INTERNAL, lambda _day: rate, exclusions)


def by_uid(result):
    return {item.source.line_uid: item for item in result.lines}


def test_classification_priority_manual_then_party_then_text():
    result = by_uid(
        compute(
            [
                line("m", -1, desc="手续费", manual_category="G01"),
                line("p", -1, desc="手续费", party="某地公积金中心"),
                line("t", -1, desc="转账手续费"),
                line("n", -1, desc="看不懂"),
            ]
        )
    )
    assert (result["m"].category_code, result["m"].category_source) == ("G01", "人工")
    assert (result["p"].category_code, result["p"].category_source) == ("G01", "规则")
    assert result["t"].category_code == "F01"
    assert (result["n"].category_code, result["n"].category_source) == (None, "")


def test_pair_same_currency_within_one_yuan_and_15_days():
    result = compute(
        [
            line("o", -100, account="A", desc="内部调拨", day="2026-10-01"),
            line("i", "99.50", account="B", desc="内部调拨", day="2026-10-16"),
        ]
    )
    items = by_uid(result)
    assert items["o"].pair_id and items["o"].pair_id == items["i"].pair_id
    assert not [alert for alert in result.alerts if alert.type == J.ALERT_UNPAIRED]


def test_pair_not_made_outside_15_days_or_same_account():
    result = compute(
        [
            line("o", -100, account="A", desc="内部调拨", day="2026-10-01"),
            line("late", 100, account="B", desc="内部调拨", day="2026-10-17"),
            line("same", 100, account="A", desc="内部调拨", day="2026-10-02"),
        ]
    )
    assert {alert.line_uid for alert in result.alerts if alert.type == J.ALERT_UNPAIRED} == {
        "o",
        "late",
        "same",
    }


def test_pair_cross_currency_by_usd_in_memo():
    result = by_uid(
        compute(
            [
                line("usd", -100, account="U", cur="USD", desc="内部调拨"),
                line("cny", 700, account="C", desc="往来款 USD 100.00"),
            ]
        )
    )
    assert result["usd"].pair_id == result["cny"].pair_id is not None


def test_pair_one_out_many_in():
    result = by_uid(
        compute(
            [
                line("o", -300, account="A", desc="内部调拨"),
                line("i1", 100, account="B", desc="内部调拨"),
                line("i2", 200, account="C", desc="内部调拨"),
            ]
        )
    )
    assert result["o"].pair_id == result["i1"].pair_id == result["i2"].pair_id is not None


def test_pingpong_usd_to_cnh_paired_by_rate_range_and_flagged():
    result = by_uid(
        compute(
            [
                line("u", -100, account="PU", cur="USD", desc="内部调拨", provider="pingpong"),
                line("c", 700, account="PC", cur="CNH", desc="内部调拨", provider="pingpong"),
            ]
        )
    )
    assert result["u"].pair_id == result["c"].pair_id is not None
    assert "汇率区间配对待核" in result["c"].flags


def test_not_in_journal_is_a_hint_not_an_anomaly():
    result = compute([line("x", -5, desc="内部调拨 忽略")])
    assert [alert.type for alert in result.alerts] == [J.HINT_NOT_IN_JOURNAL]


def test_fx_cny_usd_and_cnh():
    result = by_uid(
        compute(
            [line("c", 10), line("u", 10, cur="USD"), line("h", 10, cur="CNH")],
            rate=Decimal("7.1"),
        )
    )
    assert result["c"].amount_cny == Decimal("10")
    assert result["u"].amount_cny == Decimal("71.0000")
    assert result["h"].amount_cny == Decimal("10")  # CNH 按 1:1
    assert by_uid(compute([line("u", 10, cur="USD")]))["u"].amount_cny is None


def test_month_rate_is_read_by_business_month_and_no_fallback():
    rates = {"2026-09": Decimal("7.0"), "2026-10": Decimal("7.1")}
    assert usd_cny_rate_for(rates, date(2026, 10, 20)) == Decimal("7.1")
    assert usd_cny_rate_for(rates, date(2026, 8, 20)) is None
    assert usd_cny_rate_for(rates, date(2026, 11, 1)) is None


def test_balance_alert_when_previous_balance_is_missing():
    result = compute(
        [
            line("a", 10, balance=Decimal("110"), order=1),
            line("b", 10, balance=Decimal("120"), order=2),
            line("gap", 10, balance=Decimal("500"), order=3),
        ]
    )
    assert [alert.line_uid for alert in result.alerts if alert.type == J.ALERT_BALANCE] == ["gap"]
    gap = next(alert for alert in result.alerts if alert.type == J.ALERT_BALANCE)
    assert gap.currency_code == "CNY"


def test_unpaired_alert_carries_the_line_currency():
    result = compute([line("u", -100, cur="USD", desc="内部调拨")])
    [alert] = [item for item in result.alerts if item.type == J.ALERT_UNPAIRED]
    assert (alert.amount, alert.currency_code) == (Decimal("-100"), "USD")


def test_pingpong_has_no_balance_alert():
    result = compute(
        [
            line("a", 10, balance=Decimal("110"), order=1, provider="pingpong"),
            line("gap", 10, balance=Decimal("500"), order=2, provider="pingpong"),
        ]
    )
    assert not result.alerts


def entry(amount, *, ref=None, day=None, account=None, contains=None):
    return J.ExclusionEntry(1, ref, day, account, contains, Decimal(str(amount)), "其他部门")


def test_exclusion_list_by_ref_is_deducted_in_date_order():
    result = compute(
        [
            line("late", -80, refs=["209910100001"], day="2026-10-12"),
            line("early", -50, refs=["209910100001"], day="2026-10-11"),
        ],
        exclusions=[entry(100, ref="209910100001")],
    )
    items = by_uid(result)
    assert items["early"].list_excluded_cny == Decimal("50")
    assert items["late"].list_excluded_cny == Decimal("50")
    assert "已剔除" in items["early"].flags
    assert "部分剔除" in items["late"].flags
    assert not result.alerts


def test_exclusion_not_found_or_not_enough_raises_anomaly():
    missing = compute([line("a", -80)], exclusions=[entry(100, ref="209910100001")])
    assert [alert.type for alert in missing.alerts] == [J.ALERT_EXCLUSION]
    assert missing.alerts[0].amount == Decimal("100")
    assert missing.alerts[0].currency_code == "CNY"
    short = compute(
        [line("a", -80, refs=["209910100001"])], exclusions=[entry(100, ref="209910100001")]
    )
    assert short.alerts[0].amount == Decimal("20")
    assert "第 1 条" in short.alerts[0].message


def test_exclusion_alert_date_prefers_txn_date_then_registered_on():
    def alert_date(**fields):
        entry_ = J.ExclusionEntry(
            1, "209910100001", None, None, None, Decimal("5"), "其他部门", **fields
        )
        return compute([], exclusions=[entry_]).alerts[0].date

    assert alert_date(registered_on=date(2026, 10, 22)) == "2026-10-22"
    assert alert_date() == ""
    dated = J.ExclusionEntry(
        1, None, date(2026, 9, 24), None, "运费", Decimal("5"), "其他部门", date(2026, 10, 22)
    )
    assert compute([], exclusions=[dated]).alerts[0].date == "2026-09-24"


def test_exclusion_by_date_account_and_keyword():
    result = compute(
        [
            line("a", -100, account="A", desc="大额运费"),
            line("b", -100, account="B", desc="大额运费"),
        ],
        exclusions=[entry(100, day=date(2026, 10, 10), account="A", contains="运费")],
    )
    items = by_uid(result)
    assert items["a"].list_excluded_cny == Decimal("100")
    assert items["b"].list_excluded_cny == Decimal("0")


def test_exclusion_skips_foreign_line_without_rate():
    result = compute(
        [line("u", -100, cur="USD", refs=["209910100001"])],
        exclusions=[entry(100, ref="209910100001")],
    )
    assert result.alerts[0].type == J.ALERT_EXCLUSION
    assert by_uid(result)["u"].list_excluded_cny == Decimal("0")


def test_whole_line_exclusion_becomes_x01_and_partial_keeps_category():
    items = by_uid(
        compute(
            [
                line("w", -10, desc="手续费", exclude_amount=Decimal("10")),
                line("p", -10, desc="手续费", exclude_amount=Decimal("3")),
            ]
        )
    )
    assert (items["w"].category_code, items["w"].category_source) == ("X01", "人工")
    assert "已剔除" in items["w"].flags
    assert items["p"].category_code == "F01"
    assert "部分剔除" in items["p"].flags


def apply(state, kind, payload=None, reason=None, amount="-10"):
    return J.apply_event(
        state,
        kind=kind,
        payload=payload or {},
        reason=reason,
        line_amount=Decimal(amount),
        valid_categories=CATEGORIES,
    )


def test_review_flow():
    state = J.ReviewState()
    apply(state, J.KIND_REVIEW1_REJECT, reason="摘要不对")
    assert (state.stage, state.stage_reason) == (J.STAGE_REJ1, "摘要不对")
    apply(state, J.KIND_REVIEW1_PASS)
    assert (state.stage, state.stage_reason) == (J.STAGE_OK1, None)
    apply(state, J.KIND_REVIEW2_REJECT, reason="再核")
    assert (state.stage, state.stage_reason) == (J.STAGE_REJ2, "再核")
    apply(state, J.KIND_REVIEW1_PASS)
    apply(state, J.KIND_REVIEW2_PASS)
    assert state.stage == J.STAGE_OK2


@pytest.mark.parametrize(
    ("stage", "kind", "reason", "status", "code"),
    [
        (J.STAGE_TODO, J.KIND_REVIEW2_PASS, None, 409, J.ERR_STAGE_NOT_ALLOWED),
        (J.STAGE_REJ1, J.KIND_REVIEW2_REJECT, "x", 409, J.ERR_STAGE_NOT_ALLOWED),
        (J.STAGE_OK1, J.KIND_REVIEW1_PASS, None, 409, J.ERR_STAGE_NOT_ALLOWED),
        (J.STAGE_OK2, J.KIND_REVIEW1_REJECT, "x", 409, J.ERR_STAGE_NOT_ALLOWED),
        (J.STAGE_OK2, J.KIND_REVIEW2_PASS, None, 409, J.ERR_STAGE_NOT_ALLOWED),
        (J.STAGE_TODO, J.KIND_REVIEW1_REJECT, " ", 422, J.ERR_INVALID_EVENT),
        (J.STAGE_OK1, J.KIND_REVIEW2_REJECT, None, 422, J.ERR_INVALID_EVENT),
    ],
)
def test_review_rejections(stage, kind, reason, status, code):
    with pytest.raises(J.EventRejectedError) as caught:
        apply(J.ReviewState(stage=stage), kind, reason=reason)
    assert (caught.value.status_code, caught.value.code) == (status, code)


@pytest.mark.parametrize(
    ("kind", "payload", "reason", "start"),
    [
        (J.KIND_SET_CATEGORY, {"category_code": "G01"}, None, {}),
        (J.KIND_ATTACH_REF, {"ref": "209910100001"}, None, {}),
        (J.KIND_DETACH_REF, {"ref": "209910100001"}, None, {"refs": ["209910100001"]}),
        (J.KIND_EXCLUDE, {}, "其他部门", {}),
        (J.KIND_UNEXCLUDE, {}, None, {"exclude_amount": Decimal("10")}),
    ],
)
@pytest.mark.parametrize("stage", [J.STAGE_OK1, J.STAGE_OK2])
def test_changes_after_review_reset_to_todo(kind, payload, reason, start, stage):
    state = J.ReviewState(stage=stage, **start)
    assert apply(state, kind, payload, reason) is True
    assert state.stage == J.STAGE_TODO


def test_changes_before_review_do_not_report_reset():
    state = J.ReviewState(stage=J.STAGE_REJ1, stage_reason="x")
    assert apply(state, J.KIND_SET_CATEGORY, {"category_code": "G01"}) is False
    assert state.stage == J.STAGE_REJ1


def test_x01_cannot_be_set_as_category():
    with pytest.raises(J.EventRejectedError):
        apply(J.ReviewState(), J.KIND_SET_CATEGORY, {"category_code": "X01"})


def test_clearing_manual_category_falls_back_to_rule():
    state = J.ReviewState(manual_category="G01")
    apply(state, J.KIND_SET_CATEGORY, {"category_code": None})
    assert state.manual_category is None


def test_bad_ref_and_duplicate_ref():
    with pytest.raises(J.EventRejectedError):
        apply(J.ReviewState(), J.KIND_ATTACH_REF, {"ref": "abc"})
    with pytest.raises(J.EventRejectedError):
        apply(J.ReviewState(refs=["209910100001"]), J.KIND_ATTACH_REF, {"ref": "209910100001"})


def test_exclude_amount_rules():
    state = J.ReviewState()
    apply(state, J.KIND_EXCLUDE, {"amount": "3.5"}, "其他部门")
    assert state.exclude_amount == Decimal("3.5000")
    full = J.ReviewState()
    apply(full, J.KIND_EXCLUDE, {}, "其他部门")
    assert full.exclude_amount == Decimal("10")
    for bad in ("0", "-1", "10.01", "abc", "NaN"):
        with pytest.raises(J.EventRejectedError):
            apply(J.ReviewState(), J.KIND_EXCLUDE, {"amount": bad}, "其他部门")
    with pytest.raises(J.EventRejectedError):
        apply(J.ReviewState(), J.KIND_EXCLUDE, {}, " ")


def test_undo_first_review_back_to_todo():
    for start in (J.STAGE_OK1, J.STAGE_REJ1):
        state = J.ReviewState(stage=start, stage_reason="x")
        assert apply(state, J.KIND_REVIEW1_UNDO) is False
        assert (state.stage, state.stage_reason) == (J.STAGE_TODO, None)


def test_undo_final_review_back_to_waiting_final():
    for start in (J.STAGE_OK2, J.STAGE_REJ2):
        state = J.ReviewState(stage=start, stage_reason="x")
        assert apply(state, J.KIND_REVIEW2_UNDO) is False
        assert (state.stage, state.stage_reason) == (J.STAGE_OK1, None)


@pytest.mark.parametrize(
    ("stage", "kind"),
    [
        (J.STAGE_TODO, J.KIND_REVIEW1_UNDO),
        (J.STAGE_OK2, J.KIND_REVIEW1_UNDO),
        (J.STAGE_REJ2, J.KIND_REVIEW1_UNDO),
        (J.STAGE_TODO, J.KIND_REVIEW2_UNDO),
        (J.STAGE_OK1, J.KIND_REVIEW2_UNDO),
    ],
)
def test_undo_in_wrong_stage_is_rejected(stage, kind):
    with pytest.raises(J.EventRejectedError) as caught:
        apply(J.ReviewState(stage=stage), kind)
    assert (caught.value.status_code, caught.value.code) == (409, J.ERR_STAGE_NOT_ALLOWED)


def test_set_text_keeps_review_and_blank_restores_original():
    state = J.ReviewState(stage=J.STAGE_OK2)
    assert apply(state, J.KIND_SET_TEXT, {"description": " 房租 ", "memo": "10 月"}) is False
    assert (state.manual_description, state.manual_memo, state.stage) == (
        "房租",
        "10 月",
        J.STAGE_OK2,
    )
    apply(state, J.KIND_SET_TEXT, {"memo": ""})
    assert (state.manual_description, state.manual_memo) == ("房租", None)
    for bad in ({}, {"memo": 5}, {"description": "长" * 501}):
        with pytest.raises(J.EventRejectedError):
            apply(J.ReviewState(), J.KIND_SET_TEXT, bad)


def test_split_then_choose_category_per_part():
    state = J.ReviewState(stage=J.STAGE_OK1)
    assert apply(state, J.KIND_SPLIT, {"amounts": ["6", "4"]}) is True
    assert state.stage == J.STAGE_TODO
    assert state.parts == [
        {"amount": "6.0000", "category_code": None},
        {"amount": "4.0000", "category_code": None},
    ]
    apply(state, J.KIND_SET_PART_CATEGORY, {"index": 1, "category_code": "G01"})
    assert state.parts[1]["category_code"] == "G01"
    with pytest.raises(J.EventRejectedError):
        apply(state, J.KIND_SET_CATEGORY, {"category_code": "G01"})
    apply(state, J.KIND_UNSPLIT)
    assert state.parts is None


@pytest.mark.parametrize(
    ("kind", "payload", "start"),
    [
        (J.KIND_SPLIT, {"amounts": ["10"]}, {}),
        (J.KIND_SPLIT, {"amounts": ["6", "3"]}, {}),
        (J.KIND_SPLIT, {"amounts": ["11", "-1"]}, {}),
        (J.KIND_SPLIT, {"amounts": ["abc", "10"]}, {}),
        (J.KIND_SPLIT, {}, {}),
        (J.KIND_SET_PART_CATEGORY, {"index": 0, "category_code": "G01"}, {}),
        (J.KIND_UNSPLIT, {}, {}),
    ],
)
def test_split_rejections(kind, payload, start):
    with pytest.raises(J.EventRejectedError):
        apply(J.ReviewState(**start), kind, payload)


def test_part_text_keeps_review_and_blank_clears():
    state = J.ReviewState(stage=J.STAGE_OK1)
    apply(state, J.KIND_SPLIT, {"amounts": ["6", "4"]})
    state.stage = J.STAGE_OK1
    payload = {"index": 1, "description": " 手续费 ", "memo": "银行扣"}
    assert apply(state, J.KIND_SET_PART_TEXT, payload) is False
    assert state.stage == J.STAGE_OK1
    assert state.parts[1] == {
        "amount": "4.0000",
        "category_code": None,
        "description": "手续费",
        "memo": "银行扣",
    }
    apply(state, J.KIND_SET_PART_CATEGORY, {"index": 1, "category_code": "G01"})
    apply(state, J.KIND_SET_PART_TEXT, {"index": 1, "memo": ""})
    assert state.parts[1] == {"amount": "4.0000", "category_code": "G01", "description": "手续费"}
    for payload in ({"index": 1}, {"index": 2, "memo": "x"}, {"index": 0, "memo": "x" * 501}):
        with pytest.raises(J.EventRejectedError):
            apply(state, J.KIND_SET_PART_TEXT, payload)
    with pytest.raises(J.EventRejectedError):
        apply(J.ReviewState(), J.KIND_SET_PART_TEXT, {"index": 0, "memo": "x"})


def test_split_part_rejects_bad_index_and_x01():
    parts = [{"amount": "6", "category_code": None}, {"amount": "4", "category_code": None}]
    for payload in (
        {"index": 2, "category_code": "G01"},
        {"index": True, "category_code": "G01"},
        {"index": 0, "category_code": "X01"},
    ):
        with pytest.raises(J.EventRejectedError):
            apply(J.ReviewState(parts=[dict(p) for p in parts]), J.KIND_SET_PART_CATEGORY, payload)


# ---------------------------------------------------------------- 第三轮（rocky 11-05）


def test_gap_pair_by_tail_number_reports_fee_gap():
    # 合成数据：付出 10000 给尾号 0000 的户，两天后到 9986.80：差 13.20（0.13%）配上，差额进异常。
    result = compute(
        [
            line(
                "o",
                -10000,
                account="P",
                cur="USD",
                day="2026-10-24",
                desc="内部调拨",
                counterparty_last4="0000",
            ),
            line(
                "i",
                "9986.80",
                account="B",
                cur="USD",
                day="2026-10-26",
                desc="内部调拨",
                account_last4="0000",
            ),
        ]
    )
    items = by_uid(result)
    assert items["o"].pair_id and items["o"].pair_id == items["i"].pair_id
    gaps = [alert for alert in result.alerts if alert.type == J.ALERT_PAIR_GAP]
    assert [(alert.line_uid, alert.amount, alert.currency_code) for alert in gaps] == [
        ("o", Decimal("13.20"), "USD")
    ]
    assert not [alert for alert in result.alerts if alert.type == J.ALERT_UNPAIRED]


@pytest.mark.parametrize(
    ("received", "day", "tail"),
    [
        ("9900", "2026-10-26", "0000"),  # 差 100 > 50 美元上限
        ("9986.80", "2026-10-30", "0000"),  # 6 天
        ("9986.80", "2026-10-26", "9999"),  # 尾号对不上
        ("10010", "2026-10-26", "0000"),  # 到账比扣款多
    ],
)
def test_gap_pair_rejected_outside_tolerance(received, day, tail):
    result = compute(
        [
            line(
                "o",
                -10000,
                account="P",
                cur="USD",
                day="2026-10-24",
                desc="内部调拨",
                counterparty_last4="0000",
            ),
            line(
                "i", received, account="B", cur="USD", day=day, desc="内部调拨", account_last4=tail
            ),
        ]
    )
    assert by_uid(result)["o"].pair_id is None
    assert not [alert for alert in result.alerts if alert.type == J.ALERT_PAIR_GAP]


def test_cnh_out_pairs_with_cny_in_for_the_same_amount():
    result = compute(
        [
            line("o", -1000, account="P", cur="CNH", desc="内部调拨"),
            line("i", 1000, account="B", cur="CNY", desc="内部调拨"),
        ]
    )
    items = by_uid(result)
    assert items["o"].pair_id and items["o"].pair_id == items["i"].pair_id
    assert "汇率区间配对待核" not in items["o"].flags
    assert not [alert for alert in result.alerts if alert.type == J.ALERT_PAIR_GAP]
    assert not [alert for alert in result.alerts if alert.type == J.ALERT_UNPAIRED]


def test_cnh_out_pairs_with_cny_in_and_reports_the_fee_gap():
    result = compute(
        [
            line("o", -1000, account="P", cur="CNH", desc="内部调拨", counterparty_last4="0000"),
            line("i", 995, account="B", cur="CNY", desc="内部调拨", account_last4="0000"),
        ]
    )
    items = by_uid(result)
    assert items["o"].pair_id and items["o"].pair_id == items["i"].pair_id
    gaps = [alert for alert in result.alerts if alert.type == J.ALERT_PAIR_GAP]
    assert [(alert.line_uid, alert.amount) for alert in gaps] == [("o", Decimal("5"))]


def test_confirmed_fee_pairs_without_gap_alert():
    parts = [
        {"amount": "9986.8000", "category_code": "T02"},
        {"amount": "13.2000", "category_code": "F01", "fee_layer": "fee"},
    ]
    result = compute(
        [
            line(
                "o",
                -10000,
                account="P",
                cur="USD",
                day="2026-10-24",
                desc="内部调拨",
                counterparty_last4="0000",
                parts=parts,
            ),
            line(
                "i",
                "9986.80",
                account="B",
                cur="USD",
                day="2026-10-26",
                desc="内部调拨",
                account_last4="0000",
            ),
        ]
    )
    assert by_uid(result)["o"].pair_id == by_uid(result)["i"].pair_id
    assert not [alert for alert in result.alerts if alert.type == J.ALERT_PAIR_GAP]


def test_manual_pair_wins_and_reports_gap_even_without_internal_category():
    result = compute(
        [
            line("o", -500, account="A", desc="看不懂", manual_pair="M1"),
            line("i", 480, account="B", day="2026-10-28", desc="看不懂", manual_pair="M1"),
            line("x", 480, account="C", desc="内部调拨"),
        ]
    )
    items = by_uid(result)
    assert items["o"].pair_id == items["i"].pair_id and "人工配对" in items["o"].flags
    assert items["x"].pair_id is None
    gaps = [alert for alert in result.alerts if alert.type == J.ALERT_PAIR_GAP]
    assert [(alert.line_uid, alert.amount) for alert in gaps] == [("o", Decimal("20"))]


def test_rule_x01_is_auto_excluded_and_manual_category_undoes_it():
    classifier = J.Classifier([J.Rule("text", "归集-万里汇主账号", "X01", 1)])
    lines = [
        line("s", "-50.00", desc="归集-万里汇主账号 / 子账号 甲"),
        line("u", "-50.00", desc="归集-万里汇主账号 / 子账号 甲", manual_category="G01"),
    ]
    items = by_uid(J.compute_journal(lines, classifier, INTERNAL, lambda _day: None))
    assert (items["s"].category_code, items["s"].auto_exclude_reason) == (
        "X01",
        J.AUTO_EXCLUDE_REASON,
    )
    assert "已剔除" in items["s"].flags
    assert (items["u"].category_code, items["u"].auto_exclude_reason) == ("G01", None)


def test_confirm_fee_splits_unsplit_line_into_transfer_and_fee():
    state = J.ReviewState(stage=J.STAGE_OK1)
    payload = {"fee_amount": "13.20", "transfer_category": "T02"}
    assert apply(state, J.KIND_CONFIRM_FEE, payload, amount="-10000") is True
    assert state.parts == [
        {"amount": "9986.8000", "category_code": "T02"},
        {"amount": "13.2000", "category_code": "F01", "fee_layer": "fee"},
    ]
    with pytest.raises(J.EventRejectedError):  # 同一层只能确认一次
        apply(state, J.KIND_CONFIRM_FEE, payload, amount="-10000")
    apply(
        state, J.KIND_CONFIRM_FEE, {"fee_amount": "15.00", "fee_layer": "payoneer"}, amount="-10000"
    )
    assert state.parts[0]["amount"] == "9971.8000"
    assert state.parts[-1] == {"amount": "15.0000", "category_code": "F01", "fee_layer": "payoneer"}
    apply(state, J.KIND_UNSPLIT)
    assert state.parts is None


@pytest.mark.parametrize("fee", ["0", "-1", "abc", "10", "11"])
def test_confirm_fee_rejections(fee):
    with pytest.raises(J.EventRejectedError):
        apply(J.ReviewState(), J.KIND_CONFIRM_FEE, {"fee_amount": fee})


def test_pair_and_unpair_keep_review_but_need_final_undone_first():
    state = J.ReviewState(stage=J.STAGE_OK1)
    assert apply(state, J.KIND_PAIR, {"pair_id": "M1"}) is False
    assert (state.manual_pair, state.stage) == ("M1", J.STAGE_OK1)
    with pytest.raises(J.EventRejectedError) as caught:
        apply(state, J.KIND_UNPAIR, reason="  ")
    assert caught.value.status_code == 422
    apply(state, J.KIND_UNPAIR, reason="配错了")
    assert state.manual_pair is None
    with pytest.raises(J.EventRejectedError):
        apply(state, J.KIND_UNPAIR, reason="配错了")
    with pytest.raises(J.EventRejectedError):
        apply(J.ReviewState(), J.KIND_PAIR, {"pair_id": ""})
    with pytest.raises(J.EventRejectedError) as caught:
        apply(J.ReviewState(stage=J.STAGE_OK2, manual_pair="M1"), J.KIND_UNPAIR)
    assert caught.value.code == J.ERR_STAGE_NOT_ALLOWED


# ---------------------------------------------------------------- 拆分行挂审批单（Rocky 11-10）


def split_state():
    state = J.ReviewState()
    apply(state, J.KIND_SPLIT, {"amounts": ["4", "6"]})
    return state


def test_part_can_attach_and_detach_its_own_approval():
    state = split_state()
    state.stage = J.STAGE_OK1
    assert apply(state, J.KIND_ATTACH_PART_REF, {"index": 1, "ref": "209901010001"}) is True
    assert state.parts[1]["refs"] == ["209901010001"]
    assert J.all_refs(state) == ["209901010001"]
    with pytest.raises(J.EventRejectedError):
        apply(state, J.KIND_ATTACH_REF, {"ref": "209901010001"})
    with pytest.raises(J.EventRejectedError):
        apply(state, J.KIND_ATTACH_PART_REF, {"index": 0, "ref": "209901010001"})
    apply(state, J.KIND_DETACH_PART_REF, {"index": 1, "ref": "209901010001"})
    assert "refs" not in state.parts[1]
    with pytest.raises(J.EventRejectedError):
        apply(state, J.KIND_DETACH_PART_REF, {"index": 1, "ref": "209901010001"})


def test_unsplit_moves_part_approvals_back_to_the_line():
    state = split_state()
    apply(state, J.KIND_ATTACH_PART_REF, {"index": 0, "ref": "209901010001"})
    apply(state, J.KIND_UNSPLIT)
    assert (state.parts, state.refs) == (None, ["209901010001"])


def test_part_cny_splits_by_amount_with_rest_on_last_row():
    parts = [{"amount": "40"}, {"amount": "60"}]
    assert J.part_cny(Decimal("-667.51"), Decimal("-100"), parts) == [
        Decimal("267.00"),
        Decimal("400.51"),
    ]
    assert J.part_cny(None, Decimal("-100"), parts) == [None, None]


def test_manual_group_of_three_reports_the_total_gap_on_the_biggest_payment():
    result = compute(
        [
            line("o1", -1000, account="A", desc="看不懂", manual_pair="M2"),
            line("o2", -500, account="A", desc="看不懂", manual_pair="M2"),
            line("i", 1400, account="B", desc="看不懂", manual_pair="M2"),
        ]
    )
    items = by_uid(result)
    assert items["o1"].pair_id == items["o2"].pair_id == items["i"].pair_id
    gaps = [alert for alert in result.alerts if alert.type == J.ALERT_PAIR_GAP]
    assert [(alert.line_uid, alert.amount) for alert in gaps] == [("o1", Decimal("100"))]


# ---------------------------------------------------------------- 人工改折人民币（Rocky 11-10）


def test_set_cny_needs_reason_and_resets_review():
    state = J.ReviewState(stage=J.STAGE_OK1)
    with pytest.raises(J.EventRejectedError):
        apply(state, J.KIND_SET_CNY, {"amount_cny": "667.5"})
    with pytest.raises(J.EventRejectedError):
        apply(state, J.KIND_SET_CNY, {"amount_cny": "-1"}, reason="约定汇率")
    assert apply(state, J.KIND_SET_CNY, {"amount_cny": "667.5"}, reason="约定汇率") is True
    assert (state.manual_amount_cny, state.manual_cny_reason) == (Decimal("667.5000"), "约定汇率")
    apply(state, J.KIND_SET_CNY, {"amount_cny": None})
    assert (state.manual_amount_cny, state.manual_cny_reason) == (None, None)
    with pytest.raises(J.EventRejectedError):
        apply(state, J.KIND_SET_CNY, {})


def test_manual_cny_wins_over_the_monthly_rate():
    item = J.compute_journal(
        [line("u", "-100", cur="USD", manual_amount_cny=Decimal("667.50"))],
        J.Classifier([]),
        INTERNAL,
        lambda _day: Decimal("7"),
    ).lines[0]
    assert (item.amount_cny, item.fx_rate, item.fx_source) == (
        Decimal("-667.50"),
        Decimal("6.6750"),
        J.FX_SOURCE_MANUAL,
    )


def test_pingpong_fee_in_memo_asks_to_split_until_confirmed():
    def pp(**extra):
        return line("p", "-1010", cur="USD", provider="pingpong", **extra)

    payment = J.LineInput(**{**pp().__dict__, "memo": "PingPong 手续费 10.00"})
    alerts = [a for a in compute([payment]).alerts if a.type == J.ALERT_PINGPONG_FEE]
    assert [(a.line_uid, a.amount) for a in alerts] == [("p", Decimal("10.00"))]
    done = J.LineInput(
        **{
            **payment.__dict__,
            "parts": [
                {"amount": "1000", "category_code": None},
                {"amount": "10", "category_code": "F01", "fee_layer": J.FEE_LAYER_PINGPONG},
            ],
        }
    )
    assert not [a for a in compute([done]).alerts if a.type == J.ALERT_PINGPONG_FEE]


def test_split_again_is_refused_and_part_approvals_stay():
    state = split_state()
    apply(state, J.KIND_ATTACH_PART_REF, {"index": 0, "ref": "209901010001"})
    with pytest.raises(J.EventRejectedError) as raised:
        apply(state, J.KIND_SPLIT, {"amounts": ["5", "5"]})
    assert raised.value.status_code == 409
    assert state.parts[0]["refs"] == ["209901010001"]


def test_part_cny_rounds_half_up_on_the_absolute_value():
    # 和前端 partCny 同一个用例：-1.01 按 1:1 分两行 → -0.51、-0.50
    parts = [{"amount": "1"}, {"amount": "1"}]
    assert J.part_cny(Decimal("-1.01"), Decimal("-2"), parts) == [Decimal("0.51"), Decimal("0.50")]

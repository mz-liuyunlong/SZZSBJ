# ruff: noqa: E501
"""日记账计算（纯函数，全部合成数据）：不需要数据库。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.modules.finance_cashflow import journal as J
from app.modules.finance_cashflow.service import FxVersion, month_usd_rate

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
    result = compute([line("x", -5, desc="内部调拨 银座")])
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
    assert result["h"].amount_cny is None
    assert by_uid(compute([line("u", 10, cur="USD")]))["u"].amount_cny is None


def fx(account, start, end, rate):
    return FxVersion(account, start, end, Decimal(rate))


def test_month_rate_uses_latest_version_in_month_and_no_fallback():
    versions = [
        fx("S1", datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 10, 15, tzinfo=UTC), "7.0"),
        fx("S1", datetime(2026, 10, 15, tzinfo=UTC), None, "7.1"),
    ]
    assert month_usd_rate(versions, date(2026, 10, 20)) == Decimal("7.1")
    assert month_usd_rate(versions, date(2026, 8, 20)) is None


def test_month_rate_reads_the_same_value_from_rows_stored_per_store():
    versions = [
        fx("S1", datetime(2026, 9, 1, tzinfo=UTC), None, "7.0"),
        fx("S2", datetime(2026, 9, 1, tzinfo=UTC), None, "7.0"),
    ]
    assert month_usd_rate(versions, date(2026, 10, 1)) == Decimal("7.0")


def test_balance_alert_when_previous_balance_is_missing():
    result = compute(
        [
            line("a", 10, balance=Decimal("110"), order=1),
            line("b", 10, balance=Decimal("120"), order=2),
            line("gap", 10, balance=Decimal("500"), order=3),
        ]
    )
    assert [alert.line_uid for alert in result.alerts if alert.type == J.ALERT_BALANCE] == ["gap"]


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
            line("late", -80, refs=["202610100001"], day="2026-10-12"),
            line("early", -50, refs=["202610100001"], day="2026-10-11"),
        ],
        exclusions=[entry(100, ref="202610100001")],
    )
    items = by_uid(result)
    assert items["early"].list_excluded_cny == Decimal("50")
    assert items["late"].list_excluded_cny == Decimal("50")
    assert "已剔除" in items["early"].flags
    assert "部分剔除" in items["late"].flags
    assert not result.alerts


def test_exclusion_not_found_or_not_enough_raises_anomaly():
    missing = compute([line("a", -80)], exclusions=[entry(100, ref="202610100001")])
    assert [alert.type for alert in missing.alerts] == [J.ALERT_EXCLUSION]
    assert missing.alerts[0].amount == Decimal("100")
    short = compute(
        [line("a", -80, refs=["202610100001"])], exclusions=[entry(100, ref="202610100001")]
    )
    assert short.alerts[0].amount == Decimal("20")
    assert "第 1 条" in short.alerts[0].message


def test_exclusion_alert_date_prefers_txn_date_then_registered_on():
    def alert_date(**fields):
        entry_ = J.ExclusionEntry(
            1, "202610100001", None, None, None, Decimal("5"), "其他部门", **fields
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
        [line("u", -100, cur="USD", refs=["202610100001"])],
        exclusions=[entry(100, ref="202610100001")],
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
    ("stage", "kind", "reason", "status"),
    [
        (J.STAGE_TODO, J.KIND_REVIEW2_PASS, None, 409),
        (J.STAGE_REJ1, J.KIND_REVIEW2_REJECT, "x", 409),
        (J.STAGE_OK1, J.KIND_REVIEW1_PASS, None, 409),
        (J.STAGE_OK2, J.KIND_REVIEW1_REJECT, "x", 409),
        (J.STAGE_OK2, J.KIND_REVIEW2_PASS, None, 409),
        (J.STAGE_TODO, J.KIND_REVIEW1_REJECT, " ", 422),
        (J.STAGE_OK1, J.KIND_REVIEW2_REJECT, None, 422),
    ],
)
def test_review_rejections(stage, kind, reason, status):
    with pytest.raises(J.EventRejectedError) as caught:
        apply(J.ReviewState(stage=stage), kind, reason=reason)
    assert caught.value.status_code == status


@pytest.mark.parametrize(
    ("kind", "payload", "reason", "start"),
    [
        (J.KIND_SET_CATEGORY, {"category_code": "G01"}, None, {}),
        (J.KIND_ATTACH_REF, {"ref": "202610100001"}, None, {}),
        (J.KIND_DETACH_REF, {"ref": "202610100001"}, None, {"refs": ["202610100001"]}),
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
        apply(J.ReviewState(refs=["202610100001"]), J.KIND_ATTACH_REF, {"ref": "202610100001"})


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

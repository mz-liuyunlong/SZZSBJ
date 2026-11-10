"""回款对账纯规则：自动配对、合并打款、回款状态、审核阶段。全部合成数据，不连数据库。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.modules.walmart_bills import payout_match as rules

STORE_A = "900000000000000001"
STORE_B = "900000000000000002"
ACC_PP = "SYN_PINGPONG"
ACC_PY = "SYN_PAYONEER"


def period(store: str, key: str, day: str, payable: str, status: str = "normal"):
    return rules.PeriodIn(
        store_id=store,
        report_key=key,
        report_date=date.fromisoformat(day),
        currency_code="USD",
        payable=Decimal(payable),
        status=status,
    )


def line(uid: str, account: str, day: str, amount: str, text: str = "", currency: str = "USD"):
    return rules.LineIn(
        line_uid=uid,
        account_key=account,
        business_date=date.fromisoformat(day),
        amount=Decimal(amount),
        currency_code=currency,
        text=text,
    )


MAPS = [
    rules.AccountIn(STORE_A, ACC_PP, "", date(2026, 10, 1), None),
    rules.AccountIn(STORE_B, ACC_PY, "synthetic-b@example.test", date(2026, 10, 1), None),
]


def test_single_period_matches_within_window_account_and_tolerance():
    found = rules.find_auto_matches(
        [period(STORE_A, "k1", "2026-10-06", "100.00")],
        [line("L1", ACC_PP, "2026-10-08", "100.01")],
        MAPS,
    )
    assert found == [rules.AutoMatch("L1", ((STORE_A, "k1"),))]


def test_out_of_window_wrong_account_or_amount_do_not_match():
    periods = [period(STORE_A, "k1", "2026-10-06", "100.00")]
    for bad in (
        line("L1", ACC_PP, "2026-10-05", "100.00"),  # 账单日之前
        line("L2", ACC_PP, "2026-10-14", "100.00"),  # 超过 7 天
        line("L3", ACC_PY, "2026-10-07", "100.00"),  # 不是这家店的收款账户
        line("L4", ACC_PP, "2026-10-07", "100.02"),  # 差 0.02
        line("L5", ACC_PP, "2026-10-07", "100.00", currency="CNY"),
    ):
        assert rules.find_auto_matches(periods, [bad], MAPS) == []


def test_payee_must_appear_when_filled():
    periods = [period(STORE_B, "k1", "2026-10-06", "50.00")]
    assert rules.find_auto_matches(periods, [line("L1", ACC_PY, "2026-10-07", "50")], MAPS) == []
    hit = line("L2", ACC_PY, "2026-10-07", "50", text="Payment from SYNTHETIC-B@example.test")
    assert rules.find_auto_matches(periods, [hit], MAPS) == [
        rules.AutoMatch("L2", ((STORE_B, "k1"),))
    ]


def test_merged_payment_matches_the_sum_of_periods():
    periods = [
        period(STORE_A, "k1", "2026-10-06", "60.00"),
        period(STORE_A, "k2", "2026-10-08", "40.00"),
        period(STORE_A, "k3", "2026-10-08", "15.00"),
    ]
    found = rules.find_auto_matches(periods, [line("L1", ACC_PP, "2026-10-10", "100.00")], MAPS)
    assert found == [rules.AutoMatch("L1", ((STORE_A, "k1"), (STORE_A, "k2")))]


def test_ambiguous_solutions_and_contested_periods_are_left_for_manual():
    twin = [
        period(STORE_A, "k1", "2026-10-06", "100.00"),
        period(STORE_A, "k2", "2026-10-07", "100.00"),
    ]
    assert rules.find_auto_matches(twin, [line("L1", ACC_PP, "2026-10-08", "100")], MAPS) == []
    one = [period(STORE_A, "k1", "2026-10-06", "100.00")]
    two_lines = [line("L1", ACC_PP, "2026-10-07", "100"), line("L2", ACC_PP, "2026-10-08", "100")]
    assert rules.find_auto_matches(one, two_lines, MAPS) == []


def test_no_pay_and_voided_periods_are_never_auto_matched():
    periods = [
        period(STORE_A, "k1", "2026-10-06", "100.00", status="not_payable"),
        period(STORE_A, "k2", "2026-10-06", "-5.00"),
        period(STORE_A, "k3", "2026-10-06", "100.00", status="voided"),
    ]
    assert rules.find_auto_matches(periods, [line("L1", ACC_PP, "2026-10-07", "100")], MAPS) == []


def test_account_effective_dates_follow_the_bill_date():
    maps = [
        rules.AccountIn(STORE_A, ACC_PP, "", date(2026, 10, 1), date(2026, 10, 15)),
        rules.AccountIn(STORE_A, ACC_PY, "", date(2026, 10, 16), None),
    ]
    assert rules.account_for(maps, STORE_A, date(2026, 10, 15)).account_key == ACC_PP
    assert rules.account_for(maps, STORE_A, date(2026, 10, 16)).account_key == ACC_PY
    assert rules.account_for(maps, STORE_A, date(2026, 9, 30)) is None


def test_split_arrival_puts_the_difference_on_the_latest_period():
    split = rules.split_arrival(
        Decimal("100.50"),
        [
            ((STORE_A, "k2"), date(2026, 10, 8), Decimal("40")),
            ((STORE_A, "k1"), date(2026, 10, 6), Decimal("60")),
        ],
    )
    assert split == {(STORE_A, "k1"): Decimal("60"), (STORE_A, "k2"): Decimal("40.50")}


def test_pay_state():
    p = period(STORE_A, "k1", "2026-10-06", "100.00")
    today = date(2026, 10, 10)
    assert rules.pay_state(p, Decimal("100.01"), today) == (rules.STATE_PAID, Decimal("0.01"))
    assert rules.pay_state(p, Decimal("90"), today) == (rules.STATE_MISMATCH, Decimal("-10.00"))
    assert rules.pay_state(p, None, date(2026, 10, 5))[0] == rules.STATE_NOT_DUE
    assert rules.pay_state(p, None, date(2026, 10, 13))[0] == rules.STATE_WAITING
    assert rules.pay_state(p, None, date(2026, 10, 14))[0] == rules.STATE_UNPAID
    no_pay = period(STORE_A, "k2", "2026-10-06", "0")
    assert rules.pay_state(no_pay, None, today)[0] == rules.STATE_NO_PAY
    voided = period(STORE_A, "k3", "2026-10-06", "100", status="voided")
    assert rules.pay_state(voided, None, today)[0] == rules.STATE_VOIDED


def test_stage_replay_and_allowed_steps():
    assert rules.stage_of([]) == rules.STAGE_TODO
    assert rules.stage_of(["review1_pass"]) == rules.STAGE_OK1
    assert rules.stage_of(["review1_pass", "review2_reject"]) == rules.STAGE_REJ2
    assert rules.stage_of(["review1_pass", "review2_reject", "reset"]) == rules.STAGE_TODO
    assert rules.stage_of(["review1_pass", "review2_pass"]) == rules.STAGE_OK2
    assert rules.review_allowed("review1_pass", rules.STAGE_TODO, matched=True)
    assert rules.review_allowed("review1_pass", rules.STAGE_REJ2, matched=True)
    assert not rules.review_allowed("review1_pass", rules.STAGE_TODO, matched=False)
    assert not rules.review_allowed("review2_pass", rules.STAGE_TODO, matched=True)
    assert rules.review_allowed("review2_reject", rules.STAGE_OK1, matched=True)
    assert not rules.review_allowed("review1_pass", rules.STAGE_OK2, matched=True)


def test_journal_tag_lists_store_and_bill_dates():
    tag = rules.journal_tag("CN9901", [date(2026, 10, 20), date(2026, 10, 6)])
    assert tag == "平台回款 · CN9901 · 2026-10-06、2026-10-20"

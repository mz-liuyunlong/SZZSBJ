"""沃尔玛对账报表打款额（0097）：解析、同步写期表、领星重算保留、页面字段。全部合成数据。"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import Settings, SettingsError, get_test_database_url
from app.modules.walmart_bills import recon_payout as rp
from app.modules.walmart_bills import recon_payout_sync as sync
from app.modules.walmart_bills.models import WalmartBillPeriod, WalmartReconReportPage
from app.modules.walmart_bills.payout_models import WalmartPayoutMatch, WalmartPayoutReviewEvent
from app.modules.walmart_bills.payout_service import PayoutReconService
from app.modules.walmart_bills.periods import refresh_periods

STORE_A = "900000000000000001"
STORE_B = "900000000000000002"
CODES = {STORE_A: "SYN01", STORE_B: "SYN02"}
TODAY = date(2026, 11, 20)
NOW = datetime(2026, 11, 20, 2, 0, tzinfo=UTC)
D1117 = date(2026, 11, 17)
D1103 = date(2026, 11, 3)
D1006 = date(2026, 10, 6)


def row(
    kind: str, amount: str, *, order: str = "", po: str = "", gtin: str = "", **extra: Any
) -> dict:
    base = {
        "Transaction Type": kind,
        "Transaction Description": extra.pop("desc", ""),
        "Amount": amount,
        "Customer Order #": order,
        "Purchase Order #": po,
        "Partner GTIN": gtin,
        "Ship to City": "合成城市",
        "Partner Item Name": "合成商品",
        "Currency": "USD",
    }
    base.update(extra)
    return base


def page(
    total: str,
    *,
    extra_rows: list[dict] | None = None,
    next_offset: int | None = 19904,
    start: str = "10/29/2026",
    end: str = "11/13/2026",
) -> dict:
    rows = [
        row("Sale", "10.00", order="ORD-SYN-1", gtin="00000000000001"),
        row("Service Fee", "-1.00", order="ORD-SYN-1"),
        {
            "Transaction Type": "PaymentSummary",
            "Transaction Description": "Deposited in SYNTHETIC account",
            "Total Payable": total,
            "Period Start Date": start,
            "Period End Date": end,
            "Transaction Posted Timestamp": end,
            "Currency": "USD",
            "Amount": "",
            "Customer Order #": "",
        },
    ] + (extra_rows or [])
    return {"reportData": rows, "nextOffset": next_offset, "totalRecords": len(rows)}


# --------------------------------------------------------------------------- 纯函数


def test_parse_dates_and_summary_shapes() -> None:
    assert rp.parse_available_dates({"availableApReportDates": ["11172026", "11032026"]}) == [
        D1103,
        D1117,
    ]
    assert rp.report_date_param(D1117) == "11172026"
    for bad in ("2026-11-17", "1117202", 20261117, ""):
        with pytest.raises(rp.ReconPayoutError, match="WALMART_RECON_DATE_INVALID"):
            rp.parse_report_date(bad)
    with pytest.raises(rp.ReconPayoutError, match="WALMART_RECON_DATES_INVALID"):
        rp.parse_available_dates({"dates": []})


def test_extract_summary_keeps_account_rows_without_order_or_gtin() -> None:
    release = row("Release Reserve", "600", desc="Reserve released", **{"Transaction Key": "k1"})
    summary = rp.extract_payment_summary(
        D1117, page("1600", extra_rows=[release, row("Adjustment", "-2", order="ORD-SYN-2")])
    )
    assert summary.total_payable == Decimal("1600")
    assert (summary.period_start_date, summary.period_end_date) == (
        date(2026, 10, 29),
        date(2026, 11, 13),
    )
    assert summary.posted_date == date(2026, 11, 13)
    assert summary.currency_code == "USD"
    assert summary.page_rows == 5 and not summary.has_more  # 不满 100 行就没有下一页
    full = page("1.00", extra_rows=[row("Sale", "1", order=f"o{i}") for i in range(97)])
    assert rp.extract_payment_summary(D1117, full).has_more
    assert not rp.extract_payment_summary(D1117, {**full, "nextOffset": None}).has_more
    assert [r["Transaction Type"] for r in summary.account_rows] == ["Release Reserve"]
    # 账户级行只留固定字段，不带商品名 / 城市
    assert set(summary.account_rows[0]) <= set(rp._ACCOUNT_ROW_KEYS)
    assert rp.account_rows_note(summary.account_rows) == "Release Reserve 1 行"
    assert rp.account_rows_note([]) == ""
    assert "只看了第一页" in rp.account_rows_note([], complete=False)


@pytest.mark.parametrize(
    "payload",
    [
        {"reportData": []},
        {"reportData": [row("Sale", "1", order="o")]},
        {"reportData": [page("1")["reportData"][2], page("2")["reportData"][2]]},
        {"reportData": [{**page("1")["reportData"][2], "Total Payable": ""}]},
        {"rows": []},
        "nope",
    ],
)
def test_extract_summary_rejects_missing_or_duplicate_summary(payload: Any) -> None:
    with pytest.raises(rp.ReconPayoutError, match="WALMART_RECON_(SUMMARY_MISSING|REPORT_INVALID)"):
        rp.extract_payment_summary(D1117, payload)


def test_summary_not_on_first_page_gets_its_own_code() -> None:
    full = {"reportData": [row("Sale", "1", order=f"o{i}") for i in range(100)], "nextOffset": 100}
    with pytest.raises(rp.ReconPayoutError, match="WALMART_RECON_SUMMARY_NOT_ON_FIRST_PAGE"):
        rp.extract_payment_summary(D1117, full)


# --------------------------------------------------------------------------- 同步（假通道）


@dataclass
class Result:
    status_code: int
    data: Any
    request_id: str | None = "req-syn"


class FakeWalmart:
    """只记录调用；按店给可用日期和第一页。pages 里的值是 dict → 200，int → 该 HTTP 状态。"""

    def __init__(self, dates: dict[str, list[str]], pages: dict[tuple[str, str], Any]) -> None:
        self.dates = dates
        self.pages = pages
        self.calls: list[tuple[str, str, str, dict]] = []

    def __call__(
        self, store_code: str, method: str, path: str, *, query: dict, response_kind: str
    ) -> Result:
        self.calls.append((store_code, method, path, dict(query)))
        assert method == "GET" and response_kind == "json"
        if path == rp.RECON_DATES_PATH:
            dates = self.dates.get(store_code)
            if dates is None:
                return Result(400, {"error": "no store"})
            return Result(200, {"availableApReportDates": dates})
        if path == rp.RECON_FILE_PATH:
            assert query["offset"] == 0 and query["noOfRecords"] == 100
            found = self.pages.get((store_code, query["reportDate"]))
            if isinstance(found, int):
                return Result(found, {"error": "synthetic"})
            return Result(200, found) if found is not None else Result(400, {"error": "no report"})
        raise AssertionError(path)

    def fetched(self) -> list[tuple[str, str]]:
        return sorted((c[0], c[3]["reportDate"]) for c in self.calls if c[2] == rp.RECON_FILE_PATH)


def test_sync_refuses_paths_outside_the_two_allowed() -> None:
    def call(*args: Any, **kwargs: Any) -> Result:
        raise AssertionError("must not be called")

    with pytest.raises(rp.ReconPayoutError, match="WALMART_RECON_PATH_NOT_ALLOWED"):
        sync._get(call, "SYN01", "/v3/report/payment/statement", {})


def test_enabled_flag_default_off_and_task_returns_without_calling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert not sync.enabled({})
    assert not sync.enabled({sync.ENABLED_ENV: "true"})
    assert sync.enabled({sync.ENABLED_ENV: "1"})
    from app.modules.walmart_bills import tasks

    monkeypatch.delenv(sync.ENABLED_ENV, raising=False)

    def boom() -> Any:
        raise AssertionError("must not touch Walmart or the database when disabled")

    monkeypatch.setattr(tasks, "production_call", boom)
    monkeypatch.setattr(tasks, "get_session_factory", boom)
    tasks.recon_payout_sync_task.run()


def test_error_code_keeps_filtered_gateway_codes() -> None:
    class GatewayRejected(RuntimeError):
        pass

    assert sync._error_code(
        GatewayRejected("WALMART_GATEWAY_REJECTED:WALMART_RESPONSE_TOO_LARGE")
    ) == ("WALMART_GATEWAY_REJECTED:WALMART_RESPONSE_TOO_LARGE")
    assert (
        sync._error_code(rp.ReconPayoutError("WALMART_RECON_HTTP_400")) == "WALMART_RECON_HTTP_400"
    )
    assert sync._error_code(ValueError("secret text")) == "ValueError"


# --------------------------------------------------------------------------- PostgreSQL


@pytest.fixture
def session() -> Iterator[Session]:
    try:
        url = get_test_database_url(Settings())  # type: ignore[call-arg]
    except (SettingsError, ValidationError):
        pytest.skip("isolated PostgreSQL test database is not configured")
    engine = create_engine(url, poolclass=NullPool, hide_parameters=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
            yield db
        transaction.rollback()
    engine.dispose()


def add_period(
    session: Session,
    store: str,
    key: str,
    day: date,
    payable: str,
    *,
    line_count: int = 3,
    currency: str = "USD",
    start: date = date(2026, 10, 29),
    end: date = date(2026, 11, 13),
) -> WalmartBillPeriod:
    period = WalmartBillPeriod(
        source_account_ref="primary",
        store_id=store,
        report_key=key,
        store_name="CN9901-合成店",
        report_date=day,
        period_start_date=start,
        period_end_date=end,
        currency_code=currency,
        line_count=line_count,
        excluded_line_count=0,
        amount_sum=Decimal(payable),
        payable_amount=Decimal(payable),
        status="normal" if Decimal(payable) > 0 and line_count else "not_payable",
        refreshed_at=NOW,
    )
    session.add(period)
    session.flush()
    return period


def run(session: Session, fake: FakeWalmart, **kwargs: Any) -> sync.ReconPayoutSyncResult:
    # 测试事务里不能真 commit（外层会回滚），用保存点语义
    return sync.sync_recon_payouts(
        session, call=fake, store_codes=CODES, now=NOW, commit_each_store=False, **kwargs
    )


def test_sync_writes_walmart_payable_raw_page_and_keeps_lingxing_as_reference(
    session: Session,
) -> None:
    a = add_period(session, STORE_A, "rk-a", D1117, "1000")
    add_period(session, STORE_A, "rk-a0", D1103, "100", start=date(2026, 10, 15), end=D1103)
    old = add_period(session, STORE_A, "rk-old", D1006, "50", start=date(2026, 9, 17), end=D1006)
    b = add_period(session, STORE_B, "rk-b", D1117, "2000")
    fake = FakeWalmart(
        dates={"SYN01": ["10062026", "11032026", "11172026"], "SYN02": ["11172026", "12012026"]},
        pages={
            ("SYN01", "11172026"): page("1600", extra_rows=[row("Release Reserve", "600")]),
            ("SYN01", "11032026"): page("100", start="10/15/2026", end="11/03/2026"),
            ("SYN01", "10062026"): page(
                "999", start="09/17/2026", end="10/06/2026"
            ),  # 10 月：不该拉
            ("SYN02", "11172026"): page("2000"),
            # 12-01 沃尔玛有、领星还没有这期：不该去拉
        },
    )
    result = run(session, fake)
    assert result.failed == [] and result.written == 3 and result.reset == []
    assert [c[2] for c in fake.calls].count(rp.RECON_DATES_PATH) == 2
    assert fake.fetched() == [("SYN01", "11032026"), ("SYN01", "11172026"), ("SYN02", "11172026")]

    session.refresh(a)
    assert a.payable_source == "walmart"
    assert a.payable_amount == Decimal("1600.0000")
    assert a.walmart_total_payable == Decimal("1600.0000")
    assert a.walmart_diff == Decimal("600.0000")
    assert a.amount_sum == Decimal("1000.0000")  # 领星值不动
    assert a.walmart_account_rows[0]["Transaction Type"] == "Release Reserve"
    assert a.walmart_account_rows_complete and a.walmart_synced_at == NOW and a.status == "normal"
    session.refresh(b)
    assert b.walmart_diff == Decimal("0.0000") and b.payable_amount == Decimal("2000.0000")
    session.refresh(old)
    assert old.payable_source == "lingxing" and old.walmart_total_payable is None

    raw = session.get(WalmartReconReportPage, ("primary", STORE_A, D1117, 0))
    assert raw is not None and raw.store_code == "SYN01" and raw.request_id == "req-syn"
    assert raw.payload["reportData"][2]["Transaction Type"] == "PaymentSummary"
    assert len(raw.sha256) == 64 and raw.payload_bytes > 0

    # 第二次：已有沃尔玛数据的期不再拉
    fake.calls.clear()
    again = run(session, fake)
    assert again.written == 0 and fake.fetched() == []

    # 页面字段
    items = {r.report_key: r for r in PayoutReconService(session).list_periods(today=TODAY).items}
    assert items["rk-a"].payable_source == "walmart"
    assert items["rk-a"].lingxing_payable == Decimal("1000.0000")
    assert items["rk-a"].walmart_diff == Decimal("600.0000")
    assert items["rk-a"].walmart_note == "Release Reserve 1 行"
    assert items["rk-b"].walmart_note is None


def test_each_period_has_its_own_savepoint_and_store_keeps_going(session: Session) -> None:
    a1 = add_period(session, STORE_A, "rk-a1", D1103, "10", start=date(2026, 10, 15), end=D1103)
    a2 = add_period(session, STORE_A, "rk-a2", D1117, "20")
    a3 = add_period(session, STORE_A, "rk-a3", date(2026, 11, 20), "30", end=date(2026, 11, 20))
    fake = FakeWalmart(
        dates={"SYN01": ["11032026", "11172026", "11202026"], "SYN02": []},
        pages={
            ("SYN01", "11032026"): page("10", start="10/15/2026", end="11/03/2026"),
            ("SYN01", "11172026"): {"reportData": [row("Sale", "1", order="o")]},  # 没有汇总行
            ("SYN01", "11202026"): page("31", next_offset=None, end="11/20/2026"),
        },
    )
    result = run(session, fake)
    store = result.stores[0]
    assert store.error is None
    assert [(p.report_date, p.status) for p in store.periods] == [
        (D1103, "written"),
        (D1117, "error"),
        (date(2026, 11, 20), "written"),
    ]
    assert store.failed_periods == [(D1117, "WALMART_RECON_SUMMARY_MISSING")]
    for period in (a1, a2, a3):
        session.refresh(period)
    assert a1.payable_source == "walmart" and a3.payable_source == "walmart"
    assert a2.payable_source == "lingxing" and a2.walmart_total_payable is None
    assert session.get(WalmartReconReportPage, ("primary", STORE_A, D1117, 0)) is None


def test_rate_limit_stops_the_store_and_rolls_it_back(session: Session) -> None:
    a1 = add_period(session, STORE_A, "rk-a1", D1103, "10", start=date(2026, 10, 15), end=D1103)
    a2 = add_period(session, STORE_A, "rk-a2", D1117, "20")
    b = add_period(session, STORE_B, "rk-b", D1117, "30")
    fake = FakeWalmart(
        dates={"SYN01": ["11032026", "11172026"], "SYN02": ["11172026"]},
        pages={
            ("SYN01", "11032026"): page("10", start="10/15/2026", end="11/03/2026"),
            ("SYN01", "11172026"): 429,
            ("SYN02", "11172026"): page("30"),
        },
    )
    result = run(session, fake)
    assert result.failed == ["SYN01"] and result.stores[0].error == "WALMART_RECON_RATE_LIMITED"
    assert fake.fetched() == [("SYN01", "11032026"), ("SYN01", "11172026"), ("SYN02", "11172026")]
    for period in (a1, a2, b):
        session.refresh(period)
    assert a1.payable_source == "lingxing" and a2.payable_source == "lingxing"
    assert b.payable_source == "walmart"
    assert session.get(WalmartReconReportPage, ("primary", STORE_A, D1103, 0)) is None


def test_dates_endpoint_failure_fails_only_that_store(session: Session) -> None:
    a = add_period(session, STORE_A, "rk-a", D1117, "1")
    b = add_period(session, STORE_B, "rk-b", D1117, "2")
    fake = FakeWalmart(dates={"SYN02": ["11172026"]}, pages={("SYN02", "11172026"): page("2")})
    result = run(session, fake)
    assert result.failed == ["SYN01"] and result.stores[0].error == "WALMART_RECON_HTTP_400"
    session.refresh(a)
    session.refresh(b)
    assert a.payable_source == "lingxing" and b.payable_source == "walmart"


def test_period_or_currency_mismatch_and_duplicate_dates_are_skipped(session: Session) -> None:
    add_period(
        session, STORE_A, "rk-cur", D1103, "10", currency="CNY", start=date(2026, 10, 15), end=D1103
    )
    add_period(session, STORE_A, "rk-dup1", D1117, "20")
    add_period(session, STORE_A, "rk-dup2", D1117, "21")
    add_period(
        session,
        STORE_A,
        "rk-span",
        date(2026, 11, 20),
        "30",
        start=date(2026, 9, 1),
        end=date(2026, 9, 30),
    )
    fake = FakeWalmart(
        dates={"SYN01": ["11032026", "11172026", "11202026"], "SYN02": []},
        pages={
            ("SYN01", "11032026"): page("10", start="10/15/2026", end="11/03/2026"),
            ("SYN01", "11172026"): page("20"),
            ("SYN01", "11202026"): page("30", end="11/20/2026"),
        },
    )
    result = run(session, fake)
    assert sorted(result.stores[0].failed_periods) == [
        (D1103, "WALMART_RECON_CURRENCY_MISMATCH"),
        (D1117, "WALMART_RECON_DUPLICATE_PERIOD"),
        (date(2026, 11, 20), "WALMART_RECON_PERIOD_MISMATCH"),
    ]
    assert fake.fetched() == [("SYN01", "11032026"), ("SYN01", "11202026")]  # 重复日期不去拉
    sources = {
        p.report_key: p.payable_source
        for p in session.scalars(
            select(WalmartBillPeriod).where(WalmartBillPeriod.store_id == STORE_A)
        )
    }
    assert set(sources.values()) == {"lingxing"}


def test_not_payable_and_voided_on_both_paths(session: Session) -> None:
    neg = add_period(session, STORE_A, "rk-neg", D1103, "5", start=date(2026, 10, 15), end=D1103)
    void = add_period(session, STORE_A, "rk-void", D1117, "7", line_count=0)
    fake = FakeWalmart(
        dates={"SYN01": ["11032026", "11172026"], "SYN02": []},
        pages={
            ("SYN01", "11032026"): page("-3", start="10/15/2026", end="11/03/2026"),
            ("SYN01", "11172026"): page("7"),
        },
    )
    assert run(session, fake).written == 2
    session.refresh(neg)
    session.refresh(void)
    assert neg.status == "not_payable" and neg.payable_amount == Decimal("-3.0000")
    assert void.status == "voided" and void.payable_amount == Decimal("7.0000")
    # 领星重算只动有明细的期；这两期没有明细行，重算不碰它们，沃尔玛写的状态保留
    refresh_periods(
        session,
        source_account_ref="primary",
        keys={(STORE_A, "rk-neg"), (STORE_A, "rk-void")},
        store_names={},
        run_id=None,
    )
    session.expire_all()
    neg = session.get(WalmartBillPeriod, ("primary", STORE_A, "rk-neg"))
    void = session.get(WalmartBillPeriod, ("primary", STORE_A, "rk-void"))
    assert neg is not None and void is not None
    assert neg.status == "not_payable" and neg.payable_amount == Decimal("-3.0000")
    assert void.status == "voided" and void.payable_source == "walmart"


def test_matched_or_reviewed_period_gets_reset_when_payable_changes(session: Session) -> None:
    from app.modules.finance_cashflow.models import FinanceCashAccount
    from tests.modules.walmart_bills.test_payout_postgresql import ACC, add_line

    session.add(
        FinanceCashAccount(
            account_key=ACC,
            display_name="合成 · 账户",
            entity="合成主体",
            currency_code="USD",
            kind="platform",
            provider="pingpong",
        )
    )
    session.flush()
    add_line(session, "syn-line-1", "2026-11-05", "100")
    matched = add_period(
        session, STORE_A, "rk-m", D1103, "100", start=date(2026, 10, 15), end=D1103
    )
    reviewed = add_period(session, STORE_A, "rk-r", D1117, "200")
    same = add_period(session, STORE_B, "rk-s", D1117, "300")
    session.add(
        WalmartPayoutMatch(
            match_id=uuid4(),
            seq=0,
            line_uid="syn-line-1",
            source_account_ref="primary",
            store_id=STORE_A,
            report_key="rk-m",
            payable_amount=Decimal("100"),
            method="auto",
            created_by="u",
        )
    )
    for store, key in ((STORE_A, "rk-r"), (STORE_B, "rk-s")):
        session.add(
            WalmartPayoutReviewEvent(
                source_account_ref="primary",
                store_id=store,
                report_key=key,
                kind="review1_pass",
                actor="u",
            )
        )
    session.flush()
    fake = FakeWalmart(
        dates={"SYN01": ["11032026", "11172026"], "SYN02": ["11172026"]},
        pages={
            ("SYN01", "11032026"): page("160", start="10/15/2026", end="11/03/2026"),
            ("SYN01", "11172026"): page("190"),
            ("SYN02", "11172026"): page("300.004"),  # 差 < 0.01：不重置
        },
    )
    result = run(session, fake)
    assert sorted(result.reset) == [("SYN01", D1103), ("SYN01", D1117)]
    for period in (matched, reviewed, same):
        session.refresh(period)
    assert matched.payable_amount == Decimal("160.0000")
    assert reviewed.payable_amount == Decimal("190.0000")
    resets = session.scalars(
        select(WalmartPayoutReviewEvent).where(WalmartPayoutReviewEvent.kind == "reset")
    ).all()
    assert sorted(e.report_key for e in resets) == ["rk-m", "rk-r"]
    assert all(e.actor == sync.SYNC_ACTOR for e in resets)
    assert {Decimal(e.payload["payable_before"]) for e in resets} == {
        Decimal("100"),
        Decimal("200"),
    }
    assert {Decimal(e.payload["payable_after"]) for e in resets} == {Decimal("160"), Decimal("190")}
    items = {r.report_key: r for r in PayoutReconService(session).list_periods(today=TODAY).items}
    assert items["rk-r"].stage == "todo"  # 退回待初审
    assert items["rk-s"].stage == "ok1"  # 没变，不动
    # 已配对的期：到账 100 对新应付 160 → 金额不符，财务一眼能看到
    assert items["rk-m"].pay_state == "mismatch" and items["rk-m"].diff == Decimal("-60.0000")


def test_lingxing_refresh_keeps_walmart_payable_and_recomputes_diff(session: Session) -> None:
    from app.modules.walmart_bills.models import WalmartBillLine

    for i, amount in enumerate(("10", "5.5"), start=1):
        session.add(
            WalmartBillLine(
                source_account_ref="primary",
                store_id=STORE_A,
                line_key=f"syn-line-{i}",
                lx_line_id=str(i),
                report_key="rk-a",
                report_date=D1117,
                posted_at=datetime(2026, 11, 10, 8, 0),
                posted_date=date(2026, 11, 10),
                transaction_type="Sale",
                amount_type="Product Price",
                amount=Decimal(amount),
                currency_code="USD",
                delete_flag=0,
                row_hash=f"h{i}",
                first_seen_at=NOW,
                last_seen_at=NOW,
            )
        )
    session.flush()
    refresh_periods(
        session, source_account_ref="primary", keys={(STORE_A, "rk-a")}, store_names={}, run_id=None
    )
    period = session.get(WalmartBillPeriod, ("primary", STORE_A, "rk-a"))
    assert period is not None and period.payable_amount == Decimal("15.5000")
    sync.apply_summary(
        session,
        period,
        rp.extract_payment_summary(D1117, page("20", start="11/10/2026", end="11/10/2026")),
        now=NOW,
    )
    session.flush()
    session.expire_all()
    # 领星再同步重算这一期：应付仍是沃尔玛的 20，差额按新的领星合计重算
    refresh_periods(
        session, source_account_ref="primary", keys={(STORE_A, "rk-a")}, store_names={}, run_id=None
    )
    session.expire_all()
    period = session.get(WalmartBillPeriod, ("primary", STORE_A, "rk-a"))
    assert period is not None
    assert period.payable_amount == Decimal("20.0000")
    assert period.walmart_diff == Decimal("4.5000")
    assert period.payable_source == "walmart" and period.amount_sum == Decimal("15.5000")
    assert period.walmart_synced_at == NOW


def test_payable_source_and_walmart_value_must_agree(session: Session) -> None:
    period = add_period(session, STORE_A, "rk-x", D1117, "1")
    period.payable_source = "walmart"  # 没有沃尔玛金额却标 walmart
    with pytest.raises(IntegrityError):
        session.flush()

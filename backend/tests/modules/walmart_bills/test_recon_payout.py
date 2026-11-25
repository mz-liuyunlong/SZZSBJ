"""沃尔玛对账报表打款额（0097）：解析、同步写期表、领星重算保留、页面字段。全部合成数据。"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import Settings, SettingsError, get_test_database_url
from app.modules.walmart_bills import recon_payout as rp
from app.modules.walmart_bills import recon_payout_sync as sync
from app.modules.walmart_bills.models import WalmartBillPeriod
from app.modules.walmart_bills.payout_service import PayoutReconService
from app.modules.walmart_bills.periods import refresh_periods

STORE_A = "900000000000000001"
STORE_B = "900000000000000002"
CODES = {STORE_A: "SYN01", STORE_B: "SYN02"}
TODAY = date(2026, 11, 20)
NOW = datetime(2026, 11, 20, 2, 0, tzinfo=UTC)
D1117 = date(2026, 11, 17)
D1103 = date(2026, 11, 3)


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
    total: str, *, extra_rows: list[dict] | None = None, next_offset: int | None = 19904
) -> dict:
    rows = [
        row("Sale", "10.00", order="ORD-SYN-1", gtin="00000000000001"),
        row("Service Fee", "-1.00", order="ORD-SYN-1"),
        {
            "Transaction Type": "PaymentSummary",
            "Transaction Description": "Deposited in SYNTHETIC account",
            "Total Payable": total,
            "Period Start Date": "10/31/2026",
            "Period End Date": "11/14/2026",
            "Transaction Posted Timestamp": "11/14/2026",
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
    release = row("Release Reserve", "600.00", desc="Reserve released", **{"Transaction Key": "k1"})
    summary = rp.extract_payment_summary(
        D1117, page("7756.90", extra_rows=[release, row("Adjustment", "-2.00", order="ORD-SYN-2")])
    )
    assert summary.total_payable == Decimal("7756.90")
    assert (summary.period_start_date, summary.period_end_date) == (
        date(2026, 10, 31),
        date(2026, 11, 14),
    )
    assert summary.posted_date == date(2026, 11, 14)
    assert summary.currency_code == "USD"
    assert summary.page_rows == 5 and not summary.has_more  # 不满 100 行就没有下一页
    full = page("1.00", extra_rows=[row("Sale", "1", order=f"o{i}") for i in range(97)])
    assert rp.extract_payment_summary(D1117, full).has_more
    assert not rp.extract_payment_summary(D1117, {**full, "nextOffset": None}).has_more
    assert [r["Transaction Type"] for r in summary.account_rows] == ["Release Reserve"]
    # 账户级行只留固定字段，不带商品名 / 城市
    assert set(summary.account_rows[0]) <= set(rp._ACCOUNT_ROW_KEYS)
    assert "Ship to City" not in summary.summary_row
    assert rp.account_rows_note(summary.account_rows) == "Release Reserve 1 行"
    assert rp.account_rows_note([]) == ""


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


# --------------------------------------------------------------------------- 同步（假通道）


@dataclass
class Result:
    status_code: int
    data: Any


class FakeWalmart:
    """只记录调用；按店给可用日期和第一页。"""

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
            return Result(200, {"availableApReportDates": self.dates.get(store_code, [])})
        if path == rp.RECON_FILE_PATH:
            assert query["offset"] == 0 and query["noOfRecords"] == 100
            found = self.pages.get((store_code, query["reportDate"]))
            return Result(200, found) if found is not None else Result(400, {"error": "no report"})
        raise AssertionError(path)


def test_sync_refuses_paths_outside_the_two_allowed() -> None:
    def call(*args: Any, **kwargs: Any) -> Result:
        raise AssertionError("must not be called")

    with pytest.raises(rp.ReconPayoutError, match="WALMART_RECON_PATH_NOT_ALLOWED"):
        sync._get(call, "SYN01", "/v3/report/payment/statement", {})


def test_enabled_flag_default_off() -> None:
    assert not sync.enabled({})
    assert not sync.enabled({sync.ENABLED_ENV: "true"})
    assert sync.enabled({sync.ENABLED_ENV: "1"})
    assert os.environ.get(sync.ENABLED_ENV) != "1"


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
    session: Session, store: str, key: str, day: date, payable: str
) -> WalmartBillPeriod:
    period = WalmartBillPeriod(
        source_account_ref="primary",
        store_id=store,
        report_key=key,
        store_name="CN9901-合成店",
        report_date=day,
        period_start_date=date(2026, 10, 29),
        period_end_date=date(2026, 11, 13),
        currency_code="USD",
        line_count=3,
        excluded_line_count=0,
        amount_sum=Decimal(payable),
        payable_amount=Decimal(payable),
        status="normal",
        refreshed_at=NOW,
    )
    session.add(period)
    session.flush()
    return period


def test_sync_writes_walmart_payable_and_keeps_lingxing_as_reference(session: Session) -> None:
    a = add_period(session, STORE_A, "rk-a", D1117, "7156.90")
    add_period(session, STORE_A, "rk-a0", D1103, "100.00")
    b = add_period(session, STORE_B, "rk-b", D1117, "10114.89")
    fake = FakeWalmart(
        dates={"SYN01": ["10062026", "11032026", "11172026"], "SYN02": ["11172026", "12012026"]},
        pages={
            ("SYN01", "11172026"): page("7756.90", extra_rows=[row("Release Reserve", "600.00")]),
            ("SYN01", "11032026"): page("100.00"),
            ("SYN02", "11172026"): page("10114.89"),
            # 12-01 沃尔玛有、领星还没有这期：不该去拉
        },
    )
    result = sync.sync_recon_payouts(session, call=fake, store_codes=CODES, today=TODAY, now=NOW)
    assert result.failed == [] and result.written == 3
    assert [c[2] for c in fake.calls].count(rp.RECON_DATES_PATH) == 2
    fetched = sorted((c[0], c[3]["reportDate"]) for c in fake.calls if c[2] == rp.RECON_FILE_PATH)
    assert fetched == [("SYN01", "11032026"), ("SYN01", "11172026"), ("SYN02", "11172026")]

    session.refresh(a)
    assert a.payable_source == "walmart"
    assert a.payable_amount == Decimal("7756.9000")
    assert a.walmart_total_payable == Decimal("7756.9000")
    assert a.walmart_diff == Decimal("600.0000")
    assert a.amount_sum == Decimal("7156.9000")  # 领星值不动
    assert a.walmart_account_rows[0]["Transaction Type"] == "Release Reserve"
    assert a.walmart_synced_at == NOW and a.status == "normal"
    session.refresh(b)
    assert b.walmart_diff == Decimal("0.0000") and b.payable_amount == Decimal("10114.8900")

    # 第二次：已有沃尔玛数据的期不再拉
    fake.calls.clear()
    again = sync.sync_recon_payouts(session, call=fake, store_codes=CODES, today=TODAY, now=NOW)
    assert again.written == 0 and [c for c in fake.calls if c[2] == rp.RECON_FILE_PATH] == []

    # 页面字段
    items = {r.report_key: r for r in PayoutReconService(session).list_periods(today=TODAY).items}
    assert items["rk-a"].payable_source == "walmart"
    assert items["rk-a"].lingxing_payable == Decimal("7156.9000")
    assert items["rk-a"].walmart_diff == Decimal("600.0000")
    assert items["rk-a"].walmart_note == "Release Reserve 1 行"
    assert items["rk-b"].walmart_note is None


def test_store_failure_rolls_back_only_that_store(session: Session) -> None:
    a = add_period(session, STORE_A, "rk-a", D1117, "1.00")
    b = add_period(session, STORE_B, "rk-b", D1117, "2.00")
    fake = FakeWalmart(
        dates={"SYN01": ["11172026"], "SYN02": ["11172026"]},
        pages={("SYN01", "11172026"): page("1.00")},  # SYN02 第一页 400
    )
    result = sync.sync_recon_payouts(session, call=fake, store_codes=CODES, today=TODAY, now=NOW)
    assert result.failed == ["SYN02"]
    assert result.stores[1].error == "WALMART_RECON_HTTP_400"
    session.refresh(a)
    session.refresh(b)
    assert a.payable_source == "walmart" and b.payable_source == "lingxing"
    assert b.walmart_total_payable is None


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
    sync.apply_summary(session, period, rp.extract_payment_summary(D1117, page("20.00")), now=NOW)
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
    period = add_period(session, STORE_A, "rk-x", D1117, "1.00")
    period.payable_source = "walmart"  # 没有沃尔玛金额却标 walmart
    with pytest.raises(IntegrityError):
        session.flush()

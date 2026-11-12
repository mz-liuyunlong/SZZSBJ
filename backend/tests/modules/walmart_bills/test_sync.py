"""沃尔玛账单同步：不连领星，全部合成数据；没配隔离 PostgreSQL 测试库就跳过。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import JsonValue, ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.api import ApiError
from app.core.config import Settings, SettingsError, get_test_database_url
from app.integrations.lingxing.client import LingxingRawEnvelope
from app.modules.data_pages.models import LingxingStoreDimension
from app.modules.integration_sync import execution as execution_module
from app.modules.integration_sync.catalog import IntegrationCatalogService
from app.modules.integration_sync.execution import SyncRunExecutionService
from app.modules.integration_sync.handlers.lingxing_walmart_bill_sync import (
    LingxingWalmartBillSyncHandler,
    WalmartBillSyncError,
)
from app.modules.integration_sync.models import (
    ApiRawRequestRef,
    IntegrationInterface,
    IntegrationSyncConfig,
    IntegrationSyncRun,
    IntegrationSyncRunWorkItem,
)
from app.modules.integration_sync.product_info_runner import ProductInfoOneTimeRunError
from app.modules.integration_sync.scheduler import IntegrationSchedulerService
from app.modules.integration_sync.schemas import TriggerRequest
from app.modules.integration_sync.service import IntegrationSyncService
from app.modules.integration_sync.tasks import TaskDispatchError
from app.modules.integration_sync.walmart_bill_catalog import WALMART_BILL_SYNC_SPEC
from app.modules.walmart_bills import sync as bill_sync
from app.modules.walmart_bills.models import WalmartBillLine, WalmartBillPeriod
from app.modules.walmart_bills.reader import list_periods

# 上海时间 2026-11-09 01:00 → 最近 35 天 = 2026-10-06 ~ 2026-11-09。
NOW = datetime(2026, 11, 8, 17, 0, tzinfo=UTC)
STORE_A = "900000000000000001"
STORE_B = "900000000000000002"
SHANGHAI = ZoneInfo("Asia/Shanghai")


def bill_line(
    line_id: int,
    store_id: str,
    report_key: str,
    posted: str,
    amount: str,
    *,
    amount_type: str = "Product Price",
    delete_flag: int = 0,
    report_date: str = "2026-10-20",
) -> dict[str, Any]:
    return {
        "id": line_id,
        "storeId": store_id,
        "reportKey": report_key,
        "reportId": 1,
        "reportDate": report_date,
        "periodStartDate": None,
        "periodEndDate": None,
        "transactionPostedTimestamp": f"{posted} 08:00:00",
        "transactionType": "Sale",
        "amountType": amount_type,
        "amount": amount,
        "currency": "USD",
        "totalPayable": None,
        "deleteFlag": delete_flag,
        "partnerItemName": "合成商品",
        "shipToCity": "合成城市",
    }


class FakeLingxing:
    """按「交易日期」筛选、offset/length 翻页，跟领星 statement/list 一样。"""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, date, date, int]] = []
        self.total_bump: dict[tuple[str, int], int] = {}
        self.extra_rows: dict[str, list[dict[str, Any]]] = {}

    def fetch_walmart_bill_page(self, **kw: Any) -> LingxingRawEnvelope:
        store, start, end = kw["store_id"], kw["start_date"], kw["end_date"]
        offset, length = kw["offset"], kw["length"]
        self.calls.append((store, start, end, offset))
        matching = [
            row
            for row in self.rows
            if row["storeId"] == store
            and start <= date.fromisoformat(row["transactionPostedTimestamp"][:10]) <= end
        ] + self.extra_rows.get(store, [])
        total = len(matching) + self.total_bump.get((store, offset), 0)
        page = matching[offset : offset + length]
        body: JsonValue = {
            "code": 0,
            "message": "success",
            "data": {"list": page, "totalCount": total, "totalSum": {}},
        }
        return LingxingRawEnvelope(
            api_path=WALMART_BILL_SYNC_SPEC.endpoint_path,
            request_body_json={"offset": offset, "length": length},
            response_json=body,
            response_code=200,
            is_success=True,
            pulled_at=NOW,
            page_no=kw["page_no"],
            page_size=length,
            store_id=store,
            object_type="lingxing_walmart_bill_statement",
            trace_id=kw["run_id"],
            run_id=kw["run_id"],
            batch_id=kw["work_item_id"],
            attempt_no=1,
        )

    def windows(self, store: str) -> list[tuple[date, date]]:
        return sorted({(start, end) for name, start, end, _ in self.calls if name == store})


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


def add_stores(session: Session) -> None:
    for store_id, name in ((STORE_A, "CN9901-合成甲"), (STORE_B, "CN9902-合成乙")):
        session.add(
            LingxingStoreDimension(
                source_account_ref="primary",
                platform_code_raw="10008",
                platform_code="walmart",
                store_id=store_id,
                store_name=name,
                sid=store_id,
                synced_at=NOW,
            )
        )
    session.flush()


def governed(
    session: Session, *, enabled: bool = True, page_size: int = 2, max_pages: int = 50
) -> IntegrationInterface:
    IntegrationCatalogService(session).bootstrap_walmart_bill_governance("primary")
    interface = session.scalars(
        select(IntegrationInterface).where(
            IntegrationInterface.interface_key == WALMART_BILL_SYNC_SPEC.interface_key
        )
    ).one()
    config = session.scalars(
        select(IntegrationSyncConfig).where(IntegrationSyncConfig.interface_id == interface.id)
    ).one()
    interface.outbound_enabled = enabled
    config.is_enabled = enabled
    config.page_size = page_size
    config.max_pages = max_pages
    session.flush()
    return interface


def queued_run(
    session: Session,
    interface: IntegrationInterface,
    *,
    trigger: str = "manual",
    window: tuple[datetime, datetime] | None = None,
) -> IntegrationSyncRun:
    config = session.scalars(
        select(IntegrationSyncConfig).where(IntegrationSyncConfig.interface_id == interface.id)
    ).one()
    run = IntegrationSyncRun(
        config_id=config.id,
        interface_id=interface.id,
        provider="lingxing",
        interface_key=interface.interface_key,
        source_account_ref="primary",
        trigger_type=trigger,
        status="queued",
        idempotency_key=f"bill-{uuid4()}",
        queued_at=NOW,
        window_start=window[0] if window else None,
        window_end=window[1] if window else None,
        work_items_total=0,
        work_items_succeeded=0,
        work_items_failed=0,
        records_seen=0,
        records_written=0,
    )
    session.add(run)
    session.flush()
    return run


def run_sync(
    session: Session,
    interface: IntegrationInterface,
    client: FakeLingxing,
    **kwargs: Any,
) -> IntegrationSyncRun:
    run = queued_run(session, interface, **kwargs)
    run.status = "running"
    LingxingWalmartBillSyncHandler(session, client=client, now=lambda: NOW).execute(run, interface)
    return run


def period(session: Session, store_id: str, report_key: str) -> WalmartBillPeriod:
    found = session.get(WalmartBillPeriod, ("primary", store_id, report_key))
    assert found is not None
    return found


def base_rows() -> list[dict[str, Any]]:
    return [
        bill_line(1, STORE_A, "rk-a1", "2026-10-15", "10"),
        bill_line(2, STORE_A, "rk-a1", "2026-10-16", "5.5"),
        bill_line(3, STORE_A, "rk-a1", "2026-10-17", "-1.5", amount_type="Commission"),
        bill_line(4, STORE_A, "rk-a2", "2026-10-18", "7", delete_flag=1),
        bill_line(5, STORE_A, "rk-a3", "2026-11-02", "-3", report_date="2026-11-03"),
        bill_line(6, STORE_B, "rk-b1", "2026-10-20", "20"),
    ]


def test_bootstrap_is_default_off_and_idempotent(session: Session) -> None:
    service = IntegrationCatalogService(session)
    assert service.bootstrap_walmart_bill_governance("primary").interface_statuses == ("created",)
    assert service.bootstrap_walmart_bill_governance("primary").sync_config_statuses == (
        "unchanged",
    )
    interface = session.scalars(
        select(IntegrationInterface).where(
            IntegrationInterface.interface_key == WALMART_BILL_SYNC_SPEC.interface_key
        )
    ).one()
    config = session.scalars(
        select(IntegrationSyncConfig).where(IntegrationSyncConfig.interface_id == interface.id)
    ).one()
    assert interface.outbound_enabled is False
    assert (config.is_enabled, config.schedule_enabled) == (False, False)
    assert (config.page_size, config.max_pages) == (200, 500)


def test_sync_stores_raw_first_and_builds_periods(session: Session) -> None:
    add_stores(session)
    interface = governed(session)
    client = FakeLingxing(base_rows())
    run = run_sync(session, interface, client)

    assert (run.status, run.error_code) == ("succeeded", None)
    assert (run.records_seen, run.records_written) == (6, 6)
    assert client.windows(STORE_A) == [
        (date(2026, 10, 6), date(2026, 10, 31)),
        (date(2026, 11, 1), date(2026, 11, 9)),
    ]
    refs = session.scalar(
        select(func.count()).select_from(ApiRawRequestRef).where(ApiRawRequestRef.run_id == run.id)
    )
    assert refs == run.work_items_total

    a1 = period(session, STORE_A, "rk-a1")
    assert (a1.line_count, a1.excluded_line_count) == (3, 0)
    assert a1.payable_amount == Decimal("14.0000")
    assert a1.total_payable is None
    assert a1.status == "normal"
    assert a1.store_name == "CN9901-合成甲"
    assert (a1.period_start_date, a1.period_end_date) == (date(2026, 10, 15), date(2026, 10, 17))
    assert a1.amounts_by_type == {"Commission": "-1.5000", "Product Price": "15.5000"}
    assert period(session, STORE_A, "rk-a2").status == "voided"
    assert period(session, STORE_A, "rk-a3").status == "not_payable"
    assert period(session, STORE_B, "rk-b1").payable_amount == Decimal("20.0000")

    stored = session.scalars(select(WalmartBillLine).where(WalmartBillLine.lx_line_id == "1")).one()
    assert "shipToCity" not in stored.extra_fields
    assert stored.extra_fields["partnerItemName"] == "合成商品"
    assert [item.report_key for item in list_periods(session)][:1] == ["rk-a3"]


def test_rerun_marks_lines_gone_from_lingxing_and_recomputes(session: Session) -> None:
    add_stores(session)
    interface = governed(session)
    rows = base_rows()
    run_sync(session, interface, FakeLingxing(rows))

    without_line_two = [row for row in rows if row["id"] != 2]
    second = run_sync(session, interface, FakeLingxing(without_line_two))
    assert second.status == "succeeded"
    gone = session.scalars(select(WalmartBillLine).where(WalmartBillLine.lx_line_id == "2")).one()
    assert gone.missing_since is not None
    a1 = period(session, STORE_A, "rk-a1")
    assert (a1.line_count, a1.excluded_line_count) == (2, 1)
    assert a1.payable_amount == Decimal("8.5000")

    run_sync(session, interface, FakeLingxing(rows))
    session.refresh(gone)
    assert gone.missing_since is None
    assert period(session, STORE_A, "rk-a1").payable_amount == Decimal("14.0000")
    assert session.scalar(select(func.count()).select_from(WalmartBillLine)) == 6


def test_long_bill_is_chased_back_until_its_first_line(session: Session) -> None:
    add_stores(session)
    interface = governed(session)
    rows = [
        bill_line(20 + index, STORE_A, "rk-long", day, "1")
        for index, day in enumerate(("2026-08-20", "2026-09-06", "2026-09-20", "2026-10-07"))
    ]
    client = FakeLingxing(rows)
    assert run_sync(session, interface, client).status == "succeeded"

    # 窗口 10-06 起；10-07 那笔太靠前 → 往前补 09-05~10-05 → 09-06 又靠前 → 再补 08-05~09-04；
    # 08-20 离那段开头够远，停。
    assert (date(2026, 9, 5), date(2026, 10, 5)) in client.windows(STORE_A)
    assert (date(2026, 8, 5), date(2026, 9, 4)) in client.windows(STORE_A)
    assert (date(2026, 7, 5), date(2026, 8, 4)) not in client.windows(STORE_A)
    assert client.windows(STORE_B) == [
        (date(2026, 10, 6), date(2026, 10, 31)),
        (date(2026, 11, 1), date(2026, 11, 9)),
    ]
    long_bill = period(session, STORE_A, "rk-long")
    assert long_bill.line_count == 4
    assert long_bill.period_start_date == date(2026, 8, 20)
    assert long_bill.payable_amount == Decimal("4.0000")


def test_bill_first_seen_in_an_extension_is_chased_back_too(session: Session) -> None:
    """2026-11-11 回填 10-06 期缺 8 月中旬明细：那期账单只在往前补的段里出现，也要接着往前追。"""
    add_stores(session)
    interface = governed(session)
    rows = [
        # 窗口（10-06 起）里只看得到 rk-trigger，它靠近窗口开头，触发往前补 09-05~10-05
        bill_line(40, STORE_A, "rk-trigger", "2026-10-07", "1", report_date="2026-11-03"),
        # rk-new 账单日在窗口里，但明细全在窗口之前：第一次往前补才出现，且靠近那段开头
        bill_line(41, STORE_A, "rk-new", "2026-09-06", "1", report_date="2026-10-20"),
        bill_line(42, STORE_A, "rk-new", "2026-08-20", "-5", report_date="2026-10-20"),
    ]
    client = FakeLingxing(rows)
    assert run_sync(session, interface, client).status == "succeeded"

    assert (date(2026, 9, 5), date(2026, 10, 5)) in client.windows(STORE_A)
    assert (date(2026, 8, 5), date(2026, 9, 4)) in client.windows(STORE_A)
    assert (date(2026, 7, 5), date(2026, 8, 4)) not in client.windows(STORE_A)
    new_bill = period(session, STORE_A, "rk-new")
    assert new_bill.line_count == 2
    assert new_bill.period_start_date == date(2026, 8, 20)
    assert new_bill.payable_amount == Decimal("-4.0000")


def _chase_from_trigger(session: Session, report_key: str, report_date: str) -> FakeLingxing:
    """窗口（10-06~11-09）里只有 rk-trigger 靠近开头，触发往前补 09-05~10-05；
    report_key 那期第一次出现在这段里，09-06 那笔靠近段开头，08-20 还要再往前补一段才拿得到。"""
    add_stores(session)
    interface = governed(session)
    rows = [
        bill_line(50, STORE_A, "rk-trigger", "2026-10-07", "1", report_date="2026-11-03"),
        bill_line(51, STORE_A, report_key, "2026-09-06", "1", report_date=report_date),
        bill_line(52, STORE_A, report_key, "2026-08-20", "-5", report_date=report_date),
    ]
    client = FakeLingxing(rows)
    assert run_sync(session, interface, client).status == "succeeded"
    assert (date(2026, 9, 5), date(2026, 10, 5)) in client.windows(STORE_A)
    return client


def test_new_bill_dated_before_the_window_is_not_chased(session: Session) -> None:
    client = _chase_from_trigger(session, "rk-old", "2026-09-22")
    assert (date(2026, 8, 5), date(2026, 9, 4)) not in client.windows(STORE_A)
    assert period(session, STORE_A, "rk-old").line_count == 1


def test_new_bill_dated_after_the_window_is_not_chased(session: Session) -> None:
    client = _chase_from_trigger(session, "rk-later", "2026-11-20")
    assert (date(2026, 8, 5), date(2026, 9, 4)) not in client.windows(STORE_A)
    assert period(session, STORE_A, "rk-later").line_count == 1


def test_bill_already_chased_keeps_going_whatever_its_bill_date(session: Session) -> None:
    """窗口里就看到、已经在追的账单，账单日在窗口之后也照旧往前追，不因账单日判断提前停。"""
    add_stores(session)
    interface = governed(session)
    rows = [
        bill_line(60 + index, STORE_A, "rk-carry", day, "1", report_date="2026-11-20")
        for index, day in enumerate(("2026-08-20", "2026-09-06", "2026-10-07"))
    ]
    client = FakeLingxing(rows)
    assert run_sync(session, interface, client).status == "succeeded"

    assert (date(2026, 9, 5), date(2026, 10, 5)) in client.windows(STORE_A)
    assert (date(2026, 8, 5), date(2026, 9, 4)) in client.windows(STORE_A)
    assert (date(2026, 7, 5), date(2026, 8, 4)) not in client.windows(STORE_A)
    assert period(session, STORE_A, "rk-carry").line_count == 3


def test_identical_rows_from_lingxing_are_both_kept(session: Session) -> None:
    add_stores(session)
    interface = governed(session)
    twin = bill_line(50, STORE_A, "rk-twin", "2026-10-20", "3")
    client = FakeLingxing([twin, dict(twin), bill_line(51, STORE_A, "rk-twin", "2026-10-21", "1")])
    assert run_sync(session, interface, client).status == "succeeded"
    assert period(session, STORE_A, "rk-twin").line_count == 3
    assert period(session, STORE_A, "rk-twin").payable_amount == Decimal("7.0000")

    # 再拉一次，三行都还在，不新增也不标消失。
    assert run_sync(session, interface, client).status == "succeeded"
    assert session.scalar(select(func.count()).select_from(WalmartBillLine)) == 3
    assert period(session, STORE_A, "rk-twin").line_count == 3


def test_amount_changed_by_lingxing_replaces_the_old_line(session: Session) -> None:
    add_stores(session)
    interface = governed(session)
    rows = base_rows()
    run_sync(session, interface, FakeLingxing(rows))
    changed = [dict(row, amount="11") if row["id"] == 1 else row for row in rows]
    assert run_sync(session, interface, FakeLingxing(changed)).status == "succeeded"
    versions = session.scalars(
        select(WalmartBillLine).where(WalmartBillLine.lx_line_id == "1")
    ).all()
    assert sorted(line.missing_since is None for line in versions) == [False, True]
    assert period(session, STORE_A, "rk-a1").payable_amount == Decimal("15.0000")


def test_total_changing_mid_paging_fails_only_that_store(session: Session) -> None:
    add_stores(session)
    interface = governed(session)
    client = FakeLingxing(base_rows())
    client.total_bump[(STORE_A, 2)] = 1
    run = run_sync(session, interface, client)

    assert (run.status, run.error_code) == ("failed", "SYNC_WALMART_BILL_STORE_PARTIAL")
    assert run.work_items_failed == 1
    assert session.get(WalmartBillPeriod, ("primary", STORE_A, "rk-a1")) is None
    assert period(session, STORE_B, "rk-b1").status == "normal"


def test_row_outside_requested_dates_fails_the_store_and_keeps_old_data(session: Session) -> None:
    add_stores(session)
    interface = governed(session)
    rows = base_rows()
    run_sync(session, interface, FakeLingxing(rows))

    client = FakeLingxing(rows)
    client.extra_rows[STORE_A] = [bill_line(99, STORE_A, "rk-x", "2026-01-01", "1")]
    run = run_sync(session, interface, client)
    assert (run.status, run.error_code) == ("failed", "SYNC_WALMART_BILL_STORE_PARTIAL")
    missing = session.scalar(
        select(func.count())
        .select_from(WalmartBillLine)
        .where(WalmartBillLine.missing_since.is_not(None))
    )
    assert missing == 0
    assert period(session, STORE_A, "rk-a1").payable_amount == Decimal("14.0000")


def test_too_many_rows_splits_the_dates_in_half(session: Session) -> None:
    add_stores(session)
    interface = governed(session, page_size=2, max_pages=1)
    rows = [
        bill_line(31, STORE_A, "rk-s", "2026-10-08", "1"),
        bill_line(32, STORE_A, "rk-s", "2026-10-10", "1"),
        bill_line(33, STORE_A, "rk-s", "2026-10-25", "1"),
    ]
    client = FakeLingxing(rows)
    assert run_sync(session, interface, client).status == "succeeded"
    assert (date(2026, 10, 6), date(2026, 10, 18)) in client.windows(STORE_A)
    assert (date(2026, 10, 19), date(2026, 10, 31)) in client.windows(STORE_A)
    assert period(session, STORE_A, "rk-s").line_count == 3


def test_backfill_uses_the_run_window_and_never_goes_before_march(session: Session) -> None:
    add_stores(session)
    interface = governed(session)
    window = (
        datetime(2026, 2, 1, tzinfo=SHANGHAI),
        datetime(2026, 4, 1, tzinfo=SHANGHAI),
    )
    client = FakeLingxing(
        [bill_line(41, STORE_A, "rk-m", "2026-03-15", "2", report_date="2026-03-20")]
    )
    run = run_sync(session, interface, client, trigger="backfill", window=window)
    assert run.status == "succeeded"
    assert client.windows(STORE_A) == [(date(2026, 3, 1), date(2026, 3, 31))]
    assert period(session, STORE_A, "rk-m").payable_amount == Decimal("2.0000")


def test_handler_refuses_a_disabled_interface(session: Session) -> None:
    add_stores(session)
    interface = governed(session, enabled=False)
    run = queued_run(session, interface)
    handler = LingxingWalmartBillSyncHandler(session, client=FakeLingxing([]), now=lambda: NOW)
    with pytest.raises(WalmartBillSyncError, match="SYNC_WALMART_BILL_EXECUTION_NOT_AUTHORIZED"):
        handler.execute(run, interface)


def test_task_centre_dispatches_here_and_test_env_cannot_reach_lingxing(session: Session) -> None:
    add_stores(session)
    run = queued_run(session, governed(session))
    SyncRunExecutionService(session).execute(run.id)
    session.refresh(run)
    assert (run.status, run.error_code) == ("failed", "SYNC_WALMART_BILL_RUNTIME_NOT_AUTHORIZED")


def test_task_centre_refuses_a_disabled_config(session: Session) -> None:
    run = queued_run(session, governed(session, enabled=False))
    SyncRunExecutionService(session).execute(run.id)
    session.refresh(run)
    assert (run.status, run.error_code) == ("failed", "SYNC_CONFIG_DISABLED")


def bill_config(session: Session) -> IntegrationSyncConfig:
    return session.scalars(
        select(IntegrationSyncConfig)
        .join(IntegrationInterface, IntegrationSyncConfig.interface_id == IntegrationInterface.id)
        .where(IntegrationInterface.interface_key == WALMART_BILL_SYNC_SPEC.interface_key)
    ).one()


def test_enable_without_schedule_opens_manual_runs_only(session: Session) -> None:
    catalog = IntegrationCatalogService(session)
    catalog.bootstrap_walmart_bill_governance("primary")
    assert catalog.enable_walmart_bill_sync("other") is False
    assert catalog.enable_walmart_bill_sync("primary") is True
    config = bill_config(session)
    interface = session.get(IntegrationInterface, config.interface_id)
    assert interface is not None and interface.outbound_enabled is True
    assert (config.is_enabled, config.schedule_enabled) == (True, False)
    assert config.next_run_at is None

    later = NOW + timedelta(days=8)
    run_ids = IntegrationSchedulerService(session).create_due_runs(now=later)
    scheduled = [
        run
        for run in (session.get(IntegrationSyncRun, run_id) for run_id in run_ids)
        if run is not None and run.interface_key == WALMART_BILL_SYNC_SPEC.interface_key
    ]
    assert scheduled == []


def test_enable_with_schedule_turns_on_a_weekly_wednesday_schedule(session: Session) -> None:
    catalog = IntegrationCatalogService(session)
    catalog.bootstrap_walmart_bill_governance("primary")
    assert catalog.enable_walmart_bill_sync("other", schedule=True) is False
    assert catalog.enable_walmart_bill_sync("primary") is True
    assert bill_config(session).schedule_enabled is False
    assert catalog.enable_walmart_bill_sync("primary", schedule=True) is True
    config = session.scalars(
        select(IntegrationSyncConfig)
        .join(IntegrationInterface, IntegrationSyncConfig.interface_id == IntegrationInterface.id)
        .where(IntegrationInterface.interface_key == WALMART_BILL_SYNC_SPEC.interface_key)
    ).one()
    assert config.schedule_cron == "0 19 * * 2"
    planned = config.next_run_at
    assert planned is not None
    local = planned.astimezone(SHANGHAI)
    assert (local.weekday(), local.hour, local.minute) == (2, 3, 0)

    due = planned + timedelta(minutes=1)
    run_ids = IntegrationSchedulerService(session).create_due_runs(now=due)
    runs = [
        run
        for run in (session.get(IntegrationSyncRun, run_id) for run_id in run_ids)
        if run is not None and run.interface_key == WALMART_BILL_SYNC_SPEC.interface_key
    ]
    assert len(runs) == 1 and runs[0].trigger_type == "schedule"


def test_manual_run_is_refused_until_enabled(session: Session) -> None:
    catalog = IntegrationCatalogService(session)
    catalog.bootstrap_walmart_bill_governance("primary")
    interface = session.scalars(
        select(IntegrationInterface).where(
            IntegrationInterface.interface_key == WALMART_BILL_SYNC_SPEC.interface_key
        )
    ).one()
    config = session.scalars(
        select(IntegrationSyncConfig).where(IntegrationSyncConfig.interface_id == interface.id)
    ).one()

    def press() -> UUID:
        return (
            IntegrationSyncService(session)
            .create_manual_run(
                config.id,
                TriggerRequest(reason="合成", idempotency_key=f"bill-{uuid4()}"),
                actor_ref="admin",
                request_id="r",
                account_refs=frozenset({"primary"}),
            )
            .run_id
        )

    with pytest.raises(ApiError) as refused:
        press()
    assert refused.value.code == "SYNC_INTERFACE_DISABLED"
    catalog.enable_walmart_bill_sync("primary")
    run = session.get(IntegrationSyncRun, press())
    assert run is not None and (run.status, run.trigger_type) == ("queued", "manual")


def test_page_button_needs_enabling_never_doubles_and_reports_status(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatched: list[UUID] = []
    monkeypatch.setattr(bill_sync, "dispatch_sync_run", dispatched.append)
    assert bill_sync.latest_walmart_bill_sync(session).status == "never"
    with pytest.raises(bill_sync.WalmartBillSyncNotConfiguredError):
        bill_sync.start_walmart_bill_sync(session, actor="admin", request_id="r")

    catalog = IntegrationCatalogService(session)
    catalog.bootstrap_walmart_bill_governance("primary")
    with pytest.raises(bill_sync.WalmartBillSyncNotConfiguredError):
        bill_sync.start_walmart_bill_sync(session, actor="admin", request_id="r")
    assert catalog.enable_walmart_bill_sync("primary") is True

    first = bill_sync.start_walmart_bill_sync(session, actor="admin", request_id="r")
    assert (first.status, first.trigger_type) == ("queued", "manual")
    second = bill_sync.start_walmart_bill_sync(session, actor="admin", request_id="r")
    assert second.run_id == first.run_id
    assert dispatched == [first.run_id]


def test_page_button_reports_when_the_queue_is_down(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def down(_run_id: UUID) -> None:
        raise TaskDispatchError("SYNC_DISPATCH_FAILED")

    monkeypatch.setattr(bill_sync, "dispatch_sync_run", down)
    catalog = IntegrationCatalogService(session)
    catalog.bootstrap_walmart_bill_governance("primary")
    catalog.enable_walmart_bill_sync("primary")
    with pytest.raises(bill_sync.WalmartBillSyncUnavailableError):
        bill_sync.start_walmart_bill_sync(session, actor="admin", request_id="r")


def assert_periods_match_lines(session: Session, store_id: str) -> None:
    """期汇总 = 有效明细合计（领星账单总额都是空的时候）。"""
    for item in session.scalars(
        select(WalmartBillPeriod).where(WalmartBillPeriod.store_id == store_id)
    ).all():
        total = session.scalar(
            select(func.coalesce(func.sum(WalmartBillLine.amount), 0)).where(
                WalmartBillLine.store_id == store_id,
                WalmartBillLine.report_key == item.report_key,
                WalmartBillLine.delete_flag == 0,
                WalmartBillLine.missing_since.is_(None),
            )
        )
        assert item.payable_amount == Decimal(total), item.report_key


def test_whole_period_gone_on_rerun_becomes_voided_with_zero(session: Session) -> None:
    add_stores(session)
    interface = governed(session)
    rows = base_rows()
    run_sync(session, interface, FakeLingxing(rows))
    assert period(session, STORE_A, "rk-a1").payable_amount == Decimal("14.0000")

    without_a1 = [row for row in rows if row["reportKey"] != "rk-a1"]
    assert run_sync(session, interface, FakeLingxing(without_a1)).status == "succeeded"
    a1 = period(session, STORE_A, "rk-a1")
    assert (a1.status, a1.payable_amount, a1.amount_sum) == ("voided", Decimal("0"), Decimal("0"))
    assert (a1.line_count, a1.excluded_line_count) == (0, 3)
    assert a1.amounts_by_type == {}
    assert_periods_match_lines(session, STORE_A)


def test_lines_moved_to_a_new_report_key_void_the_old_period(session: Session) -> None:
    add_stores(session)
    interface = governed(session)
    rows = base_rows()
    run_sync(session, interface, FakeLingxing(rows))

    moved = [
        dict(row, reportKey="rk-a1-new") if row["reportKey"] == "rk-a1" else row for row in rows
    ]
    assert run_sync(session, interface, FakeLingxing(moved)).status == "succeeded"
    old = period(session, STORE_A, "rk-a1")
    new = period(session, STORE_A, "rk-a1-new")
    assert (old.status, old.payable_amount) == ("voided", Decimal("0"))
    assert (new.status, new.payable_amount, new.line_count) == ("normal", Decimal("14.0000"), 3)
    assert old.payable_amount + new.payable_amount == Decimal("14.0000")
    assert_periods_match_lines(session, STORE_A)


def test_bad_second_page_rolls_back_the_whole_store(session: Session) -> None:
    add_stores(session)
    interface = governed(session)
    rows = base_rows()
    run_sync(session, interface, FakeLingxing(rows))
    lines_before = session.scalar(
        select(func.count()).select_from(WalmartBillLine).where(WalmartBillLine.store_id == STORE_A)
    )

    # 每页 2 条：第 1 页 = 明细 1、2（合法），第 2 页里有一条金额不是数字。
    bad = [*rows[:2], bill_line(7, STORE_A, "rk-a1", "2026-10-16", "not-a-number"), *rows[2:]]
    bad[0] = dict(bad[0], amount="12")  # 第 1 页改了金额：如果没回滚，旧行会被标消失、新行写进来
    run = run_sync(session, interface, FakeLingxing(bad))

    assert (run.status, run.error_code) == ("failed", "SYNC_WALMART_BILL_STORE_PARTIAL")
    lines_after = session.scalar(
        select(func.count()).select_from(WalmartBillLine).where(WalmartBillLine.store_id == STORE_A)
    )
    assert lines_after == lines_before
    missing = session.scalar(
        select(func.count())
        .select_from(WalmartBillLine)
        .where(WalmartBillLine.missing_since.is_not(None))
    )
    assert missing == 0
    assert period(session, STORE_A, "rk-a1").payable_amount == Decimal("14.0000")
    assert_periods_match_lines(session, STORE_A)
    assert_periods_match_lines(session, STORE_B)

    failed = session.scalars(
        select(IntegrationSyncRunWorkItem).where(
            IntegrationSyncRunWorkItem.run_id == run.id,
            IntegrationSyncRunWorkItem.status == "failed",
        )
    ).all()
    assert [item.error_code for item in failed] == ["SYNC_WALMART_BILL_INVALID_AMOUNT"]
    assert run.work_items_failed == 1
    kept = session.scalar(
        select(func.count())
        .select_from(ApiRawRequestRef)
        .where(ApiRawRequestRef.work_item_id == failed[0].id)
    )
    assert kept == 1


def test_empty_answer_for_dates_that_had_lines_fails_the_store(session: Session) -> None:
    add_stores(session)
    interface = governed(session)
    rows = base_rows()
    run_sync(session, interface, FakeLingxing(rows))

    # 11 月这段原来有 rk-a3；领星这次一条都没给 → 不当成「全被删」，整店失败、什么都不标。
    without_november = [row for row in rows if row["id"] != 5]
    run = run_sync(session, interface, FakeLingxing(without_november))
    assert (run.status, run.error_code) == ("failed", "SYNC_WALMART_BILL_STORE_PARTIAL")
    failed = session.scalars(
        select(IntegrationSyncRunWorkItem.error_code).where(
            IntegrationSyncRunWorkItem.run_id == run.id,
            IntegrationSyncRunWorkItem.status == "failed",
        )
    ).all()
    assert failed == ["SYNC_WALMART_BILL_EMPTY_UNEXPECTED"]
    line_five = session.scalars(
        select(WalmartBillLine).where(WalmartBillLine.lx_line_id == "5")
    ).one()
    assert line_five.missing_since is None
    assert period(session, STORE_A, "rk-a3").status == "not_payable"
    assert period(session, STORE_B, "rk-b1").status == "normal"


def store_line_count(session: Session, store_id: str) -> int:
    return session.scalar(
        select(func.count())
        .select_from(WalmartBillLine)
        .where(WalmartBillLine.store_id == store_id)
    )


def test_heartbeat_that_commits_the_business_session_cannot_leak_half_a_store(
    session: Session,
) -> None:
    """模拟生产：心跳在同一个 session 上 commit 会把保存点提交掉；店内提交要被拒绝、整店回滚。"""
    add_stores(session)
    interface = governed(session)
    rows = base_rows()
    run_sync(session, interface, FakeLingxing(rows))
    before = store_line_count(session, STORE_A)

    bad = [*rows[:2], bill_line(7, STORE_A, "rk-a1", "2026-10-16", "not-a-number"), *rows[2:]]
    bad[0] = dict(bad[0], amount="12")
    run = queued_run(session, interface)
    run.status = "running"
    LingxingWalmartBillSyncHandler(
        session, client=FakeLingxing(bad), now=lambda: NOW, heartbeat=session.commit
    ).execute(run, interface)

    assert run.status == "failed"
    failed_codes = session.scalars(
        select(IntegrationSyncRunWorkItem.error_code).where(
            IntegrationSyncRunWorkItem.run_id == run.id,
            IntegrationSyncRunWorkItem.status == "failed",
        )
    ).all()
    assert failed_codes and set(failed_codes) == {"SYNC_WALMART_BILL_COMMIT_INSIDE_STORE"}
    assert store_line_count(session, STORE_A) == before
    missing = session.scalar(
        select(func.count())
        .select_from(WalmartBillLine)
        .where(WalmartBillLine.missing_since.is_not(None))
    )
    assert missing == 0
    assert period(session, STORE_A, "rk-a1").payable_amount == Decimal("14.0000")
    assert_periods_match_lines(session, STORE_A)
    assert_periods_match_lines(session, STORE_B)


def test_task_centre_renews_the_lock_on_a_separate_session(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_stores(session)
    run = queued_run(session, governed(session))
    calls: list[tuple[str, UUID]] = []

    class StubHandler:
        handler_key = LingxingWalmartBillSyncHandler.handler_key

        def __init__(self, _session: Session, *, heartbeat: Any) -> None:
            self.heartbeat = heartbeat

        def execute(self, _run: IntegrationSyncRun, _interface: IntegrationInterface) -> None:
            self.heartbeat()

    monkeypatch.setattr(execution_module, "LingxingWalmartBillSyncHandler", StubHandler)
    monkeypatch.setattr(
        SyncRunExecutionService,
        "_heartbeat_data_pages_lock",
        staticmethod(lambda run_id: calls.append(("separate", run_id))),
    )
    monkeypatch.setattr(
        SyncRunExecutionService,
        "_heartbeat_lock",
        lambda _self, run_id: calls.append(("same", run_id)),
    )
    SyncRunExecutionService(session).execute(run.id)
    assert ("separate", run.id) in calls
    assert all(kind != "same" for kind, _ in calls)


def test_lost_lock_stops_the_whole_run_before_the_next_store(session: Session) -> None:
    add_stores(session)
    interface = governed(session)
    client = FakeLingxing(base_rows())
    run = queued_run(session, interface)
    run.status = "running"

    def lost() -> None:
        raise ProductInfoOneTimeRunError("SYNC_LOCK_LEASE_LOST")

    handler = LingxingWalmartBillSyncHandler(
        session, client=client, now=lambda: NOW, heartbeat=lost
    )
    with pytest.raises(ProductInfoOneTimeRunError, match="SYNC_LOCK_LEASE_LOST"):
        handler.execute(run, interface)
    assert client.calls == []
    assert client.windows(STORE_B) == []
    assert store_line_count(session, STORE_A) == 0
    assert store_line_count(session, STORE_B) == 0


def test_a_period_with_two_currencies_fails_the_store(session: Session) -> None:
    add_stores(session)
    interface = governed(session)
    rows = base_rows()
    rows[1] = dict(rows[1], currency="CAD")
    run = run_sync(session, interface, FakeLingxing(rows))
    assert (run.status, run.error_code) == ("failed", "SYNC_WALMART_BILL_STORE_PARTIAL")
    failed = session.scalars(
        select(IntegrationSyncRunWorkItem.error_code).where(
            IntegrationSyncRunWorkItem.run_id == run.id,
            IntegrationSyncRunWorkItem.status == "failed",
        )
    ).all()
    assert failed == ["SYNC_WALMART_BILL_MIXED_CURRENCY"]
    assert session.get(WalmartBillPeriod, ("primary", STORE_A, "rk-a1")) is None
    assert period(session, STORE_B, "rk-b1").status == "normal"

"""领星月汇率同步。不连接口，全部合成数据；数据库部分没配隔离库就跳过。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from pydantic import JsonValue, ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.api import ApiError
from app.core.config import Settings, SettingsError, get_test_database_url
from app.integrations.lingxing.client import LingxingRawEnvelope
from app.modules.finance_cashflow import fx_sync
from app.modules.fx_rates.models import LingxingFxRate
from app.modules.fx_rates.reader import list_usd_cny_rates, load_usd_cny_rates
from app.modules.integration_sync.catalog import IntegrationCatalogService
from app.modules.integration_sync.execution import SyncRunExecutionService
from app.modules.integration_sync.fx_catalog import FX_RATE_SYNC_SPEC
from app.modules.integration_sync.handlers.lingxing_fx_rate_sync import (
    FxRateSyncError,
    LingxingFxRateSyncHandler,
    fx_response_succeeded,
    fx_rows,
    months_back,
    parse_fx_rows,
)
from app.modules.integration_sync.models import (
    ApiRawRequestRef,
    IntegrationInterface,
    IntegrationSyncConfig,
    IntegrationSyncRun,
    IntegrationSyncRunWorkItem,
)
from app.modules.integration_sync.scheduler import IntegrationSchedulerService
from app.modules.integration_sync.schemas import TriggerRequest
from app.modules.integration_sync.service import IntegrationSyncService
from app.modules.integration_sync.tasks import TaskDispatchError

NOW = datetime(2026, 11, 5, 3, tzinfo=UTC)
MONTHS = ["2026-09", "2026-10", "2026-11"]


def row(month: str, code: str = "USD", my_rate: JsonValue = "7.1000000000") -> dict[str, JsonValue]:
    return {
        "date": month,
        "code": code,
        "icon": "$",
        "name": "合成币种",
        "rate_org": "7.2000",
        "my_rate": my_rate,
        "update_time": "2026-11-01 00:00:00",
    }


def body(rows: JsonValue, code: int = 0) -> dict[str, JsonValue]:
    return {"code": code, "message": "success", "data": rows, "total": 1}


class FakeClient:
    def __init__(self, responses: dict[str, JsonValue], *, success: bool = True) -> None:
        self.responses = responses
        self.success = success
        self.months: list[str] = []

    def fetch_fx_month(self, **kwargs: str) -> LingxingRawEnvelope:
        month = kwargs["month"]
        self.months.append(month)
        response = self.responses[month]
        if isinstance(response, str):
            raise RuntimeError(response)
        return LingxingRawEnvelope(
            api_path=FX_RATE_SYNC_SPEC.endpoint_path,
            request_body_json={"date": month},
            response_json=response,
            response_code=200,
            is_success=self.success,
            pulled_at=NOW,
            page_no=1,
            page_size=1,
            store_id=kwargs["source_account_ref"],
            object_type="lingxing_fx_rate",
            trace_id=kwargs["run_id"],
            run_id=kwargs["run_id"],
            batch_id=kwargs["work_item_id"],
            attempt_no=1,
        )


def test_spec_is_default_off() -> None:
    assert FX_RATE_SYNC_SPEC.initial_outbound_enabled is False
    assert FX_RATE_SYNC_SPEC.schedule_enabled is False


def test_months_back_uses_shanghai_month_and_crosses_years() -> None:
    assert months_back(NOW, 3) == MONTHS
    assert months_back(datetime(2026, 10, 31, 16, tzinfo=UTC), 1) == ["2026-11"]
    assert months_back(datetime(2026, 2, 1, 4, tzinfo=UTC), 3) == [
        "2025-12",
        "2026-01",
        "2026-02",
    ]


def test_rows_are_read_from_single_layer_data_array() -> None:
    assert fx_rows(body([row("2026-10")])) == [row("2026-10")]
    assert fx_rows(body(None)) == []
    assert fx_rows(body({"data": []})) is None
    assert fx_rows({"code": 0}) is None
    assert fx_rows([]) is None


def test_success_needs_code_zero_and_an_array() -> None:
    path = FX_RATE_SYNC_SPEC.endpoint_path
    response = httpx.Response(200)
    assert fx_response_succeeded(path, response, body([])) is True
    assert fx_response_succeeded(path, response, body([], code=1)) is False
    assert fx_response_succeeded(path, response, body({"list": []})) is False
    assert fx_response_succeeded("/other", response, body([])) is False


def test_parse_keeps_rates_and_treats_empty_or_zero_as_missing() -> None:
    parsed = parse_fx_rows(
        [row("2026-10"), row("2026-10", "eur", ""), row("2026-10", "GBP", "0")],
        "2026-10",
    )
    assert parsed is not None
    assert [(item["currency_code"], item["my_rate"]) for item in parsed] == [
        ("USD", Decimal("7.1000000000")),
        ("EUR", None),
        ("GBP", None),
    ]


@pytest.mark.parametrize(
    "bad",
    [
        row("2026-09"),
        row("2026-10", ""),
        row("2026-10", "TOOLONGCODE"),
        row("2026-10", my_rate="abc"),
        row("2026-10", my_rate="-1"),
        row("2026-10", my_rate="NaN"),
    ],
)
def test_parse_rejects_wrong_month_and_bad_numbers(bad: dict[str, object]) -> None:
    assert parse_fx_rows([bad], "2026-10") is None


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


def governed(session: Session, *, enabled: bool = True) -> IntegrationInterface:
    IntegrationCatalogService(session).bootstrap_fx_governance("primary")
    interface = session.scalars(
        select(IntegrationInterface).where(
            IntegrationInterface.interface_key == FX_RATE_SYNC_SPEC.interface_key
        )
    ).one()
    config = session.scalars(
        select(IntegrationSyncConfig).where(IntegrationSyncConfig.interface_id == interface.id)
    ).one()
    interface.outbound_enabled = enabled
    config.is_enabled = enabled
    config.max_pages = 3
    session.flush()
    return interface


def queued_run(session: Session, interface: IntegrationInterface) -> IntegrationSyncRun:
    config = session.scalars(
        select(IntegrationSyncConfig).where(IntegrationSyncConfig.interface_id == interface.id)
    ).one()
    run = IntegrationSyncRun(
        config_id=config.id,
        interface_id=interface.id,
        provider="lingxing",
        interface_key=interface.interface_key,
        source_account_ref="primary",
        trigger_type="manual",
        status="queued",
        idempotency_key=f"fx-{uuid4()}",
        queued_at=NOW,
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
    client: FakeClient,
) -> IntegrationSyncRun:
    run = queued_run(session, interface)
    run.status = "running"
    LingxingFxRateSyncHandler(session, client=client, now=lambda: NOW).execute(run, interface)
    return run


def test_bootstrap_is_default_off_and_idempotent(session: Session) -> None:
    service = IntegrationCatalogService(session)
    assert service.bootstrap_fx_governance("primary").interface_statuses == ("created",)
    assert service.bootstrap_fx_governance("primary").sync_config_statuses == ("unchanged",)
    interface = session.scalars(
        select(IntegrationInterface).where(
            IntegrationInterface.interface_key == FX_RATE_SYNC_SPEC.interface_key
        )
    ).one()
    config = session.scalars(
        select(IntegrationSyncConfig).where(IntegrationSyncConfig.interface_id == interface.id)
    ).one()
    assert interface.outbound_enabled is False
    assert config.is_enabled is False
    assert config.schedule_enabled is False
    assert (config.page_size, config.max_pages) == (1, 13)


def test_sync_stores_raw_first_skips_empty_month_and_rerun_overwrites(session: Session) -> None:
    interface = governed(session)
    client = FakeClient(
        {
            "2026-09": body([]),
            "2026-10": body([row("2026-10"), row("2026-10", "EUR", "8")]),
            "2026-11": body([row("2026-11", my_rate="")]),
        }
    )
    run = run_sync(session, interface, client)

    assert client.months == MONTHS
    assert (run.status, run.records_seen, run.records_written) == ("succeeded", 3, 3)
    assert (run.work_items_total, run.work_items_succeeded) == (3, 3)
    assert load_usd_cny_rates(session) == {"2026-10": Decimal("7.1000000000")}
    stored = session.get(LingxingFxRate, ("2026-10", "USD"))
    assert stored is not None
    assert stored.source == "sync"
    assert stored.raw_request_ref_id is not None
    ref = session.get(ApiRawRequestRef, stored.raw_request_ref_id)
    assert ref is not None
    assert (ref.run_id, ref.response_count, ref.provider_code) == (run.id, 2, "0")
    assert ref.request_safe_params == {"date": "2026-10"}
    scopes = session.scalars(
        select(IntegrationSyncRunWorkItem.scope_key)
        .where(IntegrationSyncRunWorkItem.run_id == run.id)
        .order_by(IntegrationSyncRunWorkItem.ordinal)
    ).all()
    assert list(scopes) == MONTHS

    client.responses["2026-10"] = body([row("2026-10", my_rate="6.5")])
    assert run_sync(session, interface, client).status == "succeeded"
    session.expire_all()
    assert load_usd_cny_rates(session) == {"2026-10": Decimal("6.5000000000")}


def test_sync_overwrites_a_seeded_rate(session: Session) -> None:
    interface = governed(session)
    session.add(
        LingxingFxRate(
            rate_month="2026-10", currency_code="USD", my_rate=Decimal("1"), source="seed"
        )
    )
    session.flush()
    run_sync(
        session,
        interface,
        FakeClient({"2026-09": body([]), "2026-10": body([row("2026-10")]), "2026-11": body([])}),
    )
    session.expire_all()
    stored = session.get(LingxingFxRate, ("2026-10", "USD"))
    assert stored is not None
    assert (stored.my_rate, stored.source) == (Decimal("7.1000000000"), "sync")


def test_all_months_empty_fails_the_run(session: Session) -> None:
    interface = governed(session)
    run = run_sync(session, interface, FakeClient({month: body([]) for month in MONTHS}))
    assert (run.status, run.error_code) == ("failed", "SYNC_FX_ALL_MONTHS_EMPTY")


@pytest.mark.parametrize(
    ("bad", "success", "message"),
    [
        (body([], code=1), False, "SYNC_FX_RESPONSE_FAILED"),
        (body([row("2026-09")]), True, "SYNC_FX_INVALID_ROW"),
        ("连接失败", True, "SYNC_FX_REQUEST_FAILED"),
    ],
)
def test_a_bad_month_stops_the_run_and_keeps_earlier_months(
    session: Session,
    bad: JsonValue,
    success: bool,
    message: str,
) -> None:
    interface = governed(session)
    client = FakeClient(
        {"2026-09": body([row("2026-09")]), "2026-10": bad},
        success=True,
    )
    if not success:
        original = client.fetch_fx_month

        def failing(**kwargs: str) -> LingxingRawEnvelope:
            envelope = original(**kwargs)
            is_bad_month = kwargs["month"] == "2026-10"
            return envelope.model_copy(update={"is_success": not is_bad_month})

        client.fetch_fx_month = failing  # type: ignore[method-assign]
    run = queued_run(session, interface)
    run.status = "running"
    handler = LingxingFxRateSyncHandler(session, client=client, now=lambda: NOW)
    with pytest.raises(FxRateSyncError, match=message):
        handler.execute(run, interface)
    assert client.months == ["2026-09", "2026-10"]
    assert run.work_items_failed == 1
    assert load_usd_cny_rates(session) == {"2026-09": Decimal("7.1000000000")}
    assert (
        session.scalar(
            select(func.count())
            .select_from(LingxingFxRate)
            .where(LingxingFxRate.rate_month == "2026-10")
        )
        == 0
    )


def test_task_centre_dispatches_here_and_test_env_cannot_reach_lingxing(session: Session) -> None:
    run = queued_run(session, governed(session))
    SyncRunExecutionService(session).execute(run.id)
    session.refresh(run)
    assert (run.status, run.error_code) == ("failed", "SYNC_FX_RUNTIME_NOT_AUTHORIZED")


def test_task_centre_refuses_a_disabled_config(session: Session) -> None:
    run = queued_run(session, governed(session, enabled=False))
    SyncRunExecutionService(session).execute(run.id)
    session.refresh(run)
    assert (run.status, run.error_code) == ("failed", "SYNC_CONFIG_DISABLED")


def test_handler_refuses_a_disabled_interface(session: Session) -> None:
    interface = governed(session, enabled=False)
    run = queued_run(session, interface)
    handler = LingxingFxRateSyncHandler(
        session, client=cast(FakeClient, FakeClient({})), now=lambda: NOW
    )
    with pytest.raises(FxRateSyncError, match="SYNC_FX_EXECUTION_NOT_AUTHORIZED"):
        handler.execute(run, interface)


def test_manual_button_is_refused_until_enabled_then_queues_a_run(session: Session) -> None:
    catalog = IntegrationCatalogService(session)
    catalog.bootstrap_fx_governance("primary")
    interface = session.scalars(
        select(IntegrationInterface).where(
            IntegrationInterface.interface_key == FX_RATE_SYNC_SPEC.interface_key
        )
    ).one()
    config = session.scalars(
        select(IntegrationSyncConfig).where(IntegrationSyncConfig.interface_id == interface.id)
    ).one()
    service = IntegrationSyncService(session)

    def press() -> UUID:
        created = service.create_manual_run(
            config.id,
            TriggerRequest(reason="合成", idempotency_key=f"fx-{uuid4()}"),
            actor_ref="admin",
            request_id="r",
            account_refs=frozenset({"primary"}),
        )
        return created.run_id

    with pytest.raises(ApiError) as refused:
        press()
    assert refused.value.code == "SYNC_INTERFACE_DISABLED"

    assert catalog.enable_fx_sync("other") is False
    assert config.schedule_enabled is False
    assert config.next_run_at is None
    assert catalog.enable_fx_sync("primary") is True
    assert config.schedule_enabled is True
    assert config.schedule_cron == "0 18 * * 0"
    assert config.next_run_at is not None
    run = session.get(IntegrationSyncRun, press())
    assert run is not None
    assert (run.status, run.trigger_type) == ("queued", "manual")


def test_page_list_is_usd_only_newest_first_and_keeps_months_without_a_rate(
    session: Session,
) -> None:
    session.add_all(
        LingxingFxRate(rate_month=month, currency_code=code, my_rate=rate, source="seed")
        for month, code, rate in [
            ("2026-09", "USD", Decimal("7.1")),
            ("2026-10", "USD", None),
            ("2026-10", "EUR", Decimal("8")),
        ]
    )
    session.flush()
    assert [(row.rate_month, row.my_rate) for row in list_usd_cny_rates(session)] == [
        ("2026-10", None),
        ("2026-09", Decimal("7.1000000000")),
    ]


def test_enable_turns_on_a_weekly_schedule_that_really_queues_and_runs(session: Session) -> None:
    catalog = IntegrationCatalogService(session)
    catalog.bootstrap_fx_governance("primary")
    assert catalog.enable_fx_sync("primary") is True
    config = session.scalars(
        select(IntegrationSyncConfig)
        .join(IntegrationInterface, IntegrationSyncConfig.interface_id == IntegrationInterface.id)
        .where(IntegrationInterface.interface_key == FX_RATE_SYNC_SPEC.interface_key)
    ).one()
    config.max_pages = 1
    planned = config.next_run_at
    assert planned is not None
    utc = planned.astimezone(UTC)
    assert (utc.hour, utc.minute) == (18, 0)
    assert planned.astimezone(ZoneInfo("Asia/Shanghai")).weekday() == 0

    # 重复执行不改已有的定时。
    config.schedule_cron = "0 1 * * *"
    assert catalog.enable_fx_sync("primary") is True
    assert (config.schedule_cron, config.next_run_at) == ("0 1 * * *", planned)
    config.schedule_cron = "0 18 * * 0"
    session.flush()

    due = planned + timedelta(minutes=1)
    run_ids = IntegrationSchedulerService(session).create_due_runs(now=due)
    fx_runs = [
        run
        for run in (session.get(IntegrationSyncRun, run_id) for run_id in run_ids)
        if run is not None and run.interface_key == FX_RATE_SYNC_SPEC.interface_key
    ]
    assert len(fx_runs) == 1
    run = fx_runs[0]
    assert run.trigger_type == "schedule"
    assert config.next_run_at is not None and config.next_run_at > due

    month = months_back(due, 1)[0]
    run.status = "running"
    interface = session.get(IntegrationInterface, run.interface_id)
    assert interface is not None
    LingxingFxRateSyncHandler(
        session,
        client=FakeClient({month: body([row(month)])}),
        now=lambda: due,
    ).execute(run, interface)
    assert run.status == "succeeded"
    assert load_usd_cny_rates(session) == {month: Decimal("7.1000000000")}


def test_page_button_needs_enabling_never_doubles_and_reports_status(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatched: list[UUID] = []
    monkeypatch.setattr(fx_sync, "dispatch_sync_run", dispatched.append)
    assert fx_sync.latest_fx_sync(session).status == "never"
    with pytest.raises(fx_sync.FxSyncNotConfiguredError):
        fx_sync.start_fx_sync(session, actor="admin", request_id="r")

    catalog = IntegrationCatalogService(session)
    catalog.bootstrap_fx_governance("primary")
    with pytest.raises(fx_sync.FxSyncNotConfiguredError):
        fx_sync.start_fx_sync(session, actor="admin", request_id="r")
    assert catalog.enable_fx_sync("primary") is True

    first = fx_sync.start_fx_sync(session, actor="admin", request_id="r")
    assert first.status == "queued"
    second = fx_sync.start_fx_sync(session, actor="admin", request_id="r")
    assert second.run_id == first.run_id
    assert dispatched == [first.run_id]

    run = session.get(IntegrationSyncRun, first.run_id)
    assert run is not None
    assert run.trigger_type == "manual"
    run.status = "failed"
    run.error_code = "SYNC_FX_RESPONSE_FAILED"
    session.flush()
    failed = fx_sync.latest_fx_sync(session)
    assert (failed.status, failed.error_code) == ("failed", "SYNC_FX_RESPONSE_FAILED")
    assert failed.last_success_at is None


def test_page_button_reports_when_the_queue_is_down(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def down(_run_id: UUID) -> None:
        raise TaskDispatchError("SYNC_DISPATCH_FAILED")

    monkeypatch.setattr(fx_sync, "dispatch_sync_run", down)
    catalog = IntegrationCatalogService(session)
    catalog.bootstrap_fx_governance("primary")
    catalog.enable_fx_sync("primary")
    with pytest.raises(fx_sync.FxSyncUnavailableError):
        fx_sync.start_fx_sync(session, actor="admin", request_id="r")

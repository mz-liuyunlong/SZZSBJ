import json
import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import JsonValue, SecretStr
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.core.config import Settings
from app.integrations.lingxing.client import (
    LingxingClientError,
    LingxingRawEnvelope,
    LingxingReadonlyClient,
)
from app.modules.integration_sync.execution import SyncRunExecutionService
from app.modules.integration_sync.handlers.lingxing_product_list_sync import (
    LingxingProductListSyncHandler,
    ProductListSyncError,
    product_list_client,
    product_list_response_succeeded,
)
from app.modules.integration_sync.models import IntegrationInterface, IntegrationSyncRun
from app.modules.integration_sync.parsers.lingxing_product_list import (
    inspect_productlist_sku_ids,
)
from app.modules.integration_sync.scheduler import IntegrationSchedulerService
from app.modules.integration_sync.schemas import TriggerRequest
from app.modules.integration_sync.service import IntegrationSyncService

RUN_ID = UUID("00000000-0000-0000-0000-000000000001")
CONFIG_ID = UUID("00000000-0000-0000-0000-000000000002")
INTERFACE_ID = UUID("00000000-0000-0000-0000-000000000003")
POLICY_ID = UUID("00000000-0000-0000-0000-000000000004")
SYNTHETIC_DATABASE_URL = "postgresql+psycopg://synthetic@db.invalid/synthetic"
SYNTHETIC_APP_ID = "0123456789ABCDEF"
SYNTHETIC_ACCESS = "synthetic-access-fixture"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


class FakeTokenProvider:
    def __init__(self) -> None:
        self.get_calls = 0

    def get_access_token(self) -> SecretStr:
        self.get_calls += 1
        return SecretStr(SYNTHETIC_ACCESS)

    def recover_from_access_error(self, provider_code: int | str) -> SecretStr:
        del provider_code
        return SecretStr(SYNTHETIC_ACCESS)


class FakePageClient:
    def __init__(self, envelopes: list[LingxingRawEnvelope]) -> None:
        self.envelopes = envelopes
        self.calls: list[tuple[int, int, int]] = []

    def fetch_product_list_page(
        self,
        *,
        offset: int,
        length: int,
        page_no: int,
        source_account_ref: str,
        run_id: str,
        work_item_id: str,
    ) -> LingxingRawEnvelope:
        del source_account_ref, run_id, work_item_id
        self.calls.append((offset, length, page_no))
        return self.envelopes.pop(0)


def _settings(*, real_calls: bool) -> Settings:
    return Settings.model_validate(
        {
            "APP_ENV": "test",
            "TEST_DATABASE_URL": SYNTHETIC_DATABASE_URL,
            "LINGXING_BASE_URL": "https://provider.invalid",
            "LINGXING_APP_ID": SYNTHETIC_APP_ID,
            "LINGXING_ENABLE_REAL_CALLS": real_calls,
        }
    )


def _envelope(
    *,
    page_no: int,
    page_size: int,
    payload: JsonValue,
    success: bool = True,
) -> LingxingRawEnvelope:
    return LingxingRawEnvelope(
        api_path="/erp/sc/routing/data/local_inventory/productList",
        request_body_json={"offset": (page_no - 1) * page_size, "length": page_size},
        response_json=payload,
        response_code=200,
        is_success=success,
        pulled_at=NOW,
        page_no=page_no,
        page_size=page_size,
        object_type="lingxing_product_list",
        trace_id=str(RUN_ID),
        run_id=str(RUN_ID),
        batch_id=str(uuid4()),
        attempt_no=1,
    )


def _run() -> IntegrationSyncRun:
    return IntegrationSyncRun(
        id=RUN_ID,
        config_id=CONFIG_ID,
        interface_id=INTERFACE_ID,
        provider="lingxing",
        interface_key="productList",
        source_account_ref="default",
        trigger_type="manual",
        status="queued",
        work_items_total=0,
        work_items_succeeded=0,
        work_items_failed=0,
        records_seen=0,
        records_written=0,
        error_code=None,
        error_message=None,
    )


def _interface() -> IntegrationInterface:
    return IntegrationInterface(
        id=INTERFACE_ID,
        provider="lingxing",
        interface_key="productList",
        method="POST",
        endpoint_path="/erp/sc/routing/data/local_inventory/productList",
        request_kind="offset_page",
        outbound_enabled=True,
    )


def _handler(
    client: FakePageClient | None,
    *,
    page_size: int = 2,
) -> tuple[LingxingProductListSyncHandler, MagicMock, MagicMock]:
    session = MagicMock(spec=Session)
    handler = LingxingProductListSyncHandler(session, client=client)
    repository = MagicMock()
    handler.repository = repository
    repository.get_config.return_value = SimpleNamespace(
        is_enabled=True,
        schedule_enabled=False,
        page_size=page_size,
        max_pages=5,
    )
    repository.get_retention_policy.return_value = SimpleNamespace(id=POLICY_ID)
    repository.find_blob_by_hash.return_value = None
    repository.add_raw_blob.side_effect = lambda value: value
    repository.add_raw_request_ref.side_effect = lambda value: value
    repository.get_raw_request_ref_for_work_item.return_value = SimpleNamespace(id=uuid4())
    repository.get_lingxing_identity.return_value = None
    repository.deactivate_absent_identities.return_value = 1
    return handler, repository, session


def test_productlist_transport_uses_mocked_token_and_keeps_auth_out_of_envelope() -> None:
    token_provider = FakeTokenProvider()
    captured_body: dict[str, int] = {}
    captured_auth: dict[str, str] = {}

    def transport(request: httpx.Request) -> httpx.Response:
        captured_body.update(json.loads(request.content))
        captured_auth.update(
            {
                key: value
                for key, value in request.url.params.items()
                if key in {"access_token", "app_key", "sign"}
            }
        )
        return httpx.Response(200, json={"code": 0, "data": [], "total": 0})

    client = LingxingReadonlyClient(
        _settings(real_calls=True),
        token_provider=token_provider,
        success_evaluator=product_list_response_succeeded,
        transport=httpx.MockTransport(transport),
    )
    try:
        result = client.fetch_product_list_page(
            offset=0,
            length=1000,
            page_no=1,
            source_account_ref="default",
            run_id=str(RUN_ID),
            work_item_id=str(uuid4()),
        )
    finally:
        client.close()

    assert captured_body == {"offset": 0, "length": 1000}
    assert token_provider.get_calls == 1
    assert result.is_success is True
    serialized = result.model_dump_json()
    assert set(captured_auth) == {"access_token", "app_key", "sign"}
    assert SYNTHETIC_ACCESS not in serialized
    assert SYNTHETIC_APP_ID not in serialized
    assert captured_auth["sign"] not in serialized


def test_default_productlist_client_requires_production_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.integration_sync.handlers.lingxing_product_list_sync.get_settings",
        lambda: _settings(real_calls=True),
    )

    with pytest.raises(
        ProductListSyncError,
        match="SYNC_PRODUCTLIST_SERVER_ENVIRONMENT_REQUIRED",
    ):
        with product_list_client():
            pass


def test_handler_rejects_default_client_before_marking_run_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.integration_sync.handlers.lingxing_product_list_sync.get_settings",
        lambda: _settings(real_calls=True),
    )
    handler, _, session = _handler(None)
    run = _run()

    result = handler.execute(run, _interface())

    assert result.status == "failed"
    assert run.error_code == "SYNC_PRODUCTLIST_SERVER_ENVIRONMENT_REQUIRED"
    assert run.started_at is None
    session.commit.assert_called_once_with()


def test_productlist_transport_is_disabled_before_token_and_network() -> None:
    token_provider = FakeTokenProvider()
    network_calls = 0

    def transport(request: httpx.Request) -> httpx.Response:
        nonlocal network_calls
        del request
        network_calls += 1
        return httpx.Response(200, json={})

    client = LingxingReadonlyClient(
        _settings(real_calls=False),
        token_provider=token_provider,
        success_evaluator=product_list_response_succeeded,
        transport=httpx.MockTransport(transport),
    )
    try:
        with pytest.raises(LingxingClientError, match="disabled"):
            client.fetch_product_list_page(
                offset=0,
                length=1000,
                page_no=1,
                source_account_ref="default",
                run_id=str(RUN_ID),
                work_item_id=str(uuid4()),
            )
    finally:
        client.close()

    assert token_provider.get_calls == 0
    assert network_calls == 0


def test_handler_paginates_raw_first_upserts_identity_and_reconciles() -> None:
    client = FakePageClient(
        [
            _envelope(
                page_no=1,
                page_size=2,
                payload={"code": 0, "total": 3, "data": [{"id": "a"}, {"id": "b"}]},
            ),
            _envelope(
                page_no=2,
                page_size=2,
                payload={"code": 0, "total": 3, "data": [{"id": "c"}]},
            ),
        ]
    )
    handler, repository, _ = _handler(client)
    result = handler.execute(_run(), _interface())

    assert result.status == "succeeded"
    assert result.total_captured == 3
    assert result.work_items_count == 2
    assert result.inactive_ids_count == 1
    assert client.calls == [(0, 2, 1), (2, 2, 2)]
    assert repository.add_raw_blob.call_count == 2
    assert repository.add_raw_request_ref.call_count == 2
    raw_ref = repository.add_raw_request_ref.call_args_list[0].args[0]
    assert raw_ref.request_safe_params == {"offset": 0, "length": 2}
    assert set(raw_ref.request_safe_params) == {"offset", "length"}
    assert repository.add_productlist_refs.call_count == 2
    assert repository.add_identity.call_count == 3
    assert repository.add_event.call_count == 0
    assert repository.add_parse_job.call_count == 0
    observed = repository.deactivate_absent_identities.call_args.kwargs["observed_ids"]
    assert observed == {"a", "b", "c"}


def test_handler_commits_raw_before_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakePageClient(
        [_envelope(page_no=1, page_size=2, payload={"code": 0, "total": 1, "data": []})]
    )
    handler, _, session = _handler(client)
    events: list[str] = []
    session.commit.side_effect = lambda: events.append("commit")

    def inspect(payload: object) -> SimpleNamespace:
        del payload
        events.append("parse")
        return SimpleNamespace(values=(), response_count=0, duplicate_count=0)

    monkeypatch.setattr(
        "app.modules.integration_sync.handlers.lingxing_product_list_sync."
        "inspect_productlist_sku_ids",
        inspect,
    )
    handler.execute(_run(), _interface())

    assert events.index("parse") >= 2
    assert events[events.index("parse") - 1] == "commit"


def test_duplicate_ids_fail_with_count_and_without_identity_publication() -> None:
    client = FakePageClient(
        [
            _envelope(
                page_no=1,
                page_size=2,
                payload={"code": 0, "total": 2, "data": [{"id": "a"}, {"id": "a"}]},
            )
        ]
    )
    handler, repository, _ = _handler(client)
    run = _run()
    result = handler.execute(run, _interface())

    assert result.status == "failed"
    assert result.duplicate_ids_detected == 1
    assert run.error_code == "SYNC_PRODUCTLIST_DUPLICATE_ID"
    assert run.error_message == "duplicate_ids_detected=1"
    repository.add_raw_blob.assert_called_once()
    repository.add_productlist_refs.assert_not_called()
    repository.add_identity.assert_not_called()
    repository.deactivate_absent_identities.assert_not_called()


def test_nested_productlist_data_ids_are_supported_without_exposing_values() -> None:
    inspected = inspect_productlist_sku_ids(
        {"code": 0, "productList": {"total": 1, "data": [{"id": "synthetic"}]}}
    )

    assert inspected.response_count == 1
    assert inspected.duplicate_count == 0
    assert len(inspected.values) == 1


def test_execution_routes_productlist_without_lock_or_event_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    service = SyncRunExecutionService(session)
    repository = MagicMock()
    service.repository = repository
    run = _run()
    repository.get_run_for_update.return_value = run
    repository.get_interface.return_value = _interface()
    execute = MagicMock()

    class FakeHandler:
        def __init__(self, handler_session: Session) -> None:
            assert handler_session is session

        def execute(self, handler_run: IntegrationSyncRun, interface: IntegrationInterface) -> None:
            execute(handler_run, interface)

    monkeypatch.setattr(
        "app.modules.integration_sync.execution.LingxingProductListSyncHandler",
        FakeHandler,
    )

    service.execute(RUN_ID)

    execute.assert_called_once_with(run, repository.get_interface.return_value)
    repository.add_lock.assert_not_called()
    repository.add_event.assert_not_called()


@pytest.mark.parametrize(
    ("interface", "schedule_enabled", "error_code"),
    [
        (
            SimpleNamespace(
                id=INTERFACE_ID,
                provider="lingxing",
                interface_key="batchGetProductInfo",
                method="POST",
                endpoint_path="/erp/sc/routing/data/local_inventory/batchGetProductInfo",
                request_kind="id_batch_page",
                outbound_enabled=True,
            ),
            False,
            "SYNC_PRODUCTLIST_ONLY",
        ),
        (_interface(), True, "SYNC_PRODUCTLIST_MANUAL_ONLY"),
    ],
)
def test_manual_trigger_rejects_other_interfaces_and_scheduled_productlist(
    interface: SimpleNamespace,
    schedule_enabled: bool,
    error_code: str,
) -> None:
    session = MagicMock(spec=Session)
    service = IntegrationSyncService(session)
    service.repository = MagicMock()
    service.repository.get_config.return_value = SimpleNamespace(
        id=CONFIG_ID,
        interface_id=INTERFACE_ID,
        source_account_ref="default",
        is_enabled=True,
        schedule_enabled=schedule_enabled,
    )
    service.repository.get_interface.return_value = interface

    with pytest.raises(ApiError) as error:
        service.create_manual_run(
            CONFIG_ID,
            TriggerRequest(reason="synthetic"),
            actor_ref="synthetic-user",
            request_id="synthetic-request",
            account_refs=frozenset({"default"}),
        )

    assert error.value.code == error_code
    service.repository.add_run.assert_not_called()


def test_productlist_manual_trigger_writes_run_without_unapproved_event() -> None:
    session = MagicMock(spec=Session)
    service = IntegrationSyncService(session)
    service.repository = MagicMock()
    service.repository.get_config.return_value = SimpleNamespace(
        id=CONFIG_ID,
        interface_id=INTERFACE_ID,
        source_account_ref="default",
        is_enabled=True,
        schedule_enabled=False,
    )
    service.repository.get_interface.return_value = _interface()
    service.repository.find_run_by_idempotency.return_value = None

    def add_run(run: IntegrationSyncRun) -> IntegrationSyncRun:
        run.id = RUN_ID
        return run

    service.repository.add_run.side_effect = add_run
    created = service.create_manual_run(
        CONFIG_ID,
        TriggerRequest(reason="synthetic"),
        actor_ref="synthetic-user",
        request_id="synthetic-request",
        account_refs=frozenset({"default"}),
    )

    assert created.run_id == RUN_ID
    assert created.status.value == "queued"
    service.repository.add_event.assert_not_called()
    session.commit.assert_called_once_with()


def test_scheduler_never_creates_productlist_run() -> None:
    session = MagicMock(spec=Session)
    service = IntegrationSchedulerService(session)
    service.repository = MagicMock()
    service.repository.list_due_configs.return_value = [
        SimpleNamespace(interface_id=INTERFACE_ID, next_run_at=NOW)
    ]
    service.repository.get_interface.return_value = _interface()

    assert service.create_due_runs() == []
    service.repository.add_run.assert_not_called()
    service.repository.add_event.assert_not_called()
    session.commit.assert_called_once_with()


def test_productlist_logs_only_safe_aggregates(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.integration_sync.product_list")
    client = FakePageClient(
        [_envelope(page_no=1, page_size=1, payload={"code": 0, "total": 0, "data": []})]
    )
    handler, _, _ = _handler(client, page_size=1)

    handler.execute(_run(), _interface())

    assert SYNTHETIC_ACCESS not in caplog.text
    assert "productlist_sync_succeeded" in caplog.text

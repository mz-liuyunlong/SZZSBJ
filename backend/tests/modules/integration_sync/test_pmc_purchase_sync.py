from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from pydantic import JsonValue
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.integrations.lingxing.client import LingxingRawEnvelope
from app.integrations.lingxing.pmc_purchase_contracts import (
    PURCHASE_ORDER_ENDPOINT,
    PURCHASE_PLAN_ENDPOINT,
    RECEIPT_ORDER_ENDPOINT,
)
from app.modules.integration_sync.execution import SyncRunExecutionService
from app.modules.integration_sync.handlers.lingxing_pmc_purchase_sync import (
    PMC_PURCHASE_HANDLERS,
    LingxingPmcPurchaseSyncHandler,
    LingxingPurchaseOrderListSyncHandler,
    LingxingPurchasePlanListSyncHandler,
    LingxingPurchaseReceiptOrderListSyncHandler,
)
from app.modules.integration_sync.models import (
    DataLineage,
    IntegrationInterface,
    IntegrationSyncRun,
    IntegrationSyncRunWorkItem,
    ParseJob,
)
from app.modules.integration_sync.pmc_purchase_catalog import PMC_PURCHASE_SPECS_BY_INTERFACE_KEY
from app.modules.integration_sync.repository import RECOVERABLE_INTERFACE_KEYS
from app.modules.integration_sync.schemas import TriggerRequest
from app.modules.integration_sync.service import IntegrationSyncService
from app.modules.pmc_purchase.models import (
    LingxingPurchaseOrderItemOds,
    LingxingPurchaseOrderOds,
    LingxingPurchasePlanOds,
    LingxingReceiptOrderItemOds,
    LingxingReceiptOrderOds,
)

RUN_ID = UUID("00000000-0000-0000-0000-00000000d001")
CONFIG_ID = UUID("00000000-0000-0000-0000-00000000d002")
INTERFACE_ID = UUID("00000000-0000-0000-0000-00000000d003")
POLICY_ID = UUID("00000000-0000-0000-0000-00000000d004")
BLOB_ID = UUID("00000000-0000-0000-0000-00000000d005")
NOW = datetime(2026, 9, 19, tzinfo=UTC)
WINDOW_START = datetime(2026, 8, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 8, 31, tzinfo=UTC)


class FakePageClient:
    def __init__(self, envelopes: list[LingxingRawEnvelope]) -> None:
        self.envelopes = envelopes
        self.calls: list[dict[str, object]] = []

    def fetch_pmc_purchase_page(self, **kwargs: object) -> LingxingRawEnvelope:
        self.calls.append(kwargs)
        return self.envelopes.pop(0)


def _envelope(
    api_path: str, *, page_no: int, page_size: int, payload: JsonValue, success: bool = True
) -> LingxingRawEnvelope:
    return LingxingRawEnvelope(
        api_path=api_path,  # type: ignore[arg-type]
        request_body_json={"offset": (page_no - 1) * page_size, "length": page_size},
        response_json=payload,
        response_code=200,
        is_success=success,
        pulled_at=NOW,
        page_no=page_no,
        page_size=page_size,
        object_type="pmc_purchase_test",
        trace_id=str(RUN_ID),
        run_id=str(RUN_ID),
        batch_id=str(uuid4()),
        attempt_no=1,
    )


def _run(interface_key: str, *, with_window: bool = True) -> IntegrationSyncRun:
    return IntegrationSyncRun(
        id=RUN_ID,
        config_id=CONFIG_ID,
        interface_id=INTERFACE_ID,
        provider="lingxing",
        interface_key=interface_key,
        source_account_ref="primary",
        trigger_type="manual",
        status="queued",
        window_start=WINDOW_START if with_window else None,
        window_end=WINDOW_END if with_window else None,
        work_items_total=0,
        work_items_succeeded=0,
        work_items_failed=0,
        records_seen=0,
        records_written=0,
    )


def _interface(interface_key: str, *, outbound: bool = True) -> IntegrationInterface:
    spec = PMC_PURCHASE_SPECS_BY_INTERFACE_KEY[interface_key]
    return IntegrationInterface(
        id=INTERFACE_ID,
        provider="lingxing",
        interface_key=interface_key,
        method="POST",
        endpoint_path=spec.endpoint_path,
        request_kind="offset_page",
        handler_key=spec.handler_key,
        outbound_enabled=outbound,
    )


class Captured:
    def __init__(self) -> None:
        self.work_items: list[IntegrationSyncRunWorkItem] = []
        self.ods: list[object] = []
        self.parse_jobs: list[ParseJob] = []
        self.lineage: list[DataLineage] = []
        self.raw_refs: list[object] = []


def _handler(
    handler_cls: type[LingxingPmcPurchaseSyncHandler],
    client: FakePageClient | None,
    *,
    page_size: int = 2,
    run: IntegrationSyncRun | None = None,
) -> tuple[LingxingPmcPurchaseSyncHandler, MagicMock, Captured]:
    session = MagicMock(spec=Session)
    handler = handler_cls(session, client=client)
    repository = MagicMock()
    handler.repository = repository
    captured = Captured()
    repository.get_config.return_value = SimpleNamespace(
        is_enabled=True, schedule_enabled=False, page_size=page_size, max_pages=5
    )
    repository.get_retention_policy.return_value = SimpleNamespace(id=POLICY_ID)
    repository.find_blob_by_hash.return_value = SimpleNamespace(id=BLOB_ID)
    repository.add_raw_request_ref.side_effect = lambda ref: captured.raw_refs.append(ref) or ref
    repository.get_raw_request_ref_for_work_item.return_value = SimpleNamespace(
        id=uuid4(), raw_blob_id=BLOB_ID
    )
    repository.add_work_items.side_effect = lambda items: captured.work_items.extend(items) or items
    repository.add_ods_records.side_effect = lambda rows: captured.ods.extend(rows)
    repository.add_parse_job.side_effect = lambda job: captured.parse_jobs.append(job) or job
    repository.add_lineage.side_effect = lambda rows: captured.lineage.extend(rows) or list(rows)
    if run is not None:
        repository.get_run_for_update.return_value = run
        repository.get_work_item_for_update.side_effect = lambda run_id, work_id: next(
            (w for w in captured.work_items if w.id == work_id), None
        )
    return handler, repository, captured


# --- happy paths -----------------------------------------------------------------------


def test_plan_sync_paginates_with_total_and_writes_ods_and_lineage() -> None:
    plans = [{"plan_sn": f"PP{i}", "status": 2, "quantity_plan": i} for i in range(3)]
    client = FakePageClient(
        [
            _envelope(
                PURCHASE_PLAN_ENDPOINT,
                page_no=1,
                page_size=2,
                payload={"code": 0, "total": 3, "data": plans[:2]},
            ),
            _envelope(
                PURCHASE_PLAN_ENDPOINT,
                page_no=2,
                page_size=2,
                payload={"code": 0, "total": 3, "data": plans[2:]},
            ),
        ]
    )
    run = _run("purchasePlanList")
    handler, _, captured = _handler(LingxingPurchasePlanListSyncHandler, client)

    result = handler.execute(run, _interface("purchasePlanList"))

    assert result.status == "succeeded"
    assert result.headers_written == 3 and result.lines_written == 0
    assert run.records_seen == 3 and run.records_written == 3
    assert run.work_items_total == 2 and run.work_items_succeeded == 2
    assert [call["offset"] for call in client.calls] == [0, 2]
    assert all(call["start_date"] == date(2026, 8, 1) for call in client.calls)
    assert all(call["end_date"] == date(2026, 8, 31) for call in client.calls)
    assert all(call["date_dimension"] == "update_time" for call in client.calls)
    assert captured.work_items[0].request_safe_params == {
        "offset": 0,
        "length": 2,
        "start_date": "2026-08-01",
        "end_date": "2026-08-31",
    }
    assert all(isinstance(row, LingxingPurchasePlanOds) for row in captured.ods)
    assert [row.plan_sn for row in captured.ods] == ["PP0", "PP1", "PP2"]
    assert [row.source_item_ordinal for row in captured.ods] == [0, 1, 0]
    assert len(captured.parse_jobs) == 2
    assert all(
        job.target_layer == "DWD" and job.status == "succeeded" for job in captured.parse_jobs
    )
    assert len(captured.lineage) == 3
    assert {entry.target_table for entry in captured.lineage} == {"ods_lingxing_purchase_plans"}
    assert captured.lineage[0].source_path == "$.data[0]"
    assert captured.lineage[2].source_path == "$.data[0]"
    assert all(entry.raw_blob_id == BLOB_ID for entry in captured.lineage)
    assert "quality" in (run.error_message or "")


def test_order_sync_stops_on_short_page_without_total_and_splits_lines() -> None:
    orders = [
        {"order_sn": "PO1", "quantity_total": 5, "item_list": [{"id": 1, "quantity_plan": 5}]},
        {"order_sn": "PO2", "quantity_total": 4, "item_list": [{"id": 2, "quantity_plan": 4}]},
        {
            "order_sn": "PO3",
            "quantity_total": 3,
            "item_list": [{"id": 3, "quantity_plan": 1}, {"id": 4, "quantity_plan": 2}],
        },
    ]
    client = FakePageClient(
        [
            _envelope(
                PURCHASE_ORDER_ENDPOINT,
                page_no=1,
                page_size=2,
                payload={"code": 0, "data": orders[:2]},
            ),
            _envelope(
                PURCHASE_ORDER_ENDPOINT,
                page_no=2,
                page_size=2,
                payload={"code": 0, "data": orders[2:]},
            ),
        ]
    )
    run = _run("purchaseOrderList")
    handler, _, captured = _handler(LingxingPurchaseOrderListSyncHandler, client)

    result = handler.execute(run, _interface("purchaseOrderList"))

    assert result.status == "succeeded"
    assert result.headers_written == 3 and result.lines_written == 4
    assert len(client.calls) == 2  # short second page terminates without a total
    headers = [row for row in captured.ods if isinstance(row, LingxingPurchaseOrderOds)]
    lines = [row for row in captured.ods if isinstance(row, LingxingPurchaseOrderItemOds)]
    assert [row.order_sn for row in headers] == ["PO1", "PO2", "PO3"]
    assert [(row.order_sn, row.item_id, row.line_ordinal) for row in lines] == [
        ("PO1", "1", 0),
        ("PO2", "2", 0),
        ("PO3", "3", 0),
        ("PO3", "4", 1),
    ]
    assert [entry.target_field for entry in captured.lineage].count("item_id") == 4
    assert [entry.source_path for entry in captured.lineage if entry.target_field == "item_id"][
        -1
    ] == ("$.data[0].item_list[1]")
    assert result.quality.header_line_mismatches == 0


def test_receipt_sync_reads_nested_list_and_skips_duplicate_keys_across_pages() -> None:
    receipt = {"order_sn": "RC1", "business_order_sn": "PO1", "item_list": [{"order_item_id": 1}]}
    client = FakePageClient(
        [
            _envelope(
                RECEIPT_ORDER_ENDPOINT,
                page_no=1,
                page_size=1,
                payload={"code": 0, "data": {"total": 2, "list": [receipt]}},
            ),
            _envelope(
                RECEIPT_ORDER_ENDPOINT,
                page_no=2,
                page_size=1,
                payload={"code": 0, "data": {"total": 2, "list": [receipt]}},
            ),
        ]
    )
    run = _run("purchaseReceiptOrderList")
    handler, _, captured = _handler(
        LingxingPurchaseReceiptOrderListSyncHandler, client, page_size=1
    )

    result = handler.execute(run, _interface("purchaseReceiptOrderList"))

    assert result.status == "succeeded"
    assert result.headers_written == 1 and result.lines_written == 1
    assert result.duplicates_skipped == 1
    assert client.calls[0]["date_dimension"] == 4  # date_type=4: update time (Owner 2026-09-21)
    assert isinstance(captured.ods[0], LingxingReceiptOrderOds)
    assert isinstance(captured.ods[1], LingxingReceiptOrderItemOds)
    assert captured.ods[1].order_item_id == "1"
    assert captured.parse_jobs[1].records_rejected == 1
    assert captured.lineage[0].source_path == "$.data.list[0]"


# --- failures --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda run, iface: setattr(run, "trigger_type", "schedule"),
            "SYNC_PURCHASE_EXECUTION_NOT_AUTHORIZED",
        ),
        (
            lambda run, iface: setattr(iface, "outbound_enabled", False),
            "SYNC_PURCHASE_EXECUTION_NOT_AUTHORIZED",
        ),
        (
            lambda run, iface: setattr(iface, "handler_key", "lingxing.other.v1"),
            "SYNC_PURCHASE_EXECUTION_NOT_AUTHORIZED",
        ),
        (lambda run, iface: setattr(run, "window_start", None), "SYNC_PURCHASE_WINDOW_REQUIRED"),
        (
            lambda run, iface: setattr(run, "window_end", datetime(2026, 12, 31, tzinfo=UTC)),
            "SYNC_PURCHASE_WINDOW_INVALID",
        ),
    ],
)
def test_preflight_rejections_fail_run_without_calling_provider(mutate, expected: str) -> None:
    client = FakePageClient([])
    run = _run("purchasePlanList")
    interface = _interface("purchasePlanList")
    mutate(run, interface)
    handler, _, _ = _handler(LingxingPurchasePlanListSyncHandler, client)

    result = handler.execute(run, interface)

    assert result.status == "failed"
    assert run.error_code == expected
    assert client.calls == []


def test_config_disabled_or_scheduled_is_manual_only() -> None:
    run = _run("purchasePlanList")
    handler, repository, _ = _handler(LingxingPurchasePlanListSyncHandler, FakePageClient([]))
    repository.get_config.return_value = SimpleNamespace(
        is_enabled=True, schedule_enabled=True, page_size=2, max_pages=5
    )
    result = handler.execute(run, _interface("purchasePlanList"))
    assert result.status == "failed" and run.error_code == "SYNC_PURCHASE_MANUAL_ONLY"


def test_total_change_and_parse_failure_mark_work_item_failed() -> None:
    client = FakePageClient(
        [
            _envelope(
                PURCHASE_PLAN_ENDPOINT,
                page_no=1,
                page_size=1,
                payload={"code": 0, "total": 3, "data": [{"plan_sn": "A"}]},
            ),
            _envelope(
                PURCHASE_PLAN_ENDPOINT,
                page_no=2,
                page_size=1,
                payload={"code": 0, "total": 9, "data": [{"plan_sn": "B"}]},
            ),
        ]
    )
    run = _run("purchasePlanList")
    handler, _, captured = _handler(
        LingxingPurchasePlanListSyncHandler, client, page_size=1, run=run
    )
    result = handler.execute(run, _interface("purchasePlanList"))
    assert result.status == "failed" and run.error_code == "SYNC_PURCHASE_TOTAL_CHANGED"
    assert captured.work_items[-1].status == "failed"
    assert run.work_items_failed == 1

    bad = FakePageClient(
        [
            _envelope(
                PURCHASE_PLAN_ENDPOINT,
                page_no=1,
                page_size=1,
                payload={"code": 0, "data": [{"sku": "no key"}]},
            )
        ]
    )
    run2 = _run("purchasePlanList")
    handler2, _, _ = _handler(LingxingPurchasePlanListSyncHandler, bad, page_size=1, run=run2)
    result2 = handler2.execute(run2, _interface("purchasePlanList"))
    assert result2.status == "failed" and run2.error_code == "SYNC_PURCHASE_BUSINESS_KEY_MISSING"


def test_provider_failure_envelope_fails_run_with_provider_code() -> None:
    client = FakePageClient(
        [
            _envelope(
                PURCHASE_ORDER_ENDPOINT,
                page_no=1,
                page_size=2,
                payload={"code": 500, "message": "boom"},
                success=False,
            )
        ]
    )
    run = _run("purchaseOrderList")
    handler, _, captured = _handler(LingxingPurchaseOrderListSyncHandler, client, run=run)
    result = handler.execute(run, _interface("purchaseOrderList"))
    assert result.status == "failed" and run.error_code == "SYNC_PURCHASE_RESPONSE_FAILED"
    assert len(captured.raw_refs) == 1  # the failed response is still retained in ODS raw


def test_default_client_requires_production_environment() -> None:
    run = _run("purchasePlanList")
    handler, _, _ = _handler(LingxingPurchasePlanListSyncHandler, None)
    result = handler.execute(run, _interface("purchasePlanList"))
    assert result.status == "failed"
    assert run.error_code in {
        "SYNC_PURCHASE_SERVER_ENVIRONMENT_REQUIRED",
        "SYNC_PURCHASE_CONFIG_INVALID",
    }


# --- wiring ---------------------------------------------------------------------------


def test_handlers_are_registered_for_dispatch_and_recovery() -> None:
    assert set(PMC_PURCHASE_HANDLERS) == set(PMC_PURCHASE_SPECS_BY_INTERFACE_KEY)
    for key, handler in PMC_PURCHASE_HANDLERS.items():
        assert handler.handler_key == PMC_PURCHASE_SPECS_BY_INTERFACE_KEY[key].handler_key
        assert key in RECOVERABLE_INTERFACE_KEYS
    assert "productList" in RECOVERABLE_INTERFACE_KEYS


def test_execution_service_dispatches_purchase_runs_to_the_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    service = SyncRunExecutionService(session)
    run = _run("purchaseOrderList")
    interface = _interface("purchaseOrderList")
    repository = MagicMock()
    repository.get_run_for_update.return_value = run
    repository.get_interface.return_value = interface
    service.repository = repository
    executed: list[tuple[IntegrationSyncRun, IntegrationInterface]] = []

    class StubHandler:
        handler_key = interface.handler_key

        def __init__(self, session: Session) -> None:
            del session

        def execute(self, run: IntegrationSyncRun, interface: IntegrationInterface) -> None:
            executed.append((run, interface))

    monkeypatch.setitem(PMC_PURCHASE_HANDLERS, "purchaseOrderList", StubHandler)  # type: ignore[misc]
    service.execute(run.id)
    assert executed == [(run, interface)]


def test_manual_trigger_gate_admits_purchase_interfaces_but_not_schedules() -> None:
    session = MagicMock(spec=Session)
    service = IntegrationSyncService(session)
    service.repository = MagicMock()
    interface = _interface("purchaseReceiptOrderList")
    config = SimpleNamespace(
        id=CONFIG_ID,
        interface_id=INTERFACE_ID,
        source_account_ref="primary",
        is_enabled=True,
        schedule_enabled=False,
    )
    service.repository.get_config.return_value = config
    service.repository.get_interface.return_value = interface
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
        account_refs=frozenset({"primary"}),
    )
    assert created.run_id == RUN_ID
    assert created.status.value == "queued"

    config.schedule_enabled = True
    with pytest.raises(ApiError) as scheduled:
        service.create_manual_run(
            CONFIG_ID,
            TriggerRequest(reason="synthetic"),
            actor_ref="synthetic-user",
            request_id="synthetic-request",
            account_refs=frozenset({"primary"}),
        )
    assert scheduled.value.code == "SYNC_PRODUCTLIST_MANUAL_ONLY"

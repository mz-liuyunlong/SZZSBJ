from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy.orm import Session

from app.integrations.lingxing.client import LingxingRawEnvelope
from app.integrations.lingxing.pmc_wfs_contracts import (
    WFS_CARGO_PAGE_ENDPOINT,
    WFS_SHIPPING_LIST_PAGE_ENDPOINT,
)
from app.modules.integration_sync.handlers.lingxing_pmc_wfs_board_sync import (
    PMC_WFS_HANDLERS,
    LingxingPmcWfsBoardSyncHandler,
    LingxingWfsCargoPageSyncHandler,
    LingxingWfsShippingListPageSyncHandler,
)
from app.modules.integration_sync.models import (
    DataLineage,
    IntegrationInterface,
    IntegrationSyncRun,
    IntegrationSyncRunWorkItem,
)
from app.modules.integration_sync.pmc_wfs_catalog import PMC_WFS_SPECS_BY_INTERFACE_KEY
from app.modules.pmc_wfs.lingxing_models import (
    LingxingWfsCargoGoodsOds,
    LingxingWfsCargoOds,
    LingxingWfsShippingListOds,
)
from tests.modules.pmc_wfs.wfs_board_fixtures import CARGOS, SHIPPING_LISTS, page

RUN_ID = UUID("00000000-0000-0000-0000-00000000e001")
CONFIG_ID = UUID("00000000-0000-0000-0000-00000000e002")
INTERFACE_ID = UUID("00000000-0000-0000-0000-00000000e003")
POLICY_ID = UUID("00000000-0000-0000-0000-00000000e004")
BLOB_ID = UUID("00000000-0000-0000-0000-00000000e005")
NOW = datetime(2026, 10, 30, tzinfo=UTC)
WINDOW_START = datetime(2026, 6, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 10, 30, tzinfo=UTC)


class FakePageClient:
    def __init__(self, envelopes: list[LingxingRawEnvelope]) -> None:
        self.envelopes = envelopes
        self.calls: list[dict[str, object]] = []

    def fetch_pmc_wfs_page(self, **kwargs: object) -> LingxingRawEnvelope:
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
        object_type="pmc_wfs_test",
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
    spec = PMC_WFS_SPECS_BY_INTERFACE_KEY[interface_key]
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
        self.lineage: list[DataLineage] = []
        self.raw_refs: list[object] = []


def _handler(
    handler_cls: type[LingxingPmcWfsBoardSyncHandler],
    client: FakePageClient | None,
    *,
    page_size: int = 2,
    run: IntegrationSyncRun | None = None,
) -> tuple[LingxingPmcWfsBoardSyncHandler, MagicMock, Captured]:
    session = MagicMock(spec=Session)
    handler = handler_cls(session, client=client, page_gap_seconds=0)
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
    repository.add_lineage.side_effect = lambda rows: captured.lineage.extend(rows) or list(rows)
    if run is not None:
        repository.get_run_for_update.return_value = run
        repository.get_work_item_for_update.side_effect = lambda run_id, work_id: next(
            (w for w in captured.work_items if w.id == work_id), None
        )
    return handler, repository, captured


def test_handlers_registered_for_both_feeds() -> None:
    assert set(PMC_WFS_HANDLERS) == {"wfsCargoPage", "wfsShippingListPage"}
    assert PMC_WFS_HANDLERS["wfsCargoPage"] is LingxingWfsCargoPageSyncHandler
    assert LingxingWfsCargoPageSyncHandler.handler_key == "lingxing.pmc_wfs.cargo_page.v1"


def test_cargo_sync_paginates_by_total_and_writes_headers_goods_and_lineage() -> None:
    client = FakePageClient(
        [
            _envelope(WFS_CARGO_PAGE_ENDPOINT, page_no=1, page_size=2, payload=page(CARGOS[:2], 3)),
            _envelope(WFS_CARGO_PAGE_ENDPOINT, page_no=2, page_size=2, payload=page(CARGOS[2:], 3)),
        ]
    )
    run = _run("wfsCargoPage")
    handler, _, captured = _handler(LingxingWfsCargoPageSyncHandler, client)

    result = handler.execute(run, _interface("wfsCargoPage"))

    assert result.status == "succeeded"
    assert result.records_written == 3 and result.duplicates_skipped == 0
    assert run.records_seen == 3 and run.records_written == 3
    assert run.work_items_total == 2 and run.work_items_succeeded == 2
    assert [call["offset"] for call in client.calls] == [0, 2]
    assert all(call["start_date"] == date(2026, 6, 1) for call in client.calls)
    assert all(call["end_date"] == date(2026, 10, 30) for call in client.calls)
    assert all(call["extra"] is None for call in client.calls)
    assert captured.work_items[0].request_safe_params == {
        "offset": 0,
        "length": 2,
        "start_time": "2026-06-01",
        "end_time": "2026-10-30",
    }
    headers = [row for row in captured.ods if isinstance(row, LingxingWfsCargoOds)]
    goods = [row for row in captured.ods if isinstance(row, LingxingWfsCargoGoodsOds)]
    assert [h.cargo_id for h in headers] == ["23212872", "23212873", "23212874"]
    assert [h.source_item_ordinal for h in headers] == [0, 1, 0]
    assert [g.cargo_id for g in goods] == ["23212872", "23212873", "23212873"]
    assert goods[1].damaged_qty == 2
    assert len(captured.lineage) == 6
    assert {entry.target_table for entry in captured.lineage} == {
        "ods_lingxing_wfs_cargos",
        "ods_lingxing_wfs_cargo_goods",
    }
    assert captured.lineage[0].source_path == "$.data.records[0]"
    assert captured.lineage[1].source_path == "$.data.records[0].cargo_good_list[0]"
    assert all(entry.raw_blob_id == BLOB_ID for entry in captured.lineage)
    assert all(ref.provider_code == "0" for ref in captured.raw_refs)


def test_shipping_list_sync_single_page_when_total_reached() -> None:
    client = FakePageClient(
        [
            _envelope(
                WFS_SHIPPING_LIST_PAGE_ENDPOINT,
                page_no=1,
                page_size=2,
                payload=page(SHIPPING_LISTS, 2),
            )
        ]
    )
    run = _run("wfsShippingListPage")
    handler, _, captured = _handler(LingxingWfsShippingListPageSyncHandler, client)

    result = handler.execute(run, _interface("wfsShippingListPage"))

    assert result.status == "succeeded" and result.records_written == 2
    assert len(client.calls) == 1
    rows = [row for row in captured.ods if isinstance(row, LingxingWfsShippingListOds)]
    assert [r.shipping_code for r in rows] == ["SP202610160010009", "SP202610170010010"]
    assert rows[0].cargo_codes == ["3292441WFB"]
    assert rows[1].arrival_time == "2026-10-28 00:00:00"


def test_total_change_between_pages_fails_run() -> None:
    client = FakePageClient(
        [
            _envelope(WFS_CARGO_PAGE_ENDPOINT, page_no=1, page_size=2, payload=page(CARGOS[:2], 3)),
            _envelope(WFS_CARGO_PAGE_ENDPOINT, page_no=2, page_size=2, payload=page(CARGOS[2:], 4)),
        ]
    )
    run = _run("wfsCargoPage")
    handler, _, captured = _handler(LingxingWfsCargoPageSyncHandler, client, run=run)

    result = handler.execute(run, _interface("wfsCargoPage"))

    assert result.status == "failed"
    assert run.error_code == "SYNC_WFS_TOTAL_CHANGED"
    assert run.work_items_succeeded == 1 and run.work_items_failed == 1
    assert captured.work_items[1].status == "failed"


def test_missing_total_fails_run() -> None:
    payload = {"code": 0, "data": {"records": CARGOS[:1]}}
    client = FakePageClient(
        [_envelope(WFS_CARGO_PAGE_ENDPOINT, page_no=1, page_size=2, payload=payload)]
    )
    run = _run("wfsCargoPage")
    handler, _, _ = _handler(LingxingWfsCargoPageSyncHandler, client, run=run)

    result = handler.execute(run, _interface("wfsCargoPage"))

    assert result.status == "failed" and run.error_code == "SYNC_WFS_TOTAL_REQUIRED"


def test_duplicate_identity_across_pages_fails_run() -> None:
    client = FakePageClient(
        [
            _envelope(WFS_CARGO_PAGE_ENDPOINT, page_no=1, page_size=2, payload=page(CARGOS[:2], 3)),
            _envelope(WFS_CARGO_PAGE_ENDPOINT, page_no=2, page_size=2, payload=page(CARGOS[:1], 3)),
        ]
    )
    run = _run("wfsCargoPage")
    handler, _, _ = _handler(LingxingWfsCargoPageSyncHandler, client, run=run)

    result = handler.execute(run, _interface("wfsCargoPage"))

    assert result.status == "failed" and run.error_code == "SYNC_WFS_DUPLICATE_IDENTITY"


def test_preflight_rejects_missing_window_and_disabled_interface() -> None:
    handler, _, _ = _handler(LingxingWfsCargoPageSyncHandler, FakePageClient([]))
    run = _run("wfsCargoPage", with_window=False)
    assert handler.execute(run, _interface("wfsCargoPage")).status == "failed"
    assert run.error_code == "SYNC_WFS_WINDOW_REQUIRED"

    handler, _, _ = _handler(LingxingWfsCargoPageSyncHandler, FakePageClient([]))
    run = _run("wfsCargoPage")
    assert handler.execute(run, _interface("wfsCargoPage", outbound=False)).status == "failed"
    assert run.error_code == "SYNC_WFS_EXECUTION_NOT_AUTHORIZED"


def test_transport_failure_marks_work_item_failed() -> None:
    class Boom:
        def fetch_pmc_wfs_page(self, **kwargs: object) -> LingxingRawEnvelope:
            raise RuntimeError("network")

    run = _run("wfsCargoPage")
    handler, _, captured = _handler(LingxingWfsCargoPageSyncHandler, Boom(), run=run)  # type: ignore[arg-type]

    result = handler.execute(run, _interface("wfsCargoPage"))

    assert result.status == "failed" and run.error_code == "SYNC_WFS_TRANSPORT_FAILED"
    assert captured.work_items[0].status == "failed"
    assert captured.ods == []

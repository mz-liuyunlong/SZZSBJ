"""Synthetic-only integration tests; never access Lingxing or a business database."""

from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_optional_principal
from app.core.config import Settings
from app.db.session import get_db_session
from app.integrations.lingxing.client import LingxingReadonlyClient
from app.integrations.lingxing.pmc_domestic_contracts import (
    WAREHOUSE_STATEMENT_ENDPOINT,
    build_pmc_domestic_page_body,
    pmc_domestic_response_succeeded,
)
from app.main import create_app
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.integration_sync.parsers.lingxing_domestic import parse_domestic_page
from app.modules.pmc_domestic.inbound_builder import (
    InboundDataError,
    build_inbound_rows,
)
from app.modules.pmc_domestic.inbound_collector import (
    BATCH_PATH,
    collect_inbound,
    export_inbound_csv,
)
from app.modules.pmc_domestic.inbound_models import DomesticBoardPublication as Pub
from app.modules.pmc_domestic.inbound_models import DomesticInboundBoard as Board
from app.modules.pmc_domestic.inbound_publisher import InboundPublisher
from app.modules.pmc_domestic.inbound_schemas import InboundFilter, InboundQuery
from app.modules.pmc_domestic.inbound_service import InboundReadService

NOW = datetime(2026, 10, 20, 4, tzinfo=UTC)
START, END = date(2026, 10, 1), date(2026, 10, 21)
READ = "page:pmc:domestic-warehouse-board:view"
PREFIX = "/api/pmc/domestic/inbound-batches"


def event(**changes):
    return {
        "statement_id": "180000000000000001",
        "wid": "WH1",
        "order_sn": "IB1",
        "sku": "SKU1",
        "sub_type": "2202",
        "product_qc_num": "100",
        "product_total": "100",
        "ref_order_sn": "PO1",
        "opt_time": "2026-10-10 08:00",
        **changes,
    }


def batch(**changes):
    return {
        "wid": "WH1",
        "wh_name": "惠州仓库",
        "batch_no": "B1",
        "order_sn": "IB1",
        "sku": "SKU1",
        "type": 2202,
        "store_id": "S1",
        "balance_num": 40,
        "source_batch_no": [],
        "delivery_order_sns": ["CR1"],
        "purchase_order_sns": ["PO1"],
        **changes,
    }


def build(events=None, batches=None, **kwargs):
    return build_inbound_rows(
        [event()] if events is None else events,
        [batch()] if batches is None else batches,
        account="account",
        warehouse="WH1",
        **kwargs,
    )


def test_projection_does_not_duplicate_parent_qty_or_guess_shipments():
    rows = build(batches=[batch(), batch(batch_no="B2", store_id="S2", balance_num=0)])
    assert len(rows) == 2
    assert [r["balance_num"] for r in rows] == [40, 0]
    assert all(r["total_inbound_qty"] is None for r in rows)
    assert all(r["parent_inbound_qty"] == 100 for r in rows)
    assert all(r["arrival_business_date"] is None for r in rows)  # timezone not assumed
    assert all("shipped" not in r for r in rows)
    assert rows[0]["id"] == build(batches=[batch()])[0]["id"]


def test_signs_missing_stock_backfill_and_warehouse_type_isolation():
    reverse = event(statement_id="2", product_qc_num="-20", product_total="-20")
    row = build(events=[event(), reverse], batches=[], source_timezone="Asia/Shanghai")[0]
    assert row["parent_inbound_qty"] == 80 and row["balance_num"] is None
    assert row["arrival_business_date"] == "2026-10-10"
    assert row["store_id"] is None
    old = build(events=[], batches=[batch(purchase_in_time="2026-08-01 10:00")])[0]
    assert old["source_kind"] == "batch_backfill" and old["parent_inbound_qty"] is None
    assert build(events=[], batches=[batch(type=2401, order_sn="TF1")]) == []
    assert build(events=[], batches=[batch(wid="WH-OTHER")]) == []


def test_duplicate_conflict_fails_and_arrays_preserved():
    with pytest.raises(InboundDataError, match="DUPLICATE_CONFLICT"):
        build(events=[event(), event(product_total=999)])
    row = build(batches=[batch(), batch()])[0]
    assert row["balance_num"] == 40
    assert row["batch_details"][0]["receipt_order_sns"] == ["CR1"]
    with pytest.raises(InboundDataError):
        build(batches=[batch(balance_num=True)])


def envelope(data, total=None):
    return SimpleNamespace(
        response_json={"code": 0, "data": data, "total": len(data) if total is None else total},
        is_success=True,
        pulled_at=NOW,
    )


def fetch(path, body):
    assert body["wids"] == "WH1"
    if path == BATCH_PATH:
        assert body["show_zero_stock"] == 1
        return envelope([batch()])
    return envelope([event()])


def test_file_export_without_database_config_and_json_roundtrip(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    output = tmp_path / "capture"
    manifest = export_inbound_csv(
        fetch,
        output=output,
        account="account",
        warehouse="WH1",
        start=START,
        end=END,
        source_timezone="Asia/Shanghai",
    )
    assert manifest["complete"] and manifest["files"]["inbound_board_preview.csv"]["rows"] == 1
    with (output / "batch_details.csv").open(encoding="utf-8-sig", newline="") as stream:
        saved = list(csv.DictReader(stream))
    assert json.loads(saved[0]["delivery_order_sns"]) == ["CR1"]
    with pytest.raises(FileExistsError):
        export_inbound_csv(
            fetch, output=output, account="account", warehouse="WH1", start=START, end=END
        )


def test_incomplete_or_wrong_warehouse_does_not_mark_export_complete(tmp_path):
    def incomplete(path, body):
        return envelope([], total=1)

    output = tmp_path / "failed"
    with pytest.raises(InboundDataError, match="INCOMPLETE_PAGE"):
        export_inbound_csv(
            incomplete, output=output, account="account", warehouse="WH1", start=START, end=END
        )
    assert json.loads((output / "manifest.json").read_text())["complete"] is False
    with pytest.raises(InboundDataError, match="WAREHOUSE_MISMATCH"):
        collect_inbound(
            lambda *args: envelope([batch(wid="OTHER")]),
            account="account",
            warehouse="WH1",
            start=START,
            end=END,
        )


def test_window_splitting_and_page_budget():
    windows = []

    def empty(path, body):
        if path != BATCH_PATH:
            windows.append((body["start_date"], body["end_date"]))
        return envelope([])

    collect_inbound(
        empty, account="a", warehouse="WH1", start=date(2026, 8, 1), end=date(2026, 10, 1)
    )
    assert windows == [
        ("2026-08-01", "2026-08-31"),
        ("2026-08-31", "2026-09-30"),
        ("2026-09-30", "2026-10-01"),
    ]
    with pytest.raises(InboundDataError, match="PAGE_LIMIT"):
        collect_inbound(empty, account="a", warehouse="WH1", start=START, end=END, max_pages=1)


def test_shared_client_signed_contract_and_signed_quantity_parser():
    body = build_pmc_domestic_page_body(
        WAREHOUSE_STATEMENT_ENDPOINT, offset=0, length=200, start_date=START, end_date=END
    )
    assert "time_filter_field" not in body
    parsed = parse_domestic_page(
        WAREHOUSE_STATEMENT_ENDPOINT, {"code": 0, "total": 1, "data": [event(product_qc_num="-5")]}
    )
    assert parsed.headers[0].columns["product_qc_num"] == -5
    settings = Settings(
        APP_ENV="test",
        TEST_DATABASE_URL="postgresql+psycopg://test@invalid/test",
        LINGXING_BASE_URL="https://openapi.lingxing.com",
        LINGXING_APP_ID="0123456789abcdef",
        LINGXING_ENABLE_REAL_CALLS=True,
    )

    def send(request):
        assert request.method == "POST"
        assert request.url.path == WAREHOUSE_STATEMENT_ENDPOINT
        assert "sign" in request.url.params
        assert json.loads(request.content)["wids"] == "WH1"
        return httpx.Response(200, json={"code": 0, "data": [], "total": 0})

    client = LingxingReadonlyClient(
        settings,
        token_provider=SimpleNamespace(get_access_token=lambda: SecretStr("synthetic-token")),
        success_evaluator=pmc_domestic_response_succeeded,
        transport=httpx.MockTransport(send),
    )
    try:
        result = client.fetch_inbound_page(
            api_path=WAREHOUSE_STATEMENT_ENDPOINT,
            body={**body, "wids": "WH1"},
            source_account_ref="a",
            run_id="run",
            work_item_id="work",
        )
        assert result.is_success
    finally:
        client.close()


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Pub.__table__.create(engine)
    Board.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def save(session, rows, account="account"):
    identity = InboundPublisher(session)._save(
        account, "WH1", rows, uuid4(), [uuid4()], START, END, NOW
    )
    session.commit()
    return identity


def test_read_model_stats_version_switch_isolation_and_stable_details(session):
    rows = build(batches=[batch(), batch(batch_no="B2", store_id="S2", balance_num=60)])
    first = save(session, rows)
    service = InboundReadService(session, NOW)
    data, meta = service.list(InboundQuery(), frozenset({"account"}))
    assert data.total == 2 and meta.publication_ids == [first]
    assert data.items[0].days_in_warehouse is None
    summary, _ = service.summary(InboundFilter(), frozenset({"account"}))
    assert summary.total_inbound_qty == 100 and summary.balance_qty == 100
    assert summary.inbound_order_count == 1
    assert service.list(InboundQuery(), frozenset({"other"}))[0].total == 0
    assert (
        service.list(InboundQuery(purchase_order_sn=["PO10"]), frozenset({"account"}))[0].total == 0
    )
    assert (
        service.list(InboundQuery(purchase_order_sn=["PO1"]), frozenset({"account"}))[0].total == 2
    )
    latest = save(session, build(batches=[batch(balance_num=0)]))
    # One request stays pinned; a new request sees the newly published version.
    assert service.list(InboundQuery(), frozenset({"account"}))[1].publication_ids == [first]
    service = InboundReadService(session, NOW)
    data, meta = service.list(InboundQuery(), frozenset({"account"}))
    assert data.total == 1 and data.items[0].balance_num == 0 and meta.publication_ids == [latest]
    assert session.scalar(select(Pub.is_current).where(Pub.id == first)) is False
    assert service.detail(UUID(rows[0]["id"]), frozenset({"account"}))[0].publication_id == latest
    with pytest.raises(Exception) as error:
        service.detail(UUID(rows[0]["id"]), frozenset({"other"}))
    assert error.value.status_code == 404


def test_unpublished_is_different_from_successful_empty_publication(session):
    service = InboundReadService(session, NOW)
    assert service.list(InboundQuery(), frozenset({"account"}))[1].data_status == "not_published"
    save(session, [])
    service = InboundReadService(session, NOW)
    data, meta = service.list(InboundQuery(), frozenset({"account"}))
    assert data.total == 0 and meta.data_status == "ready"


def test_route_auth_scope_validation_and_old_contract_retained(monkeypatch):
    application = create_app()
    paths = application.openapi()["paths"]
    assert PREFIX in paths and "/api/pmc/domestic/batches" in paths
    application.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    application.dependency_overrides[get_optional_principal] = lambda: None
    client = TestClient(application)
    assert client.get(PREFIX).status_code == 401
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="test", permissions=frozenset()
    )
    assert client.get(PREFIX).status_code == 403
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="test", permissions=frozenset({READ})
    )
    application.dependency_overrides[require_source_account_scope] = lambda: frozenset({"account"})
    for params in (
        {"page_size": 201},
        {"unexpected": "x"},
        {"inbound_from": "2026-10-20", "inbound_to": "2026-10-01"},
    ):
        assert client.get(PREFIX, params=params).status_code == 422

    from app.modules.pmc_domestic.inbound_schemas import InboundList, InboundMeta

    def empty_list(self, query, accounts):
        assert accounts == frozenset({"account"})
        return InboundList(items=[], total=0), InboundMeta(
            data_status="not_published",
            as_of=date(2026, 10, 20),
            total=0,
        )

    monkeypatch.setattr(InboundReadService, "list", empty_list)
    response = client.get(PREFIX)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"success", "data", "error", "meta", "request_id"}
    assert body["meta"]["data_status"] == "not_published"
    assert body["meta"]["source_objects"] == [Board.__tablename__, Pub.__tablename__]


def test_file_settings_do_not_require_or_inherit_database_permissions(monkeypatch):
    from app.integrations.lingxing.file_settings import LingxingFileSettings

    for key in ("APP_ENV", "DATABASE_URL", "TEST_DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    settings = LingxingFileSettings(LINGXING_APP_ID="synthetic", LINGXING_APP_SECRET="secret")
    assert settings.lingxing_enable_real_calls is False
    assert settings.lingxing_enable_token_requests is False
    assert "database_url" not in settings.model_fields
    with pytest.raises(ValueError):
        LingxingFileSettings(
            LINGXING_APP_ID="a",
            LINGXING_APP_SECRET="s",
            LINGXING_BASE_URL="https://example.invalid",
        )


def test_new_tables_compile_as_postgresql_without_running_a_migration():
    from sqlalchemy.dialects.postgresql import dialect
    from sqlalchemy.schema import CreateTable

    from app.db.model_registry import register_productlist_sync_models
    from app.modules.pmc_domestic.inbound_models import DomesticWarehouseStatement

    register_productlist_sync_models()
    for model in (DomesticWarehouseStatement, Pub, Board):
        ddl = str(CreateTable(model.__table__).compile(dialect=dialect()))
        assert model.__tablename__ in ddl
        assert "UUID" in ddl and "JSONB" in ddl


@pytest.mark.parametrize("interface_key", ["domesticBatchDetailList", "domesticWarehouseStatement"])
def test_scoped_governed_sync_keeps_warehouse_in_request_and_audit(interface_key):
    from app.modules.integration_sync.handlers.lingxing_pmc_domestic_sync import (
        PMC_DOMESTIC_HANDLERS,
    )

    session = MagicMock()
    handler = PMC_DOMESTIC_HANDLERS[interface_key](session, warehouse_id="HU_TEST")
    run = SimpleNamespace(id=uuid4(), source_account_ref="account", work_items_total=0)
    window = (
        (date(2026, 10, 1), date(2026, 10, 20))
        if interface_key == "domesticWarehouseStatement"
        else (None, None)
    )
    work = handler._start_work_item(run, 1, 0, 200, window)
    assert work.request_safe_params["wids"] == "HU_TEST"
    if interface_key == "domesticBatchDetailList":
        assert work.request_safe_params["show_zero_stock"] == 1
    handler._start_work_item = MagicMock(return_value=work)
    handler._persist_raw_response = MagicMock()
    handler._publish_page = MagicMock(return_value=(0, 0))
    handler._succeed = MagicMock(return_value="success")
    client = MagicMock()
    client.fetch_inbound_page.return_value = SimpleNamespace(
        response_json={"code": 0, "total": 0, "data": []}, is_success=True, pulled_at=NOW
    )
    assert handler._execute_pages(run, client, MagicMock(), window, 200, 1) == "success"
    body = client.fetch_inbound_page.call_args.kwargs["body"]
    assert body["wids"] == "HU_TEST"
    assert not client.fetch_pmc_domestic_page.called


def test_scoped_governed_sync_rejects_other_warehouse_before_ods_write():
    from app.modules.integration_sync.handlers.lingxing_pmc_domestic_sync import (
        PMC_DOMESTIC_HANDLERS,
        PmcDomesticSyncError,
    )

    session = MagicMock()
    handler = PMC_DOMESTIC_HANDLERS["domesticBatchDetailList"](session, warehouse_id="HU_TEST")
    parsed = SimpleNamespace(headers=[SimpleNamespace(columns={"source_warehouse_id": "OTHER"})])
    with pytest.raises(PmcDomesticSyncError, match="WAREHOUSE_MISMATCH"):
        handler._publish_page(
            SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4()), NOW, parsed, set()
        )
    assert not session.add.called


def test_scoped_governed_sync_rejects_a_missing_provider_total():
    from app.modules.integration_sync.handlers.lingxing_pmc_domestic_sync import (
        PMC_DOMESTIC_HANDLERS,
    )

    handler = PMC_DOMESTIC_HANDLERS["domesticBatchDetailList"](MagicMock(), warehouse_id="HU_TEST")
    handler._start_work_item = MagicMock(return_value=SimpleNamespace(id=uuid4()))
    handler._persist_raw_response = MagicMock()
    handler._fail_run = MagicMock(return_value="failed")
    handler._publish_page = MagicMock()
    client = MagicMock()
    client.fetch_inbound_page.return_value = SimpleNamespace(
        response_json={"code": 0, "data": []}, is_success=True, pulled_at=NOW
    )
    result = handler._execute_pages(
        SimpleNamespace(id=uuid4(), source_account_ref="account"),
        client,
        MagicMock(),
        (None, None),
        200,
        1,
    )
    assert result == "failed"
    assert handler._fail_run.call_args.args[2] == "SYNC_DOMESTIC_TOTAL_REQUIRED"
    assert not handler._publish_page.called


def test_trace_identifiers_are_text_before_crossing_json_boundary():
    row = build_inbound_rows(
        [event(statement_id=180000000000000001)], [batch()], account="account", warehouse="WH1"
    )
    assert row[0]["inbound_events"][0]["statement_id"] == "180000000000000001"


def test_ods_ingestion_preserves_lineage_without_mislabeling_dwd_parse_job():
    from app.modules.integration_sync.handlers.lingxing_pmc_domestic_sync import (
        PMC_DOMESTIC_HANDLERS,
    )

    session = MagicMock()
    handler = PMC_DOMESTIC_HANDLERS["domesticBatchDetailList"](session, warehouse_id="WH1")
    handler.repository = MagicMock()
    ref = SimpleNamespace(id=uuid4(), raw_blob_id=uuid4())
    handler.repository.get_raw_request_ref_for_work_item.return_value = ref
    run = SimpleNamespace(
        id=uuid4(), source_account_ref="account", work_items_succeeded=0, records_written=0
    )
    work = SimpleNamespace(id=uuid4())
    parsed = parse_domestic_page(BATCH_PATH, {"code": 0, "total": 1, "data": [batch()]})
    assert handler._publish_page(run, work, NOW, parsed, set()) == (1, 0)
    assert not handler.repository.add_parse_job.called
    record = handler.repository.add_ods_records.call_args.args[0][0]
    lineage = handler.repository.add_lineage.call_args.args[0][0]
    assert lineage.parse_job_id is None
    assert lineage.raw_request_ref_id == ref.id
    assert lineage.target_record_id == str(record.id)
    assert lineage.target_table == "ods_lingxing_domestic_batches"
    assert lineage.transform_key and lineage.transform_version
    assert run.records_written == 1

"""结算利润 PR-2：发货单 / 发货单明细 / 销售出库单同步。不连接口，全部合成数据。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from pydantic import JsonValue, ValidationError
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import Settings, SettingsError, get_test_database_url
from app.integrations.lingxing.client import LingxingRawEnvelope
from app.modules.data_pages.models import LingxingStoreDimension
from app.modules.integration_sync.catalog import IntegrationCatalogService
from app.modules.integration_sync.execution import FIN_SHIPPING_HANDLERS, SyncRunExecutionService
from app.modules.integration_sync.fin_shipping_catalog import (
    FIN_SHIPPING_DETAIL_SYNC_SPEC,
    FIN_SHIPPING_LIST_SYNC_SPEC,
    FIN_SHIPPING_SYNC_SPECS,
    FIN_WMS_OUTBOUND_SYNC_SPEC,
    FinShippingSyncInterfaceSpec,
)
from app.modules.integration_sync.handlers.lingxing_fin_shipping_sync import (
    LingxingFinShippingDetailSyncHandler,
    LingxingFinShippingListSyncHandler,
    parse_shipping_detail_items,
    parse_shipping_list_row,
    pending_detail_codes,
)
from app.modules.integration_sync.handlers.lingxing_fin_sync_base import (
    FinSyncError,
    FinSyncResult,
    lx_datetime,
    response_total,
    rolling_window,
    scrub_pii,
)
from app.modules.integration_sync.handlers.lingxing_fin_wms_outbound_sync import (
    LingxingFinWmsOutboundSyncHandler,
    parse_wms_order_row,
)
from app.modules.integration_sync.models import (
    ApiRawBlob,
    ApiRawRequestRef,
    IntegrationInterface,
    IntegrationSyncConfig,
    IntegrationSyncRun,
    IntegrationSyncRunWorkItem,
)
from app.modules.integration_sync.product_info_runner import ProductInfoOneTimeRunError
from app.modules.settlement_profit.models import (
    FinShippingDetailItem,
    FinShippingList,
    FinWmsOutboundOrder,
)

NOW = datetime(2026, 11, 20, 2, 0, tzinfo=UTC)
STORE_A = "990000000000000001"
STORE_B = "990000000000000002"
ACCOUNT = "primary"


# --------------------------------------------------------------------------- 合成数据


def shipping_row(
    code: str, *, status: int = 2, delivery: str = "2026-11-10 11:26"
) -> dict[str, Any]:
    return {
        "id": "1",
        "shippingListCode": code,
        "warehouseId": 28030,
        "platformCode": "10008",
        "logisticsProviderId": "6899",
        "logisticsProviderName": "合成物流商",
        "logisticsChannelName": "合成渠道",
        "creator": "合成人",
        "gmtCreate": "2026-11-01 09:00",
        "deliveryTime": delivery,
        "shippingListStatus": status,
        "shippingListStatusDesc": "已发货" if status == 2 else "待发货",
        "goodExtDetails": [{"msku": "SYN-001", "storeId": STORE_A, "shipmentsNum": "10"}],
    }


def detail_item(msku: str, *, qty: int = 10, purchase: str = "3.00") -> dict[str, Any]:
    return {
        "msku": msku,
        "sku": msku.split("-")[0],
        "gtin": "00000000000001",
        "storeId": int(STORE_A),
        "deliveryNum": qty,
        "purchasePrice": purchase,
        "headStockPrice": "1.50",
        "perFirstletCost": "2.00",
        "perFirstletActual": "2.00",
        "perFirstletExpected": "2.50",
        "perTax": "0.00",
        "wfsStockPrice": "6.50",
        "otherCost": "20.00",
        "transportationCost": "0.00",
        "totalCostCurrency": "￥",
        "logisticsWay": "合成-卡派",
        "headFeeTypeStr": "按SKU数量",
        "valueSourceStr": "实际费用",
    }


def wms_row(order_no: str, *, fee: str = "4.20", status: int = 3) -> dict[str, Any]:
    return {
        "wo_number": order_no,
        "sid": int(STORE_A),
        "platform_order_no": [f"P{order_no}"],
        "status": status,
        "status_name": "已出库" if status == 3 else "已截单",
        "logistics_freight": fee,
        "logistics_freight_currency_code": "USD",
        "delivered_at": "2026-11-12 10:00:00",
        "consignee": "某人",
        "consignee_phone": "000",
        "address_line": "somewhere",
        "order_buyer_notes": "note",
        "product_info": [
            {
                "wod_id": 1,
                "seller_sku": "SYN-001",
                "sku": "SYN",
                "count": 2,
                "apportion_freight": fee,
                "stock_cost": "12.00",
                "customization": "secret",
            }
        ],
        "create_at": "2026-11-11 10:00:00",
        "update_at": "2026-11-12 10:00:00",
    }


def list_body(rows: list[dict[str, Any]], total: int | None = None) -> dict[str, JsonValue]:
    return {
        "code": 0,
        "message": "success",
        "data": {"list": rows, "total": str(len(rows) if total is None else total)},
    }


def detail_body(items: list[dict[str, Any]] | None) -> dict[str, JsonValue]:
    return {"code": 0, "message": "success", "data": {"firstLetListResponseList": items}}


def wms_body(rows: list[dict[str, Any]], total: int | None = None) -> dict[str, JsonValue]:
    return {
        "code": 0,
        "message": "success",
        "data": rows,
        "total": len(rows) if total is None else total,
    }


class FakeLingxing:
    """按 (store, offset/page) 返回合成页；detail 按发货单号返回。"""

    def __init__(self) -> None:
        self.list_pages: dict[tuple[str, int], JsonValue] = {}
        self.details: dict[str, JsonValue] = {}
        self.wms_pages: dict[tuple[str, int], JsonValue] = {}
        self.calls: list[tuple[str, ...]] = []

    def _envelope(
        self, path: str, body: JsonValue, kw: dict[str, Any], page: int
    ) -> LingxingRawEnvelope:
        if isinstance(body, str):
            raise RuntimeError(body)
        return LingxingRawEnvelope(
            api_path=path,  # type: ignore[arg-type]
            response_json=body,
            response_code=200,
            is_success=isinstance(body, dict) and body.get("code") == 0,
            pulled_at=NOW,
            page_no=page,
            page_size=kw.get("length") or kw.get("page_size") or 1,
            store_id=kw["store_id"],
            object_type="synthetic",
            trace_id=kw["run_id"],
            run_id=kw["run_id"],
            batch_id=kw["work_item_id"],
            attempt_no=1,
        )

    @staticmethod
    def _total(first: JsonValue, *keys: str) -> int | None:
        node: Any = first
        for key in keys:
            node = node.get(key) if isinstance(node, dict) else None
        return int(node) if isinstance(node, (int, str)) and str(node).isdigit() else None

    def fetch_fin_shipping_list_page(self, **kw: Any) -> LingxingRawEnvelope:
        self.calls.append(("list", kw["store_id"], str(kw["offset"])))
        # 没准备的页按「空页、total 同第一页」返回，和领星真实翻到末尾之后的样子一致。
        first = self.list_pages.get((kw["store_id"], 0), {})
        body = self.list_pages.get(
            (kw["store_id"], kw["offset"]), list_body([], total=self._total(first, "data", "total"))
        )
        return self._envelope(FIN_SHIPPING_LIST_SYNC_SPEC.endpoint_path, body, kw, kw["page_no"])

    def fetch_fin_shipping_detail(self, **kw: Any) -> LingxingRawEnvelope:
        self.calls.append(("detail", kw["store_id"], kw["shipping_list_code"]))
        body = self.details.get(kw["shipping_list_code"], detail_body([]))
        return self._envelope(FIN_SHIPPING_DETAIL_SYNC_SPEC.endpoint_path, body, kw, 1)

    def fetch_fin_wms_order_page(self, **kw: Any) -> LingxingRawEnvelope:
        self.calls.append(("wms", kw["store_id"], str(kw["page_no"])))
        first = self.wms_pages.get((kw["store_id"], 1), {})
        body = self.wms_pages.get(
            (kw["store_id"], kw["page_no"]), wms_body([], total=self._total(first, "total"))
        )
        return self._envelope(FIN_WMS_OUTBOUND_SYNC_SPEC.endpoint_path, body, kw, kw["page_no"])


# --------------------------------------------------------------------------- 纯函数


def test_specs_are_default_off_and_registered_in_execution() -> None:
    for spec in FIN_SHIPPING_SYNC_SPECS:
        assert spec.initial_outbound_enabled is False
        assert spec.schedule_enabled is False
        assert FIN_SHIPPING_HANDLERS[spec.interface_key].handler_key == spec.handler_key
    assert len({spec.interface_key for spec in FIN_SHIPPING_SYNC_SPECS}) == 3


def test_rolling_window_is_90_days_in_shanghai() -> None:
    start, end = rolling_window(NOW)
    assert (start, end) == (date(2026, 8, 22), date(2026, 11, 20))


def test_lingxing_times_are_shanghai_and_zero_dates_are_missing() -> None:
    parsed = lx_datetime("2026-11-10 11:26")
    assert parsed is not None
    assert parsed.astimezone(UTC) == datetime(2026, 11, 10, 3, 26, tzinfo=UTC)
    assert lx_datetime("0000-00-00 00:00:00") is None
    assert lx_datetime("") is None
    assert lx_datetime(None) is None
    assert lx_datetime("2026-11-10 11:26:30") is not None


def test_response_total_accepts_string_and_int() -> None:
    assert response_total({"data": {"total": "12"}}, "data", "total") == 12
    assert response_total({"total": 3}, "total") == 3
    assert response_total({"total": "x"}, "total") is None
    assert response_total({"total": True}, "total") is None


def test_scrub_pii_drops_recipient_keys_recursively() -> None:
    cleaned = scrub_pii(
        {
            "a": 1,
            "consignee_phone": "x",
            "surface_file": {"cos_url": "u"},
            "picker": "p",
            "deliverer": "d",
            "nested": [{"address": "y", "sku": "s", "customization": "c"}],
        }
    )
    assert cleaned == {"a": 1, "nested": [{"sku": "s"}]}


def test_parse_shipping_list_row_maps_columns() -> None:
    parsed = parse_shipping_list_row(
        shipping_row("SP2026T0001"), store_id=STORE_A, source_account_ref=ACCOUNT
    )
    assert parsed is not None
    assert parsed["shipping_list_code"] == "SP2026T0001"
    assert parsed["shipping_list_status"] == "2"
    assert parsed["logistics_provider_id"] == "6899"
    assert parsed["warehouse_id"] == "28030"
    assert parsed["delivery_at"] is not None
    assert (
        parse_shipping_list_row(
            {"shippingListCode": ""}, store_id=STORE_A, source_account_ref=ACCOUNT
        )
        is None
    )


def test_parse_detail_items_merges_duplicate_msku_and_maps_currency_symbol() -> None:
    items = parse_shipping_detail_items(
        [detail_item("SYN-001", qty=10), detail_item("SYN-001", qty=5), detail_item("SYN-002")],
        shipping_list_code="SP2026T0001",
        default_store_id=STORE_B,
        source_account_ref=ACCOUNT,
    )
    assert [(item["msku"], item["delivery_num"]) for item in items] == [
        ("SYN-001", Decimal("15")),
        ("SYN-002", Decimal("10")),
    ]
    assert items[0]["raw_row"]["merged_rows"] == 2
    assert items[0]["raw_row"]["merged_delivery_num"] == "15"
    single = parse_shipping_detail_items(
        [detail_item("SYN-001", qty=10)],
        shipping_list_code="SP2026T0001",
        default_store_id=STORE_B,
        source_account_ref=ACCOUNT,
    )
    assert single[0]["row_hash"] != items[0]["row_hash"]
    assert items[0]["currency_code"] == "CNY"
    assert items[0]["store_id"] == STORE_A
    assert items[0]["purchase_price"] == Decimal("3.00")
    assert items[0]["head_fee_type"] == "按SKU数量"


def test_parse_wms_row_keeps_first_platform_order_and_trims_items() -> None:
    parsed = parse_wms_order_row(wms_row("WO1"), store_id=STORE_A, source_account_ref=ACCOUNT)
    assert parsed is not None
    assert parsed["platform_order_no"] == "PWO1"
    assert parsed["order_status"] == "已出库"
    assert parsed["logistics_fee"] == Decimal("4.20")
    assert parsed["currency_code"] == "USD"
    assert parsed["outbound_at"] is not None
    assert parsed["items"] == [
        {
            "wod_id": 1,
            "seller_sku": "SYN-001",
            "sku": "SYN",
            "count": 2,
            "apportion_freight": "4.20",
            "stock_cost": "12.00",
        }
    ]
    assert "product_info" not in parsed["raw_row"]
    assert (
        parse_wms_order_row({"wo_number": None}, store_id=STORE_A, source_account_ref=ACCOUNT)
        is None
    )
    assert parse_wms_order_row(wms_row("WO1"), store_id=STORE_B, source_account_ref=ACCOUNT) is None


# --------------------------------------------------------------------------- 数据库


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


def add_stores(session: Session, *stores: str) -> None:
    for index, store_id in enumerate(stores or (STORE_A,), start=1):
        session.add(
            LingxingStoreDimension(
                source_account_ref=ACCOUNT,
                platform_code_raw="10008",
                platform_code="walmart",
                store_id=store_id,
                store_name=f"CN99{index:02d}-合成",
                sid=store_id,
                synced_at=NOW,
            )
        )
    session.flush()


def governed(
    session: Session,
    spec: FinShippingSyncInterfaceSpec,
    *,
    enabled: bool = True,
    page_size: int | None = None,
    max_pages: int | None = None,
) -> IntegrationInterface:
    # bootstrap 会把已登记的接口重新置回默认关闭，所以同一个测试里登记过就不再登记。
    query = select(IntegrationInterface).where(
        IntegrationInterface.interface_key == spec.interface_key
    )
    if session.scalars(query).one_or_none() is None:
        IntegrationCatalogService(session).bootstrap_fin_shipping_governance(ACCOUNT)
    interface = session.scalars(query).one()
    config = session.scalars(
        select(IntegrationSyncConfig).where(IntegrationSyncConfig.interface_id == interface.id)
    ).one()
    interface.outbound_enabled = enabled
    config.is_enabled = enabled
    if page_size is not None:
        config.page_size = page_size
    if max_pages is not None:
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
        source_account_ref=ACCOUNT,
        trigger_type=trigger,
        status="queued",
        idempotency_key=f"fin-{uuid4()}",
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
    *,
    now: datetime = NOW,
    **kwargs: Any,
) -> IntegrationSyncRun:
    run = queued_run(session, interface, **kwargs)
    run.status = "running"
    handler = FIN_SHIPPING_HANDLERS[interface.interface_key]
    handler(session, client=client, now=lambda: now).execute(run, interface)
    return run


def test_bootstrap_is_default_off_and_idempotent(session: Session) -> None:
    service = IntegrationCatalogService(session)
    first = service.bootstrap_fin_shipping_governance(ACCOUNT)
    assert first.interface_statuses == ("created", "created", "created")
    second = service.bootstrap_fin_shipping_governance(ACCOUNT)
    assert second.sync_config_statuses == ("unchanged", "unchanged", "unchanged")
    for spec in FIN_SHIPPING_SYNC_SPECS:
        interface = session.scalars(
            select(IntegrationInterface).where(
                IntegrationInterface.interface_key == spec.interface_key
            )
        ).one()
        config = session.scalars(
            select(IntegrationSyncConfig).where(IntegrationSyncConfig.interface_id == interface.id)
        ).one()
        assert interface.outbound_enabled is False
        assert config.is_enabled is False
        assert config.schedule_enabled is False
        assert (config.page_size, config.max_pages) == (
            spec.default_page_size,
            spec.default_max_pages,
        )


def test_enable_opens_manual_first_and_schedule_only_when_asked(session: Session) -> None:
    service = IntegrationCatalogService(session)
    assert service.enable_fin_shipping_sync(ACCOUNT) is False
    service.bootstrap_fin_shipping_governance(ACCOUNT)
    assert service.enable_fin_shipping_sync(ACCOUNT) is True
    configs = session.scalars(select(IntegrationSyncConfig)).all()
    assert all(config.is_enabled and not config.schedule_enabled for config in configs)
    assert service.enable_fin_shipping_sync(ACCOUNT, schedule=True) is True
    session.expire_all()
    configs = session.scalars(select(IntegrationSyncConfig)).all()
    assert all(config.schedule_enabled and config.next_run_at is not None for config in configs)
    crons = {config.schedule_cron for config in configs}
    assert crons == {"0 20 * * 2", "30 20 * * 2", "0 21 * * 2"}


def test_shipping_list_sync_pages_stores_raw_first_and_upserts(session: Session) -> None:
    add_stores(session, STORE_A, STORE_B)
    interface = governed(session, FIN_SHIPPING_LIST_SYNC_SPEC, page_size=2)
    client = FakeLingxing()
    client.list_pages[(STORE_A, 0)] = list_body(
        [shipping_row("SP2026T0001"), shipping_row("SP2026T0002", status=1, delivery="")], total=3
    )
    client.list_pages[(STORE_A, 2)] = list_body([shipping_row("SP2026T0003")], total=3)
    run = run_sync(session, interface, client)

    assert run.status == "succeeded"
    assert (run.work_items_total, run.work_items_succeeded) == (3, 3)
    assert (run.records_seen, run.records_written) == (3, 3)
    assert client.calls == [
        ("list", STORE_A, "0"),
        ("list", STORE_A, "2"),
        ("list", STORE_B, "0"),
    ]
    rows = session.scalars(
        select(FinShippingList).order_by(FinShippingList.shipping_list_code)
    ).all()
    assert [(row.store_id, row.shipping_list_code, row.shipping_list_status) for row in rows] == [
        (STORE_A, "SP2026T0001", "2"),
        (STORE_A, "SP2026T0002", "1"),
        (STORE_A, "SP2026T0003", "2"),
    ]
    assert rows[1].delivery_at is None
    assert rows[0].source_run_id == run.id
    ref = session.get(ApiRawRequestRef, rows[0].source_raw_request_ref_id)
    assert ref is not None
    assert (ref.run_id, ref.response_count, ref.provider_code, ref.is_success) == (
        run.id,
        2,
        "0",
        True,
    )
    blob = session.get(ApiRawBlob, ref.raw_blob_id)
    assert blob is not None
    assert blob.payload_json == client.list_pages[(STORE_A, 0)]
    first_updated = rows[0].updated_at

    # 重跑：内容没变 updated_at 不动；变了才动。
    client.list_pages[(STORE_A, 0)] = list_body(
        [shipping_row("SP2026T0001"), shipping_row("SP2026T0002", status=2)], total=3
    )
    later = datetime(2026, 11, 27, 2, 0, tzinfo=UTC)
    assert run_sync(session, interface, client, now=later).status == "succeeded"
    session.expire_all()
    rows = session.scalars(
        select(FinShippingList).order_by(FinShippingList.shipping_list_code)
    ).all()
    assert rows[0].updated_at == first_updated
    assert rows[1].shipping_list_status == "2"
    assert rows[1].updated_at > first_updated
    assert session.scalar(select(func.count()).select_from(FinShippingList)) == 3


def test_shipping_list_bad_page_fails_only_that_store(session: Session) -> None:
    add_stores(session, STORE_A, STORE_B)
    interface = governed(session, FIN_SHIPPING_LIST_SYNC_SPEC)
    client = FakeLingxing()
    client.list_pages[(STORE_A, 0)] = {"code": 1, "message": "synthetic failure", "data": None}
    client.list_pages[(STORE_B, 0)] = list_body([shipping_row("SP2026T0009")])
    run = run_sync(session, interface, client)
    assert (run.status, run.error_code) == ("failed", "SYNC_FIN_STORE_PARTIAL")
    assert run.error_message is not None and "SYNC_FIN_RESPONSE_FAILED" in run.error_message
    assert (run.work_items_failed, run.work_items_succeeded) == (1, 1)
    assert session.scalar(select(func.count()).select_from(FinShippingList)) == 1
    work = session.scalars(
        select(IntegrationSyncRunWorkItem).where(IntegrationSyncRunWorkItem.status == "failed")
    ).one()
    assert work.error_code == "SYNC_FIN_RESPONSE_FAILED"


def test_shipping_list_runaway_paging_is_refused(session: Session) -> None:
    add_stores(session)
    interface = governed(session, FIN_SHIPPING_LIST_SYNC_SPEC, page_size=1, max_pages=2)
    client = FakeLingxing()
    for offset in range(3):
        client.list_pages[(STORE_A, offset)] = list_body(
            [shipping_row(f"SP2026T000{offset}")], total=99
        )
    run = run_sync(session, interface, client)
    assert (run.status, run.error_code) == ("failed", "SYNC_FIN_ALL_STORES_FAILED")
    assert "SYNC_FIN_SHIPPING_TOO_MANY_PAGES" in (run.error_message or "")


def test_shipping_list_sync_keeps_detail_synced_at_until_the_list_changes(
    session: Session,
) -> None:
    add_stores(session)
    lists = governed(session, FIN_SHIPPING_LIST_SYNC_SPEC)
    details = governed(session, FIN_SHIPPING_DETAIL_SYNC_SPEC)
    client = FakeLingxing()
    client.list_pages[(STORE_A, 0)] = list_body([shipping_row("SP2026T0001")])
    client.details["SP2026T0001"] = detail_body([detail_item("SYN-001")])
    assert run_sync(session, lists, client).status == "succeeded"
    assert run_sync(session, details, client).status == "succeeded"
    shipping = session.scalars(
        select(FinShippingList).where(FinShippingList.shipping_list_code == "SP2026T0001")
    ).one()
    stamped = shipping.detail_synced_at
    assert stamped is not None

    # 发货单内容不变再同步一次：detail_synced_at 不能被清空，明细也不重拉。
    client.calls.clear()
    assert run_sync(session, lists, client).status == "succeeded"
    assert run_sync(session, details, client).status == "succeeded"
    session.expire_all()
    assert shipping.detail_synced_at == stamped
    assert client.calls == [("list", STORE_A, "0")]

    # 发货单内容变了：updated_at 往后走，明细重拉。
    client.calls.clear()
    client.list_pages[(STORE_A, 0)] = list_body(
        [shipping_row("SP2026T0001", delivery="2026-11-11 08:00")]
    )
    assert run_sync(session, lists, client).status == "succeeded"
    assert run_sync(session, details, client).status == "succeeded"
    session.expire_all()
    assert client.calls == [("list", STORE_A, "0"), ("detail", STORE_A, "SP2026T0001")]
    assert shipping.detail_synced_at is not None
    assert shipping.detail_synced_at > stamped


def test_database_error_while_writing_fails_the_page_and_the_store(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_stores(session)
    interface = governed(session, FIN_SHIPPING_LIST_SYNC_SPEC)
    client = FakeLingxing()
    client.list_pages[(STORE_A, 0)] = list_body([shipping_row("SP2026T0001")])

    def boom(*args: Any, **kwargs: Any) -> int:
        raise RuntimeError("synthetic database failure")

    monkeypatch.setattr(
        "app.modules.integration_sync.handlers.lingxing_fin_shipping_sync._upsert_shipping_lists",
        boom,
    )
    run = run_sync(session, interface, client)
    assert (run.status, run.error_code) == ("failed", "SYNC_FIN_ALL_STORES_FAILED")
    assert "SYNC_FIN_STORE_FAILED" in (run.error_message or "")
    work = session.scalars(select(IntegrationSyncRunWorkItem)).one()
    assert (work.status, work.error_code) == ("failed", "SYNC_FIN_STORE_FAILED")
    assert run.work_items_failed == 1
    assert session.scalar(select(func.count()).select_from(FinShippingList)) == 0


def test_short_delivery_against_total_is_incomplete_not_success(session: Session) -> None:
    add_stores(session)
    interface = governed(session, FIN_SHIPPING_LIST_SYNC_SPEC, page_size=2)
    client = FakeLingxing()
    # 领星说共 5 条，只给了 2 条，下一页空：不能记成功。
    client.list_pages[(STORE_A, 0)] = list_body(
        [shipping_row("SP2026T0001"), shipping_row("SP2026T0002")], total=5
    )
    run = run_sync(session, interface, client)
    assert (run.status, run.error_code) == ("failed", "SYNC_FIN_ALL_STORES_FAILED")
    assert "SYNC_FIN_SHIPPING_INCOMPLETE" in (run.error_message or "")
    assert (run.work_items_succeeded, run.work_items_failed) == (1, 1)

    wms = governed(session, FIN_WMS_OUTBOUND_SYNC_SPEC, page_size=2)
    client.wms_pages[(STORE_A, 1)] = wms_body([wms_row("WO1")], total=3)
    run = run_sync(session, wms, client)
    assert run.status == "failed"
    assert "SYNC_FIN_WMS_INCOMPLETE" in (run.error_message or "")

    # total 为 0 或没有 total 时，空页正常结束。
    client.list_pages[(STORE_A, 0)] = list_body([], total=0)
    assert run_sync(session, interface, client).status == "succeeded"
    client.list_pages[(STORE_A, 0)] = {"code": 0, "data": {"list": [shipping_row("SP2026T0009")]}}
    assert run_sync(session, interface, client).status == "succeeded"


def test_repeated_page_from_lingxing_stops_the_store_at_once(session: Session) -> None:
    add_stores(session)
    interface = governed(session, FIN_SHIPPING_LIST_SYNC_SPEC, page_size=1, max_pages=50)
    client = FakeLingxing()
    for offset in range(3):
        client.list_pages[(STORE_A, offset)] = list_body([shipping_row("SP2026T0001")], total=99)
    run = run_sync(session, interface, client)
    assert (run.status, run.error_code) == ("failed", "SYNC_FIN_ALL_STORES_FAILED")
    assert "SYNC_FIN_SHIPPING_PAGE_REPEATED" in (run.error_message or "")
    assert run.work_items_total == 2

    wms = governed(session, FIN_WMS_OUTBOUND_SYNC_SPEC, page_size=1, max_pages=50)
    for page in (1, 2, 3):
        client.wms_pages[(STORE_A, page)] = wms_body([wms_row("WO1")], total=99)
    run = run_sync(session, wms, client)
    assert "SYNC_FIN_WMS_PAGE_REPEATED" in (run.error_message or "")
    assert run.work_items_total == 2


def test_lease_lost_stops_the_whole_run(session: Session) -> None:
    add_stores(session, STORE_A, STORE_B)
    interface = governed(session, FIN_SHIPPING_LIST_SYNC_SPEC)
    run = queued_run(session, interface)
    run.status = "running"

    def lost() -> None:
        raise ProductInfoOneTimeRunError("SYNC_LOCK_LEASE_LOST")

    handler = LingxingFinShippingListSyncHandler(
        session, client=FakeLingxing(), heartbeat=lost, now=lambda: NOW
    )
    with pytest.raises(ProductInfoOneTimeRunError, match="SYNC_LOCK_LEASE_LOST"):
        handler.execute(run, interface)
    assert run.work_items_total == 1


def test_backfill_window_is_used_and_never_before_may(session: Session) -> None:
    add_stores(session)
    interface = governed(session, FIN_SHIPPING_LIST_SYNC_SPEC)
    client = FakeLingxing()
    run = queued_run(
        session,
        interface,
        trigger="backfill",
        window=(datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 6, 30, 16, tzinfo=UTC)),
    )
    run.status = "running"
    LingxingFinShippingListSyncHandler(session, client=client, now=lambda: NOW).execute(
        run, interface
    )
    work = session.scalars(select(IntegrationSyncRunWorkItem)).one()
    assert work.request_safe_params["startTime"] == "2026-05-01"
    assert work.request_safe_params["endTime"] == "2026-06-30"


def seed_shipping_list(
    session: Session, code: str, *, status: str = "2", delivery: datetime | None = None
) -> None:
    session.add(
        FinShippingList(
            source_account_ref=ACCOUNT,
            store_id=STORE_A,
            shipping_list_code=code,
            shipping_list_status=status,
            delivery_at=delivery or datetime(2026, 11, 10, 3, tzinfo=UTC),
            synced_at=NOW,
            updated_at=NOW,
            row_hash="0" * 64,
            raw_row={},
        )
    )
    session.flush()


def test_detail_sync_pulls_shipped_lists_once_until_the_list_changes(session: Session) -> None:
    add_stores(session)
    seed_shipping_list(session, "SP2026T0001")
    seed_shipping_list(session, "SP2026T0002", status="1")
    seed_shipping_list(session, "SP2026T0003", delivery=datetime(2026, 1, 5, tzinfo=UTC))
    interface = governed(session, FIN_SHIPPING_DETAIL_SYNC_SPEC)
    client = FakeLingxing()
    client.details["SP2026T0001"] = detail_body(
        [detail_item("SYN-001"), detail_item("SYN-002", qty=4)]
    )

    run = run_sync(session, interface, client)
    assert run.status == "succeeded"
    assert client.calls == [("detail", STORE_A, "SP2026T0001")]
    assert (run.records_seen, run.records_written) == (2, 2)
    items = session.scalars(
        select(FinShippingDetailItem).order_by(FinShippingDetailItem.msku)
    ).all()
    assert [(item.msku, item.delivery_num, item.wfs_stock_price) for item in items] == [
        ("SYN-001", Decimal("10"), Decimal("6.5")),
        ("SYN-002", Decimal("4"), Decimal("6.5")),
    ]
    assert items[0].shipping_list_code == "SP2026T0001"
    assert items[0].currency_code == "CNY"
    shipping = session.scalars(
        select(FinShippingList).where(FinShippingList.shipping_list_code == "SP2026T0001")
    ).one()
    assert shipping.detail_synced_at is not None

    # 第二次：明细已经是最新，不再请求。
    client.calls.clear()
    later = datetime(2026, 11, 27, 2, 0, tzinfo=UTC)
    assert run_sync(session, interface, client, now=later).status == "succeeded"
    assert client.calls == []

    # 发货单变了（updated_at 晚于明细同步时间）→ 重拉；新明细里没有的 MSKU 删掉，其余覆盖。
    # 这里用真实当前时间：处理器写 detail_synced_at 用的是真实时钟，不是注入的 now。
    shipping.updated_at = datetime.now(UTC)
    session.flush()
    client.details["SP2026T0001"] = detail_body([detail_item("SYN-001", purchase="3.50")])
    assert (
        run_sync(session, interface, client, now=datetime(2026, 11, 29, tzinfo=UTC)).status
        == "succeeded"
    )
    assert client.calls == [("detail", STORE_A, "SP2026T0001")]
    session.expire_all()
    items = session.scalars(select(FinShippingDetailItem)).all()
    assert [(item.msku, item.purchase_price) for item in items] == [("SYN-001", Decimal("3.5"))]
    assert shipping.detail_synced_at is not None
    assert shipping.detail_synced_at > shipping.updated_at


def test_empty_detail_is_pulled_once_and_stale_rows_are_removed(session: Session) -> None:
    add_stores(session)
    seed_shipping_list(session, "SP2026T0001")
    interface = governed(session, FIN_SHIPPING_DETAIL_SYNC_SPEC)
    client = FakeLingxing()
    client.details["SP2026T0001"] = detail_body([detail_item("SYN-001")])
    assert run_sync(session, interface, client).status == "succeeded"
    assert session.scalar(select(func.count()).select_from(FinShippingDetailItem)) == 1

    shipping = session.scalars(
        select(FinShippingList).where(FinShippingList.shipping_list_code == "SP2026T0001")
    ).one()
    shipping.updated_at = datetime.now(UTC)
    session.flush()
    client.details["SP2026T0001"] = detail_body([])
    client.calls.clear()
    run = run_sync(session, interface, client, now=datetime(2026, 11, 29, tzinfo=UTC))
    assert (run.status, run.records_seen, run.records_written) == ("succeeded", 0, 0)
    assert client.calls == [("detail", STORE_A, "SP2026T0001")]
    assert session.scalar(select(func.count()).select_from(FinShippingDetailItem)) == 0

    client.calls.clear()
    assert (
        run_sync(session, interface, client, now=datetime(2026, 11, 30, tzinfo=UTC)).status
        == "succeeded"
    )
    assert client.calls == []


def test_pending_detail_codes_respects_limit_and_order(session: Session) -> None:
    for day in (3, 1, 2):
        seed_shipping_list(
            session, f"SP2026T000{day}", delivery=datetime(2026, 11, day, tzinfo=UTC)
        )
    codes = pending_detail_codes(
        session,
        source_account_ref=ACCOUNT,
        store_id=STORE_A,
        start=date(2026, 10, 1),
        end=date(2026, 11, 30),
        limit=2,
    )
    assert codes == ["SP2026T0003", "SP2026T0002"]


def test_detail_sync_with_bad_shape_fails_the_store(session: Session) -> None:
    add_stores(session)
    seed_shipping_list(session, "SP2026T0001")
    interface = governed(session, FIN_SHIPPING_DETAIL_SYNC_SPEC)
    client = FakeLingxing()
    client.details["SP2026T0001"] = {"code": 0, "data": {"firstLetListResponseList": "oops"}}
    run = run_sync(session, interface, client)
    assert (run.status, run.error_code) == ("failed", "SYNC_FIN_ALL_STORES_FAILED")
    assert "SYNC_FIN_SHIPPING_RESPONSE_SHAPE" in (run.error_message or "")
    assert session.scalar(select(func.count()).select_from(FinShippingDetailItem)) == 0


def test_wms_sync_pages_scrubs_pii_and_upserts(session: Session) -> None:
    add_stores(session)
    interface = governed(session, FIN_WMS_OUTBOUND_SYNC_SPEC, page_size=2)
    client = FakeLingxing()
    client.wms_pages[(STORE_A, 1)] = wms_body([wms_row("WO1"), wms_row("WO2", status=4)], total=3)
    client.wms_pages[(STORE_A, 2)] = wms_body([wms_row("WO3")], total=3)
    run = run_sync(session, interface, client)

    assert run.status == "succeeded"
    assert client.calls == [("wms", STORE_A, "1"), ("wms", STORE_A, "2")]
    assert (run.records_seen, run.records_written) == (3, 3)
    orders = session.scalars(
        select(FinWmsOutboundOrder).order_by(FinWmsOutboundOrder.outbound_order_no)
    ).all()
    assert [
        (order.outbound_order_no, order.platform_order_no, order.order_status) for order in orders
    ] == [
        ("WO1", "PWO1", "已出库"),
        ("WO2", "PWO2", "已截单"),
        ("WO3", "PWO3", "已出库"),
    ]
    assert orders[0].logistics_fee == Decimal("4.2")
    assert orders[0].items[0]["seller_sku"] == "SYN-001"
    assert "customization" not in orders[0].items[0]
    for key in ("consignee", "consignee_phone", "address_line", "order_buyer_notes"):
        assert key not in orders[0].raw_row
    ref = session.get(ApiRawRequestRef, orders[0].source_raw_request_ref_id)
    assert ref is not None
    blob = session.get(ApiRawBlob, ref.raw_blob_id)
    assert blob is not None
    raw_rows = blob.payload_json["data"]  # type: ignore[index]
    assert all("consignee" not in row and "consignee_phone" not in row for row in raw_rows)
    assert raw_rows[0]["product_info"][0]["seller_sku"] == "SYN-001"

    client.wms_pages[(STORE_A, 1)] = wms_body([wms_row("WO1", fee="5.00")], total=1)
    assert run_sync(session, interface, client).status == "succeeded"
    session.expire_all()
    order = session.scalars(
        select(FinWmsOutboundOrder).where(FinWmsOutboundOrder.outbound_order_no == "WO1")
    ).one()
    assert order.logistics_fee == Decimal("5")
    assert session.scalar(select(func.count()).select_from(FinWmsOutboundOrder)) == 3


def test_wms_invalid_row_fails_the_store_and_keeps_old_data(session: Session) -> None:
    add_stores(session)
    interface = governed(session, FIN_WMS_OUTBOUND_SYNC_SPEC)
    client = FakeLingxing()
    client.wms_pages[(STORE_A, 1)] = wms_body([wms_row("WO1")])
    assert run_sync(session, interface, client).status == "succeeded"
    client.wms_pages[(STORE_A, 1)] = wms_body([wms_row("WO2"), {"wo_number": ""}])
    run = run_sync(session, interface, client)
    assert (run.status, run.error_code) == ("failed", "SYNC_FIN_ALL_STORES_FAILED")
    assert "SYNC_FIN_WMS_INVALID_ROW" in (run.error_message or "")
    codes = session.scalars(select(FinWmsOutboundOrder.outbound_order_no)).all()
    assert list(codes) == ["WO1"]


def test_handler_refuses_a_disabled_interface_and_wrong_handler(session: Session) -> None:
    add_stores(session)
    interface = governed(session, FIN_WMS_OUTBOUND_SYNC_SPEC, enabled=False)
    run = queued_run(session, interface)
    with pytest.raises(FinSyncError, match="SYNC_FIN_EXECUTION_NOT_AUTHORIZED"):
        LingxingFinWmsOutboundSyncHandler(session, client=FakeLingxing()).execute(run, interface)
    interface.outbound_enabled = True
    with pytest.raises(FinSyncError, match="SYNC_FIN_EXECUTION_NOT_AUTHORIZED"):
        LingxingFinShippingDetailSyncHandler(session, client=FakeLingxing()).execute(run, interface)


def test_no_walmart_store_fails_the_run(session: Session) -> None:
    interface = governed(session, FIN_SHIPPING_LIST_SYNC_SPEC)
    run = queued_run(session, interface)
    with pytest.raises(FinSyncError, match="SYNC_FIN_NO_STORES"):
        LingxingFinShippingListSyncHandler(session, client=FakeLingxing()).execute(run, interface)


@pytest.mark.parametrize("spec", FIN_SHIPPING_SYNC_SPECS, ids=lambda spec: spec.interface_key)
def test_task_centre_dispatches_here_and_test_env_cannot_reach_lingxing(
    session: Session, spec: FinShippingSyncInterfaceSpec
) -> None:
    add_stores(session)
    run = queued_run(session, governed(session, spec))
    SyncRunExecutionService(session).execute(run.id)
    session.refresh(run)
    assert (run.status, run.error_code) == ("failed", "SYNC_FIN_RUNTIME_NOT_AUTHORIZED")


def test_task_centre_refuses_a_disabled_config(session: Session) -> None:
    run = queued_run(session, governed(session, FIN_SHIPPING_LIST_SYNC_SPEC, enabled=False))
    SyncRunExecutionService(session).execute(run.id)
    session.refresh(run)
    assert (run.status, run.error_code) == ("failed", "SYNC_CONFIG_DISABLED")


def wms_result(
    session: Session, interface: IntegrationInterface, client: FakeLingxing
) -> FinSyncResult:
    run = queued_run(session, interface)
    run.status = "running"
    handler = LingxingFinWmsOutboundSyncHandler(session, client=client, now=lambda: NOW)
    return handler.execute(run, interface)


def test_wms_sync_reports_only_changed_rows_as_affected(session: Session) -> None:
    add_stores(session)
    interface = governed(session, FIN_WMS_OUTBOUND_SYNC_SPEC)
    client = FakeLingxing()
    client.wms_pages[(STORE_A, 1)] = wms_body([wms_row("WO1"), wms_row("WO2")])
    first = wms_result(session, interface, client)
    # 新出库单：明细 MSKU（归一成小写）和平台订单号都记上
    assert first.affected.mskus == {(STORE_A, "syn-001")}
    assert first.affected.orders == {(STORE_A, "PWO1"), (STORE_A, "PWO2")}
    # 内容没变再同步一次：一个键都没有
    second = wms_result(session, interface, client)
    assert second.affected.is_empty()
    # 只改 WO2 的运费：只记 WO2
    client.wms_pages[(STORE_A, 1)] = wms_body([wms_row("WO1"), wms_row("WO2", fee="9.90")])
    third = wms_result(session, interface, client)
    assert third.affected.orders == {(STORE_A, "PWO2")}
    assert third.affected.unresolved == 0


def test_partial_store_failure_keeps_affected_keys_of_the_successful_store(
    session: Session,
) -> None:
    add_stores(session, STORE_A, STORE_B)
    interface = governed(session, FIN_WMS_OUTBOUND_SYNC_SPEC)
    client = FakeLingxing()
    client.wms_pages[(STORE_A, 1)] = {"code": 1, "message": "synthetic failure", "data": None}
    client.wms_pages[(STORE_B, 1)] = wms_body([{**wms_row("WOB1"), "sid": int(STORE_B)}])
    result = wms_result(session, interface, client)
    assert (result.status, result.stores_failed) == ("failed", 1)
    assert result.affected.orders == {(STORE_B, "PWOB1")}
    assert result.affected.mskus == {(STORE_B, "syn-001")}


def test_detail_sync_reports_changed_and_removed_mskus(session: Session) -> None:
    add_stores(session)
    seed_shipping_list(session, "SP2026T0001")
    interface = governed(session, FIN_SHIPPING_DETAIL_SYNC_SPEC)
    client = FakeLingxing()
    client.details["SP2026T0001"] = detail_body([detail_item("SYN-001"), detail_item("SYN-002")])
    run = queued_run(session, interface)
    run.status = "running"
    handler = LingxingFinShippingDetailSyncHandler(session, client=client, now=lambda: NOW)
    first = handler.execute(run, interface)
    assert first.affected.mskus == {(STORE_A, "syn-001"), (STORE_A, "syn-002")}
    # 同一张单再拉一次：SYN-001 价格变了，SYN-002 不在了 → 两个都记
    client.details["SP2026T0001"] = detail_body([detail_item("SYN-001", purchase="3.50")])
    session.execute(
        update(FinShippingList)
        .where(FinShippingList.shipping_list_code == "SP2026T0001")
        .values(detail_synced_at=None)
    )
    run = queued_run(session, interface)
    run.status = "running"
    handler = LingxingFinShippingDetailSyncHandler(session, client=client, now=lambda: NOW)
    second = handler.execute(run, interface)
    assert second.affected.mskus == {(STORE_A, "syn-001"), (STORE_A, "syn-002")}


def stub_fin_handler(interface: IntegrationInterface, result: FinSyncResult) -> type:
    class StubHandler:
        handler_key = FIN_SHIPPING_HANDLERS[interface.interface_key].handler_key

        def __init__(self, _session: Session, *, heartbeat: Any) -> None:
            self.heartbeat = heartbeat

        def execute(self, run_: Any, _interface: Any) -> FinSyncResult:
            return result

    return StubHandler


@pytest.mark.parametrize("shape", ["changed", "unchanged", "unresolved"])
def test_fin_sync_enqueues_only_affected_periods(
    session: Session, monkeypatch: pytest.MonkeyPatch, shape: str
) -> None:
    from app.modules.integration_sync import execution as execution_module
    from app.modules.integration_sync.models import IntegrationSyncRunEvent
    from app.modules.settlement_profit.order_review.recalc_scope import AffectedKeys

    interface = governed(session, FIN_SHIPPING_DETAIL_SYNC_SPEC)
    run = queued_run(session, interface)
    keys = AffectedKeys()
    if shape == "changed":
        keys.add(STORE_A, mskus=["SYN-001"])
    elif shape == "unresolved":
        keys.add(STORE_A)  # 拿不到 MSKU 也拿不到订单号
    # 部分店失败也算：成功店已提交的页照样投递
    result = FinSyncResult(
        run_id=run.id,
        status="failed",
        stores_total=2,
        stores_failed=1,
        records_written=3,
        affected=keys,
    )
    scopes: list[AffectedKeys] = []
    enqueued: list[tuple[list[tuple[str, str]], str]] = []

    def fake_periods(_session: Session, *, source_account_ref: str, keys: AffectedKeys) -> Any:
        scopes.append(keys)
        return [(STORE_A, "2026-11-03")]

    def fake_enqueue(_session: Session, pairs: Any, *, reason: str) -> int:
        enqueued.append((list(pairs), reason))
        return len(pairs)

    def no_full_recalc(*args: Any, **kwargs: Any) -> bool:
        raise AssertionError("cost sync must never dispatch a store-wide recalc")

    monkeypatch.setitem(
        FIN_SHIPPING_HANDLERS, interface.interface_key, stub_fin_handler(interface, result)
    )
    monkeypatch.setattr(execution_module, "affected_periods", fake_periods)
    monkeypatch.setattr(execution_module, "enqueue_affected", fake_enqueue)
    monkeypatch.setattr(execution_module, "dispatch_order_review_recalc", no_full_recalc)
    monkeypatch.setattr(SyncRunExecutionService, "_heartbeat_lock", lambda _self, run_id: None)
    SyncRunExecutionService(session).execute(run.id)

    events = session.scalars(
        select(IntegrationSyncRunEvent).where(
            IntegrationSyncRunEvent.run_id == run.id,
            IntegrationSyncRunEvent.message_code == "ORDER_REVIEW_RECALC_MANUAL_NEEDED",
        )
    ).all()
    if shape == "changed":
        assert [k.mskus for k in scopes] == [{(STORE_A, "syn-001")}]
        assert enqueued == [([(STORE_A, "2026-11-03")], f"{interface.interface_key}_sync")]
        assert events == []
    elif shape == "unchanged":
        assert (scopes, enqueued, events) == ([], [], [])
    else:
        # 拿不到键：不投递、不退回全量，记运行事件提示手动重算
        assert (scopes, enqueued) == ([], [])
        assert len(events) == 1
        assert events[0].safe_details == {"msku_keys": 0, "order_keys": 0, "unresolved_rows": 1}

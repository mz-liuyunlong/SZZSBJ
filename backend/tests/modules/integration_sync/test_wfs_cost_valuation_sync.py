"""Offline checks for the WFS cost valuation flow (contract, client gate, parser, catalog)."""

from __future__ import annotations

import ast
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import SecretStr

from app.core.config import Settings
from app.integrations.lingxing.client import (
    _ENDPOINT_CONTRACTS,
    LingxingClientError,
    LingxingReadonlyClient,
)
from app.integrations.lingxing.wfs_cost_valuation_contracts import (
    WFS_COST_VALUATION_ENDPOINT,
    WfsCostValuationContractError,
    build_wfs_cost_valuation_body,
    wfs_cost_valuation_records,
    wfs_cost_valuation_response_succeeded,
    wfs_cost_valuation_total,
)
from app.modules.integration_sync.handlers.lingxing_wfs_cost_valuation_sync import (
    StoreDirectory,
    WfsCostValuationSyncError,
    parse_record,
    row_hash,
    store_code_from_seller_name,
)
from app.modules.integration_sync.wfs_cost_valuation_catalog import WFS_COST_VALUATION_SYNC_SPEC
from app.modules.warehouse_wfs.inventory_flow_models import WfsCostValuationFlowOds

BACKEND_ROOT = Path(__file__).resolve().parents[3]
REVISION = "20261103_0073_wfs_cost_valuation_flow"
PREVIOUS = "20261103_0072_fin_settle_profit_v2"
TABLE = "ods_lingxing_wfs_cost_valuation_flow"
EMPTY_STORES = StoreDirectory(by_sid={}, by_code={})


def synthetic_record(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "sid": "",
        "dateLocal": "2026-10-02 08:00:00",
        "imageUrl": "https://example.invalid/a.png",
        "gtin": "00000000000001",
        "msku": "SYN-MSKU",
        "title": "synthetic",
        "localName": "合成",
        "localSku": "SYN-SKU",
        "sellerName": "ZZ0001-合成店铺",
        "businessType": "D16",
        "businessName": "库存调整出库",
        "businessDesc": "Damaged at FC",
        "quantity": -2,
        "businessNumber": "SYN-SHIP",
        "costSource": "shipment:SYN",
        "orderBasePurchaseAmount": "1.23456",
        "purchaseTotalAmount": -2.5,
        "orderBaseLogisticsAmount": None,
        "logisticsTotalAmount": "",
        "orderBaseOtherAmount": "0",
        "otherTotalAmount": "0",
        "orderNumber": "SYN-ORDER",
        "date1": "2026-10-05 00:00:00",
        "serialNumber": "SYNSERIAL000001",
    }
    value.update(overrides)
    return value


def test_request_body_never_filters_business_type_or_store() -> None:
    body = build_wfs_cost_valuation_body(
        start=date(2026, 10, 1), end=date(2026, 10, 31), offset=200, length=200
    )
    assert body == {
        "startDate": "2026-10-01",
        "endDate": "2026-10-31",
        "dateType": 0,
        "sortField": "dateLocal",
        "sortType": "asc",
        "offset": 200,
        "length": 200,
    }
    contract = _ENDPOINT_CONTRACTS[WFS_COST_VALUATION_ENDPOINT]
    assert "businessType" not in contract.allowed_body_fields
    assert "sidList" not in contract.allowed_body_fields
    assert contract.auth_strategy == "query_sign"


@pytest.mark.parametrize(
    ("start", "end", "offset", "length"),
    [
        (date(2026, 10, 2), date(2026, 10, 1), 0, 200),
        (date(2026, 5, 1), date(2026, 10, 1), 0, 200),
        (date(2026, 10, 1), date(2026, 10, 2), -1, 200),
        (date(2026, 10, 1), date(2026, 10, 2), 0, 201),
        (date(2026, 10, 1), date(2026, 10, 2), 0, 0),
    ],
)
def test_request_body_rejects_out_of_contract_values(
    start: date, end: date, offset: int, length: int
) -> None:
    with pytest.raises(WfsCostValuationContractError):
        build_wfs_cost_valuation_body(start=start, end=end, offset=offset, length=length)


class FakeTokenProvider:
    def get_access_token(self) -> SecretStr:
        return SecretStr("synthetic-access")

    def recover_from_access_error(self, provider_code: int | str) -> SecretStr:
        del provider_code
        return SecretStr("synthetic-access")


def _client(
    *, real_calls: bool, transport: httpx.BaseTransport | None = None
) -> LingxingReadonlyClient:
    settings = Settings.model_validate(
        {
            "APP_ENV": "test",
            "TEST_DATABASE_URL": "postgresql+psycopg://synthetic@db.invalid/synthetic",
            "LINGXING_BASE_URL": "https://provider.invalid",
            "LINGXING_APP_ID": "0123456789ABCDEF",
            "LINGXING_ENABLE_REAL_CALLS": real_calls,
        }
    )
    return LingxingReadonlyClient(
        settings,
        token_provider=FakeTokenProvider(),
        success_evaluator=wfs_cost_valuation_response_succeeded,
        transport=transport,
    )


def _fetch(client: LingxingReadonlyClient, **overrides: object):  # noqa: ANN202
    kwargs: dict[str, object] = {
        "start_date": date(2026, 10, 1),
        "end_date": date(2026, 10, 2),
        "offset": 0,
        "length": 200,
        "page_no": 1,
        "source_account_ref": "fixture",
        "run_id": "run",
        "work_item_id": "work",
    }
    kwargs.update(overrides)
    return client.fetch_wfs_cost_valuation_page(**kwargs)  # type: ignore[arg-type]


def test_client_refuses_when_real_calls_are_disabled() -> None:
    client = _client(real_calls=False)
    try:
        with pytest.raises(LingxingClientError):
            _fetch(client)
    finally:
        client.close()


def test_client_sends_only_contract_fields_to_a_mock_transport() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"code": 0, "data": {"page": {"records": [], "total": 0}}})

    client = _client(real_calls=True, transport=httpx.MockTransport(handler))
    try:
        envelope = _fetch(client)
        with pytest.raises(LingxingClientError):
            _fetch(client, length=201)
    finally:
        client.close()
    assert envelope.is_success
    assert len(seen) == 1
    assert seen[0].url.path == WFS_COST_VALUATION_ENDPOINT
    body = json.loads(seen[0].content)
    assert set(body) == {
        "startDate",
        "endDate",
        "dateType",
        "sortField",
        "sortType",
        "offset",
        "length",
    }
    assert body["dateType"] == 0


def test_response_helpers_read_data_page_records() -> None:
    payload = {"code": 0, "data": {"page": {"records": [{}], "total": 5}}}
    assert wfs_cost_valuation_records(payload) == [{}]
    assert wfs_cost_valuation_total(payload) == 5
    assert wfs_cost_valuation_response_succeeded(WFS_COST_VALUATION_ENDPOINT, None, payload)
    assert not wfs_cost_valuation_response_succeeded(
        WFS_COST_VALUATION_ENDPOINT, None, {"code": 1, "data": {"page": {"records": []}}}
    )
    assert wfs_cost_valuation_records({"code": 0, "data": {"list": []}}) is None


def test_parse_record_maps_typed_columns() -> None:
    columns = parse_record(synthetic_record(), EMPTY_STORES)
    assert columns["date_local"] == datetime(2026, 10, 2, 8, 0, 0)
    assert columns["business_date"] == date(2026, 10, 2)
    assert columns["settlement_date"] == date(2026, 10, 5)
    assert columns["store_code"] == "ZZ0001"
    assert columns["store_id"] is None
    assert columns["store_mapping_status"] == "unmapped"
    assert columns["business_type"] == "D16"
    assert columns["quantity"] == -2
    assert columns["order_base_purchase_amount"] == Decimal("1.2346")
    assert columns["purchase_total_amount"] == Decimal("-2.5000")
    assert columns["order_base_logistics_amount"] is None
    assert columns["logistics_total_amount"] is None
    assert columns["currency_code"] is None
    assert columns["serial_number"] == "SYNSERIAL000001"


@pytest.mark.parametrize(
    "override",
    [
        {"dateLocal": None},
        {"dateLocal": "02/10/2026"},
        {"businessType": ""},
        {"sellerName": None},
        {"quantity": "1.5"},
        {"quantity": True},
        {"purchaseTotalAmount": "abc"},
        {"purchaseTotalAmount": "1e20"},
    ],
)
def test_parse_record_rejects_unusable_rows(override: dict[str, object]) -> None:
    with pytest.raises(WfsCostValuationSyncError):
        parse_record(synthetic_record(**override), EMPTY_STORES)


def test_store_directory_prefers_sid_then_unique_code() -> None:
    stores = StoreDirectory(by_sid={"555": "9001"}, by_code={"ZZ0002": "9002", "ZZ0003": None})
    assert stores.resolve("555", "ZZ0009") == "9001"
    assert stores.resolve("", "ZZ0002") == "9002"
    assert stores.resolve(None, "ZZ0003") is None
    assert stores.resolve(None, "ZZ0404") is None
    assert store_code_from_seller_name("  ZZ0001-合成 ") == "ZZ0001"
    assert store_code_from_seller_name("") is None


def test_row_hash_ignores_image_url_only() -> None:
    base = synthetic_record()
    assert row_hash(base) == row_hash({**base, "imageUrl": "https://example.invalid/b.png"})
    assert row_hash(base) != row_hash({**base, "quantity": -3})


def test_catalog_spec_is_default_off() -> None:
    spec = WFS_COST_VALUATION_SYNC_SPEC
    assert spec.endpoint_path == WFS_COST_VALUATION_ENDPOINT
    assert spec.initial_outbound_enabled is False
    assert spec.schedule_enabled is False
    assert spec.target_table == TABLE
    assert spec.default_page_size == 200


def test_identity_is_request_and_ordinal_not_serial_number() -> None:
    table = WfsCostValuationFlowOds.__table__
    uniques = [
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    ]
    assert uniques == [("raw_request_ref_id", "source_item_ordinal")]
    assert table.c.serial_number.unique is not True
    for name in (
        "purchase_total_amount",
        "logistics_total_amount",
        "other_total_amount",
    ):
        assert (table.c[name].type.precision, table.c[name].type.scale) == (18, 4)
    assert table.c.currency_code.type.length == 3


def test_migration_is_single_head_on_settlement_profit_and_touches_only_its_table() -> None:
    script = ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini")))
    assert script.get_heads() == [REVISION]
    assert script.get_revision(REVISION).down_revision == PREVIOUS
    source = (BACKEND_ROOT / "alembic" / "versions" / f"{REVISION}.py").read_text("utf-8")
    tables: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "op"
            and node.func.attr in {"create_table", "drop_table"}
        ):
            first = node.args[0]
            tables.add(ast.literal_eval(first) if isinstance(first, ast.Constant) else "TABLE")
    assert tables <= {TABLE, "TABLE"}
    assert f'TABLE = "{TABLE}"' in source

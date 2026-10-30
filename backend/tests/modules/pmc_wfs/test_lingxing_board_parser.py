from datetime import UTC, datetime

import pytest

from app.integrations.lingxing.pmc_wfs_contracts import (
    WFS_CARGO_PAGE_ENDPOINT,
    WFS_SHIPPING_LIST_PAGE_ENDPOINT,
)
from app.modules.integration_sync.parsers.lingxing_wfs_board import (
    WfsBoardParseError,
    parse_wfs_page,
)
from tests.modules.pmc_wfs.wfs_board_fixtures import CARGOS, SHIPPING_LISTS, page


def test_cargo_page_yields_headers_with_goods_children() -> None:
    parsed = parse_wfs_page(WFS_CARGO_PAGE_ENDPOINT, page(CARGOS, 3))

    assert parsed.provider_total == 3 and parsed.response_count == 3
    first, second, third = parsed.headers
    assert first.business_key == "23212872"
    assert first.source_path == "$.data.records[0]"
    assert first.columns["cargo_code"] == "3292441WFB"
    assert first.columns["shipping_list_codes"] == ["SP202610160010009"]
    assert first.columns["status"] == 1 and first.columns["status_name"] == "AWAITING_DELIVERY"
    assert first.columns["to_pending_at"] == datetime.fromtimestamp(1792136538.901, tz=UTC)
    assert first.columns["to_receive_at"] is None
    assert first.columns["goods_count"] == 1
    assert len(first.children) == 1
    child = first.children[0]
    assert child.business_key == "23212872#0"
    assert child.source_path == "$.data.records[0].cargo_good_list[0]"
    assert child.columns["declare_num"] == 72 and child.columns["shipments_num"] == 72
    assert child.columns["damaged_qty"] == 0
    assert child.columns["gtin"] == "00000000000011"

    assert [c.columns["damaged_qty"] for c in second.children] == [2, 0]
    assert second.columns["to_receive_at"] is not None
    assert third.children == () and third.columns["goods_count"] == 0
    assert third.columns["to_await_at"] is None


def test_shipping_list_page_reduces_nested_arrays() -> None:
    parsed = parse_wfs_page(WFS_SHIPPING_LIST_PAGE_ENDPOINT, page(SHIPPING_LISTS, 2))

    assert parsed.provider_total == 2
    first, second = parsed.headers
    assert first.business_key == "SP202610160010009"
    assert first.columns["warehouse_id"] == "16168"
    assert first.columns["cargo_codes"] == ["3292441WFB"]
    assert first.columns["logistics_numbers"] == ["ZY010009"]
    assert first.columns["tracking_numbers"] == []
    assert first.columns["delivery_time"] is None  # 1970-01-01 placeholder
    assert first.columns["actual_delivery_time"] == "2026-10-18 10:00:00"
    assert first.columns["box_num_total"] == 2 and first.columns["shipments_num_total"] == 28
    assert first.columns["actual_due_time"] is None
    assert second.columns["arrival_time"] == "2026-10-28 00:00:00"


def test_parser_rejects_bad_shapes() -> None:
    with pytest.raises(WfsBoardParseError) as missing_id:
        parse_wfs_page(WFS_CARGO_PAGE_ENDPOINT, page([{"cargo_code": "X"}], 1))
    assert missing_id.value.code == "SYNC_WFS_CARGO_ID_MISSING"
    with pytest.raises(WfsBoardParseError) as bad_goods:
        parse_wfs_page(WFS_CARGO_PAGE_ENDPOINT, page([{"id": "1", "cargo_good_list": "x"}], 1))
    assert bad_goods.value.code == "SYNC_WFS_CARGO_GOODS_SHAPE_INVALID"
    with pytest.raises(WfsBoardParseError) as shape:
        parse_wfs_page(WFS_CARGO_PAGE_ENDPOINT, {"code": 0, "data": []})
    assert shape.value.code == "SYNC_WFS_ITEM_SHAPE_INVALID"
    with pytest.raises(WfsBoardParseError) as no_code:
        parse_wfs_page(WFS_SHIPPING_LIST_PAGE_ENDPOINT, page([{"shipping_status": "x"}], 1))
    assert no_code.value.code == "SYNC_WFS_SHIPPING_CODE_MISSING"

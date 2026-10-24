from app.integrations.lingxing.pmc_domestic_contracts import WAREHOUSE_LIST_ENDPOINT
from app.modules.integration_sync.parsers.lingxing_domestic import parse_domestic_page


def test_parse_warehouse_list_page() -> None:
    payload = {
        "code": 0,
        "data": [{"wid": 1300, "name": "Local WH", "type": 1}],
        "total": 1,
    }
    parsed = parse_domestic_page(WAREHOUSE_LIST_ENDPOINT, payload)
    assert parsed.response_count == 1
    row = parsed.headers[0]
    assert row.business_key == "1300"
    assert row.columns["source_warehouse_id"] == "1300"
    assert row.columns["warehouse_name"] == "Local WH"

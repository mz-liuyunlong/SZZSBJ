from datetime import date

import pytest

from scripts.wfs_settlement_probe import (
    ProbeConfig,
    ProbeError,
    _load_config,
    _page,
    _request_body,
    _validate_scope,
)


def config() -> ProbeConfig:
    return ProbeConfig(
        source_account_ref="primary",
        store_id="110704872940532224",
        msku="YC00115-1A",
        start_date=date(2026, 8, 19),
        end_date=date(2026, 10, 17),
        page_size=20,
        max_pages=20,
    )


def test_probe_config_is_exactly_bounded() -> None:
    loaded = _load_config(
        {
            "WFS_PROBE_SOURCE_ACCOUNT_REF": "primary",
            "WFS_PROBE_STORE_ID": "110704872940532224",
            "WFS_PROBE_MSKU": "YC00115-1A",
            "WFS_PROBE_START_DATE": "2026-08-19",
            "WFS_PROBE_END_DATE": "2026-10-17",
            "WFS_PROBE_PAGE_SIZE": "20",
            "WFS_PROBE_MAX_PAGES": "20",
        }
    )

    assert loaded == config()
    body = _request_body(loaded, offset=20)
    assert body["sids"] == "110704872940532224"
    assert body["searchField"] == "msku"
    assert body["searchValue"] == "YC00115-1A"
    assert body["offset"] == 20
    assert body["length"] == 20


@pytest.mark.parametrize(
    ("field", "value"),
    [("WFS_PROBE_PAGE_SIZE", "21"), ("WFS_PROBE_MAX_PAGES", "21")],
)
def test_probe_rejects_expanded_pagination(field: str, value: str) -> None:
    environ = {
        "WFS_PROBE_SOURCE_ACCOUNT_REF": "primary",
        "WFS_PROBE_STORE_ID": "110704872940532224",
        "WFS_PROBE_MSKU": "YC00115-1A",
        "WFS_PROBE_START_DATE": "2026-08-19",
        "WFS_PROBE_END_DATE": "2026-10-17",
        "WFS_PROBE_PAGE_SIZE": "20",
        "WFS_PROBE_MAX_PAGES": "20",
    }
    environ[field] = value

    with pytest.raises(ProbeError, match="WFS_PROBE_SCOPE_INVALID"):
        _load_config(environ)


def test_probe_parses_only_successful_bounded_shape() -> None:
    rows, total = _page(
        {
            "code": 0,
            "data": {
                "list": [
                    {
                        "storeId": "110704872940532224",
                        "msku": "YC00115-1A",
                        "platformOrderNo": "order-1",
                        "salesNum": "1",
                        "settlementDate": "2026-09-01",
                        "uniqueId": "line-1",
                        "rowIndex": 0,
                        "currencyCode": "USD",
                        "platformCode": "10008",
                        "transactionTypes": 0,
                        "platformLogisticsAmount": "6.95",
                    }
                ],
                "total": 1,
            },
        }
    )
    _validate_scope(rows, config=config())
    assert total == 1


def test_probe_rejects_cross_scope_rows_and_provider_errors() -> None:
    with pytest.raises(ProbeError, match="WFS_PROBE_STORE_SCOPE_MISMATCH"):
        _validate_scope(
            [
                {
                    "storeId": "other",
                    "msku": "YC00115-1A",
                    "currencyCode": "USD",
                    "platformCode": "10008",
                    "transactionTypes": 0,
                }
            ],
            config=config(),
        )
    with pytest.raises(ProbeError, match="WFS_PROBE_PROVIDER_RESPONSE_FAILED"):
        _page({"code": 500, "data": {"list": [], "total": 0}})


def test_probe_rejects_non_sales_and_non_numeric_fee_fields() -> None:
    base_row = {
        "storeId": "110704872940532224",
        "msku": "YC00115-1A",
        "platformOrderNo": "order-1",
        "salesNum": "1",
        "settlementDate": "2026-09-01",
        "uniqueId": "line-1",
        "rowIndex": 0,
        "currencyCode": "USD",
        "platformCode": "10008",
        "transactionTypes": 0,
    }
    with pytest.raises(ProbeError, match="WFS_PROBE_BUSINESS_SCOPE_MISMATCH"):
        _validate_scope([{**base_row, "transactionTypes": 4}], config=config())
    with pytest.raises(ProbeError, match="WFS_PROBE_FEE_FIELD_TYPE_INVALID"):
        _validate_scope(
            [{**base_row, "platformLogisticsAmount": "not-a-number"}],
            config=config(),
        )


def test_probe_rejects_missing_settlement_evidence() -> None:
    with pytest.raises(ProbeError, match="WFS_PROBE_REQUIRED_FIELD_MISSING"):
        _validate_scope(
            [
                {
                    "storeId": "110704872940532224",
                    "msku": "YC00115-1A",
                    "platformOrderNo": "order-1",
                    "salesNum": "1",
                    "uniqueId": "line-1",
                    "rowIndex": 0,
                    "currencyCode": "USD",
                    "platformCode": "10008",
                    "transactionTypes": 0,
                }
            ],
            config=config(),
        )

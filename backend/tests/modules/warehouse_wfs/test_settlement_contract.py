"""Static contract regression tests; no API calls or database access."""

from app.integrations.lingxing.client import _ENDPOINT_CONTRACTS

ENDPOINT = "/basicOpen/multiplatform/profit/report/order"


def test_settlement_contract_exists():
    contract = _ENDPOINT_CONTRACTS[ENDPOINT]
    assert contract.method == "POST"
    assert contract.outbound_enabled is True
    assert contract.require_json_body is True
    assert contract.allow_query_parameters is False


def test_settlement_filters_are_allowed():
    contract = _ENDPOINT_CONTRACTS[ENDPOINT]

    expected = {
        "offset",
        "length",
        "sids",
        "mids",
        "platformCodeS",
        "transactionTypeS",
        "currencyCode",
        "searchDateType",
        "startDate",
        "endDate",
        "searchField",
        "searchValue",
    }

    assert contract.allowed_body_fields == expected


def test_existing_scope_contract_preserved():
    contract = _ENDPOINT_CONTRACTS[ENDPOINT]

    assert contract.required_body_fields == {
        "offset",
        "length",
        "sids",
    }
    assert contract.store_field == "sids"
    assert contract.offset_field == "offset"
    assert contract.page_size_field == "length"

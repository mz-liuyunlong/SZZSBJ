from datetime import date

import pytest

from app.integrations.lingxing.client import _ENDPOINT_CONTRACTS
from app.integrations.lingxing.pmc_wfs_contracts import (
    PMC_WFS_ENDPOINT_SPECS,
    WFS_CARGO_PAGE_ENDPOINT,
    WFS_SHIPPING_LIST_PAGE_ENDPOINT,
    PmcWfsContractError,
    build_pmc_wfs_page_body,
    pmc_wfs_response_items,
    pmc_wfs_response_succeeded,
    pmc_wfs_response_total,
)


def test_specs_are_registered_in_shared_client_contracts() -> None:
    for path, spec in PMC_WFS_ENDPOINT_SPECS.items():
        contract = _ENDPOINT_CONTRACTS[path]  # type: ignore[index]
        assert contract.outbound_enabled is True
        assert contract.auth_strategy == "query_sign"
        assert contract.allowed_body_fields == spec.allowed_body_fields
        assert contract.required_body_fields == {"offset", "length"}
        assert contract.store_field is None
        assert spec.max_page_size == 200


def test_body_uses_creation_window_in_provider_date_format() -> None:
    body = build_pmc_wfs_page_body(
        WFS_CARGO_PAGE_ENDPOINT,
        offset=200,
        length=200,
        start_date=date(2026, 6, 1),
        end_date=date(2026, 10, 30),
    )
    assert body == {
        "offset": 200,
        "length": 200,
        "start_time": "2026-06-01",
        "end_time": "2026-10-30",
    }


def test_body_rejects_contract_violations() -> None:
    with pytest.raises(PmcWfsContractError):
        build_pmc_wfs_page_body(WFS_CARGO_PAGE_ENDPOINT, offset=0, length=200)
    with pytest.raises(PmcWfsContractError):
        build_pmc_wfs_page_body(
            WFS_CARGO_PAGE_ENDPOINT,
            offset=0,
            length=201,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2),
        )
    with pytest.raises(PmcWfsContractError):
        build_pmc_wfs_page_body(
            WFS_SHIPPING_LIST_PAGE_ENDPOINT,
            offset=0,
            length=200,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2),
            extra={"sid": "1"},
        )
    with pytest.raises(PmcWfsContractError):
        build_pmc_wfs_page_body(
            WFS_SHIPPING_LIST_PAGE_ENDPOINT,
            offset=0,
            length=200,
            start_date=date(2026, 6, 2),
            end_date=date(2026, 6, 1),
        )
    with pytest.raises(PmcWfsContractError):
        build_pmc_wfs_page_body("/erp/sc/other", offset=0, length=1)


def test_response_helpers_read_records_and_string_total() -> None:
    payload = {"code": 0, "data": {"total": "806", "records": [{"id": "1"}]}}
    assert pmc_wfs_response_items(WFS_CARGO_PAGE_ENDPOINT, payload) == [{"id": "1"}]
    assert pmc_wfs_response_total(payload) == 806
    assert pmc_wfs_response_total({"code": 0, "data": {"total": 12, "records": []}}) == 12
    assert pmc_wfs_response_total({"code": 0, "data": {"total": "x", "records": []}}) is None
    assert pmc_wfs_response_items(WFS_CARGO_PAGE_ENDPOINT, {"code": 0, "data": []}) is None
    assert pmc_wfs_response_succeeded(WFS_CARGO_PAGE_ENDPOINT, None, payload) is True
    assert pmc_wfs_response_succeeded(WFS_CARGO_PAGE_ENDPOINT, None, {"code": 1}) is False
    assert pmc_wfs_response_succeeded("/erp/sc/other", None, payload) is False

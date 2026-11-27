"""Settlement (recon) report contracts: two GETs, no file download."""

from __future__ import annotations

import pytest

from app.integrations.walmart.contracts import ContractError
from app.integrations.walmart.recon_catalog import recon_read_registry
from app.integrations.walmart.unified_api import reviewed_registry


def test_recon_registry_is_read_only_and_disabled_by_default() -> None:
    registry = recon_read_registry()
    assert set(registry.keys()) == {"recon_report_dates", "recon_report_json"}
    assert all(not registry.get(key).enabled for key in registry.keys())
    assert all(registry.get(key).method == "GET" for key in registry.keys())
    with pytest.raises(ContractError, match="WALMART_OPERATION_NOT_APPROVED"):
        registry.prepare("recon_report_dates", params={"reportVersion": "v1"})
    with pytest.raises(ContractError, match="WALMART_APPROVED_OPERATION_UNKNOWN"):
        recon_read_registry(approved_keys=frozenset({"recon_report_file"}))


def test_recon_json_page_bounds_and_required_params() -> None:
    registry = recon_read_registry(
        approved_keys=frozenset({"recon_report_dates", "recon_report_json"})
    )
    dates = registry.prepare("recon_report_dates", params={"reportVersion": "v1"})
    assert dates.path == "/v3/report/reconreport/availableReconFiles" and not dates.is_write
    with pytest.raises(ContractError, match="WALMART_FIELD_INVALID"):
        registry.prepare("recon_report_dates", params={"reportVersion": "v2"})
    page = registry.prepare(
        "recon_report_json", params={"reportDate": "11/03/2026", "offset": 0, "noOfRecords": 1000}
    )
    assert page.path == "/v3/report/reconreport/reconFileJson"
    assert dict(page.query) == {"reportDate": "11/03/2026", "offset": 0, "noOfRecords": 1000}
    with pytest.raises(ContractError, match="WALMART_FIELD_INVALID"):
        registry.prepare(
            "recon_report_json",
            params={"reportDate": "11/03/2026", "offset": 0, "noOfRecords": 1001},
        )
    with pytest.raises(ContractError):
        registry.prepare("recon_report_json", params={"reportDate": "11/03/2026"})


def test_recon_operations_are_in_the_reviewed_registry_as_reads() -> None:
    registry = reviewed_registry()
    for key in ("recon_report_dates", "recon_report_json"):
        operation = registry.get(key)
        assert operation.family == "recon" and operation.permission == "action:walmart:recon:read"
        assert operation.risk == "read"

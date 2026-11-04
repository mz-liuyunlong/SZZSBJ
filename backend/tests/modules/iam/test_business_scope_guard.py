"""Existing persisted dimensional scopes fail closed on unreviewed business APIs."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.core.api import ApiError
from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal
from app.modules.iam.business_scope_guard import (
    _scope_sources,
    require_business_scope_coverage,
)


def _request(path: str, method: str = "GET") -> Request:
    return Request({"type": "http", "path": path, "method": method, "headers": []})


def _session(rows: list[dict[str, object]]) -> MagicMock:
    session = MagicMock(spec=Session)
    session.execute.return_value.mappings.return_value = rows
    session.scalar.return_value = False
    return session


def _principal(user_id: str = "42") -> Principal:
    return Principal(user_id=user_id, permissions=frozenset({"products:read"}))


def test_scope_sources_use_user_override_per_dimension() -> None:
    session = _session([
        {"origin": "role", "scope_type": "store", "scope_value": "A1|S1"},
        {"origin": "user", "scope_type": "store", "scope_value": "A2|S2"},
        {"origin": "role", "scope_type": "sku", "scope_value": "SKU-01"},
        {"origin": "user", "scope_type": "owner", "scope_value": "OWNER-42"},
    ])
    scopes = _scope_sources(session, 42)
    assert scopes["store"] == frozenset({"A2|S2"})
    assert scopes["sku"] == frozenset({"SKU-01"})
    assert scopes["owner"] == frozenset({"OWNER-42"})
    assert scopes["product"] == frozenset()


@pytest.mark.parametrize(("dimension", "allowed", "denied"), [
    ("sku", "/api/sales/order-profit", "/api/products"),
    ("product", "/api/sales/daily-sales", "/api/sales/order-profit"),
])
def test_legacy_identity_dimensions_are_only_reviewed_for_specific_reads(
    dimension: str, allowed: str, denied: str
) -> None:
    session = _session([
        {"origin": "role", "scope_type": dimension, "scope_value": "A1|id-1"},
    ])
    require_business_scope_coverage(_request(allowed), _principal(), session)
    with pytest.raises(ApiError) as error:
        require_business_scope_coverage(_request(denied), _principal(), session)
    assert error.value.status_code == 403
    assert error.value.details == {
        "scope_reason": "SKU_SCOPE_NOT_ENFORCED" if dimension == "sku" else "PRODUCT_SCOPE_NOT_ENFORCED"
    }


@pytest.mark.parametrize("path", [
    "/api/operations/plans",
    "/api/warehouse/wfs-fee-cases/legacy-compare",
    "/api/pmc/purchase/sku-cycles",
    "/api/products",
    "/api/sales/order-profit",
])
def test_store_scoped_user_cannot_read_unreviewed_business_paths(path: str) -> None:
    session = _session([
        {"origin": "role", "scope_type": "store", "scope_value": "A1|S1"},
    ])
    with pytest.raises(ApiError) as error:
        require_business_scope_coverage(_request(path), _principal(), session)
    assert error.value.status_code == 403
    assert error.value.details == {"scope_reason": "STORE_SCOPE_NOT_ENFORCED"}


@pytest.mark.parametrize("path", [
    "/api/sales/daily-sales",
    "/api/sales/daily-sales/export",
    "/api/listings/walmart/filter-options",
    "/api/pmc/purchase/board",
    "/api/pmc/purchase/orders/PO123",
    "/api/pmc/purchase/plans/pending",
    "/api/after-sales/refunds/items",
    "/api/warehouse/wfs-fee-cases",
    "/api/approvals",
])
def test_store_scoped_user_can_reach_reviewed_sql_paths(path: str) -> None:
    session = _session([
        {"origin": "user", "scope_type": "store", "scope_value": "A1|S1"},
    ])
    require_business_scope_coverage(_request(path), _principal(), session)
    session.execute.assert_called_once()


def test_store_scoped_user_cannot_mutate_read_only_listing() -> None:
    session = _session([
        {"origin": "user", "scope_type": "store", "scope_value": "A1|S1"},
    ])
    with pytest.raises(ApiError) as error:
        require_business_scope_coverage(
            _request("/api/listings/walmart/id/archive", "POST"), _principal(), session
        )
    assert error.value.status_code == 403


@pytest.mark.parametrize("path", [
    "/health",
    "/api/settings/rbac/roles",
    "/api/auth/login",
    "/api/integrations/feishu/organization-events",
])
def test_public_admin_and_auth_paths_do_not_query_scopes(path: str) -> None:
    session = _session([])
    require_business_scope_coverage(_request(path), _principal(), session)
    session.execute.assert_not_called()


def test_preview_and_super_admin_do_not_query_scope_grants() -> None:
    session = _session([])
    require_business_scope_coverage(
        _request("/api/products"),
        Principal(user_id=PREVIEW_PRINCIPAL_ID, permissions=frozenset()),
        session,
    )
    require_business_scope_coverage(
        _request("/api/products"),
        Principal(user_id="1", permissions=frozenset({"*"})),
        session,
    )
    session.execute.assert_not_called()


def test_department_scoped_user_cannot_enter_unreviewed_business_area() -> None:
    session = _session([
        {"origin": "role", "scope_type": "org_department", "scope_value": "dept-1"},
    ])
    with pytest.raises(ApiError) as denied:
        require_business_scope_coverage(_request("/api/operations/plans"), _principal(), session)
    assert denied.value.status_code == 403
    assert denied.value.details == {"scope_reason": "ORGANIZATION_SCOPE_NOT_ENFORCED"}


def test_department_scoped_user_can_use_reviewed_refund_and_wfs_paths() -> None:
    session = _session([
        {"origin": "role", "scope_type": "org_department", "scope_value": "dept-1"},
    ])
    require_business_scope_coverage(
        _request("/api/after-sales/refunds/items"), _principal(), session
    )
    require_business_scope_coverage(
        _request("/api/warehouse/wfs-fee-cases"), _principal(), session
    )
    require_business_scope_coverage(
        _request("/api/approvals"), _principal(), session
    )


def test_department_scope_denies_unreviewed_wfs_legacy_compare_and_approval_bulk() -> None:
    session = _session([
        {"origin": "role", "scope_type": "org_department", "scope_value": "dept-1"},
    ])
    for method, path in [
        ("GET", "/api/warehouse/wfs-fee-cases/legacy-compare"),
        ("POST", "/api/warehouse/wfs-fee-cases/sync-legacy-execute"),
        ("POST", "/api/approvals/workflow/bulk-approve"),
        ("POST", "/api/approvals/legacy/00000000-0000-0000-0000-000000000001/reattest"),
    ]:
        with pytest.raises(ApiError) as denied:
            require_business_scope_coverage(_request(path, method), _principal(), session)
        assert denied.value.details == {"scope_reason": "ORGANIZATION_SCOPE_NOT_ENFORCED"}


def test_own_linked_owner_identity_enforces_org_boundary_even_without_department_grant() -> None:
    session = _session([])
    session.scalar.return_value = True
    with pytest.raises(ApiError) as denied:
        require_business_scope_coverage(_request("/api/operations/plans"), _principal(), session)
    assert denied.value.details == {"scope_reason": "ORGANIZATION_SCOPE_NOT_ENFORCED"}
    session.scalar.assert_called_once()


def test_global_org_grant_does_not_weaken_a_separate_store_scope() -> None:
    session = _session([
        {"origin": "role", "scope_type": "org_department", "scope_value": "*"},
        {"origin": "role", "scope_type": "store", "scope_value": "SHOP1|STORE1"},
    ])
    with pytest.raises(ApiError) as denied:
        require_business_scope_coverage(_request("/api/sales/order-profit"), _principal(), session)
    assert denied.value.details == {"scope_reason": "STORE_SCOPE_NOT_ENFORCED"}


def test_department_scoped_wfs_case_write_contract_allows_only_reviewed_actions() -> None:
    session = _session([
        {"origin": "role", "scope_type": "org_department", "scope_value": "dept-1"},
    ])
    require_business_scope_coverage(
        _request("/api/warehouse/wfs-fee-cases/00000000-0000-0000-0000-000000000001/follow", "POST"),
        _principal(), session,
    )
    with pytest.raises(ApiError):
        require_business_scope_coverage(
            _request("/api/warehouse/wfs-fee-alerts/detection-preview", "POST"),
            _principal(), session,
        )


def test_store_scoped_user_can_access_reviewed_wfs_write_but_not_bulk_approval() -> None:
    session = _session([
        {"origin": "user", "scope_type": "store", "scope_value": "SHOP1|STORE1"},
    ])
    require_business_scope_coverage(
        _request(
            "/api/warehouse/wfs-fee-cases/00000000-0000-0000-0000-000000000001/follow",
            "POST",
        ),
        _principal(), session,
    )
    with pytest.raises(ApiError) as denied:
        require_business_scope_coverage(
            _request("/api/approvals/workflow/bulk-approve", "POST"),
            _principal(), session,
        )
    assert denied.value.details == {"scope_reason": "STORE_SCOPE_NOT_ENFORCED"}


@pytest.mark.parametrize("path", [
    "/api/sales/daily-sales",
    "/api/sales/daily-sales/export",
    "/api/sales/order-profit",
    "/api/sales/order-profit/export",
    "/api/listings/walmart",
    "/api/listings/walmart/filter-options",
])
def test_explicit_owner_scope_only_enters_reviewed_data_page_reads(path: str) -> None:
    session = _session([
        {"origin": "user", "scope_type": "owner", "scope_value": "A1|UID1"},
    ])
    require_business_scope_coverage(_request(path), _principal(), session)


@pytest.mark.parametrize(("method", "path"), [
    ("GET", "/api/products"),
    ("GET", "/api/pmc/purchase/board"),
    ("GET", "/api/after-sales/refunds/items"),
    ("GET", "/api/warehouse/wfs-fee-cases"),
    ("GET", "/api/listings/tags"),
    ("POST", "/api/listings/walmart/id/archive"),
    ("POST", "/api/sales/daily-sales/export"),
])
def test_explicit_owner_scope_denies_unreviewed_business_routes(
    method: str, path: str
) -> None:
    session = _session([
        {"origin": "role", "scope_type": "owner", "scope_value": "A1|UID1"},
    ])
    with pytest.raises(ApiError) as denied:
        require_business_scope_coverage(_request(path, method), _principal(), session)
    assert denied.value.details == {"scope_reason": "OWNER_SCOPE_NOT_ENFORCED"}

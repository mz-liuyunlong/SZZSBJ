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


@pytest.mark.parametrize("dimension", ["owner", "sku", "product"])
def test_legacy_unenforced_dimensions_deny_even_reviewed_reads(dimension: str) -> None:
    session = _session([
        {"origin": "role", "scope_type": dimension, "scope_value": "*"},
    ])
    with pytest.raises(ApiError) as error:
        require_business_scope_coverage(
            _request("/api/sales/daily-sales"), _principal(), session
        )
    assert error.value.status_code == 403
    assert error.value.details == {"scope_reason": "UNENFORCED_DIMENSION"}


@pytest.mark.parametrize("path", [
    "/api/operations/plans",
    "/api/warehouse/wfs-fee-cases",
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

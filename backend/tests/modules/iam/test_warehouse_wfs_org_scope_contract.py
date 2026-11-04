"""WFS case source and organization isolation across reads and mutations."""

from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from starlette.requests import Request

from app.core.api import ApiError
from app.core.auth import Principal
from app.modules.iam.organization_access import ORG_OWNER_SCOPE_SESSION_KEY
from app.modules.warehouse_wfs.router import require_wfs_org_scope
from app.modules.warehouse_wfs.schemas import WfsFeeCaseQuery
from app.modules.warehouse_wfs.service import WfsFeeAlertService


def _session() -> MagicMock:
    session = MagicMock()
    session.info = {ORG_OWNER_SCOPE_SESSION_KEY: frozenset({"uid-review"})}
    return session


def test_wfs_cases_count_and_list_share_owner_filter() -> None:
    session = _session()
    session.execute.return_value.scalar_one.return_value = 0
    session.execute.return_value.mappings.return_value.all.return_value = []
    WfsFeeAlertService(session).list_cases(WfsFeeCaseQuery(), frozenset({"source-a"}))
    assert session.execute.call_count == 2
    for call in session.execute.call_args_list:
        statement, params = call.args
        assert "owner_ref = any(:org_owner_refs)" in str(statement)
        assert params["org_owner_refs"] == ["uid-review"]
        assert params["accounts"] == ["source-a"]


def test_wfs_detail_cannot_resolve_out_of_scope_owner() -> None:
    session = _session()
    session.execute.return_value.mappings.return_value.first.return_value = None
    with pytest.raises(ApiError) as error:
        WfsFeeAlertService(session).get_case(UUID(int=1), frozenset({"source-a"}))
    assert error.value.status_code == 404
    statement, params = session.execute.call_args.args
    assert "owner_ref=any(:org_owner_refs)" in str(statement)
    assert params["org_owner_refs"] == ["uid-review"]


def test_wfs_mutation_locks_and_checks_owner_before_writing() -> None:
    session = _session()
    session.execute.return_value.first.return_value = None
    with pytest.raises(ApiError) as error:
        WfsFeeAlertService(session).ensure_case_visible(UUID(int=1), frozenset({"source-a"}))
    assert error.value.status_code == 404
    statement, params = session.execute.call_args.args
    assert "owner_ref=any(:org_owner_refs)" in str(statement)
    assert "FOR UPDATE" in str(statement)
    assert params["org_owner_refs"] == ["uid-review"]


def test_wfs_permission_checked_before_org_resolution() -> None:
    request = Request(
        {"type": "http", "method": "GET", "path": "/api/warehouse/wfs-fee-cases", "headers": []}
    )
    principal = Principal(user_id="8", permissions=frozenset())
    session = _session()
    with patch("app.modules.warehouse_wfs.router.resolve_business_owner_refs") as resolver:
        with pytest.raises(ApiError) as error:
            require_wfs_org_scope(request, principal, session)
    assert error.value.status_code == 403
    resolver.assert_not_called()


def test_wfs_scoped_user_is_limited_to_verified_owners() -> None:
    request = Request(
        {"type": "http", "method": "GET", "path": "/api/warehouse/wfs-fee-cases", "headers": []}
    )
    principal = Principal(user_id="8", permissions=frozenset({"page:warehouse:wfs-fee-alert:view"}))
    session = _session()
    with patch(
        "app.modules.warehouse_wfs.router.resolve_business_owner_refs",
        return_value=frozenset({"uid-restricted"}),
    ):
        require_wfs_org_scope(request, principal, session)
    assert session.info[ORG_OWNER_SCOPE_SESSION_KEY] == frozenset({"uid-restricted"})

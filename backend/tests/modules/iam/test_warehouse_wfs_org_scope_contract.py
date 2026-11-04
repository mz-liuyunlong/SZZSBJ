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


def test_wfs_account_owner_pairs_gate_list_detail_and_mutations() -> None:
    import json

    from app.modules.iam.organization_access import ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY

    session = MagicMock()
    session.info = {
        ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY: frozenset({
            ("source-a", "same-uid"),
        })
    }
    session.execute.return_value.scalar_one.return_value = 0
    session.execute.return_value.mappings.return_value.all.return_value = []
    WfsFeeAlertService(session).list_cases(
        WfsFeeCaseQuery(), frozenset({"source-a", "source-b"})
    )
    for call in session.execute.call_args_list:
        statement, params = call.args
        assert "allowed.account_ref=source_account_ref" in str(statement)
        assert "allowed.owner_uid=owner_ref" in str(statement)
        assert json.loads(params["org_account_owners"]) == [
            {"account_ref": "source-a", "owner_uid": "same-uid"}
        ]

    session.execute.reset_mock()
    session.execute.return_value.mappings.return_value.first.return_value = None
    with pytest.raises(ApiError):
        WfsFeeAlertService(session).get_case(UUID(int=1), frozenset({"source-a", "source-b"}))
    statement, params = session.execute.call_args.args
    assert "allowed.account_ref=source_account_ref" in str(statement)
    assert json.loads(params["org_account_owners"])[0]["account_ref"] == "source-a"

    session.execute.reset_mock()
    session.execute.return_value.first.return_value = None
    with pytest.raises(ApiError):
        WfsFeeAlertService(session).ensure_case_visible(
            UUID(int=1), frozenset({"source-a", "source-b"})
        )
    statement, params = session.execute.call_args.args
    assert "allowed.owner_uid=owner_ref" in str(statement)
    assert "FOR UPDATE" in str(statement)
    assert json.loads(params["org_account_owners"])[0]["owner_uid"] == "same-uid"


def test_wfs_router_install_account_owner_scope_without_legacy_identity() -> None:
    from app.modules.iam.organization_access import ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY

    request = Request({
        "type": "http", "method": "GET",
        "path": "/api/warehouse/wfs-fee-cases",
        "headers": [],
    })
    principal = Principal(
        user_id="8", permissions=frozenset({"page:warehouse:wfs-fee-alert:view"})
    )
    session = MagicMock()
    session.info = {}
    with (
        patch(
            "app.modules.warehouse_wfs.router.resolve_business_account_owner_pairs",
            return_value=frozenset({("source-a", "same-uid")}),
        ),
        patch("app.modules.warehouse_wfs.router.resolve_business_owner_refs") as legacy,
    ):
        require_wfs_org_scope(request, principal, session)
    legacy.assert_not_called()
    assert session.info[ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY] == frozenset({
        ("source-a", "same-uid")
    })


def test_wfs_store_scope_checks_account_store_pair_in_read_and_write_sql() -> None:
    import json

    from app.modules.iam.store_scope import STORE_SCOPE_SESSION_KEY

    session = MagicMock()
    session.info = {STORE_SCOPE_SESSION_KEY: frozenset({("source-a", "store-one")})}
    session.execute.return_value.scalar_one.return_value = 0
    session.execute.return_value.mappings.return_value.all.return_value = []
    WfsFeeAlertService(session).list_cases(
        WfsFeeCaseQuery(), frozenset({"source-a", "source-b"})
    )
    for call in session.execute.call_args_list:
        statement, params = call.args
        assert "stores.account_ref=source_account_ref" in str(statement)
        assert "stores.store_key=store_id" in str(statement)
        assert json.loads(params["org_account_stores"]) == [
            {"account_ref": "source-a", "store_key": "store-one"}
        ]

    session.execute.reset_mock()
    session.execute.return_value.first.return_value = None
    with pytest.raises(ApiError):
        WfsFeeAlertService(session).ensure_case_visible(
            UUID(int=1), frozenset({"source-a", "source-b"})
        )
    sql, params = session.execute.call_args.args
    assert "FOR UPDATE" in str(sql)
    assert "stores.store_key=store_id" in str(sql)
    assert json.loads(params["org_account_stores"])[0]["account_ref"] == "source-a"


def test_wfs_store_scope_installation_does_not_require_restricted_org_scope() -> None:
    from app.modules.iam.store_scope import STORE_SCOPE_SESSION_KEY

    request = Request({
        "type": "http", "method": "GET",
        "path": "/api/warehouse/wfs-fee-cases",
        "headers": [],
    })
    session = MagicMock()
    session.info = {}
    principal = Principal(
        user_id="8", permissions=frozenset({"page:warehouse:wfs-fee-alert:view"})
    )
    with (
        patch("app.modules.warehouse_wfs.router.resolve_business_account_owner_pairs", return_value=None),
        patch("app.modules.warehouse_wfs.router.resolve_business_owner_refs", return_value=None),
        patch(
            "app.modules.warehouse_wfs.router.resolve_account_store_scope",
            return_value=frozenset({("source-a", "store-one")}),
        ),
    ):
        require_wfs_org_scope(request, principal, session)
    assert session.info[STORE_SCOPE_SESSION_KEY] == frozenset({("source-a", "store-one")})

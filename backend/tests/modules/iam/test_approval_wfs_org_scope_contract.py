"""Approval workbench uses the same verified owner scope as WFS cases."""

from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from app.core.api import ApiError
from app.core.auth import Principal
from app.modules.approvals.router import require_approval_org_scope
from app.modules.approvals.schemas import ApprovalQuery
from app.modules.approvals.service import ApprovalService
from app.modules.iam.organization_access import ORG_OWNER_SCOPE_SESSION_KEY


def _session() -> MagicMock:
    session = MagicMock()
    session.info = {ORG_OWNER_SCOPE_SESSION_KEY: frozenset({"uid-a"})}
    return session


def test_approval_detail_requires_current_wfs_owner() -> None:
    session = _session()
    session.execute.return_value.mappings.return_value.first.return_value = None
    with pytest.raises(ApiError) as exc:
        ApprovalService(session)._record(UUID(int=1), frozenset({"A1"}))
    assert exc.value.status_code == 404
    statement, params = session.execute.call_args.args
    assert "wc.owner_ref=any(:org_owner_refs)" in str(statement)
    assert params["org_owner_refs"] == ["uid-a"]


def test_approval_case_decision_requires_current_wfs_owner() -> None:
    session = _session()
    session.execute.return_value.mappings.return_value.first.return_value = None
    with pytest.raises(ApiError) as exc:
        ApprovalService(session)._case("synthetic-case", frozenset({"A1"}), lock=True)
    assert exc.value.status_code == 404
    statement, params = session.execute.call_args.args
    assert "owner_ref=any(:org_owner_refs)" in str(statement)
    assert "for update" in str(statement)
    assert params["org_owner_refs"] == ["uid-a"]


def test_formal_and_legacy_approval_lists_limit_wfs_owner() -> None:
    session = _session()
    session.execute.return_value.scalar_one.return_value = 0
    session.execute.return_value.mappings.return_value.all.return_value = []
    service = ApprovalService(session)
    service.list_requests(
        ApprovalQuery(view="created"), frozenset({"A1"}), "actor", may_review=True
    )
    for call in session.execute.call_args_list:
        sql = str(call.args[0])
        assert "wc.owner_ref=any(:org_owner_refs)" in sql
        assert call.args[1]["org_owner_refs"] == ["uid-a"]

    session.execute.reset_mock()
    service.list_requests(ApprovalQuery(), frozenset({"A1"}), "actor", may_review=True)
    for call in session.execute.call_args_list:
        sql = str(call.args[0])
        assert "wc.owner_ref=any(:org_owner_refs)" in sql
        assert "c.owner_ref=any(:org_owner_refs)" in sql
        assert call.args[1]["org_owner_refs"] == ["uid-a"]


def test_approval_scope_is_applied_to_each_request() -> None:
    session = _session()
    principal = Principal(
        user_id="8", permissions=frozenset({"page:data-center:approval-workspace:view"})
    )
    with patch(
        "app.modules.approvals.router.resolve_business_owner_refs",
        return_value=frozenset({"uid-b"}),
    ):
        require_approval_org_scope(principal, session)
    assert session.info[ORG_OWNER_SCOPE_SESSION_KEY] == frozenset({"uid-b"})


def test_workbench_summary_aggregates_filter_formal_and_legacy_cases() -> None:
    session = _session()
    session.execute.return_value.mappings.return_value.one.side_effect = [
        {
            "pending": 0,
            "high_risk": 0,
            "info_required": 0,
            "approved": 0,
        },
        {
            "total": 0,
            "still_pending": 0,
            "info_required": 0,
            "high_risk": 0,
            "approved": 0,
        },
    ]
    ApprovalService(session).summary(frozenset({"A1"}), actor="actor", may_review=True)
    assert session.execute.call_count == 2
    formal_sql = str(session.execute.call_args_list[0].args[0])
    legacy_sql = str(session.execute.call_args_list[1].args[0])
    assert "wc.owner_ref=any(:org_owner_refs)" in formal_sql
    assert "c.owner_ref=any(:org_owner_refs)" in legacy_sql
    for call in session.execute.call_args_list:
        assert call.args[1]["org_owner_refs"] == ["uid-a"]


def test_scoped_approvals_do_not_inherit_access_to_unreviewed_approval_types() -> None:
    """A WFS case grant cannot authorize unrelated approval categories."""
    service = ApprovalService(_session())
    condition = service._approval_scope_condition("a")
    assert "a.approval_type='wfs_case_abandon'" in condition
    assert "a.approval_type <> 'wfs_case_abandon'" not in condition
    assert "wc.id::text=a.business_ref" in condition
    assert "wc.source_account_ref=a.source_account_ref" in condition


def test_account_scoped_approval_detail_and_case_actions_enforce_both_identity_keys() -> None:
    import json

    from app.modules.iam.organization_access import ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY

    session = MagicMock()
    session.info = {
        ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY: frozenset({
            ("ACCOUNT-1", "SHARED-UID"),
        })
    }
    session.execute.return_value.mappings.return_value.first.return_value = None
    service = ApprovalService(session)
    with pytest.raises(ApiError) as denied:
        service._record(UUID(int=1), frozenset({"ACCOUNT-1", "ACCOUNT-2"}), lock=True)
    assert denied.value.status_code == 404
    sql, params = session.execute.call_args.args
    assert "wc.source_account_ref=a.source_account_ref" in str(sql)
    assert "granted.account_ref=wc.source_account_ref" in str(sql)
    assert "granted.owner_uid=wc.owner_ref" in str(sql)
    assert "for update" in str(sql)
    assert json.loads(params["org_account_owners"]) == [
        {"account_ref": "ACCOUNT-1", "owner_uid": "SHARED-UID"}
    ]

    session.execute.reset_mock()
    with pytest.raises(ApiError):
        service._case("synthetic", frozenset({"ACCOUNT-1", "ACCOUNT-2"}), lock=True)
    sql, params = session.execute.call_args.args
    assert "granted.account_ref=ops_wfs_fee_anomaly_cases.source_account_ref" in str(sql)
    assert "granted.owner_uid=ops_wfs_fee_anomaly_cases.owner_ref" in str(sql)
    assert json.loads(params["org_account_owners"])[0]["account_ref"] == "ACCOUNT-1"


def test_account_scoped_approval_route_prefers_reviewed_pairs() -> None:
    from app.modules.iam.organization_access import ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY

    session = MagicMock()
    session.info = {}
    principal = Principal(user_id="8", permissions=frozenset({
        "page:data-center:approval-workspace:view",
    }))
    with (
        patch(
            "app.modules.approvals.router.resolve_business_account_owner_pairs",
            return_value=frozenset({("ACCOUNT-1", "SHARED-UID")}),
        ),
        patch("app.modules.approvals.router.resolve_business_owner_refs") as legacy,
    ):
        require_approval_org_scope(principal, session)
    legacy.assert_not_called()
    assert session.info[ORG_OWNER_ACCOUNT_SCOPE_SESSION_KEY] == frozenset({
        ("ACCOUNT-1", "SHARED-UID"),
    })


def test_store_scoped_wfs_approval_detail_and_case_lock_require_account_store() -> None:
    import json

    from app.modules.iam.store_scope import STORE_SCOPE_SESSION_KEY

    session = MagicMock()
    session.info = {
        STORE_SCOPE_SESSION_KEY: frozenset({("ACCOUNT-1", "STORE-1")}),
    }
    session.execute.return_value.mappings.return_value.first.return_value = None
    service = ApprovalService(session)
    with pytest.raises(ApiError):
        service._record(UUID(int=1), frozenset({"ACCOUNT-1", "ACCOUNT-2"}), lock=True)
    statement, params = session.execute.call_args.args
    assert "a.approval_type='wfs_case_abandon'" in str(statement)
    assert "stores.account_ref=wc.source_account_ref" in str(statement)
    assert "stores.store_key=wc.store_id" in str(statement)
    assert json.loads(params["org_account_stores"]) == [
        {"account_ref": "ACCOUNT-1", "store_key": "STORE-1"}
    ]
    session.execute.reset_mock()
    with pytest.raises(ApiError):
        service._case("synthetic-case", frozenset({"ACCOUNT-1", "ACCOUNT-2"}), lock=True)
    statement, params = session.execute.call_args.args
    assert "stores.account_ref=ops_wfs_fee_anomaly_cases.source_account_ref" in str(statement)
    assert "stores.store_key=ops_wfs_fee_anomaly_cases.store_id" in str(statement)
    assert json.loads(params["org_account_stores"])[0]["store_key"] == "STORE-1"


def test_store_scope_is_set_for_approval_requests_even_with_global_org() -> None:
    from app.modules.iam.store_scope import STORE_SCOPE_SESSION_KEY

    session = MagicMock()
    session.info = {}
    principal = Principal(user_id="8", permissions=frozenset({
        "page:data-center:approval-workspace:view",
    }))
    with (
        patch("app.modules.approvals.router.resolve_business_account_owner_pairs", return_value=None),
        patch("app.modules.approvals.router.resolve_business_owner_refs", return_value=None),
        patch(
            "app.modules.approvals.router.resolve_account_store_scope",
            return_value=frozenset({("ACCOUNT-1", "STORE-1")}),
        ),
    ):
        require_approval_org_scope(principal, session)
    assert session.info[STORE_SCOPE_SESSION_KEY] == frozenset({("ACCOUNT-1", "STORE-1")})

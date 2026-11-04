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

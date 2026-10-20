"""Regression contracts for the approval workflow hardening.

All tests use synthetic data and never connect to production systems.
"""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.main import create_app
from app.modules.approvals.schemas import ApprovalQuery
from app.modules.approvals.service import ApprovalService
from app.modules.approvals.workflow import ApprovalWorkflow

CASE_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/approvals/workflow/rules"),
        ("put", "/api/approvals/workflow/rules/{approval_type}"),
        ("get", "/api/approvals/workflow/notifications"),
        ("post", "/api/approvals/workflow/notifications/{notification_id}/read"),
        ("post", "/api/approvals/workflow/requests"),
    ],
)
def test_obsolete_approval_actions_have_no_api_route(method: str, path: str) -> None:
    paths = create_app().openapi()["paths"]
    assert method not in paths.get(path, {})


def test_legacy_list_requires_legacy_mirror() -> None:
    session = MagicMock(spec=Session)
    session.execute.return_value.scalar_one.return_value = 0
    session.execute.return_value.mappings.return_value.all.return_value = []
    response, total = ApprovalService(session).legacy_unverified(
        ApprovalQuery(tab="pending"),
        frozenset({"account-1"}),
    )
    assert total == 0
    assert response.items == []
    assert all(
        "source_kind='legacy_mirror'" in str(call.args[0])
        for call in session.execute.call_args_list
    )


def test_legacy_detail_rejects_regular_case() -> None:
    service = ApprovalService(MagicMock(spec=Session))
    service._case = lambda *_args, **_kwargs: {  # type: ignore[method-assign]
        "source_kind": "live",
        "status": "archive_pending",
        "archive_review_status": "pending",
    }
    with pytest.raises(ApiError):
        service.legacy_detail(CASE_ID, frozenset({"account-1"}))


def test_reattest_rejects_regular_case() -> None:
    service = ApprovalWorkflow(MagicMock(spec=Session))
    service.legacy._case = lambda *_args, **_kwargs: {  # type: ignore[method-assign]
        "source_kind": "live",
        "status": "archive_pending",
        "archive_review_status": "pending",
    }
    with pytest.raises(ApiError):
        service.reattest_wfs(
            CASE_ID,
            frozenset({"account-1"}),
            "applicant-1",
            "other",
            "new explanation",
            "actual evidence",
        )


def test_reattest_snapshots_multistep_rule() -> None:
    session = MagicMock(spec=Session)
    existing = MagicMock()
    existing.first.return_value = None
    rule = MagicMock()
    rule.mappings.return_value.first.return_value = {"required_steps": 2}
    session.execute.side_effect = [existing, rule, MagicMock(), MagicMock()]
    service = ApprovalWorkflow(session)
    service.legacy._case = lambda *_args, **_kwargs: {  # type: ignore[method-assign]
        "id": CASE_ID,
        "source_kind": "legacy_mirror",
        "status": "archive_pending",
        "archive_review_status": "pending",
        "source_account_ref": "account-1",
        "estimated_recover_amount": Decimal("550"),
        "recovered_amount": Decimal("0"),
        "archive_requested_by": "old-actor-unverified",
    }
    service.legacy._event = MagicMock()
    approval_id = service.reattest_wfs(
        CASE_ID,
        frozenset({"account-1"}),
        "present-applicant",
        "other",
        "new reason",
        "new evidence",
    )
    assert UUID(approval_id)
    insert = next(
        call
        for call in session.execute.call_args_list
        if "insert into app_approval_requests" in str(call.args[0])
    )
    snapshot = json.loads(insert.args[1]["snapshot"])
    assert snapshot["approval_policy"]["required_steps"] == 2
    assert insert.args[1]["actor"] == "present-applicant"
    assert insert.args[1]["risk"] == "high"
    session.commit.assert_called_once()

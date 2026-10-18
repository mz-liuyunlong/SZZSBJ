"""Approval contract and authorization boundaries (no production database)."""

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.core.auth import Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.approvals.schemas import (
    ApprovalDecisionWrite,
    ApprovalQuery,
    ApprovalSubmitResult,
    ApprovalSummary,
)
from app.modules.approvals.service import (
    ApprovalService,
    calculate_pending_recovery,
    make_snapshot,
    signature,
)
from app.modules.integration_sync.dependencies import require_source_account_scope


def test_snapshot_excludes_account_scope_and_preserves_full_log() -> None:
    case = {
        "id": UUID("00000000-0000-0000-0000-000000000001"),
        "source_account_ref": "not-exposed-in-snapshot",
        "msku": "private-product",
        "follow_log": "10-01 第1次跟进：提交资料\n10-04 第2次跟进：平台回复",
        "estimated_recover_amount": Decimal("200.00"),
        "recovered_amount": Decimal("0.00"),
        "status": "following",
        "archive_reason": "private",
    }
    snapshot = make_snapshot(case)
    assert snapshot["follow_log"].count("\n") == 1
    assert snapshot["status"] == "following"
    assert snapshot["pending_recover_amount"] == "200.00"
    assert "source_account_ref" not in snapshot
    assert "archive_reason" not in snapshot
    assert signature(snapshot) == signature(dict(reversed(list(snapshot.items()))))


def test_preview_principal_cannot_call_any_approval_routes() -> None:
    app = create_app()
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="preview-operator",
        permissions=frozenset({"warehouse:wfs-fee-alert:write"}),
    )
    app.dependency_overrides[require_source_account_scope] = lambda: frozenset({"account-1"})
    app.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    client = TestClient(app)
    case = "00000000-0000-0000-0000-000000000001"
    assert client.get("/api/approvals").status_code == 403
    assert client.get("/api/approvals/summary").status_code == 403
    assert (
        client.post(
            "/api/approvals/" + case + "/decision",
            json={"decision": "approved", "expected_version": 1},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/approvals/" + case + "/supplement",
            json={"note": "please update", "expected_version": 1},
        ).status_code
        == 403
    )


def _approval_client(monkeypatch: pytest.MonkeyPatch, permissions: set[str]) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user",
        permissions=frozenset(permissions),
    )
    app.dependency_overrides[require_source_account_scope] = lambda: frozenset({"account-1"})
    app.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    monkeypatch.setattr(
        ApprovalService,
        "summary",
        lambda *_args, **_kwargs: ApprovalSummary(
            pending=0,
            high_risk=0,
            info_required=0,
            approved=0,
        ),
    )
    return TestClient(app)


def test_canonical_approval_page_permission_can_read_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _approval_client(
        monkeypatch,
        {"page:data-center:approval-workspace:view"},
    )

    response = client.get("/api/approvals/summary")

    assert response.status_code == 200


def test_approval_page_view_cannot_review_or_supplement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _approval_client(
        monkeypatch,
        {"page:data-center:approval-workspace:view"},
    )
    approval_id = "00000000-0000-0000-0000-000000000001"

    decision = client.post(
        f"/api/approvals/{approval_id}/decision",
        json={"decision": "approved", "expected_version": 1},
    )
    supplement = client.post(
        f"/api/approvals/{approval_id}/supplement",
        json={"note": "synthetic note", "evidence": "", "expected_version": 1},
    )

    assert decision.status_code == 403
    assert supplement.status_code == 403


def test_archive_request_permission_can_submit_wfs_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ApprovalService,
        "submit_wfs",
        lambda *_args, **_kwargs: ApprovalSubmitResult(
            approval_id="00000000-0000-0000-0000-000000000002",
            created=True,
        ),
    )
    client = _approval_client(
        monkeypatch,
        {"action:warehouse:wfs-fee-alert:archive-request"},
    )

    response = client.post(
        "/api/approvals/wfs-cases/00000000-0000-0000-0000-000000000001",
        json={
            "archive_reason_type": "synthetic",
            "archive_reason": "synthetic reason",
            "archive_evidence": "",
        },
    )

    assert response.status_code == 200


def test_super_admin_wildcard_can_use_archive_review_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reviewed: list[bool] = []

    def decide(*_args: object, **kwargs: object) -> None:
        reviewed.append(bool(kwargs.get("may_review") or _args[-1]))

    monkeypatch.setattr(ApprovalService, "decide", decide)
    monkeypatch.setattr(
        ApprovalService,
        "_record",
        lambda *_args, **_kwargs: {"approval_type": "wfs_case_abandon"},
    )
    client = _approval_client(monkeypatch, {"*"})

    response = client.post(
        "/api/approvals/00000000-0000-0000-0000-000000000001/decision",
        json={"decision": "approved", "expected_version": 1},
    )

    assert response.status_code == 200
    assert reviewed == [True]


def test_review_payload_requires_optimistic_version() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ApprovalDecisionWrite(decision="approved")  # type: ignore[call-arg]


def test_operator_list_always_filters_to_own_applications() -> None:
    session = MagicMock(spec=Session)
    count = MagicMock()
    count.scalar_one.return_value = 0
    rows = MagicMock()
    rows.mappings.return_value.all.return_value = []
    session.execute.side_effect = [count, rows]
    service = ApprovalService(session)
    service.list_requests(
        ApprovalQuery(view="all"),
        frozenset({"allowed-account"}),
        actor="operator-1",
        may_review=False,
    )
    assert all("a.applicant_id=:actor" in str(c.args[0]) for c in session.execute.call_args_list)


def test_decision_refuses_user_without_review_permission() -> None:
    service = ApprovalService(MagicMock(spec=Session))
    with pytest.raises(ApiError) as exc:
        service.decide(
            UUID("00000000-0000-0000-0000-000000000001"),
            ApprovalDecisionWrite(decision="approved", expected_version=1),
            frozenset({"allowed-account"}),
            actor="operator",
            may_review=False,
        )
    assert exc.value.status_code == 403


def test_wfs_pending_recovery_is_derived_from_0036_persisted_columns() -> None:
    case = {
        "estimated_recover_amount": Decimal("100.10"),
        "recovered_amount": Decimal("20.15"),
        "status": "following",
    }
    assert calculate_pending_recovery(case) == Decimal("79.95")
    assert make_snapshot(case)["pending_recover_amount"] == "79.95"
    assert calculate_pending_recovery(
        {
            "estimated_recover_amount": Decimal("20"),
            "recovered_amount": Decimal("25"),
        }
    ) == Decimal("0.00")


def test_unverified_legacy_case_is_read_only_and_does_not_create_approval() -> None:
    from app.modules.approvals.schemas import ApprovalQuery

    session = MagicMock(spec=Session)
    count_result = MagicMock()
    count_result.scalar_one.return_value = 1
    rows_result = MagicMock()
    rows_result.mappings.return_value.all.return_value = [
        {
            "id": UUID("00000000-0000-0000-0000-000000000001"),
            "source_account_ref": "account-1",
            "estimated_recover_amount": Decimal("130.00"),
            "recovered_amount": Decimal("0.00"),
            "currency_code": "USD",
            "archive_reason": None,
            "status": "archive_pending",
        }
    ]
    session.execute.side_effect = [count_result, rows_result]
    data, total = ApprovalService(session).legacy_unverified(
        ApprovalQuery(tab="legacy"), frozenset({"account-1"})
    )
    assert total == 1
    assert data.items[0].status == "legacy_unverified"
    assert data.items[0].requires_verification is True
    assert data.items[0].can_review is False
    assert data.items[0].applicant_id is None
    assert data.items[0].submitted_at is None
    assert all("insert into" not in str(c.args[0]).lower() for c in session.execute.call_args_list)
    assert all("update " not in str(c.args[0]).lower() for c in session.execute.call_args_list)
    session.commit.assert_not_called()


def test_non_reviewer_cannot_view_legacy_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _approval_client(monkeypatch, {"page:data-center:approval-workspace:view"})
    response = client.get("/api/approvals?tab=legacy")
    assert response.status_code == 403
    response = client.get("/api/approvals/legacy/00000000-0000-0000-0000-000000000001")
    assert response.status_code == 403


def test_generic_approval_disallows_self_review() -> None:
    from app.modules.approvals.generic import GenericApprovalService

    session = MagicMock(spec=Session)
    approval_id = UUID("00000000-0000-0000-0000-000000000123")
    service = GenericApprovalService(session)
    service.approvals._record = lambda *_args, **_kwargs: {
        "id": approval_id,
        "approval_type": "purchase_exception",
        "business_ref": "source-order",
        "source_account_ref": "account-1",
        "status": "submitted",
        "version": 1,
        "applicant_id": "same-operator",
    }
    with pytest.raises(ApiError):
        service.decide(
            approval_id,
            frozenset({"account-1"}),
            "same-operator",
            "approved",
            "",
            1,
        )
    session.commit.assert_not_called()


def test_generic_bulk_does_not_approve_non_allowlisted_type() -> None:
    from app.modules.approvals.generic import GenericApprovalService

    session = MagicMock(spec=Session)
    rule = MagicMock()
    rule.mappings.return_value.first.return_value = {
        "required_steps": 1,
        "allows_bulk": True,
    }
    session.execute.return_value = rule
    service = GenericApprovalService(session)
    approval_id = UUID("00000000-0000-0000-0000-000000000123")
    service.approvals._record = lambda *_args, **_kwargs: {
        "id": approval_id,
        "approval_type": "wfs_case_abandon",
        "business_ref": str(approval_id),
        "source_account_ref": "account-1",
        "risk_level": "high",
        "status": "submitted",
        "version": 1,
        "applicant_id": "applicant",
        "snapshot": {"approval_policy": {"required_steps": 1}},
    }
    with pytest.raises(ApiError):
        service.approve_bulk(
            [approval_id],
            {str(approval_id): 1},
            frozenset({"account-1"}),
            "reviewer",
            "not safe for bulk",
        )
    session.commit.assert_not_called()



def test_purchase_exception_applicant_can_supplement_with_pmc_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        ApprovalService,
        "_record",
        lambda *_args, **_kwargs: {"approval_type": "purchase_exception"},
    )
    monkeypatch.setattr(
        ApprovalService,
        "supplement",
        lambda _self, _id, _payload, _accounts, actor: calls.append(actor),
    )
    client = _approval_client(
        monkeypatch,
        {
            "page:data-center:approval-workspace:view",
            "action:pmc:purchase-board:override",
        },
    )
    response = client.post(
        "/api/approvals/00000000-0000-0000-0000-000000000123/supplement",
        json={"note": "revised evidence", "evidence": "additional details", "expected_version": 1},
    )
    assert response.status_code == 200
    assert calls == ["synthetic-user"]


def test_page_view_only_cannot_supplement_purchase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        ApprovalService,
        "_record",
        lambda *_args, **_kwargs: {"approval_type": "purchase_exception"},
    )
    monkeypatch.setattr(
        ApprovalService,
        "supplement",
        lambda _self, *_args: calls.append("unexpected"),
    )
    client = _approval_client(
        monkeypatch,
        {"page:data-center:approval-workspace:view"},
    )
    response = client.post(
        "/api/approvals/00000000-0000-0000-0000-000000000123/supplement",
        json={"note": "revised evidence", "evidence": "additional details", "expected_version": 1},
    )
    assert response.status_code == 403
    assert calls == []

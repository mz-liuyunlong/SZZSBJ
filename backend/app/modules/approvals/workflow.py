"""Approval request orchestration and safe legacy WFS re-attestation.

Approval never fabricates a historical application. Conversion is a *new*
application signed by the current authenticated user, with old facts preserved.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.approvals.service import (
    ApprovalService,
    calculate_pending_recovery,
    make_snapshot,
    signature,
)


def conflict() -> None:
    raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409)


class ApprovalWorkflow:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.legacy = ApprovalService(session)

    def reattest_wfs(
        self,
        case_id: UUID,
        accounts: frozenset[str],
        actor: str,
        reason_type: str,
        reason: str,
        evidence: str,
    ) -> str:
        """Creates fresh request without changing imported case or legacy timestamp."""
        if len(reason.strip()) < 5 or len(evidence.strip()) < 5 or not reason_type.strip():
            raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
        case = self.legacy._case(str(case_id), accounts, lock=True)
        if (
            case["source_kind"] != "legacy_mirror"
            or case["status"] != "archive_pending"
            or case["archive_review_status"] != "pending"
        ):
            conflict()
        linked = self.session.execute(
            text("""
            select 1 from app_approval_requests
            where approval_type='wfs_case_abandon' and business_ref=:id
            limit 1
        """),
            {"id": str(case_id)},
        ).first()
        if linked:
            conflict()

        now = datetime.now(UTC)
        approval_id = str(uuid4())
        rule = (
            self.session.execute(
                text("""
                select required_steps from app_approval_rules
                where approval_type='wfs_case_abandon' and is_active=true
            """)
            )
            .mappings()
            .first()
        )
        if rule is None:
            conflict()
        snapshot = make_snapshot(case)
        snapshot["approval_policy"] = {"required_steps": int(rule["required_steps"])}
        amount = calculate_pending_recovery(case)
        risk = (
            "high" if amount >= Decimal("500") else "medium" if amount >= Decimal("100") else "low"
        )
        self.session.execute(
            text("""
            insert into app_approval_requests
              (id, approval_type, business_ref, source_account_ref, applicant_id,
               title, reason, evidence, status, risk_level, snapshot, snapshot_hash,
               submitted_at, updated_at)
            values (:id,'wfs_case_abandon',:case_id,:account,:actor,
              'WFS 历史申请补充核验',:reason,:evidence,'submitted',:risk,
              cast(:snapshot as jsonb),:hash,:now,:now)
        """),
            {
                "id": approval_id,
                "case_id": str(case_id),
                "account": case["source_account_ref"],
                "actor": actor,
                "reason": reason.strip(),
                "evidence": evidence.strip(),
                "risk": risk,
                "snapshot": json.dumps(snapshot, ensure_ascii=False),
                "hash": signature(snapshot),
                "now": now,
            },
        )
        self.session.execute(
            text("""
            insert into app_approval_attestations
              (id,case_id,approval_id,submitted_by,legacy_actor_claim,
               reason_type,reason,evidence,submitted_at)
            values (:id,:case_id,:approval_id,:actor,:legacy_actor,
                    :reason_type,:reason,:evidence,:now)
        """),
            {
                "id": str(uuid4()),
                "case_id": str(case_id),
                "approval_id": approval_id,
                "actor": actor,
                "legacy_actor": case.get("archive_requested_by"),
                "reason_type": reason_type.strip(),
                "reason": reason.strip(),
                "evidence": evidence.strip(),
                "now": now,
            },
        )
        self.legacy._event(
            approval_id,
            "legacy_reattested",
            actor,
            reason.strip(),
            {
                "legacy_case_id": case.get("legacy_case_id"),
                "legacy_actor_unverified": True,
                "legacy_timestamp_unverified": True,
                "original_archive_requested_at": (
                    case["archive_requested_at"].isoformat()
                    if case.get("archive_requested_at")
                    else None
                ),
                "snapshot_hash": signature(snapshot),
            },
        )
        self.session.commit()
        return approval_id

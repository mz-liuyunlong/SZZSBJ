"""Approval request orchestration and safe legacy WFS re-attestation.

Approval never fabricates a historical application. Conversion is a *new*
application signed by the current authenticated user, with old facts preserved.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.approvals.service import ApprovalService, make_snapshot, signature


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
        if len(reason.strip()) < 5 or not reason_type.strip():
            raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
        case = self.legacy._case(str(case_id), accounts, lock=True)
        if case["status"] != "archive_pending" or case["archive_review_status"] != "pending":
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
        snapshot = make_snapshot(case)
        amount = snapshot["pending_recover_amount"]
        risk = "high" if float(amount) >= 500 else "medium" if float(amount) >= 100 else "low"
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

    def available_rules(self) -> list[dict]:
        rows = (
            self.session.execute(
                text("""
            select approval_type,title,required_steps,min_reason_length,
                   due_hours,allows_bulk,is_active,version
            from app_approval_rules order by approval_type
        """)
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def update_rule(
        self,
        kind: str,
        actor: str,
        expected_version: int,
        steps: int,
        due_hours: int,
        allows_bulk: bool,
    ) -> None:
        if kind == "wfs_case_abandon" and allows_bulk:
            conflict()
        previous = self.session.execute(
            text("""
            select required_steps,due_hours,allows_bulk,version
            from app_approval_rules where approval_type=:kind for update
        """),
            {"kind": kind},
        ).mappings().first()
        if previous is None or int(previous["version"]) != expected_version:
            conflict()
        result = self.session.execute(
            text("""
            update app_approval_rules set
                required_steps=:steps,due_hours=:due_hours,
                allows_bulk=:bulk,updated_by=:actor,
                updated_at=now(),version=version+1
            where approval_type=:kind and version=:version
        """),
            {
                "steps": steps,
                "due_hours": due_hours,
                "bulk": allows_bulk,
                "actor": actor,
                "kind": kind,
                "version": expected_version,
            },
        )
        if result.rowcount != 1:
            conflict()
        self.session.execute(
            text("""
            insert into app_approval_rule_events
              (id,approval_type,actor_id,before_policy,after_policy)
            values (:id,:kind,:actor,cast(:before as jsonb),cast(:after as jsonb))
        """),
            {
                "id": str(uuid4()),
                "kind": kind,
                "actor": actor,
                "before": json.dumps(dict(previous)),
                "after": json.dumps({
                    "required_steps": steps,
                    "due_hours": due_hours,
                    "allows_bulk": allows_bulk,
                    "version": expected_version + 1,
                }),
            },
        )
        self.session.commit()

    def inbox(self, actor: str) -> list[dict]:
        return [
            dict(row)
            for row in self.session.execute(
                text("""
            select id::text,approval_id::text,event_key,status,created_at
            from app_approval_notifications
            where recipient_id=:actor
            order by created_at desc limit 100
        """),
                {"actor": actor},
            )
            .mappings()
            .all()
        ]

    def mark_read(self, notification_id: UUID, actor: str) -> bool:
        count = self.session.execute(
            text("""
            update app_approval_notifications
            set status='read',read_at=now()
            where id=:id and recipient_id=:actor and status='unread'
        """),
            {"id": str(notification_id), "actor": actor},
        ).rowcount
        self.session.commit()
        return bool(count)

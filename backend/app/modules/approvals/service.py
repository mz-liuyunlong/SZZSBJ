"""Unified approval service: atomic WFS request/decision and immutable events."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.approvals.schemas import (
    ApprovalDecisionWrite,
    ApprovalDetail,
    ApprovalEventRead,
    ApprovalItem,
    ApprovalListData,
    ApprovalQuery,
    ApprovalSubmitResult,
    ApprovalSummary,
    ApprovalSupplementWrite,
)


def blocked(status: int = 409) -> None:
    raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=status)


def calculate_pending_recovery(case: dict) -> Decimal:
    """Derived amount: 0036 stores estimated and recovered, not a pending column."""
    estimate = Decimal(str(case["estimated_recover_amount"]))
    recovered = Decimal(str(case["recovered_amount"]))
    return max(estimate - recovered, Decimal("0.00"))


def make_snapshot(case: dict) -> dict:
    """Exclude internal access identifiers and select review-relevant facts."""
    fields = (
        "id",
        "store_id",
        "store_name_snapshot",
        "item_id",
        "msku",
        "local_sku_snapshot",
        "product_name_snapshot",
        "owner_name_snapshot",
        "currency_code",
        "manual_unit_fee",
        "actual_unit_fee",
        "unit_fee_diff",
        "affected_units",
        "estimated_recover_amount",
        "pending_recover_amount",
        "claim_amount",
        "recovered_amount",
        "case_nos",
        "first_alert_at",
        "case_opened_at",
        "status",
        "follow_log",
        "latest_follow_note",
        "log_updated_at",
        "reason",
        "remark",
        "walmart_response_summary",
        "evidence_summary",
        "last_follow_at",
    )
    result = {key: case.get(key) for key in fields}
    # WFS Case 0036 exposes pending recovery as a SELECT expression only.
    # Always derive it from persisted columns before making an immutable snapshot.
    result["pending_recover_amount"] = calculate_pending_recovery(case)
    return json.loads(json.dumps(result, ensure_ascii=False, default=str))


def signature(snapshot: dict) -> str:
    return hashlib.sha256(
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class ApprovalService:
    def __init__(self, session: Session):
        self.session = session

    def _case(self, case_id: str, account_refs: frozenset[str], lock: bool = False) -> dict:
        row = (
            self.session.execute(
                text(
                    """
            select * from ops_wfs_fee_anomaly_cases
             where id = :id and source_account_ref = any(:accounts) and is_deleted = false
        """
                    + (" for update" if lock else "")
                ),
                {"id": case_id, "accounts": list(account_refs)},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        return dict(row)

    def _event(
        self, approval_id: str, kind: str, actor: str, note: str = "", detail: dict | None = None
    ):
        self.session.execute(
            text("""
            insert into app_approval_events
              (id, approval_id, event_type, actor_id, note, detail)
            values (:id, :approval_id, :kind, :actor, :note, cast(:detail as jsonb))
        """),
            {
                "id": str(uuid4()),
                "approval_id": approval_id,
                "kind": kind,
                "actor": actor,
                "note": note or None,
                "detail": json.dumps(detail or {}, ensure_ascii=False),
            },
        )

    def submit_wfs(
        self,
        case_id: UUID,
        *,
        reason_type: str,
        reason: str,
        evidence: str,
        account_refs: frozenset[str],
        actor: str,
    ) -> ApprovalSubmitResult:
        if len(reason.strip()) < 5:
            blocked(422)
        case = self._case(str(case_id), account_refs, lock=True)
        if case["status"] not in ("pending_confirm", "following"):
            blocked()
        if self.session.execute(
            text("""
            select 1 from app_approval_requests
             where approval_type='wfs_case_abandon'
               and business_ref=:ref and status in ('submitted','info_required')
        """),
            {"ref": str(case_id)},
        ).first():
            blocked()

        now = datetime.now(UTC)
        rule_row = self.session.execute(text("""
            select required_steps from app_approval_rules
            where approval_type='wfs_case_abandon' and is_active=true
        """)).mappings().first()
        if rule_row is None:
            blocked()
        required_steps = int(rule_row["required_steps"])
        snapshot = make_snapshot(case)
        snapshot["approval_policy"] = {"required_steps": required_steps}
        snapshot_hash = signature(snapshot)
        approval_id = str(uuid4())
        pending_amount = calculate_pending_recovery(case)
        risk = (
            "high"
            if pending_amount >= Decimal("500")
            else "medium"
            if pending_amount >= Decimal("100")
            else "low"
        )
        self.session.execute(
            text("""
            insert into app_approval_requests
              (id, approval_type, business_ref, source_account_ref,
               applicant_id, title, reason, evidence, status, risk_level,
               snapshot, snapshot_hash, submitted_at, updated_at)
            values (:id, 'wfs_case_abandon', :case_id, :account, :actor,
               'WFS Case 放弃跟进', :reason, :evidence, 'submitted', :risk,
               cast(:snapshot as jsonb), :hash, :now, :now)
        """),
            {
                "id": approval_id,
                "case_id": str(case_id),
                "account": case["source_account_ref"],
                "actor": actor,
                "reason": reason,
                "evidence": evidence,
                "risk": risk,
                "snapshot": json.dumps(snapshot, ensure_ascii=False),
                "hash": snapshot_hash,
                "now": now,
            },
        )
        updated = self.session.execute(
            text("""
            update ops_wfs_fee_anomaly_cases set
              status='archive_pending', archive_review_status='pending',
              archive_requested_by=:actor, archive_requested_at=:now,
              archive_reason_type=:reason_type, archive_reason=:reason,
              archive_evidence=nullif(:evidence, ''),
              status_changed_at=:now, status_changed_by=:actor,
              updated_by=:actor, updated_at=:now
            where id=:id and status in ('pending_confirm','following')
        """),
            {
                "id": str(case_id),
                "actor": actor,
                "now": now,
                "reason_type": reason_type,
                "reason": reason,
                "evidence": evidence,
            },
        )
        if updated.rowcount != 1:
            blocked()
        self._event(
            approval_id,
            "submitted",
            actor,
            reason,
            {"business_status_before": case["status"], "snapshot_hash": snapshot_hash},
        )
        self.session.commit()
        return ApprovalSubmitResult(approval_id=approval_id, created=True)

    def _record(self, approval_id: UUID, account_refs: frozenset[str], lock: bool = False) -> dict:
        row = (
            self.session.execute(
                text(
                    """
            select * from app_approval_requests where id=:id
              and source_account_ref=any(:accounts)
        """
                    + (" for update" if lock else "")
                ),
                {
                    "id": str(approval_id),
                    "accounts": list(account_refs),
                },
            )
            .mappings()
            .first()
        )
        if not row:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        return dict(row)

    def _as_item(self, r: dict, actor: str, may_review: bool) -> ApprovalItem:
        snapshot = r["snapshot"] if isinstance(r["snapshot"], dict) else {}
        return ApprovalItem(
            id=str(r["id"]),
            version=r["version"],
            approval_type=r["approval_type"],
            business_ref=r["business_ref"],
            title=r["title"],
            source_account_ref=r["source_account_ref"],
            applicant_id=r["applicant_id"],
            status=r["status"],
            risk_level=r["risk_level"],
            amount=str(snapshot.get("pending_recover_amount"))
            if snapshot.get("pending_recover_amount") is not None
            else None,
            currency_code=snapshot.get("currency_code"),
            submitted_at=r["submitted_at"],
            reviewed_at=r["reviewed_at"],
            reviewed_by=r["reviewed_by"],
            reason=r["reason"],
            can_review=(may_review and r["status"] == "submitted" and r["applicant_id"] != actor),
        )

    def legacy_unverified(
        self, query: ApprovalQuery, account_refs: frozenset[str]
    ) -> tuple[ApprovalListData, int]:
        """Read-only legacy cases: no identity inference and no approval authorization."""
        params: dict = {
            "accounts": list(account_refs),
            "limit": query.page_size,
            "offset": (query.page - 1) * query.page_size,
        }
        where = [
            "c.source_account_ref=any(:accounts)",
            "c.is_deleted=false",
            "c.status='archive_pending'",
            "c.archive_review_status='pending'",
            "not exists (select 1 from app_approval_requests a where "
            "a.approval_type='wfs_case_abandon' and a.business_ref=c.id::text)",
        ]
        if query.approval_type and query.approval_type != "wfs_case_abandon":
            return ApprovalListData(items=[]), 0
        if query.keyword:
            where.append(
                "(c.store_name_snapshot ilike :keyword or c.case_nos ilike :keyword "
                "or c.owner_name_snapshot ilike :keyword or c.item_id ilike :keyword)"
            )
            params["keyword"] = f"%{query.keyword.strip()}%"
        if query.risk_level:
            where.append(
                "(case when greatest(c.estimated_recover_amount-c.recovered_amount,0)>=500 "
                "then 'high' when greatest(c.estimated_recover_amount-c.recovered_amount,0)>=100 "
                "then 'medium' else 'low' end)=:risk"
            )
            params["risk"] = query.risk_level
        condition = " and ".join(where)
        total = int(
            self.session.execute(
                text(f"select count(*) from ops_wfs_fee_anomaly_cases c where {condition}"),
                params,
            ).scalar_one()
        )
        rows = (
            self.session.execute(
                text(f"""
            select c.* from ops_wfs_fee_anomaly_cases c where {condition}
            order by c.archive_requested_at desc nulls last, c.id
            limit :limit offset :offset
        """),
                params,
            )
            .mappings()
            .all()
        )
        items = []
        for record in rows:
            case = dict(record)
            pending = calculate_pending_recovery(case)
            risk = "high" if pending >= 500 else "medium" if pending >= 100 else "low"
            items.append(
                ApprovalItem(
                    id=str(case["id"]),
                    version=1,
                    approval_type="wfs_case_abandon",
                    business_ref=str(case["id"]),
                    title="WFS 历史待核验 · 放弃跟进",
                    source_account_ref=case["source_account_ref"],
                    applicant_id=None,
                    status="legacy_unverified",
                    risk_level=risk,
                    amount=str(pending),
                    currency_code=case["currency_code"],
                    submitted_at=None,
                    reviewed_at=None,
                    reviewed_by=None,
                    reason=case.get("archive_reason") or "历史记录缺少正式申请理由，需人工核验",
                    can_review=False,
                    requires_verification=True,
                )
            )
        return ApprovalListData(items=items), total

    def legacy_detail(self, case_id: UUID, account_refs: frozenset[str]) -> ApprovalDetail:
        """Read-only display; do not fabricate approvals, applicants, or events."""
        record = self._case(str(case_id), account_refs)
        if record["status"] != "archive_pending" or record["archive_review_status"] != "pending":
            blocked()
        linked = self.session.execute(
            text("""
            select 1 from app_approval_requests where approval_type='wfs_case_abandon'
              and business_ref=:case_id limit 1
        """),
            {"case_id": str(case_id)},
        ).first()
        if linked:
            blocked()
        pending = calculate_pending_recovery(record)
        risk = "high" if pending >= 500 else "medium" if pending >= 100 else "low"
        item = ApprovalItem(
            id=str(case_id),
            version=1,
            approval_type="wfs_case_abandon",
            business_ref=str(case_id),
            title="WFS 历史待核验 · 放弃跟进",
            source_account_ref=record["source_account_ref"],
            applicant_id=None,
            status="legacy_unverified",
            risk_level=risk,
            amount=str(pending),
            currency_code=record["currency_code"],
            submitted_at=None,
            reviewed_at=None,
            reviewed_by=None,
            reason=record.get("archive_reason") or "历史记录缺少正式申请理由，需人工核验",
            can_review=False,
            requires_verification=True,
        )
        return ApprovalDetail(
            **item.model_dump(),
            snapshot=make_snapshot(record),
            evidence=record.get("archive_evidence"),
            current_case=make_snapshot(record),
            data_changed=False,
            can_supplement=False,
            events=[],
        )

    def list_requests(
        self, query: ApprovalQuery, account_refs: frozenset[str], actor: str, may_review: bool
    ) -> tuple[ApprovalListData, int]:
        if query.tab == "legacy":
            return self.legacy_unverified(query, account_refs)
        status_clause = (
            "a.status in ('submitted','info_required')"
            if query.tab == "pending"
            else "a.status='approved'"
            if query.tab == "approved"
            else "a.status='rejected'"
        )
        where = ["a.source_account_ref=any(:accounts)", status_clause]
        params: dict = {
            "accounts": list(account_refs),
            "actor": actor,
            "limit": query.page_size,
            "offset": (query.page - 1) * query.page_size,
        }
        if not may_review:
            where.append("a.applicant_id=:actor")
        elif query.view == "created":
            where.append("a.applicant_id=:actor")
        elif query.view == "mine":
            where.append("a.applicant_id<>:actor")
        if query.approval_type:
            where.append("a.approval_type=:kind")
            params["kind"] = query.approval_type
        if query.risk_level:
            where.append("a.risk_level=:risk")
            params["risk"] = query.risk_level
        if query.keyword:
            where.append("(a.title ilike :keyword or a.reason ilike :keyword)")
            params["keyword"] = f"%{query.keyword.strip()}%"
        condition = " and ".join(where)
        total = self.session.execute(
            text(f"select count(*) from app_approval_requests a where {condition}"), params
        ).scalar_one()
        rows = (
            self.session.execute(
                text(f"""
            select a.* from app_approval_requests a where {condition}
            order by case a.risk_level when 'high' then 0 when 'medium' then 1 else 2 end,
                     a.submitted_at desc, a.id
            limit :limit offset :offset
        """),
                params,
            )
            .mappings()
            .all()
        )
        return ApprovalListData(
            items=[self._as_item(dict(r), actor, may_review) for r in rows]
        ), int(total)

    def summary(
        self, account_refs: frozenset[str], actor: str, may_review: bool
    ) -> ApprovalSummary:
        row = (
            self.session.execute(
                text("""
            select
              count(*) filter (where status='submitted') pending,
              count(*) filter (where status='submitted' and risk_level='high') high_risk,
              count(*) filter (where status='info_required') info_required,
              count(*) filter (where status='approved') approved
            from app_approval_requests where source_account_ref=any(:accounts)
              and (:may_review or applicant_id=:actor)
        """),
                {"accounts": list(account_refs), "actor": actor, "may_review": may_review},
            )
            .mappings()
            .one()
        )
        legacy = self.session.execute(
            text("""
            select count(*) from ops_wfs_fee_anomaly_cases c
            where c.source_account_ref=any(:accounts) and c.is_deleted=false
              and c.status='archive_pending' and c.archive_review_status='pending'
              and not exists (select 1 from app_approval_requests a
               where a.approval_type='wfs_case_abandon' and a.business_ref=c.id::text)
        """),
            {"accounts": list(account_refs)},
        ).scalar_one()
        return ApprovalSummary(**dict(row), legacy_unverified=int(legacy))

    def detail(
        self, approval_id: UUID, account_refs: frozenset[str], actor: str, may_review: bool
    ) -> ApprovalDetail:
        record = self._record(approval_id, account_refs)
        if not may_review and record["applicant_id"] != actor:
            raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
        item = self._as_item(record, actor, may_review)
        events = (
            self.session.execute(
                text("""
            select event_type, actor_id, note, created_at
              from app_approval_events where approval_id=:id
             order by created_at, id
        """),
                {"id": str(approval_id)},
            )
            .mappings()
            .all()
        )
        case = self._case(record["business_ref"], account_refs)
        current = make_snapshot(case)
        saved = record["snapshot"]
        # Submission switches WFS status to archive_pending, which is not
        # itself a stale change. Compare meaningful fields excluding status.
        changed = any(
            current.get(k) != saved.get(k)
            for k in saved
            if k not in ("status", "archive_reason", "archive_reason_type", "approval_policy")
        )
        return ApprovalDetail(
            **item.model_dump(),
            snapshot=saved,
            evidence=record["evidence"],
            current_case=current,
            data_changed=changed,
            can_supplement=(
                record["status"] == "info_required" and record["applicant_id"] == actor
            ),
            events=[ApprovalEventRead(**dict(e)) for e in events],
        )

    def decide(
        self,
        approval_id: UUID,
        payload: ApprovalDecisionWrite,
        account_refs: frozenset[str],
        actor: str,
        may_review: bool,
    ):
        if not may_review:
            raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
        if payload.decision in ("rejected", "info_required") and len(payload.note) < 5:
            blocked(422)
        r = self._record(approval_id, account_refs, lock=True)
        if r["status"] != "submitted" or r["version"] != payload.expected_version:
            blocked()
        if r["applicant_id"] == actor:
            raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
        if r["approval_type"] != "wfs_case_abandon":
            blocked(422)
        case = self._case(r["business_ref"], account_refs, lock=True)
        if case["status"] != "archive_pending" or case["archive_review_status"] != "pending":
            blocked()
        snapshot = r["snapshot"]
        current = make_snapshot(case)
        if any(
            current.get(k) != snapshot.get(k)
            for k in snapshot
            if k not in ("status", "archive_reason", "archive_reason_type")
        ):
            blocked()
        current_step = self.session.execute(text("""
            select count(*) from app_approval_step_decisions
            where approval_id=:id and decision='approved'
        """), {"id": str(approval_id)}).scalar_one()
        repeated = self.session.execute(text("""
            select 1 from app_approval_step_decisions
            where approval_id=:id and reviewer_id=:actor
        """), {"id": str(approval_id), "actor": actor}).first()
        if repeated:
            blocked()
        required_steps = int(snapshot.get("approval_policy", {}).get("required_steps", 1))
        final_step = int(current_step) + 1 >= required_steps
        if payload.decision == "approved":
            self.session.execute(text("""
                insert into app_approval_step_decisions
                    (id,approval_id,step_number,reviewer_id,decision,note)
                values (:id,:approval_id,:step,:actor,'approved',:note)
            """), {
                "id": str(uuid4()), "approval_id": str(approval_id),
                "step": int(current_step) + 1, "actor": actor,
                "note": payload.note or None,
            })
        if payload.decision == "approved" and not final_step:
            advanced = self.session.execute(text("""
                update app_approval_requests set
                    version=version+1,updated_at=now()
                where id=:id and status='submitted' and version=:version
            """), {"id": str(approval_id), "version": payload.expected_version})
            if advanced.rowcount != 1:
                blocked()
            self._event(str(approval_id), "step_approved", actor, payload.note, {
                "step": int(current_step) + 1, "required_steps": required_steps,
            })
            self.session.commit()
            return
        if payload.decision == "info_required":
            new_status = "info_required"
        elif payload.decision == "approved":
            new_status = "approved"
        else:
            new_status = "rejected"
        now = datetime.now(UTC)
        changed = self.session.execute(
            text("""
            update app_approval_requests set status=:status, reviewed_by=:actor,
               reviewed_at=:now, review_note=:note, version=version+1, updated_at=:now
             where id=:id and status='submitted' and version=:expected
        """),
            {
                "status": new_status,
                "actor": actor,
                "now": now,
                "note": payload.note or None,
                "id": str(approval_id),
                "expected": payload.expected_version,
            },
        )
        if changed.rowcount != 1:
            blocked()
        if payload.decision != "info_required":
            case_status = "archived" if payload.decision == "approved" else "following"
            updated = self.session.execute(
                text("""
                update ops_wfs_fee_anomaly_cases set
                  status=:case_status, archive_review_status=:review_status,
                  archive_reviewed_by=:actor, archive_reviewed_at=:now,
                  archive_review_note=nullif(:note,''),
                  archived_at=case when :case_status='archived' then :now else archived_at end,
                  last_reopened_at=case when :case_status='following'
                      then :now else last_reopened_at end,
                  reopen_count=reopen_count+case when :case_status='following' then 1 else 0 end,
                  status_changed_at=:now, status_changed_by=:actor,
                  updated_by=:actor, updated_at=:now
                where id=:id and status='archive_pending'
                  and archive_review_status='pending'
                  and archive_requested_by is distinct from :actor
            """),
                {
                    "case_status": case_status,
                    "review_status": new_status,
                    "actor": actor,
                    "note": payload.note,
                    "now": now,
                    "id": r["business_ref"],
                },
            )
            if updated.rowcount != 1:
                blocked()
        self._event(str(approval_id), payload.decision, actor, payload.note)
        self.session.commit()

    def supplement(
        self,
        approval_id: UUID,
        payload: ApprovalSupplementWrite,
        account_refs: frozenset[str],
        actor: str,
    ):
        r = self._record(approval_id, account_refs, lock=True)
        if (
            r["status"] != "info_required"
            or r["version"] != payload.expected_version
            or r["applicant_id"] != actor
        ):
            blocked()
        case = self._case(r["business_ref"], account_refs, lock=True)
        if case["status"] != "archive_pending":
            blocked()
        now = datetime.now(UTC)
        self.session.execute(
            text("""
            update app_approval_requests set
              status='submitted', reason=:note, evidence=:evidence,
              reviewed_at=null, reviewed_by=null, review_note=null,
              version=version+1, updated_at=:now
            where id=:id and status='info_required'
        """),
            {
                "note": payload.note,
                "evidence": payload.evidence,
                "now": now,
                "id": str(approval_id),
            },
        )
        self._event(str(approval_id), "resubmitted", actor, payload.note)
        self.session.commit()

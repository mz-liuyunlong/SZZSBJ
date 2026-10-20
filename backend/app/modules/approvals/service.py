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
        rule_row = (
            self.session.execute(
                text("""
            select required_steps from app_approval_rules
            where approval_type='wfs_case_abandon' and is_active=true
        """)
            )
            .mappings()
            .first()
        )
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
            follow_log=r.get("follow_log"),
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
            "c.source_kind='legacy_mirror'",
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
                    follow_log=case.get("follow_log"),
                )
            )
        return ApprovalListData(items=items), total

    @staticmethod
    def _case_version(case: dict) -> int:
        # PostgreSQL timestamptz: compatible with floor(extract(epoch)*1e6).
        dt = case["updated_at"]
        return int(dt.timestamp()) * 1_000_000 + dt.microsecond

    @staticmethod
    def _case_pending_status(case: dict) -> str:
        return (
            "info_required"
            if str(case.get("archive_review_note") or "").startswith("[资料补充请求]")
            else "submitted"
        )

    def legacy_detail(
        self, case_id: UUID, account_refs: frozenset[str], actor: str = ""
    ) -> ApprovalDetail:
        """Current pending WFS Case detail, with truthful source identity fields."""
        record = self._case(str(case_id), account_refs)
        pending_case = (
            record["status"] == "archive_pending" and record["archive_review_status"] == "pending"
        )
        completed_case = record["archive_review_status"] in ("approved", "rejected") and str(
            record.get("archive_review_note") or ""
        ).startswith("[当前审批]")
        if record["source_kind"] != "legacy_mirror" or not (pending_case or completed_case):
            blocked()
        if self.session.execute(
            text("""select 1 from app_approval_requests
            where approval_type='wfs_case_abandon' and business_ref=:ref limit 1"""),
            {"ref": str(case_id)},
        ).first():
            blocked()
        pending = calculate_pending_recovery(record)
        risk = "high" if pending >= 500 else "medium" if pending >= 100 else "low"
        applicant = record.get("archive_requested_by") or None
        status = (
            self._case_pending_status(record) if pending_case else record["archive_review_status"]
        )
        detail_item = ApprovalItem(
            id=str(case_id),
            version=self._case_version(record),
            approval_type="wfs_case_abandon",
            business_ref=str(case_id),
            title="WFS 费用异常 · 放弃跟进",
            source_account_ref=record["source_account_ref"],
            applicant_id=applicant,
            status=status,
            risk_level=risk,
            amount=str(pending),
            currency_code=record["currency_code"],
            submitted_at=record.get("archive_requested_at"),
            reviewed_at=record.get("archive_reviewed_at") if completed_case else None,
            reviewed_by=record.get("archive_reviewed_by") if completed_case else None,
            reason=record.get("archive_reason") or "当前 Case 未记录申请原因，请核查业务依据",
            can_review=bool(actor) and pending_case and applicant != actor,
            requires_verification=False,
            case_review=True,
        )
        case_view = make_snapshot(record)
        # Not a submitted snapshot: this is the currently persisted case.
        events = []
        if (
            completed_case
            and record.get("archive_reviewed_by")
            and record.get("archive_reviewed_at")
        ):
            events = [
                ApprovalEventRead(
                    event_type="approved" if status == "approved" else "rejected",
                    actor_id=record["archive_reviewed_by"],
                    note=str(record.get("archive_review_note") or "").removeprefix("[当前审批] "),
                    created_at=record["archive_reviewed_at"],
                )
            ]
        return ApprovalDetail(
            **detail_item.model_dump(),
            snapshot=case_view,
            evidence=record.get("archive_evidence"),
            current_case=case_view,
            data_changed=False,
            can_supplement=False,
            events=events,
        )

    def review_pending_case(
        self,
        case_id: UUID,
        payload: ApprovalDecisionWrite,
        account_refs: frozenset[str],
        actor: str,
    ) -> None:
        """Review current WFS archive request without creating a phantom applicant.

        One transaction, locked case row, account scope, version check and
        a formal-request-exists check prevent duplicate or stale decisions.
        This path intentionally does NOT generate an attested application.
        """
        if payload.decision in ("rejected", "info_required") and len(payload.note) < 5:
            blocked(422)
        case = self._case(str(case_id), account_refs, lock=True)
        if (
            case["source_kind"] != "legacy_mirror"
            or case["status"] != "archive_pending"
            or case["archive_review_status"] != "pending"
            or self._case_version(case) != payload.expected_version
        ):
            blocked()
        if self.session.execute(
            text("""select 1 from app_approval_requests
            where approval_type='wfs_case_abandon' and business_ref=:ref limit 1"""),
            {"ref": str(case_id)},
        ).first():
            blocked()
        applicant = case.get("archive_requested_by")
        if applicant and applicant == actor:
            raise ApiError(
                code=ErrorCode.FORBIDDEN,
                status_code=403,
                details={"reason": "SELF_REVIEW_FORBIDDEN"},
            )
        if not applicant and not payload.acknowledge_missing_applicant:
            blocked(422)
        now = datetime.now(UTC)
        decision = payload.decision
        if decision == "info_required":
            # The Case stays pending. The note is stored as a distinct
            # request for more information; do not pretend final review.
            result = self.session.execute(
                text("""
                update ops_wfs_fee_anomaly_cases set
                  archive_review_note = :note,
                  follow_log = concat_ws(E'\n', nullif(follow_log, ''), :event),
                  updated_at = :now, updated_by = :actor
                where id=:id and source_account_ref=any(:accounts)
                  and is_deleted=false and status='archive_pending'
                  and archive_review_status='pending'
                  and floor(extract(epoch from updated_at)*1000000)::bigint=:version
            """),
                {
                    "id": str(case_id),
                    "accounts": list(account_refs),
                    "note": "[资料补充请求] " + payload.note.strip(),
                    "event": (
                        f"[当前审批·要求补资料] {now.isoformat()} {actor}: {payload.note.strip()}"
                    ),
                    "now": now,
                    "actor": actor,
                    "version": payload.expected_version,
                },
            )
        else:
            approved = decision == "approved"
            result = self.session.execute(
                text("""
                update ops_wfs_fee_anomaly_cases set
                  status=:status, archive_review_status=:review_status,
                  archive_reviewed_by=:actor, archive_reviewed_at=:now,
                  archive_review_note=:note,
                  archived_at=case when :approved then :now else archived_at end,
                  last_reopened_at=case when :approved then last_reopened_at else :now end,
                  reopen_count=case when :approved then reopen_count else reopen_count+1 end,
                  status_changed_at=:now, status_changed_by=:actor,
                  updated_at=:now, updated_by=:actor,
                  follow_log=concat_ws(E'\n',nullif(follow_log,''),:event)
                where id=:id and source_account_ref=any(:accounts)
                  and is_deleted=false and status='archive_pending'
                  and archive_review_status='pending'
                  and floor(extract(epoch from updated_at)*1000000)::bigint=:version
            """),
                {
                    "id": str(case_id),
                    "accounts": list(account_refs),
                    "status": "archived" if approved else "following",
                    "review_status": "approved" if approved else "rejected",
                    "approved": approved,
                    "actor": actor,
                    "now": now,
                    "note": "[当前审批] " + (payload.note.strip() or "审核通过"),
                    "event": (
                        f"[当前审批·{'通过' if approved else '驳回'}] "
                        f"{now.isoformat()} {actor}: {payload.note.strip() or '审核通过'}"
                    ),
                    "version": payload.expected_version,
                },
            )
        if result.rowcount != 1:
            self.session.rollback()
            blocked()
        self.session.commit()

    def _list_pending_with_legacy(
        self,
        query: ApprovalQuery,
        account_refs: frozenset[str],
        actor: str,
        is_admin: bool,
    ) -> tuple[ApprovalListData, int]:
        """Page formal approvals and current WFS Case decisions without duplicates."""
        params: dict = {
            "accounts": list(account_refs),
            "actor": actor,
            "is_admin": is_admin,
            "limit": query.page_size,
            "offset": (query.page - 1) * query.page_size,
        }
        formal_status = (
            "a.status in ('submitted','info_required')"
            if query.tab == "pending"
            else "a.status='approved'"
            if query.tab == "approved"
            else "a.status='rejected'"
        )
        formal_where = [
            "a.source_account_ref=any(:accounts)",
            formal_status,
            "(a.approval_type='wfs_case_abandon' or a.applicant_id=:actor or :is_admin)",
        ]
        case_status = (
            ["c.status='archive_pending'", "c.archive_review_status='pending'"]
            if query.tab == "pending"
            else [
                "c.archive_review_status=:case_review_status",
                "c.archive_review_note like '[当前审批]%'",
            ]
        )
        if query.tab != "pending":
            params["case_review_status"] = query.tab
        legacy_where = [
            "c.source_account_ref=any(:accounts)",
            "c.is_deleted=false",
            "c.source_kind='legacy_mirror'",
            *case_status,
            "not exists (select 1 from app_approval_requests a where "
            "a.approval_type='wfs_case_abandon' and a.business_ref=c.id::text)",
        ]
        if query.view == "mine":
            formal_where.append("a.applicant_id<>:actor")
            if query.tab == "pending":
                legacy_where.append("c.archive_requested_by is distinct from :actor")
            else:
                legacy_where.append("c.archive_reviewed_by=:actor")
        if query.approval_type:
            params["kind"] = query.approval_type
            formal_where.append("a.approval_type=:kind")
            if query.approval_type != "wfs_case_abandon":
                legacy_where.append("false")
        pending_amount = "greatest(c.estimated_recover_amount-c.recovered_amount,0)"
        legacy_risk = (
            f"case when {pending_amount}>=500 then 'high' "
            f"when {pending_amount}>=100 then 'medium' else 'low' end"
        )
        if query.risk_level:
            params["risk"] = query.risk_level
            formal_where.append("a.risk_level=:risk")
            legacy_where.append(f"({legacy_risk})=:risk")
        if query.keyword:
            params["keyword"] = f"%{query.keyword.strip()}%"
            formal_where.append("(a.title ilike :keyword or a.reason ilike :keyword)")
            legacy_where.append(
                "(c.store_name_snapshot ilike :keyword or c.case_nos ilike :keyword "
                "or c.owner_name_snapshot ilike :keyword or c.item_id ilike :keyword "
                "or c.archive_reason ilike :keyword)"
            )
        params["case_tab"] = query.tab
        formal_condition = " and ".join(formal_where)
        legacy_condition = " and ".join(legacy_where)
        combined = f"""
            select a.id::text as id, a.version, a.approval_type, a.business_ref,
                   a.title, a.source_account_ref, a.applicant_id, a.status,
                   a.risk_level,
                   a.snapshot->>'pending_recover_amount' as amount,
                   a.snapshot->>'currency_code' as currency_code,
                   a.submitted_at, a.reviewed_at, a.reviewed_by, a.reason,
                   (a.status='submitted' and a.applicant_id<>:actor) as can_review,
                   false as requires_verification, false as case_review,
                   a.submitted_at as sort_time,
                   (select wc.follow_log from ops_wfs_fee_anomaly_cases wc
                     where a.approval_type='wfs_case_abandon'
                       and wc.id::text=a.business_ref
                       and wc.source_account_ref=a.source_account_ref
                       and wc.is_deleted=false
                     limit 1) as follow_log
            from app_approval_requests a where {formal_condition}
            union all
            select c.id::text,
                   floor(extract(epoch from c.updated_at)*1000000)::bigint,
                   'wfs_case_abandon', c.id::text,
                   'WFS 费用异常 · 放弃跟进', c.source_account_ref,
                   nullif(c.archive_requested_by, ''),
                   case when :case_tab='approved' then 'approved'
                        when :case_tab='rejected' then 'rejected'
                        when coalesce(c.archive_review_note,'') like '[资料补充请求]%'
                        then 'info_required' else 'submitted' end,
                   ({legacy_risk}), {pending_amount}::text, c.currency_code,
                   c.archive_requested_at, c.archive_reviewed_at, c.archive_reviewed_by,
                   coalesce(nullif(c.archive_reason, ''), '未填写申请原因'),
                   (:case_tab='pending' and c.archive_requested_by is distinct from :actor),
                   false, true,
                   case when :case_tab='pending' then c.archive_requested_at
                        else c.archive_reviewed_at end, c.follow_log as follow_log
            from ops_wfs_fee_anomaly_cases c where {legacy_condition}
        """
        total = int(
            self.session.execute(
                text(f"select count(*) from ({combined}) pending_items"), params
            ).scalar_one()
        )
        rows = (
            self.session.execute(
                text(f"""
                select
                    pending_items.id,
                    pending_items.version,
                    pending_items.approval_type,
                    pending_items.business_ref,
                    pending_items.title,
                    pending_items.source_account_ref,
                    pending_items.applicant_id,
                    pending_items.status,
                    pending_items.risk_level,
                    pending_items.amount,
                    pending_items.currency_code,
                    pending_items.submitted_at,
                    pending_items.reviewed_at,
                    pending_items.reviewed_by,
                    pending_items.reason,
                    pending_items.can_review,
                    pending_items.requires_verification,
                    pending_items.case_review,
                    pending_items.follow_log,
                    coalesce(c_meta.case_opened_at, c_meta.first_alert_at) as case_opened_at,
                    c_meta.follow_count
                from ({combined}) pending_items
                left join ops_wfs_fee_anomaly_cases c_meta
                  on c_meta.id::text = pending_items.business_ref
                 and pending_items.approval_type = 'wfs_case_abandon'
                order by case risk_level when 'high' then 0
                                         when 'medium' then 1 else 2 end,
                         sort_time desc nulls last, pending_items.id
                limit :limit offset :offset
                """),
                params,
            )
            .mappings()
            .all()
        )
        return ApprovalListData(items=[ApprovalItem(**dict(row)) for row in rows]), total

    def list_requests(
        self,
        query: ApprovalQuery,
        account_refs: frozenset[str],
        actor: str,
        may_review: bool,
        is_admin: bool = False,
    ) -> tuple[ApprovalListData, int]:
        if may_review and query.view != "created":
            return self._list_pending_with_legacy(query, account_refs, actor, is_admin)
        status_clause = (
            "a.status in ('submitted','info_required')"
            if query.tab == "pending"
            else "a.status='approved'"
            if query.tab == "approved"
            else "a.status='rejected'"
        )
        where = [
            "a.source_account_ref=any(:accounts)",
            status_clause,
            "(a.approval_type='wfs_case_abandon' or a.applicant_id=:actor or :is_admin)",
        ]
        params: dict = {
            "accounts": list(account_refs),
            "actor": actor,
            "is_admin": is_admin,
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
                          select a.*,
                  (select wc.follow_log from ops_wfs_fee_anomaly_cases wc
                    where a.approval_type='wfs_case_abandon'
                      and wc.id::text=a.business_ref
                      and wc.source_account_ref=a.source_account_ref
                      and wc.is_deleted=false
                    limit 1) as follow_log
              from app_approval_requests a where {condition}
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
        self,
        account_refs: frozenset[str],
        actor: str,
        may_review: bool,
        is_admin: bool = False,
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
              and (approval_type='wfs_case_abandon' or applicant_id=:actor or :is_admin)
        """),
                {
                    "accounts": list(account_refs),
                    "actor": actor,
                    "may_review": may_review,
                    "is_admin": is_admin,
                },
            )
            .mappings()
            .one()
        )
        legacy = 0
        legacy_high_risk = 0
        legacy_pending = 0
        legacy_info = 0
        legacy_approved = 0
        if may_review:
            legacy_stats = (
                self.session.execute(
                    text("""
                    select
                      count(*) filter (where c.archive_review_status='pending') as total,
                      count(*) filter (where c.archive_review_status='pending'
                        and coalesce(c.archive_review_note,'')
                        not like '[资料补充请求]%') as still_pending,
                      count(*) filter (where c.archive_review_status='pending'
                        and coalesce(c.archive_review_note,'')
                        like '[资料补充请求]%') as info_required,
                      count(*) filter (where c.archive_review_status='pending'
                        and greatest(
                          c.estimated_recover_amount-c.recovered_amount,0
                        ) >= 500) as high_risk,
                      count(*) filter (where c.archive_review_status='approved') as approved
                    from ops_wfs_fee_anomaly_cases c
                    where c.source_account_ref=any(:accounts) and c.is_deleted=false
                      and c.source_kind='legacy_mirror'
                      and ((c.status='archive_pending' and c.archive_review_status='pending')
                        or (c.archive_review_status='approved'
                          and c.archive_review_note like '[当前审批]%'))
                      and not exists (select 1 from app_approval_requests a
                       where a.approval_type='wfs_case_abandon' and a.business_ref=c.id::text)
                """),
                    {"accounts": list(account_refs)},
                )
                .mappings()
                .one()
            )
            legacy = int(legacy_stats["total"])
            legacy_pending = int(legacy_stats.get("still_pending", legacy))
            legacy_info = int(legacy_stats.get("info_required", 0))
            legacy_approved = int(legacy_stats.get("approved", 0))
            legacy_high_risk = int(legacy_stats["high_risk"])
        counts = dict(row)
        counts["pending"] = int(counts["pending"]) + legacy_pending
        counts["high_risk"] = int(counts["high_risk"]) + legacy_high_risk
        counts["info_required"] = int(counts["info_required"]) + legacy_info
        counts["approved"] = int(counts["approved"]) + legacy_approved
        return ApprovalSummary(**counts, legacy_unverified=legacy)

    def detail(
        self,
        approval_id: UUID,
        account_refs: frozenset[str],
        actor: str,
        may_review: bool,
        is_admin: bool = False,
    ) -> ApprovalDetail:
        record = self._record(approval_id, account_refs)
        if (not may_review and record["applicant_id"] != actor) or (
            record["approval_type"] != "wfs_case_abandon"
            and not is_admin
            and record["applicant_id"] != actor
        ):
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
        if record["approval_type"] in (
            "purchase_exception",
            "finance_exception",
            "access_change",
            "operations_plan_ack",
        ):
            return ApprovalDetail(
                **item.model_dump(),
                snapshot=record["snapshot"],
                evidence=record["evidence"],
                current_case=None,
                data_changed=False,
                can_supplement=(
                    record["status"] == "info_required" and record["applicant_id"] == actor
                ),
                events=[ApprovalEventRead(**dict(e)) for e in events],
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
            if k not in ("status", "archive_reason", "archive_reason_type", "approval_policy")
        ):
            blocked()
        current_step = self.session.execute(
            text("""
            select count(*) from app_approval_step_decisions
            where approval_id=:id and decision='approved'
        """),
            {"id": str(approval_id)},
        ).scalar_one()
        repeated = self.session.execute(
            text("""
            select 1 from app_approval_step_decisions
            where approval_id=:id and reviewer_id=:actor
        """),
            {"id": str(approval_id), "actor": actor},
        ).first()
        if repeated:
            blocked()
        if payload.decision == "info_required" and int(current_step) > 0:
            blocked()
        required_steps = int(snapshot.get("approval_policy", {}).get("required_steps", 1))
        final_step = int(current_step) + 1 >= required_steps
        if payload.decision == "approved":
            self.session.execute(
                text("""
                insert into app_approval_step_decisions
                    (id,approval_id,step_number,reviewer_id,decision,note)
                values (:id,:approval_id,:step,:actor,'approved',:note)
            """),
                {
                    "id": str(uuid4()),
                    "approval_id": str(approval_id),
                    "step": int(current_step) + 1,
                    "actor": actor,
                    "note": payload.note or None,
                },
            )
        if payload.decision == "approved" and not final_step:
            advanced = self.session.execute(
                text("""
                update app_approval_requests set
                    version=version+1,updated_at=now()
                where id=:id and status='submitted' and version=:version
            """),
                {"id": str(approval_id), "version": payload.expected_version},
            )
            if advanced.rowcount != 1:
                blocked()
            self._event(
                str(approval_id),
                "step_approved",
                actor,
                payload.note,
                {
                    "step": int(current_step) + 1,
                    "required_steps": required_steps,
                },
            )
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
            # An unverified historical actor cannot replace the new applicant identity.
            fresh_attestation = bool(
                self.session.execute(
                    text("""
                    select 1 from app_approval_attestations
                    where approval_id=:approval_id and submitted_by=:applicant
                    limit 1
                """),
                    {"approval_id": str(approval_id), "applicant": r["applicant_id"]},
                ).first()
            )
            case_status = "archived" if payload.decision == "approved" else "following"
            updated = self.session.execute(
                text("""
                update ops_wfs_fee_anomaly_cases set
                  status=CAST(:case_status AS varchar(32)), archive_review_status=:review_status,
                  archive_reviewed_by=:actor, archive_reviewed_at=:now,
                  archive_review_note=nullif(:note,''),
                  archived_at=case
                  when CAST(:case_status AS varchar(32))='archived'
                  then :now else archived_at end,
                  last_reopened_at=case when CAST(:case_status AS varchar(32))='following'
                      then :now else last_reopened_at end,
                  reopen_count=reopen_count+case
                  when CAST(:case_status AS varchar(32))='following'
                  then 1 else 0 end,
                  status_changed_at=:now, status_changed_by=:actor,
                  updated_by=:actor, updated_at=:now
                where id=:id and status='archive_pending'
                  and archive_review_status='pending'
                  and (:fresh_attestation or archive_requested_by is distinct from :actor)
            """),
                {
                    "case_status": case_status,
                    "review_status": new_status,
                    "actor": actor,
                    "note": payload.note,
                    "now": now,
                    "id": r["business_ref"],
                    "fresh_attestation": fresh_attestation,
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
        if r["approval_type"] == "wfs_case_abandon":
            case = self._case(r["business_ref"], account_refs, lock=True)
            if case["status"] != "archive_pending":
                blocked()
        else:
            from app.modules.approvals.generic import GenericApprovalService

            actual = GenericApprovalService(self.session)._source(
                r["approval_type"],
                r["business_ref"],
                r["source_account_ref"],
            )
            if signature(actual) != signature(r["snapshot"]["source"]):
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

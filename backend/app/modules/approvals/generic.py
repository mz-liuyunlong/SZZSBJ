"""Safe generic business approvals: approval != execution.

Adapters validate immutable source identifiers in PostgreSQL and do not issue
writes to purchase, profit or IAM tables.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.approvals.service import ApprovalService, blocked, signature

BUSINESS_TYPES = frozenset(
    {"purchase_exception", "finance_exception", "access_change", "operations_plan_ack"}
)


class GenericApprovalService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.approvals = ApprovalService(session)

    def _source(self, kind: str, source_ref: str, account: str) -> dict:
        if kind == "purchase_exception":
            row = (
                self.session.execute(
                    text("""
                select order_sn, status, amount_total, purchase_currency, source_account_ref
                from dwd_purchase_order where order_sn=:ref and source_account_ref=:account
            """),
                    {"ref": source_ref, "account": account},
                )
                .mappings()
                .first()
            )
        elif kind == "finance_exception":
            # Source record identity uses date + SKU; business-day fact is immutable
            # for this request, but financial execution is NEVER done here.
            date, sep, sku = source_ref.partition("|")
            if not sep or not date or not sku:
                blocked(422)
            from datetime import date as date_type

            try:
                date_type.fromisoformat(date)
            except ValueError:
                blocked(422)
            row = (
                self.session.execute(
                    text("""
                select business_date_la, local_sku, source_account_ref
                from mart_order_profit_sku_day
                where business_date_la=cast(:date as date)
                  and local_sku=:sku and source_account_ref=:account
            """),
                    {"date": date, "sku": sku, "account": account},
                )
                .mappings()
                .first()
            )
        elif kind == "operations_plan_ack":
            try:
                UUID(source_ref)
            except ValueError:
                blocked(422)
            row = (
                self.session.execute(
                    text("""
                select id::text as id,source_account_ref,plan_status,operation_status,
                       stock_status,owner_ref,target_sales_amount,target_gross_profit_amount
                from ops_operation_product_plans
                where id=:ref and source_account_ref=:account
            """),
                    {"ref": source_ref, "account": account},
                )
                .mappings()
                .first()
            )
        elif kind == "access_change":
            if not source_ref.isdecimal():
                blocked(422)
            row = (
                self.session.execute(
                    text("""
                select id, username, is_active from app_users
                where id=:id
            """),
                    {"id": int(source_ref)},
                )
                .mappings()
                .first()
            )
        else:
            blocked(422)
        if not row:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        return json.loads(json.dumps(dict(row), ensure_ascii=False, default=str))

    def submit(
        self,
        kind: str,
        source_ref: str,
        account: str,
        accounts: frozenset[str],
        actor: str,
        reason: str,
        evidence: str,
    ) -> str:
        if kind not in BUSINESS_TYPES or account not in accounts:
            raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
        if len(reason.strip()) < 5 or len(source_ref) > 128:
            blocked(422)
        rule = (
            self.session.execute(
                text("""
            select required_steps,min_reason_length from app_approval_rules
            where approval_type=:kind and is_active=true
        """),
                {"kind": kind},
            )
            .mappings()
            .first()
        )
        if not rule or len(reason.strip()) < rule["min_reason_length"]:
            blocked(422)
        source = self._source(kind, source_ref, account)
        policy = {"required_steps": int(rule["required_steps"])}
        snapshot = {"source": source, "approval_policy": policy, "execution_pending": True}
        now = datetime.now(UTC)
        approval_id = str(uuid4())
        self.session.execute(
            text("""
            insert into app_approval_requests
              (id,approval_type,business_ref,source_account_ref,applicant_id,
               title,reason,evidence,status,risk_level,snapshot,snapshot_hash,
               submitted_at,updated_at)
            values (:id,:kind,:ref,:account,:actor,:title,:reason,:evidence,
                    'submitted',:risk,cast(:snapshot as jsonb),:hash,:now,:now)
        """),
            {
                "id": approval_id,
                "kind": kind,
                "ref": source_ref,
                "account": account,
                "actor": actor,
                "title": {
                    "purchase_exception": "采购异常处理申请",
                    "finance_exception": "财务例外处理申请",
                    "access_change": "权限变更申请",
                    "operations_plan_ack": "运营计划事项确认",
                }[kind],
                "reason": reason.strip(),
                "evidence": evidence.strip(),
                "snapshot": json.dumps(snapshot, ensure_ascii=False),
                "hash": signature(snapshot),
                "now": now,
            },
        )
        self.approvals._event(
            approval_id,
            "submitted",
            actor,
            reason.strip(),
            {
                "execution_pending": True,
                "source_hash": signature(source),
            },
        )
        self.session.commit()
        return approval_id

    def decide(
        self,
        approval_id: UUID,
        accounts: frozenset[str],
        actor: str,
        decision: str,
        note: str,
        expected_version: int,
    ) -> None:
        if decision not in ("approved", "rejected", "info_required"):
            blocked(422)
        if decision != "approved" and len(note.strip()) < 5:
            blocked(422)
        row = self.approvals._record(approval_id, accounts, lock=True)
        if row["approval_type"] not in BUSINESS_TYPES or row["status"] != "submitted":
            blocked()
        if row["version"] != expected_version or row["applicant_id"] == actor:
            blocked()
        snapshot = row["snapshot"]
        actual = self._source(row["approval_type"], row["business_ref"], row["source_account_ref"])
        if signature(snapshot["source"]) != signature(actual):
            blocked()
        prev = self.session.execute(
            text("""
            select count(*) from app_approval_step_decisions
            where approval_id=:approval_id and decision='approved'
        """),
            {"approval_id": str(approval_id)},
        ).scalar_one()
        already = self.session.execute(
            text("""
            select 1 from app_approval_step_decisions
            where approval_id=:approval_id and reviewer_id=:actor
        """),
            {"approval_id": str(approval_id), "actor": actor},
        ).first()
        if already:
            blocked()
        if decision == "info_required" and int(prev) > 0:
            blocked()
        step = int(prev) + 1
        required_steps = int(snapshot["approval_policy"]["required_steps"])
        if decision == "approved":
            self.session.execute(
                text("""
                insert into app_approval_step_decisions
                  (id,approval_id,step_number,reviewer_id,decision,note)
                values (:id,:approval_id,:step,:actor,'approved',:note)
            """),
                {
                    "id": str(uuid4()),
                    "approval_id": str(approval_id),
                    "step": step,
                    "actor": actor,
                    "note": note.strip(),
                },
            )
        completed = decision != "approved" or step >= required_steps
        status = decision if completed else "submitted"
        updated = self.session.execute(
            text("""
            update app_approval_requests
            set status=:status,reviewed_by=:actor,reviewed_at=:reviewed_at,
                review_note=:note,updated_at=now(),version=version+1
            where id=:id and version=:expected_version and status='submitted'
        """),
            {
                "id": str(approval_id),
                "status": status,
                "actor": actor if completed else None,
                "reviewed_at": datetime.now(UTC) if completed else None,
                "note": note.strip() if completed else None,
                "expected_version": expected_version,
            },
        )
        if updated.rowcount != 1:
            blocked()
        self.approvals._event(
            str(approval_id),
            decision if completed else "step_approved",
            actor,
            note.strip(),
            {
                "step": step,
                "required_steps": required_steps,
                "executed": False,
            },
        )
        self.approvals._notify_applicant(str(approval_id), decision)
        self.session.commit()

    def approve_bulk(
        self,
        ids: list[UUID],
        expected_versions: dict[str, int],
        accounts: frozenset[str],
        actor: str,
        note: str,
    ) -> int:
        """Single transaction; all cases validated under locks before any update."""
        if not 1 <= len(ids) <= 20 or len(set(ids)) != len(ids) or len(note.strip()) < 5:
            blocked(422)
        if set(expected_versions) != {str(i) for i in ids}:
            blocked(422)
        rule = (
            self.session.execute(
                text("""
            select required_steps,allows_bulk from app_approval_rules
            where approval_type='operations_plan_ack' and is_active=true
        """)
            )
            .mappings()
            .first()
        )
        if not rule or not rule["allows_bulk"] or int(rule["required_steps"]) != 1:
            blocked()
        rows = [self.approvals._record(i, accounts, lock=True) for i in sorted(ids)]
        for row in rows:
            if (
                row["approval_type"] != "operations_plan_ack"
                or row["status"] != "submitted"
                or row["risk_level"] != "low"
                or row["applicant_id"] == actor
                or row["version"] != expected_versions[str(row["id"])]
                or row["snapshot"]["approval_policy"].get("required_steps") != 1
            ):
                blocked()
            previous = self.session.execute(
                text("""
                select 1 from app_approval_step_decisions
                where approval_id=:id
            """),
                {"id": str(row["id"])},
            ).first()
            if previous:
                blocked()
            current = self._source(
                row["approval_type"], row["business_ref"], row["source_account_ref"]
            )
            if signature(current) != signature(row["snapshot"]["source"]):
                blocked()
        for row in rows:
            approval_id = str(row["id"])
            self.session.execute(
                text("""
                insert into app_approval_step_decisions
                  (id,approval_id,step_number,reviewer_id,decision,note)
                values (:id,:approval_id,1,:actor,'approved',:note)
            """),
                {
                    "id": str(uuid4()),
                    "approval_id": approval_id,
                    "actor": actor,
                    "note": note.strip(),
                },
            )
            changed = self.session.execute(
                text("""
                update app_approval_requests set
                  status='approved',reviewed_by=:actor,reviewed_at=now(),
                  review_note=:note,version=version+1,updated_at=now()
                where id=:id and version=:expected and status='submitted'
            """),
                {
                    "id": approval_id,
                    "actor": actor,
                    "note": note.strip(),
                    "expected": expected_versions[approval_id],
                },
            )
            if changed.rowcount != 1:
                blocked()
            self.approvals._event(
                approval_id,
                "approved",
                actor,
                note.strip(),
                {"batch": True, "executed": False},
            )
            self.approvals._notify_applicant(approval_id, "approved")
        self.session.commit()
        return len(rows)

"""Atomic local decisions. Locks serialize with publication; no provider write exists.

The source snapshot does not prove historical approval coverage. All commands are
restricted to real local verification records, with a second guard on the DB URL.
"""

import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from app.core.api import ApiError, ErrorCode
from app.core.config import get_settings
from app.modules.pmc_domestic.packing_models import (
    PackingAllocation,
    PackingEvent,
    PackingOrder,
)
from app.modules.pmc_domestic.packing_repository import (
    PackingRepository,
    matches,
    order_read,
)
from app.modules.pmc_domestic.packing_rules import fingerprint
from app.modules.pmc_domestic.packing_schemas import (
    CandidateList,
    OrderList,
    OrderRead,
    PackingSummary,
)


def conflict(reason):
    raise ApiError(
        code=ErrorCode.INVALID_REQUEST, status_code=409, details={"reason": reason}
    )


def missing():
    raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)


class PackingService:
    def __init__(self, session):
        self.session = session
        self.repo = PackingRepository(session)

    def pending_rows(self, q, accounts):
        rows = [r for r in self.repo.candidates(accounts) if matches(r, q)]
        rows.sort(
            key=lambda r: (
                r.candidate_created_on.isoformat() if r.candidate_created_on else "",
                str(r.id),
            ),
            reverse=getattr(q, "sort", "created_desc") == "created_desc",
        )
        return rows

    def pending(self, q, accounts):
        rows = self.pending_rows(q, accounts)
        start = (q.page - 1) * q.page_size
        return CandidateList(items=rows[start : start + q.page_size], total=len(rows))

    def summary(self, q, accounts):
        rows = self.pending_rows(q, accounts)
        orders = [
            r for r in self.repo.orders(accounts) if matches(order_read(r).snapshot, q)
        ]
        return PackingSummary(
            pending=len(rows),
            overdue=sum(r.overdue is True for r in rows),
            blocked=sum(not r.can_approve for r in rows),
            approved=sum(r.status == "approved" for r in orders),
            rejected=sum(r.status == "rejected" for r in orders),
        )

    def orders(self, q, accounts):
        rows = [
            order_read(r)
            for r in self.repo.orders(accounts)
            if matches(order_read(r).snapshot, q)
        ]
        start = (q.page - 1) * q.page_size
        return OrderList(items=rows[start : start + q.page_size], total=len(rows))

    def order(self, ident, accounts):
        row = self.session.scalar(
            select(PackingOrder).where(
                PackingOrder.id == ident,
                PackingOrder.source_account_ref.in_(accounts),
                PackingOrder.warehouse_id == "16168",
            )
        )
        if row is None:
            missing()
        return row

    def lock(self, key):
        value = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], signed=True)
        self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": value})

    def guard_local(self):
        bind = self.session.get_bind()
        u = bind.engine.url
        env = get_settings().app_env.value
        allowed = (env == "local" and u.database == "szzsbj_dev") or (
            env == "test" and u.database == "szzsbj_test"
        )
        if not allowed or u.host != "127.0.0.1" or u.port != 55432 or u.query:
            raise ApiError(
                code=ErrorCode.FORBIDDEN,
                status_code=403,
                details={"reason": "LOCAL_DATABASE_ONLY"},
            )

    def decide(self, ident, cmd, kind, actor, accounts):
        if cmd.source_account_ref not in accounts:
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
        self.guard_local()
        s = self.session
        try:
            s.execute(text("SET LOCAL lock_timeout='5s'"))
            s.execute(text("SET LOCAL statement_timeout='30s'"))
            self.lock(f"packing-command:{cmd.source_account_ref}:{cmd.idempotency_key}")
            request = {
                "kind": kind,
                "candidate_id": str(ident),
                "actor_uid": actor,
                **cmd.model_dump(mode="json"),
            }
            digest = fingerprint(request)
            prior = s.scalar(
                select(PackingEvent).where(
                    PackingEvent.source_account_ref == cmd.source_account_ref,
                    PackingEvent.idempotency_key == cmd.idempotency_key,
                )
            )
            if prior:
                if prior.request_hash != digest:
                    conflict("IDEMPOTENCY_KEY_REUSED")
                result = OrderRead.model_validate(prior.response_json)
                s.commit()
                return result
            # Same exact lock as InboundPublisher: the current publication cannot
            # switch between source revalidation and allocation commit.
            self.lock(f"{cmd.source_account_ref}\0{cmd.warehouse_id}")
            if s.scalar(
                select(PackingOrder.id).where(
                    PackingOrder.source_account_ref == cmd.source_account_ref,
                    PackingOrder.candidate_id == ident,
                )
            ):
                conflict("ALREADY_DECIDED")
            candidate = next(
                (
                    r
                    for r in self.repo.candidates(frozenset({cmd.source_account_ref}))
                    if r.id == ident and r.warehouse_id == cmd.warehouse_id
                ),
                None,
            )
            if candidate is None:
                missing()
            if candidate.candidate_version != cmd.candidate_version:
                conflict("SOURCE_CHANGED")
            if kind == "approve":
                if not candidate.can_approve:
                    conflict("CANDIDATE_BLOCKED")
                if (
                    candidate.available_quantity is None
                    or cmd.qty > candidate.available_quantity
                ):
                    conflict("INSUFFICIENT_STOCK")
            pk = None
            if kind == "approve":
                day = datetime.now(ZoneInfo("Asia/Shanghai")).date()
                serial = s.scalar(
                    text(
                        "INSERT INTO ops_domestic_pk_sequences (business_date,last_value) "
                        "VALUES (:day,1) ON CONFLICT (business_date) DO UPDATE "
                        "SET last_value=ops_domestic_pk_sequences.last_value+1 "
                        "WHERE ops_domestic_pk_sequences.last_value<999 RETURNING last_value"
                    ),
                    {"day": day},
                )
                if serial is None:
                    conflict("PK_DAILY_LIMIT")
                pk = f"PK{day:%y%m%d}-{serial:03d}"
            customs = getattr(cmd, "customs", "default")
            row = PackingOrder(
                source_account_ref=cmd.source_account_ref,
                warehouse_id=cmd.warehouse_id,
                candidate_id=ident,
                inbound_order_sn=candidate.inbound_order_sn,
                sku=candidate.sku,
                store_id=candidate.store_id,
                item_id=candidate.item_id,
                pk=pk,
                qty=cmd.qty if kind == "approve" else None,
                customs_value={"default": None, "declare": True, "skip": False}[
                    customs
                ],
                customs_src="unknown" if customs == "default" else "manual",
                rwh=getattr(cmd, "rwh", None),
                is_test=True,
                status="approved" if kind == "approve" else "rejected",
                version=1,
                source_publication_id=candidate.publication_id,
                source_board_id=candidate.board_id,
                snapshot_json=candidate.model_dump(mode="json"),
                actor_uid=actor,
                note=getattr(cmd, "note", None),
            )
            s.add(row)
            s.flush()
            if kind == "approve":
                s.add(
                    PackingAllocation(
                        order_id=row.id,
                        source_account_ref=row.source_account_ref,
                        warehouse_id=row.warehouse_id,
                        source_publication_id=row.source_publication_id,
                        source_board_id=row.source_board_id,
                        qty=cmd.qty,
                    )
                )
            result = order_read(row)
            s.add(
                PackingEvent(
                    order_id=row.id,
                    source_account_ref=row.source_account_ref,
                    idempotency_key=cmd.idempotency_key,
                    actor_uid=actor,
                    event_kind=kind,
                    order_version=1,
                    request_hash=digest,
                    request_json=request,
                    response_json=result.model_dump(mode="json"),
                )
            )
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise

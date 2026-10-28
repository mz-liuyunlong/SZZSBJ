"""Atomic packing decisions. Locks serialize with publication; no provider write exists.

The source snapshot does not prove historical approval coverage. Writes stay on the
database selected by APP_ENV: local and test remain verification records, and
production writes formal records on the production database only.
"""

import hashlib
from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text

from app.core.api import ApiError, ErrorCode
from app.core.config import get_settings
from app.modules.data_pages.models import LingxingStoreDimension as Store
from app.modules.data_pages.models import WalmartListingDimension as Listing
from app.modules.pmc_domestic.packing_models import (
    PackingAllocation,
    PackingEvent,
    PackingOrder,
    PackingPendingEdit,
)
from app.modules.pmc_domestic.packing_repository import (
    PackingRepository,
    matches,
    order_read,
)
from app.modules.pmc_domestic.packing_rules import fingerprint, listing_version
from app.modules.pmc_domestic.packing_schemas import (
    ApproveCommand,
    Candidate,
    CandidateList,
    EditDraftSaved,
    EditOptions,
    ListingChoice,
    OrderList,
    OrderRead,
    PackingSummary,
)


def conflict(reason):
    raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409, details={"reason": reason})


LOCAL_DATABASE_HOST = "127.0.0.1"
LOCAL_DATABASE_PORT = 55432


def database_write_allowed(env, url) -> bool:
    """Local and test stay on the isolated databases. Production uses its own server database."""
    if url.query or not url.host or not url.database:
        return False
    if env == "local":
        return (
            url.host == LOCAL_DATABASE_HOST
            and url.port == LOCAL_DATABASE_PORT
            and url.database == "szzsbj_dev"
        )
    if env == "test":
        return (
            url.host == LOCAL_DATABASE_HOST
            and url.port == LOCAL_DATABASE_PORT
            and url.database == "szzsbj_test"
        )
    if env == "production":
        return not (
            url.host == LOCAL_DATABASE_HOST
            and url.port == LOCAL_DATABASE_PORT
            and url.database in {"szzsbj_dev", "szzsbj_test"}
        )
    return False


def verification_record(env: str) -> bool:
    """Production orders are formal. Local and test orders stay marked as verification records."""
    return env != "production"


def missing():
    raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)


class PackingService:
    def __init__(self, session):
        self.session = session
        self.repo = PackingRepository(session)

    def pending_rows(self, q, accounts):
        rows = [r for r in self.all_candidates(accounts) if matches(r, q)]
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
        orders = [r for r in self.repo.orders(accounts) if matches(order_read(r).snapshot, q)]
        return PackingSummary(
            pending=len(rows),
            overdue=sum(r.overdue is True for r in rows),
            blocked=sum(not r.can_approve for r in rows),
            approved=sum(r.status == "approved" for r in orders),
            rejected=sum(r.status == "rejected" for r in orders),
        )

    def orders(self, q, accounts):
        rows = [
            order_read(r) for r in self.repo.orders(accounts) if matches(order_read(r).snapshot, q)
        ]
        rows.sort(key=lambda r: (r.created_at, str(r.id)), reverse=q.sort == "created_desc")
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
        url = self.session.get_bind().engine.url
        if not database_write_allowed(get_settings().app_env.value, url):
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
                **cmd.model_dump(mode="json", exclude={"passcode"}),
            }
            digest = fingerprint(request)
            prior = s.scalar(
                select(PackingEvent).where(
                    PackingEvent.source_account_ref == cmd.source_account_ref,
                    PackingEvent.idempotency_key == cmd.idempotency_key,
                )
            )
            from app.modules.pmc_domestic.packing_models import PackingManualRequest

            if s.scalar(
                select(PackingManualRequest.id).where(
                    PackingManualRequest.source_account_ref == cmd.source_account_ref,
                    PackingManualRequest.idempotency_key == cmd.idempotency_key,
                )
            ):
                conflict("IDEMPOTENCY_KEY_REUSED")
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
                    PackingOrder.status != "voided",
                )
            ):
                conflict("ALREADY_DECIDED")
            candidate = next(
                (
                    r
                    for r in self.all_candidates(frozenset({cmd.source_account_ref}))
                    if r.id == ident and r.warehouse_id == cmd.warehouse_id
                ),
                None,
            )
            if candidate is None:
                missing()
            if candidate.candidate_version != cmd.candidate_version:
                conflict("SOURCE_CHANGED")
            original_candidate = candidate.model_copy(deep=True)
            if candidate.origin == "manual":
                from app.modules.pmc_domestic.packing_models import PackingManualRequest
                from app.modules.pmc_domestic.packing_schemas import Candidate

                draft = s.get(PackingManualRequest, candidate.id)
                original_candidate = Candidate.model_validate(draft.source_snapshot_json)
            if kind == "approve":
                candidate = self.final_candidate(candidate, cmd)
                if not candidate.can_approve:
                    conflict("CANDIDATE_BLOCKED")
                if candidate.available_quantity is None or cmd.qty > candidate.available_quantity:
                    conflict("INSUFFICIENT_STOCK")
            identity_key = fingerprint(
                [str(candidate.board_id), candidate.store_id, candidate.item_id]
            )
            if candidate.origin != "manual" and s.scalar(
                select(PackingOrder.id).where(
                    PackingOrder.source_account_ref == cmd.source_account_ref,
                    PackingOrder.source_board_id == candidate.board_id,
                    PackingOrder.store_id == candidate.store_id,
                    PackingOrder.item_id == candidate.item_id,
                    PackingOrder.status != "voided",
                )
            ):
                conflict("FINAL_IDENTITY_ALREADY_DECIDED")
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
            verify = verification_record(get_settings().app_env.value)
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
                customs_value=candidate.customs_default
                if customs == "default"
                else customs == "declare",
                customs_src=candidate.customs_default_src if customs == "default" else "manual",
                rwh=getattr(cmd, "rwh", None),
                is_test=verify,
                status="approved" if kind == "approve" else "rejected",
                version=1,
                source_publication_id=candidate.publication_id,
                source_board_id=candidate.board_id,
                snapshot_json=candidate.model_dump(mode="json"),
                source_snapshot_json=original_candidate.model_dump(mode="json"),
                final_identity_key=identity_key if candidate.origin != "manual" else None,
                business_test=verify,
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
            if kind == "approve":
                pending_edit = s.get(PackingPendingEdit, ident)
                if pending_edit is not None:
                    s.delete(pending_edit)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise

    def listing_rows(self, candidate):
        """Same eligibility as Listing 管理: published WFS rows with a product link."""
        return list(
            self.session.scalars(
                select(Listing).where(
                    Listing.source_account_ref == candidate.source_account_ref,
                    Listing.local_sku == candidate.sku,
                    Listing.standard_status == "PUBLISHED",
                    Listing.fulfillment_type == "1",
                    Listing.item_url.isnot(None),
                    func.length(func.trim(Listing.item_url)) > 0,
                )
            )
        )

    def edit_options(self, ident, account, accounts):
        if account not in accounts:
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
        candidate = next(
            (r for r in self.all_candidates(frozenset({account})) if r.id == ident), None
        )
        if candidate is None:
            missing()
        stores = {
            r.store_id: r.store_name
            for r in self.session.scalars(select(Store).where(Store.source_account_ref == account))
        }
        return EditOptions(
            candidate=candidate,
            cross_store_proof_available=candidate.available_quantity is not None,
            listings=[
                ListingChoice(
                    store_id=r.store_id,
                    store_name=stores.get(r.store_id),
                    item_id=r.item_id,
                    gtin=r.gtin,
                    msku=r.msku,
                    listing_version=listing_version(r),
                    cross_store=r.store_id != candidate.store_id,
                )
                for r in self.listing_rows(candidate)
            ],
        )

    def final_candidate(self, candidate, cmd):
        target_store = cmd.target_store_id or candidate.store_id
        target_item = cmd.target_item_id or candidate.item_id
        edited = target_store != candidate.store_id or target_item != candidate.item_id
        if edited and len((cmd.edit_reason or "").strip()) < 2:
            conflict("EDIT_REASON_REQUIRED")
        # Owner decision 2026-10-21: the published inbound row is the allocation
        # basis. A new target Listing never moves or duplicates source inventory.
        rows = [
            r
            for r in self.listing_rows(candidate)
            if r.store_id == target_store and r.item_id == target_item
        ]
        if len(rows) != 1:
            conflict("LISTING_MISSING_OR_AMBIGUOUS")
        listing = rows[0]
        if listing.fulfillment_type != "1":
            conflict("WFS_NOT_CONVERTED")
        if (edited and not cmd.listing_version) or (
            cmd.listing_version and cmd.listing_version != listing_version(listing)
        ):
            conflict("LISTING_CHANGED")
        blocked = [
            r
            for r in candidate.blocked_reasons
            if r
            not in (
                "ELIGIBLE_LISTING_MISSING",
                "WFS_NOT_CONVERTED",
                "GTIN_INVALID",
                "MSKU_MISSING",
                "STORE_UNKNOWN",
            )
        ]
        if not listing.gtin or not listing.gtin.isdigit() or len(listing.gtin) != 14:
            blocked.append("GTIN_INVALID")
        if not listing.msku:
            blocked.append("MSKU_MISSING")
        names = set(
            self.session.scalars(
                select(Store.store_name).where(
                    Store.source_account_ref == candidate.source_account_ref,
                    Store.store_id == target_store,
                )
            )
        )
        target_name = next(iter(names)) if len(names) == 1 else None
        return candidate.model_copy(
            update={
                "store_id": listing.store_id,
                "store_name": target_name,
                "item_id": listing.item_id,
                "gtin": listing.gtin,
                "msku": listing.msku,
                "can_approve": not blocked,
                "blocked_reasons": blocked,
            }
        )

    def _base_candidates(self, accounts):
        from app.modules.pmc_domestic.draft_numbers import attach_draft_numbers
        from app.modules.pmc_domestic.packing_manual_service import ManualPackingService

        rows = self.repo.candidates(accounts) + ManualPackingService(self).pending(accounts)
        attach_draft_numbers(self.session, rows, accounts)
        return rows

    def _apply_pending_edits(self, rows, accounts):
        if not accounts:
            return rows
        auto_ids = [r.id for r in rows if r.origin != "manual"]
        if not auto_ids:
            return rows
        drafts = {
            d.candidate_id: d
            for d in self.session.scalars(
                select(PackingPendingEdit).where(
                    PackingPendingEdit.source_account_ref.in_(accounts),
                    PackingPendingEdit.candidate_id.in_(auto_ids),
                )
            )
        }
        merged: list[Candidate] = []
        for row in rows:
            draft = drafts.get(row.id)
            if draft is None or row.origin == "manual":
                merged.append(row)
                continue
            if draft.base_candidate_version != row.candidate_version:
                blocked = list(row.blocked_reasons)
                if "EDIT_DRAFT_STALE" not in blocked:
                    blocked.append("EDIT_DRAFT_STALE")
                merged.append(
                    row.model_copy(
                        update={
                            "edit_draft_stale": True,
                            "can_approve": False,
                            "blocked_reasons": blocked,
                        }
                    )
                )
                continue
            snap = Candidate.model_validate(draft.draft_snapshot_json)
            merged.append(
                snap.model_copy(
                    update={
                        "default_quantity": draft.requested_qty,
                        "manual_customs": draft.customs,
                        "edit_draft_pending": True,
                    }
                )
            )
        return merged

    def save_pending_edit(self, ident, cmd, actor, accounts):
        if cmd.source_account_ref not in accounts:
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
        self.guard_local()
        candidate = next(
            (r for r in self._base_candidates(frozenset({cmd.source_account_ref})) if r.id == ident),
            None,
        )
        if candidate is None:
            missing()
        if candidate.origin == "manual":
            conflict("MANUAL_DRAFT_UNSUPPORTED")
        if candidate.candidate_version != cmd.candidate_version:
            conflict("SOURCE_CHANGED")
        merged = self.final_candidate(
            candidate,
            ApproveCommand(
                source_account_ref=cmd.source_account_ref,
                warehouse_id=cmd.warehouse_id,
                candidate_version=cmd.candidate_version,
                idempotency_key=uuid4(),
                qty=cmd.qty,
                customs=cmd.customs,
                target_store_id=cmd.target_store_id,
                target_item_id=cmd.target_item_id,
                listing_version=cmd.listing_version,
                edit_reason=cmd.edit_reason,
            ),
        )
        if not merged.can_approve:
            conflict("CANDIDATE_BLOCKED")
        if merged.available_quantity is None or cmd.qty > merged.available_quantity:
            conflict("INSUFFICIENT_STOCK")
        s = self.session
        row = s.get(PackingPendingEdit, ident) or PackingPendingEdit(
            candidate_id=ident,
            source_account_ref=cmd.source_account_ref,
        )
        row.base_candidate_version = candidate.candidate_version
        row.requested_qty = cmd.qty
        row.customs = cmd.customs
        row.edit_reason = cmd.edit_reason
        row.draft_snapshot_json = merged.model_dump(mode="json")
        row.actor_uid = actor
        row.updated_at = datetime.now(UTC)
        s.add(row)
        s.commit()
        snapshot = merged.model_copy(
            update={
                "default_quantity": cmd.qty,
                "manual_customs": cmd.customs,
                "edit_draft_pending": True,
            }
        )
        return EditDraftSaved(candidate_id=ident, snapshot=snapshot)

    def all_candidates(self, accounts):
        return self._apply_pending_edits(self._base_candidates(accounts), accounts)

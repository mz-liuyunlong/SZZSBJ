"""Atomic packing decisions. Locks serialize with publication; no provider write exists.

The source snapshot does not prove historical approval coverage. Writes stay on the
database selected by APP_ENV: local and test remain verification records, and
production writes formal records on the production database only.
"""

import hashlib
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select, text

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
from app.modules.pmc_domestic.packing_rules import (
    fingerprint,
    listing_blocked_reasons,
    listing_version,
)
from app.modules.pmc_domestic.packing_schemas import (
    Candidate,
    CandidateList,
    EditDraftSaved,
    EditOptions,
    ListingChoice,
    ListingHit,
    ListingSearch,
    OrderList,
    OrderRead,
    PackingSummary,
    SplitLine,
)

MAX_SPLIT_LINES = 10
LISTING_SEARCH_LIMIT = 20


def split_child_id(base, number):
    """Deterministic id for split line ``number`` (>= 2): candidate or idempotency key.

    Line 1 keeps the original value, so the active-candidate unique index, replay by
    idempotency key and the pending list (which hides decided candidates) are unchanged.
    """
    return uuid5(NAMESPACE_URL, f"szzsbj:packing-split:{base}:{number}")


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
            if kind == "approve" and len(candidate.split_lines) > 1:
                return self._approve_split(
                    ident, cmd, candidate, original_candidate, actor, request, digest
                )
            if kind == "approve":
                candidate = self.final_candidate(candidate, cmd)
                if not candidate.can_approve:
                    conflict("CANDIDATE_BLOCKED")
                if candidate.available_quantity is None or cmd.qty > candidate.available_quantity:
                    conflict("INSUFFICIENT_STOCK")
            row = self._create_order(
                ident,
                cmd,
                kind,
                candidate,
                original_candidate,
                actor,
                qty=cmd.qty if kind == "approve" else None,
            )
            result = order_read(row)
            if row.pk:
                result = result.model_copy(update={"split_pks": [row.pk]})
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
            # Both terminal decisions invalidate the editable draft. The order
            # snapshots and event remain the immutable record in this transaction.
            pending_edit = s.get(PackingPendingEdit, ident)
            if pending_edit is not None:
                s.delete(pending_edit)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise

    def _next_pk(self):
        day = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        serial = self.session.scalar(
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
        return f"PK{day:%y%m%d}-{serial:03d}"

    def _create_order(self, candidate_id, cmd, kind, candidate, original_candidate, actor, *, qty):
        """Insert one decided packing order (+ stock allocation when approved)."""
        s = self.session
        identity_key = fingerprint([str(candidate.board_id), candidate.store_id, candidate.item_id])
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
        pk = self._next_pk() if kind == "approve" else None
        customs = getattr(cmd, "customs", "default")
        verify = verification_record(get_settings().app_env.value)
        row = PackingOrder(
            source_account_ref=cmd.source_account_ref,
            warehouse_id=cmd.warehouse_id,
            candidate_id=candidate_id,
            inbound_order_sn=candidate.inbound_order_sn,
            sku=candidate.sku,
            store_id=candidate.store_id,
            item_id=candidate.item_id,
            pk=pk,
            qty=qty,
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
                    qty=qty,
                )
            )
        return row

    def _approve_split(self, ident, cmd, candidate, original_candidate, actor, request, digest):
        """Saved split draft: one packing order (own PK and allocation) per line, atomically."""
        s = self.session
        if cmd.target_store_id or cmd.target_item_id:
            conflict("SPLIT_DRAFT_TARGET_FIXED")
        total = sum(line.qty for line in candidate.split_lines)
        if cmd.qty != total:
            conflict("SPLIT_QTY_MISMATCH")
        if candidate.available_quantity is None or total > candidate.available_quantity:
            conflict("INSUFFICIENT_STOCK")
        stores = self._store_names(candidate.source_account_ref)
        resolved = [
            self._resolve_line(candidate, line.store_id, line.item_id, line.listing_version, stores)
            for line in candidate.split_lines
        ]
        rows = []
        for number, (line, (listing, blocked)) in enumerate(
            zip(candidate.split_lines, resolved, strict=True), 1
        ):
            if blocked:
                conflict(blocked[0])
            line_candidate = self._with_target(candidate, listing, stores, blocked=[]).model_copy(
                update={"default_quantity": line.qty}
            )
            if not line_candidate.can_approve:
                conflict("CANDIDATE_BLOCKED")
            rows.append(
                self._create_order(
                    ident if number == 1 else split_child_id(ident, number),
                    cmd,
                    "approve",
                    line_candidate,
                    original_candidate,
                    actor,
                    qty=line.qty,
                )
            )
        pks = [row.pk for row in rows]
        results = []
        for number, row in enumerate(rows, 1):
            result = order_read(row).model_copy(update={"split_pks": pks})
            results.append(result)
            s.add(
                PackingEvent(
                    order_id=row.id,
                    source_account_ref=row.source_account_ref,
                    idempotency_key=cmd.idempotency_key
                    if number == 1
                    else split_child_id(cmd.idempotency_key, number),
                    actor_uid=actor,
                    event_kind="approve",
                    order_version=1,
                    request_hash=digest,
                    request_json={**request, "split_line": number, "split_pks": pks},
                    response_json=result.model_dump(mode="json"),
                )
            )
        pending_edit = s.get(PackingPendingEdit, ident)
        if pending_edit is not None:
            s.delete(pending_edit)
        s.commit()
        return results[0]

    def listing_rows(self, candidate):
        """Same eligibility as Listing 管理: published WFS rows with a product link.

        Rows are found by local SKU or by the ItemID the resolver attributed to the
        candidate (its listing may have no local SKU yet; owner decision 2026-10-31).
        """
        identity = or_(Listing.local_sku == candidate.sku)
        attributed = getattr(candidate, "item_id", None)
        if attributed:
            identity = or_(Listing.local_sku == candidate.sku, Listing.item_id == attributed)
        return list(
            self.session.scalars(
                select(Listing).where(
                    Listing.source_account_ref == candidate.source_account_ref,
                    identity,
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
            listings=[listing_choice(r, candidate, stores) for r in self.listing_rows(candidate)],
        )

    # --- target Listing resolution (modify form, approve) ---------------------------

    def _store_names(self, account):
        names: dict[str, set[str]] = {}
        for row in self.session.scalars(select(Store).where(Store.source_account_ref == account)):
            if row.store_name:
                names.setdefault(row.store_id, set()).add(row.store_name)
        return {k: next(iter(v)) for k, v in names.items() if len(v) == 1}

    def _target_blocked(self, candidate, listing):
        """Why a Listing may not be the target of this candidate (empty = usable).

        Same proof as the pending list (published, product link, WFS converted, GTIN,
        MSKU) plus: the Listing's own local SKU, when recorded, must be this SKU; a
        cross-store target needs the shared-stock proof.
        """
        blocked = list(listing_blocked_reasons(listing))
        if listing_sku_mismatch(listing, candidate.sku):
            blocked.append("SKU_MISMATCH")
        cross = candidate.store_id is not None and listing.store_id != candidate.store_id
        if cross and candidate.available_quantity is None:
            blocked.append("CROSS_STORE_PROOF_MISSING")
        return blocked

    def _listings_by_identity(self, account, store_id, item_id):
        return list(
            self.session.scalars(
                select(Listing).where(
                    Listing.source_account_ref == account,
                    Listing.store_id == store_id,
                    Listing.item_id == item_id,
                )
            )
        )

    def _resolve_line(self, candidate, store_id, item_id, version, stores):
        rows = self._listings_by_identity(candidate.source_account_ref, store_id, item_id)
        if len(rows) != 1:
            conflict("LISTING_MISSING_OR_AMBIGUOUS")
        listing = rows[0]
        if version and version != listing_version(listing):
            conflict("LISTING_CHANGED")
        return listing, self._target_blocked(candidate, listing)

    def _with_target(self, candidate, listing, stores, blocked):
        other = [
            r
            for r in candidate.blocked_reasons
            if r
            not in (
                "ELIGIBLE_LISTING_MISSING",
                "WFS_NOT_CONVERTED",
                "GTIN_INVALID",
                "MSKU_MISSING",
                "STORE_UNKNOWN",
                "SKU_MISMATCH",
                "CROSS_STORE_PROOF_MISSING",
            )
        ]
        reasons = other + [r for r in blocked if r not in other]
        return candidate.model_copy(
            update={
                "store_id": listing.store_id,
                "store_name": stores.get(listing.store_id),
                "item_id": listing.item_id,
                "gtin": listing.gtin,
                "msku": listing.msku,
                "can_approve": not reasons,
                "blocked_reasons": reasons,
            }
        )

    def listing_search(self, ident, account, item_text, accounts):
        """ItemID search over Listing 管理 (whole account), for the modify form."""
        if account not in accounts:
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
        candidate = next(
            (r for r in self.all_candidates(frozenset({account})) if r.id == ident), None
        )
        if candidate is None:
            missing()
        text_value = (item_text or "").strip()
        if not text_value.isdigit() or not 4 <= len(text_value) <= 20:
            return ListingSearch(items=[])
        stores = self._store_names(account)
        exact = list(
            self.session.scalars(
                select(Listing).where(
                    Listing.source_account_ref == account, Listing.item_id == text_value
                )
            )
        )
        prefix = list(
            self.session.scalars(
                select(Listing)
                .where(
                    Listing.source_account_ref == account,
                    Listing.item_id.like(f"{text_value}%"),
                    Listing.item_id != text_value,
                )
                .order_by(Listing.item_id, Listing.store_id)
                .limit(LISTING_SEARCH_LIMIT)
            )
        )
        hits = []
        for listing in (exact + prefix)[:LISTING_SEARCH_LIMIT]:
            blocked = self._target_blocked(candidate, listing)
            hits.append(
                ListingHit(
                    store_id=listing.store_id,
                    store_name=stores.get(listing.store_id),
                    item_id=listing.item_id,
                    gtin=listing.gtin,
                    msku=listing.msku,
                    local_sku=listing.local_sku,
                    listing_version=listing_version(listing),
                    cross_store=candidate.store_id is not None
                    and listing.store_id != candidate.store_id,
                    wfs_converted=listing.fulfillment_type == "1",
                    usable=not blocked,
                    blocked_reasons=blocked,
                )
            )
        return ListingSearch(items=hits)

    def final_candidate(self, candidate, cmd):
        target_store = cmd.target_store_id or candidate.store_id
        target_item = cmd.target_item_id or candidate.item_id
        edited = target_store != candidate.store_id or target_item != candidate.item_id
        if edited and len((cmd.edit_reason or "").strip()) < 2:
            conflict("EDIT_REASON_REQUIRED")
        if edited and not cmd.listing_version:
            conflict("LISTING_CHANGED")
        # Owner decision 2026-10-21: the published inbound row is the allocation
        # basis. A new target Listing never moves or duplicates source inventory.
        stores = self._store_names(candidate.source_account_ref)
        listing, blocked = self._resolve_line(
            candidate, target_store, target_item, cmd.listing_version, stores
        )
        if "WFS_NOT_CONVERTED" in blocked:
            conflict("WFS_NOT_CONVERTED")
        if "SKU_MISMATCH" in blocked:
            conflict("SKU_MISMATCH")
        return self._with_target(candidate, listing, stores, blocked)

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
            (
                r
                for r in self._base_candidates(frozenset({cmd.source_account_ref}))
                if r.id == ident
            ),
            None,
        )
        if candidate is None:
            missing()
        if candidate.origin == "manual":
            conflict("MANUAL_DRAFT_UNSUPPORTED")
        if candidate.candidate_version != cmd.candidate_version:
            conflict("SOURCE_CHANGED")
        # Rocky 2026-11-01: every modification carries a reason.
        if len((cmd.edit_reason or "").strip()) < 2:
            conflict("EDIT_REASON_REQUIRED")
        lines = cmd.lines or []
        if len({(line.target_store_id, line.target_item_id) for line in lines}) != len(lines):
            conflict("SPLIT_LINES_DUPLICATE")
        stores = self._store_names(cmd.source_account_ref)
        resolved = []
        for line in lines:
            listing, blocked = self._resolve_line(
                candidate, line.target_store_id, line.target_item_id, line.listing_version, stores
            )
            for reason in ("WFS_NOT_CONVERTED", "SKU_MISMATCH", "CROSS_STORE_PROOF_MISSING"):
                if reason in blocked:
                    conflict(reason)
            resolved.append((line, listing, blocked))
        first_listing = resolved[0][1]
        merged = self._with_target(
            candidate,
            first_listing,
            stores,
            sorted({r for _, _, blocked in resolved for r in blocked}),
        )
        if not merged.can_approve:
            conflict("CANDIDATE_BLOCKED")
        total = cmd.total_qty
        if merged.available_quantity is None or total > merged.available_quantity:
            conflict("INSUFFICIENT_STOCK")
        split = [
            SplitLine(
                store_id=listing.store_id,
                store_name=stores.get(listing.store_id),
                item_id=listing.item_id,
                gtin=listing.gtin,
                msku=listing.msku,
                listing_version=listing_version(listing),
                qty=line.qty,
            )
            for line, listing, _ in resolved
        ]
        merged = merged.model_copy(update={"split_lines": split if len(split) > 1 else []})
        s = self.session
        row = s.get(PackingPendingEdit, ident) or PackingPendingEdit(
            candidate_id=ident,
            source_account_ref=cmd.source_account_ref,
        )
        row.base_candidate_version = candidate.candidate_version
        row.requested_qty = total
        row.customs = cmd.customs
        row.edit_reason = cmd.edit_reason
        row.draft_snapshot_json = merged.model_dump(mode="json")
        row.actor_uid = actor
        row.updated_at = datetime.now(UTC)
        s.add(row)
        s.commit()
        snapshot = merged.model_copy(
            update={
                "default_quantity": total,
                "manual_customs": cmd.customs,
                "edit_draft_pending": True,
            }
        )
        return EditDraftSaved(candidate_id=ident, snapshot=snapshot)

    def all_candidates(self, accounts):
        return self._apply_pending_edits(self._base_candidates(accounts), accounts)


def listing_choice(row, candidate, stores) -> ListingChoice:
    """One target-Listing option for the edit dialog.

    ``sku_mismatch``: the listing has its own local SKU and it is not the row SKU. Such a
    listing only appears because its ItemID is the one attributed to the row
    (``listing_rows`` matches local SKU *or* the attributed ItemID). It is listed
    and the dialog shows it disabled with the reason; ``final_candidate`` refuses it with
    ``SKU_MISMATCH`` (owner decision 2026-11-02).
    """
    local = (row.local_sku or "").strip() if isinstance(row.local_sku, str) else ""
    mismatch = listing_sku_mismatch(row, candidate.sku)
    return ListingChoice(
        store_id=row.store_id,
        store_name=stores.get(row.store_id),
        item_id=row.item_id,
        gtin=row.gtin,
        msku=row.msku,
        listing_version=listing_version(row),
        cross_store=row.store_id != candidate.store_id,
        local_sku=local or None,
        sku_mismatch=mismatch,
    )


def listing_sku_mismatch(listing, sku) -> bool:
    """The Listing records its own local SKU and it is not ``sku`` (blank = no opinion)."""
    local = (listing.local_sku or "").strip() if isinstance(listing.local_sku, str) else ""
    return bool(local) and local != (sku or "").strip()

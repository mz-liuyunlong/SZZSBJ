"""Manual requests select a published inbound source; submission never allocates stock."""

from uuid import uuid4

from sqlalchemy import select, text

from app.core.api import ApiError, ErrorCode
from app.modules.data_pages.models import LingxingStoreDimension as Store
from app.modules.pmc_domestic.packing_models import PackingEvent
from app.modules.pmc_domestic.packing_models import PackingManualRequest as Draft
from app.modules.pmc_domestic.packing_repository import matches
from app.modules.pmc_domestic.packing_rules import fingerprint, listing_version
from app.modules.pmc_domestic.packing_schemas import (
    ApproveCommand,
    Candidate,
    CandidateList,
    EditOptions,
    ListingChoice,
    ManualSubmitted,
)


class ManualPackingService:
    def __init__(self, service):
        self.base, self.session = service, service.session

    def sources(self, accounts):
        unique = {}
        for row in sorted(
            self.base.repo.candidates(accounts, include_decided=True),
            key=lambda r: (r.source_account_ref, str(r.board_id), r.item_id or ""),
        ):
            unique.setdefault((row.source_account_ref, row.board_id), row)
        return list(unique.values())

    def source(self, board_id, account, accounts):
        if account not in accounts:
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
        row = next((r for r in self.sources(frozenset({account})) if r.board_id == board_id), None)
        if row is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        return row

    def source_list(self, query, accounts):
        rows = [r for r in self.sources(accounts) if matches(r, query)]
        rows.sort(
            key=lambda r: (
                r.candidate_created_on.isoformat() if r.candidate_created_on else "",
                str(r.board_id),
            ),
            reverse=True,
        )
        start = (query.page - 1) * query.page_size
        return CandidateList(items=rows[start : start + query.page_size], total=len(rows))

    def options(self, board_id, account, accounts):
        source = self.source(board_id, account, accounts)
        stores = {
            r.store_id: r.store_name
            for r in self.session.scalars(select(Store).where(Store.source_account_ref == account))
        }
        return EditOptions(
            candidate=source,
            cross_store_proof_available=source.available_quantity is not None,
            listings=[
                ListingChoice(
                    store_id=r.store_id,
                    store_name=stores.get(r.store_id),
                    item_id=r.item_id,
                    gtin=r.gtin,
                    msku=r.msku,
                    listing_version=listing_version(r),
                    cross_store=r.store_id != source.store_id,
                )
                for r in self.base.listing_rows(source)
            ],
        )

    def pending(self, accounts):
        if not accounts:
            return []
        sources = {(r.source_account_ref, r.board_id): r for r in self.sources(accounts)}
        decided = {r.candidate_id for r in self.base.repo.orders(accounts) if r.status != "voided"}
        drafts = self.session.scalars(
            select(Draft)
            .where(Draft.source_account_ref.in_(accounts), Draft.warehouse_id == "16168")
            .order_by(Draft.submitted_at, Draft.id)
        )
        result = []
        for draft in drafts:
            if draft.id in decided:
                continue
            saved = Candidate.model_validate(draft.requested_snapshot_json)
            source = sources.get((draft.source_account_ref, draft.source_board_id))
            if source is None:
                result.append(
                    saved.model_copy(
                        update={
                            "available_quantity": None,
                            "can_approve": False,
                            "blocked_reasons": ["SOURCE_NOT_CURRENT"],
                            "candidate_version": fingerprint([str(draft.id), "missing"]),
                        }
                    )
                )
                continue
            listings = [
                r
                for r in self.base.listing_rows(source)
                if r.store_id == saved.store_id and r.item_id == saved.item_id
            ]
            target = listings[0] if len(listings) == 1 else None
            blocked = [
                x
                for x in source.blocked_reasons
                if x
                not in ("ELIGIBLE_LISTING_MISSING", "GTIN_INVALID", "MSKU_MISSING", "STORE_UNKNOWN")
            ]
            if target is None:
                blocked.append("ELIGIBLE_LISTING_MISSING")
            else:
                if not target.gtin or not target.gtin.isdigit() or len(target.gtin) != 14:
                    blocked.append("GTIN_INVALID")
                if not target.msku:
                    blocked.append("MSKU_MISSING")
            update = {
                k: getattr(source, k)
                for k in (
                    "publication_id",
                    "source_observed_at",
                    "stock_balance",
                    "available_quantity",
                    "candidate_created_on",
                    "overdue",
                    "waiting_days",
                    "history_complete",
                    "customs_default",
                    "customs_default_src",
                    "customs_proof",
                )
            }
            update.update(
                can_approve=not blocked,
                blocked_reasons=blocked,
                default_quantity=draft.requested_qty,
                candidate_version=fingerprint(
                    [
                        source.candidate_version,
                        str(draft.id),
                        listing_version(target) if target else None,
                        draft.requested_qty,
                    ]
                ),
            )
            if target:
                update.update(gtin=target.gtin, msku=target.msku)
            result.append(saved.model_copy(update=update))
        return result

    def submit(self, cmd, actor, accounts):
        self.base.guard_local()
        if cmd.source_account_ref not in accounts:
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
        s = self.session
        request = {"kind": "manual_submit", "actor_uid": actor, **cmd.model_dump(mode="json")}
        digest = fingerprint(request)
        try:
            s.execute(text("SET LOCAL lock_timeout='5s'"))
            self.base.lock(f"packing-command:{cmd.source_account_ref}:{cmd.idempotency_key}")
            prior = s.scalar(
                select(Draft).where(
                    Draft.source_account_ref == cmd.source_account_ref,
                    Draft.idempotency_key == cmd.idempotency_key,
                )
            )
            if prior:
                if prior.request_hash != digest:
                    self.conflict("IDEMPOTENCY_KEY_REUSED")
                result = ManualSubmitted(id=prior.id)
                s.commit()
                return result
            if s.scalar(
                select(PackingEvent.id).where(
                    PackingEvent.source_account_ref == cmd.source_account_ref,
                    PackingEvent.idempotency_key == cmd.idempotency_key,
                )
            ):
                self.conflict("IDEMPOTENCY_KEY_REUSED")
            self.base.lock(f"{cmd.source_account_ref}\0{cmd.warehouse_id}")
            source = self.source(cmd.board_id, cmd.source_account_ref, accounts)
            if source.candidate_version != cmd.source_version:
                self.conflict("SOURCE_CHANGED")
            target = self.base.final_candidate(
                source,
                ApproveCommand(
                    source_account_ref=cmd.source_account_ref,
                    candidate_version=cmd.source_version,
                    idempotency_key=cmd.idempotency_key,
                    qty=cmd.qty,
                    target_store_id=cmd.target_store_id,
                    target_item_id=cmd.target_item_id,
                    listing_version=cmd.listing_version,
                    edit_reason=cmd.reason,
                ),
            )
            if not target.can_approve:
                self.conflict("CANDIDATE_BLOCKED")
            if source.available_quantity is None or cmd.qty > source.available_quantity:
                self.conflict("INSUFFICIENT_STOCK")
            ident = uuid4()
            target = target.model_copy(
                update={
                    "id": ident,
                    "origin": "manual",
                    "manual_reason": cmd.reason,
                    "source_store_id": source.store_id,
                    "manual_customs": cmd.customs,
                    "manual_rwh": cmd.rwh,
                    "default_quantity": cmd.qty,
                }
            )
            s.add(
                Draft(
                    id=ident,
                    source_account_ref=cmd.source_account_ref,
                    warehouse_id=cmd.warehouse_id,
                    source_publication_id=source.publication_id,
                    source_board_id=source.board_id,
                    source_snapshot_json=source.model_dump(mode="json"),
                    requested_snapshot_json=target.model_dump(mode="json"),
                    requested_qty=cmd.qty,
                    customs=cmd.customs,
                    rwh=cmd.rwh,
                    reason=cmd.reason,
                    actor_uid=actor,
                    idempotency_key=cmd.idempotency_key,
                    request_hash=digest,
                    request_json=request,
                )
            )
            s.commit()
            return ManualSubmitted(id=ident)
        except Exception:
            s.rollback()
            raise

    @staticmethod
    def conflict(reason):
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409, details={"reason": reason})

"""Atomic preparation only: validate physical boxes and reserve them without external calls."""

from collections import defaultdict
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.core.api import ApiError, ErrorCode
from app.core.config import get_settings
from app.modules.data_pages.models import LingxingStoreDimension as Store
from app.modules.pmc_domestic.packing_models import (
    PackingAllocation,
    PackingEvent,
    PackingOrder,
    now,
)
from app.modules.pmc_domestic.packing_rules import fingerprint, listing_version
from app.modules.pmc_domestic.packing_schemas import Candidate, ListingChoice
from app.modules.pmc_domestic.packing_service import PackingService, conflict, missing
from app.modules.pmc_domestic.packing_stock_models import PackingExtraAllocation
from app.modules.pmc_domestic.warehouse_models import (
    PackingBoxLine,
    PackingBoxSet,
    PackingVarianceCase,
)
from app.modules.pmc_domestic.warehouse_service import WarehouseService
from app.modules.pmc_wfs.models import WfsBoxAllocation, WfsDraft, WfsDraftItem, WfsEvent
from app.modules.pmc_wfs.repository import WfsRepository, assert_not_occupied
from app.modules.pmc_wfs.schemas import (
    DraftRead,
    DraftResult,
    IdentityOptions,
    PendingFilter,
    PendingList,
    PendingOptions,
    PendingRow,
    PendingSummary,
    StoreOption,
)


def draft_read(row):
    return DraftRead.model_validate({key: getattr(row, key) for key in DraftRead.model_fields})


class WfsService:
    def __init__(self, session, accounts, stores):
        self.session, self.accounts, self.stores = session, accounts, stores
        self.base = PackingService(session)
        self.repo = WfsRepository(session)
        self.warehouse = WarehouseService(session)

    def visible(self, row):
        return (
            row
            and row.source_account_ref in self.accounts
            and (self.stores is None or row.store_id in self.stores)
        )

    def order(self, ident, lock=False):
        row = self.warehouse.repo.order(ident, self.accounts, lock=lock)
        if not self.visible(row) or row.status != "approved":
            missing()
        return row

    def rows(self, orders):
        occupied = self.repo.occupied([o.id for o in orders])
        result = []
        for raw, order in zip(orders, self.warehouse.read_rows(orders), strict=True):
            box = order.box_set
            reasons = []
            if not box or not box.completed_at:
                reasons.append("PACKING_NOT_COMPLETED")
            if not order.store_id or not order.item_id or not order.msku:
                reasons.append("IDENTITY_MISSING")
            if (
                not order.gtin
                or len(order.gtin) != 14
                or not order.gtin.isascii()
                or not order.gtin.isdigit()
            ):
                reasons.append("GTIN_INVALID")
            lines = box.lines if box else []
            used = [r.id for r in lines if r.id in occupied]
            available = [r.id for r in lines if r.id not in occupied] if not reasons else []
            if not lines:
                reasons.append("BOXES_REQUIRED")
            result.append(
                PendingRow(
                    order=order,
                    business_test=raw.business_test,
                    occupied_line_ids=used,
                    available_line_ids=available,
                    blocked_reasons=reasons,
                    can_edit=not used and bool(box and box.completed_at),
                )
            )
        return result

    def list(self, query):
        stmt = self.repo.query(query, self.accounts, self.stores)
        total = self.repo.count(stmt)
        orders = list(
            self.session.scalars(
                stmt.offset((query.page - 1) * query.page_size).limit(query.page_size)
            )
        )
        return PendingList(items=self.rows(orders), total=total)

    def detail(self, ident):
        row = self.rows([self.order(ident)])[0]
        if not row.order.box_set or not row.order.box_set.completed_at:
            missing()
        return row

    def summary(self, query):
        # Summary aggregates all matching completed PKs, never only the current page.
        orders = list(self.session.scalars(self.repo.query(query, self.accounts, self.stores)))
        rows = self.rows(orders)
        all_orders = list(
            self.session.scalars(
                self.repo.query(query, self.accounts, self.stores, completed=False)
            )
        )
        sets, *_ = self.warehouse.repo.context(all_orders) if all_orders else ({},)
        waiting = [o for o in all_orders if o.id not in sets or not sets[o.id].completed_at]
        lines = [
            line for r in rows for line in r.order.box_set.lines if line.id in r.available_line_ids
        ]
        return PendingSummary(
            completed=len(rows),
            ready=sum(bool(r.available_line_ids) for r in rows),
            test=sum(r.business_test for r in rows),
            waiting=len(waiting),
            no_box=sum(o.id not in sets for o in waiting),
            filled_not_done=sum(o.id in sets for o in waiting),
            available_boxes=sum(r.boxes for r in lines),
            available_units=sum(r.boxes * r.units_per_box for r in lines),
        )

    def options(self):
        orders = self.session.scalars(self.repo.query(PendingFilter(), self.accounts, self.stores))
        values = {
            r.store_id: r.snapshot_json.get("store_name") or r.store_id
            for r in orders
            if r.store_id
        }
        return PendingOptions(
            stores=[StoreOption(value=k, label=v) for k, v in sorted(values.items())]
        )

    def draft(self, ident):
        row = self.repo.draft(ident, self.accounts, self.stores)
        if row is None:
            missing()
        return draft_read(row)

    def begin(self, command, actor, kind):
        if command.source_account_ref not in self.accounts:
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
        # This phase is explicitly local/test only, regardless of broader domestic deployment.
        if get_settings().app_env.value not in {"local", "test"}:
            raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
        self.base.guard_local()
        self.session.execute(text("SET LOCAL lock_timeout='5s'"))
        self.base.lock(f"wfs-command:{command.source_account_ref}:{command.idempotency_key}")
        self.base.lock(f"{command.source_account_ref}\0{16168}")
        request = {"actor_uid": actor, "kind": kind, **command.model_dump(mode="json")}
        digest = fingerprint(request)
        prior = self.repo.prior(command.source_account_ref, command.idempotency_key)
        if prior and prior.request_hash != digest:
            conflict("IDEMPOTENCY_KEY_REUSED")
        return request, digest, prior

    def record(self, command, actor, kind, request, digest, result):
        self.session.add(
            WfsEvent(
                source_account_ref=command.source_account_ref,
                idempotency_key=command.idempotency_key,
                kind=kind,
                actor_uid=actor,
                request_hash=digest,
                request_json=request,
                response_json=result,
            )
        )

    def submit(self, cmd, actor):
        s = self.session
        try:
            request, digest, prior = self.begin(cmd, actor, "submit")
            if prior:
                result = DraftResult.model_validate(prior.response_json)
                for d in result.drafts:
                    self.draft(d.id)  # Retry must still obey the user's current scope.
                s.commit()
                return result
            if len({r.order_id for r in cmd.selections}) != len(cmd.selections):
                conflict("DUPLICATE_ORDER")
            selected = []
            for choice in sorted(cmd.selections, key=lambda r: str(r.order_id)):
                order = self.order(choice.order_id, lock=True)
                if order.source_account_ref != cmd.source_account_ref:
                    missing()
                row = self.detail(order.id)
                box = row.order.box_set
                if order.version != choice.expected_version:
                    conflict("ORDER_VERSION_CHANGED")
                if not box or box.version != choice.expected_box_version:
                    conflict("BOX_VERSION_CHANGED")
                if row.blocked_reasons:
                    conflict("PACKING_NOT_ELIGIBLE")
                if len(set(choice.box_line_ids)) != len(choice.box_line_ids):
                    conflict("DUPLICATE_BOX_LINE")
                if not set(choice.box_line_ids).issubset(row.available_line_ids):
                    conflict("WFS_BOXES_OCCUPIED_OR_INVALID")
                selected.append((order, row, [r for r in box.lines if r.id in choice.box_line_ids]))
            if len({(o.store_id, o.business_test) for o, _, _ in selected}) != 1:
                conflict("STORE_OR_TEST_MIXED")
            # Same SKU with different per-box quantities must go to different drafts.
            groups = defaultdict(list)
            for order, row, lines in selected:
                for line in lines:
                    groups[line.units_per_box].append((order, row, line))
            drafts = []
            for _per, values in sorted(groups.items()):
                ident = uuid4()
                draft = WfsDraft(
                    id=ident,
                    number=f"WS{now():%y%m%d}-{ident.hex[:16]}",
                    source_account_ref=cmd.source_account_ref,
                    store_id=values[0][0].store_id,
                    business_test=values[0][0].business_test,
                    status="pending",
                    actor_uid=actor,
                    payload={
                        "return_address": cmd.return_address.model_dump(),
                        "its": cmd.its,
                        "operation": "create",
                        "items": [],
                    },
                )
                s.add(draft)
                s.flush()
                snapshots = []
                for order, row, line in values:
                    snapshot = {
                        "order": row.order.model_dump(mode="json"),
                        "line": line.model_dump(mode="json"),
                    }
                    item = WfsDraftItem(
                        id=uuid4(),
                        draft_id=ident,
                        sku=order.sku,
                        gtin=row.order.gtin,
                        boxes=line.boxes,
                        units_per_box=line.units_per_box,
                        snapshot=snapshot,
                    )
                    s.add(item)
                    s.flush()
                    s.add(
                        WfsBoxAllocation(
                            item_id=item.id,
                            order_id=order.id,
                            box_line_id=line.id,
                            box_version=row.order.box_set.version,
                            snapshot=snapshot,
                        )
                    )
                    snapshots.append(snapshot)
                draft.payload = {**draft.payload, "items": snapshots}
                drafts.append(draft)
            s.flush()
            result = DraftResult(drafts=[draft_read(r) for r in drafts])
            self.record(cmd, actor, "submit", request, digest, result.model_dump(mode="json"))
            s.commit()
            return result
        except IntegrityError:
            s.rollback()
            conflict("WFS_BOXES_OCCUPIED_OR_INVALID")
        except Exception:
            s.rollback()
            raise

    def identity_options(self, ident):
        order = self.order(ident)
        candidate = Candidate.model_validate(order.snapshot_json)
        stores = {
            r.store_id: r.store_name
            for r in self.session.scalars(
                select(Store).where(Store.source_account_ref == order.source_account_ref)
            )
        }
        return IdentityOptions(
            listings=[
                ListingChoice(
                    store_id=r.store_id,
                    store_name=stores.get(r.store_id),
                    item_id=r.item_id,
                    gtin=r.gtin,
                    msku=r.msku,
                    listing_version=listing_version(r),
                    cross_store=r.store_id != order.store_id,
                )
                for r in self.base.listing_rows(candidate)
                if self.stores is None or r.store_id in self.stores
            ]
        )

    def switch(self, ident, cmd, actor):
        s = self.session
        try:
            request, digest, prior = self.begin(cmd, actor, f"identity:{ident}")
            if prior:
                result = self.detail(prior.response_json["new_order_id"])
                s.commit()
                return result
            old = self.order(ident, lock=True)
            if old.source_account_ref != cmd.source_account_ref:
                missing()
            if self.stores is not None and cmd.target_store_id not in self.stores:
                raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
            assert_not_occupied(s, old.id)
            box = s.scalar(select(PackingBoxSet).where(PackingBoxSet.order_id == old.id))
            if old.version != cmd.expected_version:
                conflict("ORDER_VERSION_CHANGED")
            if not box or not box.completed_at or box.version != cmd.expected_box_version:
                conflict("BOX_VERSION_CHANGED")
            if (old.store_id, old.item_id) == (cmd.target_store_id, cmd.target_item_id):
                conflict("NO_CHANGE")
            choices = [
                r
                for r in self.identity_options(ident).listings
                if (r.store_id, r.item_id) == (cmd.target_store_id, cmd.target_item_id)
            ]
            if len(choices) != 1 or choices[0].listing_version != cmd.listing_version:
                conflict("LISTING_CHANGED")
            choice = choices[0]
            if (
                not choice.gtin
                or len(choice.gtin) != 14
                or not choice.gtin.isdigit()
                or not choice.msku
            ):
                conflict("IDENTITY_MISSING")
            if s.scalar(
                select(PackingOrder.id).where(
                    PackingOrder.source_account_ref == old.source_account_ref,
                    PackingOrder.source_board_id == old.source_board_id,
                    PackingOrder.store_id == choice.store_id,
                    PackingOrder.item_id == choice.item_id,
                    PackingOrder.status != "voided",
                )
            ):
                conflict("FINAL_IDENTITY_ALREADY_DECIDED")
            variance = s.get(PackingVarianceCase, old.id)
            if variance and variance.state in {"blocked", "ready"}:
                conflict("VARIANCE_REQUIRES_RESOLUTION")
            before = self.detail(old.id).model_dump(mode="json")
            moment = now()
            day = datetime.now(ZoneInfo("Asia/Taipei")).date()
            serial = s.scalar(
                text(
                    "INSERT INTO ops_domestic_pk_sequences (business_date,last_value) "
                    "VALUES (:day,1) "
                    "ON CONFLICT (business_date) DO UPDATE SET "
                    "last_value=ops_domestic_pk_sequences.last_value+1 "
                    "WHERE ops_domestic_pk_sequences.last_value<999 RETURNING last_value"
                ),
                {"day": day},
            )
            if serial is None:
                conflict("PK_DAILY_LIMIT")
            old.status, old.voided_at, old.void_note = "voided", moment, cmd.reason
            old.version += 1
            old.updated_at = moment
            s.flush()  # Release active-identity uniqueness before creating the replacement.
            fields = {c.key: getattr(old, c.key) for c in PackingOrder.__table__.columns}
            new_id = uuid4()
            snap = {
                **old.snapshot_json,
                "id": str(new_id),
                "store_id": choice.store_id,
                "store_name": choice.store_name,
                "item_id": choice.item_id,
                "gtin": choice.gtin,
                "msku": choice.msku,
            }
            fields.update(
                id=new_id,
                candidate_id=new_id,
                pk=f"PK{day:%y%m%d}-{serial:03d}",
                store_id=choice.store_id,
                item_id=choice.item_id,
                status="approved",
                version=1,
                voided_at=None,
                void_note=None,
                actor_uid=actor,
                snapshot_json=snap,
                note=cmd.reason,
                created_at=moment,
                updated_at=moment,
                final_identity_key=fingerprint(
                    [str(old.source_board_id), choice.store_id, choice.item_id]
                ),
            )
            new = PackingOrder(**fields)
            s.add(new)
            s.flush()
            # Transfer ownership only: source quantities and source evidence never change.
            for model in (PackingAllocation, PackingExtraAllocation):
                for allocation in s.scalars(select(model).where(model.order_id == old.id)):
                    allocation.order_id = new_id
            new_box_id = uuid4()
            box_fields = {c.key: getattr(box, c.key) for c in PackingBoxSet.__table__.columns}
            box_fields.update(id=new_box_id, order_id=new_id)
            s.add(PackingBoxSet(**box_fields))
            s.flush()
            for line in s.scalars(
                select(PackingBoxLine).where(PackingBoxLine.box_set_id == box.id)
            ):
                values = {c.key: getattr(line, c.key) for c in PackingBoxLine.__table__.columns}
                values.update(id=uuid4(), box_set_id=new_box_id)
                s.add(PackingBoxLine(**values))
            if variance:
                values = {
                    c.key: getattr(variance, c.key) for c in PackingVarianceCase.__table__.columns
                }
                values.update(order_id=new_id)
                s.add(PackingVarianceCase(**values))
            s.flush()
            result = self.detail(new_id)
            for order, kind in ((old, "void"), (new, "approve")):
                s.add(
                    PackingEvent(
                        order_id=order.id,
                        source_account_ref=order.source_account_ref,
                        idempotency_key=uuid4(),
                        actor_uid=actor,
                        event_kind=kind,
                        order_version=order.version,
                        request_hash=digest,
                        request_json={
                            **request,
                            "before": before,
                            "from_pk": old.pk,
                            "to_pk": new.pk,
                        },
                        response_json=result.order.model_dump(mode="json"),
                    )
                )
            self.record(cmd, actor, "identity", request, digest, {"new_order_id": str(new_id)})
            s.commit()
            return result
        except IntegrityError:
            s.rollback()
            conflict("IDENTITY_OR_VERSION_CONFLICT")
        except Exception:
            s.rollback()
            raise

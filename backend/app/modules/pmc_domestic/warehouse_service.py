"""Atomic warehouse commands with one-shot completion and explicit variance cases."""

from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import delete, func, select, text

from app.core.api import ApiError, ErrorCode
from app.modules.pmc_domestic.draft_numbers import attach_draft_numbers
from app.modules.pmc_domestic.inbound_models import DomesticInboundBoard
from app.modules.pmc_domestic.packing_models import (
    PackingAllocation,
    PackingEvent,
    PackingManualRequest,
    PackingOrder,
    now,
)
from app.modules.pmc_domestic.packing_rules import fingerprint
from app.modules.pmc_domestic.packing_schemas import Candidate
from app.modules.pmc_domestic.packing_service import PackingService, conflict, missing
from app.modules.pmc_domestic.packing_stock_models import PackingExtraAllocation
from app.modules.pmc_domestic.warehouse_completion_rules import UNDER_REASONS
from app.modules.pmc_domestic.warehouse_models import (
    PackingBoxLine,
    PackingBoxSet,
    PackingVarianceCase,
    PackingWarehouseNote,
)
from app.modules.pmc_domestic.warehouse_overpack import WarehouseOverpack
from app.modules.pmc_domestic.warehouse_repository import WarehouseRepository
from app.modules.pmc_domestic.warehouse_schemas import (
    NOTE_LABELS,
    BoxLineRead,
    BoxSetRead,
    ExtraAllocationRead,
    NoteRead,
    PackageInput,
    ProductRequirement,
    VarianceRead,
    WarehouseEventRead,
    WarehouseEvents,
    WarehouseList,
    WarehouseOption,
    WarehouseOptions,
    WarehouseOrderRead,
    WarehouseSummary,
)

BOX_DIMENSIONS = {"A": (58, 40, 45), "B": (46, 46, 52), "C": (53, 43, 48)}


def requirement(rows):
    if len(rows) != 1:
        return ProductRequirement(
            state="unknown",
            version=fingerprint(["product_unknown", sorted(str(r.id) for r in rows)]),
            reason="产品资料缺失或同SKU身份有歧义",
        )
    row = rows[0]
    values = {
        "length_cm": row.package_length_cm,
        "width_cm": row.package_width_cm,
        "height_cm": row.package_height_cm,
        "gross_weight_g": row.product_gross_weight_g,
        "net_weight_g": row.product_net_weight_g,
    }
    version = fingerprint([str(row.source_snapshot_id), values])
    try:
        package = PackageInput.model_validate(values)
    except ValidationError:
        return ProductRequirement(
            state="missing",
            version=version,
            source_snapshot_id=row.source_snapshot_id,
            reason="包装尺寸或单品毛重缺失/无效，须仓库补填",
        )
    return ProductRequirement(
        state="complete",
        version=version,
        source_snapshot_id=row.source_snapshot_id,
        package=package,
    )


class WarehouseService:
    def __init__(self, session, publication_provider=None):
        self.session = session
        self.repo = WarehouseRepository(session)
        self.base = PackingService(session)
        self.overpack = WarehouseOverpack(session, publication_provider)

    def read_rows(self, orders):
        if not orders:
            return []
        sets, lines, notes, products, balances = self.repo.context(orders)
        receipts = self.repo.receipts(orders)
        cases = {
            r.order_id: r
            for r in self.session.scalars(
                select(PackingVarianceCase).where(
                    PackingVarianceCase.order_id.in_([o.id for o in orders])
                )
            )
        }
        extra_allocations = {o.id: [] for o in orders}
        for extra, source in self.session.execute(
            select(PackingExtraAllocation, DomesticInboundBoard)
            .join(
                DomesticInboundBoard,
                (DomesticInboundBoard.id == PackingExtraAllocation.source_board_id)
                & (
                    DomesticInboundBoard.publication_id
                    == PackingExtraAllocation.source_publication_id
                ),
            )
            .where(PackingExtraAllocation.order_id.in_([o.id for o in orders]))
        ):
            extra_allocations[extra.order_id].append(
                ExtraAllocationRead(
                    source_publication_id=extra.source_publication_id,
                    source_board_id=extra.source_board_id,
                    inbound_order_sn=source.inbound_order_sn,
                    quantity=extra.qty,
                )
            )
        budgets = self.overpack.stock.budgets(
            {(o.source_account_ref, o.warehouse_id, o.sku) for o in orders}
        )
        result = []
        for order in orders:
            snap = Candidate.model_validate(order.snapshot_json)
            box = sets.get(order.id)
            note = notes.get(order.id)
            product = requirement(products.get((order.source_account_ref, order.sku), []))
            balance = balances.get((order.source_account_ref, order.source_board_id))
            done = bool(box and box.completed_at)
            variance = cases.get(order.id)
            reasons = []
            if done:
                reasons.append("ALREADY_COMPLETED")
            if not box:
                reasons.append("BOXES_REQUIRED")
            budget = (
                self.overpack.budget(order)
                if len(orders) == 1
                else budgets[(order.source_account_ref, order.warehouse_id, order.sku)]
            )
            if box and box.total_qty > order.qty and budget.available is None:
                reasons.append("STOCK_PROOF_UNKNOWN")
            if product.state != "complete" and not (box and box.package_snapshot):
                reasons.append("PACKAGE_REQUIRED")
            approved_date = order.created_at.astimezone(ZoneInfo("Asia/Shanghai")).date()
            stop = box.completed_at if done else now()
            result.append(
                WarehouseOrderRead(
                    id=order.id,
                    source_account_ref=order.source_account_ref,
                    version=order.version,
                    pk=order.pk,
                    is_test=order.is_test,
                    approved_at=order.created_at,
                    approved_date=approved_date,
                    inbound_order_sn=order.inbound_order_sn,
                    inbound_date=balance[0].arrival_business_date
                    if balance
                    else snap.candidate_created_on,
                    arrival_date=balance[0].arrival_business_date
                    if balance
                    else snap.candidate_created_on,
                    arrival_status="inbound_date"
                    if (balance[0].arrival_business_date if balance else snap.candidate_created_on)
                    else "unknown",
                    warehouse_days=max(
                        0,
                        (
                            now().astimezone(ZoneInfo("Asia/Shanghai")).date()
                            - (
                                balance[0].arrival_business_date
                                if balance
                                else snap.candidate_created_on
                            )
                        ).days,
                    )
                    if (balance[0].arrival_business_date if balance else snap.candidate_created_on)
                    else None,
                    received_dates=receipts[order.id][0],
                    receipt_order_sns=receipts[order.id][1],
                    purchase_order_sns=snap.purchase_order_sns,
                    sku=order.sku,
                    product_name=snap.product_name,
                    store_id=order.store_id,
                    store_name=snap.store_name,
                    item_id=order.item_id,
                    gtin=snap.gtin,
                    msku=snap.msku,
                    approved_quantity=order.qty,
                    stock_balance=balance[0].balance_num if balance else None,
                    balance_publication_id=balance[1].id if balance else None,
                    balance_observed_at=balance[1].source_observed_at if balance else None,
                    status="packed" if done else "todo",
                    packing_days=max(
                        0,
                        (stop.astimezone(ZoneInfo("Asia/Shanghai")).date() - approved_date).days,
                    ),
                    customs_value=order.customs_value,
                    customs_src=order.customs_src,
                    product_requirement=product,
                    box_set=BoxSetRead(
                        id=box.id,
                        version=box.version,
                        total_qty=box.total_qty,
                        variance_qty=box.total_qty - order.qty,
                        variance_reason=box.variance_reason,
                        completed_at=box.completed_at,
                        completed_by=box.completed_by,
                        package_snapshot=box.package_snapshot,
                        lines=[
                            BoxLineRead(
                                id=r.id,
                                line_no=r.line_no,
                                box_type=r.box_type,
                                boxes=r.boxes,
                                units_per_box=r.units_per_box,
                                gross_weight_kg=r.gross_weight_kg,
                                length_cm=r.length_cm,
                                width_cm=r.width_cm,
                                height_cm=r.height_cm,
                            )
                            for r in lines[box.id]
                        ],
                    )
                    if box
                    else None,
                    current_note=NoteRead(
                        category=note.category,
                        category_label=NOTE_LABELS[note.category],
                        text=note.text,
                        resolved=note.resolved,
                        actor_uid=note.actor_uid,
                        updated_at=note.updated_at,
                    )
                    if note
                    else None,
                    extra_allocations=extra_allocations[order.id],
                    extra_available=budget.available,
                    extra_publication_id=budget.publication_id,
                    variance_case=VarianceRead(
                        last_sync_code=variance.evidence.get("last_sync_code"),
                        last_sync_gap=variance.evidence.get("last_sync_gap"),
                        notification_state=variance.evidence.get("notification_state"),
                        proposed_lines=variance.evidence.get("proposed_lines"),
                        kind=variance.kind,
                        state=variance.state,
                        quantity=variance.quantity,
                        gap_qty=variance.gap_qty,
                        reason_category=variance.reason_category,
                        reason=variance.reason,
                        supplemental_ib=variance.supplemental_ib,
                    )
                    if variance
                    else None,
                    can_complete=not reasons,
                    completion_blocked_reasons=reasons,
                )
            )
        attach_draft_numbers(
            self.session, result, frozenset(order.source_account_ref for order in orders)
        )
        return result

    def list(self, q, accounts):
        rows, total = self.repo.list(q, accounts)
        return WarehouseList(items=self.read_rows(rows), total=total)

    def order(self, ident, accounts):
        row = self.repo.order(ident, accounts)
        if row is None or row.status != "approved":
            missing()
        return row

    def detail(self, ident, accounts):
        return self.read_rows([self.order(ident, accounts)])[0]

    def summary(self, q, accounts):
        ids = (
            self.repo.query(q, accounts, status=False).with_only_columns(PackingOrder.id).subquery()
        )
        total = self.session.scalar(select(func.count()).select_from(ids))
        packed = self.session.scalar(
            select(func.count())
            .select_from(PackingBoxSet)
            .where(
                PackingBoxSet.order_id.in_(select(ids.c.id)),
                PackingBoxSet.completed_at.is_not(None),
            )
        )

        def cases(kind, state):
            return self.session.scalar(
                select(func.count())
                .select_from(PackingVarianceCase)
                .where(
                    PackingVarianceCase.order_id.in_(select(ids.c.id)),
                    PackingVarianceCase.kind == kind,
                    PackingVarianceCase.state == state,
                )
            )

        return WarehouseSummary(
            todo=total - packed,
            packed=packed,
            overpack_blocked=cases("over", "blocked"),
            unpacked_pending=cases("under", "pending"),
        )

    def options(self, accounts):
        rows = self.session.scalars(
            select(PackingOrder)
            .where(
                PackingOrder.source_account_ref.in_(accounts),
                PackingOrder.warehouse_id == "16168",
                PackingOrder.status == "approved",
            )
            .order_by(PackingOrder.created_at.desc())
        )
        values = {}
        for row in rows:
            if row.store_id:
                values.setdefault(row.store_id, row.snapshot_json.get("store_name") or row.store_id)
        return WarehouseOptions(
            stores=[WarehouseOption(value=k, label=v) for k, v in sorted(values.items())]
        )

    def events(self, ident, accounts, page, page_size):
        self.order(ident, accounts)
        stmt = select(PackingEvent).where(
            PackingEvent.order_id == ident,
            PackingEvent.source_account_ref.in_(accounts),
        )
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        items = []
        for event in self.session.scalars(
            stmt.order_by(PackingEvent.order_version.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ):
            request = event.request_json
            items.append(
                WarehouseEventRead(
                    id=event.id,
                    kind=event.event_kind,
                    actor_uid=event.actor_uid,
                    order_version=event.order_version,
                    occurred_at=event.occurred_at,
                    reason=request.get("reason") or request.get("text") or request.get("note"),
                    before=request.get("before"),
                    result=event.response_json,
                )
            )
        return WarehouseEvents(items=items, total=total)

    def command(self, ident, kind, cmd, actor, accounts):
        if cmd.source_account_ref not in accounts:
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
        self.base.guard_local()
        s = self.session
        request = {
            "kind": kind,
            "order_id": str(ident),
            "actor_uid": actor,
            **cmd.model_dump(mode="json"),
        }
        digest = fingerprint(request)
        try:
            s.execute(text("SET LOCAL lock_timeout='5s'"))
            s.execute(text("SET LOCAL statement_timeout='30s'"))
            self.base.lock(f"packing-command:{cmd.source_account_ref}:{cmd.idempotency_key}")
            self.base.lock(f"{cmd.source_account_ref}\0{16168}")
            order = self.repo.order(ident, frozenset({cmd.source_account_ref}), lock=True)
            if order is None:
                missing()
            prior = s.scalar(
                select(PackingEvent).where(
                    PackingEvent.source_account_ref == cmd.source_account_ref,
                    PackingEvent.idempotency_key == cmd.idempotency_key,
                )
            )
            if prior:
                if prior.request_hash != digest:
                    conflict("IDEMPOTENCY_KEY_REUSED")
                result = WarehouseOrderRead.model_validate(prior.response_json)
                s.commit()
                return result
            if s.scalar(
                select(PackingManualRequest.id).where(
                    PackingManualRequest.source_account_ref == cmd.source_account_ref,
                    PackingManualRequest.idempotency_key == cmd.idempotency_key,
                )
            ):
                conflict("IDEMPOTENCY_KEY_REUSED")
            if order.status != "approved":
                conflict("ORDER_STATE_CHANGED")
            if order.version != cmd.expected_version:
                conflict("ORDER_VERSION_CHANGED")
            before = self.read_rows([order])[0]
            box = s.scalar(select(PackingBoxSet).where(PackingBoxSet.order_id == ident))
            event_id = uuid4()
            outcome = "saved"
            if kind in {"boxes", "rebox"}:
                if kind == "boxes" and box and box.completed_at:
                    conflict("ALREADY_COMPLETED")
                if kind == "rebox":
                    if not box or not box.completed_at:
                        conflict("COMPLETED_BOXES_REQUIRED")
                    if box.version != cmd.expected_box_version:
                        conflict("BOX_VERSION_CHANGED")
                    variance = s.get(PackingVarianceCase, ident)
                    if variance and variance.state in {"released", "voided"}:
                        conflict("UNPACKED_ALREADY_DISPOSED")
                total = sum(row.boxes * row.units_per_box for row in cmd.lines)
                reason = (cmd.reason or "").strip()
                if kind == "rebox":
                    decision, budget = self.overpack.assess(order, total, cmd)
                    if decision.outcome == "supplement_required":
                        pending = self.overpack.block(order, total, decision, budget, actor, reason)
                        pending.evidence = {
                            **pending.evidence,
                            "proposed_lines": [r.model_dump(mode="json") for r in cmd.lines],
                        }
                        outcome = "blocked"
                    else:
                        self.overpack.reserve(order, total, budget)
                    if decision.blocker:
                        conflict(decision.blocker)
                    if outcome != "blocked":
                        if decision.unpacked_qty:
                            if variance is None:
                                variance = PackingVarianceCase(
                                    order_id=ident,
                                    kind="under",
                                    state="pending",
                                    quantity=decision.unpacked_qty,
                                    actor_uid=actor,
                                )
                                s.add(variance)
                            variance.kind = "under"
                            variance.gap_qty = None
                            variance.state = "pending"
                            variance.quantity = decision.unpacked_qty
                            variance.reason_category = cmd.reason_category
                            variance.reason = reason
                            variance.actor_uid = actor
                            variance.evidence = {
                                "approved_qty": order.qty,
                                "packed_qty": total,
                                "stock_release": "pending_mid_office_disposition",
                            }
                            variance.updated_at = now()
                        elif variance:
                            variance.state = "resolved"
                            variance.actor_uid = actor
                            variance.updated_at = now()
                if outcome != "blocked":
                    if box is None:
                        box = PackingBoxSet(
                            order_id=ident,
                            total_qty=total,
                            approved_qty_snapshot=order.qty,
                            actor_uid=actor,
                            variance_reason=reason or None,
                        )
                        s.add(box)
                        s.flush()
                    else:
                        box.version += 1
                        s.execute(delete(PackingBoxLine).where(PackingBoxLine.box_set_id == box.id))
                    box.total_qty = total
                    box.variance_reason = reason or None
                    box.actor_uid = actor
                    box.updated_at = now()
                    previous_package = box.package_snapshot
                    box.package_snapshot = (
                        {
                            "source": "warehouse_draft",
                            "values": cmd.package.model_dump(mode="json"),
                        }
                        if cmd.package
                        else previous_package
                        if kind == "rebox"
                        else None
                    )
                    if kind == "rebox" and cmd.package:
                        box.package_snapshot = {
                            "source": "warehouse_measurement",
                            "values": cmd.package.model_dump(mode="json"),
                        }
                    for index, row in enumerate(cmd.lines, 1):
                        dims = BOX_DIMENSIONS.get(
                            row.box_type, (row.length_cm, row.width_cm, row.height_cm)
                        )
                        if row.box_type != "custom" and any(
                            v is not None and v != expected
                            for v, expected in zip(
                                (row.length_cm, row.width_cm, row.height_cm),
                                dims,
                                strict=True,
                            )
                        ):
                            conflict("FIXED_BOX_DIMENSIONS_CHANGED")
                        s.add(
                            PackingBoxLine(
                                box_set_id=box.id,
                                line_no=index,
                                box_type=row.box_type,
                                boxes=row.boxes,
                                units_per_box=row.units_per_box,
                                gross_weight_kg=row.gross_weight_kg,
                                length_cm=dims[0],
                                width_cm=dims[1],
                                height_cm=dims[2],
                            )
                        )
                    if kind == "boxes":
                        self.overpack.refresh_draft_case(order, total, actor)
            elif kind == "done":
                if box is None:
                    conflict("BOXES_REQUIRED")
                if box.completed_at:
                    conflict("ALREADY_COMPLETED")
                if box.version != cmd.expected_box_version:
                    conflict("BOX_VERSION_CHANGED")
                decision, budget = self.overpack.assess(order, box.total_qty, cmd)
                if decision.blocker:
                    conflict(decision.blocker)
                if (
                    sum(line.boxes * line.units_per_box for line in before.box_set.lines)
                    != box.total_qty
                ):
                    conflict("BOX_TOTAL_CHANGED")
                product = before.product_requirement
                if product.version != cmd.requirement_version:
                    conflict("PRODUCT_REQUIREMENT_CHANGED")
                measured = cmd.package
                if (
                    measured is None
                    and box.package_snapshot
                    and box.package_snapshot.get("source") == "warehouse_draft"
                ):
                    measured = PackageInput.model_validate(box.package_snapshot["values"])
                if product.state != "complete" and measured is None:
                    conflict("PACKAGE_REQUIRED")
                if decision.outcome == "supplement_required":
                    self.overpack.block(order, box.total_qty, decision, budget, actor, cmd.reason)
                    outcome = "blocked"
                else:
                    self.overpack.reserve(order, box.total_qty, budget)
                    outcome = "completed"
                    if decision.unpacked_qty:
                        variance = s.get(PackingVarianceCase, ident)
                        if variance is not None:
                            if variance.kind != "over":
                                conflict("VARIANCE_STATE_CHANGED")
                            s.delete(variance)
                            s.flush()
                        s.add(
                            PackingVarianceCase(
                                order_id=ident,
                                kind="under",
                                state="pending",
                                quantity=decision.unpacked_qty,
                                reason_category=cmd.reason_category,
                                reason=(cmd.reason or "").strip() or None,
                                actor_uid=actor,
                                evidence={
                                    "approved_qty": order.qty,
                                    "packed_qty": box.total_qty,
                                    "stock_release": "pending_mid_office_disposition",
                                },
                            )
                        )
                        box.variance_reason = UNDER_REASONS[cmd.reason_category] + (
                            ": " + cmd.reason.strip() if cmd.reason else ""
                        )
                    box.completed_at = now()
                    box.completed_by = actor
                    box.product_snapshot_id = product.source_snapshot_id
                    box.package_snapshot = {
                        "source": "warehouse_measurement" if measured else "product_snapshot",
                        "values": (measured or product.package).model_dump(mode="json"),
                        "snapshot_id": str(product.source_snapshot_id)
                        if product.source_snapshot_id
                        else None,
                    }
                    box.version += 1
                    box.updated_at = now()
            elif kind == "unpacked":
                variance = s.get(PackingVarianceCase, ident)
                if (
                    not box
                    or not box.completed_at
                    or not variance
                    or variance.kind != "under"
                    or variance.state != "pending"
                ):
                    conflict("NO_PENDING_UNPACKED")
                allocation = s.scalar(
                    select(PackingAllocation)
                    .where(PackingAllocation.order_id == ident)
                    .with_for_update()
                )
                if (
                    allocation is None
                    or allocation.released_at is not None
                    or allocation.qty != order.qty
                ):
                    conflict("ALLOCATION_STATE_CHANGED")
                previous_qty = allocation.qty
                if cmd.action == "resend":
                    # The original approval Q is immutable; only its live hold is reduced.
                    allocation.qty = box.total_qty
                    variance.state = "released"
                else:
                    # Do not invent a Lingxing stock write-off. Keep an exclusion hold
                    # until mid-office reconciles physical/provider inventory separately.
                    variance.state = "voided"
                variance.evidence = {
                    **variance.evidence,
                    "disposition": cmd.action,
                    "disposition_reason": cmd.reason,
                    "hold_before": previous_qty,
                    "hold_after": allocation.qty,
                    "operator": actor,
                    "disposed_at": now().isoformat(),
                }
                variance.actor_uid = actor
                variance.updated_at = now()
            elif kind == "ib":
                self.overpack.register_ib(order, cmd.inbound_order_sn, actor)
            elif kind == "sync":
                code = self.overpack.sync(order, actor)
                outcome = "ready" if code == "MATCHED" else "blocked"
            elif kind == "customs":
                if order.customs_value is cmd.value:
                    conflict("NO_CHANGE")
                order.customs_value = cmd.value
                order.customs_src = "manual"
            elif kind != "note":
                raise ValueError("unsupported warehouse command")
            order.version += 1
            order.updated_at = now()
            # Insert the immutable event first so the current-note FK is valid.
            event = PackingEvent(
                id=event_id,
                order_id=ident,
                source_account_ref=order.source_account_ref,
                idempotency_key=cmd.idempotency_key,
                actor_uid=actor,
                event_kind=kind,
                order_version=order.version,
                request_hash=digest,
                request_json={**request, "before": before.model_dump(mode="json")},
                response_json={},
            )
            if kind == "note":
                current = s.get(PackingWarehouseNote, ident)
                if cmd.category == "resolved" and (current is None or current.resolved):
                    conflict("NO_ACTIVE_NOTE")
                # Flush the event before creating/updating its projection, never mutate it later.
                # Immutable events are INSERT-only; build the response before inserting.
                note_value = NoteRead(
                    category=cmd.category,
                    category_label=NOTE_LABELS[cmd.category],
                    text=cmd.text,
                    resolved=cmd.category == "resolved",
                    actor_uid=actor,
                    updated_at=now(),
                )
            s.flush()
            result = self.read_rows([order])[0].model_copy(update={"command_outcome": outcome})
            if kind == "note":
                result = result.model_copy(update={"current_note": note_value})
            event.response_json = result.model_dump(mode="json")
            s.add(event)
            s.flush()
            if kind == "note":
                if current is None:
                    current = PackingWarehouseNote(order_id=ident)
                    s.add(current)
                current.category = cmd.category
                current.text = cmd.text
                current.resolved = cmd.category == "resolved"
                current.last_event_id = event_id
                current.actor_uid = actor
                current.updated_at = note_value.updated_at
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise

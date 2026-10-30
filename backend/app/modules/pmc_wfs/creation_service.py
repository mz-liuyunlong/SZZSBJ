"""Count-based commands with scope, row locks and replay-safe operation snapshots."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError

from app.core.api import ApiError
from app.core.config import get_settings
from app.modules.pmc_domestic.packing_rules import fingerprint
from app.modules.pmc_domestic.packing_service import conflict, missing
from app.modules.pmc_wfs.allocation import allocate
from app.modules.pmc_wfs.creation_models import (
    WfsBoxHold,
    WfsCreation,
    WfsCreationEvent,
    WfsCreationTicket,
)
from app.modules.pmc_wfs.creation_schemas import (
    OperationList,
    OperationRead,
    ShipmentRead,
    TicketRead,
)


def guard_write(session):
    """V2 stays local/test; isolated test instances need not share the business DB port."""
    env = get_settings().app_env.value
    url = session.get_bind().url
    if env not in {"local", "test"} or url.host not in {"127.0.0.1", "localhost"}:
        raise ApiError(code="WFS_LOCAL_ONLY", status_code=403)
    if env == "test" and not (url.database or "").startswith("wfs_v2_test_"):
        raise ApiError(code="WFS_ISOLATED_TEST_DATABASE_REQUIRED", status_code=403)
    if env == "local" and (url.database != "szzsbj_dev" or url.port != 55432):
        raise ApiError(code="WFS_LOCAL_ONLY", status_code=403)


def holds(session, orders):
    return list(session.scalars(select(WfsBoxHold).where(WfsBoxHold.order_id.in_(orders))))


class CreationService:
    def __init__(self, base, gateway, dispatch):
        from app.modules.pmc_wfs.repository import require_creation_schema

        require_creation_schema(base.session)
        self.base, self.s, self.gateway, self.dispatch = base, base.session, gateway, dispatch

    def preview(self, command, lock=False):
        selections = [command, *command.additional_selections]
        sources, used, identities = [], set(), {}
        for choice in sorted(selections, key=lambda s: str(s.order_id)):
            order = self.base.order(choice.order_id, lock=lock)
            row = self.base.detail(order.id)
            box = row.order.box_set
            if order.version != choice.expected_version:
                conflict("ORDER_VERSION_CHANGED")
            if not box or box.version != choice.expected_box_version:
                conflict("BOX_VERSION_CHANGED")
            if row.blocked_reasons:
                conflict("PACKING_NOT_ELIGIBLE")
            identity = (row.order.item_id, row.order.gtin, row.order.msku)
            if order.sku in identities and identities[order.sku] != identity:
                conflict("SKU_IDENTITY_CONFLICT")
            identities[order.sku] = identity
            legacy = self.base.repo.occupied([order.id])
            used.update((h.box_line_id, h.box_ordinal) for h in holds(self.s, [order.id]))
            used.update(
                (line.id, i)
                for line in box.lines
                if line.id in legacy
                for i in range(1, line.boxes + 1)
            )
            sources.append((order, box))
        if len({(o.source_account_ref, o.store_id, o.business_test) for o, _ in sources}) != 1:
            conflict("STORE_OR_TEST_MIXED")
        return allocate(command, sources, used)

    def operation(self, ident, lock=False):
        stmt = select(WfsCreation).where(
            WfsCreation.id == ident,
            WfsCreation.source_account_ref.in_(self.base.accounts),
        )
        if self.base.stores is not None:
            stmt = stmt.where(WfsCreation.store_id.in_(self.base.stores))
        op = self.s.scalar(stmt.with_for_update() if lock else stmt)
        if op is None:
            missing()
        return op

    def read(self, ident):
        op = self.operation(ident)
        tickets = self.s.scalars(
            select(WfsCreationTicket)
            .where(WfsCreationTicket.operation_id == op.id)
            .order_by(WfsCreationTicket.number)
        )
        return OperationRead(
            id=op.id,
            order_id=op.order_id,
            state=op.state,
            created_at=op.created_at,
            automatically_approved_at=op.snapshot.get("automatic_approval", {}).get("at"),
            tickets=[
                TicketRead(
                    id=t.id,
                    number=t.number,
                    state=t.state,
                    allocation=t.allocation,
                    shipments=[
                        ShipmentRead(shipment_id=sid, label_state=value["state"])
                        for sid, value in t.result.get("labels", {}).items()
                    ],
                    error_code=t.error_code,
                )
                for t in tickets
            ],
        )

    def list(self, order_id, page, size):
        self.base.order(order_id)
        stmt = select(WfsCreation).where(
            or_(
                WfsCreation.order_id == order_id,
                WfsCreation.id.in_(
                    select(WfsCreationTicket.operation_id)
                    .join(WfsBoxHold, WfsBoxHold.ticket_id == WfsCreationTicket.id)
                    .where(WfsBoxHold.order_id == order_id)
                ),
            ),
            WfsCreation.source_account_ref.in_(self.base.accounts),
        )
        if self.base.stores is not None:
            stmt = stmt.where(WfsCreation.store_id.in_(self.base.stores))
        total = self.s.scalar(select(func.count()).select_from(stmt.subquery()))
        ids = list(
            self.s.scalars(
                stmt.order_by(WfsCreation.created_at.desc(), WfsCreation.id)
                .offset((page - 1) * size)
                .limit(size)
            )
        )
        return OperationList(items=[self.read(op.id) for op in ids], total=total)

    def submit(self, cmd, actor):
        guard_write(self.s)
        if cmd.source_account_ref not in self.base.accounts:
            raise ApiError(code="DATA_SCOPE_DENIED", status_code=403)
        request = {"actor_uid": actor, **cmd.model_dump(mode="json")}
        digest = fingerprint(request)
        try:
            self.s.execute(text("SET LOCAL lock_timeout='5s'"))
            self.base.base.lock(f"wfs-v2:{cmd.source_account_ref}:{cmd.idempotency_key}")
            self.base.base.lock(f"{cmd.source_account_ref}\0{16168}")
            prior = self.s.scalar(
                select(WfsCreation).where(
                    WfsCreation.source_account_ref == cmd.source_account_ref,
                    WfsCreation.idempotency_key == cmd.idempotency_key,
                )
            )
            if prior:
                self.operation(prior.id)
                if prior.request_hash != digest:
                    conflict("IDEMPOTENCY_KEY_REUSED")
                result = self.read(prior.id)
                self.s.commit()
                return result
            preview = self.preview(cmd, lock=True)
            order = self.base.order(cmd.order_id)
            if order.source_account_ref != cmd.source_account_ref:
                missing()
            if preview.preview_hash != cmd.preview_hash:
                conflict("ALLOCATION_PREVIEW_CHANGED")
            snapshot = {
                **request,
                "order": self.base.detail(order.id).order.model_dump(mode="json"),
                "orders": [
                    self.base.detail(s.order_id).order.model_dump(mode="json")
                    for s in preview.selections
                ],
            }
            self.gateway.validate(snapshot)  # Reject before any persistent hold when disabled.
            snapshot["automatic_approval"] = {
                "at": datetime.now(UTC).isoformat(),
                "actor": "system:wfs-validation",
                "rule_version": "wfs-v2-20261029",
                "checks": [
                    "permission",
                    "scope",
                    "packing",
                    "versions",
                    "quantities",
                    "identity",
                    "availability",
                    "execution_capability",
                ],
            }
            op = WfsCreation(
                id=uuid4(),
                order_id=order.id,
                source_account_ref=order.source_account_ref,
                store_id=order.store_id,
                idempotency_key=cmd.idempotency_key,
                request_hash=digest,
                snapshot=snapshot,
                actor_uid=actor,
                state="QUEUED",
            )
            self.s.add(op)
            self.s.flush()
            for allocation in preview.tickets:
                ticket = WfsCreationTicket(
                    id=uuid4(),
                    operation_id=op.id,
                    number=allocation.number,
                    state="QUEUED",
                    allocation=allocation.model_dump(mode="json"),
                    result={},
                )
                self.s.add(ticket)
                self.s.flush()
                self.s.add_all(
                    [
                        WfsBoxHold(
                            ticket_id=ticket.id,
                            order_id=r.order_id,
                            box_line_id=r.line_id,
                            box_version=r.box_version,
                            box_ordinal=i,
                        )
                        for r in allocation.ranges
                        for i in range(r.start, r.end + 1)
                    ]
                )
            self.s.add(
                WfsCreationEvent(
                    operation_id=op.id,
                    actor_uid=actor,
                    kind="confirmed",
                    evidence={"request_hash": digest, "preview_hash": preview.preview_hash},
                )
            )
            self.s.add(
                WfsCreationEvent(
                    operation_id=op.id,
                    actor_uid="system:wfs-validation",
                    kind="automatically_approved",
                    evidence=snapshot["automatic_approval"],
                )
            )
            self.s.commit()
            ident = op.id
        except IntegrityError:
            self.s.rollback()
            conflict("WFS_BOXES_OCCUPIED_OR_INVALID")
        except Exception:
            self.s.rollback()
            raise
        # The committed QUEUED record is recoverable if broker delivery fails.
        try:
            self.dispatch(str(ident), "execute")
        except Exception:
            self.s.add(
                WfsCreationEvent(
                    operation_id=ident,
                    actor_uid=actor,
                    kind="dispatch_failed",
                    evidence={},
                )
            )
            self.s.commit()
        self.s.expire_all()
        return self.read(ident)

    def recover(self, ident, actor, action):
        guard_write(self.s)
        op = self.operation(ident)
        self.gateway.validate(op.snapshot)
        self.s.add(
            WfsCreationEvent(
                operation_id=op.id,
                actor_uid=actor,
                kind=f"requested_{action}",
                evidence={},
            )
        )
        self.s.commit()
        try:
            self.dispatch(str(ident), action)
        except Exception:
            raise ApiError(code="WFS_DISPATCH_FAILED", status_code=503) from None
        self.s.expire_all()
        return self.read(ident)

    def optional_preview(self, cmd):
        allocation = self.preview(cmd)
        snapshot = {
            **cmd.model_dump(mode="json"),
            "allocation": allocation.model_dump(mode="json"),
            "orders": [
                self.base.detail(s.order_id).order.model_dump(mode="json")
                for s in allocation.selections
            ],
            "order": self.base.detail(cmd.order_id).order.model_dump(mode="json"),
        }
        if snapshot["order"]["source_account_ref"] != cmd.source_account_ref:
            missing()
        self.gateway.validate(snapshot)
        return {"preview_hash": allocation.preview_hash, "result": self.gateway.preview(snapshot)}

    def label(self, ident, shipment_id):
        import base64

        self.operation(ident)
        for ticket in self.s.scalars(
            select(WfsCreationTicket).where(
                WfsCreationTicket.operation_id == ident,
            )
        ):
            label = ticket.result.get("labels", {}).get(shipment_id)
            if label and label.get("state") == "READY":
                return base64.b64decode(label["pdf"], validate=True)
        missing()

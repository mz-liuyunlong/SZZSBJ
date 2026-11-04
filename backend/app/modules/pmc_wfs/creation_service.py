"""Count-based commands with scope, row locks and replay-safe operation snapshots."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError

from app.core.api import ApiError
from app.core.config import get_settings
from app.modules.pmc_domestic.packing_rules import fingerprint
from app.modules.pmc_domestic.packing_service import conflict, missing
from app.modules.pmc_wfs.allocation import allocate
from app.modules.pmc_wfs.creation_config import CREATION_MODES, POLL_MAX_ATTEMPTS, creation_mode
from app.modules.pmc_wfs.creation_models import (
    WfsBoxHold,
    WfsCreation,
    WfsCreationEvent,
    WfsCreationTicket,
)
from app.modules.pmc_wfs.creation_schemas import (
    CreationDefaultsRead,
    OperationList,
    OperationRead,
    ProbeResult,
    ShipmentRead,
    TicketRead,
)
from app.modules.pmc_wfs.repository import domestic_packing_lock_key


def guard_write(session):
    """Local/test keep the original database checks. Any other environment writes only when
    the owner switched creation on (``WFS_CREATION_MODE`` = single / batch)."""
    env = get_settings().app_env.value
    url = session.get_bind().url
    if env not in {"local", "test"}:
        if creation_mode() not in CREATION_MODES:
            raise ApiError(code="WFS_CREATION_DISABLED", status_code=403)
        return
    if url.host not in {"127.0.0.1", "localhost"}:
        raise ApiError(code="WFS_LOCAL_ONLY", status_code=403)
    if env == "test" and not (url.database or "").startswith("wfs_v2_test_"):
        raise ApiError(code="WFS_ISOLATED_TEST_DATABASE_REQUIRED", status_code=403)
    if env == "local" and (url.database != "szzsbj_dev" or url.port != 55432):
        raise ApiError(code="WFS_LOCAL_ONLY", status_code=403)


def creation_defaults(session, account):
    """WFS 设置 · 创建默认值 for one account (8088 defaults when never saved)."""
    from app.modules.pmc_wfs.settings_models import WfsCreationDefaults
    from app.modules.pmc_wfs.settings_seed import CREATION_DEFAULTS

    row = session.get(WfsCreationDefaults, account)
    if row is None:
        return {**CREATION_DEFAULTS, "saved": False}
    return {
        "transport": row.transport,
        "ship_date_offset": row.ship_date_offset,
        "pallet_boxes": row.pallet_boxes,
        "mixed_boxes": row.mixed_boxes,
        "carrier_opt": row.carrier_opt,
        "saved": True,
    }


def default_delivery_at(defaults):
    """Expected delivery = today (Asia/Shanghai) + ship_date_offset days, midnight local."""
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("Asia/Shanghai")
    day = datetime.now(zone).date() + timedelta(days=int(defaults["ship_date_offset"]))
    return datetime(day.year, day.month, day.day, tzinfo=zone)


AUTOMATIC_CHECKS_RULE_VERSION = "wfs-v2-20261029"


def manually_approved(op) -> bool:
    """True only when a human approval record exists (approval_ref, approver, time)."""
    return bool(op.approval_ref and op.approved_by and op.approved_at)


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
            automatic_checks_at=op.snapshot.get("automatic_checks", {}).get("at"),
            approval_ref=op.approval_ref,
            approved_by=op.approved_by,
            approved_at=op.approved_at,
            tickets=[
                TicketRead(
                    id=t.id,
                    number=t.number,
                    state=t.state,
                    allocation=t.allocation,
                    shipments=[
                        ShipmentRead(
                            shipment_id=sid,
                            label_state=value["state"],
                            fc=(t.result.get("shipments", {}).get(sid) or {}).get("fc"),
                        )
                        for sid, value in t.result.get("labels", {}).items()
                    ],
                    error_code=t.error_code,
                    error_message=t.result.get("error_message"),
                    submissions=int(t.result.get("submissions", 0)),
                    polls=(t.result.get("polling") or {}).get("count"),
                    max_polls=(t.result.get("polling") or {}).get("max", POLL_MAX_ATTEMPTS)
                    if t.result.get("polling")
                    else None,
                    next_poll_at=(t.result.get("polling") or {}).get("next_at"),
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
            # Same lock as the domestic packing/warehouse commands (see repository docstring).
            self.base.base.lock(domestic_packing_lock_key(cmd.source_account_ref))
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
            # WFS 设置 · 创建默认值: recorded with the operation; fills the delivery date.
            defaults = creation_defaults(self.s, cmd.source_account_ref)
            snapshot["creation_defaults"] = defaults
            if not snapshot.get("expected_delivery_at"):
                snapshot["expected_delivery_at"] = default_delivery_at(defaults).isoformat()
            self.gateway.validate(snapshot)  # Reject before any persistent hold when disabled.
            # Machine checks only. They are evidence for the human approver, never an
            # approval: the operation waits in AWAITING_APPROVAL until approve() runs.
            snapshot["automatic_checks"] = {
                "at": datetime.now(UTC).isoformat(),
                "actor": "system:wfs-validation",
                "rule_version": AUTOMATIC_CHECKS_RULE_VERSION,
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
                state="AWAITING_APPROVAL",
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
                    kind="automatic_checks_passed",
                    evidence=snapshot["automatic_checks"],
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
        # Boxes are held, nothing is dispatched: execution starts only from approve().
        self.s.expire_all()
        return self.read(ident)

    def approve(self, ident, cmd, actor):
        """Record the written human approval for one operation, then dispatch it."""
        guard_write(self.s)
        try:
            self.s.execute(text("SET LOCAL lock_timeout='5s'"))
            op = self.operation(ident, lock=True)
            if op.state != "AWAITING_APPROVAL" or manually_approved(op):
                conflict("WFS_APPROVAL_NOT_PENDING")
            self.gateway.validate(op.snapshot)
            op.approval_ref = cmd.approval_ref
            op.approved_by = actor
            op.approved_at = datetime.now(UTC)
            op.state = "QUEUED"
            self.s.add(
                WfsCreationEvent(
                    operation_id=op.id,
                    actor_uid=actor,
                    kind="manually_approved",
                    evidence={
                        "approval_ref": cmd.approval_ref,
                        "approved_by": actor,
                        "approved_at": op.approved_at.isoformat(),
                        "automatic_checks": op.snapshot.get("automatic_checks"),
                    },
                )
            )
            self.s.commit()
        except Exception:
            self.s.rollback()
            raise
        # The committed QUEUED (approved) record is recoverable if broker delivery fails.
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
        """reconcile = read back now; labels = fetch missing labels; retry = resend FAILED
        tickets (after a read-back by the same order id, in the worker)."""
        guard_write(self.s)
        if action == "retry":
            return self.retry(ident, actor)
        op = self.operation(ident)
        if not manually_approved(op):
            conflict("WFS_APPROVAL_REQUIRED")
        if not (self.gateway.enabled or getattr(self.gateway, "preview_enabled", False)):
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

    def retry(self, ident, actor):
        """FAILED tickets only. Boxes are held again first; while anything of this operation
        is still being submitted (RUNNING) a retry is refused."""
        try:
            self.s.execute(text("SET LOCAL lock_timeout='5s'"))
            op = self.operation(ident, lock=True)
            if not manually_approved(op):
                conflict("WFS_APPROVAL_REQUIRED")
            self.gateway.validate(op.snapshot)
            tickets = list(
                self.s.scalars(
                    select(WfsCreationTicket)
                    .where(WfsCreationTicket.operation_id == op.id)
                    .order_by(WfsCreationTicket.number)
                    .with_for_update()
                )
            )
            if any(t.state in ("RUNNING", "QUEUED", "UNKNOWN") for t in tickets):
                raise ApiError(
                    code="WFS_SUBMITTING",
                    status_code=409,
                    message="这批货件正在提交或等待 Walmart 结果，不能重复提交",
                )
            failed = [t for t in tickets if t.state == "FAILED"]
            if not failed:
                conflict("WFS_NOTHING_TO_RETRY")
            for ticket in failed:
                self._hold_again(ticket)
                ticket.state, ticket.error_code = "QUEUED", None
            op.state = "QUEUED"
            self.s.add(
                WfsCreationEvent(
                    operation_id=op.id,
                    actor_uid=actor,
                    kind="requested_retry",
                    evidence={"tickets": [str(t.id) for t in failed]},
                )
            )
            self.s.commit()
        except IntegrityError:
            self.s.rollback()
            raise ApiError(
                code="WFS_BOXES_OCCUPIED_OR_INVALID",
                status_code=409,
                message="这票的箱子已被其他货件占用，不能重试",
            ) from None
        except Exception:
            self.s.rollback()
            raise
        try:
            self.dispatch(str(ident), "retry")
        except Exception:
            self.s.add(
                WfsCreationEvent(
                    operation_id=ident, actor_uid=actor, kind="dispatch_failed", evidence={}
                )
            )
            self.s.commit()
        self.s.expire_all()
        return self.read(ident)

    def _hold_again(self, ticket):
        ranges = ticket.allocation["ranges"]
        for order_id in {r["order_id"] for r in ranges}:
            order = self.base.order(UUID(str(order_id)), lock=True)
            box = self.base.detail(order.id).order.box_set
            if not box or any(
                r["box_version"] != box.version for r in ranges if r["order_id"] == order_id
            ):
                conflict("BOX_VERSION_CHANGED")
        if self.s.scalar(
            select(func.count()).select_from(WfsBoxHold).where(WfsBoxHold.ticket_id == ticket.id)
        ):
            return  # still held (e.g. an old ticket failed before release existed)
        self.s.add_all(
            [
                WfsBoxHold(
                    ticket_id=ticket.id,
                    order_id=UUID(str(r["order_id"])),
                    box_line_id=UUID(str(r["line_id"])),
                    box_version=r["box_version"],
                    box_ordinal=i,
                )
                for r in ranges
                for i in range(r["start"], r["end"] + 1)
            ]
        )
        self.s.flush()

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
        defaults = creation_defaults(self.s, cmd.source_account_ref)
        snapshot["creation_defaults"] = defaults
        if not snapshot.get("expected_delivery_at"):
            snapshot["expected_delivery_at"] = default_delivery_at(defaults).isoformat()
        if not getattr(self.gateway, "preview_enabled", self.gateway.enabled):
            self.gateway.validate(snapshot)
        return {"preview_hash": allocation.preview_hash, "result": self.gateway.preview(snapshot)}

    def defaults(self, account):
        if account not in self.base.accounts:
            raise ApiError(code="DATA_SCOPE_DENIED", status_code=403)
        values = creation_defaults(self.s, account)
        return CreationDefaultsRead(
            source_account_ref=account,
            expected_delivery_date=default_delivery_at(values).date().isoformat(),
            **values,
        )

    def probe(self, store_id):
        """Read-only Walmart connectivity check for one store (探测, no shipment created)."""
        if self.base.stores is not None and store_id not in self.base.stores:
            raise ApiError(code="DATA_SCOPE_DENIED", status_code=403)
        probe = getattr(self.gateway, "probe", None)
        if probe is None:
            self.gateway.validate({})
        try:
            return ProbeResult(**probe(store_id))
        except ApiError:
            raise
        except Exception as error:
            code = getattr(error, "code", None) or "WFS_PROBE_FAILED"
            raise ApiError(
                code="WFS_PROBE_FAILED", status_code=502, message=f"探测失败：{code}"
            ) from None

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

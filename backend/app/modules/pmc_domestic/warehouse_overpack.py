"""Inventory/exception workflow. Sync reads a governed publication, never Lingxing.

The optional publication provider is a trusted server seam, never accepted from an
HTTP request. It must return a governed current publication, validated again here.
The HTTP route supplies the current publication in this process database.
"""

from uuid import UUID

from sqlalchemy import select, update

from app.modules.pmc_domestic.inbound_models import DomesticBoardPublication as Pub
from app.modules.pmc_domestic.inbound_models import DomesticInboundBoard as Board
from app.modules.pmc_domestic.packing_models import now
from app.modules.pmc_domestic.packing_rules import fingerprint
from app.modules.pmc_domestic.packing_service import conflict
from app.modules.pmc_domestic.packing_stock_repository import PackingStockRepository
from app.modules.pmc_domestic.warehouse_completion_rules import decide_completion
from app.modules.pmc_domestic.warehouse_models import PackingNotificationOutbox as Notice
from app.modules.pmc_domestic.warehouse_models import PackingVarianceCase as Case


def current_board_publication(session, account, warehouse_id, _sku, _inbound_sn):
    """Current inbound publication for this account and warehouse.

    Matching the supplemental inbound row stays in validate_publication.
    This lookup does not call Lingxing and uses only the process database.
    """
    return session.scalar(
        select(Pub.id).where(
            Pub.is_current.is_(True),
            Pub.status == "published",
            Pub.source_account_ref == account,
            Pub.source_warehouse_id == warehouse_id,
        )
    )


class WarehouseOverpack:
    def __init__(self, session, publication_provider=None):
        self.session = session
        self.stock = PackingStockRepository(session)
        self.publication_provider = publication_provider

    def budget(self, order):
        return self.stock.budget(
            order.source_account_ref, order.warehouse_id, order.sku, excluding_extra_order=order.id
        )

    def assess(self, order, total, cmd):
        budget = self.budget(order)
        if total > order.qty and budget.available is None:
            conflict("STOCK_PROOF_UNKNOWN")
        decision = decide_completion(
            order.qty,
            total,
            extra_available=budget.available,
            reason_category=getattr(cmd, "reason_category", None),
            reason=cmd.reason,
            confirm_extra=getattr(cmd, "confirm_extra", False),
        )
        return decision, budget

    def cancel_notices(self, order):
        self.session.execute(
            update(Notice)
            .where(Notice.order_id == order.id, Notice.state == "pending_configuration")
            .values(state="cancelled")
        )

    def block(self, order, total, decision, budget, actor, reason):
        case = self.session.get(Case, order.id)
        signature = fingerprint([order.qty, total, decision.gap_qty])
        should_notify = (
            not case
            or case.kind != "over"
            or case.state != "blocked"
            or case.evidence.get("notification_signature") != signature
        )
        if case is None:
            case = Case(
                order_id=order.id,
                kind="over",
                state="blocked",
                quantity=decision.excess_qty,
                actor_uid=actor,
                evidence={},
            )
            self.session.add(case)
        previous = case.evidence or {}
        case.kind = "over"
        case.state = "blocked"
        case.quantity = decision.excess_qty
        case.gap_qty = decision.gap_qty
        case.reason = reason.strip()
        case.actor_uid = actor
        case.updated_at = now()
        case.evidence = {
            **previous,
            "approved_qty": order.qty,
            "packed_qty": total,
            "required_inbound_qty": decision.gap_qty,
            "source_publication_id": str(budget.publication_id),
            "blocked_at": now().isoformat(),
            "extra_available": budget.available,
            "notification_signature": signature,
            "notification_state": "pending_configuration",
        }
        if should_notify:
            self.cancel_notices(order)
            self.session.add(
                Notice(
                    order_id=order.id,
                    order_version=order.version + 1,
                    kind="overpack",
                    state="pending_configuration",
                    payload={
                        "pk": order.pk,
                        "sku": order.sku,
                        "source_account_ref": order.source_account_ref,
                        "warehouse_id": order.warehouse_id,
                        "approved_qty": order.qty,
                        "packed_qty": total,
                        "excess_qty": decision.excess_qty,
                        "gap_qty": decision.gap_qty,
                        "actor_uid": actor,
                        "occurred_at": now().isoformat(),
                    },
                )
            )
        return case

    def refresh_draft_case(self, order, total, actor):
        case = self.session.get(Case, order.id)
        if not case or case.kind != "over" or case.state not in {"blocked", "ready"}:
            return
        budget = self.budget(order)
        excess = max(0, total - order.qty)
        if excess == 0 or budget.available is not None and excess <= budget.available:
            case.state = "ready" if excess else "resolved"
            case.gap_qty = 0
            case.evidence = {
                **case.evidence,
                "cleared_by": "warehouse_boxes",
                "notification_state": "cancelled",
                "packed_qty": total,
            }
            case.actor_uid = actor
            case.updated_at = now()
            self.cancel_notices(order)
        elif budget.available is not None:
            decision = decide_completion(
                order.qty, total, extra_available=budget.available, reason=case.reason
            )
            self.block(order, total, decision, budget, actor, case.reason)

    def reserve(self, order, total, budget):
        self.stock.replace_extra(order, max(0, total - order.qty), budget)
        case = self.session.get(Case, order.id)
        if case and case.kind == "over":
            case.state = "resolved"
            case.gap_qty = 0
            case.evidence = {
                **{k: v for k, v in case.evidence.items() if k != "proposed_lines"},
                "resolved_at": now().isoformat(),
                "notification_state": "cancelled",
            }
            self.cancel_notices(order)

    def register_ib(self, order, ib, actor):
        case = self.session.get(Case, order.id)
        if not case or case.kind != "over" or case.state != "blocked":
            conflict("NO_BLOCKED_OVERPACK")
        case.supplemental_ib = ib
        case.actor_uid = actor
        case.updated_at = now()
        case.evidence = {
            **case.evidence,
            "ib_registered_at": now().isoformat(),
            "last_sync_code": "NOT_SYNCED",
        }

    def sync(self, order, actor):
        case = self.session.get(Case, order.id)
        if not case or case.kind != "over" or case.state != "blocked" or not case.supplemental_ib:
            conflict("SUPPLEMENTAL_IB_REQUIRED")
        code = "LINGXING_SYNC_NOT_CONFIGURED"
        detail = {}
        if self.publication_provider is not None:
            # The provider only names an already published version. A newer Lingxing
            # capture must finish outside this command and publish before sync can match.
            try:
                with self.session.begin_nested():
                    ident = self.publication_provider(
                        order.source_account_ref,
                        order.warehouse_id,
                        order.sku,
                        case.supplemental_ib,
                    )
            except Exception:
                code = "LINGXING_SYNC_FAILED"
            else:
                code, detail = self.validate_publication(order, case, ident)
        case.evidence = {
            **case.evidence,
            **detail,
            "last_sync_code": code,
            "last_sync_at": now().isoformat(),
        }
        case.actor_uid = actor
        case.updated_at = now()
        if code == "MATCHED":
            case.state = "ready"
            case.gap_qty = 0
            case.evidence = {**case.evidence, "notification_state": "cancelled"}
            self.cancel_notices(order)
        return code

    def validate_publication(self, order, case, ident):
        try:
            ident = UUID(str(ident))
        except (ValueError, TypeError):
            return "SYNC_EVIDENCE_INVALID", {}
        pub = self.session.get(Pub, ident)
        if (
            not pub
            or not pub.is_current
            or pub.source_account_ref != order.source_account_ref
            or pub.source_warehouse_id != order.warehouse_id
        ):
            return "SYNC_SCOPE_MISMATCH", {}
        if (
            str(pub.id) == case.evidence.get("source_publication_id")
            or pub.source_observed_at < case.created_at
        ):
            return "SYNC_EVIDENCE_STALE", {}
        rows = list(
            self.session.scalars(
                select(Board).where(
                    Board.publication_id == ident,
                    Board.source_account_ref == order.source_account_ref,
                    Board.source_warehouse_id == order.warehouse_id,
                    Board.inbound_order_sn == case.supplemental_ib,
                    Board.sku == order.sku,
                )
            )
        )
        if not rows:
            return "IB_SKU_WAREHOUSE_MISMATCH", {}
        # parent_inbound_qty repeats across store attributions: deduplicate at IB×SKU.
        quantities = {r.payload_json.get("parent_inbound_qty") for r in rows}
        required = case.evidence["required_inbound_qty"]
        if len(quantities) != 1 or any(
            isinstance(q, bool) or not isinstance(q, int) or q < 0 for q in quantities
        ):
            return "IB_QUANTITY_UNKNOWN", {}
        actual = quantities.pop()
        if actual < required:
            return "IB_QUANTITY_INSUFFICIENT", {
                "last_sync_gap": required - actual,
                "verified_ib_qty": actual,
            }
        budget = self.budget(order)
        packed = case.evidence["packed_qty"]
        if budget.available is None:
            return "STOCK_PROOF_UNKNOWN", {}
        if max(0, packed - order.qty) > budget.available:
            return "STOCK_STILL_INSUFFICIENT", {
                "last_sync_gap": packed - order.qty - budget.available
            }
        return "MATCHED", {
            "verified_publication_id": str(ident),
            "verified_ib_qty": actual,
            "last_sync_gap": 0,
        }

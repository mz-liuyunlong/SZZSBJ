"""Current published candidates, synchronized purchase evidence and local decisions.

Only positive-balance Huizhou sources participate. SKU/store/ItemID are explicit;
missing mappings stay blocked. Purchase remarks and cumulative receipt counters
are projected from local ODS; GET never calls the provider or freezes an identity.
"""

from collections import defaultdict
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.modules.data_pages.models import LingxingStoreDimension as Store
from app.modules.data_pages.models import WalmartListingDimension as Listing
from app.modules.pmc_domestic.board_item_ids import attach_board_item_ids
from app.modules.pmc_domestic.inbound_models import DomesticBoardPublication as Pub
from app.modules.pmc_domestic.inbound_models import DomesticInboundBoard as Board
from app.modules.pmc_domestic.inbound_schemas import ItemIdentity
from app.modules.pmc_domestic.packing_customs_rules import candidate_customs
from app.modules.pmc_domestic.packing_models import PackingAllocation, PackingOrder
from app.modules.pmc_domestic.packing_procurement_repository import PackingProcurementRepository
from app.modules.pmc_domestic.packing_rules import fingerprint
from app.modules.pmc_domestic.packing_schemas import Candidate, OrderRead
from app.modules.pmc_domestic.packing_stock_models import PackingExtraAllocation
from app.modules.pmc_domestic.packing_stock_repository import PackingStockRepository
from app.modules.pmc_domestic.packing_suggestions import batch_metrics, suggest_quantities
from app.modules.pmc_purchase.gate3_models import DwdPurchaseOrderLineItem


def order_read(row):
    return OrderRead(
        id=row.id,
        candidate_id=row.candidate_id,
        pk=row.pk,
        status=row.status,
        qty=row.qty,
        version=row.version,
        is_test=row.is_test,
        customs_value=row.customs_value,
        customs_src=row.customs_src,
        rwh=row.rwh,
        actor_uid=row.actor_uid,
        note=row.note,
        created_at=row.created_at,
        snapshot=Candidate.model_validate(row.snapshot_json),
        source_snapshot=Candidate.model_validate(row.source_snapshot_json)
        if row.source_snapshot_json
        else None,
        voided_at=row.voided_at,
        void_note=row.void_note,
    )


def matches(row, q):
    if q.store_id and row.store_id not in q.store_id:
        return False
    if q.overdue != "all" and row.overdue is not (q.overdue == "overdue"):
        return False
    if q.arrival != "all" and row.arrival_status != q.arrival:
        return False
    split = getattr(q, "split_arrival", "all")
    if (
        split != "all"
        and row.split_arrival is not {"yes": True, "no": False, "unknown": None}[split]
    ):
        return False
    if q.created_from and (
        not row.candidate_created_on or row.candidate_created_on < q.created_from
    ):
        return False
    if q.created_to and (not row.candidate_created_on or row.candidate_created_on > q.created_to):
        return False
    words = [
        row.inbound_order_sn,
        row.sku,
        row.item_id,
        row.msku,
        *row.purchase_order_sns,
    ]
    return not q.keyword or any(q.keyword.casefold() in (v or "").casefold() for v in words)


class _PackingBoardRow:
    """Adapter so packing candidates reuse the inbound board ItemID resolver."""

    def __init__(self, board: Board) -> None:
        payload = board.payload_json if isinstance(board.payload_json, dict) else {}
        sns = payload.get("purchase_order_sns")
        self.source_account_ref = board.source_account_ref
        self.sku = board.sku
        self.store_id = board.store_id
        self.purchase_order_sns = list(sns) if isinstance(sns, list) else []
        self.item_identities: list[ItemIdentity] = []
        self.identity_status = "missing"


class PackingRepository:
    def __init__(self, session):
        self.session = session

    def orders(self, accounts):
        if not accounts:
            return []
        rows = list(
            self.session.scalars(
                select(PackingOrder)
                .where(
                    PackingOrder.source_account_ref.in_(accounts),
                    PackingOrder.warehouse_id == "16168",
                )
                .order_by(PackingOrder.created_at.desc(), PackingOrder.id)
            )
        )

        return rows

    def candidates(self, accounts, include_decided=False):
        if not accounts:
            return []
        s = self.session
        sources = list(
            s.execute(
                select(Board, Pub)
                .join(Pub, Pub.id == Board.publication_id)
                .where(
                    Pub.is_current.is_(True),
                    Pub.status == "published",
                    Board.source_account_ref.in_(accounts),
                    Board.source_warehouse_id == "16168",
                    Board.balance_num > 0,
                )
            ).all()
        )
        skus = {b.sku for b, _ in sources}
        listing_by_item: dict[tuple[str, str, str, str], Listing] = {}
        store_listing_ids = defaultdict(set)
        if skus:
            for listing in s.scalars(
                select(Listing).where(
                    Listing.source_account_ref.in_(accounts),
                    Listing.local_sku.in_(skus),
                )
            ):
                store_listing_ids[
                    (listing.source_account_ref, listing.store_id, listing.local_sku)
                ].add(listing.item_id)
                listing_by_item[
                    (
                        listing.source_account_ref,
                        listing.store_id,
                        listing.local_sku,
                        listing.item_id,
                    )
                ] = listing
        board_rows = [_PackingBoardRow(b) for b, _ in sources]
        attach_board_item_ids(s, board_rows, frozenset(accounts))
        identities_by_board = {
            str(b.id): row for (b, _), row in zip(sources, board_rows, strict=True)
        }
        used = {
            (a, w, str(b)): q
            for a, w, b, q in s.execute(
                select(
                    PackingAllocation.source_account_ref,
                    PackingAllocation.warehouse_id,
                    PackingAllocation.source_board_id,
                    func.sum(PackingAllocation.qty),
                )
                .join(PackingOrder, PackingOrder.id == PackingAllocation.order_id)
                .where(
                    PackingOrder.status == "approved",
                    PackingAllocation.released_at.is_(None),
                    PackingAllocation.source_account_ref.in_(accounts),
                )
                .group_by(
                    PackingAllocation.source_account_ref,
                    PackingAllocation.warehouse_id,
                    PackingAllocation.source_board_id,
                )
            )
        }
        for a, w, b, q in s.execute(
            select(
                PackingExtraAllocation.source_account_ref,
                PackingExtraAllocation.warehouse_id,
                PackingExtraAllocation.source_board_id,
                func.sum(PackingExtraAllocation.qty),
            )
            .join(PackingOrder, PackingOrder.id == PackingExtraAllocation.order_id)
            .where(
                PackingOrder.status == "approved",
                PackingExtraAllocation.source_account_ref.in_(accounts),
            )
            .group_by(
                PackingExtraAllocation.source_account_ref,
                PackingExtraAllocation.warehouse_id,
                PackingExtraAllocation.source_board_id,
            )
        ):
            key = (a, w, str(b))
            used[key] = used.get(key, 0) + q
        stock = PackingStockRepository(s)
        budgets = stock.budgets(
            {(b.source_account_ref, b.source_warehouse_id, b.sku) for b, _ in sources}
        )
        orders = [r for r in self.orders(accounts) if r.status != "voided"]
        decided = {(r.source_account_ref, str(r.candidate_id)) for r in orders}
        final_decided = {
            (r.source_account_ref, str(r.source_board_id), r.store_id, r.item_id) for r in orders
        }
        stores = {
            (r.source_account_ref, r.store_id): r.store_name
            for r in s.scalars(select(Store).where(Store.source_account_ref.in_(accounts)))
        }
        # DWD repeats original quantity_real when a line is split by plans. Deduplicate
        # by original order_item_id before summing purchase quantities per order+SKU.
        purchase_lines = []
        if skus:
            for p in s.scalars(
                select(DwdPurchaseOrderLineItem).where(
                    DwdPurchaseOrderLineItem.source_account_ref.in_(accounts),
                    DwdPurchaseOrderLineItem.sku.in_(skus),
                )
            ):
                purchase_lines.append(p)
        procurement = PackingProcurementRepository(s, accounts, skus, purchase_lines)
        # Include depleted batches and deduplicate store-split rows; pending alone
        # cannot prove how many times a purchase order arrived.
        batch_orders = defaultdict(dict)
        if skus:
            for batch in s.scalars(
                select(Board)
                .join(Pub, Pub.id == Board.publication_id)
                .where(
                    Pub.is_current.is_(True),
                    Pub.status == "published",
                    Board.source_account_ref.in_(accounts),
                    Board.source_warehouse_id == "16168",
                    Board.sku.in_(skus),
                )
            ):
                data = batch.payload_json if isinstance(batch.payload_json, dict) else {}
                for sn in data.get("purchase_order_sns", []):
                    batch_orders[(batch.source_account_ref, sn, batch.sku)][
                        batch.inbound_order_sn
                    ] = batch.arrival_business_date
        consumed_by_board = defaultdict(lambda: defaultdict(int))
        for account, board_id, item_id, quantity in s.execute(
            select(
                PackingAllocation.source_account_ref,
                PackingAllocation.source_board_id,
                PackingOrder.item_id,
                func.sum(PackingAllocation.qty),
            )
            .join(PackingOrder, PackingOrder.id == PackingAllocation.order_id)
            .where(
                PackingOrder.status == "approved",
                PackingAllocation.released_at.is_(None),
                PackingAllocation.source_account_ref.in_(accounts),
            )
            .group_by(
                PackingAllocation.source_account_ref,
                PackingAllocation.source_board_id,
                PackingOrder.item_id,
            )
        ):
            consumed_by_board[(account, str(board_id))][item_id] += quantity
        for account, board_id, item_id, quantity in s.execute(
            select(
                PackingExtraAllocation.source_account_ref,
                PackingExtraAllocation.source_board_id,
                PackingOrder.item_id,
                func.sum(PackingExtraAllocation.qty),
            )
            .join(PackingOrder, PackingOrder.id == PackingExtraAllocation.order_id)
            .where(
                PackingOrder.status == "approved",
                PackingExtraAllocation.source_account_ref.in_(accounts),
            )
            .group_by(
                PackingExtraAllocation.source_account_ref,
                PackingExtraAllocation.source_board_id,
                PackingOrder.item_id,
            )
        ):
            consumed_by_board[(account, str(board_id))][item_id] += quantity
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        result = []
        for b, pub in sources:
            payload = b.payload_json if isinstance(b.payload_json, dict) else {}
            board_identities = identities_by_board[str(b.id)].item_identities
            if board_identities:
                options: list[tuple[ItemIdentity | None, Listing | None]] = []
                for identity in board_identities:
                    listing = listing_by_item.get(
                        (b.source_account_ref, b.store_id or "", b.sku, identity.item_id)
                    )
                    options.append((identity, listing))
            else:
                options = [(None, None)]
            qty = payload.get("available_good_num")
            if not isinstance(qty, int) or isinstance(qty, bool) or qty < 0:
                qty = None
            available = (
                max(
                    0,
                    qty - used.get((b.source_account_ref, b.source_warehouse_id, str(b.id)), 0),
                )
                if qty is not None
                else None
            )
            key = (b.source_account_ref, b.source_warehouse_id, b.sku)
            global_available = budgets[key].available
            available = (
                min(available, global_available)
                if available is not None and global_available is not None
                else None
            )
            purchases = payload.get("purchase_order_sns", [])
            arrival = procurement.arrival(b.source_account_ref, b.sku, purchases)
            batches = {}
            for sn in purchases:
                batches.update(batch_orders.get((b.source_account_ref, sn, b.sku), {}))
            batch_info = batch_metrics(
                batches,
                b.inbound_order_sn,
                arrival["arrival_status"],
                bool(payload.get("history_complete", False)),
            )
            weights, refs = procurement.weights(
                b.source_account_ref,
                b.sku,
                b.store_id,
                purchases,
                {identity.item_id for identity in board_identities},
                store_listing_ids[(b.source_account_ref, b.store_id, b.sku)],
            )
            box_pcs, box_ref = procurement.box(b.source_account_ref, b.sku)
            suggestions, tail = suggest_quantities(
                qty,
                available,
                weights,
                consumed_by_board[(b.source_account_ref, str(b.id))],
                box_pcs,
            )
            single = len(board_identities) == 1
            notes = []
            if not single and not weights:
                notes.append("采购计划比例依据不足，请人工填写")
            if not box_pcs:
                notes.append("箱规缺失或不唯一，未按箱规取整")
            if tail:
                notes.append(f"不足整箱尾差 {tail} 件，请人工确认")
            suggestion = {
                "rule": "single" if single else "plan_ratio" if weights else "manual",
                "plan_weights": {k: float(v) for k, v in weights.items()},
                "box_pcs": box_pcs,
                "tail_quantity": tail,
                "notes": notes,
                "source_refs": refs + ([box_ref] if box_ref else []),
            }
            for identity, listing in options:
                item = identity.item_id if identity else None
                ident = uuid5(
                    NAMESPACE_URL,
                    f"szzsbj:packing:{b.source_account_ref}:{b.source_warehouse_id}:"
                    f"{b.id}:{item or 'unmapped'}",
                )
                if not include_decided and (
                    (b.source_account_ref, str(ident)) in decided
                    or (b.source_account_ref, str(b.id), b.store_id, item) in final_decided
                ):
                    continue
                blocked = []
                if not b.store_id:
                    blocked.append("STORE_UNKNOWN")
                if listing is None or listing.standard_status != "PUBLISHED":
                    blocked.append("ELIGIBLE_LISTING_MISSING")
                if listing and listing.fulfillment_type != "1":
                    blocked.append("WFS_NOT_CONVERTED")
                if listing and (
                    not listing.gtin or not listing.gtin.isdigit() or len(listing.gtin) != 14
                ):
                    blocked.append("GTIN_INVALID")
                if listing and not listing.msku:
                    blocked.append("MSKU_MISSING")
                if available is None:
                    blocked.append("STOCK_PROOF_UNKNOWN")
                elif available <= 0:
                    blocked.append("STOCK_FULLY_ALLOCATED")
                raw = {
                    "id": str(ident),
                    "source_account_ref": b.source_account_ref,
                    "warehouse_id": b.source_warehouse_id,
                    "warehouse_name": name.strip()
                    if isinstance(name := payload.get("warehouse_name"), str) and name.strip()
                    else None,
                    "publication_id": str(pub.id),
                    "board_id": str(b.id),
                    "inbound_order_sn": b.inbound_order_sn,
                    "sku": b.sku,
                    "store_id": b.store_id,
                    "source_store_id": b.store_id,
                    "store_name": stores.get((b.source_account_ref, b.store_id)),
                    "item_id": item,
                    "gtin": (listing.gtin if listing else None)
                    or (identity.gtin if identity else None),
                    "msku": listing.msku if listing else None,
                    "product_name": payload.get("product_name"),
                    "purchase_order_sns": purchases,
                    **arrival,
                    **batch_info,
                    "quantity_suggestion": suggestion,
                    "candidate_created_on": b.arrival_business_date,
                    "overdue": (today - b.arrival_business_date).days >= 1
                    if b.arrival_business_date
                    else None,
                    "stock_balance": b.balance_num,
                    "available_quantity": available,
                    "default_quantity": available if single else suggestions.get(item),
                    "can_approve": not blocked,
                    "blocked_reasons": blocked,
                    "source_observed_at": pub.source_observed_at,
                    "waiting_days": max(0, (today - b.arrival_business_date).days)
                    if b.arrival_business_date
                    else None,
                    "history_complete": bool(payload.get("history_complete", False)),
                    **candidate_customs(payload.get("customs_proof")),
                }
                # Do not include date-dependent overdue in a source concurrency token.
                token = {
                    k: v
                    for k, v in raw.items()
                    if k
                    not in ("overdue", "store_name", "waiting_days", "warehouse_name", "draft_nos")
                }
                token["listing_hash"] = listing.business_hash if listing else None
                raw["candidate_version"] = fingerprint(token)
                result.append(Candidate.model_validate(raw))
        return result

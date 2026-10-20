"""Current published candidates and local decisions; GETs never touch provider ODS.

Only positive-balance Huizhou sources participate. SKU/store/ItemID are explicit;
missing mappings stay blocked. Receipt facts absent in DWD remain unknown.
"""

from collections import defaultdict
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.modules.data_pages.models import LingxingStoreDimension as Store
from app.modules.data_pages.models import WalmartListingDimension as Listing
from app.modules.pmc_domestic.inbound_models import DomesticBoardPublication as Pub
from app.modules.pmc_domestic.inbound_models import DomesticInboundBoard as Board
from app.modules.pmc_domestic.packing_models import PackingAllocation, PackingOrder
from app.modules.pmc_domestic.packing_rules import fingerprint
from app.modules.pmc_domestic.packing_schemas import Candidate, OrderRead
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
    )


def matches(row, q):
    if q.store_id and row.store_id not in q.store_id:
        return False
    if q.overdue != "all" and row.overdue is not (q.overdue == "overdue"):
        return False
    if q.arrival != "all" and row.arrival_status != q.arrival:
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


class PackingRepository:
    def __init__(self, session):
        self.session = session

    def orders(self, accounts):
        if not accounts:
            return []
        return list(
            self.session.scalars(
                select(PackingOrder)
                .where(
                    PackingOrder.source_account_ref.in_(accounts),
                    PackingOrder.warehouse_id == "16168",
                )
                .order_by(PackingOrder.created_at.desc(), PackingOrder.id)
            )
        )

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
                    Board.source_account_ref.in_(accounts),
                    Board.source_warehouse_id == "16168",
                    Board.balance_num > 0,
                )
            ).all()
        )
        skus = {b.sku for b, _ in sources}
        listings = defaultdict(list)
        if skus:
            for listing in s.scalars(
                select(Listing).where(
                    Listing.source_account_ref.in_(accounts),
                    Listing.local_sku.in_(skus),
                    Listing.standard_status == "PUBLISHED",
                    Listing.fulfillment_type.in_(["0", "1"]),
                )
            ):
                listings[(listing.source_account_ref, listing.local_sku, listing.store_id)].append(
                    listing
                )
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
                    PackingAllocation.source_account_ref.in_(accounts),
                )
                .group_by(
                    PackingAllocation.source_account_ref,
                    PackingAllocation.warehouse_id,
                    PackingAllocation.source_board_id,
                )
            )
        }
        decided = {(r.source_account_ref, str(r.candidate_id)) for r in self.orders(accounts)}
        stores = {
            (r.source_account_ref, r.store_id): r.store_name
            for r in s.scalars(select(Store).where(Store.source_account_ref.in_(accounts)))
        }
        # DWD repeats original quantity_real when a line is split by plans. Deduplicate
        # by original order_item_id before summing purchase quantities per order+SKU.
        purchase = defaultdict(dict)
        if skus:
            for p in s.scalars(
                select(DwdPurchaseOrderLineItem).where(
                    DwdPurchaseOrderLineItem.source_account_ref.in_(accounts),
                    DwdPurchaseOrderLineItem.sku.in_(skus),
                )
            ):
                purchase[(p.source_account_ref, p.order_sn, p.sku)][p.order_item_id] = (
                    p.quantity_real
                )
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        result = []
        for b, pub in sources:
            payload = b.payload_json
            options = listings.get((b.source_account_ref, b.sku, b.store_id), []) or [None]
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
            purchases = payload.get("purchase_order_sns", [])
            values = [
                v
                for sn in purchases
                for v in purchase.get((b.source_account_ref, sn, b.sku), {}).values()
            ]
            purchased = (
                sum(values)
                if values
                and all(v is not None for v in values)
                and all(purchase.get((b.source_account_ref, sn, b.sku)) for sn in purchases)
                else None
            )
            for listing in options:
                item = listing.item_id if listing else None
                ident = uuid5(
                    NAMESPACE_URL,
                    f"szzsbj:packing:{b.source_account_ref}:{b.source_warehouse_id}:"
                    f"{b.id}:{item or 'unmapped'}",
                )
                if not include_decided and (b.source_account_ref, str(ident)) in decided:
                    continue
                blocked = []
                if not b.store_id:
                    blocked.append("STORE_UNKNOWN")
                if listing is None:
                    blocked.append("ELIGIBLE_LISTING_MISSING")
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
                    "publication_id": str(pub.id),
                    "board_id": str(b.id),
                    "inbound_order_sn": b.inbound_order_sn,
                    "sku": b.sku,
                    "store_id": b.store_id,
                    "store_name": stores.get((b.source_account_ref, b.store_id)),
                    "item_id": item,
                    "gtin": listing.gtin if listing else None,
                    "msku": listing.msku if listing else None,
                    "product_name": payload.get("product_name"),
                    "purchase_order_sns": purchases,
                    "arrival_purchased": purchased,
                    "candidate_created_on": b.arrival_business_date,
                    "overdue": (today - b.arrival_business_date).days >= 1
                    if b.arrival_business_date
                    else None,
                    "stock_balance": b.balance_num,
                    "available_quantity": available,
                    "default_quantity": available if len(options) == 1 else None,
                    "can_approve": not blocked,
                    "blocked_reasons": blocked,
                    "source_observed_at": pub.source_observed_at,
                }
                # Do not include date-dependent overdue in a source concurrency token.
                token = {k: v for k, v in raw.items() if k not in ("overdue", "store_name")}
                token["listing_hash"] = listing.business_hash if listing else None
                raw["candidate_version"] = fingerprint(token)
                result.append(Candidate.model_validate(raw))
        return result

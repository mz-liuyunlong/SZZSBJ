"""SQL-scoped warehouse reads; current balances never replace approval snapshots."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import String, cast, func, or_, select

from app.modules.pmc_domestic.inbound_models import DomesticBoardPublication as Pub
from app.modules.pmc_domestic.inbound_models import DomesticInboundBoard as Board
from app.modules.pmc_domestic.packing_models import PackingOrder
from app.modules.pmc_domestic.warehouse_models import (
    PackingBoxLine,
    PackingBoxSet,
    PackingVarianceCase,
    PackingWarehouseNote,
)
from app.modules.sku_detail.models import LingxingSkuIdentity as Identity
from app.modules.sku_detail.models import LingxingSkuProductInfoCurrent as Product


class WarehouseRepository:
    def __init__(self, session):
        self.session = session

    def query(self, q, accounts, status=True):
        stmt = (
            select(PackingOrder)
            .outerjoin(PackingBoxSet, PackingBoxSet.order_id == PackingOrder.id)
            .where(
                PackingOrder.source_account_ref.in_(accounts),
                PackingOrder.warehouse_id == "16168",
                PackingOrder.status == "approved",
            )
        )
        if q.exception == "overpack":
            stmt = stmt.join(
                PackingVarianceCase, PackingVarianceCase.order_id == PackingOrder.id
            ).where(PackingVarianceCase.kind == "over", PackingVarianceCase.state == "blocked")
        if q.store_id:
            stmt = stmt.where(PackingOrder.store_id == q.store_id)
        if q.keyword:
            word = q.keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = "%" + word + "%"
            stmt = stmt.where(
                or_(
                    *[
                        column.ilike(pattern, escape="\\")
                        for column in (
                            PackingOrder.pk,
                            PackingOrder.sku,
                            PackingOrder.inbound_order_sn,
                            PackingOrder.item_id,
                            cast(PackingOrder.snapshot_json["purchase_order_sns"], String),
                            cast(PackingOrder.snapshot_json["msku"], String),
                        )
                    ]
                )
            )
        for value, upper in ((q.approved_from, False), (q.approved_to, True)):
            if value:
                boundary = datetime.combine(
                    value + timedelta(days=1) if upper else value,
                    time.min,
                    ZoneInfo("Asia/Shanghai"),
                ).astimezone(UTC)
                stmt = stmt.where(
                    PackingOrder.created_at < boundary
                    if upper
                    else PackingOrder.created_at >= boundary
                )
        if status and q.status != "all":
            stmt = stmt.where(
                PackingBoxSet.completed_at.is_not(None)
                if q.status == "packed"
                else PackingBoxSet.completed_at.is_(None)
            )
        return stmt

    def list(self, q, accounts):
        stmt = self.query(q, accounts)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        ordering = (
            (PackingOrder.created_at.asc(), PackingOrder.id.asc())
            if q.sort == "approved_asc"
            else (PackingOrder.created_at.desc(), PackingOrder.id.desc())
        )
        rows = list(
            self.session.scalars(
                stmt.order_by(*ordering).offset((q.page - 1) * q.page_size).limit(q.page_size)
            )
        )
        return rows, total

    def order(self, ident, accounts, lock=False):
        stmt = select(PackingOrder).where(
            PackingOrder.id == ident,
            PackingOrder.source_account_ref.in_(accounts),
            PackingOrder.warehouse_id == "16168",
        )
        return self.session.scalar(stmt.with_for_update() if lock else stmt)

    def context(self, orders):
        ids = [r.id for r in orders]
        sets = {
            r.order_id: r
            for r in self.session.scalars(
                select(PackingBoxSet).where(PackingBoxSet.order_id.in_(ids))
            )
        }
        lines = {r.id: [] for r in sets.values()}
        for row in self.session.scalars(
            select(PackingBoxLine)
            .where(PackingBoxLine.box_set_id.in_(list(lines)))
            .order_by(PackingBoxLine.line_no)
        ):
            lines[row.box_set_id].append(row)
        notes = {
            r.order_id: r
            for r in self.session.scalars(
                select(PackingWarehouseNote).where(PackingWarehouseNote.order_id.in_(ids))
            )
        }
        accounts = {r.source_account_ref for r in orders}
        skus = {r.sku for r in orders}
        products = {}
        for row in self.session.scalars(
            select(Product)
            .join(Identity, Identity.id == Product.identity_id)
            .where(
                Product.source_account_ref.in_(accounts),
                Product.lingxing_sku_code.in_(skus),
                Identity.is_active.is_(True),
                Identity.source_account_ref == Product.source_account_ref,
                Product.provider == "lingxing",
            )
        ):
            products.setdefault((row.source_account_ref, row.lingxing_sku_code), []).append(row)
        balances = {}
        for board, pub in self.session.execute(
            select(Board, Pub)
            .join(Pub, Pub.id == Board.publication_id)
            .where(
                Pub.is_current.is_(True),
                Board.source_account_ref.in_(accounts),
                Board.source_warehouse_id == "16168",
                Board.id.in_({r.source_board_id for r in orders}),
            )
        ):
            balances[(board.source_account_ref, board.id)] = (board, pub)
        return sets, lines, notes, products, balances

    def receipts(self, orders):
        """Only verified receipt links to an actually allocated source batch qualify."""
        from app.modules.pmc_domestic.models import DwdDomesticReceiptBatch as Receipt
        from app.modules.pmc_domestic.models import DwdDomesticReceiptBatchLink as Link

        result = {order.id: ([], []) for order in orders}
        if not orders:
            return result
        sources = {
            (r.publication_id, r.id): r
            for r in self.session.scalars(
                select(Board).where(
                    Board.publication_id.in_({o.source_publication_id for o in orders}),
                    Board.id.in_({o.source_board_id for o in orders}),
                )
            )
        }
        links = list(
            self.session.execute(
                select(Receipt, Link)
                .join(Link, Link.receipt_batch_id == Receipt.id)
                .where(
                    Receipt.source_account_ref.in_({o.source_account_ref for o in orders}),
                    Link.source_account_ref == Receipt.source_account_ref,
                    Receipt.source_warehouse_id == "16168",
                    Receipt.sku.in_({o.sku for o in orders}),
                    Link.mapping_status == "matched",
                    Link.batch_order_sn.in_({o.inbound_order_sn for o in orders}),
                )
            )
        )
        for order in orders:
            source = sources.get((order.source_publication_id, order.source_board_id))
            batches = set(source.payload_json.get("batch_nos", [])) if source else set()
            matches = [
                r
                for r, link in links
                if r.source_account_ref == order.source_account_ref
                and r.sku == order.sku
                and link.batch_order_sn == order.inbound_order_sn
                and link.batch_no in batches
            ]
            result[order.id] = (
                sorted({r.received_business_date for r in matches if r.received_business_date}),
                sorted({r.receipt_order_sn for r in matches}),
            )
        return result

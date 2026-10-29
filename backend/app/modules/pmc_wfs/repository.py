"""Scoped SQL queries; current domestic facts remain owned by the domestic module."""

from sqlalchemy import String, cast, func, or_, select, text

from app.modules.pmc_domestic.packing_models import PackingOrder
from app.modules.pmc_domestic.warehouse_models import PackingBoxSet
from app.modules.pmc_wfs.models import WfsBoxAllocation, WfsDraft, WfsDraftItem, WfsEvent


class WfsRepository:
    def __init__(self, session):
        self.session = session

    def query(self, q, accounts, stores, completed=True):
        stmt = (
            select(PackingOrder)
            .outerjoin(PackingBoxSet, PackingBoxSet.order_id == PackingOrder.id)
            .where(
                PackingOrder.status == "approved",
                PackingOrder.warehouse_id == "16168",
                PackingOrder.source_account_ref.in_(accounts),
            )
        )
        if stores is not None:
            stmt = stmt.where(PackingOrder.store_id.in_(stores))
        if completed:
            stmt = stmt.where(PackingBoxSet.completed_at.is_not(None))
        if q.store_id:
            stmt = stmt.where(PackingOrder.store_id == q.store_id)
        if q.only_test:
            stmt = stmt.where(PackingOrder.business_test.is_(True))
        if q.keyword:
            word = q.keyword.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{word}%"
            stmt = stmt.where(
                or_(
                    *[
                        c.ilike(pattern, escape="\\")
                        for c in (
                            PackingOrder.pk,
                            PackingOrder.sku,
                            PackingOrder.item_id,
                            cast(PackingOrder.snapshot_json["gtin"], String),
                            cast(PackingOrder.snapshot_json["msku"], String),
                        )
                    ]
                )
            )
        return stmt.order_by(PackingOrder.created_at.desc(), PackingOrder.id)

    def count(self, stmt):
        return self.session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))

    def occupied(self, order_ids):
        return set(
            self.session.scalars(
                select(WfsBoxAllocation.box_line_id).where(WfsBoxAllocation.order_id.in_(order_ids))
            )
        )

    def prior(self, account, key):
        return self.session.scalar(
            select(WfsEvent).where(
                WfsEvent.source_account_ref == account, WfsEvent.idempotency_key == key
            )
        )

    def draft(self, ident, accounts, stores):
        stmt = select(WfsDraft).where(
            WfsDraft.id == ident, WfsDraft.source_account_ref.in_(accounts)
        )
        if stores is not None:
            stmt = stmt.where(WfsDraft.store_id.in_(stores))
        return self.session.scalar(stmt)


def assert_not_occupied(session, order_id):
    """All domestic mutation entry points must use this under the shared PK lock."""
    from app.modules.pmc_domestic.packing_service import conflict

    # Domestic-only installations cannot contain a WFS hold before this module's
    # additive schema is installed. Do not require a WFS rollout for unrelated PK edits.
    if not session.scalar(text("SELECT to_regclass('ops_pmc_wfs_box_allocations') IS NOT NULL")):
        return
    if session.scalar(
        select(WfsBoxAllocation.id).where(WfsBoxAllocation.order_id == order_id).limit(1)
    ):
        conflict("WFS_BOXES_OCCUPIED")


WFS_TABLES = (
    WfsDraft.__table__,
    WfsDraftItem.__table__,
    WfsBoxAllocation.__table__,
    WfsEvent.__table__,
)

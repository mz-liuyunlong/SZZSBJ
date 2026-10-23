"""Current version queries only: no source call or RAW/ODS reads."""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import Text, and_, cast, func, or_, select
from sqlalchemy.orm import Session

from app.modules.data_pages.models import LingxingStoreDimension
from app.modules.pmc_domestic.filter_sources import current_product_owners
from app.modules.pmc_domestic.inbound_models import DomesticBoardPublication as Pub
from app.modules.pmc_domestic.inbound_models import DomesticInboundBoard as Row
from app.modules.pmc_domestic.inbound_schemas import InboundFilter, InboundQuery


class InboundRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._publications: dict[tuple[str, ...], list[Pub]] = {}

    def publications(self, accounts: frozenset[str], warehouses: list[str]) -> list[Pub]:
        key = tuple(sorted(accounts))
        if key in self._publications:
            pubs = self._publications[key]
            return [p for p in pubs if not warehouses or p.source_warehouse_id in warehouses]
        query = select(Pub).where(
            Pub.source_account_ref.in_(sorted(accounts)),
            Pub.is_current.is_(True),
            Pub.status == "published",
        )
        self._publications[key] = list(self.session.scalars(query))
        return self.publications(accounts, warehouses)

    def statement(self, query: InboundFilter, accounts: frozenset[str]):
        stmt = (
            select(Row)
            .join(
                Pub,
                and_(
                    Row.publication_id == Pub.id,
                    Row.source_account_ref == Pub.source_account_ref,
                    Row.source_warehouse_id == Pub.source_warehouse_id,
                ),
            )
            .where(
                Row.source_account_ref.in_(sorted(accounts)),
                Pub.id.in_([p.id for p in self.publications(accounts, query.warehouse_id)]),
                Pub.status == "published",
            )
        )
        for name, column in (
            ("warehouse_id", Row.source_warehouse_id),
            ("store_id", Row.store_id),
            ("sku", Row.sku),
            ("inbound_order_sn", Row.inbound_order_sn),
        ):
            if values := getattr(query, name):
                stmt = stmt.where(column.in_(values))
        if query.owner_uid:
            owners = current_product_owners(accounts)
            # EXISTS preserves the inbound grain and quantity sums when DIM rows multiply.
            stmt = stmt.where(
                select(owners.c.uid)
                .where(
                    owners.c.account == Row.source_account_ref,
                    owners.c.sku == Row.sku,
                    owners.c.uid.in_(query.owner_uid),
                )
                .exists()
            )
        if query.purchase_order_sn:
            # Quote an entire JSON string token: PO1 must never match PO10.
            stmt = stmt.where(
                or_(
                    *[
                        cast(Row.payload_json["purchase_order_sns"], Text).contains(
                            json.dumps(v, ensure_ascii=False),
                            autoescape=True,
                        )
                        for v in query.purchase_order_sn
                    ]
                )
            )
        if query.inbound_from:
            stmt = stmt.where(Row.arrival_business_date >= query.inbound_from)
        if query.inbound_to:
            stmt = stmt.where(Row.arrival_business_date <= query.inbound_to)
        if query.inventory_status:
            stmt = stmt.where(
                Row.balance_num.is_(None)
                if query.inventory_status == "unknown"
                else Row.balance_num.is_not(None)
            )
        if query.search and (term := query.search.strip()):
            stmt = stmt.where(
                or_(
                    *[
                        c.contains(term, autoescape=True)
                        for c in (
                            Row.inbound_order_sn,
                            Row.sku,
                            cast(Row.payload_json["purchase_order_sns"], Text),
                            cast(Row.payload_json["batch_nos"], Text),
                        )
                    ]
                )
            )
        return stmt

    def filter_options(self, accounts: frozenset[str], warehouses: list[str]):
        # Options cover every current visible row, independent of paging and selected filters.
        visible = self.statement(InboundFilter(warehouse_id=warehouses), accounts).subquery()
        store = LingxingStoreDimension
        name = func.nullif(func.trim(store.store_name), "")
        stores = self.session.execute(
            select(visible.c.store_id, func.count(func.distinct(name)), func.max(name))
            .select_from(visible)
            .outerjoin(
                store,
                and_(
                    store.source_account_ref == visible.c.source_account_ref,
                    store.store_id == visible.c.store_id,
                ),
            )
            .where(visible.c.store_id.is_not(None), func.trim(visible.c.store_id) != "")
            .group_by(visible.c.store_id)
            .order_by(visible.c.store_id)
        ).all()
        owners = current_product_owners(accounts)
        people = self.session.execute(
            select(owners.c.uid, func.count(func.distinct(owners.c.name)), func.max(owners.c.name))
            .select_from(visible)
            .join(
                owners,
                and_(
                    owners.c.account == visible.c.source_account_ref,
                    owners.c.sku == visible.c.sku,
                ),
            )
            .group_by(owners.c.uid)
            .order_by(owners.c.uid)
        ).all()

        def options(rows):
            return [
                {"value": value, "label": name if count == 1 and name else value}
                for value, count, name in rows
            ]

        return {"stores": options(stores), "owners": options(people)}

    def list(self, query: InboundQuery, accounts: frozenset[str]) -> tuple[list[Row], int]:
        stmt = self.statement(query, accounts)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        order = {
            "inbound_date_desc": Row.arrival_business_date.desc().nulls_last(),
            "inbound_date_asc": Row.arrival_business_date.asc().nulls_last(),
            "balance_desc": Row.balance_num.desc().nulls_last(),
        }[query.sort]
        rows = self.session.scalars(
            stmt.order_by(order, Row.id)
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        return list(rows), int(total)

    def all(self, query: InboundFilter, accounts: frozenset[str]) -> list[Row]:
        return list(self.session.scalars(self.statement(query, accounts)))

    def detail(self, identity: UUID, accounts: frozenset[str]) -> Row | None:
        return self.session.scalar(
            self.statement(InboundFilter(), accounts).where(Row.id == identity)
        )

"""M1 board reads creation facts only; no Lingxing fulfillment projection."""

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.modules.data_pages.models import LingxingStoreDimension as Store
from app.modules.pmc_domestic.packing_models import PackingOrder
from app.modules.pmc_domestic.packing_service import missing
from app.modules.pmc_wfs.creation_models import WfsCreation, WfsCreationTicket
from app.modules.pmc_wfs.repository import require_creation_schema
from app.modules.pmc_wfs.shipment_board_schemas import (
    ShipmentBoardDetail,
    ShipmentBoardFilter,
    ShipmentBoardList,
    ShipmentBoardOptions,
    ShipmentBoardQuery,
    ShipmentBoardRow,
    ShipmentBoardSummary,
    StoreOption,
)


def row_id(ticket_id, shipment_id: str) -> str:
    return f"{ticket_id}:{shipment_id}"


class ShipmentBoardService:
    def __init__(self, session, accounts, stores):
        self.session = session
        self.accounts = accounts
        self.stores = stores

    def _operations_stmt(self):
        stmt = select(WfsCreation).where(WfsCreation.source_account_ref.in_(self.accounts))
        if self.stores is not None:
            stmt = stmt.where(WfsCreation.store_id.in_(self.stores))
        return stmt.order_by(WfsCreation.created_at.desc(), WfsCreation.id)

    def _order_map(self, order_ids):
        if not order_ids:
            return {}
        rows = self.session.scalars(select(PackingOrder).where(PackingOrder.id.in_(order_ids)))
        return {row.id: row for row in rows}

    def _expand(self) -> list[ShipmentBoardRow]:
        require_creation_schema(self.session)
        ops = list(self.session.scalars(self._operations_stmt()))
        if not ops:
            return []
        op_ids = [op.id for op in ops]
        tickets = list(
            self.session.scalars(
                select(WfsCreationTicket)
                .where(WfsCreationTicket.operation_id.in_(op_ids))
                .order_by(WfsCreationTicket.operation_id, WfsCreationTicket.number)
            )
        )
        by_op = {op.id: op for op in ops}
        order_ids = {op.order_id for op in ops}
        orders = self._order_map(order_ids)
        rows: list[ShipmentBoardRow] = []
        for ticket in tickets:
            labels = ticket.result.get("labels") or {}
            if not labels:
                continue
            op = by_op[ticket.operation_id]
            order = orders.get(op.order_id)
            snap_order = (op.snapshot.get("order") or {}) if isinstance(op.snapshot, dict) else {}
            pk = (order.pk if order else None) or snap_order.get("pk") or ""
            business_test = order.business_test if order else bool(snap_order.get("business_test"))
            for shipment_id, meta in labels.items():
                if not isinstance(shipment_id, str) or not shipment_id.strip():
                    continue
                state = meta.get("state", "PENDING") if isinstance(meta, dict) else "PENDING"
                if state not in {"PENDING", "READY", "FAILED"}:
                    state = "PENDING"
                rows.append(
                    ShipmentBoardRow(
                        id=row_id(ticket.id, shipment_id),
                        shipment_id=shipment_id,
                        operation_id=op.id,
                        ticket_id=ticket.id,
                        ticket_number=ticket.number,
                        order_id=op.order_id,
                        pk=pk,
                        store_id=op.store_id,
                        store_name=snap_order.get("store_name"),
                        sku=snap_order.get("sku"),
                        product_name=snap_order.get("product_name"),
                        item_id=snap_order.get("item_id"),
                        gtin=snap_order.get("gtin"),
                        msku=snap_order.get("msku"),
                        business_test=business_test,
                        its=bool(op.snapshot.get("its")) if isinstance(op.snapshot, dict) else False,
                        label_state=state,
                        creation_state=op.state,
                        ticket_state=ticket.state,
                        created_at=op.created_at,
                    )
                )
        return rows

    @staticmethod
    def _match_keyword(row: ShipmentBoardRow, field: str, word: str) -> bool:
        word = word.lower()
        targets = {
            "shipment": row.shipment_id,
            "pk": row.pk,
            "msku": row.msku,
            "sku": row.sku,
            "item": row.item_id,
            "gtin": row.gtin,
        }
        value = targets.get(field) or ""
        return word in (value or "").lower()

    def _filter(self, rows: list[ShipmentBoardRow], query: ShipmentBoardFilter):
        word = query.keyword.strip()
        return [
            row
            for row in rows
            if (not query.store_id or row.store_id == query.store_id)
            and (not query.only_test or row.business_test)
            and (not word or self._match_keyword(row, query.keyword_field, word))
        ]

    @staticmethod
    def _sort(rows: list[ShipmentBoardRow], query: ShipmentBoardQuery):
        reverse = query.sort_dir == "desc"
        return sorted(rows, key=lambda r: (r.created_at, r.shipment_id), reverse=reverse)

    def list(self, query: ShipmentBoardQuery) -> ShipmentBoardList:
        filtered = self._sort(self._filter(self._expand(), query), query)
        start = (query.page - 1) * query.page_size
        end = start + query.page_size
        asof = datetime.now(UTC)
        return ShipmentBoardList(
            items=filtered[start:end],
            total=len(filtered),
            data_asof=asof,
        )

    def summary(self, query: ShipmentBoardFilter) -> ShipmentBoardSummary:
        rows = self._filter(self._expand(), query)
        return ShipmentBoardSummary(
            total=len(rows),
            pending_lingxing_sync=len(rows),
            test=sum(r.business_test for r in rows),
        )

    def options(self) -> ShipmentBoardOptions:
        require_creation_schema(self.session)
        name = func.nullif(func.trim(Store.store_name), "")
        stmt = (
            select(Store.store_id, func.count(func.distinct(name)), func.max(name))
            .where(
                Store.source_account_ref.in_(self.accounts),
                func.trim(Store.store_id) != "",
            )
            .group_by(Store.store_id)
            .order_by(Store.store_id)
        )
        if self.stores is not None:
            stmt = stmt.where(Store.store_id.in_(self.stores))
        values = {
            store_id: (label if count == 1 and label else store_id)
            for store_id, count, label in self.session.execute(stmt).all()
        }
        for row in self._expand():
            values.setdefault(row.store_id, row.store_name or row.store_id)
        return ShipmentBoardOptions(
            stores=[StoreOption(value=k, label=v) for k, v in sorted(values.items())]
        )

    def detail(self, ident: str) -> ShipmentBoardDetail:
        if ":" not in ident:
            missing()
        ticket_part, shipment_id = ident.split(":", 1)
        try:
            from uuid import UUID

            ticket_id = UUID(ticket_part)
        except ValueError:
            missing()
        row = next(
            (r for r in self._expand() if r.ticket_id == ticket_id and r.shipment_id == shipment_id),
            None,
        )
        if row is None:
            missing()
        op = self.session.get(WfsCreation, row.operation_id)
        ticket = self.session.get(WfsCreationTicket, ticket_id)
        snapshot = op.snapshot if op and isinstance(op.snapshot, dict) else {}
        return ShipmentBoardDetail(
            **row.model_dump(),
            return_address=snapshot.get("return_address"),
            expected_delivery_at=snapshot.get("expected_delivery_at"),
            allocation=ticket.allocation if ticket else None,
        )

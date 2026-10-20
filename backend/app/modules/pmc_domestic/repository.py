"""Scoped domestic reads; existing DIM/DWD supply names and current ownership."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, SQLColumnExpression, and_, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from app.modules.data_pages.models import LingxingStoreDimension
from app.modules.pmc_domestic.filter_sources import current_product_owners
from app.modules.pmc_domestic.models import DwdDomesticReceiptBatch, DwdDomesticReceiptBatchLink
from app.modules.pmc_domestic.schemas import BatchFilterQuery, BatchListQuery

BatchRow = DwdDomesticReceiptBatch
LinkRow = DwdDomesticReceiptBatchLink


class PmcDomesticBatchRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _current_owners(self, accounts: frozenset[str]) -> Subquery:
        return current_product_owners(accounts)

    def filter_options(self, accounts: frozenset[str]) -> dict[str, list[dict[str, str]]]:
        if not accounts:
            return {"stores": [], "owners": []}
        store = LingxingStoreDimension
        store_name = func.nullif(func.trim(store.store_name), "")
        store_rows = self.session.execute(
            select(LinkRow.store_id, func.count(func.distinct(store_name)),
                   func.max(store_name))
            .join(BatchRow, and_(BatchRow.id == LinkRow.receipt_batch_id,
                                BatchRow.source_account_ref == LinkRow.source_account_ref))
            .outerjoin(store, and_(store.source_account_ref == LinkRow.source_account_ref,
                                  store.store_id == LinkRow.store_id))
            .where(BatchRow.source_account_ref.in_(sorted(accounts)),
                   LinkRow.store_id.is_not(None), func.trim(LinkRow.store_id) != "")
            .group_by(LinkRow.store_id).order_by(LinkRow.store_id)
        ).all()
        owners = self._current_owners(accounts)
        owner_rows = self.session.execute(
            select(owners.c.uid, func.count(func.distinct(owners.c.name)),
                   func.max(owners.c.name))
            .join(BatchRow, and_(BatchRow.source_account_ref == owners.c.account,
                                BatchRow.sku == owners.c.sku))
            .where(BatchRow.source_account_ref.in_(sorted(accounts)))
            .group_by(owners.c.uid).order_by(owners.c.uid)
        ).all()
        # Name conflicts across accounts/platforms must not pick an arbitrary display name.
        def option(value: str, count: int, name: str | None) -> dict[str, str]:
            return {"value": value, "label": name if count == 1 and name else value}

        return {"stores": [option(*row) for row in store_rows],
                "owners": [option(*row) for row in owner_rows]}

    def list_batches(
        self, query: BatchListQuery, accounts: frozenset[str]
    ) -> tuple[list[BatchRow], int]:
        if not accounts:
            return [], 0
        filtered = self._filtered(query, accounts)
        total = int(self.session.scalar(select(func.count()).select_from(filtered.subquery())) or 0)
        stmt = filtered.order_by(*self._order(query)).offset((query.page - 1) * query.page_size)
        rows = list(self.session.scalars(stmt.limit(query.page_size)))
        return rows, total

    def summary_rows(
        self, query: BatchFilterQuery, accounts: frozenset[str]
    ) -> list[BatchRow]:
        if not accounts:
            return []
        return list(self.session.scalars(self._filtered(query, accounts)))

    def get_batch(self, batch_id: UUID, accounts: frozenset[str]) -> BatchRow | None:
        if not accounts:
            return None
        return self.session.scalar(
            select(BatchRow).where(
                BatchRow.id == batch_id,
                BatchRow.source_account_ref.in_(sorted(accounts)),
            )
        )

    def links_for(
        self, batch_ids: Sequence[UUID], accounts: frozenset[str],
    ) -> dict[UUID, list[LinkRow]]:
        grouped: dict[UUID, list[LinkRow]] = {batch_id: [] for batch_id in batch_ids}
        if not batch_ids or not accounts:
            return grouped
        rows = self.session.scalars(
            select(LinkRow)
            .where(
                LinkRow.receipt_batch_id.in_(list(batch_ids)),
                LinkRow.source_account_ref.in_(sorted(accounts)),
            )
            .order_by(LinkRow.created_at, LinkRow.id)
        )
        for row in rows:
            grouped.setdefault(row.receipt_batch_id, []).append(row)
        return grouped

    def freshness(self, query: BatchFilterQuery, accounts: frozenset[str]) -> datetime | None:
        if not accounts:
            return None
        filtered = self._filtered(query, accounts).subquery()
        value = self.session.scalar(select(func.max(filtered.c.updated_at)))
        return value if isinstance(value, datetime) else None

    def _filtered(
        self, query: BatchFilterQuery, accounts: frozenset[str],
    ) -> Select[tuple[BatchRow]]:
        stmt = select(BatchRow).where(*self._clauses(query, accounts))
        return stmt

    def _clauses(
        self, query: BatchFilterQuery, accounts: frozenset[str],
    ) -> list[ColumnElement[bool]]:
        account_list = sorted(accounts)
        clauses: list[ColumnElement[bool]] = [BatchRow.source_account_ref.in_(account_list)]
        if query.warehouse_id:
            clauses.append(BatchRow.source_warehouse_id.in_(query.warehouse_id))
        if query.sku:
            clauses.append(BatchRow.sku.in_(query.sku))
        if query.purchase_order_sn:
            clauses.append(BatchRow.purchase_order_sn.in_(query.purchase_order_sn))
        if query.receipt_order_sn:
            clauses.append(BatchRow.receipt_order_sn.in_(query.receipt_order_sn))
        if query.received_from is not None:
            clauses.append(BatchRow.received_business_date >= query.received_from)
        if query.received_to is not None:
            clauses.append(BatchRow.received_business_date <= query.received_to)
        if query.store_id:
            clauses.append(BatchRow.id.in_(self._store_ids(query.store_id, account_list)))
        if query.owner_uid:
            owners = self._current_owners(accounts)
            clauses.append(select(owners.c.uid).where(
                owners.c.account == BatchRow.source_account_ref,
                owners.c.sku == BatchRow.sku,
                owners.c.uid.in_(query.owner_uid),
            ).exists())
        if query.mapping_status == "matched":
            clauses.append(BatchRow.id.in_(self._matched_ids(account_list)))
        elif query.mapping_status == "unresolved":
            clauses.append(BatchRow.id.not_in(self._matched_ids(account_list)))
        if query.search:
            term = f"%{query.search.strip()}%"
            link_hit = select(LinkRow.receipt_batch_id).where(
                LinkRow.source_account_ref.in_(account_list),
                or_(LinkRow.batch_no.ilike(term), LinkRow.batch_order_sn.ilike(term)),
            )
            clauses.append(
                or_(
                    BatchRow.sku.ilike(term),
                    BatchRow.receipt_order_sn.ilike(term),
                    BatchRow.purchase_order_sn.ilike(term),
                    BatchRow.id.in_(link_hit),
                )
            )
        return clauses

    def _matched_ids(self, accounts: list[str]) -> Select[tuple[UUID]]:
        return select(LinkRow.receipt_batch_id).where(
            LinkRow.source_account_ref.in_(accounts),
            LinkRow.mapping_status == "matched",
        )

    def _store_ids(self, store_ids: list[str], accounts: list[str]) -> Select[tuple[UUID]]:
        return select(LinkRow.receipt_batch_id).where(
            LinkRow.source_account_ref.in_(accounts),
            LinkRow.store_id.in_(store_ids),
        )

    def _order(self, query: BatchListQuery) -> tuple[SQLColumnExpression[Any], ...]:
        received = BatchRow.received_business_date
        if query.sort == "received_date_asc":
            return (received.asc().nulls_last(), BatchRow.receipt_order_sn, BatchRow.line_ordinal)
        if query.sort == "qty_desc":
            return (
                BatchRow.received_qty.desc().nulls_last(),
                received.desc().nulls_last(),
                BatchRow.line_ordinal,
            )
        return (received.desc().nulls_last(), BatchRow.receipt_order_sn, BatchRow.line_ordinal)

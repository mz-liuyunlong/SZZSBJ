"""Read-only inbound behavior, with parent-level quantity deduplication."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.pmc_domestic.board_item_ids import attach_board_item_ids
from app.modules.pmc_domestic.draft_numbers import attach_draft_numbers
from app.modules.pmc_domestic.filter_sources import OWNER_OBJECTS
from app.modules.pmc_domestic.inbound_builder import with_request_days
from app.modules.pmc_domestic.inbound_repository import InboundRepository
from app.modules.pmc_domestic.inbound_schemas import (
    InboundFilter,
    InboundList,
    InboundMeta,
    InboundOptions,
    InboundOptionsQuery,
    InboundQuery,
    InboundRow,
    InboundSummary,
    InboundTrace,
)


class InboundReadService:
    def __init__(self, session: Session, now: datetime | None = None) -> None:
        self.repository = InboundRepository(session)
        self.today = (now or datetime.now(UTC)).astimezone(ZoneInfo("Asia/Taipei")).date()

    def _row(self, row) -> InboundRow:
        data = with_request_days(row.payload_json, self.today)
        return InboundRow.model_validate(
            {**data, "id": row.id, "publication_id": row.publication_id}
        )

    def _meta(self, accounts: frozenset[str], query: InboundFilter, **values) -> InboundMeta:
        pubs = self.repository.publications(accounts, query.warehouse_id)
        start = max((p.coverage_start for p in pubs), default=None)
        end = min((p.coverage_end for p in pubs), default=None)
        if start and end and start >= end:
            start = end = None
        source_objects = ["mart_domestic_inbound_batch_board", "gov_domestic_board_publications"]
        if query.owner_uid:
            source_objects.extend(OWNER_OBJECTS)
        return InboundMeta(
            source_objects=source_objects,
            data_status="ready" if pubs else "not_published",
            as_of=self.today,
            freshness_at=min((p.source_observed_at for p in pubs), default=None),
            publication_ids=[p.id for p in pubs],
            # The common intersection must not pretend disjoint windows are covered.
            coverage_start=start,
            coverage_end=end,
            **values,
        )

    def filter_options(self, query: InboundOptionsQuery, accounts: frozenset[str]):
        values = self.repository.filter_options(accounts, query.warehouse_id)
        # These are capability declarations, never business classifications inferred from stock.
        reason = "尚未发布打包、发货及出库关联数据，业务状态暂不可筛选"
        statuses = [
            {"value": value, "label": label, "disabled": True, "reason": reason}
            for value, label in (
                ("in_stock", "在库"),
                ("approved", "待打包（领星打包单已建）"),
                ("packed", "已打包待发"),
                ("overdue", "超时未发"),
                ("shipped", "已发出"),
                ("other_out", "非发货出库"),
            )
        ]
        meta = self._meta(accounts, InboundFilter(warehouse_id=query.warehouse_id))
        meta.source_objects.extend(["dim_lingxing_stores", *OWNER_OBJECTS])
        return InboundOptions(**values, statuses=statuses), meta

    def list(self, query: InboundQuery, accounts: frozenset[str]):
        rows, total = self.repository.list(query, accounts)
        items = [self._row(r) for r in rows]
        attach_draft_numbers(self.repository.session, items, accounts)
        attach_board_item_ids(self.repository.session, items, accounts)
        return InboundList(items=items, total=total), self._meta(
            accounts,
            query,
            page=query.page,
            page_size=query.page_size,
            total=total,
        )

    def summary(self, query: InboundFilter, accounts: frozenset[str]):
        rows = self.repository.all(query, accounts)
        parents = {}
        stocks = {}
        for row in rows:
            p = row.payload_json
            parents[
                (row.source_account_ref, row.source_warehouse_id, row.inbound_order_sn, row.sku)
            ] = p.get("parent_inbound_qty")
            for b in p["batch_details"]:
                stocks[
                    (
                        row.source_account_ref,
                        row.source_warehouse_id,
                        b["batch_no"],
                        row.sku,
                        row.store_id,
                    )
                ] = b["balance_num"]
        data = InboundSummary(
            board_row_count=len(rows),
            inbound_order_count=len(
                {(r.source_account_ref, r.source_warehouse_id, r.inbound_order_sn) for r in rows}
            ),
            sku_count=len({r.sku for r in rows}),
            balance_qty=sum(v for v in stocks.values() if v is not None),
            unknown_inventory_row_count=sum(r.balance_num is None for r in rows),
            total_inbound_qty=sum(v for v in parents.values() if v is not None),
            unknown_inbound_qty_count=sum(v is None for v in parents.values()),
            missing_arrival_date_count=sum(r.arrival_business_date is None for r in rows),
            as_of=self.today,
        )
        return data, self._meta(accounts, query)

    def detail(self, identity: UUID, accounts: frozenset[str]):
        row = self.repository.detail(identity, accounts)
        if row is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        item = self._row(row)
        attach_draft_numbers(self.repository.session, [item], accounts)
        attach_board_item_ids(self.repository.session, [item], accounts)
        return item, self._meta(
            accounts, InboundFilter(warehouse_id=[row.source_warehouse_id])
        )

    def trace(self, identity: UUID, accounts: frozenset[str]):
        row = self.repository.detail(identity, accounts)
        if row is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        batch = self._row(row)
        attach_draft_numbers(self.repository.session, [batch], accounts)
        attach_board_item_ids(self.repository.session, [batch], accounts)
        return InboundTrace(
            batch=batch, inbound_events=row.payload_json["inbound_events"]
        ), self._meta(
            accounts,
            InboundFilter(warehouse_id=[row.source_warehouse_id]),
        )

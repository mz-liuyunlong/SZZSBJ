"""Batch board read service. Arrival days use Asia/Taipei."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.pmc_domestic.models import DwdDomesticReceiptBatch, DwdDomesticReceiptBatchLink
from app.modules.pmc_domestic.repository import PmcDomesticBatchRepository
from app.modules.pmc_domestic.schemas import (
    BatchFilterQuery,
    BatchLinkRead,
    BatchListData,
    BatchListQuery,
    BatchRowRead,
    BatchSummaryData,
    BatchTraceData,
    DomesticFilterOptionsData,
    MappingStatus,
    OutboundTrace,
)

TAIPEI = ZoneInfo("Asia/Taipei")


class PmcDomesticBatchReadService:
    def __init__(self, session: Session, now: datetime | None = None) -> None:
        self.repository = PmcDomesticBatchRepository(session)
        self.now = now or datetime.now(UTC)
        self.today = self.now.astimezone(TAIPEI).date()

    def filter_options(self, accounts: frozenset[str]) -> DomesticFilterOptionsData:
        return DomesticFilterOptionsData.model_validate(self.repository.filter_options(accounts))

    def list_batches(
        self, query: BatchListQuery, accounts: frozenset[str]
    ) -> tuple[BatchListData, int, datetime | None]:
        rows, total = self.repository.list_batches(query, accounts)
        links = self.repository.links_for([row.id for row in rows], accounts)
        items = [self._row(row, links.get(row.id, [])) for row in rows]
        return (
            BatchListData(items=items, total=total),
            total,
            self.repository.freshness(query, accounts),
        )

    def summary(
        self, query: BatchFilterQuery, accounts: frozenset[str]
    ) -> tuple[BatchSummaryData, datetime | None]:
        rows = self.repository.summary_rows(query, accounts)
        links = self.repository.links_for([row.id for row in rows], accounts)
        matched = sum(1 for row in rows if _mapping_status(links.get(row.id, [])) == "matched")
        warehouses = {row.source_warehouse_id for row in rows if row.source_warehouse_id}
        received = sum(row.received_qty or 0 for row in rows)
        missing_dates = sum(1 for row in rows if row.received_business_date is None)
        data = BatchSummaryData(
            receipt_batch_count=len(rows),
            received_qty=received,
            warehouse_count=len(warehouses),
            matched_batch_count=matched,
            unresolved_batch_count=len(rows) - matched,
            missing_arrival_date_count=missing_dates,
            as_of=self.today,
        )
        return data, self.repository.freshness(query, accounts)

    def detail(
        self, batch_id: UUID, accounts: frozenset[str]
    ) -> tuple[BatchRowRead, datetime | None]:
        row = self._require(batch_id, accounts)
        links = self.repository.links_for([row.id], accounts).get(row.id, [])
        return self._row(row, links), row.updated_at

    def trace(
        self, batch_id: UUID, accounts: frozenset[str]
    ) -> tuple[BatchTraceData, datetime | None]:
        batch, freshness = self.detail(batch_id, accounts)
        return BatchTraceData(batch=batch, outbound=OutboundTrace()), freshness

    def _require(self, batch_id: UUID, accounts: frozenset[str]) -> DwdDomesticReceiptBatch:
        row = self.repository.get_batch(batch_id, accounts)
        if row is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        return row

    def _row(
        self, row: DwdDomesticReceiptBatch, links: list[DwdDomesticReceiptBatchLink]
    ) -> BatchRowRead:
        arrival_known = row.received_business_date is not None
        return BatchRowRead(
            id=row.id,
            source_account_ref=row.source_account_ref,
            receipt_order_sn=row.receipt_order_sn,
            line_ordinal=row.line_ordinal,
            purchase_order_sn=row.purchase_order_sn,
            source_warehouse_id=row.source_warehouse_id,
            sku=row.sku,
            received_qty=row.received_qty,
            receive_time=row.receive_time,
            received_business_date=row.received_business_date,
            days_in_warehouse=_days(row.received_business_date, self.today),
            arrival_date_status="known" if arrival_known else "unknown",
            mapping_status=_mapping_status(links),
            links=[_link(item) for item in links],
        )


def _days(received: date | None, today: date) -> int | None:
    if received is None:
        return None
    return (today - received).days


def _mapping_status(links: list[DwdDomesticReceiptBatchLink]) -> MappingStatus:
    if any(item.mapping_status == "matched" for item in links):
        return "matched"
    return "unresolved"


def _link(row: DwdDomesticReceiptBatchLink) -> BatchLinkRead:
    status: MappingStatus = "matched" if row.mapping_status == "matched" else "unresolved"
    return BatchLinkRead(
        id=row.id,
        batch_order_sn=row.batch_order_sn,
        batch_no=row.batch_no,
        store_id=row.store_id,
        mapped_qty=row.mapped_qty,
        mapping_status=status,
        mapping_method=row.mapping_method,
    )

"""Publish receipt ODS into ``dwd_domestic_receipt_batch`` (phase 1).

Reads only ODS rows from succeeded sync runs. Does not call Lingxing. Batch↔receipt
matching is out of scope: each new DWD row gets an ``unresolved`` link stub when none
exists yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.integration_sync.models import IntegrationSyncRun
from app.modules.pmc_domestic.dwd_builder import (
    DWD_BUILDER_VERSION,
    DwdBuildReport,
    ReceiptBatchRow,
    build_receipt_batches,
)
from app.modules.pmc_domestic.models import DwdDomesticReceiptBatch, DwdDomesticReceiptBatchLink
from app.modules.pmc_purchase.models import LingxingReceiptOrderItemOds, LingxingReceiptOrderOds


class PmcDomesticDwdPublishError(RuntimeError):
    """Stable error code; transaction rolled back."""


@dataclass(frozen=True, slots=True)
class DwdPublishResult:
    source_account_ref: str
    batches_inserted: int
    batches_updated: int
    batches_unchanged: int
    link_stubs_inserted: int
    report: DwdBuildReport
    builder_version: str = DWD_BUILDER_VERSION

    def as_message(self) -> str:
        return (
            f"batches={self.batches_inserted}/{self.batches_updated}/{self.batches_unchanged} "
            f"link_stubs={self.link_stubs_inserted} "
            f"receipts_kept={self.report.receipts_kept} lines_kept={self.report.lines_kept}"
        )


@dataclass
class _Counter:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0


class PmcDomesticDwdPublisher:
    def __init__(self, session: Session, now: datetime | None = None) -> None:
        self.session = session
        self.now = now or datetime.now(UTC)
        self.builder_version = DWD_BUILDER_VERSION

    def publish(self, *, source_account_ref: str) -> DwdPublishResult:
        account = source_account_ref.strip()
        if not account:
            raise PmcDomesticDwdPublishError("PMC_DOMESTIC_DWD_PUBLISH_ACCOUNT_INVALID")
        try:
            result = self._publish(account)
            self.session.commit()
        except PmcDomesticDwdPublishError:
            self.session.rollback()
            raise
        except Exception as error:
            self.session.rollback()
            raise PmcDomesticDwdPublishError("PMC_DOMESTIC_DWD_PUBLISH_FAILED") from error
        return result

    def _publish(self, account: str) -> DwdPublishResult:
        succeeded = select(IntegrationSyncRun.id).where(IntegrationSyncRun.status == "succeeded")

        def _scoped(model: Any) -> Any:
            return (
                select(model)
                .where(model.source_account_ref == account)
                .where(model.run_id.in_(succeeded))
            )

        built, report = build_receipt_batches(
            list(self.session.scalars(_scoped(LingxingReceiptOrderOds))),
            list(self.session.scalars(_scoped(LingxingReceiptOrderItemOds))),
        )
        counter = _Counter()
        link_stubs = 0
        existing = {
            (row.source_account_ref, row.receipt_order_sn, row.line_ordinal): row
            for row in self.session.scalars(
                select(DwdDomesticReceiptBatch).where(
                    DwdDomesticReceiptBatch.source_account_ref == account
                )
            )
        }
        for row in built:
            key = (row.source_account_ref, row.receipt_order_sn, row.line_ordinal)
            values = {
                "purchase_order_sn": row.purchase_order_sn,
                "source_warehouse_id": row.source_warehouse_id,
                "sku": row.sku,
                "received_qty": row.received_qty,
                "receive_time": row.receive_time,
                "received_business_date": row.received_business_date,
            }
            current = existing.get(key)
            if current is None:
                record = DwdDomesticReceiptBatch(
                    id=uuid4(),
                    source_account_ref=row.source_account_ref,
                    receipt_order_sn=row.receipt_order_sn,
                    line_ordinal=row.line_ordinal,
                    **values,
                )
                self._stamp_source(record, row)
                self.session.add(record)
                self.session.flush()
                existing[key] = record
                counter.inserted += 1
                link_stubs += self._ensure_unresolved_link(record)
                continue
            unchanged = current.source_ods_id == row.source.ods_id and all(
                getattr(current, field) == values[field] for field in values
            )
            if unchanged:
                counter.unchanged += 1
                continue
            for field, value in values.items():
                setattr(current, field, value)
            self._stamp_source(current, row)
            counter.updated += 1
        return DwdPublishResult(
            source_account_ref=account,
            batches_inserted=counter.inserted,
            batches_updated=counter.updated,
            batches_unchanged=counter.unchanged,
            link_stubs_inserted=link_stubs,
            report=report,
            builder_version=self.builder_version,
        )

    def _stamp_source(self, record: DwdDomesticReceiptBatch, row: ReceiptBatchRow) -> None:
        record.source_run_id = row.source.run_id
        record.source_ods_id = row.source.ods_id
        record.source_observed_at = row.source.observed_at
        record.provider_update_time = row.source.provider_update_time
        record.builder_version = self.builder_version
        record.updated_at = self.now

    def _ensure_unresolved_link(self, batch: DwdDomesticReceiptBatch) -> int:
        has_link = self.session.scalar(
            select(DwdDomesticReceiptBatchLink.id)
            .where(DwdDomesticReceiptBatchLink.receipt_batch_id == batch.id)
            .limit(1)
        )
        if has_link is not None:
            return 0
        self.session.add(
            DwdDomesticReceiptBatchLink(
                source_account_ref=batch.source_account_ref,
                receipt_batch_id=batch.id,
                mapping_status="unresolved",
            )
        )
        return 1

"""ODS → DWD publication for the PMC purchase board (Gate 3, PR G3-B part 2).

``dwd_builder`` decides *what* the current version of each document is; this module
writes it. Contract (rules v4 §7, gate3-plan G3-B):

* Only ODS rows from runs with ``status = 'succeeded'`` are considered.
* DWD keeps one row per business key. A row is inserted when new, rewritten when the
  chosen ODS version changed (``source_ods_id`` differs), and left untouched otherwise.
  Nothing is deleted: documents never disappear from the append-only ODS layer.
* ``dwd_purchase_plan.first_seen_pending_date`` (rules §2, S2 start) is set the first
  time the plan is published with status 2 and never overwritten afterwards.
* ``store_matched`` is the join against ``dim_lingxing_stores`` for the same account;
  unmatched ids keep their value (rules §1.1).
* Every write is traced: one ``gov_parse_jobs`` row per raw page (request ref) that
  contributed a chosen version, and ``gov_data_lineage`` rows for the key fields of
  each inserted/rewritten DWD row (same pattern as ``sku_detail.publisher``).

The service commits at the end of a successful ``publish`` and rolls back on any error.
It never calls a provider, never touches governance rows and never schedules itself.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.data_pages.models import LingxingStoreDimension
from app.modules.integration_sync.models import (
    ApiRawRequestRef,
    DataLineage,
    IntegrationSyncRun,
    ParseJob,
)
from app.modules.pmc_purchase.calculations import PLAN_STATUS_PENDING_PURCHASE
from app.modules.pmc_purchase.dwd_builder import (
    DWD_BUILDER_VERSION,
    DwdBuildReport,
    DwdOrderLineRow,
    DwdOrderRow,
    DwdPlanRow,
    SourceRef,
    build_dwd,
)
from app.modules.pmc_purchase.gate3_models import (
    DwdPurchaseOrder,
    DwdPurchaseOrderLineItem,
    DwdPurchasePlan,
)
from app.modules.pmc_purchase.models import (
    LingxingPurchaseOrderItemOds,
    LingxingPurchaseOrderOds,
    LingxingPurchasePlanOds,
    LingxingReceiptOrderItemOds,
    LingxingReceiptOrderOds,
)

PARSER_KEY = "pmc_purchase.dwd.v1"
TRANSFORM_KEY = "pmc_purchase.dwd.current"

PLAN_LINEAGE_FIELDS: dict[str, str] = {
    "plan_sn": "$.data[].plan_sn",
    "status": "$.data[].status",
    "create_date": "$.data[].create_time",
    "store_id": "$.data[].sid",
    "quantity_plan": "$.data[].quantity_plan",
    "remark_item_id": "$.data[].remark",
}
ORDER_LINEAGE_FIELDS: dict[str, str] = {
    "order_sn": "$.data[].order_sn",
    "status": "$.data[].status",
    "order_date": "$.data[].order_time",
    "quantity_total": "$.data[].quantity_total",
    "amount_total": "$.data[].amount_total",
}
LINE_LINEAGE_FIELDS: dict[str, str] = {
    "order_item_id": "$.data[].item_list[].id",
    "plan_sn": "$.data[].item_list[].plan_sn",
    "store_id": "$.data[].item_list[].sid",
    "quantity_allocated": "$.data[].item_list[].quantity_real",
    "amount_allocated": "$.data[].item_list[].amount",
}


class PmcPurchaseDwdPublishError(RuntimeError):
    """Raised with a stable code; the transaction has been rolled back."""


@dataclass(frozen=True, slots=True)
class DwdPublishResult:
    source_account_ref: str
    plans_inserted: int
    plans_updated: int
    plans_unchanged: int
    orders_inserted: int
    orders_updated: int
    orders_unchanged: int
    lines_inserted: int
    lines_updated: int
    lines_unchanged: int
    parse_jobs_written: int
    lineage_written: int
    stores_known: int
    report: DwdBuildReport
    builder_version: str = DWD_BUILDER_VERSION
    receipt_lines: int = 0
    notes: list[str] = field(default_factory=list)

    def as_message(self) -> str:
        return (
            f"plans={self.plans_inserted}/{self.plans_updated}/{self.plans_unchanged} "
            f"orders={self.orders_inserted}/{self.orders_updated}/{self.orders_unchanged} "
            f"lines={self.lines_inserted}/{self.lines_updated}/{self.lines_unchanged} "
            f"parse_jobs={self.parse_jobs_written} lineage={self.lineage_written} "
            f"stores_known={self.stores_known} receipt_lines={self.receipt_lines} "
            f"(inserted/updated/unchanged)"
        )


@dataclass
class _Counter:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0


class PmcPurchaseDwdPublisher:
    """Publish the current document versions from ODS into the three DWD tables."""

    def __init__(
        self,
        session: Session,
        *,
        builder_version: str = DWD_BUILDER_VERSION,
        now: datetime | None = None,
    ) -> None:
        self.session = session
        self.builder_version = builder_version
        self.now = now or datetime.now(UTC)
        self._blob_cache: dict[UUID, UUID] = {}

    # --- public --------------------------------------------------------------------------

    def publish(self, *, source_account_ref: str) -> DwdPublishResult:
        if not source_account_ref or source_account_ref != source_account_ref.strip():
            raise PmcPurchaseDwdPublishError("PMC_PURCHASE_DWD_SOURCE_ACCOUNT_REF_INVALID")
        try:
            result = self._publish(source_account_ref)
            self.session.commit()
        except PmcPurchaseDwdPublishError:
            self.session.rollback()
            raise
        except Exception as error:  # pragma: no cover - defensive
            self.session.rollback()
            raise PmcPurchaseDwdPublishError("PMC_PURCHASE_DWD_PUBLISH_FAILED") from error
        return result

    # --- internals -----------------------------------------------------------------------

    def _publish(self, account: str) -> DwdPublishResult:
        succeeded_runs = select(IntegrationSyncRun.id).where(
            IntegrationSyncRun.status == "succeeded"
        )

        def _scoped(model: Any) -> Any:
            return (
                select(model)
                .where(model.source_account_ref == account)
                .where(model.run_id.in_(succeeded_runs))
            )

        built = build_dwd(
            ods_plans=list(self.session.scalars(_scoped(LingxingPurchasePlanOds))),
            ods_orders=list(self.session.scalars(_scoped(LingxingPurchaseOrderOds))),
            ods_items=list(self.session.scalars(_scoped(LingxingPurchaseOrderItemOds))),
            ods_receipts=list(self.session.scalars(_scoped(LingxingReceiptOrderOds))),
            ods_receipt_items=list(self.session.scalars(_scoped(LingxingReceiptOrderItemOds))),
        )
        stores = set(
            self.session.scalars(
                select(LingxingStoreDimension.store_id).where(
                    LingxingStoreDimension.source_account_ref == account
                )
            )
        )

        lineage: list[DataLineage] = []
        touched_sources: dict[UUID, _Counter] = {}
        today = self.now.date()

        plans = self._upsert_plans(built.plans, stores, today, lineage, touched_sources)
        orders = self._upsert_orders(built.orders, lineage, touched_sources)
        lines = self._upsert_lines(built.lines, stores, lineage, touched_sources)

        parse_jobs = self._record_parse_jobs(touched_sources)
        if lineage:
            self.session.add_all(lineage)
            self.session.flush()

        return DwdPublishResult(
            source_account_ref=account,
            plans_inserted=plans.inserted,
            plans_updated=plans.updated,
            plans_unchanged=plans.unchanged,
            orders_inserted=orders.inserted,
            orders_updated=orders.updated,
            orders_unchanged=orders.unchanged,
            lines_inserted=lines.inserted,
            lines_updated=lines.updated,
            lines_unchanged=lines.unchanged,
            parse_jobs_written=parse_jobs,
            lineage_written=len(lineage),
            stores_known=len(stores),
            report=built.report,
            builder_version=self.builder_version,
            receipt_lines=len(built.receipt_lines),
        )

    # --- upserts -----------------------------------------------------------------------------

    def _upsert_plans(
        self,
        rows: Sequence[DwdPlanRow],
        stores: set[str],
        today: date,
        lineage: list[DataLineage],
        touched: dict[UUID, _Counter],
    ) -> _Counter:
        counter = _Counter()
        existing = {
            r.plan_sn: r
            for r in self.session.scalars(
                select(DwdPurchasePlan).where(
                    DwdPurchasePlan.source_account_ref.in_({r.source_account_ref for r in rows})
                )
            )
        }
        for row in rows:
            values: dict[str, Any] = {
                "plan_sn": row.plan_sn,
                "status": row.status,
                "create_date": row.create_date,
                "expect_arrive_date": row.expect_arrive_date,
                "store_id": row.store_id,
                "store_attributed": row.store_attributed,
                "store_matched": row.store_id is not None and row.store_id in stores,
                "sku": row.sku,
                "product_name": row.product_name,
                "quantity_plan": row.quantity_plan,
                "remark": row.remark,
                "remark_item_id": row.remark_item_id,
            }
            current = existing.get(row.plan_sn)
            pending_now = row.status == PLAN_STATUS_PENDING_PURCHASE
            if current is None:
                record = DwdPurchasePlan(
                    id=uuid4(),
                    source_account_ref=row.source_account_ref,
                    first_seen_pending_date=today if pending_now else None,
                    **values,
                )
                self._stamp_source(record, row.source)
                self.session.add(record)
                self._bump(touched, row.source, inserted=True)
                counter.inserted += 1
                lineage.extend(
                    self._lineage(record.id, "dwd_purchase_plan", PLAN_LINEAGE_FIELDS, row.source)
                )
                continue
            if current.source_ods_id == row.source.ods_id:
                counter.unchanged += 1
                continue
            for key, value in values.items():
                setattr(current, key, value)
            if pending_now and current.first_seen_pending_date is None:
                current.first_seen_pending_date = today
            self._stamp_source(current, row.source)
            self._bump(touched, row.source, inserted=False)
            counter.updated += 1
            lineage.extend(
                self._lineage(current.id, "dwd_purchase_plan", PLAN_LINEAGE_FIELDS, row.source)
            )
        self.session.flush()
        return counter

    def _upsert_orders(
        self,
        rows: Sequence[DwdOrderRow],
        lineage: list[DataLineage],
        touched: dict[UUID, _Counter],
    ) -> _Counter:
        counter = _Counter()
        existing = {
            r.order_sn: r
            for r in self.session.scalars(
                select(DwdPurchaseOrder).where(
                    DwdPurchaseOrder.source_account_ref.in_({r.source_account_ref for r in rows})
                )
            )
        }
        for row in rows:
            values: dict[str, Any] = {
                "order_sn": row.order_sn,
                "status": row.status,
                "order_date": row.order_date,
                "create_date": row.create_date,
                "quantity_total": row.quantity_total,
                "quantity_receive": row.quantity_receive,
                "quantity_real": row.quantity_real,
                "amount_total": row.amount_total,
                "currency_code": row.currency_code,
                "purchase_rate": row.purchase_rate,
                "shipping_price": row.shipping_price,
                "other_fee": row.other_fee,
                "line_count": row.line_count,
            }
            current = existing.get(row.order_sn)
            if current is None:
                record = DwdPurchaseOrder(
                    id=uuid4(), source_account_ref=row.source_account_ref, **values
                )
                self._stamp_source(record, row.source)
                self.session.add(record)
                self._bump(touched, row.source, inserted=True)
                counter.inserted += 1
                lineage.extend(
                    self._lineage(record.id, "dwd_purchase_order", ORDER_LINEAGE_FIELDS, row.source)
                )
                continue
            if current.source_ods_id == row.source.ods_id and current.line_count == row.line_count:
                counter.unchanged += 1
                continue
            for key, value in values.items():
                setattr(current, key, value)
            self._stamp_source(current, row.source)
            self._bump(touched, row.source, inserted=False)
            counter.updated += 1
            lineage.extend(
                self._lineage(current.id, "dwd_purchase_order", ORDER_LINEAGE_FIELDS, row.source)
            )
        self.session.flush()
        return counter

    def _upsert_lines(
        self,
        rows: Sequence[DwdOrderLineRow],
        stores: set[str],
        lineage: list[DataLineage],
        touched: dict[UUID, _Counter],
    ) -> _Counter:
        counter = _Counter()
        existing = {
            (r.order_sn, r.order_item_id, r.plan_key): r
            for r in self.session.scalars(
                select(DwdPurchaseOrderLineItem).where(
                    DwdPurchaseOrderLineItem.source_account_ref.in_(
                        {r.source_account_ref for r in rows}
                    )
                )
            )
        }
        for row in rows:
            plan_key = row.plan_sn or ""
            values: dict[str, Any] = {
                "order_sn": row.order_sn,
                "order_item_id": row.order_item_id,
                "line_ordinal": row.line_ordinal,
                "plan_sn": row.plan_sn,
                "plan_key": plan_key,
                "plan_count": row.plan_count,
                "allocation_ratio": row.allocation_ratio,
                "is_merged": row.is_merged,
                "plan_found": row.plan_found,
                "store_id": row.store_id,
                "store_attributed": row.store_attributed,
                "store_matched": row.store_id is not None and row.store_id in stores,
                "sku": row.sku,
                "product_name": row.product_name,
                "quantity_plan": row.quantity_plan,
                "quantity_real": row.quantity_real,
                "quantity_allocated": row.quantity_allocated,
                "amount_allocated": row.amount_allocated,
                "unit_price": row.unit_price,
                "expect_arrive_date": row.expect_arrive_date,
                "remark_item_id": row.remark_item_id,
            }
            current = existing.get((row.order_sn, row.order_item_id, plan_key))
            if current is None:
                record = DwdPurchaseOrderLineItem(
                    id=uuid4(), source_account_ref=row.source_account_ref, **values
                )
                self._stamp_source(record, row.source)
                self.session.add(record)
                self._bump(touched, row.source, inserted=True)
                counter.inserted += 1
                lineage.extend(
                    self._lineage(
                        record.id, "dwd_purchase_order_line_item", LINE_LINEAGE_FIELDS, row.source
                    )
                )
                continue
            # A line's allocation depends on the plans too, so compare the derived values
            # and not only the ODS version.
            unchanged = current.source_ods_id == row.source.ods_id and all(
                getattr(current, key) == value
                for key, value in values.items()
                if key not in ("allocation_ratio", "amount_allocated", "unit_price")
            )
            if unchanged:
                counter.unchanged += 1
                continue
            for key, value in values.items():
                setattr(current, key, value)
            self._stamp_source(current, row.source)
            self._bump(touched, row.source, inserted=False)
            counter.updated += 1
            lineage.extend(
                self._lineage(
                    current.id, "dwd_purchase_order_line_item", LINE_LINEAGE_FIELDS, row.source
                )
            )
        self.session.flush()
        return counter

    # --- governance ------------------------------------------------------------------------

    def _record_parse_jobs(self, touched: dict[UUID, _Counter]) -> int:
        written = 0
        for raw_request_ref_id, counter in touched.items():
            job = self.session.scalar(
                select(ParseJob).where(
                    ParseJob.raw_request_ref_id == raw_request_ref_id,
                    ParseJob.parser_key == PARSER_KEY,
                    ParseJob.parser_version == self.builder_version,
                )
            )
            records = counter.inserted + counter.updated
            if job is None:
                run_id = self.session.scalar(
                    select(ApiRawRequestRef.run_id).where(ApiRawRequestRef.id == raw_request_ref_id)
                )
                if run_id is None:
                    raise PmcPurchaseDwdPublishError("PMC_PURCHASE_DWD_RAW_REQUEST_REF_MISSING")
                self.session.add(
                    ParseJob(
                        id=uuid4(),
                        run_id=run_id,
                        raw_request_ref_id=raw_request_ref_id,
                        parser_key=PARSER_KEY,
                        parser_version=self.builder_version,
                        target_layer="DWD",
                        status="succeeded",
                        records_seen=records,
                        records_written=records,
                        records_rejected=0,
                        started_at=self.now,
                        finished_at=self.now,
                    )
                )
            else:
                job.records_seen += records
                job.records_written += records
                job.finished_at = self.now
            written += 1
        self.session.flush()
        return written

    def _lineage(
        self,
        record_id: UUID,
        target_table: str,
        fields: dict[str, str],
        source: SourceRef,
    ) -> list[DataLineage]:
        raw_blob_id = self._raw_blob_id(source.raw_request_ref_id)
        return [
            DataLineage(
                id=uuid4(),
                run_id=source.run_id,
                parse_job_id=None,
                raw_request_ref_id=source.raw_request_ref_id,
                raw_blob_id=raw_blob_id,
                source_path=path,
                target_table=target_table,
                target_record_id=str(record_id),
                target_field=field_name,
                transform_key=TRANSFORM_KEY,
                transform_version=self.builder_version,
            )
            for field_name, path in fields.items()
        ]

    def _raw_blob_id(self, raw_request_ref_id: UUID) -> UUID:
        cache = self._blob_cache
        if raw_request_ref_id not in cache:
            blob_id = self.session.scalar(
                select(ApiRawRequestRef.raw_blob_id).where(
                    ApiRawRequestRef.id == raw_request_ref_id
                )
            )
            if blob_id is None:
                raise PmcPurchaseDwdPublishError("PMC_PURCHASE_DWD_RAW_REQUEST_REF_MISSING")
            cache[raw_request_ref_id] = blob_id
        return cache[raw_request_ref_id]

    def _stamp_source(self, record: Any, source: SourceRef) -> None:
        record.source_run_id = source.run_id
        record.source_ods_id = source.ods_id
        record.source_observed_at = source.observed_at
        record.provider_update_time = source.provider_update_time
        record.builder_version = self.builder_version
        record.updated_at = self.now

    @staticmethod
    def _bump(touched: dict[UUID, _Counter], source: SourceRef, *, inserted: bool) -> None:
        counter = touched.setdefault(source.raw_request_ref_id, _Counter())
        if inserted:
            counter.inserted += 1
        else:
            counter.updated += 1


def summarize(results: Iterable[DwdPublishResult]) -> str:
    return "\n".join(r.as_message() for r in results)

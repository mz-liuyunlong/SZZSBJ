"""Persistence for normalized WFS settlement evidence."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.data_pages.models import WalmartListingDimension
from app.modules.integration_sync.models import (
    IntegrationSyncRun,
    IntegrationSyncRunWorkItem,
)
from app.modules.warehouse_wfs.fee_detection import SettlementFeeRow
from app.modules.warehouse_wfs.models import WalmartWfsFeeActualFact


class WfsSettlementPersistenceError(ValueError):
    """Safe persistence error."""


class WfsSettlementRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_rows(
        self,
        rows: tuple[SettlementFeeRow, ...],
        *,
        raw_request_ref_id: UUID,
        observed_at: datetime | None = None,
    ) -> int:
        """Upsert one canonical source line; RAW retains every response version."""

        now = observed_at or datetime.now(UTC)
        written = 0
        for row in rows:
            item_ids = self.session.scalars(
                select(WalmartListingDimension.item_id).where(
                    WalmartListingDimension.source_account_ref == row.source_account_ref,
                    WalmartListingDimension.store_id == row.store_id,
                    WalmartListingDimension.msku == row.msku,
                )
            ).all()
            if len(item_ids) != 1:
                raise WfsSettlementPersistenceError("WFS_SETTLEMENT_IDENTITY_UNRESOLVED")

            statement = insert(WalmartWfsFeeActualFact).values(
                id=uuid4(),
                source_account_ref=row.source_account_ref,
                business_date_la=date.fromisoformat(row.settlement_date),
                store_id=row.store_id,
                item_id=item_ids[0],
                msku=row.msku,
                source_line_ref=row.source_line_ref,
                platform_order_no=row.platform_order_no,
                sales_num=row.sales_num,
                platform_logistics_amount=row.platform_logistics_amount,
                settlement_date=date.fromisoformat(row.settlement_date),
                actual_fee_amount=abs(row.platform_logistics_amount),
                currency_code="USD",
                source_type="lingxing_profit_order",
                source_observed_at=now,
                source_raw_request_ref_id=raw_request_ref_id,
                created_at=now,
                updated_at=now,
            )
            statement = statement.on_conflict_do_update(
                index_elements=["source_account_ref", "source_line_ref"],
                set_={
                    "business_date_la": statement.excluded.business_date_la,
                    "item_id": statement.excluded.item_id,
                    "platform_order_no": statement.excluded.platform_order_no,
                    "sales_num": statement.excluded.sales_num,
                    "platform_logistics_amount": statement.excluded.platform_logistics_amount,
                    "settlement_date": statement.excluded.settlement_date,
                    "actual_fee_amount": statement.excluded.actual_fee_amount,
                    "source_observed_at": statement.excluded.source_observed_at,
                    "source_raw_request_ref_id": statement.excluded.source_raw_request_ref_id,
                    "updated_at": statement.excluded.updated_at,
                },
                where=and_(
                    WalmartWfsFeeActualFact.store_id == statement.excluded.store_id,
                    WalmartWfsFeeActualFact.item_id == statement.excluded.item_id,
                    WalmartWfsFeeActualFact.msku == statement.excluded.msku,
                ),
            ).returning(WalmartWfsFeeActualFact.id)
            persisted_id = self.session.execute(statement).scalar_one_or_none()
            if persisted_id is None:
                raise WfsSettlementPersistenceError("WFS_SETTLEMENT_SOURCE_IDENTITY_CONFLICT")
            written += 1
        return written

    def list_rows(
        self,
        *,
        source_account_ref: str,
        store_id: str,
        start_date: date,
        end_date: date,
    ) -> tuple[SettlementFeeRow, ...]:
        facts = self.session.scalars(
            select(WalmartWfsFeeActualFact).where(
                WalmartWfsFeeActualFact.source_account_ref == source_account_ref,
                WalmartWfsFeeActualFact.store_id == store_id,
                WalmartWfsFeeActualFact.settlement_date >= start_date,
                WalmartWfsFeeActualFact.settlement_date <= end_date,
            )
        ).all()
        rows = []
        for fact in facts:
            if (
                fact.platform_order_no is None
                or fact.sales_num is None
                or fact.platform_logistics_amount is None
                or fact.settlement_date is None
            ):
                raise WfsSettlementPersistenceError("WFS_SETTLEMENT_EVIDENCE_INCOMPLETE")
            rows.append(
                SettlementFeeRow(
                    source_account_ref=fact.source_account_ref,
                    store_id=fact.store_id,
                    msku=fact.msku,
                    platform_order_no=fact.platform_order_no,
                    sales_num=Decimal(fact.sales_num),
                    platform_logistics_amount=Decimal(fact.platform_logistics_amount),
                    settlement_date=fact.settlement_date.isoformat(),
                    source_line_ref=fact.source_line_ref,
                )
            )
        return tuple(rows)

    def has_completed_collection(
        self,
        *,
        source_account_ref: str,
        store_id: str,
        start_date: date,
        end_date: date,
    ) -> bool:
        """Require a successful store work item in a complete exact-window run."""

        run_id = self.session.scalar(
            select(IntegrationSyncRun.id)
            .join(
                IntegrationSyncRunWorkItem,
                IntegrationSyncRunWorkItem.run_id == IntegrationSyncRun.id,
            )
            .where(
                IntegrationSyncRun.provider == "lingxing",
                IntegrationSyncRun.interface_key == "wfsProfitOrder",
                IntegrationSyncRun.source_account_ref == source_account_ref,
                IntegrationSyncRun.status == "succeeded",
                IntegrationSyncRun.work_items_failed == 0,
                func.date(IntegrationSyncRun.window_start) == start_date,
                func.date(IntegrationSyncRun.window_end) == end_date,
                IntegrationSyncRunWorkItem.scope_key == store_id,
                IntegrationSyncRunWorkItem.status == "succeeded",
            )
            .limit(1)
        )
        return run_id is not None

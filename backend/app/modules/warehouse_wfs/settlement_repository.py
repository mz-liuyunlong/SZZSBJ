"""Persistence for normalized WFS settlement evidence."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.data_pages.models import WalmartListingDimension
from app.modules.warehouse_wfs.fee_detection import SettlementFeeRow
from app.modules.warehouse_wfs.models import (
    WalmartWfsFeeActualFact,
    WfsSettlementCollection,
)


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
        collection_id: UUID,
        observed_at: datetime | None = None,
    ) -> int:
        """Upsert one canonical source line; RAW retains every response version."""

        if not rows:
            return 0
        source_identities = {(row.source_account_ref, row.source_line_ref) for row in rows}
        if len(source_identities) != len(rows):
            raise WfsSettlementPersistenceError("WFS_SETTLEMENT_DUPLICATE_SOURCE_IDENTITY")
        now = observed_at or datetime.now(UTC)
        identity_keys = {(row.source_account_ref, row.store_id, row.msku) for row in rows}
        listing_rows = self.session.execute(
            select(
                WalmartListingDimension.source_account_ref,
                WalmartListingDimension.store_id,
                WalmartListingDimension.msku,
                WalmartListingDimension.item_id,
            ).where(
                tuple_(
                    WalmartListingDimension.source_account_ref,
                    WalmartListingDimension.store_id,
                    WalmartListingDimension.msku,
                ).in_(identity_keys)
            )
        ).all()
        item_ids_by_key: dict[tuple[str, str, str], list[str]] = {}
        for account_ref, store_id, msku, item_id in listing_rows:
            item_ids_by_key.setdefault((account_ref, store_id, msku), []).append(item_id)

        values: list[dict[str, object]] = []
        for row in rows:
            item_ids = item_ids_by_key.get(
                (row.source_account_ref, row.store_id, row.msku),
                [],
            )
            if len(item_ids) != 1:
                raise WfsSettlementPersistenceError("WFS_SETTLEMENT_IDENTITY_UNRESOLVED")

            values.append(
                {
                    "id": uuid4(),
                    "source_account_ref": row.source_account_ref,
                    "business_date_la": date.fromisoformat(row.settlement_date),
                    "store_id": row.store_id,
                    "item_id": item_ids[0],
                    "msku": row.msku,
                    "source_line_ref": row.source_line_ref,
                    "platform_order_no": row.platform_order_no,
                    "sales_num": row.sales_num,
                    "platform_logistics_amount": row.platform_logistics_amount,
                    "settlement_date": date.fromisoformat(row.settlement_date),
                    "actual_fee_amount": abs(row.platform_logistics_amount),
                    "currency_code": "USD",
                    "source_type": "lingxing_profit_order",
                    "source_observed_at": now,
                    "source_raw_request_ref_id": raw_request_ref_id,
                    "collection_id": collection_id,
                    "created_at": now,
                    "updated_at": now,
                }
            )

        statement = insert(WalmartWfsFeeActualFact).values(values)
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
                "collection_id": statement.excluded.collection_id,
                "updated_at": statement.excluded.updated_at,
            },
            where=and_(
                WalmartWfsFeeActualFact.store_id == statement.excluded.store_id,
                WalmartWfsFeeActualFact.item_id == statement.excluded.item_id,
                WalmartWfsFeeActualFact.msku == statement.excluded.msku,
            ),
        ).returning(WalmartWfsFeeActualFact.id)
        persisted_ids = self.session.execute(statement).scalars().all()
        if len(persisted_ids) != len(rows):
            raise WfsSettlementPersistenceError("WFS_SETTLEMENT_SOURCE_IDENTITY_CONFLICT")
        return len(persisted_ids)

    def list_rows(
        self,
        *,
        source_account_ref: str,
        store_id: str,
        start_date: date,
        end_date: date,
        collection_id: UUID | None = None,
    ) -> tuple[SettlementFeeRow, ...]:
        collection = (
            self.get_verified_collection(
                source_account_ref=source_account_ref,
                store_id=store_id,
                start_date=start_date,
                end_date=end_date,
            )
            if collection_id is None
            else self.session.get(WfsSettlementCollection, collection_id)
        )
        if (
            collection is None
            or collection.collection_status != "verified"
            or collection.source_account_ref != source_account_ref
            or collection.store_id != store_id
            or collection.window_start != start_date
            or collection.window_end != end_date
        ):
            raise WfsSettlementPersistenceError("WFS_COLLECTION_NOT_VERIFIED")
        facts = self.session.scalars(
            select(WalmartWfsFeeActualFact).where(
                WalmartWfsFeeActualFact.collection_id == collection.id,
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
                    fee_scope_status=collection.wfs_scope_status,
                )
            )
        if len(rows) != collection.verified_count:
            raise WfsSettlementPersistenceError("WFS_COLLECTION_FACT_COUNT_MISMATCH")
        return tuple(rows)

    def create_collection(
        self,
        *,
        run_id: UUID,
        source_account_ref: str,
        store_id: str,
        start_date: date,
        end_date: date,
        wfs_scope_status: str = "unverified",
    ) -> WfsSettlementCollection:
        if wfs_scope_status not in {"verified_wfs", "unverified"}:
            raise WfsSettlementPersistenceError("WFS_SETTLEMENT_SCOPE_INVALID")
        collection = WfsSettlementCollection(
            id=uuid4(),
            run_id=run_id,
            source_account_ref=source_account_ref,
            store_id=store_id,
            window_start=start_date,
            window_end=end_date,
            collection_status="running",
            wfs_scope_status=wfs_scope_status,
            expected_total=None,
            captured_count=0,
            accepted_count=0,
            business_excluded_count=0,
            invalid_count=0,
            missing_store_count=0,
            duplicate_count=0,
            missing_identity_count=0,
            verified_count=0,
            started_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        self.session.add(collection)
        self.session.flush()
        return collection

    def finalize_collection(
        self,
        collection: WfsSettlementCollection,
        *,
        expected_total: int,
        captured_count: int,
        accepted_count: int,
        business_excluded_count: int,
        invalid_count: int,
        missing_store_count: int,
        duplicate_count: int,
        missing_identity_count: int,
        latest_settlement_date: date | None,
    ) -> None:
        classified = (
            accepted_count
            + business_excluded_count
            + invalid_count
            + missing_store_count
            + duplicate_count
            + missing_identity_count
        )
        persisted = self.session.scalar(
            select(func.count())
            .select_from(WalmartWfsFeeActualFact)
            .where(WalmartWfsFeeActualFact.collection_id == collection.id)
        )
        collection.expected_total = expected_total
        collection.captured_count = captured_count
        collection.accepted_count = accepted_count
        collection.business_excluded_count = business_excluded_count
        collection.invalid_count = invalid_count
        collection.missing_store_count = missing_store_count
        collection.duplicate_count = duplicate_count
        collection.missing_identity_count = missing_identity_count
        collection.verified_count = int(persisted or 0)
        collection.latest_settlement_date = latest_settlement_date
        collection.finished_at = datetime.now(UTC)
        if (
            captured_count == expected_total
            and classified == captured_count
            and invalid_count == 0
            and missing_store_count == 0
            and duplicate_count == 0
            and missing_identity_count == 0
            and collection.verified_count == accepted_count
        ):
            collection.collection_status = "verified"
            collection.error_code = None
            return
        collection.collection_status = "partial"
        collection.error_code = "SYNC_WFS_COLLECTION_INCOMPLETE"
        raise WfsSettlementPersistenceError("WFS_COLLECTION_INCOMPLETE")

    def fail_collection(self, collection: WfsSettlementCollection, code: str) -> None:
        collection.collection_status = "partial" if collection.captured_count else "failed"
        collection.error_code = code
        collection.finished_at = datetime.now(UTC)

    def get_verified_collection(
        self,
        *,
        source_account_ref: str,
        store_id: str,
        start_date: date,
        end_date: date,
    ) -> WfsSettlementCollection | None:
        return cast(
            WfsSettlementCollection | None,
            self.session.scalar(
                select(WfsSettlementCollection)
                .where(
                    WfsSettlementCollection.source_account_ref == source_account_ref,
                    WfsSettlementCollection.store_id == store_id,
                    WfsSettlementCollection.window_start == start_date,
                    WfsSettlementCollection.window_end == end_date,
                    WfsSettlementCollection.collection_status == "verified",
                )
                .order_by(WfsSettlementCollection.finished_at.desc())
                .limit(1)
            ),
        )

    def has_completed_collection(
        self,
        *,
        source_account_ref: str,
        store_id: str,
        start_date: date,
        end_date: date,
    ) -> bool:
        """Require an exact store/window proof, independent of sibling stores."""

        return (
            self.get_verified_collection(
                source_account_ref=source_account_ref,
                store_id=store_id,
                start_date=start_date,
                end_date=end_date,
            )
            is not None
        )

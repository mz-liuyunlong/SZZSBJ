from collections.abc import Mapping, Sequence
from uuid import UUID

from sqlalchemy import Select, String, func, nulls_last, or_, select
from sqlalchemy.orm import Session

from app.modules.integration_sync.models import (
    ApiRawBlob,
    ApiRawRequestRef,
    DataLineage,
    IntegrationSyncRun,
    IntegrationSyncRunEvent,
    IntegrationSyncRunWorkItem,
)
from app.modules.products.models import ProductPlatformListing
from app.modules.sku_detail.models import (
    LingxingSkuGlobalTag,
    LingxingSkuIdentity,
    LingxingSkuProductImage,
    LingxingSkuProductInfoCurrent,
    LingxingSkuProductInfoSnapshot,
    SkuBaseProfileCurrent,
)

type SkuProjection = tuple[
    LingxingSkuIdentity,
    LingxingSkuProductInfoCurrent | None,
    SkuBaseProfileCurrent | None,
]


class SkuDetailRepository:
    """SKU projection persistence; callers own all transactions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_skus(
        self,
        *,
        account_refs: frozenset[str],
        active: bool | None,
        mapping_status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[SkuProjection], int]:
        statement = self._projection().where(
            LingxingSkuIdentity.source_account_ref.in_(account_refs)
        )
        if active is not None:
            statement = statement.where(LingxingSkuIdentity.is_active == active)
        if mapping_status is not None:
            statement = statement.where(LingxingSkuIdentity.mapping_status == mapping_status)
        total = self.session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        rows = self.session.execute(
            statement.order_by(
                nulls_last(LingxingSkuIdentity.lingxing_sku_code.asc()),
                LingxingSkuIdentity.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [(row[0], row[1], row[2]) for row in rows], int(total or 0)

    def get_projection(self, sku_id: UUID, account_refs: frozenset[str]) -> SkuProjection | None:
        row = self.session.execute(
            self._projection().where(
                LingxingSkuIdentity.id == sku_id,
                LingxingSkuIdentity.source_account_ref.in_(account_refs),
            )
        ).first()
        return None if row is None else (row[0], row[1], row[2])

    def list_images(self, snapshot_id: UUID) -> list[LingxingSkuProductImage]:
        return list(
            self.session.scalars(
                select(LingxingSkuProductImage)
                .where(LingxingSkuProductImage.source_snapshot_id == snapshot_id)
                .order_by(LingxingSkuProductImage.ordinal, LingxingSkuProductImage.id)
            ).all()
        )

    def list_tags(self, snapshot_id: UUID) -> list[LingxingSkuGlobalTag]:
        return list(
            self.session.scalars(
                select(LingxingSkuGlobalTag)
                .where(LingxingSkuGlobalTag.source_snapshot_id == snapshot_id)
                .order_by(LingxingSkuGlobalTag.ordinal, LingxingSkuGlobalTag.id)
            ).all()
        )

    def list_history(
        self, identity_id: UUID, *, page: int, page_size: int
    ) -> tuple[
        list[
            tuple[
                LingxingSkuProductInfoSnapshot,
                IntegrationSyncRun,
                IntegrationSyncRunWorkItem,
            ]
        ],
        int,
    ]:
        statement = (
            select(
                LingxingSkuProductInfoSnapshot,
                IntegrationSyncRun,
                IntegrationSyncRunWorkItem,
            )
            .join(
                IntegrationSyncRun,
                IntegrationSyncRun.id == LingxingSkuProductInfoSnapshot.source_run_id,
            )
            .join(
                ApiRawRequestRef,
                ApiRawRequestRef.id == LingxingSkuProductInfoSnapshot.source_raw_request_ref_id,
            )
            .join(
                IntegrationSyncRunWorkItem,
                IntegrationSyncRunWorkItem.id == ApiRawRequestRef.work_item_id,
            )
            .where(LingxingSkuProductInfoSnapshot.identity_id == identity_id)
        )
        total = self.session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        rows = self.session.execute(
            statement.order_by(
                LingxingSkuProductInfoSnapshot.source_observed_at.desc(),
                LingxingSkuProductInfoSnapshot.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [(row[0], row[1], row[2]) for row in rows], int(total or 0)

    def list_lineage(
        self, identity_id: UUID, *, page: int, page_size: int
    ) -> tuple[list[tuple[DataLineage, ApiRawBlob]], int]:
        snapshot_ids = select(LingxingSkuProductInfoSnapshot.id).where(
            LingxingSkuProductInfoSnapshot.identity_id == identity_id
        )
        statement = (
            select(DataLineage, ApiRawBlob)
            .join(ApiRawBlob, ApiRawBlob.id == DataLineage.raw_blob_id)
            .where(
                or_(
                    DataLineage.target_record_id == str(identity_id),
                    DataLineage.target_record_id.in_(
                        select(func.cast(LingxingSkuProductInfoSnapshot.id, String)).where(
                            LingxingSkuProductInfoSnapshot.id.in_(snapshot_ids)
                        )
                    ),
                )
            )
        )
        return self._row_page(
            statement.order_by(DataLineage.created_at.desc(), DataLineage.id),
            page,
            page_size,
        )

    def list_platform_listings(
        self, product_id: UUID, *, page: int, page_size: int
    ) -> tuple[list[ProductPlatformListing], int]:
        statement = select(ProductPlatformListing).where(
            ProductPlatformListing.product_id == product_id,
            ProductPlatformListing.deleted_at.is_(None),
        )
        total = self.session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        rows = self.session.scalars(
            statement.order_by(
                ProductPlatformListing.platform,
                ProductPlatformListing.store_name,
                ProductPlatformListing.msku,
                ProductPlatformListing.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(total or 0)

    def list_cost_history(
        self, identity_id: UUID, *, page: int, page_size: int
    ) -> tuple[list[LingxingSkuProductInfoSnapshot], int]:
        statement = select(LingxingSkuProductInfoSnapshot).where(
            LingxingSkuProductInfoSnapshot.identity_id == identity_id
        )
        total = self.session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        rows = self.session.scalars(
            statement.order_by(
                LingxingSkuProductInfoSnapshot.source_observed_at.desc(),
                LingxingSkuProductInfoSnapshot.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(total or 0)

    def list_operation_logs(
        self,
        identity_id: UUID,
        *,
        event_type: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple[IntegrationSyncRunEvent, IntegrationSyncRun]], int]:
        run_ids = select(LingxingSkuProductInfoSnapshot.source_run_id).where(
            LingxingSkuProductInfoSnapshot.identity_id == identity_id
        )
        statement = (
            select(IntegrationSyncRunEvent, IntegrationSyncRun)
            .join(IntegrationSyncRun, IntegrationSyncRun.id == IntegrationSyncRunEvent.run_id)
            .where(IntegrationSyncRunEvent.run_id.in_(run_ids))
        )
        if event_type is not None:
            statement = statement.where(IntegrationSyncRunEvent.event_type == event_type)
        return self._row_page(
            statement.order_by(
                IntegrationSyncRunEvent.occurred_at.desc(), IntegrationSyncRunEvent.id
            ),
            page,
            page_size,
        )

    def add_snapshot(
        self, snapshot: LingxingSkuProductInfoSnapshot
    ) -> LingxingSkuProductInfoSnapshot:
        self.session.add(snapshot)
        self.session.flush()
        return snapshot

    def add_images(
        self, images: Sequence[LingxingSkuProductImage]
    ) -> list[LingxingSkuProductImage]:
        self.session.add_all(images)
        self.session.flush()
        return list(images)

    def add_tags(self, tags: Sequence[LingxingSkuGlobalTag]) -> list[LingxingSkuGlobalTag]:
        self.session.add_all(tags)
        self.session.flush()
        return list(tags)

    def get_current(self, identity_id: UUID) -> LingxingSkuProductInfoCurrent | None:
        return self.session.scalar(
            select(LingxingSkuProductInfoCurrent).where(
                LingxingSkuProductInfoCurrent.identity_id == identity_id
            )
        )

    def add_current(self, current: LingxingSkuProductInfoCurrent) -> LingxingSkuProductInfoCurrent:
        self.session.add(current)
        self.session.flush()
        return current

    def get_profile(self, identity_id: UUID) -> SkuBaseProfileCurrent | None:
        return self.session.scalar(
            select(SkuBaseProfileCurrent).where(SkuBaseProfileCurrent.identity_id == identity_id)
        )

    def add_profile(self, profile: SkuBaseProfileCurrent) -> SkuBaseProfileCurrent:
        self.session.add(profile)
        self.session.flush()
        return profile

    def update_record[ModelT](self, record: ModelT, values: Mapping[str, object]) -> ModelT:
        for name, value in values.items():
            setattr(record, name, value)
        self.session.flush()
        return record

    @staticmethod
    def _projection() -> Select[
        tuple[
            LingxingSkuIdentity,
            LingxingSkuProductInfoCurrent,
            SkuBaseProfileCurrent,
        ]
    ]:
        return (
            select(
                LingxingSkuIdentity,
                LingxingSkuProductInfoCurrent,
                SkuBaseProfileCurrent,
            )
            .outerjoin(
                LingxingSkuProductInfoCurrent,
                LingxingSkuProductInfoCurrent.identity_id == LingxingSkuIdentity.id,
            )
            .outerjoin(
                SkuBaseProfileCurrent,
                SkuBaseProfileCurrent.identity_id == LingxingSkuIdentity.id,
            )
        )

    def _row_page[LeftT, RightT](
        self,
        statement: Select[tuple[LeftT, RightT]],
        page: int,
        page_size: int,
    ) -> tuple[list[tuple[LeftT, RightT]], int]:
        total = self.session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        rows = self.session.execute(statement.offset((page - 1) * page_size).limit(page_size)).all()
        return [(row[0], row[1]) for row in rows], int(total or 0)

from typing import Literal, cast
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.sku_detail.models import LingxingSkuIdentity
from app.modules.sku_detail.repository import SkuDetailRepository, SkuProjection
from app.modules.sku_detail.schemas import (
    OperationLogQuery,
    SkuCostBlock,
    SkuCostHistoryData,
    SkuCostHistoryItem,
    SkuDetailData,
    SkuIdentityRead,
    SkuImageRead,
    SkuLineageData,
    SkuLineageItem,
    SkuListData,
    SkuListItem,
    SkuListQuery,
    SkuNonCostDetail,
    SkuOperationLogItem,
    SkuOperationLogsData,
    SkuPageQuery,
    SkuPlatformListingItem,
    SkuPlatformListingsData,
    SkuProfileRead,
    SkuSyncHistoryData,
    SkuSyncHistoryItem,
    SkuTagRead,
)


class SkuDetailService:
    def __init__(self, session: Session) -> None:
        self.repository = SkuDetailRepository(session)

    def list_skus(
        self, query: SkuListQuery, account_refs: frozenset[str]
    ) -> tuple[SkuListData, int]:
        rows, total = self.repository.list_skus(
            account_refs=account_refs,
            active=query.active,
            mapping_status=query.mapping_status,
            page=query.page,
            page_size=query.page_size,
        )
        items = [
            SkuListItem(
                sku_id=identity.id,
                lingxing_sku_code=identity.lingxing_sku_code,
                product_name=current.product_name if current else None,
                is_active=identity.is_active,
                mapping_status=cast(Literal["unmapped", "confirmed"], identity.mapping_status),
                last_seen_at=identity.last_seen_at,
                snapshot_at=current.source_observed_at if current else None,
                calculated_at=profile.calculated_at if profile else None,
            )
            for identity, current, profile in rows
        ]
        return SkuListData(items=items), total

    def get_detail(
        self,
        sku_id: UUID,
        account_refs: frozenset[str],
        *,
        include_costs: bool,
    ) -> SkuDetailData:
        identity, current, profile = self._require_projection(sku_id, account_refs)
        images = [] if current is None else self.repository.list_images(current.source_snapshot_id)
        tags = [] if current is None else self.repository.list_tags(current.source_snapshot_id)
        return SkuDetailData(
            identity=self._identity(identity),
            detail=SkuNonCostDetail.model_validate(current) if current else None,
            images=[SkuImageRead.model_validate(item) for item in images],
            tags=[SkuTagRead.model_validate(item) for item in tags],
            profile=(
                SkuProfileRead(
                    product_volume_cm3=profile.product_volume_cm3,
                    package_volume_cm3=profile.package_volume_cm3,
                    box_volume_cm3=profile.box_volume_cm3,
                    box_volume_cbm=profile.box_volume_cbm,
                    product_net_weight_kg=profile.product_net_weight_kg,
                    product_gross_weight_kg=profile.product_gross_weight_kg,
                    unit_box_weight_kg=profile.unit_box_weight_kg,
                    unit_first_leg_cost=(profile.unit_first_leg_cost if include_costs else None),
                    unit_first_leg_currency=(
                        profile.unit_first_leg_currency if include_costs else None
                    ),
                    has_customs_info=profile.has_customs_info,
                    has_package_info=profile.has_package_info,
                    has_logistics_info=profile.has_logistics_info,
                    missing_fields=profile.missing_fields_json,
                    data_quality_score=profile.data_quality_score,
                    calculated_at=profile.calculated_at,
                )
                if profile
                else None
            ),
            costs=(
                SkuCostBlock.model_validate(current)
                if include_costs and current is not None
                else None
            ),
        )

    def sync_history(
        self, sku_id: UUID, query: SkuPageQuery, account_refs: frozenset[str]
    ) -> tuple[SkuSyncHistoryData, int]:
        identity, _, _ = self._require_projection(sku_id, account_refs)
        rows, total = self.repository.list_history(
            identity.id, page=query.page, page_size=query.page_size
        )
        return (
            SkuSyncHistoryData(
                items=[
                    SkuSyncHistoryItem(
                        run_id=run.id,
                        run_status=run.status,
                        trigger_type=run.trigger_type,
                        work_item_id=work_item.id,
                        work_item_status=work_item.status,
                        snapshot_id=snapshot.id,
                        snapshot_at=snapshot.source_observed_at,
                        parser_version=snapshot.parser_version,
                    )
                    for snapshot, run, work_item in rows
                ]
            ),
            total,
        )

    def raw_lineage(
        self, sku_id: UUID, query: SkuPageQuery, account_refs: frozenset[str]
    ) -> tuple[SkuLineageData, int]:
        identity, _, _ = self._require_projection(sku_id, account_refs)
        rows, total = self.repository.list_lineage(
            identity.id, page=query.page, page_size=query.page_size
        )
        return (
            SkuLineageData(
                items=[
                    SkuLineageItem(
                        lineage_id=lineage.id,
                        raw_request_ref_id=lineage.raw_request_ref_id,
                        raw_blob_id=lineage.raw_blob_id,
                        source_path=lineage.source_path,
                        target_table=lineage.target_table,
                        target_field=lineage.target_field,
                        transform_key=lineage.transform_key,
                        transform_version=lineage.transform_version,
                        response_hash=blob.response_hash,
                        storage_mode=blob.storage_mode,
                        received_at=blob.received_at,
                    )
                    for lineage, blob in rows
                ]
            ),
            total,
        )

    def platform_listings(
        self, sku_id: UUID, query: SkuPageQuery, account_refs: frozenset[str]
    ) -> tuple[SkuPlatformListingsData, int]:
        identity, _, _ = self._require_projection(sku_id, account_refs)
        if identity.mapping_status != "confirmed" or identity.product_id is None:
            return SkuPlatformListingsData(mapping_status="unmapped", items=[]), 0
        rows, total = self.repository.list_platform_listings(
            identity.product_id, page=query.page, page_size=query.page_size
        )
        return (
            SkuPlatformListingsData(
                mapping_status="confirmed",
                items=[SkuPlatformListingItem.model_validate(row) for row in rows],
            ),
            total,
        )

    def cost_history(
        self, sku_id: UUID, query: SkuPageQuery, account_refs: frozenset[str]
    ) -> tuple[SkuCostHistoryData, int]:
        identity, _, _ = self._require_projection(sku_id, account_refs)
        rows, total = self.repository.list_cost_history(
            identity.id, page=query.page, page_size=query.page_size
        )
        return (
            SkuCostHistoryData(
                items=[
                    SkuCostHistoryItem(
                        snapshot_id=row.id,
                        source_run_id=row.source_run_id,
                        source_observed_at=row.source_observed_at,
                        purchase_cost_cny=row.purchase_cost_cny,
                        purchase_cost_currency_code=row.purchase_cost_currency_code,
                        customs_declared_unit_price=row.customs_declared_unit_price,
                        customs_declared_currency=row.customs_declared_currency,
                        us_first_leg_cost=row.us_first_leg_cost,
                        us_first_leg_currency=row.us_first_leg_currency,
                    )
                    for row in rows
                ]
            ),
            total,
        )

    def operation_logs(
        self, sku_id: UUID, query: OperationLogQuery, account_refs: frozenset[str]
    ) -> tuple[SkuOperationLogsData, int]:
        identity, _, _ = self._require_projection(sku_id, account_refs)
        rows, total = self.repository.list_operation_logs(
            identity.id,
            event_type=query.event_type,
            page=query.page,
            page_size=query.page_size,
        )
        return (
            SkuOperationLogsData(
                items=[
                    SkuOperationLogItem(
                        event_id=event.id,
                        run_id=run.id,
                        event_type=event.event_type,
                        from_status=event.from_status,
                        to_status=event.to_status,
                        message_code=event.message_code,
                        actor_ref=event.actor_ref,
                        request_id=run.request_id,
                        occurred_at=event.occurred_at,
                    )
                    for event, run in rows
                ]
            ),
            total,
        )

    def _require_projection(self, sku_id: UUID, account_refs: frozenset[str]) -> SkuProjection:
        row = self.repository.get_projection(sku_id, account_refs)
        if row is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        return row

    @staticmethod
    def _identity(identity: LingxingSkuIdentity) -> SkuIdentityRead:
        return SkuIdentityRead(
            sku_id=identity.id,
            provider=identity.provider,
            source_account_ref=identity.source_account_ref,
            lingxing_sku_code=identity.lingxing_sku_code,
            mapping_status=cast(Literal["unmapped", "confirmed"], identity.mapping_status),
            is_active=identity.is_active,
            first_seen_at=identity.first_seen_at,
            last_seen_at=identity.last_seen_at,
        )

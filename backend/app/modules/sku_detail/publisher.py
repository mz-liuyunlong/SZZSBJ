from dataclasses import asdict
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.modules.integration_sync.models import (
    DataLineage,
    IntegrationSyncRunEvent,
    ParseJob,
)
from app.modules.integration_sync.parsers.lingxing_product_info import ParsedSkuDetail
from app.modules.integration_sync.repository import IntegrationSyncRepository
from app.modules.sku_detail.calculations import calculate_sku_profile
from app.modules.sku_detail.models import (
    LingxingSkuGlobalTag,
    LingxingSkuProductImage,
    LingxingSkuProductInfoCurrent,
    LingxingSkuProductInfoSnapshot,
    SkuBaseProfileCurrent,
    utc_now,
)
from app.modules.sku_detail.repository import SkuDetailRepository

DETAIL_SOURCE_PATHS = {
    "product_name": "$.data.product_name",
    "lingxing_sku_code": "$.data.sku",
    "main_image_url": "$.data.pic_url",
    "product_developer_name": "$.data.product_developer",
    "product_developer_uid": "$.data.product_developer_uid",
    "purchase_delivery_days": "$.data.cg_delivery",
    "purchase_cost_cny": "$.data.cg_price",
    "purchase_cost_currency_code": "$.data.cg_price",
    "purchase_material": "$.data.cg_product_material",
    "customs_export_name_cn": "$.data.bg_customs_export_name",
    "customs_import_name_en": "$.data.bg_customs_import_name",
    "customs_declared_unit_price": "$.data.bg_customs_import_price",
    "china_hs_code": "$.data.bg_export_hs_code",
    "owner_uid": "$.data.permission_user_info.permission_uid",
    "owner_name": "$.data.permission_user_info.permission_user_name",
    "clearance_material_cn": "$.data.clearance.customs_clearance_material",
    "clearance_usage_cn": "$.data.clearance.customs_clearance_usage",
    "clearance_material_en": "$.data.clearance.customs_clearance_en_material",
    "us_first_leg_cost": "$.data.product_logistics_relation.US_cg_transport_costs",
    "us_first_leg_currency": "$.data.product_logistics_relation.US_currency",
    "product_length_cm": "$.data.cg_product_length",
    "product_width_cm": "$.data.cg_product_width",
    "product_height_cm": "$.data.cg_product_height",
    "product_net_weight_g": "$.data.cg_product_net_weight",
    "product_gross_weight_g": "$.data.cg_product_gross_weight",
    "package_length_cm": "$.data.cg_package_length",
    "package_width_cm": "$.data.cg_package_width",
    "package_height_cm": "$.data.cg_package_height",
    "box_length_cm": "$.data.cg_box_length",
    "box_width_cm": "$.data.cg_box_width",
    "box_height_cm": "$.data.cg_box_height",
    "box_pcs": "$.data.cg_box_pcs",
    "box_weight_kg": "$.data.cg_box_weight",
}

DWS_SOURCE_PATHS = {
    "product_volume_cm3": (
        "$.data.cg_product_length",
        "$.data.cg_product_width",
        "$.data.cg_product_height",
    ),
    "package_volume_cm3": (
        "$.data.cg_package_length",
        "$.data.cg_package_width",
        "$.data.cg_package_height",
    ),
    "box_volume_cm3": (
        "$.data.cg_box_length",
        "$.data.cg_box_width",
        "$.data.cg_box_height",
    ),
    "box_volume_cbm": (
        "$.data.cg_box_length",
        "$.data.cg_box_width",
        "$.data.cg_box_height",
    ),
    "product_net_weight_kg": ("$.data.cg_product_net_weight",),
    "product_gross_weight_kg": ("$.data.cg_product_gross_weight",),
    "unit_box_weight_kg": ("$.data.cg_box_weight", "$.data.cg_box_pcs"),
    "purchase_cost_cny": ("$.data.cg_price",),
    "purchase_cost_currency_code": ("$.data.cg_price",),
    "us_first_leg_cost": ("$.data.product_logistics_relation.US_cg_transport_costs",),
    "us_first_leg_currency": ("$.data.product_logistics_relation.US_currency",),
    "unit_first_leg_cost": (
        "$.data.product_logistics_relation.US_cg_transport_costs",
        "$.data.cg_box_pcs",
    ),
    "unit_first_leg_currency": (
        "$.data.product_logistics_relation.US_currency",
        "$.data.cg_box_pcs",
    ),
    "has_customs_info": (
        "$.data.bg_customs_export_name",
        "$.data.bg_customs_import_name",
        "$.data.bg_customs_import_price",
        "$.data.bg_export_hs_code",
        "$.data.clearance.customs_clearance_material",
        "$.data.clearance.customs_clearance_usage",
        "$.data.clearance.customs_clearance_en_material",
    ),
    "has_package_info": (
        "$.data.cg_package_length",
        "$.data.cg_package_width",
        "$.data.cg_package_height",
    ),
    "has_logistics_info": (
        "$.data.product_logistics_relation.US_cg_transport_costs",
        "$.data.product_logistics_relation.US_currency",
    ),
    "missing_fields_json": tuple(DETAIL_SOURCE_PATHS.values()),
    "data_quality_score": tuple(DETAIL_SOURCE_PATHS.values()),
}


class SkuDetailPublicationError(RuntimeError):
    """Safe publication error without raw values."""


class SkuDetailPublicationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.sync_repository = IntegrationSyncRepository(session)
        self.repository = SkuDetailRepository(session)

    def publish(
        self,
        *,
        run_id: UUID,
        raw_request_ref_id: UUID,
        source_account_ref: str,
        lingxing_sku_id: str,
        source_observed_at: datetime,
        parser_version: str,
        parsed: ParsedSkuDetail,
        calc_version: str = "v1",
    ) -> UUID:
        identity = self.sync_repository.get_lingxing_identity(source_account_ref, lingxing_sku_id)
        raw_ref = self.sync_repository.get_raw_request_ref(raw_request_ref_id)
        if identity is None or raw_ref is None or raw_ref.run_id != run_id:
            raise SkuDetailPublicationError("SKU_DETAIL_PUBLICATION_SOURCE_INVALID")
        detail_values = parsed.model_dump(exclude={"images", "tags"})
        snapshot = LingxingSkuProductInfoSnapshot(
            id=uuid4(),
            provider="lingxing",
            source_account_ref=source_account_ref,
            identity_id=identity.id,
            lingxing_sku_id=lingxing_sku_id,
            source_run_id=run_id,
            source_raw_request_ref_id=raw_request_ref_id,
            parser_version=parser_version,
            source_observed_at=source_observed_at,
            **detail_values,
        )
        now = utc_now()
        try:
            self.repository.add_snapshot(snapshot)
            images = [
                LingxingSkuProductImage(
                    id=uuid4(),
                    source_snapshot_id=snapshot.id,
                    identity_id=identity.id,
                    ordinal=image.ordinal,
                    pic_url=image.pic_url,
                    is_primary=image.is_primary,
                )
                for image in parsed.images
            ]
            tags = [
                LingxingSkuGlobalTag(
                    id=uuid4(),
                    source_snapshot_id=snapshot.id,
                    identity_id=identity.id,
                    ordinal=tag.ordinal,
                    global_tag_id=tag.global_tag_id,
                    tag_name=tag.tag_name,
                    color=tag.color,
                )
                for tag in parsed.tags
            ]
            self.repository.add_images(images)
            self.repository.add_tags(tags)
            current_id: UUID | None = None
            profile_id: UUID | None = None
            current = self.repository.get_current(identity.id)
            if current is None or current.source_observed_at <= source_observed_at:
                current_values = {
                    **detail_values,
                    "provider": "lingxing",
                    "source_account_ref": source_account_ref,
                    "identity_id": identity.id,
                    "lingxing_sku_id": lingxing_sku_id,
                    "source_snapshot_id": snapshot.id,
                    "source_run_id": run_id,
                    "source_observed_at": source_observed_at,
                    "updated_at": now,
                }
                if current is None:
                    current = LingxingSkuProductInfoCurrent(id=uuid4(), **current_values)
                    self.repository.add_current(current)
                else:
                    self.repository.update_record(current, current_values)
                current_id = current.id
                calculated = calculate_sku_profile(parsed)
                profile_values = {
                    **asdict(calculated),
                    "identity_id": identity.id,
                    "provider": "lingxing",
                    "source_account_ref": source_account_ref,
                    "lingxing_sku_id": lingxing_sku_id,
                    "source_run_id": run_id,
                    "source_snapshot_id": snapshot.id,
                    "calc_version": calc_version,
                    "calculated_at": now,
                    "updated_at": now,
                }
                profile = self.repository.get_profile(identity.id)
                if profile is None:
                    profile = SkuBaseProfileCurrent(id=uuid4(), **profile_values)
                    self.repository.add_profile(profile)
                else:
                    self.repository.update_record(profile, profile_values)
                profile_id = profile.id
            parse_job = self.sync_repository.add_parse_job(
                ParseJob(
                    id=uuid4(),
                    run_id=run_id,
                    raw_request_ref_id=raw_request_ref_id,
                    parser_key="lingxing.product_info.v1",
                    parser_version=parser_version,
                    target_layer="DWD",
                    status="succeeded",
                    records_seen=1,
                    records_written=1,
                    records_rejected=0,
                    started_at=now,
                    finished_at=now,
                )
            )
            self.sync_repository.add_lineage(
                self._lineage_entries(
                    run_id=run_id,
                    parse_job_id=parse_job.id,
                    raw_request_ref_id=raw_request_ref_id,
                    raw_blob_id=raw_ref.raw_blob_id,
                    target_table="dwd_lingxing_sku_product_info_snapshots",
                    target_record_id=snapshot.id,
                    paths=DETAIL_SOURCE_PATHS,
                    transform_key="lingxing.product_info.standardize",
                    transform_version=parser_version,
                )
                + (
                    self._lineage_entries(
                        run_id=run_id,
                        parse_job_id=parse_job.id,
                        raw_request_ref_id=raw_request_ref_id,
                        raw_blob_id=raw_ref.raw_blob_id,
                        target_table="dwd_lingxing_sku_product_info_current",
                        target_record_id=current_id,
                        paths=DETAIL_SOURCE_PATHS,
                        transform_key="lingxing.product_info.current",
                        transform_version=parser_version,
                    )
                    if current_id is not None
                    else []
                )
                + [
                    DataLineage(
                        id=uuid4(),
                        run_id=run_id,
                        parse_job_id=parse_job.id,
                        raw_request_ref_id=raw_request_ref_id,
                        raw_blob_id=raw_ref.raw_blob_id,
                        source_path=f"$.data.picture_list[{image.ordinal}].{field}",
                        target_table="dwd_lingxing_sku_product_images",
                        target_record_id=str(image.id),
                        target_field=field,
                        transform_key="lingxing.product_info.image",
                        transform_version=parser_version,
                    )
                    for image in images
                    for field in ("pic_url", "is_primary")
                ]
                + [
                    DataLineage(
                        id=uuid4(),
                        run_id=run_id,
                        parse_job_id=parse_job.id,
                        raw_request_ref_id=raw_request_ref_id,
                        raw_blob_id=raw_ref.raw_blob_id,
                        source_path=f"$.data.global_tags[{tag.ordinal}].{source_field}",
                        target_table="dwd_lingxing_sku_global_tags",
                        target_record_id=str(tag.id),
                        target_field=target_field,
                        transform_key="lingxing.product_info.tag",
                        transform_version=parser_version,
                    )
                    for tag in tags
                    for target_field, source_field in (
                        ("global_tag_id", "id"),
                        ("tag_name", "name"),
                        ("color", "color"),
                    )
                ]
                + (
                    [
                        DataLineage(
                            id=uuid4(),
                            run_id=run_id,
                            parse_job_id=parse_job.id,
                            raw_request_ref_id=raw_request_ref_id,
                            raw_blob_id=raw_ref.raw_blob_id,
                            source_path=source_path,
                            target_table="dws_sku_base_profile_current",
                            target_record_id=str(profile_id),
                            target_field=field,
                            transform_key="lingxing.sku_profile.calculate",
                            transform_version=calc_version,
                        )
                        for field, source_paths in DWS_SOURCE_PATHS.items()
                        for source_path in source_paths
                    ]
                    if profile_id is not None
                    else []
                )
            )
            self.sync_repository.add_event(
                IntegrationSyncRunEvent(
                    run_id=run_id,
                    sequence_no=self.sync_repository.next_event_sequence(run_id),
                    event_type="parse",
                    from_status=None,
                    to_status=None,
                    message_code="PARSE_JOB_SUCCEEDED",
                    safe_details={"records_written": 1},
                    occurred_at=now,
                    actor_ref="parser",
                )
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return snapshot.id

    @staticmethod
    def _lineage_entries(
        *,
        run_id: UUID,
        parse_job_id: UUID,
        raw_request_ref_id: UUID,
        raw_blob_id: UUID,
        target_table: str,
        target_record_id: UUID,
        paths: dict[str, str],
        transform_key: str,
        transform_version: str,
    ) -> list[DataLineage]:
        return [
            DataLineage(
                id=uuid4(),
                run_id=run_id,
                parse_job_id=parse_job_id,
                raw_request_ref_id=raw_request_ref_id,
                raw_blob_id=raw_blob_id,
                source_path=source_path,
                target_table=target_table,
                target_record_id=str(target_record_id),
                target_field=field,
                transform_key=transform_key,
                transform_version=transform_version,
            )
            for field, source_path in paths.items()
        ]

import inspect

import app.modules.integration_sync.models  # noqa: F401
import app.modules.products.models  # noqa: F401
import app.modules.sku_detail.models  # noqa: F401
from app.db.base import Base
from app.modules.integration_sync.repository import IntegrationSyncRepository

EXPECTED_TABLES = {
    "gov_integration_interfaces",
    "gov_integration_interface_dependencies",
    "gov_integration_sync_configs",
    "gov_integration_sync_runs",
    "gov_integration_sync_run_events",
    "gov_integration_sync_locks",
    "gov_integration_sync_run_work_items",
    "gov_raw_retention_policies",
    "gov_parse_jobs",
    "gov_data_lineage",
    "ods_api_raw_blobs",
    "ods_api_raw_request_refs",
    "ods_lingxing_productlist_sku_refs",
    "ods_lingxing_product_info_batch_items",
    "dwd_lingxing_sku_identity_index",
    "dwd_lingxing_sku_product_info_snapshots",
    "dwd_lingxing_sku_product_info_current",
    "dwd_lingxing_sku_product_images",
    "dwd_lingxing_sku_global_tags",
    "dws_sku_base_profile_current",
}


def test_twenty_approved_tables_use_single_metadata() -> None:
    assert EXPECTED_TABLES <= set(Base.metadata.tables)
    assert len(EXPECTED_TABLES) == 20


def test_repository_does_not_own_transactions_or_engines() -> None:
    source = inspect.getsource(IntegrationSyncRepository)
    assert ".commit(" not in source
    assert ".rollback(" not in source
    assert "create_engine" not in source


def test_raw_payload_is_not_part_of_api_schema() -> None:
    from app.modules.integration_sync.schemas import RawRequestMetadataRead

    assert "payload_json" not in RawRequestMetadataRead.model_fields
    assert "archive_uri" not in RawRequestMetadataRead.model_fields

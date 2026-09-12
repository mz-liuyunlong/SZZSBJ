from uuid import uuid4

from sqlalchemy.orm import Session

from app.modules.integration_sync.models import (
    IntegrationInterface,
    IntegrationInterfaceDependency,
    RawRetentionPolicy,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository


class IntegrationCatalogService:
    """Idempotent application bootstrap; never runs implicitly at startup."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = IntegrationSyncRepository(session)

    def bootstrap_lingxing_v1(self) -> None:
        try:
            product_list = self._interface(
                interface_key="productList",
                display_name="Lingxing ProductList",
                endpoint_path="/erp/sc/routing/data/local_inventory/productList",
                request_kind="offset_page",
                handler_key="lingxing.product_list_import.v1",
            )
            batch = self._interface(
                interface_key="batchGetProductInfo",
                display_name="Lingxing Batch Product Info",
                endpoint_path="/erp/sc/routing/data/local_inventory/batchGetProductInfo",
                request_kind="id_batch_page",
                handler_key="lingxing.batch_get_product_info.v1",
            )
            if self.repository.get_retention_policy("lingxing-productlist-v1") is None:
                self.repository.add_catalog_record(
                    RawRetentionPolicy(
                        id=uuid4(),
                        policy_key="lingxing-productlist-v1",
                        provider="lingxing",
                        interface_key="productList",
                        hot_retention_days=30,
                        archive_after_days=None,
                        delete_after_days=None,
                        archive_required=False,
                        legal_hold=False,
                        is_active=True,
                    )
                )
            if not self.repository.has_dependency(product_list.id, batch.id):
                self.repository.add_catalog_record(
                    IntegrationInterfaceDependency(
                        id=uuid4(),
                        source_interface_id=product_list.id,
                        target_interface_id=batch.id,
                        dependency_key="lingxing_sku_id",
                        dependency_type="requires_sku_ids",
                        is_required=True,
                    )
                )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def _interface(
        self,
        *,
        interface_key: str,
        display_name: str,
        endpoint_path: str,
        request_kind: str,
        handler_key: str,
    ) -> IntegrationInterface:
        existing = self.repository.get_interface_by_key("lingxing", interface_key)
        if existing is not None:
            return existing
        return self.repository.add_catalog_record(
            IntegrationInterface(
                id=uuid4(),
                provider="lingxing",
                interface_key=interface_key,
                display_name=display_name,
                method="POST",
                endpoint_path=endpoint_path,
                request_kind=request_kind,
                handler_key=handler_key,
                contract_version="v1",
                outbound_enabled=False,
            )
        )

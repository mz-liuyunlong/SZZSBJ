from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.modules.integration_sync.models import (
    IntegrationInterface,
    IntegrationInterfaceDependency,
    IntegrationSyncConfig,
    RawRetentionPolicy,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository

BootstrapStatus = Literal["created", "updated", "unchanged"]


class ProductListGovernanceBootstrapError(RuntimeError):
    """Safe bootstrap validation error without environment or account values."""


@dataclass(frozen=True, slots=True)
class ProductListGovernanceBootstrapResult:
    interface_status: BootstrapStatus
    retention_policy_status: BootstrapStatus
    sync_config_status: BootstrapStatus


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

    def bootstrap_productlist_governance(
        self,
        source_account_ref: str,
    ) -> ProductListGovernanceBootstrapResult:
        source_account_ref = validate_productlist_source_account_ref(source_account_ref)
        try:
            interface = self.repository.get_interface_by_key("lingxing", "productList")
            if interface is None:
                interface = self.repository.add_catalog_record(
                    IntegrationInterface(
                        id=uuid4(),
                        provider="lingxing",
                        interface_key="productList",
                        display_name="Lingxing ProductList",
                        method="POST",
                        endpoint_path="/erp/sc/routing/data/local_inventory/productList",
                        request_kind="offset_page",
                        handler_key="lingxing.product_list_sync.v1",
                        contract_version="v1",
                        outbound_enabled=True,
                    )
                )
                interface_status: BootstrapStatus = "created"
            else:
                interface_status = _apply_approved_values(
                    interface,
                    display_name="Lingxing ProductList",
                    method="POST",
                    endpoint_path="/erp/sc/routing/data/local_inventory/productList",
                    request_kind="offset_page",
                    handler_key="lingxing.product_list_sync.v1",
                    contract_version="v1",
                    outbound_enabled=True,
                )

            policy = self.repository.get_retention_policy_by_key("lingxing-productlist-v1")
            if policy is None:
                policy = self.repository.add_catalog_record(
                    RawRetentionPolicy(
                        id=uuid4(),
                        policy_key="lingxing-productlist-v1",
                        provider="lingxing",
                        interface_key="productList",
                        hot_retention_days=365,
                        archive_after_days=None,
                        delete_after_days=None,
                        archive_required=False,
                        legal_hold=False,
                        is_active=True,
                    )
                )
                retention_policy_status: BootstrapStatus = "created"
            else:
                retention_policy_status = _apply_approved_values(
                    policy,
                    provider="lingxing",
                    interface_key="productList",
                    hot_retention_days=365,
                    archive_after_days=None,
                    delete_after_days=None,
                    archive_required=False,
                    legal_hold=False,
                    is_active=True,
                )

            config = self.repository.get_config_by_scope(interface.id, source_account_ref)
            if config is None:
                self.repository.add_catalog_record(
                    IntegrationSyncConfig(
                        id=uuid4(),
                        interface_id=interface.id,
                        source_account_ref=source_account_ref,
                        is_enabled=True,
                        schedule_enabled=False,
                        schedule_cron=None,
                        schedule_timezone="UTC",
                        page_size=1000,
                        max_pages=10000,
                        max_attempts=1,
                        retention_policy_id=policy.id,
                    )
                )
                sync_config_status: BootstrapStatus = "created"
            else:
                sync_config_status = _apply_approved_values(
                    config,
                    is_enabled=True,
                    schedule_enabled=False,
                    schedule_cron=None,
                    schedule_timezone="UTC",
                    page_size=1000,
                    max_pages=10000,
                    max_attempts=1,
                    retention_policy_id=policy.id,
                )
            self.session.commit()
            return ProductListGovernanceBootstrapResult(
                interface_status=interface_status,
                retention_policy_status=retention_policy_status,
                sync_config_status=sync_config_status,
            )
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


def validate_productlist_source_account_ref(value: str) -> str:
    if not value or value != value.strip() or len(value) > 128:
        raise ProductListGovernanceBootstrapError(
            "PRODUCTLIST_GOVERNANCE_BOOTSTRAP_SOURCE_ACCOUNT_REF_INVALID"
        )
    return value


def _apply_approved_values(record: object, **values: object) -> BootstrapStatus:
    changed = False
    for name, value in values.items():
        if getattr(record, name) != value:
            setattr(record, name, value)
            changed = True
    return "updated" if changed else "unchanged"

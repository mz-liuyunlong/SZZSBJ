from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import JSON, Column, Engine, MetaData, String, Table, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.sqltypes import NullType

from app.core.auth import Principal, get_optional_principal
from app.db.model_registry import register_productlist_sync_models
from app.db.session import get_db_session
from app.main import create_app
from app.modules.integration_sync.dependencies import get_source_account_scope_provider
from app.modules.integration_sync.handlers.lingxing_batch_product_info import (
    LingxingBatchGetProductInfoSyncHandler,
)
from app.modules.integration_sync.product_info_runner import (
    ProductInfoFixtureBatch,
    ProductInfoFixtureBatchExecutor,
    ProductInfoOneTimeRunError,
    ProductInfoOneTimeRunner,
    ProductInfoSyncExecutionResult,
)
from app.modules.product_management.models import (
    ManualProductTag,
    ManualProductTagAssignment,
    ProductManagementPricingCurrent,
    ProductPricingRuleVersion,
)
from app.modules.product_management.schemas import ProductManagementListQuery
from app.modules.product_management.service import ProductManagementService
from app.modules.products.bootstrap import (
    ProductInfoProductBootstrapError,
    ProductInfoProductBootstrapResult,
    ProductInfoProductBootstrapService,
)
from app.modules.products.dependencies import get_product_scope_provider
from app.modules.products.models import Product, ProductPlatformListing
from app.modules.sku_detail.models import (
    LingxingSkuGlobalTag,
    LingxingSkuIdentity,
    LingxingSkuProductImage,
    LingxingSkuProductInfoCurrent,
    LingxingSkuProductInfoSnapshot,
    SkuBaseProfileCurrent,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
PRODUCT_ID = UUID("00000000-0000-0000-0000-000000000010")


@pytest.fixture
def product_management_db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        _create_product_management_storage(engine)
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def _create_product_management_storage(engine: Engine) -> None:
    register_productlist_sync_models()
    sources = (
        Product.__table__,
        ProductPlatformListing.__table__,
        LingxingSkuIdentity.__table__,
        LingxingSkuProductInfoSnapshot.__table__,
        LingxingSkuProductInfoCurrent.__table__,
        LingxingSkuProductImage.__table__,
        LingxingSkuGlobalTag.__table__,
        SkuBaseProfileCurrent.__table__,
        ManualProductTag.__table__,
        ManualProductTagAssignment.__table__,
        ProductPricingRuleVersion.__table__,
        ProductManagementPricingCurrent.__table__,
    )
    storage = MetaData()
    for source in sources:
        source_table = cast(Table, source)
        Table(
            source_table.name,
            storage,
            *(
                Column(
                    column.name,
                    JSON()
                    if isinstance(column.type, JSONB)
                    else String()
                    if isinstance(column.type, NullType)
                    else column.type,
                    primary_key=column.primary_key,
                    nullable=column.nullable,
                )
                for column in source_table.columns
            ),
        )
    storage.create_all(engine)


def _add_unbootstrapped_identity(session: Session) -> tuple[LingxingSkuIdentity, str]:
    suffix = uuid4().hex
    source_account_ref = f"synthetic-account-{suffix}"
    run_id = uuid4()
    identity = LingxingSkuIdentity(
        id=uuid4(),
        provider="lingxing",
        source_account_ref=source_account_ref,
        lingxing_sku_id=f"synthetic-id-{suffix}",
        product_id=None,
        mapping_status="unmapped",
        is_active=True,
        first_seen_run_id=run_id,
        last_seen_run_id=run_id,
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    snapshot = LingxingSkuProductInfoSnapshot(
        id=uuid4(),
        provider="lingxing",
        source_account_ref=source_account_ref,
        identity_id=identity.id,
        lingxing_sku_id=identity.lingxing_sku_id,
        lingxing_sku_code=f"SYNTHETIC-DB-{suffix}",
        product_name="Synthetic Database Product",
        source_run_id=run_id,
        source_raw_request_ref_id=uuid4(),
        parser_version="synthetic-contract-v1",
        source_observed_at=NOW,
    )
    current = LingxingSkuProductInfoCurrent(
        id=uuid4(),
        provider="lingxing",
        source_account_ref=source_account_ref,
        identity_id=identity.id,
        lingxing_sku_id=identity.lingxing_sku_id,
        lingxing_sku_code=snapshot.lingxing_sku_code,
        product_name=snapshot.product_name,
        source_snapshot_id=snapshot.id,
        source_run_id=run_id,
        source_observed_at=NOW,
    )
    session.add_all((identity, snapshot, current))
    session.flush()
    return identity, source_account_ref


def _bootstrap_product_in_database(session: Session) -> tuple[LingxingSkuIdentity, str]:
    identity, source_account_ref = _add_unbootstrapped_identity(session)

    result = ProductInfoProductBootstrapService(session).execute(
        source_account_ref,
        authorized=True,
    )

    assert result.created == 1
    assert identity.product_id is not None
    assert identity.mapping_status == "confirmed"
    return identity, source_account_ref


def _row(
    index: int,
    *,
    sku_code: str | None,
    product_name: str | None,
) -> tuple[LingxingSkuIdentity, SimpleNamespace, SimpleNamespace]:
    identity = LingxingSkuIdentity(
        id=UUID(int=index),
        provider="lingxing",
        source_account_ref="synthetic-account",
        lingxing_sku_id=f"synthetic-id-{index}",
        product_id=None,
        mapping_status="unmapped",
        is_active=True,
    )
    current = SimpleNamespace(
        lingxing_sku_code=sku_code,
        product_name=product_name,
        source_run_id=UUID(int=index + 100),
    )
    snapshot = SimpleNamespace(
        id=UUID(int=index + 200),
        parser_version="contract-v1",
    )
    return identity, current, snapshot


@dataclass(frozen=True)
class BootstrapHarness:
    service: ProductInfoProductBootstrapService
    session: MagicMock
    sku_repository: MagicMock
    product_repository: MagicMock


def _service(rows: Sequence[tuple[object, object, object]]) -> BootstrapHarness:
    session = MagicMock(spec=Session)
    service = ProductInfoProductBootstrapService(session)
    sku_repository = MagicMock()
    product_repository = MagicMock()
    service.sku_repository = sku_repository
    service.product_repository = product_repository
    sku_repository.list_product_bootstrap_rows.return_value = rows

    def update(record: object, values: dict[str, object]) -> object:
        for name, value in values.items():
            setattr(record, name, value)
        return record

    sku_repository.update_record.side_effect = update
    return BootstrapHarness(service, session, sku_repository, product_repository)


def test_bootstrap_creates_minimal_product_and_confirms_mapping() -> None:
    identity, current, snapshot = _row(
        1,
        sku_code="  SYNTHETIC-SKU  ",
        product_name="  Synthetic Product  ",
    )
    harness = _service([(identity, current, snapshot)])
    harness.product_repository.find_product_by_sku.return_value = None

    def add_product(product: Product) -> Product:
        product.id = PRODUCT_ID
        return product

    harness.product_repository.add_product.side_effect = add_product

    result = harness.service.execute("synthetic-account", authorized=True)

    created = harness.product_repository.add_product.call_args.args[0]
    assert created.sku == "SYNTHETIC-SKU"
    assert created.product_name == "Synthetic Product"
    assert created.purchase_price is None
    assert created.grade is None
    assert identity.product_id == PRODUCT_ID
    assert identity.mapping_status == "confirmed"
    assert identity.mapping_evidence_ref is not None
    assert identity.mapping_evidence_ref.startswith("productinfo_bootstrap:synthetic-account:")
    assert "SYNTHETIC-SKU" not in identity.mapping_evidence_ref
    assert result.created == 1
    harness.session.commit.assert_called_once_with()


def test_bootstrap_exact_links_active_product_without_overwrite() -> None:
    identity, current, snapshot = _row(
        1,
        sku_code="SYNTHETIC-SKU",
        product_name="Synced Name",
    )
    existing = Product(
        id=PRODUCT_ID,
        sku="SYNTHETIC-SKU",
        product_name="Manual Name",
        status="manual-status",
        deleted_at=None,
    )
    harness = _service([(identity, current, snapshot)])
    harness.product_repository.find_product_by_sku.return_value = existing

    result = harness.service.execute("synthetic-account", authorized=True)

    assert result.linked == 1
    assert existing.product_name == "Manual Name"
    assert existing.status == "manual-status"
    harness.product_repository.add_product.assert_not_called()
    assert identity.product_id == PRODUCT_ID
    assert identity.mapping_status == "confirmed"


def test_bootstrap_does_not_use_name_only_or_fuzzy_product_matching() -> None:
    identity, current, snapshot = _row(
        1,
        sku_code="SYNTHETIC-EXACT-ONLY",
        product_name="Same Display Name",
    )
    harness = _service([(identity, current, snapshot)])
    harness.product_repository.find_product_by_sku.return_value = None

    def add_product(product: Product) -> Product:
        product.id = PRODUCT_ID
        return product

    harness.product_repository.add_product.side_effect = add_product

    result = harness.service.execute("synthetic-account", authorized=True)

    assert result.created == 1
    harness.product_repository.find_product_by_sku.assert_called_once_with("SYNTHETIC-EXACT-ONLY")


def test_bootstrap_skips_missing_duplicate_and_deleted_cases() -> None:
    rows = [
        _row(1, sku_code=None, product_name="Synthetic"),
        _row(2, sku_code="SYNTHETIC-MISSING-NAME", product_name=None),
        _row(3, sku_code="SYNTHETIC-DUPLICATE", product_name="Synthetic A"),
        _row(4, sku_code="SYNTHETIC-DUPLICATE", product_name="Synthetic B"),
        _row(5, sku_code="SYNTHETIC-DELETED", product_name="Synthetic Deleted"),
    ]
    deleted = Product(
        id=PRODUCT_ID,
        sku="SYNTHETIC-DELETED",
        product_name="Deleted Product",
        deleted_at=NOW,
    )
    harness = _service(rows)
    harness.product_repository.find_product_by_sku.return_value = deleted

    result = harness.service.execute("synthetic-account", authorized=True)

    assert result.skipped_missing_sku_code == 1
    assert result.skipped_missing_product_name == 1
    assert result.skipped_duplicate_sku_code == 2
    assert result.skipped_existing_deleted_product == 1
    assert result.created == 0
    assert result.linked == 0
    harness.sku_repository.update_record.assert_not_called()


def test_bootstrap_dry_run_and_authorization_fail_closed_without_writes() -> None:
    harness = _service([_row(1, sku_code="SYNTHETIC-SKU", product_name="Synthetic")])
    harness.product_repository.find_product_by_sku.return_value = None

    plan = harness.service.plan("synthetic-account")

    assert plan.dry_run is True
    assert plan.would_create == 1
    harness.product_repository.add_product.assert_not_called()
    harness.sku_repository.update_record.assert_not_called()
    harness.session.commit.assert_not_called()
    with pytest.raises(ProductInfoProductBootstrapError, match="NOT_AUTHORIZED"):
        harness.service.execute("synthetic-account")


def test_bootstrap_product_is_visible_through_real_product_management_service(
    product_management_db_session: Session,
) -> None:
    identity, source_account_ref = _bootstrap_product_in_database(product_management_db_session)

    data, total, _, _ = ProductManagementService(product_management_db_session).list_skus(
        ProductManagementListQuery(),
        frozenset({source_account_ref}),
        include_costs=False,
    )

    assert total > 0
    assert [item.sku_id for item in data.items] == [identity.id]


def test_bootstrap_product_is_visible_through_real_product_management_route(
    product_management_db_session: Session,
) -> None:
    identity, source_account_ref = _bootstrap_product_in_database(product_management_db_session)
    application = create_app()
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user",
        permissions=frozenset({"products:read"}),
    )
    application.dependency_overrides[get_product_scope_provider] = lambda: (
        lambda _principal, _resource: True
    )
    application.dependency_overrides[get_source_account_scope_provider] = lambda: (
        lambda _principal: frozenset({source_account_ref})
    )
    application.dependency_overrides[get_db_session] = lambda: product_management_db_session

    client = TestClient(application)
    response = client.get("/api/product-management/skus")
    body = response.json()

    assert response.status_code == 200
    assert body["success"] is True
    assert body["meta"]["total"] > 0
    assert body["data"]["items"][0]["sku_id"] == str(identity.id)
    assert "images" not in body["data"]["items"][0]


def test_synced_identity_is_visible_without_product_bootstrap(
    product_management_db_session: Session,
) -> None:
    identity, source_account_ref = _add_unbootstrapped_identity(product_management_db_session)
    application = create_app()
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user",
        permissions=frozenset({"products:read"}),
    )
    application.dependency_overrides[get_product_scope_provider] = lambda: (
        lambda _principal, _resource: True
    )
    application.dependency_overrides[get_source_account_scope_provider] = lambda: (
        lambda _principal: frozenset({source_account_ref})
    )
    application.dependency_overrides[get_db_session] = lambda: product_management_db_session

    client = TestClient(application)
    response = client.get("/api/product-management/skus")
    body = response.json()
    summary = client.get("/api/product-management/skus/summary")

    assert response.status_code == 200
    assert body["meta"]["total"] == 1
    assert body["data"]["items"][0]["sku_id"] == str(identity.id)
    assert identity.product_id is None
    assert identity.mapping_status == "unmapped"
    assert summary.status_code == 200
    assert summary.json()["data"] == {
        "total": 1,
        "synced_detail_count": 1,
        "data_completeness_rate": "0.00",
        "with_image_count": 0,
        "with_source_tag_count": 0,
        "incomplete_count": 1,
        "missing_purchase_cost_count": 1,
        "missing_purchase_delivery_count": 1,
        "missing_gross_weight_count": 1,
        "missing_package_dimensions_count": 1,
        "missing_dimension_image_count": 1,
        "missing_image_count": 1,
        "invalid_pricing_rule_count": 0,
        "pricing_ok_count": 0,
    }
    detail = client.get(f"/api/product-management/skus/{identity.id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["images"] == []


def test_product_management_detail_returns_current_picture_list_images_in_order(
    product_management_db_session: Session,
) -> None:
    identity, source_account_ref = _add_unbootstrapped_identity(product_management_db_session)
    current = product_management_db_session.scalar(select(LingxingSkuProductInfoCurrent))
    assert current is not None
    product_management_db_session.add_all(
        [
            LingxingSkuProductImage(
                id=uuid4(),
                source_snapshot_id=current.source_snapshot_id,
                identity_id=identity.id,
                ordinal=1,
                pic_url="https://example.invalid/two.jpg",
                is_primary=False,
            ),
            LingxingSkuProductImage(
                id=uuid4(),
                source_snapshot_id=current.source_snapshot_id,
                identity_id=identity.id,
                ordinal=0,
                pic_url="https://example.invalid/one.jpg",
                is_primary=True,
            ),
        ]
    )
    product_management_db_session.commit()
    application = create_app()
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user",
        permissions=frozenset({"products:read"}),
    )
    application.dependency_overrides[get_product_scope_provider] = lambda: (
        lambda _principal, _resource: True
    )
    application.dependency_overrides[get_source_account_scope_provider] = lambda: (
        lambda _principal: frozenset({source_account_ref})
    )
    application.dependency_overrides[get_db_session] = lambda: product_management_db_session
    client = TestClient(application)

    detail = client.get(f"/api/product-management/skus/{identity.id}")
    listing = client.get("/api/product-management/skus")

    assert detail.status_code == 200
    assert detail.json()["data"]["images"] == [
        {
            "ordinal": 0,
            "url": "https://example.invalid/one.jpg",
            "thumbnail_url": None,
            "preview_url": None,
            "is_primary": True,
            "source": "picture_list",
        },
        {
            "ordinal": 1,
            "url": "https://example.invalid/two.jpg",
            "thumbnail_url": None,
            "preview_url": None,
            "is_primary": False,
            "source": "picture_list",
        },
    ]
    assert "images" not in listing.json()["data"]["items"][0]


def test_summary_counts_pricing_with_complete_inputs_even_without_images(
    product_management_db_session: Session,
) -> None:
    _, source_account_ref = _add_unbootstrapped_identity(product_management_db_session)
    current = product_management_db_session.scalar(select(LingxingSkuProductInfoCurrent))
    assert current is not None
    current.purchase_cost_cny = Decimal("20")
    current.product_gross_weight_g = Decimal("800")
    current.package_length_cm = Decimal("30.48")
    current.package_width_cm = Decimal("30.48")
    current.package_height_cm = Decimal("30.48")
    product_management_db_session.commit()
    application = create_app()
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user",
        permissions=frozenset({"products:read"}),
    )
    application.dependency_overrides[get_product_scope_provider] = lambda: (
        lambda _principal, _resource: True
    )
    application.dependency_overrides[get_source_account_scope_provider] = lambda: (
        lambda _principal: frozenset({source_account_ref})
    )
    application.dependency_overrides[get_db_session] = lambda: product_management_db_session

    response = TestClient(application).get("/api/product-management/skus/summary")

    assert response.status_code == 200
    assert response.json()["data"]["pricing_ok_count"] == 1
    assert response.json()["data"]["missing_dimension_image_count"] == 1


def test_one_time_runner_defaults_to_dry_run_and_requires_injected_executor() -> None:
    session = MagicMock(spec=Session)
    runner = ProductInfoOneTimeRunner(session)
    runner.repository = MagicMock()
    runner.bootstrap = MagicMock()
    runner.repository.list_active_lingxing_sku_ids.return_value = ["synthetic-id"]
    runner.bootstrap.plan.return_value = ProductInfoProductBootstrapResult(
        dry_run=True,
        candidates_evaluated=1,
        would_create=1,
        would_link=0,
        created=0,
        linked=0,
        skipped_missing_sku_code=0,
        skipped_missing_product_name=0,
        skipped_duplicate_sku_code=0,
        skipped_existing_deleted_product=0,
    )

    result = runner.run(source_account_ref="synthetic-account")

    assert result.dry_run is True
    assert result.work_items_planned == 1
    assert result.products_would_create == 1
    with pytest.raises(ProductInfoOneTimeRunError, match="OUTBOUND_NOT_AUTHORIZED"):
        runner.run(source_account_ref="synthetic-account", dry_run=False)


def test_one_time_runner_rejects_dwd_write_without_authorization() -> None:
    session = MagicMock(spec=Session)
    executor = MagicMock()
    runner = ProductInfoOneTimeRunner(session, executor=executor)
    runner.repository = MagicMock()
    runner.bootstrap = MagicMock()
    runner.repository.list_active_lingxing_sku_ids.return_value = ["synthetic-id"]

    with pytest.raises(ProductInfoOneTimeRunError, match="OUTBOUND_NOT_AUTHORIZED"):
        runner.run(source_account_ref="synthetic-account", dry_run=False)

    executor.execute.assert_not_called()
    runner.bootstrap.execute.assert_not_called()


def test_one_time_runner_allows_dwd_write_without_product_bootstrap() -> None:
    session = MagicMock(spec=Session)
    executor = MagicMock()
    executor.execute.return_value = ProductInfoSyncExecutionResult(1, 1, 1, 1, 1)
    runner = ProductInfoOneTimeRunner(session, executor=executor)
    runner.repository = MagicMock()
    runner.bootstrap = MagicMock()
    runner.repository.list_active_lingxing_sku_ids.return_value = ["synthetic-id"]
    authorization = True

    result = runner.run(
        source_account_ref="synthetic-account",
        dry_run=False,
        dwd_write_authorized=authorization,
    )

    assert result.snapshots_written == 1
    assert result.products_created == 0
    assert result.bootstrap_skipped_authorization is True
    executor.execute.assert_called_once()
    runner.bootstrap.execute.assert_not_called()


def test_one_time_runner_bootstraps_only_with_separate_authorization() -> None:
    session = MagicMock(spec=Session)
    executor = MagicMock()
    executor.execute.return_value = ProductInfoSyncExecutionResult(1, 1, 1, 1, 1)
    runner = ProductInfoOneTimeRunner(session, executor=executor)
    runner.repository = MagicMock()
    runner.bootstrap = MagicMock()
    runner.repository.list_active_lingxing_sku_ids.return_value = ["synthetic-id"]
    runner.bootstrap.execute.return_value = ProductInfoProductBootstrapResult(
        dry_run=False,
        candidates_evaluated=1,
        would_create=1,
        would_link=0,
        created=1,
        linked=0,
        skipped_missing_sku_code=0,
        skipped_missing_product_name=0,
        skipped_duplicate_sku_code=0,
        skipped_existing_deleted_product=0,
    )
    authorization = True

    result = runner.run(
        source_account_ref="synthetic-account",
        dry_run=False,
        dwd_write_authorized=authorization,
        product_bootstrap_authorized=authorization,
    )

    assert result.snapshots_written == 1
    assert result.products_created == 1
    assert result.bootstrap_skipped_authorization is False
    executor.execute.assert_called_once()
    runner.bootstrap.execute.assert_called_once_with(
        "synthetic-account",
        authorized=authorization,
    )


def test_offline_fixture_executor_parses_batch_and_publishes_each_snapshot() -> None:
    session = MagicMock(spec=Session)
    planned = LingxingBatchGetProductInfoSyncHandler().build_plan(
        run_id=UUID(int=500),
        source_account_ref="synthetic-account",
        lingxing_sku_ids=["synthetic-id-1", "synthetic-id-2"],
        batch_size=2,
    )
    fixture = ProductInfoFixtureBatch(
        work_item_id=planned.work_items[0].id,
        raw_request_ref_id=UUID(int=501),
        source_observed_at=NOW,
        parser_version="contract-v1",
        payload={
            "code": 0,
            "data": [
                {
                    "id": "synthetic-id-2",
                    "sku": "SYNTHETIC-B",
                    "product_name": "Synthetic B",
                },
                {
                    "id": "synthetic-id-1",
                    "sku": "SYNTHETIC-A",
                    "product_name": "Synthetic A",
                },
            ],
        },
    )
    executor = ProductInfoFixtureBatchExecutor(session, (fixture,))
    executor.publisher = MagicMock()

    result = executor.execute(source_account_ref="synthetic-account", plan=planned)

    assert result.records_seen == 2
    assert result.snapshots_written == 2
    assert executor.publisher.publish.call_count == 2

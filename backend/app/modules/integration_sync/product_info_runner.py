from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.db.model_registry import register_productlist_sync_models
from app.modules.integration_sync.handlers.lingxing_batch_product_info import (
    BatchPlan,
    LingxingBatchGetProductInfoSyncHandler,
)
from app.modules.integration_sync.parsers.lingxing_product_info import (
    parse_batch_product_info_fixture,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository
from app.modules.products.bootstrap import (
    ProductInfoProductBootstrapResult,
    ProductInfoProductBootstrapService,
)
from app.modules.sku_detail.publisher import SkuDetailPublicationService


class ProductInfoOneTimeRunError(RuntimeError):
    """Safe runner error containing no provider or product values."""


@dataclass(frozen=True, slots=True)
class ProductInfoSyncExecutionResult:
    work_items_succeeded: int
    records_seen: int
    snapshots_written: int
    images_written: int
    tags_written: int


class ProductInfoBatchExecutor(Protocol):
    def execute(
        self,
        *,
        source_account_ref: str,
        plan: BatchPlan,
    ) -> ProductInfoSyncExecutionResult: ...


@dataclass(frozen=True, slots=True)
class ProductInfoFixtureBatch:
    work_item_id: UUID
    raw_request_ref_id: UUID
    source_observed_at: datetime
    parser_version: str
    payload: object


class ProductInfoFixtureBatchExecutor:
    """Offline contract-fixture executor; it has no provider transport capability."""

    def __init__(self, session: Session, fixtures: tuple[ProductInfoFixtureBatch, ...]) -> None:
        self.publisher = SkuDetailPublicationService(session)
        self.fixtures = {fixture.work_item_id: fixture for fixture in fixtures}

    def execute(
        self,
        *,
        source_account_ref: str,
        plan: BatchPlan,
    ) -> ProductInfoSyncExecutionResult:
        if set(self.fixtures) != {item.id for item in plan.work_items}:
            raise ProductInfoOneTimeRunError("CONTRACT_FIELD_MISMATCH")
        memberships: dict[UUID, list[str]] = {}
        for item in plan.batch_items:
            memberships.setdefault(item.work_item_id, []).append(item.lingxing_sku_id)
        records_seen = 0
        snapshots_written = 0
        images_written = 0
        tags_written = 0
        for work_item in plan.work_items:
            fixture = self.fixtures[work_item.id]
            parsed_items = parse_batch_product_info_fixture(
                fixture.payload,
                expected_lingxing_sku_ids=tuple(memberships[work_item.id]),
            )
            for parsed_item in parsed_items:
                self.publisher.publish(
                    run_id=work_item.run_id,
                    raw_request_ref_id=fixture.raw_request_ref_id,
                    source_account_ref=source_account_ref,
                    lingxing_sku_id=parsed_item.lingxing_sku_id,
                    source_observed_at=fixture.source_observed_at,
                    parser_version=fixture.parser_version,
                    parsed=parsed_item.detail,
                )
                records_seen += 1
                snapshots_written += 1
                images_written += len(parsed_item.detail.images)
                tags_written += len(parsed_item.detail.tags)
        return ProductInfoSyncExecutionResult(
            work_items_succeeded=len(plan.work_items),
            records_seen=records_seen,
            snapshots_written=snapshots_written,
            images_written=images_written,
            tags_written=tags_written,
        )


@dataclass(frozen=True, slots=True)
class ProductInfoOneTimeRunResult:
    dry_run: bool
    bootstrap_skipped_authorization: bool
    active_identity_count: int
    work_items_planned: int
    work_items_succeeded: int
    records_seen: int
    snapshots_written: int
    images_written: int
    tags_written: int
    products_would_create: int
    products_would_link: int
    products_created: int
    products_linked: int
    skipped_missing_sku_code: int
    skipped_missing_product_name: int
    skipped_duplicate_sku_code: int
    skipped_existing_deleted_product: int


class ProductInfoOneTimeRunner:
    """Controlled orchestration with an injectable, separately approved transport executor."""

    def __init__(
        self,
        session: Session,
        *,
        executor: ProductInfoBatchExecutor | None = None,
    ) -> None:
        register_productlist_sync_models()
        self.repository = IntegrationSyncRepository(session)
        self.bootstrap = ProductInfoProductBootstrapService(session)
        self.executor = executor

    def run(
        self,
        *,
        source_account_ref: str,
        dry_run: bool = True,
        dwd_write_authorized: bool = False,
        product_bootstrap_authorized: bool = False,
        batch_size: int = 20,
    ) -> ProductInfoOneTimeRunResult:
        if not source_account_ref or source_account_ref != source_account_ref.strip():
            raise ProductInfoOneTimeRunError("PRODUCT_INFO_SOURCE_ACCOUNT_REF_INVALID")
        ids = self.repository.list_active_lingxing_sku_ids(source_account_ref)
        if not ids:
            raise ProductInfoOneTimeRunError("PRODUCT_INFO_IDENTITY_SET_EMPTY")
        plan = LingxingBatchGetProductInfoSyncHandler().build_plan(
            run_id=_planning_run_id(),
            source_account_ref=source_account_ref,
            lingxing_sku_ids=ids,
            batch_size=batch_size,
        )
        bootstrap: ProductInfoProductBootstrapResult | None
        if dry_run:
            execution = ProductInfoSyncExecutionResult(0, 0, 0, 0, 0)
            bootstrap = self.bootstrap.plan(source_account_ref)
        else:
            if not dwd_write_authorized or self.executor is None:
                raise ProductInfoOneTimeRunError("PRODUCT_INFO_OUTBOUND_NOT_AUTHORIZED")
            execution = self.executor.execute(
                source_account_ref=source_account_ref,
                plan=plan,
            )
            bootstrap = (
                self.bootstrap.execute(
                    source_account_ref,
                    authorized=product_bootstrap_authorized,
                )
                if product_bootstrap_authorized
                else None
            )
        return _result(
            len(ids),
            len(plan.work_items),
            execution,
            bootstrap,
            dry_run=dry_run,
            bootstrap_skipped_authorization=not dry_run and not product_bootstrap_authorized,
        )


def _planning_run_id() -> UUID:
    return uuid4()


def _result(
    active_identity_count: int,
    work_items_planned: int,
    execution: ProductInfoSyncExecutionResult,
    bootstrap: ProductInfoProductBootstrapResult | None,
    *,
    dry_run: bool,
    bootstrap_skipped_authorization: bool,
) -> ProductInfoOneTimeRunResult:
    bootstrap_counts = bootstrap or ProductInfoProductBootstrapResult(
        dry_run=dry_run,
        candidates_evaluated=0,
        would_create=0,
        would_link=0,
        created=0,
        linked=0,
        skipped_missing_sku_code=0,
        skipped_missing_product_name=0,
        skipped_duplicate_sku_code=0,
        skipped_existing_deleted_product=0,
    )
    return ProductInfoOneTimeRunResult(
        dry_run=dry_run,
        bootstrap_skipped_authorization=bootstrap_skipped_authorization,
        active_identity_count=active_identity_count,
        work_items_planned=work_items_planned,
        work_items_succeeded=execution.work_items_succeeded,
        records_seen=execution.records_seen,
        snapshots_written=execution.snapshots_written,
        images_written=execution.images_written,
        tags_written=execution.tags_written,
        products_would_create=bootstrap_counts.would_create,
        products_would_link=bootstrap_counts.would_link,
        products_created=bootstrap_counts.created,
        products_linked=bootstrap_counts.linked,
        skipped_missing_sku_code=bootstrap_counts.skipped_missing_sku_code,
        skipped_missing_product_name=bootstrap_counts.skipped_missing_product_name,
        skipped_duplicate_sku_code=bootstrap_counts.skipped_duplicate_sku_code,
        skipped_existing_deleted_product=bootstrap_counts.skipped_existing_deleted_product,
    )

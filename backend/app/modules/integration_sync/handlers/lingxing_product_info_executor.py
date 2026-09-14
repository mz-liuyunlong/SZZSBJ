from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol, cast
from uuid import UUID, uuid4

import httpx
from pydantic import JsonValue
from sqlalchemy.orm import Session

from app.core.config import AppEnvironment, get_settings
from app.integrations.lingxing.client import (
    LingxingEndpoint,
    LingxingRawEnvelope,
    LingxingReadonlyClient,
)
from app.integrations.lingxing.openapi import LingxingOpenApiClient, LingxingOpenApiError
from app.integrations.lingxing.security import canonical_json, redact_json
from app.integrations.lingxing.token_manager import LingxingTokenClient, LingxingTokenManager
from app.modules.integration_sync.handlers.lingxing_batch_product_info import BatchPlan
from app.modules.integration_sync.models import (
    ApiRawBlob,
    ApiRawRequestRef,
    IntegrationSyncRun,
    IntegrationSyncRunWorkItem,
    LingxingProductInfoBatchItem,
    RawRetentionPolicy,
    utc_now,
)
from app.modules.integration_sync.parsers.lingxing_product_info import (
    ProductInfoParseError,
    parse_batch_product_info_fixture,
)
from app.modules.integration_sync.product_info_runner import (
    ProductInfoOneTimeRunError,
    ProductInfoSyncExecutionResult,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository
from app.modules.sku_detail.publisher import (
    SkuDetailPublicationError,
    SkuDetailPublicationService,
)

PRODUCT_INFO_INTERFACE_ID = "LX-BB8D0DF598AF"
PRODUCT_INFO_ENDPOINT: LingxingEndpoint = "/erp/sc/routing/data/local_inventory/batchGetProductInfo"
PRODUCT_INFO_BATCH_SIZE = 20
PRODUCT_INFO_PARSER_VERSION = "v1"


class ProductInfoClient(Protocol):
    def fetch_batch_product_info(
        self,
        *,
        product_ids: tuple[str, ...],
        source_account_ref: str,
        run_id: str,
        work_item_id: str,
    ) -> LingxingRawEnvelope: ...


def product_info_response_succeeded(
    endpoint: LingxingEndpoint,
    response: httpx.Response,
    payload: JsonValue,
) -> bool:
    del response
    return (
        endpoint == PRODUCT_INFO_ENDPOINT
        and isinstance(payload, dict)
        and payload.get("code") == 0
        and isinstance(payload.get("data"), list)
    )


@contextmanager
def product_info_client() -> Iterator[LingxingReadonlyClient]:
    settings = get_settings()
    if settings.app_env is not AppEnvironment.PRODUCTION:
        raise ProductInfoOneTimeRunError("PRODUCT_INFO_SERVER_ENVIRONMENT_REQUIRED")
    token_client = LingxingTokenClient(settings)
    token_manager = LingxingTokenManager(token_client, settings)
    client = LingxingReadonlyClient(
        settings,
        token_provider=token_manager,
        success_evaluator=product_info_response_succeeded,
    )
    try:
        yield client
    finally:
        client.close()
        token_client.close()


class LingxingProductInfoExecutor:
    """Serial, one-attempt executor for the single owner-authorized ProductInfo endpoint."""

    def __init__(self, session: Session, *, client: ProductInfoClient) -> None:
        self.session = session
        self.client = client
        self.repository = IntegrationSyncRepository(session)
        self.publisher = SkuDetailPublicationService(session)
        self.request_builder = LingxingOpenApiClient()

    def execute(
        self,
        *,
        source_account_ref: str,
        plan: BatchPlan,
    ) -> ProductInfoSyncExecutionResult:
        if not isinstance(plan, BatchPlan):
            raise ProductInfoOneTimeRunError("CONTRACT_FIELD_MISMATCH")
        interface = self.repository.get_interface_by_key("lingxing", "batchGetProductInfo")
        policy = self.repository.get_retention_policy("lingxing-productlist-v1")
        contract = self.request_builder.registry.get(PRODUCT_INFO_INTERFACE_ID)
        if (
            interface is None
            or policy is None
            or contract is None
            or contract.method != "POST"
            or contract.api_path != PRODUCT_INFO_ENDPOINT
            or contract.token_bucket_capacity != 1
        ):
            raise ProductInfoOneTimeRunError("PRODUCT_INFO_GOVERNANCE_METADATA_MISSING")

        run = IntegrationSyncRun(
            id=plan.work_items[0].run_id,
            config_id=None,
            interface_id=interface.id,
            provider="lingxing",
            interface_key="batchGetProductInfo",
            source_account_ref=source_account_ref,
            trigger_type="manual",
            status="running",
            idempotency_key=f"product-info-once:{plan.work_items[0].run_id}",
            requested_by="product_info_one_time_runner",
            queued_at=utc_now(),
            started_at=utc_now(),
            work_items_total=len(plan.work_items),
            work_items_succeeded=0,
            work_items_failed=0,
            records_seen=0,
            records_written=0,
        )
        self.repository.add_run(run)
        self.repository.add_work_items(plan.work_items)
        self.repository.add_batch_items(plan.batch_items)
        self.session.commit()

        memberships: dict[UUID, list[LingxingProductInfoBatchItem]] = {}
        for item in plan.batch_items:
            memberships.setdefault(item.work_item_id, []).append(item)

        images_written = 0
        tags_written = 0
        records_seen = 0
        for work in plan.work_items:
            items = memberships[work.id]
            product_ids = tuple(item.lingxing_sku_id for item in items)
            try:
                request = self.request_builder.build_request(
                    PRODUCT_INFO_INTERFACE_ID,
                    {"productIds": list(product_ids)},
                )
                if tuple(request.parameters) != ("productIds",):
                    raise ProductInfoOneTimeRunError("CONTRACT_FIELD_MISMATCH")
                work.status = "running"
                work.started_at = utc_now()
                self.session.commit()
                envelope = self.client.fetch_batch_product_info(
                    product_ids=product_ids,
                    source_account_ref=source_account_ref,
                    run_id=str(run.id),
                    work_item_id=str(work.id),
                )
                raw_ref = self._persist_raw(run, work, policy, envelope)
                if not envelope.is_success or envelope.response_json is None:
                    raise ProductInfoOneTimeRunError(
                        envelope.error_code or "PRODUCT_INFO_PROVIDER_FAILED"
                    )
                parsed = parse_batch_product_info_fixture(
                    envelope.response_json,
                    expected_lingxing_sku_ids=product_ids,
                )
                for parsed_item in parsed:
                    self.publisher.publish(
                        run_id=run.id,
                        raw_request_ref_id=raw_ref.id,
                        source_account_ref=source_account_ref,
                        lingxing_sku_id=parsed_item.lingxing_sku_id,
                        source_observed_at=envelope.pulled_at,
                        parser_version=PRODUCT_INFO_PARSER_VERSION,
                        parsed=parsed_item.detail,
                    )
                    images_written += len(parsed_item.detail.images)
                    tags_written += len(parsed_item.detail.tags)
                for item in items:
                    item.raw_request_ref_id = raw_ref.id
                    item.item_status = "succeeded"
                work.status = "succeeded"
                work.response_count = len(parsed)
                work.finished_at = utc_now()
                run.work_items_succeeded += 1
                run.records_seen += len(parsed)
                run.records_written += len(parsed)
                records_seen += len(parsed)
                self.session.commit()
            except (
                LingxingOpenApiError,
                ProductInfoParseError,
                SkuDetailPublicationError,
                ProductInfoOneTimeRunError,
            ) as error:
                self._fail(run.id, work.id, _safe_error_code(error))
                raise ProductInfoOneTimeRunError(_safe_error_code(error)) from None
            except Exception:
                self._fail(run.id, work.id, "PRODUCT_INFO_EXECUTION_FAILED")
                raise ProductInfoOneTimeRunError("PRODUCT_INFO_EXECUTION_FAILED") from None

        run.status = "succeeded"
        run.finished_at = utc_now()
        self.session.commit()
        return ProductInfoSyncExecutionResult(
            work_items_succeeded=run.work_items_succeeded,
            records_seen=records_seen,
            snapshots_written=records_seen,
            images_written=images_written,
            tags_written=tags_written,
        )

    def _persist_raw(
        self,
        run: IntegrationSyncRun,
        work: IntegrationSyncRunWorkItem,
        policy: RawRetentionPolicy,
        envelope: LingxingRawEnvelope,
    ) -> ApiRawRequestRef:
        if envelope.response_json is None:
            raise ProductInfoOneTimeRunError(envelope.error_code or "PRODUCT_INFO_PROVIDER_FAILED")
        payload = redact_json(envelope.response_json)
        encoded = canonical_json(payload).encode("utf-8")
        response_hash = hashlib.sha256(encoded).hexdigest()
        blob = self.repository.find_blob_by_hash(response_hash)
        if blob is None:
            blob = self.repository.add_raw_blob(
                ApiRawBlob(
                    id=uuid4(),
                    response_hash=response_hash,
                    payload_json=payload,
                    payload_bytes=len(encoded),
                    content_type="application/json",
                    storage_mode="database",
                    retention_policy_id=policy.id,
                    received_at=envelope.pulled_at,
                )
            )
        response_count = _response_count(payload)
        raw_ref = self.repository.add_raw_request_ref(
            ApiRawRequestRef(
                id=uuid4(),
                run_id=run.id,
                work_item_id=work.id,
                raw_blob_id=blob.id,
                request_kind="id_batch_page",
                attempt_no=envelope.attempt_no,
                request_safe_params=work.request_safe_params,
                http_status=envelope.response_code,
                provider_code=_provider_code(payload),
                is_success=envelope.is_success,
                response_count=response_count,
                requested_at=work.started_at or envelope.pulled_at,
                received_at=envelope.pulled_at,
            )
        )
        work.attempt_count = envelope.attempt_no
        self.session.commit()
        return raw_ref

    def _fail(self, run_id: UUID, work_id: UUID, error_code: str) -> None:
        self.session.rollback()
        run = self.repository.get_run_for_update(run_id)
        work = self.repository.get_work_item_for_update(run_id, work_id)
        if run is None or work is None:
            raise ProductInfoOneTimeRunError("PRODUCT_INFO_FAILURE_STATE_WRITE_FAILED")
        now = utc_now()
        work.status = "failed"
        work.error_code = error_code
        work.error_message = "ProductInfo sync failed"
        work.finished_at = now
        run.status = "failed"
        run.work_items_failed += 1
        run.error_code = error_code
        run.error_message = "ProductInfo sync failed"
        run.finished_at = now
        self.session.commit()


def _provider_code(payload: JsonValue) -> str | None:
    if not isinstance(payload, dict):
        return None
    code = payload.get("code")
    if isinstance(code, bool) or not isinstance(code, (str, int)):
        return None
    return str(code)


def _response_count(payload: JsonValue) -> int | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return None
    return len(cast(list[JsonValue], payload["data"]))


def _safe_error_code(error: Exception) -> str:
    if isinstance(error, LingxingOpenApiError):
        return error.code
    code = str(error)
    return code if code.isupper() and len(code) <= 128 else "PRODUCT_INFO_EXECUTION_FAILED"

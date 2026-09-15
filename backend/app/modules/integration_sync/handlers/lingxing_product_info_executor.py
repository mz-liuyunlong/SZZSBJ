from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
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
from app.modules.integration_sync.handlers.lingxing_batch_product_info import (
    BatchPlan,
    ordered_id_hash,
)
from app.modules.integration_sync.models import (
    ApiRawBlob,
    ApiRawRequestRef,
    IntegrationInterface,
    IntegrationSyncRun,
    IntegrationSyncRunEvent,
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


class ProductInfoAnomalyError(ProductInfoOneTimeRunError):
    # Terminal frozen-plan/provider-contract anomaly with no source values.

    def __init__(self, code: str, work_item_id: UUID | None) -> None:
        super().__init__(code)
        self.code = code
        self.work_item_id = work_item_id


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
    """Execute a persisted frozen ProductInfo plan serially."""

    def __init__(
        self,
        session: Session,
        *,
        client: ProductInfoClient,
        heartbeat: Callable[[], None] | None = None,
    ) -> None:
        self.session = session
        self.client = client
        self.heartbeat = heartbeat or (lambda: None)
        self.repository = IntegrationSyncRepository(session)
        self.publisher = SkuDetailPublicationService(session)
        self.request_builder = LingxingOpenApiClient()

    def execute(
        self,
        *,
        source_account_ref: str,
        plan: BatchPlan,
    ) -> ProductInfoSyncExecutionResult:
        """Backward-compatible controlled one-time execution."""
        interface, policy = self._governance()
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
        return self._execute_persisted(run=run, plan=plan, policy=policy)

    def execute_existing_run(
        self,
        *,
        run: IntegrationSyncRun,
        plan: BatchPlan,
    ) -> ProductInfoSyncExecutionResult:
        """Execute an existing governance run without creating a second run."""
        interface, policy = self._governance()
        if (
            run.provider != "lingxing"
            or run.interface_key != "batchGetProductInfo"
            or run.interface_id != interface.id
            or run.status != "running"
        ):
            raise ProductInfoOneTimeRunError("CONTRACT_FIELD_MISMATCH")
        return self._execute_persisted(run=run, plan=plan, policy=policy)

    def _governance(self) -> tuple[IntegrationInterface, RawRetentionPolicy]:
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
        return interface, policy

    def _execute_persisted(
        self,
        *,
        run: IntegrationSyncRun,
        plan: BatchPlan,
        policy: RawRetentionPolicy,
    ) -> ProductInfoSyncExecutionResult:
        try:
            memberships = self._validated_memberships(run, plan)
        except ProductInfoAnomalyError as error:
            self._trip_anomaly_breaker(run.id, error.work_item_id, error.code)
            raise ProductInfoOneTimeRunError(error.code) from None

        max_attempts = self.repository.max_attempts_for_run(run)
        if not 1 <= max_attempts <= 10:
            raise ProductInfoOneTimeRunError("PRODUCT_INFO_MAX_ATTEMPTS_INVALID")

        images_written = 0
        tags_written = 0
        first_failure_code: str | None = None

        for work in plan.work_items:
            if work.status == "succeeded":
                continue
            if work.status != "queued":
                raise ProductInfoOneTimeRunError("PRODUCT_INFO_FROZEN_PLAN_NOT_EXECUTABLE")

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
                if work.started_at is None:
                    work.started_at = utc_now()
                self.session.commit()

                attempt_succeeded = False
                while work.attempt_count < max_attempts:
                    attempt_no = work.attempt_count + 1
                    self.heartbeat()
                    try:
                        envelope = self.client.fetch_batch_product_info(
                            product_ids=product_ids,
                            source_account_ref=run.source_account_ref,
                            run_id=str(run.id),
                            work_item_id=str(work.id),
                        )
                    except Exception:
                        work.attempt_count = attempt_no
                        self.session.commit()
                        if attempt_no < max_attempts:
                            continue
                        raise ProductInfoOneTimeRunError("PRODUCT_INFO_TRANSPORT_FAILED") from None

                    raw_ref: ApiRawRequestRef | None = None
                    if envelope.response_json is not None:
                        raw_ref = self._persist_raw(
                            run,
                            work,
                            policy,
                            envelope,
                            attempt_no=attempt_no,
                        )
                    else:
                        work.attempt_count = attempt_no
                        self.session.commit()

                    if not envelope.is_success or envelope.response_json is None:
                        error_code = envelope.error_code or "PRODUCT_INFO_PROVIDER_FAILED"
                        if _is_retryable_response(envelope) and attempt_no < max_attempts:
                            continue
                        raise ProductInfoOneTimeRunError(error_code)

                    if raw_ref is None:
                        raise ProductInfoOneTimeRunError("PRODUCT_INFO_RAW_REF_MISSING")

                    parsed = parse_batch_product_info_fixture(
                        envelope.response_json,
                        expected_lingxing_sku_ids=product_ids,
                    )
                    work.response_count = len(parsed)
                    run.records_seen += len(parsed)
                    self.session.commit()

                    items_by_id = {item.lingxing_sku_id: item for item in items}
                    for parsed_item in parsed:
                        self.heartbeat()
                        publication = self.publisher.publish_with_result(
                            run_id=run.id,
                            raw_request_ref_id=raw_ref.id,
                            source_account_ref=run.source_account_ref,
                            lingxing_sku_id=parsed_item.lingxing_sku_id,
                            source_observed_at=envelope.pulled_at,
                            parser_version=PRODUCT_INFO_PARSER_VERSION,
                            parsed=parsed_item.detail,
                        )
                        batch_item = items_by_id[parsed_item.lingxing_sku_id]
                        batch_item.raw_request_ref_id = raw_ref.id
                        batch_item.item_status = "succeeded"
                        batch_item.updated_at = utc_now()
                        if publication.status == "changed":
                            run.records_written += 1
                        images_written += publication.images_written
                        tags_written += publication.tags_written
                        # Publisher commits the normalized record itself. Persist the
                        # matching per-SKU evidence/counters immediately so a later
                        # item failure cannot erase already completed work.
                        self.session.commit()

                    work.status = "succeeded"
                    work.finished_at = utc_now()
                    run.work_items_succeeded += 1
                    self.session.commit()
                    attempt_succeeded = True
                    break

                if not attempt_succeeded:
                    raise ProductInfoOneTimeRunError("PRODUCT_INFO_MAX_ATTEMPTS_EXHAUSTED")
            except (
                LingxingOpenApiError,
                ProductInfoParseError,
                SkuDetailPublicationError,
            ) as error:
                error_code = _safe_error_code(error)
                self._trip_anomaly_breaker(run.id, work.id, error_code)
                raise ProductInfoOneTimeRunError(error_code) from None
            except ProductInfoOneTimeRunError as error:
                error_code = _safe_error_code(error)
                if _is_terminal_anomaly_code(error_code):
                    self._trip_anomaly_breaker(run.id, work.id, error_code)
                    raise ProductInfoOneTimeRunError(error_code) from None
                run = self._mark_work_failed(run.id, work.id, error_code)
                if first_failure_code is None:
                    first_failure_code = error_code
                continue
            except Exception:
                error_code = "PRODUCT_INFO_EXECUTION_FAILED"
                run = self._mark_work_failed(run.id, work.id, error_code)
                if first_failure_code is None:
                    first_failure_code = error_code
                continue

        run.finished_at = utc_now()
        if run.work_items_failed:
            run.status = "failed"
            run.error_code = first_failure_code or "PRODUCT_INFO_PARTIAL_FAILURE"
            run.error_message = "ProductInfo sync completed with failed batches"
        else:
            run.status = "succeeded"
            run.error_code = None
            run.error_message = None
        self.session.commit()

        if run.status == "failed":
            raise ProductInfoOneTimeRunError(run.error_code or "PRODUCT_INFO_PARTIAL_FAILURE")

        return ProductInfoSyncExecutionResult(
            work_items_succeeded=run.work_items_succeeded,
            records_seen=run.records_seen,
            snapshots_written=run.records_written,
            images_written=images_written,
            tags_written=tags_written,
        )

    def _validated_memberships(
        self,
        run: IntegrationSyncRun,
        plan: BatchPlan,
    ) -> dict[UUID, list[LingxingProductInfoBatchItem]]:
        if not plan.work_items or not plan.batch_items:
            raise ProductInfoAnomalyError("CONTRACT_FIELD_MISMATCH", None)

        work_by_id = {work.id: work for work in plan.work_items}
        if len(work_by_id) != len(plan.work_items):
            raise ProductInfoAnomalyError("CONTRACT_FIELD_MISMATCH", None)

        memberships: dict[UUID, list[LingxingProductInfoBatchItem]] = {}
        for item in plan.batch_items:
            work = work_by_id.get(item.work_item_id)
            if (
                work is None
                or item.run_id != run.id
                or item.source_account_ref != run.source_account_ref
                or item.batch_no != work.batch_no
            ):
                raise ProductInfoAnomalyError(
                    "CONTRACT_FIELD_MISMATCH",
                    item.work_item_id if work is not None else None,
                )
            memberships.setdefault(item.work_item_id, []).append(item)

        for work in plan.work_items:
            if (
                work.run_id != run.id
                or work.request_kind != "id_batch_page"
                or work.batch_no is None
                or work.id_count is None
                or work.id_hash is None
            ):
                raise ProductInfoAnomalyError("CONTRACT_FIELD_MISMATCH", work.id)

            items = sorted(memberships.get(work.id, []), key=lambda item: item.item_ordinal)
            if len(items) != work.id_count or [item.item_ordinal for item in items] != list(
                range(len(items))
            ):
                raise ProductInfoAnomalyError("CONTRACT_FIELD_MISMATCH", work.id)

            product_ids = [item.lingxing_sku_id for item in items]
            if (
                len(set(product_ids)) != len(product_ids)
                or ordered_id_hash(product_ids) != work.id_hash
            ):
                raise ProductInfoAnomalyError("CONTRACT_FIELD_MISMATCH", work.id)
            memberships[work.id] = items

        return memberships

    def _persist_raw(
        self,
        run: IntegrationSyncRun,
        work: IntegrationSyncRunWorkItem,
        policy: RawRetentionPolicy,
        envelope: LingxingRawEnvelope,
        *,
        attempt_no: int,
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
                attempt_no=attempt_no,
                request_safe_params=work.request_safe_params,
                http_status=envelope.response_code,
                provider_code=_provider_code(payload),
                is_success=envelope.is_success,
                response_count=response_count,
                requested_at=work.started_at or envelope.pulled_at,
                received_at=envelope.pulled_at,
            )
        )
        work.attempt_count = attempt_no
        self.session.commit()
        return raw_ref

    def _trip_anomaly_breaker(
        self,
        run_id: UUID,
        work_id: UUID | None,
        error_code: str,
    ) -> None:
        # Fail the anomalous batch and cancel every unstarted batch.
        self.session.rollback()
        run = self.repository.get_run_for_update(run_id)
        if run is None:
            raise ProductInfoOneTimeRunError("PRODUCT_INFO_FAILURE_STATE_WRITE_FAILED")

        work_items = self.repository.list_work_items_for_run_for_update(run_id)
        if not work_items and work_id is not None:
            fallback = self.repository.get_work_item_for_update(run_id, work_id)
            if fallback is not None:
                work_items = [fallback]

        current = next((item for item in work_items if item.id == work_id), None)
        if current is None:
            current = next(
                (item for item in work_items if item.status in {"running", "queued"}), None
            )

        now = utc_now()
        failed_work_id: UUID | None = None
        if current is not None:
            failed_work_id = current.id
            if current.status != "failed":
                current.status = "failed"
                current.error_code = error_code
                current.error_message = "ProductInfo anomaly detected"
                current.finished_at = now
                run.work_items_failed += 1

        canceled_work_ids: set[UUID] = set()
        for item in work_items:
            if item.id == failed_work_id:
                continue
            if item.status == "queued":
                item.status = "canceled"
                item.error_code = "PRODUCT_INFO_ANOMALY_BREAKER"
                item.error_message = "Canceled after ProductInfo anomaly"
                item.finished_at = now
                canceled_work_ids.add(item.id)

        batch_items = self.repository.list_batch_items_for_run_for_update(run_id)
        for batch_item in batch_items:
            if batch_item.work_item_id == failed_work_id and batch_item.item_status in {
                "queued",
                "running",
            }:
                batch_item.item_status = "failed"
                batch_item.updated_at = now
            elif (
                batch_item.work_item_id in canceled_work_ids and batch_item.item_status == "queued"
            ):
                batch_item.item_status = "canceled"
                batch_item.updated_at = now

        run.status = "failed"
        run.error_code = "PRODUCT_INFO_ANOMALY_BREAKER_TRIPPED"
        run.error_message = "ProductInfo anomaly detected"
        run.finished_at = now
        self.repository.add_event(
            IntegrationSyncRunEvent(
                run_id=run.id,
                sequence_no=self.repository.next_event_sequence(run.id),
                event_type="anomaly_breaker",
                from_status="running",
                to_status="failed",
                message_code="PRODUCT_INFO_ANOMALY_BREAKER_TRIPPED",
                safe_details={
                    "error_code": error_code,
                    "canceled_work_items": len(canceled_work_ids),
                },
                occurred_at=now,
                actor_ref="worker",
            )
        )
        self.session.commit()

    def _mark_work_failed(
        self,
        run_id: UUID,
        work_id: UUID,
        error_code: str,
    ) -> IntegrationSyncRun:
        """Fail one batch without preventing later frozen batches from executing."""
        self.session.rollback()
        run = self.repository.get_run_for_update(run_id)
        work = self.repository.get_work_item_for_update(run_id, work_id)
        if run is None or work is None:
            raise ProductInfoOneTimeRunError("PRODUCT_INFO_FAILURE_STATE_WRITE_FAILED")

        now = utc_now()
        if work.status != "failed":
            work.status = "failed"
            work.error_code = error_code
            work.error_message = "ProductInfo sync failed"
            work.finished_at = now
            run.work_items_failed += 1

        for batch_item in self.repository.list_batch_items_for_run_for_update(run_id):
            if batch_item.work_item_id != work_id or batch_item.item_status == "succeeded":
                continue
            batch_item.item_status = "failed"
            batch_item.updated_at = now

        self.session.commit()
        return run


def _is_terminal_anomaly_code(error_code: str) -> bool:
    return error_code in {
        "CONTRACT_FIELD_MISMATCH",
        "PRODUCT_INFO_FROZEN_PLAN_INVALID",
        "PRODUCT_INFO_RAW_REF_MISSING",
    }


def _is_retryable_response(envelope: LingxingRawEnvelope) -> bool:
    if envelope.error_code == "AUTH_ERROR":
        return True
    return (
        envelope.error_code == "HTTP_ERROR"
        and envelope.response_code is not None
        and envelope.response_code >= 500
    )


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

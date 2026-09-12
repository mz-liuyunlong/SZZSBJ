from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

import httpx
from pydantic import JsonValue
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import AppEnvironment, get_settings
from app.integrations.lingxing.client import (
    LingxingEndpoint,
    LingxingRawEnvelope,
    LingxingReadonlyClient,
)
from app.integrations.lingxing.security import canonical_json, redact_json
from app.integrations.lingxing.token_manager import LingxingTokenClient, LingxingTokenManager
from app.modules.integration_sync.models import (
    ApiRawBlob,
    ApiRawRequestRef,
    IntegrationInterface,
    IntegrationSyncConfig,
    IntegrationSyncRun,
    IntegrationSyncRunWorkItem,
    LingxingProductListSkuRef,
    RawRetentionPolicy,
    utc_now,
)
from app.modules.integration_sync.parsers.lingxing_product_list import (
    ProductListParseError,
    inspect_productlist_sku_ids,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository
from app.modules.sku_detail.models import LingxingSkuIdentity

PRODUCT_LIST_ENDPOINT: LingxingEndpoint = "/erp/sc/routing/data/local_inventory/productList"
PRODUCT_LIST_HANDLER_KEY = "lingxing.product_list_sync.v1"
MAX_PRODUCT_LIST_PAGE_SIZE = 1000
DEFAULT_PRODUCT_LIST_PAGE_SIZE = 1000
DEFAULT_PRODUCT_LIST_MAX_PAGES = 10000

logger = logging.getLogger("app.integration_sync.product_list")


class ProductListPageClient(Protocol):
    def fetch_product_list_page(
        self,
        *,
        offset: int,
        length: int,
        page_no: int,
        source_account_ref: str,
        run_id: str,
        work_item_id: str,
    ) -> LingxingRawEnvelope: ...


class ProductListSyncError(RuntimeError):
    """Safe execution error that never contains source or credential values."""


@dataclass(frozen=True, slots=True)
class ProductListSyncResult:
    run_id: UUID
    status: str
    total_captured: int
    work_items_count: int
    duplicate_ids_detected: int
    inactive_ids_count: int


def product_list_response_succeeded(
    endpoint: LingxingEndpoint,
    response: httpx.Response,
    payload: JsonValue,
) -> bool:
    del response
    return (
        endpoint == PRODUCT_LIST_ENDPOINT
        and _provider_code(payload) == "0"
        and _response_data(payload) is not None
    )


@contextmanager
def product_list_client() -> Iterator[LingxingReadonlyClient]:
    settings = get_settings()
    if settings.app_env is not AppEnvironment.PRODUCTION:
        raise ProductListSyncError("SYNC_PRODUCTLIST_SERVER_ENVIRONMENT_REQUIRED")
    token_client = LingxingTokenClient(settings)
    token_manager = LingxingTokenManager(token_client, settings)
    client = LingxingReadonlyClient(
        settings,
        token_provider=token_manager,
        success_evaluator=product_list_response_succeeded,
    )
    try:
        yield client
    finally:
        client.close()
        token_client.close()


class LingxingProductListSyncHandler:
    handler_key = PRODUCT_LIST_HANDLER_KEY
    request_kind = "offset_page"

    def __init__(self, session: Session, *, client: ProductListPageClient | None = None) -> None:
        self.session = session
        self.repository = IntegrationSyncRepository(session)
        self._client = client

    def execute(
        self,
        run: IntegrationSyncRun,
        interface: IntegrationInterface,
    ) -> ProductListSyncResult:
        try:
            config, policy = self._preflight(run, interface)
        except ProductListSyncError as error:
            return self._fail_run(run, None, str(error))
        page_size = config.page_size or DEFAULT_PRODUCT_LIST_PAGE_SIZE
        max_pages = config.max_pages or DEFAULT_PRODUCT_LIST_MAX_PAGES
        if page_size > MAX_PRODUCT_LIST_PAGE_SIZE:
            return self._fail_run(run, None, "SYNC_PRODUCTLIST_PAGE_SIZE_INVALID")
        if self._client is None:
            try:
                app_env = get_settings().app_env
            except Exception:
                return self._fail_run(run, None, "SYNC_PRODUCTLIST_CONFIG_INVALID")
            if app_env is not AppEnvironment.PRODUCTION:
                return self._fail_run(
                    run,
                    None,
                    "SYNC_PRODUCTLIST_SERVER_ENVIRONMENT_REQUIRED",
                )
        try:
            run.status = "running"
            run.started_at = utc_now()
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            recovered = self.repository.get_run_for_update(run.id)
            if recovered is None:
                raise ProductListSyncError("SYNC_PRODUCTLIST_RUN_MISSING") from None
            return self._fail_run(recovered, None, "SYNC_PRODUCTLIST_ALREADY_RUNNING")

        if self._client is not None:
            return self._execute_pages(run, self._client, policy, page_size, max_pages)
        with product_list_client() as client:
            return self._execute_pages(run, client, policy, page_size, max_pages)

    def _preflight(
        self,
        run: IntegrationSyncRun,
        interface: IntegrationInterface,
    ) -> tuple[IntegrationSyncConfig, RawRetentionPolicy]:
        if (
            run.trigger_type != "manual"
            or run.provider != "lingxing"
            or run.interface_key != "productList"
            or interface.provider != "lingxing"
            or interface.interface_key != "productList"
            or interface.method != "POST"
            or interface.endpoint_path != PRODUCT_LIST_ENDPOINT
            or not interface.outbound_enabled
            or run.config_id is None
        ):
            raise ProductListSyncError("SYNC_PRODUCTLIST_EXECUTION_NOT_AUTHORIZED")
        config = self.repository.get_config(run.config_id, frozenset({run.source_account_ref}))
        policy = self.repository.get_retention_policy("lingxing-productlist-v1")
        if config is None or policy is None:
            raise ProductListSyncError("SYNC_PRODUCTLIST_METADATA_MISSING")
        if not config.is_enabled or config.schedule_enabled:
            raise ProductListSyncError("SYNC_PRODUCTLIST_MANUAL_ONLY")
        return config, policy

    def _execute_pages(
        self,
        run: IntegrationSyncRun,
        client: ProductListPageClient,
        policy: RawRetentionPolicy,
        page_size: int,
        max_pages: int,
    ) -> ProductListSyncResult:
        observed_ids: set[str] = set()
        expected_total: int | None = None
        offset = 0
        current_work: IntegrationSyncRunWorkItem | None = None
        try:
            for page_no in range(1, max_pages + 1):
                work = current_work = self._start_work_item(run, page_no, offset, page_size)
                try:
                    envelope = client.fetch_product_list_page(
                        offset=offset,
                        length=page_size,
                        page_no=page_no,
                        source_account_ref=run.source_account_ref,
                        run_id=str(run.id),
                        work_item_id=str(work.id),
                    )
                except Exception:
                    return self._fail_run(run, work, "SYNC_PRODUCTLIST_TRANSPORT_FAILED")
                if envelope.response_json is not None:
                    self._persist_raw_response(run, work, policy, envelope)
                else:
                    work.attempt_count = envelope.attempt_no
                if not envelope.is_success or envelope.response_json is None:
                    return self._fail_run(
                        run,
                        work,
                        envelope.error_code or "SYNC_PRODUCTLIST_RESPONSE_FAILED",
                    )
                try:
                    inspected = inspect_productlist_sku_ids(envelope.response_json)
                except ProductListParseError:
                    return self._fail_run(run, work, "SYNC_PRODUCTLIST_PARSE_FAILED")
                repeated = len(observed_ids.intersection(inspected.values))
                duplicate_count = inspected.duplicate_count + repeated
                if duplicate_count:
                    return self._fail_run(
                        run,
                        work,
                        "SYNC_PRODUCTLIST_DUPLICATE_ID",
                        duplicate_count=duplicate_count,
                    )
                provider_total = _provider_total(envelope.response_json)
                if provider_total is not None:
                    if expected_total is None:
                        expected_total = provider_total
                    elif provider_total != expected_total:
                        return self._fail_run(run, work, "SYNC_PRODUCTLIST_TOTAL_CHANGED")
                projected_count = offset + inspected.response_count
                if expected_total is not None and projected_count > expected_total:
                    return self._fail_run(run, work, "SYNC_PRODUCTLIST_TOTAL_MISMATCH")
                self._publish_page(run, work, envelope.pulled_at, inspected.values)
                observed_ids.update(inspected.values)
                offset = projected_count
                logger.info(
                    "productlist_page_succeeded run_id=%s work_item_id=%s page_no=%s "
                    "response_count=%s response_hash=%s",
                    run.id,
                    work.id,
                    page_no,
                    inspected.response_count,
                    _response_hash(envelope.response_json),
                )
                if inspected.response_count == 0:
                    if expected_total is not None and offset < expected_total:
                        return self._fail_run(run, work, "SYNC_PRODUCTLIST_TOTAL_MISMATCH")
                    return self._succeed(run, observed_ids)
                if expected_total is not None and offset == expected_total:
                    return self._succeed(run, observed_ids)
                if expected_total is None and inspected.response_count < page_size:
                    return self._succeed(run, observed_ids)
            return self._fail_run(run, None, "SYNC_PRODUCTLIST_MAX_PAGES_REACHED")
        except ProductListSyncError as error:
            self.session.rollback()
            return self._fail_run(run, current_work, str(error))
        except Exception:
            self.session.rollback()
            try:
                recovered = self.repository.get_run_for_update(run.id)
                if recovered is not None and recovered.status == "running":
                    self._fail_run(recovered, None, "SYNC_PRODUCTLIST_EXECUTION_FAILED")
            except Exception:
                self.session.rollback()
            raise ProductListSyncError("SYNC_PRODUCTLIST_EXECUTION_FAILED") from None

    def _start_work_item(
        self,
        run: IntegrationSyncRun,
        page_no: int,
        offset: int,
        length: int,
    ) -> IntegrationSyncRunWorkItem:
        now = utc_now()
        work = IntegrationSyncRunWorkItem(
            id=uuid4(),
            run_id=run.id,
            ordinal=page_no,
            request_kind="offset_page",
            status="running",
            attempt_count=0,
            offset_value=offset,
            length_value=length,
            request_safe_params={"offset": offset, "length": length},
            started_at=now,
        )
        self.repository.add_work_items([work])
        run.work_items_total += 1
        self.session.commit()
        return work

    def _persist_raw_response(
        self,
        run: IntegrationSyncRun,
        work: IntegrationSyncRunWorkItem,
        policy: RawRetentionPolicy,
        envelope: LingxingRawEnvelope,
    ) -> None:
        payload = redact_json(envelope.response_json)
        response_hash = _response_hash(payload)
        encoded = canonical_json(payload).encode("utf-8")
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
        self.repository.add_raw_request_ref(
            ApiRawRequestRef(
                id=uuid4(),
                run_id=run.id,
                work_item_id=work.id,
                raw_blob_id=blob.id,
                request_kind="offset_page",
                attempt_no=envelope.attempt_no,
                request_safe_params={
                    "offset": work.offset_value,
                    "length": work.length_value,
                },
                http_status=envelope.response_code,
                provider_code=_provider_code(payload),
                is_success=envelope.is_success,
                response_count=response_count,
                requested_at=work.started_at or envelope.pulled_at,
                received_at=envelope.pulled_at,
            )
        )
        work.attempt_count = envelope.attempt_no
        work.response_count = response_count
        run.records_seen += response_count or 0
        self.session.commit()

    def _publish_page(
        self,
        run: IntegrationSyncRun,
        work: IntegrationSyncRunWorkItem,
        observed_at: datetime,
        sku_ids: tuple[str, ...],
    ) -> None:
        raw_ref = self.repository.get_raw_request_ref_for_work_item(work.id)
        if raw_ref is None:
            raise ProductListSyncError("SYNC_PRODUCTLIST_RAW_REF_MISSING")
        refs: list[LingxingProductListSkuRef] = []
        for ordinal, sku_id in enumerate(sku_ids):
            refs.append(
                LingxingProductListSkuRef(
                    id=uuid4(),
                    run_id=run.id,
                    raw_request_ref_id=raw_ref.id,
                    source_account_ref=run.source_account_ref,
                    lingxing_sku_id=sku_id,
                    source_item_ordinal=ordinal,
                    observed_at=observed_at,
                )
            )
            identity = self.repository.get_lingxing_identity(run.source_account_ref, sku_id)
            if identity is None:
                self.repository.add_identity(
                    LingxingSkuIdentity(
                        id=uuid4(),
                        provider="lingxing",
                        source_account_ref=run.source_account_ref,
                        lingxing_sku_id=sku_id,
                        mapping_status="unmapped",
                        is_active=True,
                        first_seen_run_id=run.id,
                        last_seen_run_id=run.id,
                        first_seen_at=observed_at,
                        last_seen_at=observed_at,
                    )
                )
            else:
                identity.is_active = True
                identity.last_seen_run_id = run.id
                identity.last_seen_at = observed_at
                identity.inactive_at = None
        self.repository.add_productlist_refs(refs)
        work.status = "succeeded"
        work.finished_at = utc_now()
        run.work_items_succeeded += 1
        run.records_written += len(sku_ids)
        self.session.commit()

    def _succeed(
        self,
        run: IntegrationSyncRun,
        observed_ids: set[str],
    ) -> ProductListSyncResult:
        inactive_count = self.repository.deactivate_absent_identities(
            source_account_ref=run.source_account_ref,
            observed_ids=observed_ids,
            run_id=run.id,
            inactive_at=utc_now(),
        )
        run.status = "succeeded"
        run.finished_at = utc_now()
        self.session.commit()
        logger.info(
            "productlist_sync_succeeded run_id=%s pages=%s total_captured=%s inactive_ids_count=%s",
            run.id,
            run.work_items_succeeded,
            run.records_seen,
            inactive_count,
        )
        return ProductListSyncResult(
            run_id=run.id,
            status=run.status,
            total_captured=run.records_seen,
            work_items_count=run.work_items_total,
            duplicate_ids_detected=0,
            inactive_ids_count=inactive_count,
        )

    def _fail_run(
        self,
        run: IntegrationSyncRun,
        work: IntegrationSyncRunWorkItem | None,
        error_code: str,
        *,
        duplicate_count: int = 0,
    ) -> ProductListSyncResult:
        now = utc_now()
        if work is not None:
            work.status = "failed"
            work.error_code = error_code
            work.error_message = (
                f"duplicate_ids_detected={duplicate_count}"
                if duplicate_count
                else "ProductList sync failed"
            )
            work.finished_at = now
            run.work_items_failed += 1
        run.status = "failed"
        run.error_code = error_code
        run.error_message = (
            f"duplicate_ids_detected={duplicate_count}"
            if duplicate_count
            else "ProductList sync failed"
        )
        run.finished_at = now
        self.session.commit()
        logger.warning(
            "productlist_sync_failed run_id=%s error_code=%s duplicate_ids_detected=%s",
            run.id,
            error_code,
            duplicate_count,
        )
        return ProductListSyncResult(
            run_id=run.id,
            status=run.status,
            total_captured=run.records_seen,
            work_items_count=run.work_items_total,
            duplicate_ids_detected=duplicate_count,
            inactive_ids_count=0,
        )


def _response_data(payload: JsonValue) -> list[JsonValue] | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, list):
        return data
    nested = payload.get("productList")
    if isinstance(nested, dict):
        nested_data = nested.get("data")
        if isinstance(nested_data, list):
            return nested_data
    return None


def _response_count(payload: JsonValue) -> int | None:
    data = _response_data(payload)
    return len(data) if data is not None else None


def _provider_code(payload: JsonValue) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("code")
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    return str(value).strip()[:64]


def _provider_total(payload: JsonValue) -> int | None:
    if not isinstance(payload, dict):
        return None
    container: object = payload
    if "total" not in payload:
        container = payload.get("productList")
    if not isinstance(container, dict):
        return None
    value = container.get("total")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _response_hash(payload: JsonValue) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

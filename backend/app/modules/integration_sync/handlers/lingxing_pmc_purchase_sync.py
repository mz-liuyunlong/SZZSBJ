"""Governed sync handlers for the three PMC purchase feeds (Gate 2, PR-D).

One handler class parameterised by the static ``PmcPurchaseSyncInterfaceSpec``; three
thin subclasses expose the handler keys the catalog registered. The page loop, work
item bookkeeping, raw blob / request-ref persistence and failure handling mirror
``lingxing_product_list_sync.py``; additions are the bounded date window carried on the
run, header + line ODS rows, ``gov_parse_jobs`` / ``gov_data_lineage`` rows per page and
an informational quality report.

Preflight refuses anything but a manual run on an outbound-enabled interface whose
config is enabled and not scheduled, with a window of at most 90 days.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import AppEnvironment, get_settings
from app.db.model_registry import register_productlist_sync_models
from app.integrations.lingxing.client import LingxingRawEnvelope, LingxingReadonlyClient
from app.integrations.lingxing.pmc_purchase_contracts import (
    PMC_PURCHASE_MAX_WINDOW_DAYS,
    PmcPurchaseContractError,
    pmc_purchase_provider_code,
    pmc_purchase_response_items,
    pmc_purchase_response_succeeded,
    validate_pmc_purchase_window,
)
from app.integrations.lingxing.security import canonical_json, redact_json
from app.integrations.lingxing.token_manager import LingxingTokenClient, LingxingTokenManager
from app.modules.integration_sync.models import (
    ApiRawBlob,
    ApiRawRequestRef,
    DataLineage,
    IntegrationInterface,
    IntegrationSyncConfig,
    IntegrationSyncRun,
    IntegrationSyncRunWorkItem,
    ParseJob,
    RawRetentionPolicy,
    utc_now,
)
from app.modules.integration_sync.parsers.lingxing_purchase import (
    PARSER_KEYS,
    PARSER_VERSION,
    ParsedHeader,
    PurchasePageParse,
    PurchaseParseError,
    PurchaseQualityReport,
    parse_purchase_page,
)
from app.modules.integration_sync.pmc_purchase_catalog import (
    PMC_PURCHASE_SPECS_BY_INTERFACE_KEY,
    PmcPurchaseSyncInterfaceSpec,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository
from app.modules.pmc_purchase.models import (
    LingxingPurchaseOrderItemOds,
    LingxingPurchaseOrderOds,
    LingxingPurchasePlanOds,
    LingxingReceiptOrderItemOds,
    LingxingReceiptOrderOds,
)

logger = logging.getLogger("app.integration_sync.pmc_purchase")

PmcPurchaseOdsRow = (
    LingxingPurchasePlanOds
    | LingxingPurchaseOrderOds
    | LingxingPurchaseOrderItemOds
    | LingxingReceiptOrderOds
    | LingxingReceiptOrderItemOds
)

DEFAULT_MAX_PAGES = 1000
# Provider time dimension used for the window per endpoint (Rocky 2026-09-21):
# plans and orders by creation time, receipts by receive time. Values are checked
# against ``PmcPurchaseEndpointSpec.date_dimension_values`` before any request.
# History: the first production run (2026-09-21, run 99cc1354) failed with
# PROVIDER_ERROR because plans were sent ``create_time`` — the provider spells it
# ``creator_time`` for this endpoint only. Receipts previously sent no ``date_type``,
# which the provider answers with an empty result instead of an error.
WINDOW_DIMENSION: dict[str, str | int] = {
    "purchasePlanList": "creator_time",
    "purchaseOrderList": "create_time",
    "purchaseReceiptOrderList": 2,
}
HEADER_MODELS: dict[
    str, tuple[type[PmcPurchaseOdsRow], type[PmcPurchaseOdsRow] | None, str, str | None]
] = {
    "purchasePlanList": (LingxingPurchasePlanOds, None, "plan_sn", None),
    "purchaseOrderList": (
        LingxingPurchaseOrderOds,
        LingxingPurchaseOrderItemOds,
        "order_sn",
        "item_id",
    ),
    "purchaseReceiptOrderList": (
        LingxingReceiptOrderOds,
        LingxingReceiptOrderItemOds,
        "order_sn",
        "line_ordinal",
    ),
}


class PmcPurchasePageClient(Protocol):
    def fetch_pmc_purchase_page(
        self,
        *,
        api_path: str,
        offset: int,
        length: int,
        page_no: int,
        start_date: date,
        end_date: date,
        source_account_ref: str,
        run_id: str,
        work_item_id: str,
        date_dimension: str | int | None = None,
        extra: JsonValue = None,
    ) -> LingxingRawEnvelope: ...


class PmcPurchaseSyncError(RuntimeError):
    """Safe execution error that never contains source or credential values."""


@dataclass(frozen=True, slots=True)
class PmcPurchaseSyncResult:
    run_id: UUID
    interface_key: str
    status: str
    total_captured: int
    headers_written: int
    lines_written: int
    work_items_count: int
    duplicates_skipped: int
    quality: PurchaseQualityReport


@contextmanager
def pmc_purchase_client() -> Iterator[LingxingReadonlyClient]:
    settings = get_settings()
    if settings.app_env is not AppEnvironment.PRODUCTION:
        raise PmcPurchaseSyncError("SYNC_PURCHASE_SERVER_ENVIRONMENT_REQUIRED")
    token_client = LingxingTokenClient(settings)
    token_manager = LingxingTokenManager(token_client, settings)
    client = LingxingReadonlyClient(
        settings,
        token_provider=token_manager,
        success_evaluator=pmc_purchase_response_succeeded,
    )
    try:
        yield client
    finally:
        client.close()
        token_client.close()


class LingxingPmcPurchaseSyncHandler:
    """Base handler; subclasses bind ``spec`` and ``handler_key``."""

    spec: PmcPurchaseSyncInterfaceSpec
    handler_key: str
    request_kind = "offset_page"

    def __init__(self, session: Session, *, client: PmcPurchasePageClient | None = None) -> None:
        register_productlist_sync_models()
        self.session = session
        self.repository = IntegrationSyncRepository(session)
        self._client = client

    # --- entry ------------------------------------------------------------------------

    def execute(
        self,
        run: IntegrationSyncRun,
        interface: IntegrationInterface,
    ) -> PmcPurchaseSyncResult:
        try:
            config, policy, window = self._preflight(run, interface)
        except PmcPurchaseSyncError as error:
            return self._fail_run(run, None, str(error))
        page_size = config.page_size or self.spec.default_page_size
        max_pages = config.max_pages or DEFAULT_MAX_PAGES
        if not 1 <= page_size <= self.spec.default_page_size:
            return self._fail_run(run, None, "SYNC_PURCHASE_PAGE_SIZE_INVALID")
        if self._client is None:
            try:
                app_env = get_settings().app_env
            except Exception:
                return self._fail_run(run, None, "SYNC_PURCHASE_CONFIG_INVALID")
            if app_env is not AppEnvironment.PRODUCTION:
                return self._fail_run(run, None, "SYNC_PURCHASE_SERVER_ENVIRONMENT_REQUIRED")
        try:
            run.status = "running"
            run.started_at = utc_now()
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            recovered = self.repository.get_run_for_update(run.id)
            if recovered is None:
                raise PmcPurchaseSyncError("SYNC_PURCHASE_RUN_MISSING") from None
            return self._fail_run(recovered, None, "SYNC_PURCHASE_ALREADY_RUNNING")

        if self._client is not None:
            return self._execute_pages(run, self._client, policy, window, page_size, max_pages)
        with pmc_purchase_client() as client:
            return self._execute_pages(run, client, policy, window, page_size, max_pages)

    def _preflight(
        self,
        run: IntegrationSyncRun,
        interface: IntegrationInterface,
    ) -> tuple[IntegrationSyncConfig, RawRetentionPolicy, tuple[date, date]]:
        spec = self.spec
        if (
            run.trigger_type != "manual"
            or run.provider != "lingxing"
            or run.interface_key != spec.interface_key
            or interface.provider != "lingxing"
            or interface.interface_key != spec.interface_key
            or interface.method != "POST"
            or interface.endpoint_path != spec.endpoint_path
            or interface.handler_key != spec.handler_key
            or not interface.outbound_enabled
            or run.config_id is None
        ):
            raise PmcPurchaseSyncError("SYNC_PURCHASE_EXECUTION_NOT_AUTHORIZED")
        config = self.repository.get_config(run.config_id, frozenset({run.source_account_ref}))
        policy = self.repository.get_retention_policy(spec.retention_policy_key)
        if config is None or policy is None:
            raise PmcPurchaseSyncError("SYNC_PURCHASE_METADATA_MISSING")
        if not config.is_enabled or config.schedule_enabled:
            raise PmcPurchaseSyncError("SYNC_PURCHASE_MANUAL_ONLY")
        if run.window_start is None or run.window_end is None:
            raise PmcPurchaseSyncError("SYNC_PURCHASE_WINDOW_REQUIRED")
        window = (run.window_start.date(), run.window_end.date())
        try:
            validate_pmc_purchase_window(*window)
        except PmcPurchaseContractError:
            raise PmcPurchaseSyncError("SYNC_PURCHASE_WINDOW_INVALID") from None
        return config, policy, window

    # --- page loop --------------------------------------------------------------------

    def _execute_pages(
        self,
        run: IntegrationSyncRun,
        client: PmcPurchasePageClient,
        policy: RawRetentionPolicy,
        window: tuple[date, date],
        page_size: int,
        max_pages: int,
    ) -> PmcPurchaseSyncResult:
        seen_keys: set[str] = set()
        totals = _Totals()
        expected_total: int | None = None
        offset = 0
        run_id = run.id
        current_work_id: UUID | None = None
        try:
            for page_no in range(1, max_pages + 1):
                work = self._start_work_item(run, page_no, offset, page_size, window)
                current_work_id = work.id
                try:
                    envelope = client.fetch_pmc_purchase_page(
                        api_path=self.spec.endpoint_path,
                        offset=offset,
                        length=page_size,
                        page_no=page_no,
                        start_date=window[0],
                        end_date=window[1],
                        source_account_ref=run.source_account_ref,
                        run_id=str(run.id),
                        work_item_id=str(work.id),
                        date_dimension=WINDOW_DIMENSION[self.spec.interface_key],
                    )
                except Exception:
                    return self._fail_run(run, work, "SYNC_PURCHASE_TRANSPORT_FAILED")
                if envelope.response_json is not None:
                    self._persist_raw_response(run, work, policy, envelope)
                else:
                    work.attempt_count = envelope.attempt_no
                if not envelope.is_success or envelope.response_json is None:
                    return self._fail_run(
                        run, work, envelope.error_code or "SYNC_PURCHASE_RESPONSE_FAILED"
                    )
                try:
                    parsed = parse_purchase_page(self.spec.endpoint_path, envelope.response_json)
                except PurchaseParseError as error:
                    return self._fail_run(run, work, error.code)
                if self.spec.returns_total and parsed.provider_total is not None:
                    if expected_total is None:
                        expected_total = parsed.provider_total
                    elif parsed.provider_total != expected_total:
                        return self._fail_run(run, work, "SYNC_PURCHASE_TOTAL_CHANGED")
                projected = offset + parsed.response_count
                if expected_total is not None and projected > expected_total:
                    return self._fail_run(run, work, "SYNC_PURCHASE_TOTAL_MISMATCH")
                try:
                    written = self._publish_page(run, work, envelope.pulled_at, parsed, seen_keys)
                except PmcPurchaseSyncError as error:
                    self.session.rollback()
                    return self._recover_and_fail(run_id, current_work_id, str(error))
                except Exception:
                    self.session.rollback()
                    return self._recover_and_fail(
                        run_id, current_work_id, "SYNC_PURCHASE_PUBLISH_FAILED"
                    )
                totals.add(written, parsed.quality)
                offset = projected
                logger.info(
                    "pmc_purchase_page_succeeded interface=%s run_id=%s work_item_id=%s "
                    "page_no=%s response_count=%s headers=%s lines=%s response_hash=%s",
                    self.spec.interface_key,
                    run.id,
                    work.id,
                    page_no,
                    parsed.response_count,
                    written.headers,
                    written.lines,
                    _response_hash(envelope.response_json),
                )
                if parsed.response_count == 0:
                    if expected_total is not None and offset < expected_total:
                        return self._fail_run(run, work, "SYNC_PURCHASE_TOTAL_MISMATCH")
                    return self._succeed(run, totals)
                if expected_total is not None and offset == expected_total:
                    return self._succeed(run, totals)
                if expected_total is None and parsed.response_count < page_size:
                    return self._succeed(run, totals)
            return self._fail_run(run, None, "SYNC_PURCHASE_MAX_PAGES_REACHED")
        except PmcPurchaseSyncError as error:
            self.session.rollback()
            return self._recover_and_fail(run_id, current_work_id, str(error))
        except Exception:
            self.session.rollback()
            return self._recover_and_fail(run_id, current_work_id, "SYNC_PURCHASE_EXECUTION_FAILED")

    # --- persistence ------------------------------------------------------------------

    def _start_work_item(
        self,
        run: IntegrationSyncRun,
        page_no: int,
        offset: int,
        length: int,
        window: tuple[date, date],
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
            request_safe_params={
                "offset": offset,
                "length": length,
                "start_date": window[0].isoformat(),
                "end_date": window[1].isoformat(),
            },
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
        items = pmc_purchase_response_items(self.spec.endpoint_path, payload)
        response_count = len(items) if items is not None else None
        self.repository.add_raw_request_ref(
            ApiRawRequestRef(
                id=uuid4(),
                run_id=run.id,
                work_item_id=work.id,
                raw_blob_id=blob.id,
                request_kind="offset_page",
                attempt_no=envelope.attempt_no,
                request_safe_params=work.request_safe_params,
                http_status=envelope.response_code,
                provider_code=pmc_purchase_provider_code(payload),
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
        parsed: PurchasePageParse,
        seen_keys: set[str],
    ) -> _Written:
        raw_ref = self.repository.get_raw_request_ref_for_work_item(work.id)
        if raw_ref is None:
            raise PmcPurchaseSyncError("SYNC_PURCHASE_RAW_REF_MISSING")
        header_model, line_model, header_key, line_key = HEADER_MODELS[self.spec.interface_key]
        now = utc_now()
        parse_job = ParseJob(
            id=uuid4(),
            run_id=run.id,
            raw_request_ref_id=raw_ref.id,
            parser_key=PARSER_KEYS[self.spec.endpoint_path],
            parser_version=PARSER_VERSION,
            target_layer="DWD",
            status="running",
            records_seen=parsed.response_count,
            records_written=0,
            records_rejected=0,
            started_at=now,
        )
        rows: list[object] = []
        lineage: list[DataLineage] = []
        written = _Written()
        for ordinal, header in enumerate(parsed.headers):
            if header.business_key in seen_keys:
                written.duplicates += 1
                continue
            seen_keys.add(header.business_key)
            header_row = header_model(
                id=uuid4(),
                run_id=run.id,
                raw_request_ref_id=raw_ref.id,
                source_account_ref=run.source_account_ref,
                source_item_ordinal=ordinal,
                observed_at=observed_at,
                **header.columns,
            )
            rows.append(header_row)
            written.headers += 1
            lineage.append(
                self._lineage(run, parse_job, raw_ref, header, header_model, header_row, header_key)
            )
            if line_model is None or line_key is None:
                continue
            for line in header.lines:
                line_row = line_model(
                    id=uuid4(),
                    run_id=run.id,
                    raw_request_ref_id=raw_ref.id,
                    source_account_ref=run.source_account_ref,
                    source_item_ordinal=ordinal,
                    observed_at=observed_at,
                    **line.columns,
                )
                rows.append(line_row)
                written.lines += 1
                lineage.append(
                    self._lineage(run, parse_job, raw_ref, line, line_model, line_row, line_key)
                )
        parse_job.records_written = written.headers + written.lines
        parse_job.records_rejected = written.duplicates
        parse_job.status = "succeeded"
        parse_job.finished_at = utc_now()
        try:
            self.repository.add_parse_job(parse_job)
            self.repository.add_ods_records(rows)
            self.repository.add_lineage(lineage)
        except Exception:
            raise PmcPurchaseSyncError("SYNC_PURCHASE_ODS_PUBLISH_FAILED") from None
        work.status = "succeeded"
        work.finished_at = utc_now()
        run.work_items_succeeded += 1
        run.records_written += written.headers + written.lines
        self.session.commit()
        return written

    def _lineage(
        self,
        run: IntegrationSyncRun,
        parse_job: ParseJob,
        raw_ref: ApiRawRequestRef,
        source: ParsedHeader | _LineLike,
        model: type[PmcPurchaseOdsRow],
        row: PmcPurchaseOdsRow,
        key_field: str,
    ) -> DataLineage:
        return DataLineage(
            id=uuid4(),
            run_id=run.id,
            parse_job_id=parse_job.id,
            raw_request_ref_id=raw_ref.id,
            raw_blob_id=raw_ref.raw_blob_id,
            source_path=source.source_path,
            target_table=model.__tablename__,
            target_record_id=str(row.id),
            target_field=key_field,
            transform_key=PARSER_KEYS[self.spec.endpoint_path],
            transform_version=PARSER_VERSION,
        )

    # --- terminal states --------------------------------------------------------------

    def _succeed(self, run: IntegrationSyncRun, totals: _Totals) -> PmcPurchaseSyncResult:
        run.status = "succeeded"
        run.finished_at = utc_now()
        run.error_message = f"quality {totals.quality.as_message()}"
        self.session.commit()
        logger.info(
            "pmc_purchase_sync_succeeded interface=%s run_id=%s pages=%s headers=%s lines=%s "
            "duplicates_skipped=%s %s",
            self.spec.interface_key,
            run.id,
            run.work_items_succeeded,
            totals.headers,
            totals.lines,
            totals.duplicates,
            totals.quality.as_message(),
        )
        return PmcPurchaseSyncResult(
            run_id=run.id,
            interface_key=self.spec.interface_key,
            status=run.status,
            total_captured=run.records_seen,
            headers_written=totals.headers,
            lines_written=totals.lines,
            work_items_count=run.work_items_total,
            duplicates_skipped=totals.duplicates,
            quality=totals.quality,
        )

    def _recover_and_fail(
        self,
        run_id: UUID,
        work_item_id: UUID | None,
        error_code: str,
    ) -> PmcPurchaseSyncResult:
        try:
            run = self.repository.get_run_for_update(run_id)
            if run is None:
                raise PmcPurchaseSyncError("SYNC_PURCHASE_RUN_MISSING")
            work = (
                self.repository.get_work_item_for_update(run_id, work_item_id)
                if work_item_id is not None
                else None
            )
            return self._fail_run(run, work, error_code)
        except PmcPurchaseSyncError:
            raise
        except Exception:
            self.session.rollback()
            raise PmcPurchaseSyncError("SYNC_PURCHASE_FAILURE_STATE_WRITE_FAILED") from None

    def _fail_run(
        self,
        run: IntegrationSyncRun,
        work: IntegrationSyncRunWorkItem | None,
        error_code: str,
    ) -> PmcPurchaseSyncResult:
        now = utc_now()
        if work is not None and work.status == "running":
            work.status = "failed"
            work.error_code = error_code
            work.error_message = "PMC purchase sync failed"
            work.finished_at = now
            run.work_items_failed += 1
        run.status = "failed"
        run.error_code = error_code
        run.error_message = "PMC purchase sync failed"
        run.finished_at = now
        self.session.commit()
        logger.warning(
            "pmc_purchase_sync_failed interface=%s run_id=%s error_code=%s",
            self.spec.interface_key,
            run.id,
            error_code,
        )
        return PmcPurchaseSyncResult(
            run_id=run.id,
            interface_key=self.spec.interface_key,
            status=run.status,
            total_captured=run.records_seen,
            headers_written=0,
            lines_written=0,
            work_items_count=run.work_items_total,
            duplicates_skipped=0,
            quality=PurchaseQualityReport(),
        )


class _LineLike(Protocol):
    @property
    def source_path(self) -> str: ...


@dataclass(slots=True)
class _Written:
    headers: int = 0
    lines: int = 0
    duplicates: int = 0


@dataclass(slots=True)
class _Totals:
    headers: int = 0
    lines: int = 0
    duplicates: int = 0
    quality: PurchaseQualityReport = PurchaseQualityReport()

    def add(self, written: _Written, quality: PurchaseQualityReport) -> None:
        self.headers += written.headers
        self.lines += written.lines
        self.duplicates += written.duplicates
        self.quality = self.quality.merged(quality)


def _response_hash(payload: JsonValue) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class LingxingPurchasePlanListSyncHandler(LingxingPmcPurchaseSyncHandler):
    spec = PMC_PURCHASE_SPECS_BY_INTERFACE_KEY["purchasePlanList"]
    handler_key = spec.handler_key


class LingxingPurchaseOrderListSyncHandler(LingxingPmcPurchaseSyncHandler):
    spec = PMC_PURCHASE_SPECS_BY_INTERFACE_KEY["purchaseOrderList"]
    handler_key = spec.handler_key


class LingxingPurchaseReceiptOrderListSyncHandler(LingxingPmcPurchaseSyncHandler):
    spec = PMC_PURCHASE_SPECS_BY_INTERFACE_KEY["purchaseReceiptOrderList"]
    handler_key = spec.handler_key


PMC_PURCHASE_HANDLERS: dict[str, type[LingxingPmcPurchaseSyncHandler]] = {
    handler.spec.interface_key: handler
    for handler in (
        LingxingPurchasePlanListSyncHandler,
        LingxingPurchaseOrderListSyncHandler,
        LingxingPurchaseReceiptOrderListSyncHandler,
    )
}

__all__ = [
    "PMC_PURCHASE_HANDLERS",
    "PMC_PURCHASE_MAX_WINDOW_DAYS",
    "LingxingPmcPurchaseSyncHandler",
    "LingxingPurchaseOrderListSyncHandler",
    "LingxingPurchasePlanListSyncHandler",
    "LingxingPurchaseReceiptOrderListSyncHandler",
    "PmcPurchasePageClient",
    "PmcPurchaseSyncError",
    "PmcPurchaseSyncResult",
    "pmc_purchase_client",
]

"""Governed sync handlers for the WFS shipment-board Lingxing feeds (read-only).

Mirrors the domestic warehouse handler: manual runs only, one offset page per work item,
RAW response persisted before any structured write, append-only ODS with lineage, and a
hard stop on any inconsistency (total changed, incomplete page, duplicate identity).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from time import sleep
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import AppEnvironment, get_settings
from app.db.model_registry import register_productlist_sync_models
from app.integrations.lingxing.client import LingxingRawEnvelope, LingxingReadonlyClient
from app.integrations.lingxing.pmc_wfs_contracts import (
    PmcWfsContractError,
    pmc_wfs_provider_code,
    pmc_wfs_response_items,
    pmc_wfs_response_succeeded,
    validate_pmc_wfs_window,
)
from app.integrations.lingxing.security import canonical_json, redact_json
from app.integrations.lingxing.token_manager import get_shared_lingxing_token_manager
from app.modules.integration_sync.models import (
    ApiRawBlob,
    ApiRawRequestRef,
    DataLineage,
    IntegrationInterface,
    IntegrationSyncConfig,
    IntegrationSyncRun,
    IntegrationSyncRunWorkItem,
    RawRetentionPolicy,
    utc_now,
)
from app.modules.integration_sync.parsers.lingxing_wfs_board import (
    PARSER_KEYS,
    PARSER_VERSION,
    WfsBoardParseError,
    WfsPageParse,
    parse_wfs_page,
)
from app.modules.integration_sync.pmc_wfs_catalog import (
    PMC_WFS_SPECS_BY_INTERFACE_KEY,
    PmcWfsSyncInterfaceSpec,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository
from app.modules.pmc_wfs.lingxing_models import (
    LingxingWfsCargoGoodsOds,
    LingxingWfsCargoOds,
    LingxingWfsShippingListOds,
)

logger = logging.getLogger("app.integration_sync.pmc_wfs")

DEFAULT_MAX_PAGES = 200
# The provider token bucket is shared with every other Lingxing feed; pace page requests.
PAGE_GAP_SECONDS = 1.25

ODS_MODELS: dict[str, tuple[type[LingxingWfsCargoOds] | type[LingxingWfsShippingListOds], str]] = {
    "wfsCargoPage": (LingxingWfsCargoOds, "cargo_id"),
    "wfsShippingListPage": (LingxingWfsShippingListOds, "shipping_code"),
}


class PmcWfsPageClient(Protocol):
    def fetch_pmc_wfs_page(
        self,
        *,
        api_path: str,
        offset: int,
        length: int,
        page_no: int,
        start_date: date | None,
        end_date: date | None,
        extra: dict[str, JsonValue] | None,
        source_account_ref: str,
        run_id: str,
        work_item_id: str,
    ) -> LingxingRawEnvelope: ...


class PmcWfsSyncError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PmcWfsSyncResult:
    run_id: UUID
    interface_key: str
    status: str
    records_written: int
    duplicates_skipped: int


@contextmanager
def pmc_wfs_client() -> Iterator[LingxingReadonlyClient]:
    settings = get_settings()
    # Production, or an owner-run local dev database with the real-call gate opened on
    # purpose; test environments never get a live client.
    if settings.app_env not in {AppEnvironment.PRODUCTION, AppEnvironment.LOCAL}:
        raise PmcWfsSyncError("SYNC_WFS_SERVER_ENVIRONMENT_REQUIRED")
    token_manager = get_shared_lingxing_token_manager(settings)
    client = LingxingReadonlyClient(
        settings,
        token_provider=token_manager,
        success_evaluator=pmc_wfs_response_succeeded,
    )
    try:
        yield client
    finally:
        client.close()


class LingxingPmcWfsBoardSyncHandler:
    spec: PmcWfsSyncInterfaceSpec
    handler_key: str

    def __init__(
        self,
        session: Session,
        *,
        client: PmcWfsPageClient | None = None,
        page_gap_seconds: float = PAGE_GAP_SECONDS,
    ) -> None:
        register_productlist_sync_models()
        self.session = session
        self.repository = IntegrationSyncRepository(session)
        self._client = client
        self._page_gap_seconds = page_gap_seconds

    def execute(self, run: IntegrationSyncRun, interface: IntegrationInterface) -> PmcWfsSyncResult:
        try:
            config, policy, window = self._preflight(run, interface)
        except PmcWfsSyncError as error:
            return self._fail_run(run, None, str(error))
        page_size = config.page_size or self.spec.default_page_size
        max_pages = config.max_pages or DEFAULT_MAX_PAGES
        if not 1 <= page_size <= self.spec.default_page_size:
            return self._fail_run(run, None, "SYNC_WFS_PAGE_SIZE_INVALID")
        try:
            run.status = "running"
            run.started_at = utc_now()
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            recovered = self.repository.get_run_for_update(run.id)
            if recovered is None:
                raise PmcWfsSyncError("SYNC_WFS_RUN_MISSING") from None
            return self._fail_run(recovered, None, "SYNC_WFS_ALREADY_RUNNING")
        if self._client is not None:
            return self._execute_pages(run, self._client, policy, window, page_size, max_pages)
        with pmc_wfs_client() as client:
            return self._execute_pages(run, client, policy, window, page_size, max_pages)

    def _preflight(
        self, run: IntegrationSyncRun, interface: IntegrationInterface
    ) -> tuple[IntegrationSyncConfig, RawRetentionPolicy, tuple[date, date]]:
        spec = self.spec
        if (
            run.trigger_type != "manual"
            or run.provider != "lingxing"
            or run.interface_key != spec.interface_key
            or interface.handler_key != spec.handler_key
            or not interface.outbound_enabled
            or run.config_id is None
        ):
            raise PmcWfsSyncError("SYNC_WFS_EXECUTION_NOT_AUTHORIZED")
        config = self.repository.get_config(run.config_id, frozenset({run.source_account_ref}))
        policy = self.repository.get_retention_policy(spec.retention_policy_key)
        if config is None or policy is None or not config.is_enabled or config.schedule_enabled:
            raise PmcWfsSyncError("SYNC_WFS_MANUAL_ONLY")
        if run.window_start is None or run.window_end is None:
            raise PmcWfsSyncError("SYNC_WFS_WINDOW_REQUIRED")
        window = (run.window_start.date(), run.window_end.date())
        try:
            validate_pmc_wfs_window(*window)
        except PmcWfsContractError:
            raise PmcWfsSyncError("SYNC_WFS_WINDOW_INVALID") from None
        return config, policy, window

    def _execute_pages(
        self,
        run: IntegrationSyncRun,
        client: PmcWfsPageClient,
        policy: RawRetentionPolicy,
        window: tuple[date, date],
        page_size: int,
        max_pages: int,
    ) -> PmcWfsSyncResult:
        seen_keys: set[str] = set()
        written_total = 0
        duplicates = 0
        expected_total: int | None = None
        offset = 0
        run_id = run.id
        current_work_id: UUID | None = None
        try:
            for page_no in range(1, max_pages + 1):
                work = self._start_work_item(run, page_no, offset, page_size, window)
                current_work_id = work.id
                if page_no > 1 and self._page_gap_seconds > 0:
                    sleep(self._page_gap_seconds)
                try:
                    envelope = client.fetch_pmc_wfs_page(
                        api_path=self.spec.endpoint_path,
                        offset=offset,
                        length=page_size,
                        page_no=page_no,
                        start_date=window[0],
                        end_date=window[1],
                        extra=None,
                        source_account_ref=run.source_account_ref,
                        run_id=str(run.id),
                        work_item_id=str(work.id),
                    )
                except Exception:
                    return self._fail_run(run, work, "SYNC_WFS_TRANSPORT_FAILED")
                if envelope.response_json is not None:
                    self._persist_raw_response(run, work, policy, envelope)
                else:
                    work.attempt_count = envelope.attempt_no
                if not envelope.is_success or envelope.response_json is None:
                    return self._fail_run(
                        run, work, envelope.error_code or "SYNC_WFS_RESPONSE_FAILED"
                    )
                try:
                    parsed = parse_wfs_page(self.spec.endpoint_path, envelope.response_json)
                except WfsBoardParseError as error:
                    return self._fail_run(run, work, error.code)
                if parsed.provider_total is None:
                    return self._fail_run(run, work, "SYNC_WFS_TOTAL_REQUIRED")
                if expected_total is None:
                    expected_total = parsed.provider_total
                elif parsed.provider_total != expected_total:
                    return self._fail_run(run, work, "SYNC_WFS_TOTAL_CHANGED")
                projected = offset + parsed.response_count
                if projected > expected_total:
                    return self._fail_run(run, work, "SYNC_WFS_TOTAL_MISMATCH")
                if parsed.response_count < page_size and projected < expected_total:
                    return self._fail_run(run, work, "SYNC_WFS_INCOMPLETE_PAGE")
                try:
                    written, dup = self._publish_page(
                        run, work, envelope.pulled_at, parsed, seen_keys
                    )
                except PmcWfsSyncError as error:
                    self.session.rollback()
                    return self._recover_and_fail(run_id, current_work_id, str(error))
                except Exception:
                    self.session.rollback()
                    return self._recover_and_fail(
                        run_id, current_work_id, "SYNC_WFS_PUBLISH_FAILED"
                    )
                written_total += written
                duplicates += dup
                offset = projected
                if offset >= expected_total or parsed.response_count == 0:
                    return self._succeed(run, written_total, duplicates)
            return self._fail_run(run, None, "SYNC_WFS_MAX_PAGES_REACHED")
        except PmcWfsSyncError as error:
            self.session.rollback()
            return self._recover_and_fail(run_id, current_work_id, str(error))

    def _start_work_item(
        self,
        run: IntegrationSyncRun,
        page_no: int,
        offset: int,
        length: int,
        window: tuple[date, date],
    ) -> IntegrationSyncRunWorkItem:
        params: dict[str, object] = {
            "offset": offset,
            "length": length,
            "start_time": window[0].isoformat(),
            "end_time": window[1].isoformat(),
        }
        work = IntegrationSyncRunWorkItem(
            id=uuid4(),
            run_id=run.id,
            ordinal=page_no,
            request_kind="offset_page",
            status="running",
            attempt_count=0,
            offset_value=offset,
            length_value=length,
            request_safe_params=params,
            started_at=utc_now(),
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
        items = pmc_wfs_response_items(self.spec.endpoint_path, payload)
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
                provider_code=pmc_wfs_provider_code(payload),
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
        parsed: WfsPageParse,
        seen_keys: set[str],
    ) -> tuple[int, int]:
        raw_ref = self.repository.get_raw_request_ref_for_work_item(work.id)
        if raw_ref is None:
            raise PmcWfsSyncError("SYNC_WFS_RAW_REF_MISSING")
        model, key_field = ODS_MODELS[self.spec.interface_key]
        rows: list[object] = []
        lineage: list[DataLineage] = []
        written = 0
        duplicates = 0
        for ordinal, header in enumerate(parsed.headers):
            if header.business_key in seen_keys:
                # The same cargo / shipping list twice in one run means the provider paged
                # inconsistently; a silent skip would hide missing records.
                raise PmcWfsSyncError("SYNC_WFS_DUPLICATE_IDENTITY")
            seen_keys.add(header.business_key)
            row = model(
                id=uuid4(),
                run_id=run.id,
                raw_request_ref_id=raw_ref.id,
                source_account_ref=run.source_account_ref,
                source_item_ordinal=ordinal,
                observed_at=observed_at,
                **header.columns,
            )
            rows.append(row)
            written += 1
            lineage.append(
                DataLineage(
                    id=uuid4(),
                    run_id=run.id,
                    parse_job_id=None,
                    raw_request_ref_id=raw_ref.id,
                    raw_blob_id=raw_ref.raw_blob_id,
                    source_path=header.source_path,
                    target_table=model.__tablename__,
                    target_record_id=str(row.id),
                    target_field=key_field,
                    transform_key=PARSER_KEYS[self.spec.endpoint_path],
                    transform_version=PARSER_VERSION,
                )
            )
            for child in header.children:
                child_row = LingxingWfsCargoGoodsOds(
                    id=uuid4(),
                    run_id=run.id,
                    raw_request_ref_id=raw_ref.id,
                    source_account_ref=run.source_account_ref,
                    source_item_ordinal=ordinal,
                    observed_at=observed_at,
                    **child.columns,
                )
                rows.append(child_row)
                lineage.append(
                    DataLineage(
                        id=uuid4(),
                        run_id=run.id,
                        parse_job_id=None,
                        raw_request_ref_id=raw_ref.id,
                        raw_blob_id=raw_ref.raw_blob_id,
                        source_path=child.source_path,
                        target_table=LingxingWfsCargoGoodsOds.__tablename__,
                        target_record_id=str(child_row.id),
                        target_field="cargo_id",
                        transform_key=PARSER_KEYS[self.spec.endpoint_path],
                        transform_version=PARSER_VERSION,
                    )
                )
        self.repository.add_ods_records(rows)
        self.repository.add_lineage(lineage)
        work.status = "succeeded"
        work.finished_at = utc_now()
        run.work_items_succeeded += 1
        run.records_written += written
        self.session.commit()
        return written, duplicates

    def _succeed(self, run: IntegrationSyncRun, written: int, duplicates: int) -> PmcWfsSyncResult:
        run.status = "succeeded"
        run.finished_at = utc_now()
        self.session.commit()
        logger.info(
            "pmc_wfs_sync_succeeded interface=%s run_id=%s written=%s duplicates=%s",
            self.spec.interface_key,
            run.id,
            written,
            duplicates,
        )
        return PmcWfsSyncResult(
            run_id=run.id,
            interface_key=self.spec.interface_key,
            status=run.status,
            records_written=written,
            duplicates_skipped=duplicates,
        )

    def _recover_and_fail(
        self, run_id: UUID, work_item_id: UUID | None, error_code: str
    ) -> PmcWfsSyncResult:
        run = self.repository.get_run_for_update(run_id)
        if run is None:
            raise PmcWfsSyncError("SYNC_WFS_RUN_MISSING")
        work = (
            self.repository.get_work_item_for_update(run_id, work_item_id)
            if work_item_id is not None
            else None
        )
        return self._fail_run(run, work, error_code)

    def _fail_run(
        self,
        run: IntegrationSyncRun,
        work: IntegrationSyncRunWorkItem | None,
        error_code: str,
    ) -> PmcWfsSyncResult:
        now = utc_now()
        if work is not None and work.status == "running":
            work.status = "failed"
            work.error_code = error_code
            work.finished_at = now
            run.work_items_failed += 1
        run.status = "failed"
        run.error_code = error_code
        run.finished_at = now
        self.session.commit()
        return PmcWfsSyncResult(
            run_id=run.id,
            interface_key=self.spec.interface_key,
            status=run.status,
            records_written=0,
            duplicates_skipped=0,
        )


class LingxingWfsCargoPageSyncHandler(LingxingPmcWfsBoardSyncHandler):
    spec = PMC_WFS_SPECS_BY_INTERFACE_KEY["wfsCargoPage"]
    handler_key = spec.handler_key


class LingxingWfsShippingListPageSyncHandler(LingxingPmcWfsBoardSyncHandler):
    spec = PMC_WFS_SPECS_BY_INTERFACE_KEY["wfsShippingListPage"]
    handler_key = spec.handler_key


PMC_WFS_HANDLERS: dict[str, type[LingxingPmcWfsBoardSyncHandler]] = {
    handler.spec.interface_key: handler
    for handler in (LingxingWfsCargoPageSyncHandler, LingxingWfsShippingListPageSyncHandler)
}

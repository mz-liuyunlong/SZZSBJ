"""Governed multi-store WFS settlement collection and detection."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, cast
from uuid import UUID, uuid4

import httpx
from pydantic import JsonValue
from sqlalchemy.orm import Session

from app.core.config import AppEnvironment, Settings, get_settings
from app.integrations.lingxing.client import LingxingRawEnvelope, LingxingReadonlyClient
from app.integrations.lingxing.security import canonical_json, redact_json
from app.integrations.lingxing.token_manager import get_shared_lingxing_token_manager
from app.modules.integration_sync.models import (
    ApiRawBlob,
    ApiRawRequestRef,
    IntegrationInterface,
    IntegrationSyncConfig,
    IntegrationSyncRun,
    IntegrationSyncRunWorkItem,
    RawRetentionPolicy,
    utc_now,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository
from app.modules.integration_sync.wfs_catalog import WFS_SETTLEMENT_SYNC_SPEC
from app.modules.warehouse_wfs.automation_service import detect_store_from_persisted_evidence
from app.modules.warehouse_wfs.settlement_parser import parse_settlement_rows
from app.modules.warehouse_wfs.settlement_repository import WfsSettlementRepository
from app.modules.warehouse_wfs.store_discovery import discover_walmart_stores

logger = logging.getLogger("app.integration_sync.wfs")


class WfsSettlementPageClient(Protocol):
    def fetch_wfs_settlement_page(
        self,
        *,
        store_id: str,
        offset: int,
        length: int,
        page_no: int,
        start_date: date,
        end_date: date,
        source_account_ref: str,
        run_id: str,
        work_item_id: str,
        msku: str | None = None,
    ) -> LingxingRawEnvelope: ...


class WfsSettlementSyncError(RuntimeError):
    """Safe sync error without provider payloads or credentials."""


@dataclass(frozen=True, slots=True)
class WfsSettlementSyncResult:
    run_id: UUID
    status: str
    stores_total: int
    stores_completed: int
    stores_failed: int
    records_captured: int
    cases_created_or_previewed: int


def wfs_response_succeeded(
    endpoint: str,
    response: httpx.Response,
    payload: JsonValue,
) -> bool:
    del response
    return (
        endpoint == WFS_SETTLEMENT_SYNC_SPEC.endpoint_path
        and _provider_code(payload) == "0"
        and _page_rows(payload) is not None
    )


@contextmanager
def wfs_settlement_client() -> Iterator[LingxingReadonlyClient]:
    settings = get_settings()
    _require_wfs_runtime(settings)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    client = LingxingReadonlyClient(
        settings,
        token_provider=get_shared_lingxing_token_manager(settings),
        success_evaluator=wfs_response_succeeded,
    )
    try:
        yield client
    finally:
        client.close()


def _require_wfs_runtime(settings: Settings) -> None:
    if (
        settings.app_env is AppEnvironment.TEST
        or not settings.wfs_auto_detect_enabled
        or not settings.lingxing_enable_real_calls
    ):
        raise WfsSettlementSyncError("SYNC_WFS_RUNTIME_NOT_AUTHORIZED")


class LingxingWfsSettlementSyncHandler:
    handler_key = WFS_SETTLEMENT_SYNC_SPEC.handler_key

    def __init__(
        self,
        session: Session,
        *,
        client: WfsSettlementPageClient | None = None,
        settings: Settings | None = None,
        heartbeat: Callable[[], None] | None = None,
    ) -> None:
        self.session = session
        self.repository = IntegrationSyncRepository(session)
        self._client = client
        self.settings = settings or get_settings()
        self.heartbeat = heartbeat or (lambda: None)

    def execute(
        self,
        run: IntegrationSyncRun,
        interface: IntegrationInterface,
    ) -> WfsSettlementSyncResult:
        config, policy = self._preflight(run, interface)
        if self._client is None:
            _require_wfs_runtime(self.settings)
        stores = discover_walmart_stores(
            self.session,
            source_account_ref=run.source_account_ref,
        )
        if run.window_start is None or run.window_end is None:
            raise WfsSettlementSyncError("SYNC_WFS_WINDOW_REQUIRED")
        start_date = (
            run.window_start.date() if isinstance(run.window_start, datetime) else run.window_start
        )
        end_date = run.window_end.date() if isinstance(run.window_end, datetime) else run.window_end
        page_size = config.page_size or 20
        max_pages = config.max_pages or 500
        if page_size > 20 or max_pages > 500:
            raise WfsSettlementSyncError("SYNC_WFS_PAGINATION_INVALID")

        client_context = (
            _provided_client(self._client) if self._client is not None else wfs_settlement_client()
        )
        completed = 0
        failed = 0
        cases = 0
        with client_context as client:
            for store in stores:
                try:
                    self._collect_store(
                        run,
                        client,
                        policy,
                        store_id=store.store_id,
                        store_name=store.store_name,
                        start_date=start_date,
                        end_date=end_date,
                        page_size=page_size,
                        max_pages=max_pages,
                    )
                    preview = detect_store_from_persisted_evidence(
                        self.session,
                        settings=self.settings,
                        source_account_ref=run.source_account_ref,
                        store_id=store.store_id,
                        start_date=start_date,
                        end_date=end_date,
                        execute_cases=self.settings.wfs_auto_case_create_enabled,
                        collection_verified=True,
                    )
                    cases += preview.would_create
                    completed += 1
                except Exception:
                    self.session.rollback()
                    failed += 1

        run.status = "succeeded" if completed and not failed else "failed"
        run.finished_at = utc_now()
        if failed and completed:
            run.error_code = "SYNC_WFS_STORE_PARTIAL"
            run.error_message = "部分店铺的 WFS 结算采集未完成"
        elif not completed:
            run.error_code = "SYNC_WFS_ALL_STORES_FAILED"
            run.error_message = "WFS 结算采集未完成"
        self.session.commit()
        return WfsSettlementSyncResult(
            run_id=run.id,
            status=(
                "completed"
                if completed and not failed
                else "completed_with_warnings"
                if completed
                else "failed"
            ),
            stores_total=len(stores),
            stores_completed=completed,
            stores_failed=failed,
            records_captured=run.records_seen,
            cases_created_or_previewed=cases,
        )

    def _preflight(
        self,
        run: IntegrationSyncRun,
        interface: IntegrationInterface,
    ) -> tuple[IntegrationSyncConfig, RawRetentionPolicy]:
        spec = WFS_SETTLEMENT_SYNC_SPEC
        if (
            run.provider != "lingxing"
            or run.interface_key != spec.interface_key
            or run.trigger_type not in {"manual", "schedule", "retry"}
            or run.config_id is None
            or interface.endpoint_path != spec.endpoint_path
            or interface.handler_key != spec.handler_key
            or not interface.outbound_enabled
        ):
            raise WfsSettlementSyncError("SYNC_WFS_EXECUTION_NOT_AUTHORIZED")
        config = self.repository.get_config(
            run.config_id,
            frozenset({run.source_account_ref}),
        )
        policy = self.repository.get_retention_policy(spec.retention_policy_key)
        if config is None or policy is None or not config.is_enabled:
            raise WfsSettlementSyncError("SYNC_WFS_GOVERNANCE_DISABLED")
        if not self.settings.wfs_auto_detect_enabled:
            raise WfsSettlementSyncError("SYNC_WFS_DETECTION_DISABLED")
        return config, policy

    def _collect_store(
        self,
        run: IntegrationSyncRun,
        client: WfsSettlementPageClient,
        policy: RawRetentionPolicy,
        *,
        store_id: str,
        store_name: str,
        start_date: date,
        end_date: date,
        page_size: int,
        max_pages: int,
    ) -> None:
        offset = 0
        expected_total: int | None = None
        seen_lines: set[str] = set()
        for page_no in range(1, max_pages + 1):
            work = self._start_work_item(run, store_id, page_no, offset, page_size)
            self.heartbeat()
            envelope = client.fetch_wfs_settlement_page(
                store_id=store_id,
                offset=offset,
                length=page_size,
                page_no=page_no,
                start_date=start_date,
                end_date=end_date,
                source_account_ref=run.source_account_ref,
                run_id=str(run.id),
                work_item_id=str(work.id),
            )
            raw_ref = self._persist_raw(run, work, policy, envelope, store_id)
            if not envelope.is_success or envelope.response_json is None:
                self._fail_work(run, work, envelope.error_code or "SYNC_WFS_RESPONSE_FAILED")
                raise WfsSettlementSyncError("SYNC_WFS_RESPONSE_FAILED")
            rows = _page_rows(envelope.response_json)
            total = _page_total(envelope.response_json)
            if rows is None or total is None or total < 0 or len(rows) > page_size:
                self._fail_work(run, work, "SYNC_WFS_INVALID_PAGE")
                raise WfsSettlementSyncError("SYNC_WFS_INVALID_PAGE")
            if expected_total is None:
                expected_total = total
                if total > max_pages * page_size:
                    self._fail_work(run, work, "SYNC_WFS_PAGE_LIMIT")
                    raise WfsSettlementSyncError("SYNC_WFS_PAGE_LIMIT")
            elif total != expected_total:
                self._fail_work(run, work, "SYNC_WFS_TOTAL_CHANGED")
                raise WfsSettlementSyncError("SYNC_WFS_TOTAL_CHANGED")

            parsed = parse_settlement_rows(
                rows,
                source_account_ref=run.source_account_ref,
                store_ids_by_name={store_name: store_id},
                window_start=start_date,
                window_end=end_date,
            )
            if parsed.rejected_rows or parsed.duplicate_lines:
                self._fail_work(run, work, "SYNC_WFS_PAGE_REJECTED")
                raise WfsSettlementSyncError("SYNC_WFS_PAGE_REJECTED")
            page_lines = {row.source_line_ref for row in parsed.rows}
            if seen_lines.intersection(page_lines):
                self._fail_work(run, work, "SYNC_WFS_DUPLICATE_LINE")
                raise WfsSettlementSyncError("SYNC_WFS_DUPLICATE_LINE")
            next_offset = offset + len(rows)
            if next_offset < expected_total and (not rows or len(rows) < page_size):
                self._fail_work(run, work, "SYNC_WFS_INCOMPLETE_PAGE")
                raise WfsSettlementSyncError("SYNC_WFS_INCOMPLETE_PAGE")
            seen_lines.update(page_lines)
            written = WfsSettlementRepository(self.session).upsert_rows(
                parsed.rows,
                raw_request_ref_id=raw_ref.id,
                observed_at=envelope.pulled_at,
            )
            work.status = "succeeded"
            work.finished_at = utc_now()
            work.response_count = len(rows)
            run.work_items_succeeded += 1
            run.records_seen += len(rows)
            run.records_written += written
            self.session.commit()
            self.heartbeat()

            offset = next_offset
            if offset == expected_total:
                return
        raise WfsSettlementSyncError("SYNC_WFS_MAX_PAGES")

    def _start_work_item(
        self,
        run: IntegrationSyncRun,
        store_id: str,
        page_no: int,
        offset: int,
        length: int,
    ) -> IntegrationSyncRunWorkItem:
        ordinal = run.work_items_total + 1
        work = IntegrationSyncRunWorkItem(
            id=uuid4(),
            run_id=run.id,
            ordinal=ordinal,
            request_kind="offset_page",
            scope_key=store_id,
            status="running",
            attempt_count=0,
            offset_value=offset,
            length_value=length,
            request_safe_params={
                "store_id": store_id,
                "offset": offset,
                "length": length,
                "page_no": page_no,
            },
            started_at=utc_now(),
        )
        self.repository.add_work_items([work])
        run.work_items_total += 1
        self.session.commit()
        return work

    def _persist_raw(
        self,
        run: IntegrationSyncRun,
        work: IntegrationSyncRunWorkItem,
        policy: RawRetentionPolicy,
        envelope: LingxingRawEnvelope,
        store_id: str,
    ) -> ApiRawRequestRef:
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
        rows = _page_rows(payload)
        ref = self.repository.add_raw_request_ref(
            ApiRawRequestRef(
                id=uuid4(),
                run_id=run.id,
                work_item_id=work.id,
                raw_blob_id=blob.id,
                request_kind="offset_page",
                attempt_no=envelope.attempt_no,
                request_safe_params={
                    "store_id": store_id,
                    "offset": work.offset_value,
                    "length": work.length_value,
                },
                http_status=envelope.response_code,
                provider_code=_provider_code(payload),
                is_success=envelope.is_success,
                response_count=len(rows) if rows is not None else None,
                requested_at=work.started_at or envelope.pulled_at,
                received_at=envelope.pulled_at,
            )
        )
        work.attempt_count = envelope.attempt_no
        self.session.commit()
        return ref

    def _fail_work(
        self,
        run: IntegrationSyncRun,
        work: IntegrationSyncRunWorkItem,
        code: str,
    ) -> None:
        work.status = "failed"
        work.error_code = code
        work.error_message = "WFS 结算页处理失败"
        work.finished_at = utc_now()
        run.work_items_failed += 1
        self.session.commit()


@contextmanager
def _provided_client(
    client: WfsSettlementPageClient | None,
) -> Iterator[WfsSettlementPageClient]:
    if client is None:
        raise WfsSettlementSyncError("SYNC_WFS_CLIENT_MISSING")
    yield client


def _provider_code(payload: JsonValue) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("code")
    return str(value) if isinstance(value, (int, str)) else None


def _page_rows(payload: JsonValue) -> list[dict[str, object]] | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    rows = data.get("list")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return None
    return cast(list[dict[str, object]], rows)


def _page_total(payload: JsonValue) -> int | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    top = payload.get("total")
    nested = data.get("total") if isinstance(data, dict) else None
    if top is not None and nested is not None and top != nested:
        return None
    value = top if top is not None else nested
    return value if type(value) is int else None

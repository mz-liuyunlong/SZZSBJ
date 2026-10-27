"""Governed multi-store WFS settlement collection and detection."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol, cast
from uuid import UUID, uuid4

import httpx
from pydantic import JsonValue
from sqlalchemy import select
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
from app.modules.warehouse_wfs.models import WfsSettlementCollection
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
                collection_repository = WfsSettlementRepository(self.session)
                collection = collection_repository.create_collection(
                    run_id=run.id,
                    source_account_ref=run.source_account_ref,
                    store_id=store.store_id,
                    start_date=start_date,
                    end_date=end_date,
                    wfs_scope_status=(
                        "verified_wfs"
                        if self.settings.wfs_settlement_scope_verified
                        else "unverified"
                    ),
                )
                self.session.commit()
                try:
                    self._collect_store(
                        run,
                        client,
                        policy,
                        store_id=store.store_id,
                        start_date=start_date,
                        end_date=end_date,
                        page_size=page_size,
                        max_pages=max_pages,
                        collection=collection,
                    )
                    preview = detect_store_from_persisted_evidence(
                        self.session,
                        settings=self.settings,
                        source_account_ref=run.source_account_ref,
                        store_id=store.store_id,
                        start_date=start_date,
                        end_date=end_date,
                        execute_cases=self.settings.wfs_auto_case_create_enabled,
                        collection_id=collection.id,
                        persist_evidence=True,
                    )
                    self.session.commit()
                    cases += preview.would_create
                    completed += 1
                except Exception as exc:
                    self.session.rollback()
                    code = self._safe_error_code(exc)
                    persisted_collection = self.session.get(
                        WfsSettlementCollection,
                        collection.id,
                    )
                    if (
                        persisted_collection is not None
                        and persisted_collection.collection_status != "verified"
                    ):
                        collection_repository.fail_collection(persisted_collection, code)
                    self._terminalize_store_work_items(run, store.store_id, code)
                    self.session.commit()
                    failed += 1

        # A partially collected run is not complete evidence and must not be
        # persisted as successful even when another store finished normally.
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
        start_date: date,
        end_date: date,
        page_size: int,
        max_pages: int,
        collection: WfsSettlementCollection,
    ) -> None:
        self._collect_window_segment(
            run,
            client,
            policy,
            store_id=store_id,
            start_date=start_date,
            end_date=end_date,
            page_size=page_size,
            max_pages=max_pages,
            collection=collection,
            seen_lines=set(),
        )
        WfsSettlementRepository(self.session).finalize_collection(
            collection,
            expected_total=collection.expected_total or 0,
            captured_count=collection.captured_count,
            accepted_count=collection.accepted_count,
            business_excluded_count=collection.business_excluded_count,
            invalid_count=collection.invalid_count,
            missing_store_count=collection.missing_store_count,
            duplicate_count=collection.duplicate_count,
            missing_identity_count=collection.missing_identity_count,
            latest_settlement_date=collection.latest_settlement_date,
        )
        self.session.commit()

    def _collect_window_segment(
        self,
        run: IntegrationSyncRun,
        client: WfsSettlementPageClient,
        policy: RawRetentionPolicy,
        *,
        store_id: str,
        start_date: date,
        end_date: date,
        page_size: int,
        max_pages: int,
        collection: WfsSettlementCollection,
        seen_lines: set[str],
    ) -> None:
        offset = 0
        expected_total: int | None = None
        for page_no in range(1, max_pages + 1):
            scope_key = f"{store_id}:{start_date.isoformat()}:{end_date.isoformat()}"
            work = self._start_work_item(
                run,
                scope_key,
                store_id,
                page_no,
                offset,
                page_size,
                start_date,
                end_date,
            )
            try:
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
            except Exception as exc:
                self.session.rollback()
                self._fail_work(run, work, self._safe_error_code(exc))
                raise
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
                    if start_date == end_date:
                        self._fail_work(run, work, "SYNC_WFS_DAY_PAGE_LIMIT")
                        raise WfsSettlementSyncError("SYNC_WFS_DAY_PAGE_LIMIT")
                    work.status = "succeeded"
                    work.response_count = len(rows)
                    work.finished_at = utc_now()
                    run.work_items_succeeded += 1
                    self.session.commit()
                    midpoint = start_date + timedelta(days=(end_date - start_date).days // 2)
                    self._collect_window_segment(
                        run,
                        client,
                        policy,
                        store_id=store_id,
                        start_date=start_date,
                        end_date=midpoint,
                        page_size=page_size,
                        max_pages=max_pages,
                        collection=collection,
                        seen_lines=seen_lines,
                    )
                    self._collect_window_segment(
                        run,
                        client,
                        policy,
                        store_id=store_id,
                        start_date=midpoint + timedelta(days=1),
                        end_date=end_date,
                        page_size=page_size,
                        max_pages=max_pages,
                        collection=collection,
                        seen_lines=seen_lines,
                    )
                    return
            elif total != expected_total:
                self._fail_work(run, work, "SYNC_WFS_TOTAL_CHANGED")
                raise WfsSettlementSyncError("SYNC_WFS_TOTAL_CHANGED")

            parsed = parse_settlement_rows(
                rows,
                source_account_ref=run.source_account_ref,
                expected_store_id=store_id,
                window_start=start_date,
                window_end=end_date,
                wfs_scope_verified=self.settings.wfs_settlement_scope_verified,
            )
            collection.captured_count += len(rows)
            collection.accepted_count += parsed.accepted_rows
            collection.business_excluded_count += parsed.business_excluded_rows
            collection.invalid_count += parsed.invalid_rows
            collection.missing_store_count += parsed.missing_store_rows
            collection.duplicate_count += parsed.duplicate_rows
            collection.missing_identity_count += parsed.missing_identity_rows
            if parsed.rejected_rows or parsed.duplicate_rows:
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
                collection_id=collection.id,
                observed_at=envelope.pulled_at,
            )
            page_latest = max(
                (date.fromisoformat(row.settlement_date) for row in parsed.rows),
                default=None,
            )
            if page_latest is not None and (
                collection.latest_settlement_date is None
                or page_latest > collection.latest_settlement_date
            ):
                collection.latest_settlement_date = page_latest
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
                collection.expected_total = (collection.expected_total or 0) + expected_total
                return
        raise WfsSettlementSyncError("SYNC_WFS_MAX_PAGES")

    def _start_work_item(
        self,
        run: IntegrationSyncRun,
        scope_key: str,
        store_id: str,
        page_no: int,
        offset: int,
        length: int,
        start_date: date,
        end_date: date,
    ) -> IntegrationSyncRunWorkItem:
        ordinal = run.work_items_total + 1
        work = IntegrationSyncRunWorkItem(
            id=uuid4(),
            run_id=run.id,
            ordinal=ordinal,
            request_kind="offset_page",
            scope_key=scope_key,
            status="running",
            attempt_count=0,
            offset_value=offset,
            length_value=length,
            request_safe_params={
                "store_id": store_id,
                "offset": offset,
                "length": length,
                "page_no": page_no,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
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
        if work.status in {"failed", "succeeded", "canceled"}:
            return
        work.status = "failed"
        work.error_code = code
        work.error_message = "WFS 结算页处理失败"
        work.finished_at = utc_now()
        run.work_items_failed += 1
        self.session.commit()

    def _terminalize_store_work_items(
        self,
        run: IntegrationSyncRun,
        store_id: str,
        code: str,
    ) -> None:
        running = self.session.scalars(
            select(IntegrationSyncRunWorkItem).where(
                IntegrationSyncRunWorkItem.run_id == run.id,
                IntegrationSyncRunWorkItem.scope_key.like(f"{store_id}:%"),
                IntegrationSyncRunWorkItem.status == "running",
            )
        ).all()
        for work in running:
            work.status = "failed"
            work.error_code = code
            work.error_message = "WFS 结算页处理失败"
            work.finished_at = utc_now()
            run.work_items_failed += 1

    @staticmethod
    def _safe_error_code(exc: Exception) -> str:
        code = str(exc)
        if code.startswith(("SYNC_WFS_", "WFS_")) and len(code) <= 128:
            return code
        return "SYNC_WFS_UNEXPECTED"


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

"""领星月汇率同步：原始响应先落原始层，再写 fact_lingxing_fx_rate。

只读接口，一个月一次请求。默认关闭，手动触发。某个月领星没有数据算正常（跳过）；
所有月份都没有数据，或任何一个月报错，整次算失败，不把半截结果当成功。
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol, cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx
from pydantic import JsonValue
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import AppEnvironment, Settings, get_settings
from app.integrations.lingxing.client import LingxingRawEnvelope, LingxingReadonlyClient
from app.integrations.lingxing.security import canonical_json, redact_json
from app.integrations.lingxing.token_manager import get_shared_lingxing_token_manager
from app.modules.fx_rates.models import LingxingFxRate
from app.modules.integration_sync.fx_catalog import FX_RATE_SYNC_SPEC
from app.modules.integration_sync.models import (
    ApiRawBlob,
    ApiRawRequestRef,
    IntegrationInterface,
    IntegrationSyncRun,
    IntegrationSyncRunWorkItem,
    RawRetentionPolicy,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository

SHANGHAI = ZoneInfo("Asia/Shanghai")
MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")
MAX_MONTHS = 36


def utc_now() -> datetime:
    return datetime.now(UTC)


class FxRateSyncError(RuntimeError):
    """Safe sync error without provider payloads or credentials."""


class FxRatePageClient(Protocol):
    def fetch_fx_month(
        self,
        *,
        month: str,
        source_account_ref: str,
        run_id: str,
        work_item_id: str,
    ) -> LingxingRawEnvelope: ...


@dataclass(frozen=True, slots=True)
class FxRateSyncResult:
    run_id: UUID
    status: str
    months_total: int
    months_with_rows: int
    records_written: int


def fx_response_succeeded(
    endpoint: str,
    response: httpx.Response,
    payload: JsonValue,
) -> bool:
    del response
    return (
        endpoint == FX_RATE_SYNC_SPEC.endpoint_path
        and _provider_code(payload) == "0"
        and fx_rows(payload) is not None
    )


@contextmanager
def fx_rate_client() -> Iterator[LingxingReadonlyClient]:
    settings = get_settings()
    _require_runtime(settings)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    client = LingxingReadonlyClient(
        settings,
        token_provider=get_shared_lingxing_token_manager(settings),
        success_evaluator=fx_response_succeeded,
    )
    try:
        yield client
    finally:
        client.close()


def _require_runtime(settings: Settings) -> None:
    if settings.app_env is AppEnvironment.TEST or not settings.lingxing_enable_real_calls:
        raise FxRateSyncError("SYNC_FX_RUNTIME_NOT_AUTHORIZED")


def months_back(now: datetime, count: int) -> list[str]:
    """从当月（上海时间）往回 count 个月，旧到新。"""
    local = now.astimezone(SHANGHAI)
    index = local.year * 12 + local.month - 1
    months = []
    for value in range(index - count + 1, index + 1):
        year, month = divmod(value, 12)
        months.append(f"{year:04d}-{month + 1:02d}")
    return months


class LingxingFxRateSyncHandler:
    handler_key = FX_RATE_SYNC_SPEC.handler_key

    def __init__(
        self,
        session: Session,
        *,
        client: FxRatePageClient | None = None,
        heartbeat: Callable[[], None] | None = None,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self.session = session
        self.repository = IntegrationSyncRepository(session)
        self._client = client
        self.heartbeat = heartbeat or (lambda: None)
        self._now = now

    def execute(
        self,
        run: IntegrationSyncRun,
        interface: IntegrationInterface,
    ) -> FxRateSyncResult:
        months_count, policy = self._preflight(run, interface)
        months = months_back(self._now(), months_count)
        with self._client_context() as client:
            with_rows = sum(self._sync_month(run, client, policy, month) for month in months)
        run.finished_at = utc_now()
        if with_rows:
            run.status = "succeeded"
        else:
            run.status = "failed"
            run.error_code = "SYNC_FX_ALL_MONTHS_EMPTY"
            run.error_message = "领星所有月份都没有返回汇率"
        self.session.commit()
        return FxRateSyncResult(
            run_id=run.id,
            status=run.status,
            months_total=len(months),
            months_with_rows=with_rows,
            records_written=run.records_written,
        )

    def _client_context(self) -> AbstractContextManager[FxRatePageClient]:
        return _provided_client(self._client) if self._client is not None else fx_rate_client()

    def _preflight(
        self,
        run: IntegrationSyncRun,
        interface: IntegrationInterface,
    ) -> tuple[int, RawRetentionPolicy]:
        spec = FX_RATE_SYNC_SPEC
        if (
            run.provider != "lingxing"
            or run.interface_key != spec.interface_key
            or run.trigger_type not in {"manual", "schedule", "retry"}
            or run.config_id is None
            or interface.endpoint_path != spec.endpoint_path
            or interface.handler_key != spec.handler_key
            or not interface.outbound_enabled
        ):
            raise FxRateSyncError("SYNC_FX_EXECUTION_NOT_AUTHORIZED")
        config = self.repository.get_config(run.config_id, frozenset({run.source_account_ref}))
        policy = self.repository.get_retention_policy(spec.retention_policy_key)
        if config is None or policy is None or not config.is_enabled:
            raise FxRateSyncError("SYNC_FX_GOVERNANCE_DISABLED")
        months = config.max_pages or spec.default_max_pages
        if not 1 <= months <= MAX_MONTHS:
            raise FxRateSyncError("SYNC_FX_MONTHS_INVALID")
        return months, policy

    def _sync_month(
        self,
        run: IntegrationSyncRun,
        client: FxRatePageClient,
        policy: RawRetentionPolicy,
        month: str,
    ) -> bool:
        work = self._start_work_item(run, month)
        try:
            self.heartbeat()
            envelope = client.fetch_fx_month(
                month=month,
                source_account_ref=run.source_account_ref,
                run_id=str(run.id),
                work_item_id=str(work.id),
            )
            raw_ref = self._persist_raw(run, work, policy, envelope, month)
        except Exception as exc:
            self.session.rollback()
            self._fail_work(run, work, "SYNC_FX_REQUEST_FAILED")
            raise FxRateSyncError("SYNC_FX_REQUEST_FAILED") from exc
        rows = fx_rows(envelope.response_json) if envelope.is_success else None
        if rows is None:
            self._fail_work(run, work, "SYNC_FX_RESPONSE_FAILED")
            raise FxRateSyncError("SYNC_FX_RESPONSE_FAILED")
        values = parse_fx_rows(rows, month)
        if values is None:
            self._fail_work(run, work, "SYNC_FX_INVALID_ROW")
            raise FxRateSyncError("SYNC_FX_INVALID_ROW")
        for value in values:
            statement = pg_insert(LingxingFxRate).values(
                **value, source="sync", raw_request_ref_id=raw_ref.id, updated_at=utc_now()
            )
            self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=["rate_month", "currency_code"],
                    set_={
                        key: statement.excluded[key]
                        for key in (
                            "currency_name",
                            "rate_org",
                            "my_rate",
                            "lx_update_time",
                            "source",
                            "raw_request_ref_id",
                            "updated_at",
                        )
                    },
                )
            )
        work.status = "succeeded"
        work.finished_at = utc_now()
        work.response_count = len(rows)
        run.work_items_succeeded += 1
        run.records_seen += len(rows)
        run.records_written += len(values)
        self.session.commit()
        return bool(values)

    def _start_work_item(self, run: IntegrationSyncRun, month: str) -> IntegrationSyncRunWorkItem:
        work = IntegrationSyncRunWorkItem(
            id=uuid4(),
            run_id=run.id,
            ordinal=run.work_items_total + 1,
            request_kind="offset_page",
            scope_key=month,
            status="running",
            attempt_count=0,
            offset_value=0,
            length_value=1,
            request_safe_params={"date": month},
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
        month: str,
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
        rows = fx_rows(payload)
        ref = self.repository.add_raw_request_ref(
            ApiRawRequestRef(
                id=uuid4(),
                run_id=run.id,
                work_item_id=work.id,
                raw_blob_id=blob.id,
                request_kind="offset_page",
                attempt_no=envelope.attempt_no,
                request_safe_params={"date": month},
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
        work.error_message = "领星汇率请求处理失败"
        work.finished_at = utc_now()
        run.work_items_failed += 1
        self.session.commit()


@contextmanager
def _provided_client(client: FxRatePageClient) -> Iterator[FxRatePageClient]:
    yield client


def _provider_code(payload: JsonValue) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("code")
    return str(value) if isinstance(value, (int, str)) else None


def fx_rows(payload: JsonValue) -> list[dict[str, object]] | None:
    """币种列表在响应的 data 里，是数组；data 为 null 算这个月没有数据。"""
    if not isinstance(payload, dict) or "data" not in payload:
        return None
    rows = payload["data"]
    if rows is None:
        return []
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return None
    return cast(list[dict[str, object]], rows)


def _rate(value: object) -> Decimal | None:
    """空值和 0 都算没有汇率；不是数字就抛错，让这个月失败。"""
    if value is None or value == "":
        return None
    parsed = Decimal(str(value))
    if not parsed.is_finite() or parsed < 0:
        raise InvalidOperation
    return parsed if parsed > 0 else None


def parse_fx_rows(rows: list[dict[str, object]], month: str) -> list[dict[str, object]] | None:
    """返回要写入的行；月份对不上或数字不合法返回 None。"""
    out: list[dict[str, object]] = []
    for row in rows:
        code = str(row.get("code") or "").strip().upper()
        row_month = str(row.get("date") or month).strip()
        if not code or row_month != month or not MONTH_PATTERN.match(row_month) or len(code) > 8:
            return None
        try:
            rate_org, my_rate = _rate(row.get("rate_org")), _rate(row.get("my_rate"))
        except (InvalidOperation, ValueError):
            return None
        out.append(
            {
                "rate_month": month,
                "currency_code": code,
                "currency_name": str(row.get("name") or "")[:64] or None,
                "rate_org": rate_org,
                "my_rate": my_rate,
                "lx_update_time": str(row.get("update_time") or "")[:32] or None,
            }
        )
    return out

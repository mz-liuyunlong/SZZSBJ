"""结算利润 PR-2 三个同步处理器的公共部分：预检、时间窗、店铺、工作项、原始层落库。

三个处理器都是只读接口、一个店一次请求、每页先落原始层再写 ODS、每页提交一次。
任何一个店失败不影响其他店，整次运行按「部分失败」记失败，下次重跑会把当前状态补齐（全部 upsert）。
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import JsonValue
from sqlalchemy.orm import Session

from app.core.config import AppEnvironment, Settings, get_settings
from app.integrations.lingxing.client import LingxingRawEnvelope, LingxingReadonlyClient
from app.integrations.lingxing.security import canonical_json, redact_json
from app.integrations.lingxing.token_manager import get_shared_lingxing_token_manager
from app.modules.integration_sync.fin_shipping_catalog import (
    FIN_SHIPPING_EARLIEST_DATE,
    FIN_SHIPPING_ROLLING_DAYS,
    FinShippingSyncInterfaceSpec,
)
from app.modules.integration_sync.models import (
    ApiRawBlob,
    ApiRawRequestRef,
    IntegrationInterface,
    IntegrationSyncConfig,
    IntegrationSyncRun,
    IntegrationSyncRunWorkItem,
    RawRetentionPolicy,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository
from app.modules.warehouse_wfs.store_discovery import (
    WfsSettlementStore,
    WfsStoreDiscoveryError,
    discover_walmart_stores,
)

logger = logging.getLogger(__name__)

SHANGHAI = ZoneInfo("Asia/Shanghai")
EARLIEST = date.fromisoformat(FIN_SHIPPING_EARLIEST_DATE)
MAX_PAGE_SIZE = 200
MAX_PAGES = 5000

# 销售出库单里的收件人等个人信息不进原始层也不进 ODS（和 2026-10 探测脚本同一份键名规则）。
_PII_KEY = re.compile(
    r"^(consignee|order_buyer_notes|order_customer_service_notes|customer_shipping_list"
    r"|buyers?_?info|address|receiver|phone|email|postcode|zip|tel|district"
    r"|recipient_tax_no|sender_tax_no|remark_attachment)",
    re.IGNORECASE,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class FinSyncError(RuntimeError):
    """Safe sync error without provider payloads or credentials."""


@dataclass(frozen=True, slots=True)
class FinSyncResult:
    run_id: Any
    status: str
    stores_total: int
    stores_failed: int
    records_written: int


def fin_response_succeeded(endpoint: str, response: object, payload: JsonValue) -> bool:
    del endpoint, response
    return provider_code(payload) == "0"


@contextmanager
def fin_sync_client() -> Iterator[LingxingReadonlyClient]:
    settings = get_settings()
    require_runtime(settings)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    client = LingxingReadonlyClient(
        settings,
        token_provider=get_shared_lingxing_token_manager(settings),
        success_evaluator=fin_response_succeeded,
    )
    try:
        yield client
    finally:
        client.close()


def require_runtime(settings: Settings) -> None:
    if settings.app_env is AppEnvironment.TEST or not settings.lingxing_enable_real_calls:
        raise FinSyncError("SYNC_FIN_RUNTIME_NOT_AUTHORIZED")


def provider_code(payload: JsonValue) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("code")
    return str(value) if isinstance(value, (int, str)) and not isinstance(value, bool) else None


def scrub_pii(value: JsonValue) -> JsonValue:
    """递归删掉个人信息键；其余原样保留。"""
    if isinstance(value, dict):
        return {
            key: scrub_pii(item)
            for key, item in value.items()
            if not (isinstance(key, str) and _PII_KEY.match(key))
        }
    if isinstance(value, list):
        return [scrub_pii(item) for item in value]
    return value


def row_hash(row: JsonValue) -> str:
    return hashlib.sha256(canonical_json(row).encode("utf-8")).hexdigest()


def text_or_none(value: object, limit: int) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    if not text or len(text) > limit:
        return None
    return text


def decimal_or_none(value: object) -> Decimal | None:
    """空值算没有；不是数字（或 NaN/无穷）算没有，不让一个脏字段拖垮整页。"""
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def lx_datetime(value: object) -> datetime | None:
    """领星时间是上海本地时间字符串；'0000-00-00 ...' 和空串算没有。"""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text.startswith("0000-00-00"):
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=SHANGHAI)
        except ValueError:
            continue
    return None


def rolling_window(now: datetime, days: int = FIN_SHIPPING_ROLLING_DAYS) -> tuple[date, date]:
    today = now.astimezone(SHANGHAI).date()
    return today - timedelta(days=days), today


def _local_date(value: datetime) -> date:
    return value.astimezone(SHANGHAI).date()


class FinSyncHandlerBase:
    """三个处理器共用的骨架；子类实现 `_sync_store` 并声明 `spec`。"""

    spec: FinShippingSyncInterfaceSpec
    handler_key: str

    def __init__(
        self,
        session: Session,
        *,
        client: Any | None = None,
        heartbeat: Callable[[], None] | None = None,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self.session = session
        self.repository = IntegrationSyncRepository(session)
        self._client = client
        self.heartbeat = heartbeat or (lambda: None)
        self._now = now

    # ------------------------------------------------------------------ 入口

    def execute(self, run: IntegrationSyncRun, interface: IntegrationInterface) -> FinSyncResult:
        config, policy = self._preflight(run, interface)
        start, end = self._window(run)
        stores = self._stores(run)
        page_size = config.page_size or self.spec.default_page_size
        max_pages = config.max_pages or self.spec.default_max_pages
        if not 1 <= page_size <= MAX_PAGE_SIZE or not 1 <= max_pages <= MAX_PAGES:
            raise FinSyncError("SYNC_FIN_PAGINATION_INVALID")

        failed = 0
        with self._client_context() as client:
            for store in stores:
                try:
                    self._sync_store(run, client, policy, store, start, end, page_size, max_pages)
                except FinSyncError as exc:
                    failed += 1
                    self.session.rollback()
                    self._record_store_failure(run, store.store_id, str(exc))
                except Exception as exc:
                    failed += 1
                    self.session.rollback()
                    self._record_store_failure(run, store.store_id, "SYNC_FIN_STORE_FAILED")
                    logger.exception("fin sync store failed: %s", type(exc).__name__)

        run.finished_at = utc_now()
        if failed == 0:
            run.status = "succeeded"
        else:
            run.status = "failed"
            run.error_code = (
                "SYNC_FIN_ALL_STORES_FAILED" if failed == len(stores) else "SYNC_FIN_STORE_PARTIAL"
            )
            notes = run.error_message or ""
            run.error_message = f"{self.spec.display_name}有 {failed} 个店铺未完成：{notes}"[:2000]
        self.session.commit()
        return FinSyncResult(
            run_id=run.id,
            status=run.status,
            stores_total=len(stores),
            stores_failed=failed,
            records_written=run.records_written,
        )

    def _sync_store(
        self,
        run: IntegrationSyncRun,
        client: Any,
        policy: RawRetentionPolicy,
        store: WfsSettlementStore,
        start: date,
        end: date,
        page_size: int,
        max_pages: int,
    ) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------------ 公共

    @contextmanager
    def _client_context(self) -> Iterator[Any]:
        if self._client is not None:
            yield self._client
            return
        with fin_sync_client() as client:
            yield client

    def _preflight(
        self,
        run: IntegrationSyncRun,
        interface: IntegrationInterface,
    ) -> tuple[IntegrationSyncConfig, RawRetentionPolicy]:
        spec = self.spec
        if (
            run.provider != "lingxing"
            or run.interface_key != spec.interface_key
            or run.trigger_type not in {"manual", "schedule", "retry", "backfill"}
            or run.config_id is None
            or interface.endpoint_path != spec.endpoint_path
            or interface.handler_key != spec.handler_key
            or not interface.outbound_enabled
        ):
            raise FinSyncError("SYNC_FIN_EXECUTION_NOT_AUTHORIZED")
        config = self.repository.get_config(run.config_id, frozenset({run.source_account_ref}))
        policy = self.repository.get_retention_policy(spec.retention_policy_key)
        if config is None or policy is None or not config.is_enabled:
            raise FinSyncError("SYNC_FIN_GOVERNANCE_DISABLED")
        return config, policy

    def _window(self, run: IntegrationSyncRun) -> tuple[date, date]:
        if run.window_start is not None and run.window_end is not None:
            # 回填：window_end 是开区间的时间点，取它前一刻所在的上海日期。
            start = max(EARLIEST, _local_date(run.window_start))
            end = _local_date(run.window_end - timedelta(microseconds=1))
        else:
            start, end = rolling_window(self._now())
        if start > end:
            raise FinSyncError("SYNC_FIN_WINDOW_INVALID")
        return start, end

    def _stores(self, run: IntegrationSyncRun) -> tuple[WfsSettlementStore, ...]:
        try:
            stores = discover_walmart_stores(
                self.session, source_account_ref=run.source_account_ref
            )
        except WfsStoreDiscoveryError as exc:
            raise FinSyncError("SYNC_FIN_NO_STORES") from exc
        if not stores:
            raise FinSyncError("SYNC_FIN_NO_STORES")
        return stores

    def _start_work_item(
        self,
        run: IntegrationSyncRun,
        *,
        scope_key: str,
        safe_params: dict[str, object],
        offset: int,
        length: int,
    ) -> IntegrationSyncRunWorkItem:
        work = IntegrationSyncRunWorkItem(
            id=uuid4(),
            run_id=run.id,
            ordinal=run.work_items_total + 1,
            request_kind="offset_page",
            scope_key=scope_key[:255],
            status="running",
            attempt_count=0,
            offset_value=offset,
            length_value=length,
            request_safe_params=safe_params,
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
        payload: JsonValue,
        *,
        response_count: int | None,
    ) -> ApiRawRequestRef:
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
        ref = self.repository.add_raw_request_ref(
            ApiRawRequestRef(
                id=uuid4(),
                run_id=run.id,
                work_item_id=work.id,
                raw_blob_id=blob.id,
                request_kind="offset_page",
                attempt_no=envelope.attempt_no,
                request_safe_params=cast(dict[str, object], work.request_safe_params),
                http_status=envelope.response_code,
                provider_code=provider_code(payload),
                is_success=envelope.is_success,
                response_count=response_count,
                requested_at=work.started_at or envelope.pulled_at,
                received_at=envelope.pulled_at,
            )
        )
        work.attempt_count = envelope.attempt_no
        work.http_status = envelope.response_code
        work.provider_code = provider_code(payload)
        self.session.commit()
        return ref

    def _fetch_and_store(
        self,
        run: IntegrationSyncRun,
        work: IntegrationSyncRunWorkItem,
        policy: RawRetentionPolicy,
        fetch: Callable[[], LingxingRawEnvelope],
    ) -> tuple[JsonValue, ApiRawRequestRef]:
        """请求一次，脱敏后先落原始层；请求或落库出错按 REQUEST_FAILED 记工作项失败。"""
        try:
            self.heartbeat()
            envelope = fetch()
            payload = scrub_pii(redact_json(envelope.response_json))
            ref = self._persist_raw(run, work, policy, envelope, payload, response_count=None)
        except Exception as exc:
            self.session.rollback()
            self._fail_work(run, work, "SYNC_FIN_REQUEST_FAILED")
            raise FinSyncError("SYNC_FIN_REQUEST_FAILED") from exc
        if not envelope.is_success or provider_code(payload) != "0":
            self._fail_work(run, work, "SYNC_FIN_RESPONSE_FAILED")
            raise FinSyncError("SYNC_FIN_RESPONSE_FAILED")
        return payload, ref

    def _finish_work(
        self,
        run: IntegrationSyncRun,
        work: IntegrationSyncRunWorkItem,
        ref: ApiRawRequestRef,
        *,
        seen: int,
        written: int,
    ) -> None:
        work.status = "succeeded"
        work.finished_at = utc_now()
        work.response_count = seen
        ref.response_count = seen
        run.work_items_succeeded += 1
        run.records_seen += seen
        run.records_written += written
        self.session.commit()

    def _fail_work(
        self, run: IntegrationSyncRun, work: IntegrationSyncRunWorkItem, code: str
    ) -> None:
        work.status = "failed"
        work.error_code = code
        work.error_message = f"{self.spec.display_name}请求处理失败"
        work.finished_at = utc_now()
        run.work_items_failed += 1
        self.session.commit()

    def _record_store_failure(self, run: IntegrationSyncRun, store_id: str, code: str) -> None:
        """店铺失败只留在运行的 error_message 里（店铺 ID 不是敏感信息）；工作项已各自记失败。"""
        note = f"{store_id}:{code}"
        run.error_message = f"{run.error_message};{note}" if run.error_message else note
        run.error_message = run.error_message[-2000:]
        self.session.commit()


def response_list(payload: JsonValue, *keys: str) -> list[dict[str, Any]] | None:
    """按 keys 逐层取出数组；取不到或不是对象数组返回 None；null 算空数组。"""
    node: JsonValue = payload
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    if node is None:
        return []
    if not isinstance(node, list) or not all(isinstance(item, dict) for item in node):
        return None
    return cast(list[dict[str, Any]], node)


def response_total(payload: JsonValue, *keys: str) -> int | None:
    node: JsonValue = payload
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    if isinstance(node, bool):
        return None
    if isinstance(node, int):
        return node if node >= 0 else None
    if isinstance(node, str) and node.strip().isdigit():
        return int(node.strip())
    return None

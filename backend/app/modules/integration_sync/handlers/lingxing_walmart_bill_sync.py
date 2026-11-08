"""沃尔玛账单同步（领星 statement/list）：原始响应先落原始层，再写明细表，最后重算每期汇总。

只读接口，按店、按「交易日期」时间段、每页 200 条翻页。默认关闭，手动 / 每周定时 / 回填触发。
- 手动、定时：重拉最近 35 天（上海日期）。回填：用任务里给定的时间段，最早到 2026-03-01。
- 一个时间段按自然月切开；某段条数超过翻页上限就对半再切。
- 每段拉完、条数对得上，才把「这段时间里以前有、这次没有」的明细标成 missing（不删）。
- 领星只在账单生成后才给出明细；一期账单可能横跨 35 天以上，所以发现新账单的明细一直延伸到
  窗口最早几天，就自动往前补拉一个月，直到这期账单的明细不再出现（最多补 12 次）。
- 某一页有一行不合法（店铺对不上、交易日期不在请求的时间段、金额不是数字等）整店失败，
  已有数据不动；一个店失败不影响其他店，但整次任务记为失败。
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx
from pydantic import JsonValue
from sqlalchemy import and_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
)
from app.modules.integration_sync.repository import IntegrationSyncRepository
from app.modules.integration_sync.walmart_bill_catalog import (
    WALMART_BILL_EARLIEST_DATE,
    WALMART_BILL_MAX_EXTENSIONS,
    WALMART_BILL_ROLLING_DAYS,
    WALMART_BILL_SYNC_SPEC,
)
from app.modules.walmart_bills.models import WalmartBillLine
from app.modules.walmart_bills.parsing import (
    BillRowError,
    bill_page,
    line_key,
    parse_bill_row,
    provider_code,
)
from app.modules.walmart_bills.periods import refresh_periods
from app.modules.warehouse_wfs.store_discovery import (
    WfsStoreDiscoveryError,
    discover_walmart_stores,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
EARLIEST = date.fromisoformat(WALMART_BILL_EARLIEST_DATE)
MAX_PAGE_SIZE = 200
MAX_PAGES = 1000
# 新账单最早一笔明细落在窗口开头这么多天以内，就认为它可能还延伸到窗口之前。
EDGE_DAYS = 7
EXTENSION_DAYS = 31


def utc_now() -> datetime:
    return datetime.now(UTC)


class WalmartBillSyncError(RuntimeError):
    """Safe sync error without provider payloads or credentials."""


class WalmartBillPageClient(Protocol):
    def fetch_walmart_bill_page(
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
    ) -> LingxingRawEnvelope: ...


@dataclass(frozen=True, slots=True)
class WalmartBillSyncResult:
    run_id: UUID
    status: str
    stores_total: int
    stores_failed: int
    periods_refreshed: int


@dataclass(slots=True)
class _Segment:
    """一个店、一个时间段这次实际拉到的东西。"""

    first_posted: dict[str, date] = field(default_factory=dict)  # reportKey -> 最早交易日期
    keys: set[str] = field(default_factory=set)


def walmart_bill_response_succeeded(
    endpoint: str,
    response: httpx.Response,
    payload: JsonValue,
) -> bool:
    del response
    return endpoint == WALMART_BILL_SYNC_SPEC.endpoint_path and bill_page(payload) is not None


@contextmanager
def walmart_bill_client() -> Iterator[LingxingReadonlyClient]:
    settings = get_settings()
    _require_runtime(settings)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    client = LingxingReadonlyClient(
        settings,
        token_provider=get_shared_lingxing_token_manager(settings),
        success_evaluator=walmart_bill_response_succeeded,
    )
    try:
        yield client
    finally:
        client.close()


def _require_runtime(settings: Settings) -> None:
    if settings.app_env is AppEnvironment.TEST or not settings.lingxing_enable_real_calls:
        raise WalmartBillSyncError("SYNC_WALMART_BILL_RUNTIME_NOT_AUTHORIZED")


def rolling_window(now: datetime, days: int = WALMART_BILL_ROLLING_DAYS) -> tuple[date, date]:
    """最近 days 天（含今天，上海日期）。"""
    end = now.astimezone(SHANGHAI).date()
    return max(EARLIEST, end - timedelta(days=days - 1)), end


def month_segments(start: date, end: date) -> list[tuple[date, date]]:
    """按自然月切开，旧到新。"""
    segments: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        next_month = (cursor.replace(day=1) + timedelta(days=32)).replace(day=1)
        segment_end = min(end, next_month - timedelta(days=1))
        segments.append((cursor, segment_end))
        cursor = segment_end + timedelta(days=1)
    return segments


def _local_date(value: datetime) -> date:
    if value.tzinfo is None:
        return value.date()
    return value.astimezone(SHANGHAI).date()


class LingxingWalmartBillSyncHandler:
    handler_key = WALMART_BILL_SYNC_SPEC.handler_key

    def __init__(
        self,
        session: Session,
        *,
        client: WalmartBillPageClient | None = None,
        heartbeat: Callable[[], None] | None = None,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self.session = session
        self.repository = IntegrationSyncRepository(session)
        self._client = client
        self.heartbeat = heartbeat or (lambda: None)
        self._now = now

    # ------------------------------------------------------------------ 入口

    def execute(
        self,
        run: IntegrationSyncRun,
        interface: IntegrationInterface,
    ) -> WalmartBillSyncResult:
        config, policy = self._preflight(run, interface)
        start, end = self._window(run)
        try:
            stores = discover_walmart_stores(
                self.session, source_account_ref=run.source_account_ref
            )
        except WfsStoreDiscoveryError as exc:
            raise WalmartBillSyncError("SYNC_WALMART_BILL_NO_STORES") from exc
        page_size = config.page_size or WALMART_BILL_SYNC_SPEC.default_page_size
        max_pages = config.max_pages or WALMART_BILL_SYNC_SPEC.default_max_pages
        if not 1 <= page_size <= MAX_PAGE_SIZE or not 1 <= max_pages <= MAX_PAGES:
            raise WalmartBillSyncError("SYNC_WALMART_BILL_PAGINATION_INVALID")
        names = {store.store_id: store.store_name for store in stores}

        failed = 0
        periods = 0
        with self._client_context() as client:
            for store in stores:
                try:
                    keys = self._sync_store(
                        run,
                        client,
                        policy,
                        store_id=store.store_id,
                        start=start,
                        end=end,
                        page_size=page_size,
                        max_pages=max_pages,
                    )
                    periods += refresh_periods(
                        self.session,
                        source_account_ref=run.source_account_ref,
                        keys={(store.store_id, key) for key in keys},
                        store_names=names,
                        run_id=run.id,
                    )
                    self.session.commit()
                except Exception:
                    self.session.rollback()
                    failed += 1

        run.finished_at = utc_now()
        if failed == 0:
            run.status = "succeeded"
        else:
            run.status = "failed"
            run.error_code = (
                "SYNC_WALMART_BILL_ALL_STORES_FAILED"
                if failed == len(stores)
                else "SYNC_WALMART_BILL_STORE_PARTIAL"
            )
            run.error_message = f"沃尔玛账单同步有 {failed} 个店铺未完成"
        self.session.commit()
        return WalmartBillSyncResult(
            run_id=run.id,
            status=run.status,
            stores_total=len(stores),
            stores_failed=failed,
            periods_refreshed=periods,
        )

    def _client_context(self) -> AbstractContextManager[WalmartBillPageClient]:
        if self._client is not None:
            return _provided_client(self._client)
        return walmart_bill_client()

    def _preflight(
        self,
        run: IntegrationSyncRun,
        interface: IntegrationInterface,
    ) -> tuple[IntegrationSyncConfig, RawRetentionPolicy]:
        spec = WALMART_BILL_SYNC_SPEC
        if (
            run.provider != "lingxing"
            or run.interface_key != spec.interface_key
            or run.trigger_type not in {"manual", "schedule", "retry", "backfill"}
            or run.config_id is None
            or interface.endpoint_path != spec.endpoint_path
            or interface.handler_key != spec.handler_key
            or not interface.outbound_enabled
        ):
            raise WalmartBillSyncError("SYNC_WALMART_BILL_EXECUTION_NOT_AUTHORIZED")
        config = self.repository.get_config(run.config_id, frozenset({run.source_account_ref}))
        policy = self.repository.get_retention_policy(spec.retention_policy_key)
        if config is None or policy is None or not config.is_enabled:
            raise WalmartBillSyncError("SYNC_WALMART_BILL_GOVERNANCE_DISABLED")
        return config, policy

    def _window(self, run: IntegrationSyncRun) -> tuple[date, date]:
        if run.window_start is not None and run.window_end is not None:
            # 回填：window_end 是开区间的时间点，取它前一刻所在的上海日期。
            start = max(EARLIEST, _local_date(run.window_start))
            end = _local_date(run.window_end - timedelta(microseconds=1))
        else:
            start, end = rolling_window(self._now())
        if start > end:
            raise WalmartBillSyncError("SYNC_WALMART_BILL_WINDOW_INVALID")
        return start, end

    # ------------------------------------------------------------------ 一个店

    def _sync_store(
        self,
        run: IntegrationSyncRun,
        client: WalmartBillPageClient,
        policy: RawRetentionPolicy,
        *,
        store_id: str,
        start: date,
        end: date,
        page_size: int,
        max_pages: int,
    ) -> set[str]:
        touched: set[str] = set()
        first_posted: dict[str, date] = {}
        for segment_start, segment_end in month_segments(start, end):
            segment = self._collect(
                run,
                client,
                policy,
                store_id=store_id,
                start=segment_start,
                end=segment_end,
                page_size=page_size,
                max_pages=max_pages,
            )
            touched |= segment.keys
            for key, posted in segment.first_posted.items():
                first_posted[key] = min(posted, first_posted.get(key, posted))

        # 往前补：只追「最早一笔落在窗口开头 EDGE_DAYS 天以内」的账单。
        chasing = {
            key for key, posted in first_posted.items() if posted < start + timedelta(EDGE_DAYS)
        }
        cursor = start
        for _ in range(WALMART_BILL_MAX_EXTENSIONS):
            if not chasing or cursor <= EARLIEST:
                break
            segment_end = cursor - timedelta(days=1)
            segment_start = max(EARLIEST, segment_end - timedelta(days=EXTENSION_DAYS - 1))
            segment = self._collect(
                run,
                client,
                policy,
                store_id=store_id,
                start=segment_start,
                end=segment_end,
                page_size=page_size,
                max_pages=max_pages,
            )
            touched |= segment.keys
            chasing = {
                key
                for key in chasing & segment.keys
                if segment.first_posted[key] < segment_start + timedelta(EDGE_DAYS)
            }
            cursor = segment_start
        return touched

    def _collect(
        self,
        run: IntegrationSyncRun,
        client: WalmartBillPageClient,
        policy: RawRetentionPolicy,
        *,
        store_id: str,
        start: date,
        end: date,
        page_size: int,
        max_pages: int,
    ) -> _Segment:
        """拉一个时间段；条数超过翻页上限就对半切。拉完才做「消失标记」。"""
        segment = _Segment()
        seen: dict[str, int] = {}
        started_at = utc_now()
        offset = 0
        expected: int | None = None
        for page_no in range(1, max_pages + 1):
            work = self._start_work_item(run, store_id, start, end, page_no, offset, page_size)
            try:
                self.heartbeat()
                envelope = client.fetch_walmart_bill_page(
                    store_id=store_id,
                    offset=offset,
                    length=page_size,
                    page_no=page_no,
                    start_date=start,
                    end_date=end,
                    source_account_ref=run.source_account_ref,
                    run_id=str(run.id),
                    work_item_id=str(work.id),
                )
                raw_ref = self._persist_raw(run, work, policy, envelope, store_id, start, end)
            except Exception as exc:
                self.session.rollback()
                self._fail_work(run, work, "SYNC_WALMART_BILL_REQUEST_FAILED")
                raise WalmartBillSyncError("SYNC_WALMART_BILL_REQUEST_FAILED") from exc
            page = bill_page(envelope.response_json) if envelope.is_success else None
            if page is None or len(page.rows) > page_size:
                self._fail_work(run, work, "SYNC_WALMART_BILL_RESPONSE_FAILED")
                raise WalmartBillSyncError("SYNC_WALMART_BILL_RESPONSE_FAILED")
            if expected is None:
                expected = page.total_count
                if expected > max_pages * page_size:
                    self._finish_work(run, work, len(page.rows))
                    if start == end:
                        raise WalmartBillSyncError("SYNC_WALMART_BILL_DAY_PAGE_LIMIT")
                    middle = start + timedelta(days=(end - start).days // 2)
                    first = self._collect(
                        run,
                        client,
                        policy,
                        store_id=store_id,
                        start=start,
                        end=middle,
                        page_size=page_size,
                        max_pages=max_pages,
                    )
                    second = self._collect(
                        run,
                        client,
                        policy,
                        store_id=store_id,
                        start=middle + timedelta(days=1),
                        end=end,
                        page_size=page_size,
                        max_pages=max_pages,
                    )
                    return _merge(first, second)
            elif page.total_count != expected:
                self._fail_work(run, work, "SYNC_WALMART_BILL_TOTAL_CHANGED")
                raise WalmartBillSyncError("SYNC_WALMART_BILL_TOTAL_CHANGED")
            try:
                parsed = [
                    parse_bill_row(
                        row, expected_store_id=store_id, window_start=start, window_end=end
                    )
                    for row in page.rows
                ]
            except BillRowError as exc:
                self._fail_work(run, work, exc.code)
                raise WalmartBillSyncError(exc.code) from exc
            for line in parsed:
                # 同一时间段里组合键撞上的（领星确实会返回完全相同的两笔），按出现顺序编号。
                base = line.pop("identity_base")
                seen[base] = seen.get(base, 0) + 1
                line["line_key"] = line_key(base, seen[base])
                key = line["report_key"]
                segment.keys.add(key)
                posted = line["posted_date"]
                segment.first_posted[key] = min(posted, segment.first_posted.get(key, posted))
            written = self._upsert(run, raw_ref, parsed)
            run.records_seen += len(page.rows)
            run.records_written += written
            self._finish_work(run, work, len(page.rows))
            offset += len(page.rows)
            if not page.rows or offset >= expected:
                break
        if expected is None or offset < expected:
            raise WalmartBillSyncError("SYNC_WALMART_BILL_INCOMPLETE")
        self._mark_missing(run, store_id, start, end, started_at)
        return segment

    # ------------------------------------------------------------------ 写库

    def _upsert(
        self,
        run: IntegrationSyncRun,
        raw_ref: ApiRawRequestRef,
        lines: list[dict[str, object]],
    ) -> int:
        if not lines:
            return 0
        now = utc_now()
        values = [
            {
                **line,
                "id": uuid4(),
                "source_account_ref": run.source_account_ref,
                "raw_request_ref_id": raw_ref.id,
                "first_seen_run_id": run.id,
                "last_seen_run_id": run.id,
                "first_seen_at": now,
                "last_seen_at": now,
                "missing_since": None,
            }
            for line in lines
        ]
        statement = pg_insert(WalmartBillLine).values(values)
        keep = {"id", "source_account_ref", "store_id", "line_key"}
        keep |= {"first_seen_run_id", "first_seen_at"}
        self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["source_account_ref", "store_id", "line_key"],
                set_={
                    column: statement.excluded[column] for column in values[0] if column not in keep
                },
            )
        )
        return len(values)

    def _mark_missing(
        self,
        run: IntegrationSyncRun,
        store_id: str,
        start: date,
        end: date,
        started_at: datetime,
    ) -> None:
        """这段时间以前有、这次没再出现的明细标成 missing；不删除，汇总时不算。

        这次拉到的行在写入时 last_seen_at 已更新到 started_at 之后，所以用时间判断，
        不用把几万个行号塞进 NOT IN。
        """
        self.session.execute(
            update(WalmartBillLine)
            .where(
                and_(
                    WalmartBillLine.source_account_ref == run.source_account_ref,
                    WalmartBillLine.store_id == store_id,
                    WalmartBillLine.posted_date >= start,
                    WalmartBillLine.posted_date <= end,
                    WalmartBillLine.missing_since.is_(None),
                    WalmartBillLine.last_seen_at < started_at,
                )
            )
            .values(missing_since=utc_now(), last_seen_run_id=run.id)
            .execution_options(synchronize_session=False)
        )
        self.session.commit()

    def _start_work_item(
        self,
        run: IntegrationSyncRun,
        store_id: str,
        start: date,
        end: date,
        page_no: int,
        offset: int,
        page_size: int,
    ) -> IntegrationSyncRunWorkItem:
        params = _safe_params(store_id, start, end, offset, page_size)
        work = IntegrationSyncRunWorkItem(
            id=uuid4(),
            run_id=run.id,
            ordinal=run.work_items_total + 1,
            request_kind="offset_page",
            scope_key=f"{store_id}:{start.isoformat()}:{end.isoformat()}:{page_no}",
            status="running",
            attempt_count=0,
            offset_value=offset,
            length_value=page_size,
            request_safe_params=params,
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
        start: date,
        end: date,
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
        page = bill_page(payload)
        ref = self.repository.add_raw_request_ref(
            ApiRawRequestRef(
                id=uuid4(),
                run_id=run.id,
                work_item_id=work.id,
                raw_blob_id=blob.id,
                request_kind="offset_page",
                attempt_no=envelope.attempt_no,
                request_safe_params=_safe_params(
                    store_id, start, end, work.offset_value or 0, work.length_value or 0
                ),
                http_status=envelope.response_code,
                provider_code=provider_code(payload),
                is_success=envelope.is_success,
                response_count=len(page.rows) if page is not None else None,
                requested_at=work.started_at or envelope.pulled_at,
                received_at=envelope.pulled_at,
            )
        )
        work.attempt_count = envelope.attempt_no
        self.session.commit()
        return ref

    def _finish_work(
        self, run: IntegrationSyncRun, work: IntegrationSyncRunWorkItem, rows: int
    ) -> None:
        work.status = "succeeded"
        work.finished_at = utc_now()
        work.response_count = rows
        run.work_items_succeeded += 1
        self.session.commit()

    def _fail_work(
        self,
        run: IntegrationSyncRun,
        work: IntegrationSyncRunWorkItem,
        code: str,
    ) -> None:
        work.status = "failed"
        work.error_code = code
        work.error_message = "沃尔玛账单请求处理失败"
        work.finished_at = utc_now()
        run.work_items_failed += 1
        self.session.commit()


def _safe_params(
    store_id: str, start: date, end: date, offset: int, length: int
) -> dict[str, JsonValue]:
    return {
        "sids": [store_id],
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "offset": offset,
        "length": length,
    }


def _merge(first: _Segment, second: _Segment) -> _Segment:
    merged = _Segment(first_posted=dict(first.first_posted), keys=first.keys | second.keys)
    for key, posted in second.first_posted.items():
        merged.first_posted[key] = min(posted, merged.first_posted.get(key, posted))
    return merged


@contextmanager
def _provided_client(client: WalmartBillPageClient) -> Iterator[WalmartBillPageClient]:
    yield client

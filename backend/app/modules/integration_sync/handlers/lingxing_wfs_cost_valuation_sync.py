"""Governed sync for the Lingxing WFS cost valuation flow (LX-8437AD0BCB9E).

Rules (PRPs/wfs-inventory-claim.md §7.1–§7.3):

* one run pulls one ``dateType = 0`` window for every store, without ``businessType``;
* rows are staged with ``is_current = false`` keyed by (raw request, row position);
* only after every page succeeded and the row count equals the provider total, a single
  transaction retires the window's previous current rows and promotes the new ones;
* a failed run leaves the previous current rows untouched;
* one run per source account at a time (run-table check plus a PostgreSQL advisory lock).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.core.config import AppEnvironment, Settings, get_settings
from app.integrations.lingxing.client import LingxingRawEnvelope, LingxingReadonlyClient
from app.integrations.lingxing.security import canonical_json, redact_json
from app.integrations.lingxing.token_manager import get_shared_lingxing_token_manager
from app.integrations.lingxing.wfs_cost_valuation_contracts import (
    WFS_COST_VALUATION_MAX_PAGE_SIZE,
    WfsCostValuationContractError,
    validate_wfs_cost_valuation_window,
    wfs_cost_valuation_provider_code,
    wfs_cost_valuation_records,
    wfs_cost_valuation_response_succeeded,
    wfs_cost_valuation_total,
)
from app.modules.data_pages.models import LingxingStoreDimension
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
from app.modules.integration_sync.wfs_cost_valuation_catalog import WFS_COST_VALUATION_SYNC_SPEC
from app.modules.warehouse_wfs.inventory_flow_models import WfsCostValuationFlowOds

logger = logging.getLogger("app.integration_sync.wfs_cost_valuation")

SPEC = WFS_COST_VALUATION_SYNC_SPEC
STORE_CODE_LENGTH = 6
ALLOWED_TRIGGERS = frozenset({"manual", "schedule", "retry", "backfill"})
HASH_EXCLUDED_FIELDS = frozenset({"imageUrl"})
AMOUNT_FIELDS = (
    ("orderBasePurchaseAmount", "order_base_purchase_amount"),
    ("purchaseTotalAmount", "purchase_total_amount"),
    ("orderBaseLogisticsAmount", "order_base_logistics_amount"),
    ("logisticsTotalAmount", "logistics_total_amount"),
    ("orderBaseOtherAmount", "order_base_other_amount"),
    ("otherTotalAmount", "other_total_amount"),
)
TEXT_FIELDS = (
    ("msku", "msku"),
    ("gtin", "gtin"),
    ("localSku", "local_sku"),
    ("businessName", "business_name"),
    ("businessDesc", "business_desc"),
    ("businessNumber", "business_number"),
    ("orderNumber", "order_number"),
    ("costSource", "cost_source"),
)
MONEY_QUANTUM = Decimal("0.0001")
MONEY_LIMIT = Decimal("100000000000000")  # numeric(18, 4)


class WfsCostValuationPageClient(Protocol):
    def fetch_wfs_cost_valuation_page(
        self,
        *,
        start_date: date,
        end_date: date,
        offset: int,
        length: int,
        page_no: int,
        source_account_ref: str,
        run_id: str,
        work_item_id: str,
    ) -> LingxingRawEnvelope: ...


class WfsCostValuationSyncError(RuntimeError):
    """Safe sync error without provider payloads or credentials."""


@dataclass(frozen=True, slots=True)
class WfsCostValuationSyncResult:
    run_id: UUID
    status: str
    error_code: str | None
    records_written: int
    records_superseded: int


@dataclass(frozen=True, slots=True)
class StoreDirectory:
    by_sid: dict[str, str | None]
    by_code: dict[str, str | None]

    def resolve(self, sid: str | None, store_code: str) -> str | None:
        """Unique match by provider sid, then by store-name prefix; ambiguity maps to None."""
        if sid:
            match = self.by_sid.get(sid)
            if match is not None:
                return match
        return self.by_code.get(store_code)


@contextmanager
def wfs_cost_valuation_client() -> Iterator[LingxingReadonlyClient]:
    settings = get_settings()
    _require_runtime(settings)
    client = LingxingReadonlyClient(
        settings,
        token_provider=get_shared_lingxing_token_manager(settings),
        success_evaluator=wfs_cost_valuation_response_succeeded,
    )
    try:
        yield client
    finally:
        client.close()


def _require_runtime(settings: Settings) -> None:
    if settings.app_env is not AppEnvironment.PRODUCTION or not settings.lingxing_enable_real_calls:
        raise WfsCostValuationSyncError("SYNC_WFS_FLOW_RUNTIME_NOT_AUTHORIZED")


@contextmanager
def _provided(client: WfsCostValuationPageClient) -> Iterator[WfsCostValuationPageClient]:
    yield client


def store_code_from_seller_name(value: JsonValue) -> str | None:
    if not isinstance(value, str):
        return None
    code = value.strip()[:STORE_CODE_LENGTH].strip()
    return code or None


def load_store_directory(session: Session, source_account_ref: str) -> StoreDirectory:
    rows = session.execute(
        select(
            LingxingStoreDimension.store_id,
            LingxingStoreDimension.store_name,
            LingxingStoreDimension.sid,
        ).where(LingxingStoreDimension.source_account_ref == source_account_ref)
    ).all()
    by_sid: dict[str, set[str]] = {}
    by_code: dict[str, set[str]] = {}
    for store_id, store_name, sid in rows:
        if sid:
            by_sid.setdefault(str(sid).strip(), set()).add(store_id)
        code = store_code_from_seller_name(store_name)
        if code:
            by_code.setdefault(code, set()).add(store_id)
    return StoreDirectory(
        by_sid={key: next(iter(ids)) if len(ids) == 1 else None for key, ids in by_sid.items()},
        by_code={key: next(iter(ids)) if len(ids) == 1 else None for key, ids in by_code.items()},
    )


def _text(value: JsonValue) -> str | None:
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    result = str(value).strip()
    return result or None


def _amount(value: JsonValue) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or isinstance(value, (dict, list)):
        raise WfsCostValuationSyncError("SYNC_WFS_FLOW_RECORD_INVALID")
    try:
        amount = Decimal(str(value)).quantize(MONEY_QUANTUM)
    except (InvalidOperation, ValueError):
        raise WfsCostValuationSyncError("SYNC_WFS_FLOW_RECORD_INVALID") from None
    if not amount.is_finite() or abs(amount) >= MONEY_LIMIT:
        raise WfsCostValuationSyncError("SYNC_WFS_FLOW_RECORD_INVALID")
    return amount


def _quantity(value: JsonValue) -> int:
    if isinstance(value, bool) or value is None or isinstance(value, (dict, list)):
        raise WfsCostValuationSyncError("SYNC_WFS_FLOW_RECORD_INVALID")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise WfsCostValuationSyncError("SYNC_WFS_FLOW_RECORD_INVALID") from None
    if not number.is_finite() or number != number.to_integral_value():
        raise WfsCostValuationSyncError("SYNC_WFS_FLOW_RECORD_INVALID")
    return int(number)


def _local_datetime(value: JsonValue, *, required: bool) -> datetime | None:
    raw = _text(value)
    if raw is None:
        if required:
            raise WfsCostValuationSyncError("SYNC_WFS_FLOW_RECORD_INVALID")
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, pattern)
        except ValueError:
            continue
    raise WfsCostValuationSyncError("SYNC_WFS_FLOW_RECORD_INVALID")


def row_hash(record: dict[str, JsonValue]) -> str:
    business = {key: value for key, value in record.items() if key not in HASH_EXCLUDED_FIELDS}
    return hashlib.sha256(canonical_json(business).encode("utf-8")).hexdigest()


def parse_record(record: JsonValue, stores: StoreDirectory) -> dict[str, object]:
    """Map one provider record to typed columns. Raises on any unusable row."""
    if not isinstance(record, dict):
        raise WfsCostValuationSyncError("SYNC_WFS_FLOW_RECORD_INVALID")
    date_local = _local_datetime(record.get("dateLocal"), required=True)
    assert date_local is not None
    settlement = _local_datetime(record.get("date1"), required=False)
    business_type = _text(record.get("businessType"))
    store_code = store_code_from_seller_name(record.get("sellerName"))
    if business_type is None or len(business_type) > 32 or store_code is None:
        raise WfsCostValuationSyncError("SYNC_WFS_FLOW_RECORD_INVALID")
    serial = _text(record.get("serialNumber"))
    if serial is not None and len(serial) > 32:
        raise WfsCostValuationSyncError("SYNC_WFS_FLOW_RECORD_INVALID")
    sid = _text(record.get("sid"))
    store_id = stores.resolve(sid, store_code)
    columns: dict[str, object] = {
        "serial_number": serial,
        "date_local": date_local,
        "business_date": date_local.date(),
        "settlement_date": settlement.date() if settlement is not None else None,
        "store_code": store_code,
        "store_id": store_id,
        "store_mapping_status": "mapped" if store_id is not None else "unmapped",
        "business_type": business_type,
        "quantity": _quantity(record.get("quantity")),
        # Currency is not documented by the provider; stays NULL until probed (PRP §15.2).
        "currency_code": None,
        "row_hash": row_hash(record),
        "payload_json": redact_json(record),
    }
    for source, target in TEXT_FIELDS:
        columns[target] = _text(record.get(source))
    for source, target in AMOUNT_FIELDS:
        columns[target] = _amount(record.get(source))
    return columns


def advisory_lock_key(source_account_ref: str) -> int:
    digest = hashlib.sha256(f"{SPEC.interface_key}|{source_account_ref}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


class LingxingWfsCostValuationSyncHandler:
    handler_key = SPEC.handler_key

    def __init__(
        self,
        session: Session,
        *,
        client: WfsCostValuationPageClient | None = None,
        settings: Settings | None = None,
        heartbeat: Callable[[], None] | None = None,
    ) -> None:
        self.session = session
        self.repository = IntegrationSyncRepository(session)
        self._client = client
        self.settings = settings or get_settings()
        self.heartbeat = heartbeat or (lambda: None)

    # ------------------------------------------------------------------ entry
    def execute(
        self, run: IntegrationSyncRun, interface: IntegrationInterface
    ) -> WfsCostValuationSyncResult:
        try:
            config, policy, window = self._preflight(run, interface)
        except WfsCostValuationSyncError as error:
            return self._fail(run, None, str(error))
        page_size = config.page_size or SPEC.default_page_size
        max_pages = config.max_pages or SPEC.default_max_pages
        if not 1 <= page_size <= WFS_COST_VALUATION_MAX_PAGE_SIZE or max_pages < 1:
            return self._fail(run, None, "SYNC_WFS_FLOW_PAGINATION_INVALID")
        if self._other_run_active(run):
            return self._fail(run, None, "SYNC_WFS_FLOW_CONCURRENT_RUN")
        if not self._acquire_account_lock(run.source_account_ref):
            return self._fail(run, None, "SYNC_WFS_FLOW_CONCURRENT_RUN")
        try:
            if self._client is None:
                try:
                    _require_runtime(self.settings)
                except WfsCostValuationSyncError as error:
                    return self._fail(run, None, str(error))
            if run.status != "running":
                run.status = "running"
                run.started_at = run.started_at or utc_now()
                self.session.commit()
            stores = load_store_directory(self.session, run.source_account_ref)
            context = (
                _provided(self._client) if self._client is not None else wfs_cost_valuation_client()
            )
            with context as client:
                return self._pull(run, client, policy, window, page_size, max_pages, stores)
        finally:
            self._release_account_lock(run.source_account_ref)

    # -------------------------------------------------------------- preflight
    def _preflight(
        self, run: IntegrationSyncRun, interface: IntegrationInterface
    ) -> tuple[IntegrationSyncConfig, RawRetentionPolicy, tuple[date, date]]:
        if (
            run.provider != "lingxing"
            or run.interface_key != SPEC.interface_key
            or interface.handler_key != SPEC.handler_key
            or interface.endpoint_path != SPEC.endpoint_path
            or not interface.outbound_enabled
            or run.trigger_type not in ALLOWED_TRIGGERS
            or run.config_id is None
        ):
            raise WfsCostValuationSyncError("SYNC_WFS_FLOW_EXECUTION_NOT_AUTHORIZED")
        config = self.repository.get_config(run.config_id, frozenset({run.source_account_ref}))
        if config is None or not config.is_enabled:
            raise WfsCostValuationSyncError("SYNC_WFS_FLOW_CONFIG_DISABLED")
        policy = self.repository.get_retention_policy(SPEC.retention_policy_key)
        if policy is None:
            raise WfsCostValuationSyncError("SYNC_WFS_FLOW_RETENTION_POLICY_MISSING")
        if run.window_start is None or run.window_end is None:
            raise WfsCostValuationSyncError("SYNC_WFS_FLOW_WINDOW_REQUIRED")
        start = (
            run.window_start.date() if isinstance(run.window_start, datetime) else run.window_start
        )
        end = run.window_end.date() if isinstance(run.window_end, datetime) else run.window_end
        try:
            validate_wfs_cost_valuation_window(start, end)
        except WfsCostValuationContractError:
            raise WfsCostValuationSyncError("SYNC_WFS_FLOW_WINDOW_INVALID") from None
        return config, policy, (start, end)

    # ------------------------------------------------------- account locking
    def _other_run_active(self, run: IntegrationSyncRun) -> bool:
        other = self.session.scalar(
            select(func.count())
            .select_from(IntegrationSyncRun)
            .where(
                IntegrationSyncRun.provider == run.provider,
                IntegrationSyncRun.interface_key == SPEC.interface_key,
                IntegrationSyncRun.source_account_ref == run.source_account_ref,
                IntegrationSyncRun.status == "running",
                IntegrationSyncRun.id != run.id,
            )
        )
        return bool(other)

    def _is_postgresql(self) -> bool:
        bind = self.session.get_bind()
        return bind.dialect.name == "postgresql"

    def _acquire_account_lock(self, source_account_ref: str) -> bool:
        if not self._is_postgresql():
            return True
        acquired = self.session.scalar(
            text("SELECT pg_try_advisory_lock(:key)"),
            {"key": advisory_lock_key(source_account_ref)},
        )
        self.session.commit()
        return bool(acquired)

    def _release_account_lock(self, source_account_ref: str) -> None:
        if not self._is_postgresql():
            return
        try:
            self.session.rollback()
            self.session.execute(
                text("SELECT pg_advisory_unlock(:key)"),
                {"key": advisory_lock_key(source_account_ref)},
            )
            self.session.commit()
        except Exception:  # pragma: no cover - lock dies with the connection anyway
            self.session.rollback()
            logger.warning("wfs_cost_valuation_unlock_failed")

    # ------------------------------------------------------------------ pull
    def _pull(
        self,
        run: IntegrationSyncRun,
        client: WfsCostValuationPageClient,
        policy: RawRetentionPolicy,
        window: tuple[date, date],
        page_size: int,
        max_pages: int,
        stores: StoreDirectory,
    ) -> WfsCostValuationSyncResult:
        offset = 0
        written = 0
        expected_total: int | None = None
        for page_no in range(1, max_pages + 1):
            self.heartbeat()
            work = self._start_work_item(run, page_no, offset, page_size, window)
            try:
                envelope = client.fetch_wfs_cost_valuation_page(
                    start_date=window[0],
                    end_date=window[1],
                    offset=offset,
                    length=page_size,
                    page_no=page_no,
                    source_account_ref=run.source_account_ref,
                    run_id=str(run.id),
                    work_item_id=str(work.id),
                )
            except Exception:
                self.session.rollback()
                return self._fail(run, work, "SYNC_WFS_FLOW_TRANSPORT_FAILED")
            raw_ref = None
            if envelope.response_json is not None:
                raw_ref = self._persist_raw(run, work, policy, envelope)
            if not envelope.is_success or envelope.response_json is None or raw_ref is None:
                return self._fail(run, work, envelope.error_code or "SYNC_WFS_FLOW_RESPONSE_FAILED")
            records = wfs_cost_valuation_records(envelope.response_json)
            total = wfs_cost_valuation_total(envelope.response_json)
            if records is None or total is None:
                return self._fail(run, work, "SYNC_WFS_FLOW_RESPONSE_SHAPE_INVALID")
            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                return self._fail(run, work, "SYNC_WFS_FLOW_TOTAL_CHANGED")
            if len(records) > page_size or offset + len(records) > expected_total:
                return self._fail(run, work, "SYNC_WFS_FLOW_TOTAL_MISMATCH")
            if not records and offset < expected_total:
                return self._fail(run, work, "SYNC_WFS_FLOW_INCOMPLETE_PAGE")
            if records and len(records) < page_size and offset + len(records) < expected_total:
                return self._fail(run, work, "SYNC_WFS_FLOW_INCOMPLETE_PAGE")
            try:
                written += self._stage_page(run, work, raw_ref, envelope, records, window, stores)
            except WfsCostValuationSyncError as error:
                self.session.rollback()
                return self._recover_and_fail(run.id, work.id, str(error))
            except Exception:
                self.session.rollback()
                return self._recover_and_fail(run.id, work.id, "SYNC_WFS_FLOW_PUBLISH_FAILED")
            offset += len(records)
            if offset >= expected_total:
                return self._promote(run, window, written, expected_total)
        return self._fail(run, None, "SYNC_WFS_FLOW_MAX_PAGES_REACHED")

    def _start_work_item(
        self,
        run: IntegrationSyncRun,
        page_no: int,
        offset: int,
        length: int,
        window: tuple[date, date],
    ) -> IntegrationSyncRunWorkItem:
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
                "date_type": 0,
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
        records = wfs_cost_valuation_records(payload)
        count = len(records) if records is not None else None
        ref = self.repository.add_raw_request_ref(
            ApiRawRequestRef(
                id=uuid4(),
                run_id=run.id,
                work_item_id=work.id,
                raw_blob_id=blob.id,
                request_kind="offset_page",
                attempt_no=envelope.attempt_no,
                request_safe_params=work.request_safe_params,
                http_status=envelope.response_code,
                provider_code=wfs_cost_valuation_provider_code(payload),
                is_success=envelope.is_success,
                response_count=count,
                requested_at=work.started_at or envelope.pulled_at,
                received_at=envelope.pulled_at,
            )
        )
        work.attempt_count = envelope.attempt_no
        work.response_count = count
        run.records_seen += count or 0
        self.session.commit()
        return ref

    def _stage_page(
        self,
        run: IntegrationSyncRun,
        work: IntegrationSyncRunWorkItem,
        raw_ref: ApiRawRequestRef,
        envelope: LingxingRawEnvelope,
        records: list[JsonValue],
        window: tuple[date, date],
        stores: StoreDirectory,
    ) -> int:
        rows = [
            WfsCostValuationFlowOds(
                id=uuid4(),
                run_id=run.id,
                raw_request_ref_id=raw_ref.id,
                source_account_ref=run.source_account_ref,
                source_item_ordinal=ordinal,
                window_start=window[0],
                window_end=window[1],
                is_current=False,
                observed_at=envelope.pulled_at,
                **parse_record(record, stores),
            )
            for ordinal, record in enumerate(records)
        ]
        self.repository.add_ods_records(rows)
        work.status = "succeeded"
        work.finished_at = utc_now()
        run.work_items_succeeded += 1
        self.session.commit()
        return len(rows)

    def _promote(
        self,
        run: IntegrationSyncRun,
        window: tuple[date, date],
        written: int,
        expected_total: int,
    ) -> WfsCostValuationSyncResult:
        staged = self.session.scalar(
            select(func.count())
            .select_from(WfsCostValuationFlowOds)
            .where(WfsCostValuationFlowOds.run_id == run.id)
        )
        if staged != expected_total or written != expected_total:
            return self._fail(run, None, "SYNC_WFS_FLOW_ROW_COUNT_MISMATCH")
        try:
            retired = self.session.execute(
                update(WfsCostValuationFlowOds)
                .where(
                    WfsCostValuationFlowOds.source_account_ref == run.source_account_ref,
                    WfsCostValuationFlowOds.is_current.is_(True),
                    WfsCostValuationFlowOds.business_date >= window[0],
                    WfsCostValuationFlowOds.business_date <= window[1],
                    WfsCostValuationFlowOds.run_id != run.id,
                )
                .values(is_current=False, superseded_by_run_id=run.id)
                .execution_options(synchronize_session=False)
            ).rowcount
            self.session.execute(
                update(WfsCostValuationFlowOds)
                .where(WfsCostValuationFlowOds.run_id == run.id)
                .values(is_current=True)
                .execution_options(synchronize_session=False)
            )
            run.status = "succeeded"
            run.records_written += written
            run.finished_at = utc_now()
            self.session.commit()
        except Exception:
            self.session.rollback()
            return self._recover_and_fail(run.id, None, "SYNC_WFS_FLOW_PROMOTE_FAILED")
        logger.info(
            "wfs_cost_valuation_sync_succeeded run_id=%s written=%s superseded=%s",
            run.id,
            written,
            retired,
        )
        return WfsCostValuationSyncResult(
            run_id=run.id,
            status="succeeded",
            error_code=None,
            records_written=written,
            records_superseded=int(retired or 0),
        )

    # --------------------------------------------------------------- failure
    def _recover_and_fail(
        self, run_id: UUID, work_item_id: UUID | None, error_code: str
    ) -> WfsCostValuationSyncResult:
        run = self.repository.get_run_for_update(run_id)
        if run is None:
            raise WfsCostValuationSyncError("SYNC_WFS_FLOW_RUN_MISSING")
        work = (
            self.repository.get_work_item_for_update(run_id, work_item_id)
            if work_item_id is not None
            else None
        )
        return self._fail(run, work, error_code)

    def _fail(
        self,
        run: IntegrationSyncRun,
        work: IntegrationSyncRunWorkItem | None,
        error_code: str,
    ) -> WfsCostValuationSyncResult:
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
        logger.warning("wfs_cost_valuation_sync_failed run_id=%s code=%s", run.id, error_code)
        return WfsCostValuationSyncResult(
            run_id=run.id,
            status="failed",
            error_code=error_code,
            records_written=0,
            records_superseded=0,
        )

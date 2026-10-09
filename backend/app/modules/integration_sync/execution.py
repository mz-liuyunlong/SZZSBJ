import hashlib
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.integration_sync.data_pages_business_rules_v4 import DataPagesRealSyncRunner
from app.modules.integration_sync.data_pages_real_sync import (
    DataPagesRealSyncSummary,
    data_pages_client,
)
from app.modules.integration_sync.handlers.lingxing_batch_product_info import (
    BatchPlan,
    LingxingBatchGetProductInfoSyncHandler,
)
from app.modules.integration_sync.handlers.lingxing_pmc_purchase_sync import (
    PMC_PURCHASE_HANDLERS,
)
from app.modules.integration_sync.handlers.lingxing_product_info_executor import (
    PRODUCT_INFO_BATCH_SIZE,
    LingxingProductInfoExecutor,
    product_info_client,
)
from app.modules.integration_sync.handlers.lingxing_product_list_sync import (
    LingxingProductListSyncHandler,
)
from app.modules.integration_sync.models import (
    IntegrationSyncConfig,
    IntegrationSyncLock,
    IntegrationSyncRun,
    IntegrationSyncRunEvent,
    utc_now,
)
from app.modules.integration_sync.product_info_runner import ProductInfoOneTimeRunError
from app.modules.integration_sync.repository import IntegrationSyncRepository

LOCK_LEASE_DURATION = timedelta(minutes=5)
DATA_PAGES_LA_TZ = ZoneInfo("America/Los_Angeles")
DATA_PAGES_DEFAULT_PAGE_SIZE = 100
DATA_PAGES_DEFAULT_CAMPAIGN_TYPE = "SP"
DATA_PAGES_DEFAULT_MAX_ADVERTISERS = 20
DATA_PAGES_MAX_BACKFILL_DAYS = 31
DATA_PAGES_EXECUTABLE_INTERFACE_KEYS = frozenset(
    {
        "walmartListingList",
        "saleStatPageList",
        "walmartReturnOrderList",
        "walmartAdItemSpList",
    }
)


class SyncRunExecutionService:
    """Durable governed execution for supported integration runs."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = IntegrationSyncRepository(session)

    def execute(self, run_id: UUID) -> None:
        run = self.repository.get_run_for_update(run_id)
        if run is None or run.status != "queued":
            return
        interface = self.repository.get_interface(run.interface_id)
        if interface is None:
            self._fail(run, "SYNC_INTERFACE_NOT_FOUND")
            return
        is_data_pages = (
            run.provider == "lingxing"
            and run.interface_key in DATA_PAGES_EXECUTABLE_INTERFACE_KEYS
            and interface.method == "POST"
        )
        is_productlist = run.provider == "lingxing" and run.interface_key == "productList"

        purchase_handler = PMC_PURCHASE_HANDLERS.get(run.interface_key)
        if (
            run.provider == "lingxing"
            and purchase_handler is not None
            and interface.handler_key == purchase_handler.handler_key
        ):
            purchase_handler(self.session).execute(run, interface)
            return

        is_productinfo = (
            run.provider == "lingxing"
            and run.interface_key == "batchGetProductInfo"
            and interface.handler_key == LingxingBatchGetProductInfoSyncHandler.handler_key
        )
        if is_productinfo:
            if not interface.outbound_enabled:
                self._fail(run, "SYNC_INTERFACE_DISABLED")
                return
            if run.trigger_type not in {"manual", "schedule", "retry"}:
                self._fail(run, "SYNC_TRIGGER_NOT_EXECUTABLE")
                return
            if run.config_id is None:
                self._fail(run, "SYNC_CONFIG_NOT_FOUND")
                return
            config = self.repository.get_config(
                run.config_id,
                frozenset({run.source_account_ref}),
            )
            if config is None:
                self._fail(run, "SYNC_CONFIG_NOT_FOUND")
                return
            if not config.is_enabled:
                self._fail(run, "SYNC_CONFIG_DISABLED")
                return

        if is_data_pages:
            if run.trigger_type not in {"manual", "schedule", "retry", "backfill"}:
                self._fail(run, "SYNC_TRIGGER_NOT_EXECUTABLE")
                return
            if run.config_id is None:
                self._fail(run, "SYNC_CONFIG_NOT_FOUND")
                return
            config = self.repository.get_config(
                run.config_id,
                frozenset({run.source_account_ref}),
            )
            if config is None:
                self._fail(run, "SYNC_CONFIG_NOT_FOUND")
                return
            if not config.is_enabled:
                self._fail(run, "SYNC_CONFIG_DISABLED")
                return

        now = utc_now()
        lock_interface_key = "dataPages" if is_data_pages else run.interface_key
        existing_lock = self.repository.get_lock_for_interface(run.provider, lock_interface_key)
        if existing_lock is not None:
            if existing_lock.expires_at > now:
                self.session.rollback()
                return
            stale_run = self.repository.get_run_for_update(existing_lock.run_id)
            if stale_run is not None and stale_run.status == "running":
                stale_run.status = "failed"
                stale_run.finished_at = now
                stale_run.error_code = "SYNC_LOCK_LEASE_EXPIRED"
                stale_run.error_message = "同步锁租约已过期"
                running_work_items = self.repository.list_running_work_items_for_update(
                    stale_run.id
                )
                for work in running_work_items:
                    work.status = "failed"
                    work.finished_at = now
                    work.error_code = "SYNC_LOCK_LEASE_EXPIRED"
                    work.error_message = "同步锁租约已过期"
                stale_run.work_items_failed += len(running_work_items)
                self._event(
                    stale_run.id,
                    "running",
                    "failed",
                    "SYNC_LOCK_LEASE_EXPIRED",
                )
            self.repository.delete_lock(existing_lock)

        token = uuid4().hex
        lease = IntegrationSyncLock(
            id=uuid4(),
            provider=run.provider,
            interface_key=lock_interface_key,
            run_id=run.id,
            lock_token_hash=hashlib.sha256(token.encode()).hexdigest(),
            acquired_at=now,
            heartbeat_at=now,
            expires_at=now + LOCK_LEASE_DURATION,
        )
        try:
            self.repository.add_lock(lease)
            run.status = "running"
            run.started_at = now
            self._event(run.id, "queued", "running", "SYNC_RUN_STARTED")
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            return

        try:
            if is_data_pages:
                self._execute_data_pages_run(run)
                return

            if is_productlist:
                result = LingxingProductListSyncHandler(
                    self.session,
                    heartbeat=lambda: self._heartbeat_lock(run.id),
                ).execute(run, interface)
                if getattr(result, "status", None) == "succeeded":
                    child_run = self._queue_product_info_child_run(run)
                    if child_run is not None and child_run.status == "queued":
                        self.execute(child_run.id)
                return

            if interface.handler_key != LingxingBatchGetProductInfoSyncHandler.handler_key:
                self._fail(run, "SYNC_HANDLER_NOT_EXECUTABLE")
                return

            plan = self.load_or_freeze_product_info_plan(run)
            if plan is None:
                return

            with product_info_client() as client:
                LingxingProductInfoExecutor(
                    self.session,
                    client=client,
                    heartbeat=lambda: self._heartbeat_lock(run.id),
                ).execute_existing_run(
                    run=run,
                    plan=plan,
                )
        except ProductInfoOneTimeRunError as error:
            self.session.rollback()
            recovered = self.repository.get_run_for_update(run_id)
            if recovered is not None and recovered.status == "running":
                self._fail(recovered, _safe_error_code(error))
        except Exception:
            self.session.rollback()
            recovered = self.repository.get_run_for_update(run_id)
            if recovered is not None and recovered.status == "running":
                self._fail(recovered, "SYNC_EXECUTION_FAILED")
            raise
        finally:
            current_lock = self.repository.get_lock_for_run(run_id)
            if current_lock is not None:
                self.repository.delete_lock(current_lock)
                self.session.commit()

    def _queue_product_info_child_run(
        self,
        parent_run: IntegrationSyncRun,
    ) -> IntegrationSyncRun | None:
        """Queue ProductInfo as the second phase of Product Management sync."""

        interface = self.repository.get_interface_by_key("lingxing", "batchGetProductInfo")
        if interface is None:
            self.repository.add_event(
                IntegrationSyncRunEvent(
                    run_id=parent_run.id,
                    sequence_no=self.repository.next_event_sequence(parent_run.id),
                    event_type="dependency_missing",
                    from_status=parent_run.status,
                    to_status=parent_run.status,
                    message_code="PRODUCT_INFO_INTERFACE_MISSING",
                    safe_details=None,
                    occurred_at=utc_now(),
                    actor_ref="worker",
                )
            )
            self.session.commit()
            return None

        config = self.repository.get_config_by_scope(
            interface.id,
            parent_run.source_account_ref,
        )
        idempotency_key = f"product-management:{parent_run.id}:batchGetProductInfo"
        existing = self.repository.find_run_by_idempotency(idempotency_key)
        if existing is not None:
            return existing

        child = IntegrationSyncRun(
            config_id=config.id if config is not None else None,
            interface_id=interface.id,
            provider=interface.provider,
            interface_key=interface.interface_key,
            source_account_ref=parent_run.source_account_ref,
            trigger_type=parent_run.trigger_type,
            status="queued",
            parent_run_id=parent_run.id,
            retry_of_run_id=None,
            idempotency_key=idempotency_key,
            requested_by=parent_run.requested_by or "worker",
            request_id=parent_run.request_id,
            reason="product_management_detail_sync",
            window_start=parent_run.window_start,
            window_end=parent_run.window_end,
            queued_at=utc_now(),
            work_items_total=0,
            work_items_succeeded=0,
            work_items_failed=0,
            records_seen=0,
            records_written=0,
        )
        self.repository.add_run(child)
        self.repository.add_event(
            IntegrationSyncRunEvent(
                run_id=child.id,
                sequence_no=1,
                event_type="state_transition",
                from_status=None,
                to_status="queued",
                message_code="SYNC_RUN_QUEUED",
                safe_details={"parent_interface_key": parent_run.interface_key},
                occurred_at=utc_now(),
                actor_ref="worker",
            )
        )
        self.session.commit()
        return child

    def _execute_data_pages_run(self, run: IntegrationSyncRun) -> None:
        """Execute configured DATA-PAGES business tasks.

        Four frontend-configurable Data Pages tasks are executable:
        - walmartListingList: store + listing + Listing MART.
        - saleStatPageList: sales + orders + Daily Sales/Profit MARTs.
        - walmartReturnOrderList: refunds + Daily Sales/Profit MARTs.
        - walmartAdItemSpList: advertiser/ad facts + Daily Sales/Profit MARTs.
        Raw child interfaces remain visible for governance but are not standalone
        production schedules.
        """

        if run.interface_key == "walmartListingList":
            self._execute_listing_management_run(run)
            return

        config = None
        if run.config_id is not None:
            config = self.repository.get_config(run.config_id, frozenset({run.source_account_ref}))

        days = self._data_pages_business_dates_for_run(run, config)
        if not days:
            self._fail(run, "DATA_PAGES_RUN_DATE_RANGE_INVALID")
            return

        page_size = (
            config.page_size
            if config is not None and config.page_size is not None
            else DATA_PAGES_DEFAULT_PAGE_SIZE
        )
        if not 1 <= page_size <= 200:
            self._fail(run, "DATA_PAGES_PAGE_SIZE_INVALID")
            return

        run.work_items_total = len(days)
        self.session.commit()

        records_seen = 0
        records_written = 0

        with data_pages_client() as client:
            for business_date in days:
                runner = DataPagesRealSyncRunner(
                    session=self.session,
                    client=client,
                    source_account_ref=run.source_account_ref,
                    business_date=business_date,
                    page_size=page_size,
                    campaign_type=DATA_PAGES_DEFAULT_CAMPAIGN_TYPE,
                    max_advertisers=DATA_PAGES_DEFAULT_MAX_ADVERTISERS,
                    heartbeat=lambda: self._heartbeat_lock(run.id),
                )
                summary = self._execute_data_pages_interface(run.interface_key, runner)

                records_seen += (
                    summary.store_rows
                    + summary.listing_rows
                    + summary.advertiser_rows
                    + summary.sales_rows
                    + summary.order_rows
                    + summary.refund_rows
                    + summary.ad_rows
                )
                records_written += (
                    summary.mart_daily_sales_rows
                    + summary.mart_order_profit_rows
                    + summary.mart_listing_rows
                )
                self._heartbeat_lock(run.id)

        completed = self.repository.get_run_for_update(run.id)
        if completed is None:
            return
        from_status = completed.status
        completed.status = "succeeded"
        completed.finished_at = utc_now()
        completed.work_items_succeeded = len(days)
        completed.work_items_failed = 0
        completed.records_seen = records_seen
        completed.records_written = records_written
        completed.error_code = None
        completed.error_message = None
        self._event(completed.id, from_status, "succeeded", "SYNC_RUN_SUCCEEDED")
        self.session.commit()

    def _execute_data_pages_interface(
        self,
        interface_key: str,
        runner: DataPagesRealSyncRunner,
    ) -> DataPagesRealSyncSummary:
        """Run only the dataset represented by the configured task."""

        def heartbeat() -> None:
            if runner.heartbeat is not None:
                runner.heartbeat()

        if interface_key in {"saleStatPageList", "walmartReturnOrderList"}:
            stores = runner._fetch_offset_all(
                "seller_list_multi_platform",
                runner._seller_body,
                minimum_page_size=20,
            )
            runner.store_ids = tuple(
                dict.fromkeys(
                    value
                    for row in stores
                    if (value := str(row.get("store_id") or row.get("sid") or "").strip())
                )
            )
            if not runner.store_ids:
                raise ValueError("Data Pages store scope is empty")
            heartbeat()
            runner.summary.store_rows = runner._write_stores(stores)

        if interface_key == "saleStatPageList":
            sales_rows: list[dict[str, Any]] = []
            for result_type in (1, 2, 3):
                rows = runner._fetch_page_all(
                    "sale_stat_page_list",
                    lambda page, size, result_type=result_type: runner._sale_stat_body(
                        page,
                        size,
                        result_type,
                    ),
                    body_suffix=f"result_type={result_type}",
                )
                sales_rows.extend({**row, "_result_type": result_type} for row in rows)
            orders = runner._fetch_offset_all(
                "order_v2_list",
                runner._order_body,
                minimum_page_size=20,
            )
            heartbeat()
            runner.summary.sales_rows = runner._write_sales(sales_rows)
            heartbeat()
            runner.summary.order_rows = runner._write_orders(orders)
            heartbeat()
            runner.summary.order_unresolved_rows = runner._resolve_order_items()

        elif interface_key == "walmartReturnOrderList":
            refunds = runner._fetch_return_all()
            heartbeat()
            runner.summary.refund_rows = runner._write_refunds(refunds)
            heartbeat()
            runner.summary.refund_unresolved_rows = runner._resolve_refund_items()
            heartbeat()
            runner._reprice_refunds()

        elif interface_key == "walmartAdItemSpList":
            advertisers = runner._fetch_page_all(
                "walmart_advertiser_list",
                runner._advertiser_body,
            )
            runner.advertiser_ids = tuple(
                dict.fromkeys(
                    value
                    for row in advertisers
                    if (
                        value := str(
                            row.get("advertiserId") or row.get("advertiser_id") or ""
                        ).strip()
                    )
                )
            )
            ad_rows = []
            for advertiser_id in runner.advertiser_ids[: runner.max_advertisers]:
                ad_rows.extend(runner._fetch_ads_all(advertiser_id))
            heartbeat()
            runner.summary.advertiser_rows = runner._write_advertisers(advertisers)
            heartbeat()
            runner.summary.ad_rows = runner._write_ads(ad_rows)
            heartbeat()
            runner._resolve_ads(ad_rows)

        else:
            raise ValueError("unsupported Data Pages interface")

        heartbeat()
        runner.summary.mart_daily_sales_rows = runner._refresh_daily_sales_mart()
        heartbeat()
        runner.summary.mart_order_profit_rows = runner._refresh_order_profit_mart()
        self.session.commit()
        return runner.summary

    def _execute_listing_management_run(self, run: IntegrationSyncRun) -> None:
        """Refresh Store/Listings and Listing Management MART only."""

        config = None
        if run.config_id is not None:
            config = self.repository.get_config(run.config_id, frozenset({run.source_account_ref}))

        page_size = (
            config.page_size
            if config is not None and config.page_size is not None
            else DATA_PAGES_DEFAULT_PAGE_SIZE
        )
        if not 1 <= page_size <= 200:
            self._fail(run, "DATA_PAGES_PAGE_SIZE_INVALID")
            return

        run.work_items_total = 1
        self.session.commit()

        business_date = datetime.now(DATA_PAGES_LA_TZ).date()

        with data_pages_client() as client:
            runner = DataPagesRealSyncRunner(
                session=self.session,
                client=client,
                source_account_ref=run.source_account_ref,
                business_date=business_date,
                page_size=page_size,
                campaign_type=DATA_PAGES_DEFAULT_CAMPAIGN_TYPE,
                max_advertisers=DATA_PAGES_DEFAULT_MAX_ADVERTISERS,
                heartbeat=lambda: self._heartbeat_lock(run.id),
            )
            stores = runner._fetch_offset_all(
                "seller_list_multi_platform",
                runner._seller_body,
                minimum_page_size=20,
            )
            listings = runner._fetch_offset_all("walmart_listing_list", runner._listing_body)

            runner.summary.store_rows = runner._write_stores(stores)
            runner.summary.listing_rows = runner._write_listings(listings)
            self._heartbeat_lock(run.id)
            runner.summary.mart_listing_rows = runner._refresh_listing_mart()
            runner.session.commit()

        completed = self.repository.get_run_for_update(run.id)
        if completed is None:
            return
        from_status = completed.status
        completed.status = "succeeded"
        completed.finished_at = utc_now()
        completed.work_items_succeeded = 1
        completed.work_items_failed = 0
        completed.records_seen = runner.summary.store_rows + runner.summary.listing_rows
        completed.records_written = runner.summary.mart_listing_rows
        completed.error_code = None
        completed.error_message = None
        self._event(completed.id, from_status, "succeeded", "SYNC_RUN_SUCCEEDED")
        self.session.commit()

    def _data_pages_business_dates_for_run(
        self,
        run: IntegrationSyncRun,
        config: IntegrationSyncConfig | None = None,
    ) -> tuple[date, ...]:
        if run.window_start is not None or run.window_end is not None:
            if run.window_start is None or run.window_end is None:
                return ()
            start = _as_la_date(run.window_start)
            end = _as_la_date(run.window_end)
            if end < start:
                return ()
            if (end - start).days > DATA_PAGES_MAX_BACKFILL_DAYS:
                return ()
            return tuple(_date_range(start, end))

        default_days = 2
        if run.interface_key == "saleStatPageList":
            default_days = 3
        elif run.interface_key == "walmartReturnOrderList":
            default_days = 7
        elif run.interface_key == "walmartAdItemSpList":
            default_days = 3

        configured_days = config.max_pages if config is not None else None
        if configured_days is None or configured_days < 1 or configured_days > 14:
            configured_days = default_days

        backfill_days = max(1, min(configured_days, DATA_PAGES_MAX_BACKFILL_DAYS))
        today = datetime.now(DATA_PAGES_LA_TZ).date()
        start = today - timedelta(days=backfill_days - 1)
        return tuple(_date_range(start, today))

    def load_or_freeze_product_info_plan(
        self,
        run: IntegrationSyncRun,
    ) -> BatchPlan | None:
        """Return persisted plan, freezing active identity membership exactly once."""
        work_items = self.repository.list_work_items_for_run(run.id)
        batch_items = self.repository.list_batch_items_for_run(run.id)

        if work_items or batch_items:
            if not work_items or not batch_items:
                self._fail(run, "SYNC_FROZEN_PLAN_INVALID")
                return None
            run.work_items_total = len(work_items)
            return BatchPlan(tuple(work_items), tuple(batch_items))

        ids = self.repository.list_active_lingxing_sku_ids(run.source_account_ref)
        if not ids:
            self._fail(run, "SYNC_IDENTITY_SET_EMPTY")
            return None

        batch_size = self.repository.batch_size_for_run(run) or PRODUCT_INFO_BATCH_SIZE
        if not 1 <= batch_size <= PRODUCT_INFO_BATCH_SIZE:
            self._fail(run, "SYNC_BATCH_SIZE_INVALID")
            return None

        plan = LingxingBatchGetProductInfoSyncHandler().build_plan(
            run_id=run.id,
            source_account_ref=run.source_account_ref,
            lingxing_sku_ids=ids,
            batch_size=batch_size,
        )
        try:
            self.repository.add_work_items(plan.work_items)
            self.repository.add_batch_items(plan.batch_items)
            run.work_items_total = len(plan.work_items)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return plan

    def _heartbeat_lock(self, run_id: UUID) -> None:
        # Renew before outbound/provider publication work so another worker
        # cannot mistake a healthy long-running run for an expired lease.
        lock = self.repository.get_lock_for_run_for_update(run_id)
        if lock is None:
            raise ProductInfoOneTimeRunError("SYNC_LOCK_LEASE_LOST")
        now = utc_now()
        lock.heartbeat_at = now
        lock.expires_at = now + LOCK_LEASE_DURATION
        self.session.commit()

    def _fail(self, run: IntegrationSyncRun, error_code: str) -> None:
        from_status = run.status
        run.status = "failed"
        run.finished_at = utc_now()
        run.error_code = error_code
        run.error_message = "同步执行失败"
        self._event(run.id, from_status, "failed", error_code)
        self.session.commit()

    def _event(
        self,
        run_id: UUID,
        from_status: str | None,
        to_status: str,
        message_code: str,
    ) -> None:
        self.repository.add_event(
            IntegrationSyncRunEvent(
                run_id=run_id,
                sequence_no=self.repository.next_event_sequence(run_id),
                event_type="state_transition",
                from_status=from_status,
                to_status=to_status,
                message_code=message_code,
                safe_details=None,
                occurred_at=utc_now(),
                actor_ref="worker",
            )
        )


def _as_la_date(value: datetime) -> date:
    if value.tzinfo is None:
        return value.date()
    return value.astimezone(DATA_PAGES_LA_TZ).date()


def _date_range(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def _safe_error_code(error: Exception) -> str:
    code = str(error)
    return code if code.isupper() and len(code) <= 128 else "SYNC_EXECUTION_FAILED"

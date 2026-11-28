"""WooCommerce read-only upstream integration using existing governed task-center tables.

Registration is explicit after 0102/0104 have been applied, and on subsequent
verified store changes. No automatic publish, reference-price submission or notifications.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from time import sleep
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from app.core.config import AppEnvironment, get_database_url, get_settings
from app.db.session import get_session_factory
from app.modules.integration_sync.models import (
    IntegrationInterface,
    IntegrationSyncConfig,
    IntegrationSyncRun,
    IntegrationSyncRunEvent,
    IntegrationSyncRunWorkItem,
)
from app.modules.woocommerce_config.models import WooCommerceStore
from app.modules.woocommerce_config.service import WooCommerceConfigError

PROVIDER = "woocommerce"
INTERFACE_KEY = "woocommerceProducts"
HANDLER_KEY = "woocommerce.products.read_catalog.v1"
ENDPOINT = "/wp-json/wc/v3/products"
ACCOUNT_PREFIX = "woo:"
OVERLAP = timedelta(minutes=10)
FULL_REFRESH_AGE = timedelta(days=7)


def allowed_write_target():
    cfg = get_settings()
    url = get_database_url(cfg)
    if cfg.app_env is AppEnvironment.LOCAL:
        if url.host in ("localhost", "127.0.0.1", "::1") and url.port == 55433 and not url.query:
            return
    elif cfg.app_env is AppEnvironment.PRODUCTION and url.database == "szzsbj_app":
        return
    raise WooCommerceConfigError("WOO_SYNC_WRITE_TARGET_BLOCKED", 403)


def is_woo_interface(interface):
    return (
        interface.provider == PROVIDER
        and interface.interface_key == INTERFACE_KEY
        and interface.method == "GET"
        and interface.handler_key == HANDLER_KEY
        and interface.endpoint_path == ENDPOINT
        and interface.request_kind == "offset_page"
    )


def store_ref(store_id: UUID) -> str:
    return ACCOUNT_PREFIX + str(store_id)


def parse_store_ref(value: str) -> UUID:
    if not value.startswith(ACCOUNT_PREFIX):
        raise WooCommerceConfigError("WOO_SYNC_ACCOUNT_INVALID")
    try:
        result = UUID(value[len(ACCOUNT_PREFIX) :])
    except ValueError:
        raise WooCommerceConfigError("WOO_SYNC_ACCOUNT_INVALID") from None
    if store_ref(result) != value:
        raise WooCommerceConfigError("WOO_SYNC_ACCOUNT_INVALID")
    return result


def register_store(session, store_id: UUID, *, enabled: bool) -> None:
    """Register a store in the existing task center; never turn on its schedule.

    Re-enabling a store does not silently turn automatic scheduling back on.
    Store edits before 0104 remain compatible and are registered by bootstrap.
    """
    if not session.execute(
        sa.text("SELECT to_regclass('dim_woocommerce_products') IS NOT NULL")
    ).scalar_one():
        return
    allowed_write_target()
    interface = IntegrationInterface.__table__
    cfg = IntegrationSyncConfig.__table__
    stmt = insert(interface).values(
        id=uuid4(),
        provider=PROVIDER,
        interface_key=INTERFACE_KEY,
        display_name="WooCommerce商品同步",
        method="GET",
        endpoint_path=ENDPOINT,
        request_kind="offset_page",
        handler_key=HANDLER_KEY,
        contract_version="v1",
        outbound_enabled=True,
    )
    session.execute(
        stmt.on_conflict_do_nothing(
            index_elements=[interface.c.provider, interface.c.interface_key]
        )
    )
    row = (
        session.execute(
            sa.select(interface).where(
                interface.c.provider == PROVIDER, interface.c.interface_key == INTERFACE_KEY
            )
        )
        .mappings()
        .one()
    )
    # Do not silently enable an existing interface disabled by an administrator.
    if (row["handler_key"], row["endpoint_path"], row["method"], row["request_kind"]) != (
        HANDLER_KEY,
        ENDPOINT,
        "GET",
        "offset_page",
    ):
        raise WooCommerceConfigError("WOO_TASK_CONTRACT_CONFLICT", 409)
    ref = store_ref(store_id)
    stmt = insert(cfg).values(
        id=uuid4(),
        interface_id=row["id"],
        source_account_ref=ref,
        is_enabled=enabled,
        schedule_enabled=False,
        schedule_timezone="UTC",
        max_attempts=3,
    )
    if enabled:
        # Preserve task-center disable/schedule decisions; a store may be enabled
        # but its task intentionally disabled. An operator can enable it there.
        session.execute(
            stmt.on_conflict_do_nothing(
                index_elements=[cfg.c.interface_id, cfg.c.source_account_ref]
            )
        )
    else:
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=[cfg.c.interface_id, cfg.c.source_account_ref],
                set_=dict(
                    is_enabled=False,
                    schedule_enabled=False,
                    next_run_at=None,
                    updated_at=sa.func.now(),
                ),
            )
        )


def bootstrap():
    allowed_write_target()
    with get_session_factory()() as session:
        if session.execute(sa.text("SHOW transaction_read_only")).scalar_one() != "off":
            raise WooCommerceConfigError("WOO_READ_ONLY_DATABASE", 403)
        if not session.execute(
            sa.text("SELECT to_regclass('dim_woocommerce_products') IS NOT NULL")
        ).scalar_one():
            raise WooCommerceConfigError("WOO_SCHEMA_NOT_INSTALLED", 409)
        table = WooCommerceStore.__table__
        rows = session.execute(
            sa.select(table.c.id, table.c.enabled, table.c.last_test_ok).with_for_update()
        ).all()
        for row in rows:
            register_store(session, row.id, enabled=bool(row.enabled and row.last_test_ok))
        session.commit()
        return len(rows)


def freeze_window(session, run):
    """Use a durable last successful window; never infer a watermark from an empty page.

    Manual sync is always full. Scheduled sync is incremental only after a
    successful full sync, and performs a full reconciliation at least weekly.
    Failed retries reuse the exact persisted window; a failed full stays full.
    """
    t = IntegrationSyncRun.__table__
    end = datetime.now(UTC).replace(microsecond=0)
    if run.trigger_type == "retry":
        # Retry before a worker froze the original interval falls back to a full scan.
        return run.window_start, run.window_end or end
    if run.trigger_type != "schedule":
        return None, end
    conditions = (
        t.c.provider == PROVIDER,
        t.c.interface_key == INTERFACE_KEY,
        t.c.source_account_ref == run.source_account_ref,
        t.c.status == "succeeded",
    )
    last_full = session.scalar(
        sa.select(sa.func.max(t.c.window_end)).where(*conditions, t.c.window_start.is_(None))
    )
    last_end = session.scalar(sa.select(sa.func.max(t.c.window_end)).where(*conditions))
    if (
        last_full is None
        or last_end is None
        or end - last_full >= FULL_REFRESH_AGE
        or last_end > end
    ):
        return None, end
    return last_end - OVERLAP, end


def execute_woo(service, run):
    """Called after existing executor acquired its durable lease and set running.

    Publish catalog and succeeded run/work item in one PostgreSQL transaction;
    a lost lease must never commit catalog changes. A crashed worker is recovered
    by the existing scheduler, without marking an incomplete run successful.
    """
    from app.modules.integration_sync.repository import IntegrationSyncRepository

    from .catalog import PAGE_SIZE, sync_store

    run_id = run.id
    work_id = None
    try:
        allowed_write_target()
        store_id = parse_store_ref(run.source_account_ref)
        if run.trigger_type not in {"manual", "schedule", "retry"}:
            raise WooCommerceConfigError("WOO_TRIGGER_NOT_SUPPORTED")
        config = service.repository.get_config(run.config_id, frozenset({run.source_account_ref}))
        if config is None or not config.is_enabled:
            raise WooCommerceConfigError("WOO_TASK_DISABLED", 409)
        attempts = max(1, min(3, config.max_attempts))
        start, end = freeze_window(service.session, run)
        run.window_start, run.window_end = start, end
        run.work_items_total = 1
        actor = run.requested_by or "worker"
        mode = "incremental" if start is not None else "full"
        work_id = uuid4()
        work = IntegrationSyncRunWorkItem(
            id=work_id,
            run_id=run_id,
            ordinal=1,
            request_kind="offset_page",
            scope_key=store_ref(store_id),
            status="running",
            attempt_count=0,
            offset_value=0,
            length_value=PAGE_SIZE,
            request_safe_params={
                "mode": mode,
                "scope": "store_catalog",
                "page_size": PAGE_SIZE,
                "modified_after": start.isoformat() if start is not None else None,
                "modified_before": end.isoformat(),
            },
            started_at=datetime.now(UTC),
        )
        service.session.add(work)
        service.session.commit()

        def finalize(session, result):
            repo = IntegrationSyncRepository(session)
            lease = repo.get_lock_for_run_for_update(run_id)
            if lease is None or lease.expires_at <= datetime.now(UTC):
                raise WooCommerceConfigError("WOO_SYNC_LEASE_LOST", 409)
            completed = repo.get_run_for_update(run_id)
            saved_work = session.get(IntegrationSyncRunWorkItem, work_id)
            if (
                completed is None
                or completed.status != "running"
                or saved_work is None
                or saved_work.status != "running"
            ):
                raise WooCommerceConfigError("WOO_SYNC_LEASE_LOST", 409)
            finished = datetime.now(UTC)
            completed.status = "succeeded"
            completed.finished_at = finished
            completed.work_items_succeeded = 1
            completed.work_items_failed = 0
            completed.records_seen = result["observed"]
            completed.records_written = result["written"]
            completed.error_code = None
            completed.error_message = None
            saved_work.status = "succeeded"
            saved_work.finished_at = finished
            saved_work.response_count = result["observed"]
            saved_work.error_code = None
            saved_work.error_message = None
            repo.add_event(
                IntegrationSyncRunEvent(
                    run_id=run_id,
                    sequence_no=repo.next_event_sequence(run_id),
                    event_type="state_transition",
                    from_status="running",
                    to_status="succeeded",
                    message_code="SYNC_RUN_SUCCEEDED",
                    safe_details={
                        "mode": mode,
                        "observed": result["observed"],
                        "changed": result["changed"],
                    },
                    occurred_at=finished,
                    actor_ref="worker",
                )
            )

        transient = {
            "WOO_CONNECTION_FAILED",
            "WOO_UPSTREAM_ERROR",
            "WOO_CATALOG_CHANGED_DURING_SYNC",
            "WOO_PAGE_COUNT_MISMATCH",
        }
        for attempt in range(1, attempts + 1):
            service._heartbeat_data_pages_lock(run_id)
            saved_work = service.session.get(IntegrationSyncRunWorkItem, work_id)
            if saved_work is None or saved_work.status != "running":
                raise WooCommerceConfigError("WOO_SYNC_LEASE_LOST", 409)
            saved_work.attempt_count = attempt
            service.session.commit()
            try:
                sync_store(
                    store_id,
                    actor=actor,
                    run_id=run_id,
                    window_start=start,
                    window_end=end,
                    heartbeat=lambda: service._heartbeat_data_pages_lock(run_id),
                    finalize=finalize,
                )
                return
            except WooCommerceConfigError as exc:
                if exc.code not in transient or attempt >= attempts:
                    raise
                service._event(
                    run_id,
                    "running",
                    "running",
                    "WOO_SYNC_ATTEMPT_RETRY",
                    {"attempt": attempt, "error_code": exc.code},
                )
                service.session.commit()
                sleep(min(2**attempt, 8))
    except Exception as exc:
        service.session.rollback()
        failed = service.repository.get_run_for_update(run_id)
        if failed is not None and failed.status == "running":
            failed.work_items_failed = 1 if failed.work_items_total else 0
            code = (
                exc.code if isinstance(exc, WooCommerceConfigError) else "WOO_SYNC_EXECUTION_FAILED"
            )
            if not isinstance(code, str) or len(code) > 128 or not code.replace("_", "").isalnum():
                code = "WOO_SYNC_EXECUTION_FAILED"
            failed_work = (
                service.session.get(IntegrationSyncRunWorkItem, work_id) if work_id else None
            )
            if failed_work is not None and failed_work.status == "running":
                failed_work.status = "failed"
                failed_work.finished_at = datetime.now(UTC)
                failed_work.error_code = code
                failed_work.error_message = "WooCommerce商品同步失败"
            service._fail(failed, code)
        else:
            service.session.rollback()


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", required=True)
    parser.parse_args()
    try:
        total = bootstrap()
    except WooCommerceConfigError as exc:
        raise SystemExit("STOP=" + exc.code) from None
    except Exception as exc:
        raise SystemExit("STOP=WOO_TASK_REGISTER_FAILED:" + type(exc).__name__) from None
    print("WOO_TASK_REGISTRATION=PASS")
    print("STORES_REGISTERED=" + str(total))
    print("AUTO_SCHEDULE_ENABLED_BY_REGISTRATION=NO")


if __name__ == "__main__":
    main()

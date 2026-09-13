from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import AppEnvironment, Settings, get_settings  # noqa: E402
from app.db.model_registry import register_productlist_sync_models  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.modules.integration_sync.catalog import (  # noqa: E402
    ProductListGovernanceBootstrapError,
    validate_productlist_source_account_ref,
)
from app.modules.integration_sync.handlers.lingxing_product_list_sync import (  # noqa: E402
    PRODUCT_LIST_ENDPOINT,
    PRODUCT_LIST_HANDLER_KEY,
    LingxingProductListSyncHandler,
)
from app.modules.integration_sync.models import (  # noqa: E402
    IntegrationInterface,
    IntegrationSyncConfig,
    IntegrationSyncRun,
    RawRetentionPolicy,
    utc_now,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository  # noqa: E402

PROVIDER = "lingxing"
INTERFACE_KEY = "productList"
POLICY_KEY = "lingxing-productlist-v1"
REQUESTED_BY = "owner-authorized-cli"
DEFAULT_REASON = "Owner-authorized one-time ProductList sync"
FORBIDDEN_INPUT = re.compile(
    r"https?://|(?:^|[^a-z0-9])(?:app(?:_|[ -])?(?:id|secret)|authorization|bearer|"
    r"database(?:_|[ -])?url|access(?:_|[ -])?token|refresh(?:_|[ -])?token|secret|"
    r"sign|token|raw|payload(?:_|[ -])?json|sku|msku|"
    r"product(?:_|[ -])?(?:name|title|image|value)|image(?:_|[ -])?url)"
    r"(?:$|[^a-z0-9])",
    re.IGNORECASE,
)


class ProductListOneTimeRunError(RuntimeError):
    """Safe one-time runner error containing only a stable code."""


@dataclass(frozen=True, slots=True)
class ProductListOneTimeRunResult:
    run_id: UUID
    run_status: str
    error_code: str | None
    reason_present: bool
    page_size: int
    max_pages: int
    work_items_total: int
    work_items_succeeded: int
    work_items_failed: int
    records_seen: int
    records_written: int
    raw_blobs_count: int
    request_refs_count: int
    productlist_refs_count: int
    sku_identity_active_count: int
    duplicate_ids_detected: int
    inactive_ids_count: int


class ProductListOneTimeRunner:
    """ProductList-only CLI orchestration; governance rows remain read-only."""

    def __init__(self, session: Session) -> None:
        register_productlist_sync_models()
        self.session = session
        self.repository = IntegrationSyncRepository(session)

    def execute(
        self,
        *,
        source_account_ref: str,
        idempotency_key: str,
        reason: str,
    ) -> ProductListOneTimeRunResult:
        interface = self.repository.get_interface_by_key(PROVIDER, INTERFACE_KEY)
        policy = self.repository.get_retention_policy(POLICY_KEY)
        config = (
            self.repository.get_config_by_scope(interface.id, source_account_ref)
            if interface is not None
            else None
        )
        if (
            interface is None
            or policy is None
            or config is None
            or not _governance_is_authorized(
                interface,
                policy,
                config,
                source_account_ref,
            )
        ):
            raise ProductListOneTimeRunError("PRODUCTLIST_ONE_TIME_RUN_GOVERNANCE_NOT_AUTHORIZED")
        page_size = config.page_size
        max_pages = config.max_pages
        if page_size is None or max_pages is None:
            raise ProductListOneTimeRunError("PRODUCTLIST_ONE_TIME_RUN_GOVERNANCE_NOT_AUTHORIZED")
        if self.repository.has_running_run(PROVIDER, INTERFACE_KEY):
            raise ProductListOneTimeRunError("PRODUCTLIST_ONE_TIME_RUN_ALREADY_RUNNING")
        if self.repository.find_run_by_idempotency(idempotency_key) is not None:
            raise ProductListOneTimeRunError("PRODUCTLIST_ONE_TIME_RUN_IDEMPOTENCY_CONFLICT")

        run = IntegrationSyncRun(
            id=uuid4(),
            config_id=config.id,
            interface_id=interface.id,
            provider=PROVIDER,
            interface_key=INTERFACE_KEY,
            source_account_ref=source_account_ref,
            trigger_type="manual",
            status="queued",
            idempotency_key=idempotency_key,
            requested_by=REQUESTED_BY,
            request_id=f"productlist-one-time-run:{uuid4()}",
            reason=reason,
            queued_at=utc_now(),
            work_items_total=0,
            work_items_succeeded=0,
            work_items_failed=0,
            records_seen=0,
            records_written=0,
        )
        try:
            self.repository.add_run(run)
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise ProductListOneTimeRunError("PRODUCTLIST_ONE_TIME_RUN_CONFLICT") from None

        execution = LingxingProductListSyncHandler(self.session).execute(run, interface)
        raw_blobs, request_refs, productlist_refs, active_identities = (
            self.repository.productlist_run_aggregate_counts(run.id, source_account_ref)
        )
        return ProductListOneTimeRunResult(
            run_id=run.id,
            run_status=run.status,
            error_code=run.error_code,
            reason_present=bool(reason),
            page_size=page_size,
            max_pages=max_pages,
            work_items_total=run.work_items_total,
            work_items_succeeded=run.work_items_succeeded,
            work_items_failed=run.work_items_failed,
            records_seen=run.records_seen,
            records_written=run.records_written,
            raw_blobs_count=raw_blobs,
            request_refs_count=request_refs,
            productlist_refs_count=productlist_refs,
            sku_identity_active_count=active_identities,
            duplicate_ids_detected=execution.duplicate_ids_detected,
            inactive_ids_count=execution.inactive_ids_count,
        )


def main() -> int:
    if os.getenv("PRODUCTLIST_ONE_TIME_RUN_AUTHORIZED", "").casefold() != "true":
        print("PRODUCTLIST_ONE_TIME_RUN_REQUIRES_AUTHORIZATION")
        return 2
    try:
        source_account_ref = _source_account_ref()
        idempotency_key = _idempotency_key()
        reason = _reason()
        settings = get_settings()
        _validate_runtime_settings(settings)
    except ProductListOneTimeRunError as error:
        print(str(error))
        return 2
    except Exception:
        print("PRODUCTLIST_ONE_TIME_RUN_ENV_NOT_AUTHORIZED")
        return 2

    try:
        with get_session_factory()() as session:
            result = ProductListOneTimeRunner(session).execute(
                source_account_ref=source_account_ref,
                idempotency_key=idempotency_key,
                reason=reason,
            )
    except ProductListOneTimeRunError as error:
        print(str(error))
        return 2
    except Exception:
        print("PRODUCTLIST_ONE_TIME_RUN_FAILED")
        return 1

    _print_result(result)
    return 0 if result.run_status == "succeeded" else 1


def _validate_runtime_settings(settings: Settings) -> None:
    if not (
        settings.app_env is AppEnvironment.PRODUCTION
        and settings.lingxing_enable_token_requests is True
        and settings.lingxing_enable_real_calls is True
        and settings.lingxing_dry_run is False
        and settings.lingxing_allow_raw_write is True
        and settings.lingxing_allow_structured_write is False
        and settings.lingxing_allow_full_sync is False
    ):
        raise ProductListOneTimeRunError("PRODUCTLIST_ONE_TIME_RUN_ENV_NOT_AUTHORIZED")


def _source_account_ref() -> str:
    try:
        value = validate_productlist_source_account_ref(
            os.getenv("PRODUCTLIST_SOURCE_ACCOUNT_REF", "")
        )
    except ProductListGovernanceBootstrapError:
        raise ProductListOneTimeRunError(
            "PRODUCTLIST_ONE_TIME_RUN_SOURCE_ACCOUNT_REF_INVALID"
        ) from None
    return _validate_safe_text(
        value,
        max_length=128,
        error_code="PRODUCTLIST_ONE_TIME_RUN_SOURCE_ACCOUNT_REF_INVALID",
    )


def _idempotency_key() -> str:
    value = os.getenv("PRODUCTLIST_ONE_TIME_RUN_IDEMPOTENCY_KEY")
    if value is None:
        return f"productlist-onetime:{uuid4()}"
    return _validate_safe_text(
        value,
        max_length=255,
        error_code="PRODUCTLIST_ONE_TIME_RUN_IDEMPOTENCY_KEY_INVALID",
    )


def _reason() -> str:
    value = os.getenv("PRODUCTLIST_ONE_TIME_RUN_REASON")
    if value is None:
        return DEFAULT_REASON
    return _validate_safe_text(
        value,
        max_length=1000,
        error_code="PRODUCTLIST_ONE_TIME_RUN_REASON_INVALID",
    )


def _validate_safe_text(value: str, *, max_length: int, error_code: str) -> str:
    if (
        not value
        or value != value.strip()
        or len(value) > max_length
        or FORBIDDEN_INPUT.search(value)
    ):
        raise ProductListOneTimeRunError(error_code)
    return value


def _governance_is_authorized(
    interface: IntegrationInterface,
    policy: RawRetentionPolicy,
    config: IntegrationSyncConfig,
    source_account_ref: str,
) -> bool:
    return bool(
        interface.provider == PROVIDER
        and interface.interface_key == INTERFACE_KEY
        and interface.method == "POST"
        and interface.endpoint_path == PRODUCT_LIST_ENDPOINT
        and interface.request_kind == "offset_page"
        and interface.handler_key == PRODUCT_LIST_HANDLER_KEY
        and interface.contract_version == "v1"
        and interface.outbound_enabled is True
        and policy.policy_key == POLICY_KEY
        and policy.provider == PROVIDER
        and policy.interface_key == INTERFACE_KEY
        and policy.is_active is True
        and config.source_account_ref == source_account_ref
        and config.is_enabled is True
        and config.schedule_enabled is False
        and config.schedule_cron is None
        and isinstance(config.page_size, int)
        and 1 <= config.page_size <= 1000
        and isinstance(config.max_pages, int)
        and config.max_pages > 0
        and config.max_attempts == 1
        and config.retention_policy_id == policy.id
    )


def _print_result(result: ProductListOneTimeRunResult) -> None:
    print("preflight_status=PASS")
    print(f"run_id={result.run_id}")
    print(f"run_status={result.run_status}")
    print(f"error_code={result.error_code}")
    print("source_account_ref_present=true")
    print(f"reason_present={str(result.reason_present).lower()}")
    print("trigger_type=manual")
    print("schedule_enabled=false")
    print(f"page_size={result.page_size}")
    print(f"max_pages={result.max_pages}")
    print(f"work_items_total={result.work_items_total}")
    print(f"work_items_succeeded={result.work_items_succeeded}")
    print(f"work_items_failed={result.work_items_failed}")
    print(f"records_seen={result.records_seen}")
    print(f"records_written={result.records_written}")
    print(f"raw_blobs_count={result.raw_blobs_count}")
    print(f"request_refs_count={result.request_refs_count}")
    print(f"productlist_refs_count={result.productlist_refs_count}")
    print(f"sku_identity_active_count={result.sku_identity_active_count}")
    print(f"duplicate_ids_detected={result.duplicate_ids_detected}")
    print(f"inactive_ids_count={result.inactive_ids_count}")


if __name__ == "__main__":
    raise SystemExit(main())

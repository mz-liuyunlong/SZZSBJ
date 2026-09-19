"""Owner-authorized one-time run for one PMC purchase feed over a bounded date window.

Gate 2 / PR-E. One script serves the three interfaces (selected by
``PMC_PURCHASE_INTERFACE_KEY``) so the authorization gate, runtime assertions and
governance checks stay identical. The run is created with ``trigger_type=manual`` and
the window on ``window_start`` / ``window_end``; the governed handler does the rest.

Every invocation is a production action and must be recorded per
``docs/runbooks/production-pmc-purchase-sync.md``. Nothing here enables schedules.

Environment (all read, none printed):
  PMC_PURCHASE_ONE_TIME_RUN_AUTHORIZED=true   exact gate
  PMC_PURCHASE_INTERFACE_KEY                  one of purchasePlanList / purchaseOrderList /
                                              purchaseReceiptOrderList
  PMC_PURCHASE_SOURCE_ACCOUNT_REF             governance scope
  PMC_PURCHASE_WINDOW_START / _END            YYYY-MM-DD, inclusive, <= 90 days, start >= 2026-08-01
  PMC_PURCHASE_ONE_TIME_RUN_IDEMPOTENCY_KEY   optional
  PMC_PURCHASE_ONE_TIME_RUN_REASON            optional
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import AppEnvironment, Settings, get_settings  # noqa: E402
from app.db.model_registry import register_productlist_sync_models  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.integrations.lingxing.pmc_purchase_contracts import (  # noqa: E402
    PmcPurchaseContractError,
    validate_pmc_purchase_window,
)
from app.modules.integration_sync.catalog import (  # noqa: E402
    PmcPurchaseGovernanceBootstrapError,
    validate_pmc_purchase_source_account_ref,
)
from app.modules.integration_sync.handlers.lingxing_pmc_purchase_sync import (  # noqa: E402
    PMC_PURCHASE_HANDLERS,
)
from app.modules.integration_sync.models import (  # noqa: E402
    IntegrationInterface,
    IntegrationSyncConfig,
    IntegrationSyncRun,
    RawRetentionPolicy,
    utc_now,
)
from app.modules.integration_sync.pmc_purchase_catalog import (  # noqa: E402
    PMC_PURCHASE_PAGE_SIZE,
    PMC_PURCHASE_SPECS_BY_INTERFACE_KEY,
    PmcPurchaseSyncInterfaceSpec,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository  # noqa: E402

PROVIDER = "lingxing"
REQUESTED_BY = "owner-authorized-cli"
DEFAULT_REASON = "Owner-authorized one-time PMC purchase window sync"
# Rocky 2026-09-19: production data starts here; earlier history only on explicit instruction.
EARLIEST_WINDOW_START = date(2026, 8, 1)
FORBIDDEN_INPUT = re.compile(
    r"https?://|(?:^|[^a-z0-9])(?:app(?:_|[ -])?(?:id|secret)|authorization|bearer|"
    r"database(?:_|[ -])?url|access(?:_|[ -])?token|refresh(?:_|[ -])?token|secret|"
    r"sign|token|raw|payload(?:_|[ -])?json|sku|msku|"
    r"product(?:_|[ -])?(?:name|title|image|value)|image(?:_|[ -])?url)"
    r"(?:$|[^a-z0-9])",
    re.IGNORECASE,
)


class PmcPurchaseOneTimeRunError(RuntimeError):
    """Safe one-time runner error containing only a stable code."""


@dataclass(frozen=True, slots=True)
class PmcPurchaseOneTimeRunResult:
    run_id: UUID
    interface_key: str
    run_status: str
    error_code: str | None
    reason_present: bool
    window_start: date
    window_end: date
    page_size: int
    max_pages: int
    work_items_total: int
    work_items_succeeded: int
    work_items_failed: int
    records_seen: int
    records_written: int
    headers_written: int
    lines_written: int
    duplicates_skipped: int
    quality_summary: str


class PmcPurchaseOneTimeRunner:
    """PMC-purchase-only CLI orchestration; governance rows remain read-only."""

    def __init__(self, session: Session) -> None:
        register_productlist_sync_models()
        self.session = session
        self.repository = IntegrationSyncRepository(session)

    def execute(
        self,
        *,
        spec: PmcPurchaseSyncInterfaceSpec,
        source_account_ref: str,
        window_start: date,
        window_end: date,
        idempotency_key: str,
        reason: str,
    ) -> PmcPurchaseOneTimeRunResult:
        interface = self.repository.get_interface_by_key(PROVIDER, spec.interface_key)
        policy = self.repository.get_retention_policy(spec.retention_policy_key)
        config = (
            self.repository.get_config_by_scope(interface.id, source_account_ref)
            if interface is not None
            else None
        )
        if (
            interface is None
            or policy is None
            or config is None
            or not _governance_is_authorized(spec, interface, policy, config, source_account_ref)
        ):
            raise PmcPurchaseOneTimeRunError("PMC_PURCHASE_ONE_TIME_RUN_GOVERNANCE_NOT_AUTHORIZED")
        page_size = config.page_size
        max_pages = config.max_pages
        if page_size is None or max_pages is None:
            raise PmcPurchaseOneTimeRunError("PMC_PURCHASE_ONE_TIME_RUN_GOVERNANCE_NOT_AUTHORIZED")
        # token_bucket_capacity=1 on the provider: never overlap purchase runs.
        for other_key in PMC_PURCHASE_SPECS_BY_INTERFACE_KEY:
            if self.repository.has_running_run(PROVIDER, other_key):
                raise PmcPurchaseOneTimeRunError("PMC_PURCHASE_ONE_TIME_RUN_ALREADY_RUNNING")
        if self.repository.find_run_by_idempotency(idempotency_key) is not None:
            raise PmcPurchaseOneTimeRunError("PMC_PURCHASE_ONE_TIME_RUN_IDEMPOTENCY_CONFLICT")

        run = IntegrationSyncRun(
            id=uuid4(),
            config_id=config.id,
            interface_id=interface.id,
            provider=PROVIDER,
            interface_key=spec.interface_key,
            source_account_ref=source_account_ref,
            trigger_type="manual",
            status="queued",
            idempotency_key=idempotency_key,
            requested_by=REQUESTED_BY,
            request_id=f"pmc-purchase-one-time-run:{uuid4()}",
            reason=reason,
            window_start=datetime.combine(window_start, datetime.min.time(), tzinfo=UTC),
            window_end=datetime.combine(window_end, datetime.min.time(), tzinfo=UTC),
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
            raise PmcPurchaseOneTimeRunError("PMC_PURCHASE_ONE_TIME_RUN_CONFLICT") from None

        handler_cls = PMC_PURCHASE_HANDLERS[spec.interface_key]
        execution = handler_cls(self.session).execute(run, interface)
        return PmcPurchaseOneTimeRunResult(
            run_id=run.id,
            interface_key=spec.interface_key,
            run_status=run.status,
            error_code=run.error_code,
            reason_present=bool(reason),
            window_start=window_start,
            window_end=window_end,
            page_size=page_size,
            max_pages=max_pages,
            work_items_total=run.work_items_total,
            work_items_succeeded=run.work_items_succeeded,
            work_items_failed=run.work_items_failed,
            records_seen=run.records_seen,
            records_written=run.records_written,
            headers_written=execution.headers_written,
            lines_written=execution.lines_written,
            duplicates_skipped=execution.duplicates_skipped,
            quality_summary=execution.quality.as_message(),
        )


def main() -> int:
    if os.getenv("PMC_PURCHASE_ONE_TIME_RUN_AUTHORIZED", "").casefold() != "true":
        print("PMC_PURCHASE_ONE_TIME_RUN_REQUIRES_AUTHORIZATION")
        return 2
    try:
        spec = _spec()
        source_account_ref = _source_account_ref()
        window_start, window_end = _window()
        idempotency_key = _idempotency_key(spec)
        reason = _reason()
        settings = get_settings()
        _validate_runtime_settings(settings)
    except PmcPurchaseOneTimeRunError as error:
        print(str(error))
        return 2
    except Exception:
        print("PMC_PURCHASE_ONE_TIME_RUN_ENV_NOT_AUTHORIZED")
        return 2

    try:
        with get_session_factory()() as session:
            result = PmcPurchaseOneTimeRunner(session).execute(
                spec=spec,
                source_account_ref=source_account_ref,
                window_start=window_start,
                window_end=window_end,
                idempotency_key=idempotency_key,
                reason=reason,
            )
    except PmcPurchaseOneTimeRunError as error:
        print(str(error))
        return 2
    except Exception:
        print("PMC_PURCHASE_ONE_TIME_RUN_FAILED")
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
        raise PmcPurchaseOneTimeRunError("PMC_PURCHASE_ONE_TIME_RUN_ENV_NOT_AUTHORIZED")


def _spec() -> PmcPurchaseSyncInterfaceSpec:
    key = os.getenv("PMC_PURCHASE_INTERFACE_KEY", "")
    spec = PMC_PURCHASE_SPECS_BY_INTERFACE_KEY.get(key)
    if spec is None:
        raise PmcPurchaseOneTimeRunError("PMC_PURCHASE_ONE_TIME_RUN_INTERFACE_KEY_INVALID")
    return spec


def _source_account_ref() -> str:
    try:
        value = validate_pmc_purchase_source_account_ref(
            os.getenv("PMC_PURCHASE_SOURCE_ACCOUNT_REF", "")
        )
    except PmcPurchaseGovernanceBootstrapError:
        raise PmcPurchaseOneTimeRunError(
            "PMC_PURCHASE_ONE_TIME_RUN_SOURCE_ACCOUNT_REF_INVALID"
        ) from None
    return _validate_safe_text(
        value,
        max_length=128,
        error_code="PMC_PURCHASE_ONE_TIME_RUN_SOURCE_ACCOUNT_REF_INVALID",
    )


def _window() -> tuple[date, date]:
    try:
        start = date.fromisoformat(os.getenv("PMC_PURCHASE_WINDOW_START", ""))
        end = date.fromisoformat(os.getenv("PMC_PURCHASE_WINDOW_END", ""))
    except ValueError:
        raise PmcPurchaseOneTimeRunError("PMC_PURCHASE_ONE_TIME_RUN_WINDOW_INVALID") from None
    if start < EARLIEST_WINDOW_START:
        raise PmcPurchaseOneTimeRunError("PMC_PURCHASE_ONE_TIME_RUN_WINDOW_BEFORE_GO_LIVE")
    try:
        validate_pmc_purchase_window(start, end)
    except PmcPurchaseContractError:
        raise PmcPurchaseOneTimeRunError("PMC_PURCHASE_ONE_TIME_RUN_WINDOW_INVALID") from None
    return start, end


def _idempotency_key(spec: PmcPurchaseSyncInterfaceSpec) -> str:
    value = os.getenv("PMC_PURCHASE_ONE_TIME_RUN_IDEMPOTENCY_KEY")
    if value is None:
        return f"pmc-purchase-onetime:{spec.interface_key}:{uuid4()}"
    return _validate_safe_text(
        value,
        max_length=255,
        error_code="PMC_PURCHASE_ONE_TIME_RUN_IDEMPOTENCY_KEY_INVALID",
    )


def _reason() -> str:
    value = os.getenv("PMC_PURCHASE_ONE_TIME_RUN_REASON")
    if value is None:
        return DEFAULT_REASON
    return _validate_safe_text(
        value,
        max_length=1000,
        error_code="PMC_PURCHASE_ONE_TIME_RUN_REASON_INVALID",
    )


def _validate_safe_text(value: str, *, max_length: int, error_code: str) -> str:
    if (
        not value
        or value != value.strip()
        or len(value) > max_length
        or FORBIDDEN_INPUT.search(value)
    ):
        raise PmcPurchaseOneTimeRunError(error_code)
    return value


def _governance_is_authorized(
    spec: PmcPurchaseSyncInterfaceSpec,
    interface: IntegrationInterface,
    policy: RawRetentionPolicy,
    config: IntegrationSyncConfig,
    source_account_ref: str,
) -> bool:
    return bool(
        interface.provider == PROVIDER
        and interface.interface_key == spec.interface_key
        and interface.method == "POST"
        and interface.endpoint_path == spec.endpoint_path
        and interface.request_kind == "offset_page"
        and interface.handler_key == spec.handler_key
        and interface.contract_version == "v1"
        and interface.outbound_enabled is True
        and policy.policy_key == spec.retention_policy_key
        and policy.provider == PROVIDER
        and policy.interface_key == spec.interface_key
        and policy.is_active is True
        and config.source_account_ref == source_account_ref
        and config.is_enabled is True
        and config.schedule_enabled is False
        and config.schedule_cron is None
        and isinstance(config.page_size, int)
        and 1 <= config.page_size <= PMC_PURCHASE_PAGE_SIZE
        and isinstance(config.max_pages, int)
        and config.max_pages > 0
        and config.max_attempts == 1
        and config.retention_policy_id == policy.id
    )


def _print_result(result: PmcPurchaseOneTimeRunResult) -> None:
    print("preflight_status=PASS")
    print(f"interface_key={result.interface_key}")
    print(f"run_id={result.run_id}")
    print(f"run_status={result.run_status}")
    print(f"error_code={result.error_code}")
    print("source_account_ref_present=true")
    print(f"reason_present={str(result.reason_present).lower()}")
    print("trigger_type=manual")
    print("schedule_enabled=false")
    print(f"window_start={result.window_start.isoformat()}")
    print(f"window_end={result.window_end.isoformat()}")
    print(f"page_size={result.page_size}")
    print(f"max_pages={result.max_pages}")
    print(f"work_items_total={result.work_items_total}")
    print(f"work_items_succeeded={result.work_items_succeeded}")
    print(f"work_items_failed={result.work_items_failed}")
    print(f"records_seen={result.records_seen}")
    print(f"records_written={result.records_written}")
    print(f"headers_written={result.headers_written}")
    print(f"lines_written={result.lines_written}")
    print(f"duplicates_skipped={result.duplicates_skipped}")
    print(f"quality={result.quality_summary}")


if __name__ == "__main__":
    raise SystemExit(main())

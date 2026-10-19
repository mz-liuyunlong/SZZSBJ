"""Owner-authorized one-time run for one or all domestic warehouse Lingxing feeds.

Set ``PMC_DOMESTIC_INTERFACE_KEY`` to one catalog key, or ``all`` to run the four
ODS interfaces sequentially (warehouse, inventory, batch detail, batch statement).

Environment (none printed):
  PMC_DOMESTIC_ONE_TIME_RUN_AUTHORIZED=true
  PMC_DOMESTIC_SOURCE_ACCOUNT_REF
  PMC_DOMESTIC_INTERFACE_KEY          domesticWarehouseList | … | all
  PMC_DOMESTIC_WINDOW_START / _END    required for batch statement only (YYYY-MM-DD)
  PMC_DOMESTIC_ONE_TIME_RUN_IDEMPOTENCY_KEY   optional prefix; each interface gets a suffix
  PMC_DOMESTIC_ONE_TIME_RUN_REASON    optional
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
from app.integrations.lingxing.pmc_domestic_contracts import (  # noqa: E402
    PmcDomesticContractError,
    default_statement_window_end,
    validate_pmc_domestic_window,
)
from app.modules.integration_sync.catalog import (  # noqa: E402
    PmcDomesticGovernanceBootstrapError,
    validate_pmc_domestic_source_account_ref,
)
from app.modules.integration_sync.handlers.lingxing_pmc_domestic_sync import (  # noqa: E402
    PMC_DOMESTIC_HANDLERS,
)
from app.modules.integration_sync.models import (  # noqa: E402
    IntegrationInterface,
    IntegrationSyncConfig,
    IntegrationSyncRun,
    RawRetentionPolicy,
    utc_now,
)
from app.modules.integration_sync.pmc_domestic_catalog import (  # noqa: E402
    PMC_DOMESTIC_SPECS_BY_INTERFACE_KEY,
    PMC_DOMESTIC_SYNC_INTERFACE_SPECS,
    PmcDomesticSyncInterfaceSpec,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository  # noqa: E402

PROVIDER = "lingxing"
REQUESTED_BY = "owner-authorized-cli"
DEFAULT_REASON = "Owner-authorized one-time PMC domestic warehouse sync"
FORBIDDEN_INPUT = re.compile(
    r"https?://|(?:^|[^a-z0-9])(?:app(?:_|[ -])?(?:id|secret)|authorization|bearer|"
    r"database(?:_|[ -])?url|access(?:_|[ -])?token|refresh(?:_|[ -])?token|secret|"
    r"sign|token|raw|payload(?:_|[ -])?json|sku|msku|"
    r"product(?:_|[ -])?(?:name|title|image|value)|image(?:_|[ -])?url)"
    r"(?:$|[^a-z0-9])",
    re.IGNORECASE,
)


class PmcDomesticOneTimeRunError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PmcDomesticOneTimeRunResult:
    run_id: UUID
    interface_key: str
    run_status: str
    error_code: str | None
    records_written: int
    duplicates_skipped: int
    window_start: date | None
    window_end: date | None


class PmcDomesticOneTimeRunner:
    def __init__(self, session: Session) -> None:
        register_productlist_sync_models()
        self.session = session
        self.repository = IntegrationSyncRepository(session)

    def execute(
        self,
        *,
        spec: PmcDomesticSyncInterfaceSpec,
        source_account_ref: str,
        window_start: date | None,
        window_end: date | None,
        idempotency_key: str,
        reason: str,
    ) -> PmcDomesticOneTimeRunResult:
        if spec.requires_date_window and (window_start is None or window_end is None):
            raise PmcDomesticOneTimeRunError("PMC_DOMESTIC_ONE_TIME_RUN_WINDOW_REQUIRED")
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
            raise PmcDomesticOneTimeRunError("PMC_DOMESTIC_ONE_TIME_RUN_GOVERNANCE_NOT_AUTHORIZED")
        for other in PMC_DOMESTIC_SPECS_BY_INTERFACE_KEY:
            if self.repository.has_running_run(PROVIDER, other):
                raise PmcDomesticOneTimeRunError("PMC_DOMESTIC_ONE_TIME_RUN_ALREADY_RUNNING")
        if self.repository.find_run_by_idempotency(idempotency_key) is not None:
            raise PmcDomesticOneTimeRunError("PMC_DOMESTIC_ONE_TIME_RUN_IDEMPOTENCY_CONFLICT")

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
            request_id=f"pmc-domestic-one-time-run:{uuid4()}",
            reason=reason,
            window_start=(
                datetime.combine(window_start, datetime.min.time(), tzinfo=UTC)
                if window_start is not None
                else None
            ),
            window_end=(
                datetime.combine(window_end, datetime.min.time(), tzinfo=UTC)
                if window_end is not None
                else None
            ),
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
            raise PmcDomesticOneTimeRunError("PMC_DOMESTIC_ONE_TIME_RUN_CONFLICT") from None

        execution = PMC_DOMESTIC_HANDLERS[spec.interface_key](self.session).execute(run, interface)
        return PmcDomesticOneTimeRunResult(
            run_id=run.id,
            interface_key=spec.interface_key,
            run_status=run.status,
            error_code=run.error_code,
            records_written=execution.records_written,
            duplicates_skipped=execution.duplicates_skipped,
            window_start=window_start,
            window_end=window_end,
        )


def main() -> int:
    if os.getenv("PMC_DOMESTIC_ONE_TIME_RUN_AUTHORIZED", "").casefold() != "true":
        print("PMC_DOMESTIC_ONE_TIME_RUN_REQUIRES_AUTHORIZATION")
        return 2
    try:
        specs = _specs()
        source_account_ref = _source_account_ref()
        window_start, window_end = _statement_window()
        reason = _reason()
        settings = get_settings()
        _validate_runtime_settings(settings)
    except PmcDomesticOneTimeRunError as error:
        print(str(error))
        return 2
    except Exception:
        print("PMC_DOMESTIC_ONE_TIME_RUN_ENV_NOT_AUTHORIZED")
        return 2

    idempotency_prefix = _idempotency_prefix()
    exit_code = 0
    try:
        with get_session_factory()() as session:
            runner = PmcDomesticOneTimeRunner(session)
            for spec in specs:
                key = f"{idempotency_prefix}:{spec.interface_key}:{uuid4()}"
                result = runner.execute(
                    spec=spec,
                    source_account_ref=source_account_ref,
                    window_start=window_start if spec.requires_date_window else None,
                    window_end=window_end if spec.requires_date_window else None,
                    idempotency_key=key,
                    reason=reason,
                )
                _print_result(result)
                if result.run_status != "succeeded":
                    exit_code = 1
    except PmcDomesticOneTimeRunError as error:
        print(str(error))
        return 2
    except Exception:
        print("PMC_DOMESTIC_ONE_TIME_RUN_FAILED")
        return 1
    return exit_code


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
        raise PmcDomesticOneTimeRunError("PMC_DOMESTIC_ONE_TIME_RUN_ENV_NOT_AUTHORIZED")


def _specs() -> tuple[PmcDomesticSyncInterfaceSpec, ...]:
    key = os.getenv("PMC_DOMESTIC_INTERFACE_KEY", "all").strip()
    if key.casefold() == "all":
        return PMC_DOMESTIC_SYNC_INTERFACE_SPECS
    spec = PMC_DOMESTIC_SPECS_BY_INTERFACE_KEY.get(key)
    if spec is None:
        raise PmcDomesticOneTimeRunError("PMC_DOMESTIC_ONE_TIME_RUN_INTERFACE_KEY_INVALID")
    return (spec,)


def _source_account_ref() -> str:
    try:
        value = validate_pmc_domestic_source_account_ref(
            os.getenv("PMC_DOMESTIC_SOURCE_ACCOUNT_REF", "")
        )
    except PmcDomesticGovernanceBootstrapError:
        raise PmcDomesticOneTimeRunError(
            "PMC_DOMESTIC_ONE_TIME_RUN_SOURCE_ACCOUNT_REF_INVALID"
        ) from None
    return _validate_safe_text(
        value,
        max_length=128,
        error_code="PMC_DOMESTIC_ONE_TIME_RUN_SOURCE_ACCOUNT_REF_INVALID",
    )


def _statement_window() -> tuple[date | None, date | None]:
    start_raw = os.getenv("PMC_DOMESTIC_WINDOW_START", "").strip()
    end_raw = os.getenv("PMC_DOMESTIC_WINDOW_END", "").strip()
    if not start_raw and not end_raw:
        today = date.today()
        return default_statement_window_end(today)
    if not start_raw or not end_raw:
        raise PmcDomesticOneTimeRunError("PMC_DOMESTIC_ONE_TIME_RUN_WINDOW_INVALID")
    try:
        start = date.fromisoformat(start_raw)
        end = date.fromisoformat(end_raw)
    except ValueError:
        raise PmcDomesticOneTimeRunError("PMC_DOMESTIC_ONE_TIME_RUN_WINDOW_INVALID") from None
    try:
        validate_pmc_domestic_window(start, end)
    except PmcDomesticContractError:
        raise PmcDomesticOneTimeRunError("PMC_DOMESTIC_ONE_TIME_RUN_WINDOW_INVALID") from None
    return start, end


def _idempotency_prefix() -> str:
    value = os.getenv("PMC_DOMESTIC_ONE_TIME_RUN_IDEMPOTENCY_KEY")
    if value is None:
        return f"pmc-domestic-onetime:{uuid4()}"
    return _validate_safe_text(
        value,
        max_length=200,
        error_code="PMC_DOMESTIC_ONE_TIME_RUN_IDEMPOTENCY_KEY_INVALID",
    )


def _reason() -> str:
    value = os.getenv("PMC_DOMESTIC_ONE_TIME_RUN_REASON")
    if value is None:
        return DEFAULT_REASON
    return _validate_safe_text(
        value,
        max_length=1000,
        error_code="PMC_DOMESTIC_ONE_TIME_RUN_REASON_INVALID",
    )


def _validate_safe_text(value: str, *, max_length: int, error_code: str) -> str:
    if (
        not value
        or value != value.strip()
        or len(value) > max_length
        or FORBIDDEN_INPUT.search(value)
    ):
        raise PmcDomesticOneTimeRunError(error_code)
    return value


def _governance_is_authorized(
    spec: PmcDomesticSyncInterfaceSpec,
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
        and 1 <= config.page_size <= spec.default_page_size
        and isinstance(config.max_pages, int)
        and config.max_pages > 0
        and config.max_attempts == 1
        and config.retention_policy_id == policy.id
    )


def _print_result(result: PmcDomesticOneTimeRunResult) -> None:
    print("preflight_status=PASS")
    print(f"interface_key={result.interface_key}")
    print(f"run_id={result.run_id}")
    print(f"run_status={result.run_status}")
    print(f"error_code={result.error_code}")
    print(f"records_written={result.records_written}")
    print(f"duplicates_skipped={result.duplicates_skipped}")
    if result.window_start is not None:
        print(f"window_start={result.window_start.isoformat()}")
        print(f"window_end={result.window_end.isoformat() if result.window_end else ''}")


if __name__ == "__main__":
    raise SystemExit(main())

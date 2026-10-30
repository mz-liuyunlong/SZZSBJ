"""Owner-authorized one-time run of the WFS shipment-board Lingxing feeds.

Runs ``wfsCargoPage`` then ``wfsShippingListPage`` (or one of them) for one account over one
creation-time window, then optionally publishes the board from the two new runs.

Environment (none printed):
  PMC_WFS_ONE_TIME_RUN_AUTHORIZED=true
  PMC_WFS_SOURCE_ACCOUNT_REF
  PMC_WFS_INTERFACE_KEY              wfsCargoPage | wfsShippingListPage | all   (default all)
  PMC_WFS_WINDOW_START / _END        creation window, YYYY-MM-DD (default 2026-05-01 → today)
  PMC_WFS_PUBLISH_AFTER_RUN          true → publish a board version when every run succeeds
  PMC_WFS_ONE_TIME_RUN_IDEMPOTENCY_KEY   optional prefix
  PMC_WFS_ONE_TIME_RUN_REASON        optional

Governance rows (interface outbound_enabled, config is_enabled) must already be opened by
the owner for this run and are expected to be closed again afterwards; the runner refuses
scheduled configs. Local dev databases are allowed with APP_ENV=local.
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
from app.integrations.lingxing.pmc_wfs_contracts import (  # noqa: E402
    PmcWfsContractError,
    validate_pmc_wfs_window,
)
from app.modules.integration_sync.catalog import (  # noqa: E402
    PmcDomesticGovernanceBootstrapError,
    validate_pmc_domestic_source_account_ref,
)
from app.modules.integration_sync.handlers.lingxing_pmc_wfs_board_sync import (  # noqa: E402
    PMC_WFS_HANDLERS,
)
from app.modules.integration_sync.models import (  # noqa: E402
    IntegrationInterface,
    IntegrationSyncConfig,
    IntegrationSyncRun,
    RawRetentionPolicy,
    utc_now,
)
from app.modules.integration_sync.pmc_wfs_catalog import (  # noqa: E402
    PMC_WFS_SPECS_BY_INTERFACE_KEY,
    PMC_WFS_SYNC_INTERFACE_SPECS,
    PmcWfsSyncInterfaceSpec,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository  # noqa: E402
from app.modules.pmc_wfs.board_publisher import WfsBoardPublisher  # noqa: E402

PROVIDER = "lingxing"
REQUESTED_BY = "owner-authorized-cli"
DEFAULT_REASON = "Owner-authorized one-time PMC WFS shipment-board sync"
DEFAULT_WINDOW_START = date(2026, 5, 1)
FORBIDDEN_INPUT = re.compile(
    r"https?://|(?:^|[^a-z0-9])(?:app(?:_|[ -])?(?:id|secret)|authorization|bearer|"
    r"database(?:_|[ -])?url|access(?:_|[ -])?token|refresh(?:_|[ -])?token|secret|"
    r"sign|token|raw|payload(?:_|[ -])?json|sku|msku|"
    r"product(?:_|[ -])?(?:name|title|image|value)|image(?:_|[ -])?url)"
    r"(?:$|[^a-z0-9])",
    re.IGNORECASE,
)


class PmcWfsOneTimeRunError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PmcWfsOneTimeRunResult:
    run_id: UUID
    interface_key: str
    run_status: str
    error_code: str | None
    records_written: int
    duplicates_skipped: int
    window_start: date
    window_end: date


class PmcWfsOneTimeRunner:
    def __init__(self, session: Session) -> None:
        register_productlist_sync_models()
        self.session = session
        self.repository = IntegrationSyncRepository(session)

    def execute(
        self,
        *,
        spec: PmcWfsSyncInterfaceSpec,
        source_account_ref: str,
        window_start: date,
        window_end: date,
        idempotency_key: str,
        reason: str,
    ) -> PmcWfsOneTimeRunResult:
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
            raise PmcWfsOneTimeRunError("PMC_WFS_ONE_TIME_RUN_GOVERNANCE_NOT_AUTHORIZED")
        for other in PMC_WFS_SPECS_BY_INTERFACE_KEY:
            if self.repository.has_running_run(PROVIDER, other):
                raise PmcWfsOneTimeRunError("PMC_WFS_ONE_TIME_RUN_ALREADY_RUNNING")
        if self.repository.find_run_by_idempotency(idempotency_key) is not None:
            raise PmcWfsOneTimeRunError("PMC_WFS_ONE_TIME_RUN_IDEMPOTENCY_CONFLICT")

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
            request_id=f"pmc-wfs-one-time-run:{uuid4()}",
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
            raise PmcWfsOneTimeRunError("PMC_WFS_ONE_TIME_RUN_CONFLICT") from None

        execution = PMC_WFS_HANDLERS[spec.interface_key](self.session).execute(run, interface)
        return PmcWfsOneTimeRunResult(
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
    if os.getenv("PMC_WFS_ONE_TIME_RUN_AUTHORIZED", "").casefold() != "true":
        print("PMC_WFS_ONE_TIME_RUN_REQUIRES_AUTHORIZATION")
        return 2
    try:
        specs = _specs()
        source_account_ref = _source_account_ref()
        window_start, window_end = _window()
        reason = _reason()
        settings = get_settings()
        _validate_runtime_settings(settings)
    except PmcWfsOneTimeRunError as error:
        print(str(error))
        return 2
    except Exception:
        print("PMC_WFS_ONE_TIME_RUN_ENV_NOT_AUTHORIZED")
        return 2

    idempotency_prefix = _idempotency_prefix()
    publish_after = os.getenv("PMC_WFS_PUBLISH_AFTER_RUN", "").casefold() == "true"
    exit_code = 0
    run_ids: dict[str, UUID] = {}
    try:
        with get_session_factory()() as session:
            runner = PmcWfsOneTimeRunner(session)
            for spec in specs:
                key = f"{idempotency_prefix}:{spec.interface_key}:{uuid4()}"
                result = runner.execute(
                    spec=spec,
                    source_account_ref=source_account_ref,
                    window_start=window_start,
                    window_end=window_end,
                    idempotency_key=key,
                    reason=reason,
                )
                _print_result(result)
                run_ids[spec.interface_key] = result.run_id
                if result.run_status != "succeeded":
                    exit_code = 1
            if publish_after and exit_code == 0 and "wfsCargoPage" in run_ids:
                published = WfsBoardPublisher(session).publish(
                    account=source_account_ref,
                    cargo_run_id=run_ids["wfsCargoPage"],
                    shipping_run_id=run_ids.get("wfsShippingListPage"),
                )
                print(f"publication_id={published.publication_id}")
                print(f"board_rows={published.rows}")
                print(f"cargos_without_shipping={published.cargos_without_shipping}")
    except PmcWfsOneTimeRunError as error:
        print(str(error))
        return 2
    except Exception:
        print("PMC_WFS_ONE_TIME_RUN_FAILED")
        return 1
    return exit_code


def _validate_runtime_settings(settings: Settings) -> None:
    if not (
        settings.app_env in {AppEnvironment.PRODUCTION, AppEnvironment.LOCAL}
        and settings.lingxing_enable_token_requests is True
        and settings.lingxing_enable_real_calls is True
        and settings.lingxing_dry_run is False
        and settings.lingxing_allow_raw_write is True
        and settings.lingxing_allow_full_sync is False
    ):
        raise PmcWfsOneTimeRunError("PMC_WFS_ONE_TIME_RUN_ENV_NOT_AUTHORIZED")


def _specs() -> tuple[PmcWfsSyncInterfaceSpec, ...]:
    key = os.getenv("PMC_WFS_INTERFACE_KEY", "all").strip()
    if key.casefold() == "all":
        return PMC_WFS_SYNC_INTERFACE_SPECS
    spec = PMC_WFS_SPECS_BY_INTERFACE_KEY.get(key)
    if spec is None:
        raise PmcWfsOneTimeRunError("PMC_WFS_ONE_TIME_RUN_INTERFACE_KEY_INVALID")
    return (spec,)


def _source_account_ref() -> str:
    try:
        value = validate_pmc_domestic_source_account_ref(
            os.getenv("PMC_WFS_SOURCE_ACCOUNT_REF", "")
        )
    except PmcDomesticGovernanceBootstrapError:
        raise PmcWfsOneTimeRunError("PMC_WFS_ONE_TIME_RUN_SOURCE_ACCOUNT_REF_INVALID") from None
    return _validate_safe_text(
        value, max_length=128, error_code="PMC_WFS_ONE_TIME_RUN_SOURCE_ACCOUNT_REF_INVALID"
    )


def _window() -> tuple[date, date]:
    start_raw = os.getenv("PMC_WFS_WINDOW_START", "").strip()
    end_raw = os.getenv("PMC_WFS_WINDOW_END", "").strip()
    try:
        start = date.fromisoformat(start_raw) if start_raw else DEFAULT_WINDOW_START
        end = date.fromisoformat(end_raw) if end_raw else date.today()
    except ValueError:
        raise PmcWfsOneTimeRunError("PMC_WFS_ONE_TIME_RUN_WINDOW_INVALID") from None
    try:
        validate_pmc_wfs_window(start, end)
    except PmcWfsContractError:
        raise PmcWfsOneTimeRunError("PMC_WFS_ONE_TIME_RUN_WINDOW_INVALID") from None
    return start, end


def _idempotency_prefix() -> str:
    value = os.getenv("PMC_WFS_ONE_TIME_RUN_IDEMPOTENCY_KEY")
    if value is None:
        return f"pmc-wfs-onetime:{uuid4()}"
    return _validate_safe_text(
        value, max_length=200, error_code="PMC_WFS_ONE_TIME_RUN_IDEMPOTENCY_KEY_INVALID"
    )


def _reason() -> str:
    value = os.getenv("PMC_WFS_ONE_TIME_RUN_REASON")
    if value is None:
        return DEFAULT_REASON
    return _validate_safe_text(
        value, max_length=1000, error_code="PMC_WFS_ONE_TIME_RUN_REASON_INVALID"
    )


def _validate_safe_text(value: str, *, max_length: int, error_code: str) -> str:
    if (
        not value
        or value != value.strip()
        or len(value) > max_length
        or FORBIDDEN_INPUT.search(value)
    ):
        raise PmcWfsOneTimeRunError(error_code)
    return value


def _governance_is_authorized(
    spec: PmcWfsSyncInterfaceSpec,
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


def _print_result(result: PmcWfsOneTimeRunResult) -> None:
    print("preflight_status=PASS")
    print(f"interface_key={result.interface_key}")
    print(f"run_id={result.run_id}")
    print(f"run_status={result.run_status}")
    print(f"error_code={result.error_code}")
    print(f"records_written={result.records_written}")
    print(f"duplicates_skipped={result.duplicates_skipped}")
    print(f"window_start={result.window_start.isoformat()}")
    print(f"window_end={result.window_end.isoformat()}")


if __name__ == "__main__":
    raise SystemExit(main())

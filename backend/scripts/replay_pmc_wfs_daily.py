"""Local replay of one collected WFS daily folder into a local / test database (no API calls).

Used to compare the 5173 pages with the 8088 demo on the same data day (AGENTS §1.1 step 4).
Reads the folder the approved collectors already produced::

    <daily>/lingxing/wfs_cargos.csv, shipping_lists.csv, logistics_channels.csv
    <daily>/walmart/<store_id>/{shipments,items,inventory_log}.csv
    <daily>/zhongyi/{orders_summary,orders_track}.csv

and writes the same RAW → ODS → MART chain as the real sync: the two Lingxing pages go
through the real sync handler with a file-backed page client (RAW envelopes keep the
replayed records), the other files go through :class:`WfsSourceLoader`, then the board is
published. Refused outside ``APP_ENV`` local / test or against a non-loopback database.

Usage::

    APP_ENV=local PMC_WFS_REPLAY_AUTHORIZED=true PMC_WFS_SOURCE_ACCOUNT_REF=<account> \\
      uv run python scripts/replay_pmc_wfs_daily.py <daily folder>
"""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import AppEnvironment, get_database_url, get_settings  # noqa: E402
from app.db.model_registry import register_productlist_sync_models  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.integrations.lingxing.client import LingxingRawEnvelope  # noqa: E402
from app.modules.integration_sync.catalog import IntegrationCatalogService  # noqa: E402
from app.modules.integration_sync.handlers.lingxing_pmc_wfs_board_sync import (  # noqa: E402
    PMC_WFS_HANDLERS,
)
from app.modules.integration_sync.models import IntegrationSyncRun, utc_now  # noqa: E402
from app.modules.integration_sync.pmc_wfs_catalog import (  # noqa: E402
    PMC_WFS_SYNC_INTERFACE_SPECS,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository  # noqa: E402
from app.modules.pmc_wfs.board_publisher import WfsBoardPublisher  # noqa: E402
from app.modules.pmc_wfs.exception_detector import WfsExceptionDetector  # noqa: E402
from app.modules.pmc_wfs.source_loader import WfsSourceLoader  # noqa: E402

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
FILES = {"wfsCargoPage": "wfs_cargos.csv", "wfsShippingListPage": "shipping_lists.csv"}
REPLAY_ACTOR = "local-file-replay"


class ReplayRefused(RuntimeError):
    pass


def _decode(value: str) -> Any:
    text_value = (value or "").strip()
    if text_value[:1] in "[{":
        try:
            return json.loads(text_value)
        except ValueError:
            return value
    return value


def read_records(path: Path) -> list[dict[str, Any]]:
    csv.field_size_limit(10**9)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [{k: _decode(v) for k, v in row.items()} for row in csv.DictReader(handle)]


class FilePageClient:
    """Serves collected records as Lingxing page envelopes (offset / length)."""

    def __init__(self, records: list[dict[str, Any]], pulled_at: datetime) -> None:
        self.records = records
        self.pulled_at = pulled_at

    def fetch_pmc_wfs_page(
        self,
        *,
        api_path: str,
        offset: int,
        length: int,
        page_no: int,
        run_id: str,
        work_item_id: str,
        **_: Any,
    ) -> LingxingRawEnvelope:
        chunk = self.records[offset : offset + length]
        return LingxingRawEnvelope(
            api_path=api_path,  # type: ignore[arg-type]
            request_body_json={"offset": offset, "length": length, "replay": True},
            response_json={
                "code": 0,
                "message": "success",
                "error_details": [],
                "request_id": f"replay-{uuid4()}",
                "response_time": self.pulled_at.strftime("%Y-%m-%d %H:%M:%S"),
                "data": {"total": str(len(self.records)), "records": chunk},
            },
            response_code=200,
            is_success=True,
            pulled_at=self.pulled_at,
            page_no=page_no,
            page_size=length,
            object_type="pmc_wfs_local_replay",
            trace_id=work_item_id,
            run_id=run_id,
            batch_id=f"replay-{uuid4()}",
            attempt_no=1,
        )


def _data_day(daily: Path, pulled_at: datetime) -> date:
    try:
        return datetime.strptime(daily.name, "%Y%m%d").date()
    except ValueError:
        return pulled_at.date()


def guard_target() -> None:
    settings = get_settings()
    if settings.app_env not in {AppEnvironment.LOCAL, AppEnvironment.TEST}:
        raise ReplayRefused("PMC_WFS_REPLAY_LOCAL_ONLY")
    url = get_database_url(settings)
    if url.host not in LOOPBACK or url.query:
        raise ReplayRefused("PMC_WFS_REPLAY_LOOPBACK_DATABASE_ONLY")


def replay(session: Session, daily: Path, account: str) -> dict[str, Any]:
    register_productlist_sync_models()
    manifest = json.loads((daily / "manifest.json").read_text(encoding="utf-8"))
    started = str(manifest.get("started_at") or "")[:19]
    pulled_at = (
        datetime.fromisoformat(started).replace(tzinfo=UTC) if started else datetime.now(UTC)
    )
    IntegrationCatalogService(session).bootstrap_pmc_wfs_board_governance(account)
    repo = IntegrationSyncRepository(session)
    run_ids = {}
    for spec in PMC_WFS_SYNC_INTERFACE_SPECS:
        records = read_records(daily / "lingxing" / FILES[spec.interface_key])
        interface = repo.get_interface_by_key("lingxing", spec.interface_key)
        config = repo.get_config_by_scope(interface.id, account)
        saved = (interface.outbound_enabled, config.is_enabled, config.page_size, config.max_pages)
        # Local replay only: open the manual gate for this one run, restore right after.
        interface.outbound_enabled = True
        config.is_enabled = True
        config.page_size = config.page_size or spec.default_page_size
        config.max_pages = max(config.max_pages or 0, len(records) // config.page_size + 2)
        run = IntegrationSyncRun(
            id=uuid4(),
            config_id=config.id,
            interface_id=interface.id,
            provider="lingxing",
            interface_key=spec.interface_key,
            source_account_ref=account,
            trigger_type="manual",
            status="queued",
            idempotency_key=f"replay:{daily.name}:{spec.interface_key}:{uuid4()}",
            requested_by=REPLAY_ACTOR,
            request_id=f"pmc-wfs-replay:{uuid4()}",
            reason=f"Local file replay of daily/{daily.name}",
            window_start=datetime(2026, 5, 1, tzinfo=UTC),
            window_end=datetime.combine(
                min(pulled_at.date(), date.today()), datetime.min.time(), tzinfo=UTC
            ),
            queued_at=utc_now(),
            work_items_total=0,
            work_items_succeeded=0,
            work_items_failed=0,
            records_seen=0,
            records_written=0,
        )
        repo.add_run(run)
        session.commit()
        try:
            handler = PMC_WFS_HANDLERS[spec.interface_key](
                session, client=FilePageClient(records, pulled_at), page_gap_seconds=0
            )
            result = handler.execute(run, interface)
        finally:
            interface.outbound_enabled, config.is_enabled = saved[0], saved[1]
            config.page_size, config.max_pages = saved[2], saved[3]
            session.commit()
        if result.status != "succeeded":
            raise ReplayRefused(f"PMC_WFS_REPLAY_RUN_FAILED:{run.error_code}")
        run_ids[spec.interface_key] = run.id
    loaded = WfsSourceLoader(session, actor=REPLAY_ACTOR, batch_label=daily.name).load_directory(
        daily
    )
    published = WfsBoardPublisher(session).publish(
        account=account,
        cargo_run_id=run_ids["wfsCargoPage"],
        shipping_run_id=run_ids["wfsShippingListPage"],
        as_of=_data_day(daily, pulled_at),
    )
    detected = WfsExceptionDetector(session, account, today=_data_day(daily, pulled_at)).run()
    session.commit()
    return {
        "exceptions": detected,
        "publication_id": str(published.publication_id),
        "board_rows": published.rows,
        "files": [(f.source, f.endpoint, f.scope_key, f.loaded_rows, f.skipped) for f in loaded],
    }


def main(argv: list[str]) -> int:
    if os.getenv("PMC_WFS_REPLAY_AUTHORIZED", "").casefold() != "true":
        print("PMC_WFS_REPLAY_REQUIRES_AUTHORIZATION")
        return 2
    if len(argv) != 2:
        print("usage: replay_pmc_wfs_daily.py <daily folder>")
        return 2
    account = os.getenv("PMC_WFS_SOURCE_ACCOUNT_REF", "").strip()
    daily = Path(argv[1]).resolve()
    try:
        guard_target()
        if not account or not (daily / "manifest.json").is_file():
            raise ReplayRefused("PMC_WFS_REPLAY_INPUT_INVALID")
        with get_session_factory()() as session:
            result = replay(session, daily, account)
    except ReplayRefused as error:
        print(str(error))
        return 2
    print(f"publication_id={result['publication_id']}")
    print(f"board_rows={result['board_rows']}")
    detected = result["exceptions"]
    print(
        f"exception_hits={detected.hits} created={detected.created} "
        f"auto_resolved={detected.auto_resolved} rule_version={detected.rule_version}"
    )
    for source, endpoint, scope, rows, skipped in result["files"]:
        print(f"{source}/{endpoint}/{scope}: rows={rows}{' (already loaded)' if skipped else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

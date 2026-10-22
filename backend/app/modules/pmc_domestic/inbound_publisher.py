"""Publish only explicitly selected succeeded ODS runs; never call Lingxing."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.modules.integration_sync.models import ApiRawRequestRef, IntegrationSyncRun
from app.modules.pmc_domestic.inbound_builder import (
    VERSION,
    InboundDataError,
    build_inbound_rows,
)
from app.modules.pmc_domestic.inbound_models import (
    DomesticBoardPublication as Pub,
)
from app.modules.pmc_domestic.inbound_models import (
    DomesticInboundBoard as Board,
)
from app.modules.pmc_domestic.inbound_models import (
    DomesticWarehouseStatement,
)
from app.modules.pmc_domestic.models import LingxingDomesticBatchOds
from app.modules.pmc_domestic.packing_customs_materializer import enrich_customs


class InboundPublisher:
    def __init__(self, session: Session) -> None:
        self.session = session

    def publish(
        self,
        *,
        account: str,
        warehouse: str,
        batch_run_id: UUID,
        statement_run_ids: list[UUID],
        source_timezone: str | None = None,
    ) -> UUID:
        try:
            if not account.strip() or not warehouse.strip() or not statement_run_ids:
                raise InboundDataError("INBOUND_PUBLICATION_SCOPE_INVALID")
            wanted = {batch_run_id, *statement_run_ids}
            runs = list(
                self.session.scalars(
                    select(IntegrationSyncRun).where(
                        IntegrationSyncRun.id.in_(wanted),
                        IntegrationSyncRun.source_account_ref == account,
                        IntegrationSyncRun.status == "succeeded",
                        IntegrationSyncRun.provider == "lingxing",
                    )
                )
            )
            if len(runs) != len(wanted):
                raise InboundDataError("INBOUND_SUCCESSFUL_RUNS_REQUIRED")
            by_id = {r.id: r for r in runs}
            if by_id[batch_run_id].interface_key != "domesticBatchDetailList" or any(
                by_id[r].interface_key != "domesticWarehouseStatement" for r in statement_run_ids
            ):
                raise InboundDataError("INBOUND_RUN_INTERFACE_MISMATCH")
            refs = list(
                self.session.scalars(
                    select(ApiRawRequestRef).where(
                        ApiRawRequestRef.run_id == batch_run_id,
                        ApiRawRequestRef.is_success.is_(True),
                    )
                )
            )
            if not refs or any(r.request_safe_params.get("show_zero_stock") != 1 for r in refs):
                raise InboundDataError("INBOUND_ZERO_STOCK_SNAPSHOT_REQUIRED")
            windows = [(by_id[r].window_start, by_id[r].window_end) for r in statement_run_ids]
            if any(not start or not end or start >= end for start, end in windows):
                raise InboundDataError("INBOUND_SOURCE_WINDOW_INVALID")
            windows.sort()
            end = windows[0][1]
            for start, stop in windows[1:]:
                if start > end:
                    raise InboundDataError("INBOUND_SOURCE_WINDOW_GAP")
                end = max(end, stop)
            batch_ods = list(
                self.session.scalars(
                    select(LingxingDomesticBatchOds).where(
                        LingxingDomesticBatchOds.source_account_ref == account,
                        LingxingDomesticBatchOds.run_id == batch_run_id,
                    )
                )
            )
            statement_ods = list(
                self.session.scalars(
                    select(DomesticWarehouseStatement)
                    .where(
                        DomesticWarehouseStatement.source_account_ref == account,
                        DomesticWarehouseStatement.run_id.in_(statement_run_ids),
                    )
                    .order_by(DomesticWarehouseStatement.observed_at)
                )
            )
            # A later completed reread may supersede a mutable source event. The
            # evidence remains append-only in ODS; select its latest observed copy.
            latest = {r.statement_id: r for r in statement_ods}
            projection = build_inbound_rows(
                [r.payload_json for r in latest.values()],
                [r.payload_json for r in batch_ods],
                account=account,
                warehouse=warehouse,
                source_timezone=source_timezone,
            )
            enrich_customs(self.session, account, projection)
            all_refs = list(
                self.session.scalars(
                    select(ApiRawRequestRef).where(
                        ApiRawRequestRef.run_id.in_(wanted),
                        ApiRawRequestRef.is_success.is_(True),
                    )
                )
            )
            if {r.run_id for r in all_refs} != wanted:
                raise InboundDataError("INBOUND_SOURCE_EVIDENCE_MISSING")
            observed = min(r.received_at for r in all_refs)
            identity = self._save(
                account,
                warehouse,
                projection,
                batch_run_id,
                statement_run_ids,
                windows[0][0].date(),
                end.date(),
                observed,
            )
            self.session.commit()
            return identity
        except Exception:
            self.session.rollback()
            raise

    def _save(
        self,
        account: str,
        warehouse: str,
        rows: list[dict],
        batch_run_id: UUID,
        statement_run_ids: list[UUID],
        start: date,
        end: date,
        observed: datetime,
    ) -> UUID:
        if self.session.get_bind().dialect.name == "postgresql":
            key = int.from_bytes(
                hashlib.sha256(f"{account}\0{warehouse}".encode()).digest()[:8], signed=True
            )
            self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
        identity = uuid4()
        self.session.add(
            Pub(
                id=identity,
                source_account_ref=account,
                source_warehouse_id=warehouse,
                status="published",
                is_current=False,
                batch_run_id=batch_run_id,
                statement_run_ids=[str(r) for r in statement_run_ids],
                coverage_start=start,
                coverage_end=end,
                source_observed_at=observed,
                published_at=datetime.now(UTC),
                builder_version=VERSION,
                quality_report={"rows": len(rows), "complete": True},
            )
        )
        self.session.flush()
        for row in rows:
            self.session.add(
                Board(
                    publication_id=identity,
                    id=UUID(row["id"]),
                    source_account_ref=account,
                    source_warehouse_id=warehouse,
                    inbound_order_sn=row["inbound_order_sn"],
                    sku=row["sku"],
                    store_id=row["store_id"],
                    attribution_key=row["store_id"] or "unknown",
                    arrival_business_date=date.fromisoformat(row["arrival_business_date"])
                    if row["arrival_business_date"]
                    else None,
                    balance_num=row["balance_num"],
                    payload_json=row,
                )
            )
        self.session.flush()
        self.session.execute(
            update(Pub)
            .where(
                Pub.source_account_ref == account,
                Pub.source_warehouse_id == warehouse,
                Pub.is_current.is_(True),
            )
            .values(is_current=False)
        )
        self.session.flush()
        self.session.execute(update(Pub).where(Pub.id == identity).values(is_current=True))
        return identity

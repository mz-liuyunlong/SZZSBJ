"""Manual SKU purchase-cycle overrides (Gate 3, G3-F; PRP §7.5, rules §4.2).

The only human write on the purchase board (Owner 2026-09-21: no manual ItemID).
Contract (docs/MANUAL_OVERRIDE_BOUNDARY_RULES.md):

* append-only: every correction is a new ``manual_purchase_cycle_override`` row with
  before / after / operator / reason / request reference; undo is a newer record
  (``restore`` for an exclusion, a new ``baseline`` for a baseline), never a delete;
* the source values in DWD are never touched; the DWS is rebuilt after the write so the
  effective value is visible immediately;
* the same ``request_id`` applied twice returns the first record (idempotent replay).

Validation reads the current ``dws_purchase_sku_cycle`` row: ``exclude`` / ``restore`` /
``arrival_date`` must name a purchase order that is one of the SKU's arrived samples.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.pmc_purchase.gate3_models import (
    DwsPurchaseSkuCycle,
    ManualPurchaseCycleOverride,
)
from app.modules.pmc_purchase.refresh import PmcPurchaseDwsRefresher, PmcPurchaseDwsRefreshError
from app.modules.pmc_purchase.schemas import (
    CycleOverrideListData,
    CycleOverrideMutationData,
    CycleOverrideRead,
    CycleOverrideRequest,
    SkuCycleRead,
)
from app.modules.pmc_purchase.service import _sku_cycle

OVERRIDE_ERROR_CODES = {
    "SOURCE_ACCOUNT_SCOPE_DENIED": 403,
    "SKU_CYCLE_NOT_FOUND": 404,
    "PURCHASE_ORDER_NOT_A_SAMPLE": 422,
    "PURCHASE_ORDER_NOT_EXCLUDED": 422,
    "ARRIVAL_DATE_BEFORE_ORDER_DATE": 422,
}


class PmcPurchaseOverrideService:
    def __init__(self, session: Session, *, now: datetime | None = None, today: date | None = None):
        self.session = session
        self.now = now or datetime.now(UTC)
        self.today = today or self.now.date()

    # -- write --

    def apply(
        self,
        *,
        sku: str,
        payload: CycleOverrideRequest,
        accounts: frozenset[str],
        actor_ref: str,
        request_id: str,
    ) -> CycleOverrideMutationData:
        sku = sku.strip()
        if not sku:
            raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
        account = payload.source_account_ref
        if account not in accounts:
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
        effective_request_id = payload.request_id or request_id

        replay = self._find_replay(account, sku, effective_request_id)
        if replay is not None:
            return CycleOverrideMutationData(
                override=_read(replay),
                replaced_override_id=None,
                idempotent_replay=True,
                sku_cycle=self._current_cycle(account, sku),
                refresh_board_rows=0,
            )

        cycle = self.session.scalar(
            select(DwsPurchaseSkuCycle).where(
                DwsPurchaseSkuCycle.source_account_ref == account,
                DwsPurchaseSkuCycle.sku == sku,
            )
        )
        if cycle is None:
            raise ApiError(
                code=ErrorCode.NOT_FOUND, status_code=404, details={"reason": "SKU_CYCLE_NOT_FOUND"}
            )
        sample = self._validate_against_samples(cycle, payload)

        before: dict[str, Any] = {
            "value_days": str(cycle.value_days) if cycle.value_days is not None else None,
            "source": cycle.source,
            "sample_count": cycle.sample_count,
            "baseline_days": cycle.baseline_days,
            "calc_version": cycle.calc_version,
            "rule_version": cycle.rule_version,
        }
        if sample is not None:
            before["sample"] = sample
        after: dict[str, Any] = {"kind": payload.kind}
        if payload.purchase_order_sn:
            after["purchase_order_sn"] = payload.purchase_order_sn
        if payload.value_days is not None:
            after["value_days"] = payload.value_days
        if payload.value_date is not None:
            after["value_date"] = payload.value_date.isoformat()

        replaced_id: UUID | None = None
        if payload.kind == "baseline":
            replaced_id = self._close_active_baseline(account, sku)

        record = ManualPurchaseCycleOverride(
            id=uuid4(),
            source_account_ref=account,
            sku=sku,
            kind=payload.kind,
            purchase_order_sn=payload.purchase_order_sn,
            value_days=payload.value_days,
            value_date=payload.value_date,
            before_json=before,
            after_json=after,
            reason=payload.reason.strip(),
            operator_ref=actor_ref,
            request_id=effective_request_id,
            effective_from=self.now,
            is_active=True,
        )
        self.session.add(record)
        self.session.flush()

        # Rebuild the account's DWS in the same transaction; the refresher commits on
        # success and rolls back (override included) on failure.
        try:
            result = PmcPurchaseDwsRefresher(self.session, now=self.now).refresh(
                source_account_ref=account, today=self.today, skus={sku}
            )
        except PmcPurchaseDwsRefreshError as error:
            raise ApiError(
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
                details={"reason": str(error)},
            ) from error

        return CycleOverrideMutationData(
            override=_read(record),
            replaced_override_id=replaced_id,
            idempotent_replay=False,
            sku_cycle=self._current_cycle(account, sku),
            refresh_board_rows=result.board_rows,
        )

    # -- read --

    def history(self, *, sku: str, accounts: frozenset[str]) -> CycleOverrideListData:
        rows = self.session.scalars(
            select(ManualPurchaseCycleOverride)
            .where(
                ManualPurchaseCycleOverride.source_account_ref.in_(sorted(accounts)),
                ManualPurchaseCycleOverride.sku == sku.strip(),
            )
            .order_by(
                ManualPurchaseCycleOverride.effective_from.desc(),
                ManualPurchaseCycleOverride.created_at.desc(),
            )
        )
        return CycleOverrideListData(sku=sku.strip(), items=[_read(r) for r in rows])

    # -- helpers --

    def _find_replay(
        self, account: str, sku: str, request_id: str
    ) -> ManualPurchaseCycleOverride | None:
        return self.session.scalar(
            select(ManualPurchaseCycleOverride).where(
                ManualPurchaseCycleOverride.source_account_ref == account,
                ManualPurchaseCycleOverride.sku == sku,
                ManualPurchaseCycleOverride.request_id == request_id,
            )
        )

    def _current_cycle(self, account: str, sku: str) -> SkuCycleRead | None:
        row = self.session.scalar(
            select(DwsPurchaseSkuCycle).where(
                DwsPurchaseSkuCycle.source_account_ref == account,
                DwsPurchaseSkuCycle.sku == sku,
            )
        )
        return _sku_cycle(row) if row is not None else None

    def _close_active_baseline(self, account: str, sku: str) -> UUID | None:
        previous = self.session.scalars(
            select(ManualPurchaseCycleOverride).where(
                ManualPurchaseCycleOverride.source_account_ref == account,
                ManualPurchaseCycleOverride.sku == sku,
                ManualPurchaseCycleOverride.kind == "baseline",
                ManualPurchaseCycleOverride.is_active.is_(True),
            )
        ).all()
        replaced: UUID | None = None
        for row in previous:
            row.is_active = False
            # effective_period CHECK requires effective_to > effective_from; two records in
            # the same instant (tests, replays) close the older one one microsecond later.
            started = row.effective_from
            if started.tzinfo is None:  # SQLite hands back naive UTC
                started = started.replace(tzinfo=UTC)
            row.effective_to = max(self.now, started + timedelta(microseconds=1))
            replaced = row.id
        return replaced

    @staticmethod
    def _validate_against_samples(
        cycle: DwsPurchaseSkuCycle, payload: CycleOverrideRequest
    ) -> dict[str, Any] | None:
        if payload.kind == "baseline":
            return None
        samples = {
            str(s.get("purchase_order_sn")): s
            for s in (cycle.samples_json or [])
            if isinstance(s, dict)
        }
        sample = samples.get(payload.purchase_order_sn or "")
        if sample is None:
            raise ApiError(
                code=ErrorCode.VALIDATION_ERROR,
                status_code=422,
                details={
                    "reason": "PURCHASE_ORDER_NOT_A_SAMPLE",
                    "purchase_order_sn": payload.purchase_order_sn,
                },
            )
        if payload.kind == "restore" and sample.get("exclusion") != "manual":
            raise ApiError(
                code=ErrorCode.VALIDATION_ERROR,
                status_code=422,
                details={
                    "reason": "PURCHASE_ORDER_NOT_EXCLUDED",
                    "purchase_order_sn": payload.purchase_order_sn,
                },
            )
        if payload.kind == "arrival_date" and payload.value_date is not None:
            ordered = sample.get("order_date")
            if isinstance(ordered, str) and payload.value_date < date.fromisoformat(ordered):
                raise ApiError(
                    code=ErrorCode.VALIDATION_ERROR,
                    status_code=422,
                    details={"reason": "ARRIVAL_DATE_BEFORE_ORDER_DATE", "order_date": ordered},
                )
        return dict(sample)


def _read(row: ManualPurchaseCycleOverride) -> CycleOverrideRead:
    return CycleOverrideRead(
        id=row.id,
        source_account_ref=row.source_account_ref,
        sku=row.sku,
        kind=row.kind,  # type: ignore[arg-type]
        purchase_order_sn=row.purchase_order_sn,
        value_days=row.value_days,
        value_date=row.value_date,
        before=dict(row.before_json or {}),
        after=dict(row.after_json or {}),
        reason=row.reason,
        operator_ref=row.operator_ref,
        request_id=row.request_id,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        is_active=row.is_active,
        created_at=row.created_at,
    )

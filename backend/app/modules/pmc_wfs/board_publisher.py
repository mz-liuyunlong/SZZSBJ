"""Build and publish a WFS shipment-board version from selected succeeded ODS runs.

Pure projection: reads ``ods_lingxing_wfs_*`` rows of the chosen runs, joins shipping lists
to cargos, and writes one ``mart_wfs_shipment_board`` row per cargo under a new
``gov_wfs_board_publications`` version that becomes current atomically.  Never calls
Lingxing; a rebuild from the same runs is deterministic.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.modules.integration_sync.models import ApiRawRequestRef, IntegrationSyncRun
from app.modules.pmc_wfs.lingxing_models import (
    WFS_CARGO_STATUS,
    LingxingWfsCargoGoodsOds,
    LingxingWfsCargoOds,
    LingxingWfsShippingListOds,
    WfsBoardPublication,
    WfsShipmentBoardRow,
)

BUILDER_VERSION: Final = "wfs_board.v1"
PROVIDER_TZ: Final = ZoneInfo("Asia/Shanghai")


class WfsBoardPublishError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class WfsBoardPublishResult:
    publication_id: UUID
    rows: int
    cargos_without_shipping: int
    coverage_start: date
    coverage_end: date
    source_observed_at: datetime


def provider_datetime(value: str | None) -> datetime | None:
    """``YYYY-MM-DD HH:MM:SS`` (or date-only) in the provider's Asia/Shanghai wall clock."""

    if not value:
        return None
    text_value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text_value, fmt)
        except ValueError:
            continue
        if parsed.year <= 1970:
            return None
        return parsed.replace(tzinfo=PROVIDER_TZ).astimezone(UTC)
    return None


def provider_date(value: str | None) -> date | None:
    parsed = provider_datetime(value)
    return parsed.astimezone(PROVIDER_TZ).date() if parsed else None


def _sum(values: list[int | None]) -> int | None:
    known = [v for v in values if v is not None]
    return sum(known) if known else None


def build_board_rows(
    cargos: list[LingxingWfsCargoOds],
    goods: list[LingxingWfsCargoGoodsOds],
    shipping_lists: list[LingxingWfsShippingListOds],
) -> list[dict[str, Any]]:
    """Project ODS rows to board rows (one per cargo). Pure function for tests."""

    goods_by_cargo: dict[str, list[LingxingWfsCargoGoodsOds]] = defaultdict(list)
    for good in goods:
        goods_by_cargo[good.cargo_id].append(good)
    shipping_by_code: dict[str, LingxingWfsShippingListOds] = {}
    shipping_by_cargo_code: dict[str, list[LingxingWfsShippingListOds]] = defaultdict(list)
    for shipping in shipping_lists:
        shipping_by_code[shipping.shipping_code] = shipping
        for code in shipping.cargo_codes or []:
            shipping_by_cargo_code[code].append(shipping)

    rows: list[dict[str, Any]] = []
    for cargo in cargos:
        lines = sorted(goods_by_cargo.get(cargo.cargo_id, []), key=lambda g: g.line_ordinal)
        linked: dict[str, LingxingWfsShippingListOds] = {}
        for code in cargo.shipping_list_codes or []:
            if code in shipping_by_code:
                linked[code] = shipping_by_code[code]
        if cargo.cargo_code:
            for shipping in shipping_by_cargo_code.get(cargo.cargo_code, []):
                linked.setdefault(shipping.shipping_code, shipping)
        shipping_rows = sorted(linked.values(), key=lambda s: (s.gmt_create or "", s.shipping_code))
        primary = shipping_rows[0] if shipping_rows else None
        status = cargo.status
        status_name = cargo.status_name or cargo.cargo_status
        if status_name is None and status is not None:
            status_name = WFS_CARGO_STATUS.get(status)
        row: dict[str, Any] = {
            "cargo_id": cargo.cargo_id,
            "cargo_code": cargo.cargo_code,
            "in_bound_order_id": cargo.in_bound_order_id,
            "store_id": cargo.store_id,
            "store_name": cargo.store_name,
            "status": status,
            "status_name": status_name,
            "cargo_sync_status": cargo.cargo_sync_status,
            "logistics_code": cargo.logistics_code or (primary.logistics_code if primary else None),
            "cargo_created_at": provider_datetime(cargo.cargo_create_date),
            "cargo_updated_at": provider_datetime(cargo.update_date),
            "to_await_at": cargo.to_await_at,
            "to_receive_at": cargo.to_receive_at,
            "to_closed_at": cargo.to_closed_at,
            "to_cancelled_at": cargo.to_cancelled_at,
            "declared_units": _sum([g.declare_num for g in lines]),
            "shipped_units": _sum([g.shipments_num for g in lines]),
            "received_units": _sum([g.received_num for g in lines]),
            "damaged_units": _sum([g.damaged_qty for g in lines]),
            "sku_count": len({g.msku or g.sku or str(g.line_ordinal) for g in lines}),
            "shipping_codes": [s.shipping_code for s in shipping_rows],
            "shipping_status": primary.shipping_status if primary else None,
            "warehouse_id": primary.warehouse_id if primary else None,
            "actual_delivery_date": (
                provider_date(primary.actual_delivery_time) if primary else None
            ),
            "arrival_date": provider_date(primary.arrival_time) if primary else None,
            "expected_arrival_date": (
                provider_date(primary.expected_arrival_time) if primary else None
            ),
            "logistics_numbers": sorted(
                {n for s in shipping_rows for n in (s.logistics_numbers or [])}
            ),
            "payload_json": {
                "cargo": {
                    "id": cargo.cargo_id,
                    "cargo_code": cargo.cargo_code,
                    "in_bound_order_id": cargo.in_bound_order_id,
                    "country_name": cargo.country_name,
                    "creator": cargo.creator,
                    "cargo_create_date": cargo.cargo_create_date,
                    "update_date": cargo.update_date,
                    "system_update_date": cargo.system_update_date,
                    "cargo_status": cargo.cargo_status,
                    "status_name": status_name,
                    "cargo_sync_status": cargo.cargo_sync_status,
                    "distribution_addresses": cargo.distribution_addresses,
                    "return_addresses": cargo.return_addresses,
                    "to_pending_at": _iso(cargo.to_pending_at),
                    "to_await_at": _iso(cargo.to_await_at),
                    "to_receive_at": _iso(cargo.to_receive_at),
                    "to_closed_at": _iso(cargo.to_closed_at),
                    "to_cancelled_at": _iso(cargo.to_cancelled_at),
                },
                "goods": [
                    {
                        "msku": g.msku,
                        "sku": g.sku,
                        "product_name": g.product_name,
                        "gtin": g.gtin,
                        "declare_num": g.declare_num,
                        "shipments_num": g.shipments_num,
                        "received_num": g.received_num,
                        "damaged_qty": g.damaged_qty,
                    }
                    for g in lines
                ],
                "shipping_lists": [
                    {
                        "shipping_code": s.shipping_code,
                        "shipping_status": s.shipping_status,
                        "warehouse_id": s.warehouse_id,
                        "logistics_provider_id": s.logistics_provider_id,
                        "logistics_channel_id": s.logistics_channel_id,
                        "logistics_code": s.logistics_code,
                        "creator": s.creator,
                        "principal_user_name": s.principal_user_name,
                        "gmt_create": s.gmt_create,
                        "delivery_time": s.delivery_time,
                        "actual_delivery_time": s.actual_delivery_time,
                        "sail_time": s.sail_time,
                        "arrival_time": s.arrival_time,
                        "expected_arrival_time": s.expected_arrival_time,
                        "actual_due_time": s.actual_due_time,
                        "order_logistics_status": s.order_logistics_status,
                        "head_fee_type": s.head_fee_type,
                        "logistics_numbers": s.logistics_numbers,
                        "tracking_numbers": s.tracking_numbers,
                        "box_num_total": s.box_num_total,
                        "shipments_num_total": s.shipments_num_total,
                    }
                    for s in shipping_rows
                ],
            },
        }
        rows.append(row)
    return rows


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


class WfsBoardPublisher:
    def __init__(self, session: Session) -> None:
        self.session = session

    def publish(
        self,
        *,
        account: str,
        cargo_run_id: UUID,
        shipping_run_id: UUID | None,
    ) -> WfsBoardPublishResult:
        try:
            if not account.strip():
                raise WfsBoardPublishError("WFS_BOARD_PUBLICATION_SCOPE_INVALID")
            wanted = {cargo_run_id} | ({shipping_run_id} if shipping_run_id else set())
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
                raise WfsBoardPublishError("WFS_BOARD_SUCCESSFUL_RUNS_REQUIRED")
            by_id = {r.id: r for r in runs}
            if by_id[cargo_run_id].interface_key != "wfsCargoPage" or (
                shipping_run_id is not None
                and by_id[shipping_run_id].interface_key != "wfsShippingListPage"
            ):
                raise WfsBoardPublishError("WFS_BOARD_RUN_INTERFACE_MISMATCH")
            refs = list(
                self.session.scalars(
                    select(ApiRawRequestRef).where(
                        ApiRawRequestRef.run_id.in_(wanted),
                        ApiRawRequestRef.is_success.is_(True),
                    )
                )
            )
            if {r.run_id for r in refs} != wanted:
                raise WfsBoardPublishError("WFS_BOARD_SOURCE_EVIDENCE_MISSING")
            cargo_run = by_id[cargo_run_id]
            if cargo_run.window_start is None or cargo_run.window_end is None:
                raise WfsBoardPublishError("WFS_BOARD_SOURCE_WINDOW_INVALID")
            cargos = list(
                self.session.scalars(
                    select(LingxingWfsCargoOds)
                    .where(
                        LingxingWfsCargoOds.run_id == cargo_run_id,
                        LingxingWfsCargoOds.source_account_ref == account,
                    )
                    .order_by(LingxingWfsCargoOds.source_item_ordinal)
                )
            )
            goods = list(
                self.session.scalars(
                    select(LingxingWfsCargoGoodsOds).where(
                        LingxingWfsCargoGoodsOds.run_id == cargo_run_id,
                        LingxingWfsCargoGoodsOds.source_account_ref == account,
                    )
                )
            )
            shipping_lists: list[LingxingWfsShippingListOds] = []
            if shipping_run_id is not None:
                shipping_lists = list(
                    self.session.scalars(
                        select(LingxingWfsShippingListOds).where(
                            LingxingWfsShippingListOds.run_id == shipping_run_id,
                            LingxingWfsShippingListOds.source_account_ref == account,
                        )
                    )
                )
            rows = build_board_rows(cargos, goods, shipping_lists)
            observed = min(r.received_at for r in refs)
            start = cargo_run.window_start.date()
            end = cargo_run.window_end.date()
            without_shipping = sum(1 for r in rows if not r["shipping_codes"])
            identity = self._save(
                account,
                rows,
                cargo_run_id,
                shipping_run_id,
                start,
                end,
                observed,
                {
                    "rows": len(rows),
                    "goods_rows": len(goods),
                    "shipping_lists": len(shipping_lists),
                    "cargos_without_shipping": without_shipping,
                    "complete": True,
                },
            )
            self.session.commit()
            return WfsBoardPublishResult(
                publication_id=identity,
                rows=len(rows),
                cargos_without_shipping=without_shipping,
                coverage_start=start,
                coverage_end=end,
                source_observed_at=observed,
            )
        except Exception:
            self.session.rollback()
            raise

    def _save(
        self,
        account: str,
        rows: list[dict[str, Any]],
        cargo_run_id: UUID,
        shipping_run_id: UUID | None,
        start: date,
        end: date,
        observed: datetime,
        quality: dict[str, Any],
    ) -> UUID:
        if self.session.get_bind().dialect.name == "postgresql":
            key = int.from_bytes(
                hashlib.sha256(f"wfs_board\0{account}".encode()).digest()[:8], signed=True
            )
            self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
        identity = uuid4()
        self.session.add(
            WfsBoardPublication(
                id=identity,
                source_account_ref=account,
                status="published",
                is_current=False,
                cargo_run_id=cargo_run_id,
                shipping_run_id=shipping_run_id,
                coverage_start=start,
                coverage_end=end,
                source_observed_at=observed,
                published_at=datetime.now(UTC),
                builder_version=BUILDER_VERSION,
                quality_report=quality,
            )
        )
        self.session.flush()
        for row in rows:
            self.session.add(
                WfsShipmentBoardRow(
                    publication_id=identity,
                    id=uuid4(),
                    source_account_ref=account,
                    **row,
                )
            )
        self.session.flush()
        self.session.execute(
            update(WfsBoardPublication)
            .where(
                WfsBoardPublication.source_account_ref == account,
                WfsBoardPublication.is_current.is_(True),
            )
            .values(is_current=False)
        )
        self.session.flush()
        self.session.execute(
            update(WfsBoardPublication)
            .where(WfsBoardPublication.id == identity)
            .values(is_current=True)
        )
        return identity

"""物流看板 (8088 ``pmc-logistics``) over stored records: read-only, no provider calls.

Inputs are the current WFS board publication (its Lingxing cargo and shipping-list runs; the
rule date is the publication's data day, as 8088 ``TODAY = 数据日``) plus the current
file-sourced ODS rows (logistics channels, 众壹 orders / tracks, Walmart inbound shipments and
Receipt log). Every SP is built and enriched exactly as ``build_from_daily.py`` + ``app-a.jsx``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.pmc_logistics.build import (
    LogisticsInputs,
    build_sps,
    carrier_tracks,
    walmart_facts,
)
from app.modules.pmc_logistics.rules import LogisticsRules, default_rules, enrich_sp
from app.modules.pmc_logistics.schemas import (
    LogisticsBoard,
    LogisticsDetail,
    LogisticsRuleSummary,
    Option,
)
from app.modules.pmc_wfs.board_facts import source_tables_ready
from app.modules.pmc_wfs.lingxing_models import (
    LingxingWfsCargoOds,
    LingxingWfsShippingListOds,
    WfsBoardPublication,
)
from app.modules.pmc_wfs.shipment_board_service import (
    _publication_data_day,
    business_today,
    require_board_schema,
)
from app.modules.pmc_wfs.source_models import (
    SOURCE_LINGXING,
    SOURCE_WALMART,
    SOURCE_ZHONGYI,
    CarrierZhongyiOrderOds,
    CarrierZhongyiTrackOds,
    LingxingLogisticsChannelOds,
    PmcWfsSourceFile,
    WalmartWfsInboundShipmentOds,
    WalmartWfsReceiptOds,
)

STAGE_ORDER = (
    "待发货",
    "已发货",
    "已开船",
    "已到港",
    "派送中",
    "物流签收",
    "Walmart 收货中",
    "Walmart 完成",
    "已作废",
)


@dataclass(slots=True)
class LogisticsSnapshot:
    today: date
    publication_ids: list[UUID]
    inputs: LogisticsInputs
    rules: LogisticsRules
    wm_stores: set[str]
    wm_day: str
    wm: dict[str, dict[str, Any]] = field(default_factory=dict)
    rows: list[dict[str, Any]] = field(default_factory=list)
    sources: dict[str, Any] = field(default_factory=dict)


def _current_files(session: Session, source: str, endpoint: str) -> list[PmcWfsSourceFile]:
    return list(
        session.scalars(
            select(PmcWfsSourceFile).where(
                PmcWfsSourceFile.source == source,
                PmcWfsSourceFile.endpoint == endpoint,
                PmcWfsSourceFile.is_current.is_(True),
            )
        )
    )


def _payloads(session: Session, model: Any, files: Iterable[PmcWfsSourceFile]) -> list[dict]:
    ids = [f.id for f in files]
    if not ids:
        return []
    stmt = select(model).where(model.file_id.in_(ids))
    if hasattr(model, "line_ordinal"):
        stmt = stmt.order_by(model.file_id, model.line_ordinal)
    return [dict(row.payload_json or {}) for row in session.scalars(stmt)]


_SOURCE_FILES: dict[str, tuple[str, str]] = {
    "channels": (SOURCE_LINGXING, "logistics_channels"),
    "orders": (SOURCE_ZHONGYI, "orders_summary"),
    "tracks": (SOURCE_ZHONGYI, "orders_track"),
    "shipments": (SOURCE_WALMART, "inbound_shipments"),
    "receipts": (SOURCE_WALMART, "inventory_log"),
}
_CACHE: dict[tuple[tuple[str, ...], tuple[str, ...]], LogisticsSnapshot] = {}


class LogisticsService:
    """Read-only 物流看板 over the current inputs (the 8088 page computes this in-browser)."""

    def __init__(self, session: Session, accounts: list[str], stores: set[str] | None = None):
        self.session = session
        self.accounts = accounts
        self.stores = stores
        self._snapshot: LogisticsSnapshot | None = None

    def _publications(self) -> list[WfsBoardPublication]:
        require_board_schema(self.session)
        return list(
            self.session.scalars(
                select(WfsBoardPublication).where(
                    WfsBoardPublication.source_account_ref.in_(self.accounts),
                    WfsBoardPublication.is_current.is_(True),
                )
            )
        )

    def snapshot(self) -> LogisticsSnapshot:
        """All SPs of the current inputs. Cached per process by the ids of the current
        publication and source files, so a new publication or file load rebuilds it."""

        if self._snapshot is not None:
            return self._snapshot
        pubs = self._publications()
        ready = source_tables_ready(self.session)
        files = {
            key: (_current_files(self.session, source, endpoint) if ready else [])
            for key, (source, endpoint) in _SOURCE_FILES.items()
        }
        cache_key = (
            tuple(sorted(str(p.id) for p in pubs)),
            tuple(sorted(str(f.id) for fs in files.values() for f in fs)),
        )
        cached = _CACHE.get(cache_key)
        if cached is None:
            cached = self._build(pubs, files)
            _CACHE.clear()  # one data day at a time; old entries are never read again
            _CACHE[cache_key] = cached
        self._snapshot = cached
        return cached

    def visible_rows(self) -> list[dict[str, Any]]:
        rows = self.snapshot().rows
        if self.stores is None:
            return rows
        return [
            r
            for r in rows
            if (
                {r["sp"].get("store_id")} | {c.get("store_id") for c in r["sp"].get("cargos") or []}
            )
            & self.stores
        ]

    def _build(
        self, pubs: list[WfsBoardPublication], files: dict[str, list[PmcWfsSourceFile]]
    ) -> LogisticsSnapshot:
        days = [d for p in pubs if (d := _publication_data_day(p))]
        today = max(days) if days else business_today()
        today_s = today.isoformat()
        cargo_runs = [p.cargo_run_id for p in pubs]
        shipping_runs = [p.shipping_run_id for p in pubs if p.shipping_run_id]
        cargos = (
            [
                dict(r.payload_json or {})
                for r in self.session.scalars(
                    select(LingxingWfsCargoOds).where(LingxingWfsCargoOds.run_id.in_(cargo_runs))
                )
            ]
            if cargo_runs
            else []
        )
        lists = (
            [
                dict(r.payload_json or {})
                for r in self.session.scalars(
                    select(LingxingWfsShippingListOds).where(
                        LingxingWfsShippingListOds.run_id.in_(shipping_runs)
                    )
                )
            ]
            if shipping_runs
            else []
        )
        channels = _payloads(self.session, LingxingLogisticsChannelOds, files["channels"])
        inputs = build_sps(lists, cargos, channels)
        inputs.tracks = carrier_tracks(
            inputs.sps,
            _payloads(self.session, CarrierZhongyiOrderOds, files["orders"]),
            _payloads(self.session, CarrierZhongyiTrackOds, files["tracks"]),
        )

        ship_files, log_files = files["shipments"], files["receipts"]
        store_of = {f.id: f.scope_key for f in [*ship_files, *log_files]}
        shipments = (
            [
                {**dict(r.payload_json or {}), "store_id": store_of.get(r.file_id, r.store_id)}
                for r in self.session.scalars(
                    select(WalmartWfsInboundShipmentOds).where(
                        WalmartWfsInboundShipmentOds.file_id.in_([f.id for f in ship_files])
                    )
                )
            ]
            if ship_files
            else []
        )
        receipts = (
            [
                {**dict(r.payload_json or {}), "store_id": store_of.get(r.file_id, r.store_id)}
                for r in self.session.scalars(
                    select(WalmartWfsReceiptOds)
                    .where(WalmartWfsReceiptOds.file_id.in_([f.id for f in log_files]))
                    .order_by(WalmartWfsReceiptOds.file_id, WalmartWfsReceiptOds.line_ordinal)
                )
            ]
            if log_files
            else []
        )
        wm, _ = walmart_facts(shipments, receipts, today_s)
        wm_stores = {f.scope_key for f in ship_files}
        wm_day = max((f.batch_label for f in ship_files), default="")

        rules = default_rules(inputs.sps)
        rows: list[dict[str, Any]] = []
        for sp in inputs.sps:
            track = inputs.tracks.get(sp["code"])
            view = enrich_sp(sp, track, wm, wm_stores, rules, today, wm_day=wm_day)
            rows.append({"sp": sp, "track": track, "view": view})
        return LogisticsSnapshot(
            today=today,
            publication_ids=[p.id for p in pubs],
            inputs=inputs,
            rules=rules,
            wm_stores=wm_stores,
            wm_day=wm_day,
            wm=wm,
            rows=rows,
            sources={
                "publications": len(pubs),
                "shipping_lists": len(lists),
                "cargos": len(cargos),
                "channels": len(channels),
                "carrier_tracks": len(inputs.tracks),
                "walmart_stores": sorted(wm_stores),
                "walmart_batch": wm_day,
                "excluded_test_sps": inputs.excluded_test_sps,
            },
        )
        pubs = self._publications()
        days = [d for p in pubs if (d := _publication_data_day(p))]
        today = max(days) if days else business_today()
        today_s = today.isoformat()
        cargo_runs = [p.cargo_run_id for p in pubs]
        shipping_runs = [p.shipping_run_id for p in pubs if p.shipping_run_id]
        cargos = (
            [
                dict(r.payload_json or {})
                for r in self.session.scalars(
                    select(LingxingWfsCargoOds).where(LingxingWfsCargoOds.run_id.in_(cargo_runs))
                )
            ]
            if cargo_runs
            else []
        )
        lists = (
            [
                dict(r.payload_json or {})
                for r in self.session.scalars(
                    select(LingxingWfsShippingListOds).where(
                        LingxingWfsShippingListOds.run_id.in_(shipping_runs)
                    )
                )
            ]
            if shipping_runs
            else []
        )
        ready = source_tables_ready(self.session)
        channel_files = (
            _current_files(self.session, SOURCE_LINGXING, "logistics_channels") if ready else []
        )
        channels = _payloads(self.session, LingxingLogisticsChannelOds, channel_files)
        inputs = build_sps(lists, cargos, channels)

        order_files = (
            _current_files(self.session, SOURCE_ZHONGYI, "orders_summary") if ready else []
        )
        track_files = _current_files(self.session, SOURCE_ZHONGYI, "orders_track") if ready else []
        inputs.tracks = carrier_tracks(
            inputs.sps,
            _payloads(self.session, CarrierZhongyiOrderOds, order_files),
            _payloads(self.session, CarrierZhongyiTrackOds, track_files),
        )

        ship_files = (
            _current_files(self.session, SOURCE_WALMART, "inbound_shipments") if ready else []
        )
        log_files = _current_files(self.session, SOURCE_WALMART, "inventory_log") if ready else []
        store_of = {f.id: f.scope_key for f in [*ship_files, *log_files]}
        shipments = (
            [
                {**dict(r.payload_json or {}), "store_id": store_of.get(r.file_id, r.store_id)}
                for r in self.session.scalars(
                    select(WalmartWfsInboundShipmentOds).where(
                        WalmartWfsInboundShipmentOds.file_id.in_([f.id for f in ship_files])
                    )
                )
            ]
            if ship_files
            else []
        )
        receipts = (
            [
                {**dict(r.payload_json or {}), "store_id": store_of.get(r.file_id, r.store_id)}
                for r in self.session.scalars(
                    select(WalmartWfsReceiptOds)
                    .where(WalmartWfsReceiptOds.file_id.in_([f.id for f in log_files]))
                    .order_by(WalmartWfsReceiptOds.file_id, WalmartWfsReceiptOds.line_ordinal)
                )
                if (r.payload_json or {}).get("transactionType", "Receipt") == "Receipt"
            ]
            if log_files
            else []
        )
        wm, _ = walmart_facts(shipments, receipts, today_s)
        wm_stores = {f.scope_key for f in ship_files}
        wm_day = max((f.batch_label for f in ship_files), default="")

        rules = default_rules(inputs.sps)
        rows: list[dict[str, Any]] = []
        for sp in inputs.sps:
            if (
                self.stores is not None
                and not ({sp.get("store_id")} | {c.get("store_id") for c in sp.get("cargos") or []})
                & self.stores
            ):
                continue
            track = inputs.tracks.get(sp["code"])
            view = enrich_sp(sp, track, wm, wm_stores, rules, today, wm_day=wm_day)
            rows.append({"sp": sp, "track": track, "view": view})
        self._snapshot = LogisticsSnapshot(
            today=today,
            publication_ids=[p.id for p in pubs],
            inputs=inputs,
            rules=rules,
            wm_stores=wm_stores,
            wm_day=wm_day,
            wm=wm,
            rows=rows,
            sources={
                "publications": len(pubs),
                "shipping_lists": len(lists),
                "cargos": len(cargos),
                "channels": len(channels),
                "carrier_tracks": len(inputs.tracks),
                "walmart_stores": sorted(wm_stores),
                "walmart_batch": wm_day,
                "excluded_test_sps": inputs.excluded_test_sps,
            },
        )
        return self._snapshot

    def stage_counts(self) -> dict[str, int]:
        counts = Counter(r["view"]["stage"] for r in self.visible_rows())
        return {s: counts.get(s, 0) for s in STAGE_ORDER}

    # ---- API views -----------------------------------------------------------------

    @staticmethod
    def _row(item: dict[str, Any]) -> dict[str, Any]:
        track = item["track"] or {}
        slim = (
            {
                k: track.get(k)
                for k in (
                    "number",
                    "customerNumber",
                    "status",
                    "trackCn",
                    "lastTrack",
                    "totalWeightKg",
                )
            }
            if track
            else None
        )
        return {**item["sp"], **item["view"], "tr": slim}

    def board(self) -> LogisticsBoard:
        snap = self.snapshot()
        rows = [self._row(item) for item in self.visible_rows()]
        stores = sorted(
            {(g["store_id"], g["store"]) for r in rows for g in r["goods"] if g["store_id"]},
            key=lambda x: x[1],
        )
        providers = {
            r["provider_id"]: r["provider"] or r["provider_id"] for r in rows if r["provider_id"]
        }
        rules = snap.rules
        return LogisticsBoard(
            today=snap.today,
            rows=rows,
            stages=list(STAGE_ORDER),
            stage_counts=self.stage_counts(),
            providers=[
                Option(value=k, label=v) for k, v in sorted(providers.items(), key=lambda x: x[1])
            ],
            channels=[
                {
                    "value": c["channel_id"],
                    "label": c["channel_name"],
                    "provider_id": c["provider_id"],
                }
                for c in snap.inputs.channels
                if any(r["channel_id"] == c["channel_id"] for r in rows)
            ],
            stores=[Option(value=k, label=v) for k, v in stores],
            regions=["美西", "美中", "美东", "待定"],
            rules=LogisticsRuleSummary(
                remind_before=rules.remind_before,
                delivered_not_signed=rules.delivered_not_signed,
                penalty_per_kg_day=rules.penalty_per_kg_day,
                wm_receive_buffer=rules.wm_receive_buffer,
                receive_diff_buffer=rules.receive_diff_buffer,
                region_total=dict(rules.region_total),
            ),
            sources=snap.sources,
        )

    def detail(self, code: str) -> LogisticsDetail | None:
        snap = self.snapshot()
        item = next((r for r in self.visible_rows() if r["sp"]["code"] == code), None)
        if item is None:
            return None
        cargo_codes = [c["code"] for c in item["sp"].get("cargos") or []]
        return LogisticsDetail(
            today=snap.today,
            row=self._row(item),
            track=item["track"],
            walmart=[dict(snap.wm[c], code=c) for c in cargo_codes if c in snap.wm],
        )

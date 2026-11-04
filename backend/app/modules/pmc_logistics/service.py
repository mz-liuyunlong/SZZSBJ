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
from app.modules.pmc_logistics.carriers import (
    STALE_DAYS,
    carrier_orders,
    missing_orders,
    provider_counts,
    sort_orders,
    status_counts,
    zy_provider_ids,
)
from app.modules.pmc_logistics.forecast import forecast_rows, forecast_summary
from app.modules.pmc_logistics.rules import (
    LogisticsRules,
    channel_regions,
    default_rules,
    enrich_sp,
)
from app.modules.pmc_logistics.schemas import (
    RULE_SORTS,
    AlertQuery,
    CarrierOrderDetail,
    CarrierQuery,
    ForecastQuery,
    LogisticsDetail,
    LogisticsList,
    LogisticsOptions,
    LogisticsRuleSummary,
    LogisticsRulesView,
    Option,
    OverviewQuery,
    RuleListQuery,
    SpFilters,
)
from app.modules.pmc_wfs.board_facts import source_tables_ready
from app.modules.pmc_wfs.board_lookups import item_ids_by_store_msku, owners_by_sku
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
    WalmartWfsInboundItemOds,
    WalmartWfsInboundShipmentOds,
    WalmartWfsReceiptOds,
)

EDIT_HINT = "一期只读：数值为 8088 已确认的默认规则；改规则走 PMC 设置（待 Rocky 确认）。"
SEV_RANK = {"high": 0, "mid": 1, "low": 2}
# 8088 TabAlerts EX_TYPES (filter order).
ALERT_TYPES = (
    "已超合同时效",
    "签收已超时效（可索赔）",
    "即将超时",
    "渠道与目的地区不符",
    "物流已签收 WFS 未收货",
    "物流已签收 Walmart 未签收",
    "Walmart 签收滞后于物流到货",
    "Walmart 已收货 物流未显示派送",
    "一单多运单号（待核实）",
    "收货差异（超缓冲期）",
    "收货差异（观察期）",
    "实际费用未录入",
    "预计开船缺失",
    "预计到港缺失",
    "运单号缺失",
    "未关联 WFS 货件",
    "无合同时效",
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
    carrier_orders: list[dict[str, Any]] = field(default_factory=list)


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
    "items": (SOURCE_WALMART, "inbound_shipment_items"),
}
_CACHE: dict[tuple[tuple[str, ...], tuple[str, ...]], LogisticsSnapshot] = {}


def _add_item_facts(
    wm: dict[str, dict[str, Any]],
    receipts: Iterable[dict[str, Any]],
    items: Iterable[dict[str, Any]],
    shipment_ids: set[str],
) -> None:
    """8088 ``wm[...].byGtin`` (Receipt units per GTIN) and ``itemsRecv`` (inbound-item
    ``receivedQty`` per GTIN, only for shipments in the inbound-shipment file)."""

    for w in wm.values():
        w.setdefault("byGtin", {})
        w.setdefault("itemsRecv", {})
    for r in receipts:
        w = wm.get(str(r.get("shipmentId") or ""))
        if w is not None:
            g = str(r.get("gtin") or "")
            w["byGtin"][g] = w["byGtin"].get(g, 0) + _int(r.get("changedUnits"))
    for r in items:
        sh, g = str(r.get("shipmentId") or ""), str(r.get("gtin") or "")
        if sh in shipment_ids and g and sh in wm:
            recv = wm[sh]["itemsRecv"]
            recv[g] = recv.get(g, 0) + _int(r.get("receivedQty"))


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


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
        zy_orders = _payloads(self.session, CarrierZhongyiOrderOds, files["orders"])
        zy_tracks = _payloads(self.session, CarrierZhongyiTrackOds, files["tracks"])
        inputs.tracks = carrier_tracks(inputs.sps, zy_orders, zy_tracks)

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
        _add_item_facts(
            wm,
            receipts,
            self._items(files["items"]),
            {str(r.get("shipmentId") or "") for r in shipments},
        )
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
            carrier_orders=carrier_orders(
                inputs.sps, zy_orders, zy_tracks, inputs.stores, today, inputs.providers
            ),
            sources={
                "publications": len(pubs),
                "shipping_lists": len(lists),
                "cargos": len(cargos),
                "channels": len(channels),
                "carrier_tracks": len(inputs.tracks),
                "carrier_orders": len({str(o.get("number") or "") for o in zy_orders} - {""}),
                "walmart_stores": sorted(wm_stores),
                "walmart_batch": wm_day,
                "excluded_test_sps": inputs.excluded_test_sps,
            },
        )

    def _items(self, files: list[PmcWfsSourceFile]) -> list[dict[str, Any]]:
        return _payloads(self.session, WalmartWfsInboundItemOds, files)

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

    @staticmethod
    def _list_row(row: dict[str, Any]) -> dict[str, Any]:
        """Table row without goods / cargo lines (the drawer loads those per SP)."""

        out = {k: v for k, v in row.items() if k not in ("goods", "cargos", "tr")}
        out["cargo_count"] = len(row.get("cargos") or [])
        return out

    def _rows(self) -> list[dict[str, Any]]:
        return [self._row(item) for item in self.visible_rows()]

    @staticmethod
    def _sp_filter(rows: list[dict[str, Any]], q: SpFilters) -> list[dict[str, Any]]:
        kw = q.keyword.strip().lower()

        def text(s: dict[str, Any]) -> str:
            if q.field == "cargo":
                return " ".join(c["code"] for c in s["cargos"])
            if q.field == "track":
                return " ".join(s["tracking"])
            if q.field == "sku":
                return " ".join(f"{g['sku']} {g['msku']} {g['gtin']}" for g in s["goods"])
            return s["code"]

        return [
            s
            for s in rows
            if (not q.store or any(g["store_id"] == q.store for g in s["goods"]))
            and (not q.provider or s["provider_id"] == q.provider)
            and (not q.channel or s["channel_id"] == q.channel)
            and (not q.region or s["region"] == q.region)
            and (not kw or kw in text(s).lower())
        ]

    @staticmethod
    def _page(items: list[dict[str, Any]], q: Any, summary: dict[str, Any]) -> LogisticsList:
        start = (q.page - 1) * q.page_size
        return LogisticsList(
            items=items[start : start + q.page_size],
            total=len(items),
            page=q.page,
            page_size=q.page_size,
            summary=summary,
        )

    def options(self) -> LogisticsOptions:
        snap = self.snapshot()
        rows = self._rows()
        stores = sorted(
            {(g["store_id"], g["store"]) for r in rows for g in r["goods"] if g["store_id"]},
            key=lambda x: x[1],
        )
        providers = {
            r["provider_id"]: r["provider"] or r["provider_id"] for r in rows if r["provider_id"]
        }
        orders = self._carrier_orders()
        owners = sorted({o for r in self._forecast_rows(rows) for o in r["owner"].split("、") if o})
        rules = snap.rules
        return LogisticsOptions(
            today=snap.today,
            total=len(rows),
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
            owners=owners,
            carrier_statuses=[
                Option(value=k, label=f"{k}（{v}）") for k, v in status_counts(orders).items()
            ],
            alert_types=list(ALERT_TYPES),
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

    # 物流总览 ------------------------------------------------------------------------

    def overview(self, q: OverviewQuery) -> LogisticsList:
        snap = self.snapshot()
        rows = self._rows()
        month = snap.today.isoformat()[:8] + "01"
        cards = {
            "all": lambda s: True,
            "transit": lambda s: not s["done"] and s["status"] == "已发货",
            "soon": lambda s: bool(s["soon"]),
            "over": lambda s: bool(s["overdue"]),
            "signed": lambda s: s["stage"] == "物流签收",
            "miss": lambda s: bool(s["missing"]),
            "month": lambda s: s["t"]["delivery"] >= month,
        }
        base = [s for s in self._sp_filter(rows, q) if not q.stage or s["stage"] == q.stage]
        hits = [s for s in base if cards[q.card](s)]
        summary = {
            "cards": {k: sum(1 for s in rows if f(s)) for k, f in cards.items()},
            "shipped": sum(1 for s in rows if s["status"] == "已发货"),
            "penalty_total": round(sum(s.get("penalty") or 0 for s in rows), 2),
            "month_start": month,
            "all": len(rows),
            "qty": sum(s["qty"] for s in hits),
            "boxes": sum(s["boxes"] for s in hits),
        }
        return self._page([self._list_row(s) for s in hits], q, summary)

    # 异常与提醒 ----------------------------------------------------------------------

    def alerts(self, q: AlertQuery) -> LogisticsList:
        rows = self._rows()

        def flat(sps: list[dict[str, Any]]) -> list[dict[str, Any]]:
            out = [
                {
                    "id": f"{s['code']}#{e['type']}#{i}",
                    **{k: e.get(k) for k in ("type", "sev", "desc", "since")},
                    **{
                        k: s.get(k)
                        for k in (
                            "code",
                            "stage",
                            "provider",
                            "provider_id",
                            "channel",
                            "fc",
                            "region",
                            "stores",
                        )
                    },
                }
                for s in sps
                for i, e in enumerate(s["ex"])
            ]
            out.sort(key=lambda e: e["since"] or "", reverse=True)
            out.sort(key=lambda e: SEV_RANK.get(e["sev"], 9))
            return out

        every = flat(rows)
        hits = [
            e
            for e in flat(self._sp_filter(rows, q))
            if (not q.type or e["type"] == q.type) and (not q.sev or e["sev"] == q.sev)
        ]
        summary = {
            "types": dict(Counter(e["type"] for e in every)),
            "sevs": {k: sum(1 for e in every if e["sev"] == k) for k in ("high", "mid", "low")},
            "sps": len({e["code"] for e in every}),
            "all": len(every),
        }
        return self._page(hits, q, summary)

    # 到货预测 ------------------------------------------------------------------------

    def _forecast_rows(self, rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        snap = self.snapshot()
        rows = self._rows() if rows is None else rows
        shipped = [r for r in rows if r["status"] == "已发货"]
        pairs = {(g["store_id"], g["msku"]) for r in shipped for g in r["goods"] if g["msku"]}
        skus = {g["sku"] for r in shipped for g in r["goods"] if g["sku"]}
        return forecast_rows(
            rows,
            snap.wm,
            snap.today,
            snap.rules.wm_receive_buffer,
            item_ids=item_ids_by_store_msku(self.session, self.accounts, pairs),
            owners=owners_by_sku(self.session, self.accounts, skus),
        )

    def forecast(self, q: ForecastQuery) -> LogisticsList:
        kw = q.keyword.strip().lower()
        hits = [
            r
            for r in self._forecast_rows()
            if (not q.store or r["store_id"] == q.store)
            and (not q.region or any(x["region"] == q.region for x in r["lines"]))
            and (not q.owner or q.owner in r["owner"].split("、"))
            and (not q.bucket or (r["aShip"] if q.bucket == "arrived" else r[q.bucket]) > 0)
            and (not kw or kw in self._forecast_text(r, q.field).lower())
        ]
        hits.sort(key=lambda r: (-r["total"], r["key"]))
        summary = {
            **forecast_summary(hits),
            "buffer": self.snapshot().rules.wm_receive_buffer,
            "region_total": dict(self.snapshot().rules.region_total),
        }
        return self._page(hits, q, summary)

    @staticmethod
    def _forecast_text(r: dict[str, Any], field: str) -> str:
        if field == "track":
            return " ".join(r["trackings"])
        if field == "cargo":
            return " ".join(r["cargos"])
        if field == "sp":
            return " ".join(r["codes"])
        return f"{r['sku']} {r['msku']} {r['gtin']} {r['name']} {r['item_id']}"

    # 货代看板 ------------------------------------------------------------------------

    @staticmethod
    def _carrier_text(o: dict[str, Any], field: str) -> str:
        if field == "number":
            return o["number"]
        if field == "customer":
            return o["customerNumber"]
        if field == "sp":
            return o["sp"]
        return f"{o['number']} {o['customerNumber']} {o['sp']} {o['trackCn']}"

    def _carrier_orders(self) -> list[dict[str, Any]]:
        orders = self.snapshot().carrier_orders
        if self.stores is None:
            return orders
        codes = {item["sp"]["code"] for item in self.visible_rows()}
        return [o for o in orders if o["sp"] in codes]

    def carriers(self, q: CarrierQuery) -> LogisticsList:
        snap = self.snapshot()
        orders = self._carrier_orders()
        kw = q.keyword.strip().lower()
        hits = sort_orders(
            [
                o
                for o in orders
                if (not q.status or o["status"] == q.status)
                and (not q.stale or o["stale"])
                and (not q.store or o["store_id"] == q.store)
                and (not q.provider or o["provider_id"] == q.provider)
                and (not kw or kw in self._carrier_text(o, q.field).lower())
            ]
        )
        sps = [item["sp"] for item in self.visible_rows()]
        not_found, no_tracking, queried, zy_sps = missing_orders(
            sps,
            {o["number"] for o in snap.carrier_orders},
            zy_provider_ids(snap.inputs.providers),
            snap.inputs.stores,
        )
        summary = {
            "orders": len(orders),
            "linked": sum(1 for o in orders if o["sp"]),
            "unlinked": sum(1 for o in orders if not o["sp"]),
            "stale": sum(1 for o in orders if o["stale"]),
            "stale_days": STALE_DAYS,
            "queried": queried,
            "zy_sps": zy_sps,
            "status_counts": status_counts(orders),
            "providers": provider_counts(orders),
            "missing": [*not_found, *no_tracking],
            "not_found": len(not_found),
            "no_tracking": len(no_tracking),
        }
        items = [{k: v for k, v in o.items() if k != "tracks"} for o in hits]
        return self._page(items, q, summary)

    def carrier_order(self, number: str) -> CarrierOrderDetail | None:
        order = next((o for o in self._carrier_orders() if o["number"] == number), None)
        if order is None:
            return None
        return CarrierOrderDetail(today=self.snapshot().today, order=order)

    # 时效与阈值设置（只读） -----------------------------------------------------------

    def rules_view(self) -> LogisticsRulesView:
        tables = self._rule_tables()
        return LogisticsRulesView(
            today=self.snapshot().today,
            thresholds=self._thresholds(),
            region_total=dict(self.snapshot().rules.region_total),
            counts={k: len(v) for k, v in tables.items()},
            edit_hint=EDIT_HINT,
        )

    def rule_list(self, section: str, q: RuleListQuery) -> LogisticsList | None:
        tables = self._rule_tables()
        if section not in tables:
            return None
        if q.sort is not None and q.sort not in RULE_SORTS[section]:
            raise ValueError(q.sort)
        kw = q.keyword.strip().lower()
        rows = [
            r
            for r in tables[section]
            if (not kw or kw in " ".join(str(v) for v in r.values()).lower())
            and (
                not q.region or r.get("region") == q.region or q.region in (r.get("regions") or [])
            )
        ]
        if q.sort:
            key = q.sort
            rows.sort(
                key=lambda r: (r.get(key) is None, r.get(key) if r.get(key) is not None else 0),
                reverse=q.order == "desc",
            )
        return self._page(rows, q, {"all": len(tables[section])})

    def _thresholds(self) -> list[dict[str, Any]]:
        rules = self.snapshot().rules
        thresholds = [
            ("remind_before", rules.remind_before, "天", "即将超时提醒：距合同时效剩余 ≤ N 天"),
            (
                "delivered_not_signed",
                rules.delivered_not_signed,
                "天",
                "物流签收完成 → Walmart 签收 允许间隔；超过仍未签收 = 高异常",
            ),
            (
                "receive_diff_buffer",
                rules.receive_diff_buffer,
                "天",
                "Walmart 收货差异缓冲期：差异出现后先观察，超过才转异常",
            ),
            (
                "cost_missing_after",
                rules.cost_missing_after,
                "天",
                "发货后 N 天仍无实际费用 → 缺失提醒",
            ),
            (
                "time_missing_after",
                rules.time_missing_after,
                "天",
                "发货后 N 天仍无预计开船 / 到港 → 缺失提醒",
            ),
            (
                "wm_receive_buffer",
                rules.wm_receive_buffer,
                "天",
                "到仓后 Walmart 接收上架缓冲：预计可售日 = 到仓日 + N",
            ),
            ("penalty_per_kg_day", rules.penalty_per_kg_day, "元/KG/天", "逾期赔付（合同）"),
        ]
        return [{"key": k, "value": v, "unit": u, "label": label} for k, v, u, label in thresholds]

    def _rule_tables(self) -> dict[str, list[dict[str, Any]]]:
        snap = self.snapshot()
        rules = snap.rules
        rows = self._rows()
        chans = {c["channel_id"]: c for c in snap.inputs.channels}
        providers = snap.inputs.providers
        cycles = []
        for cid, c in rules.cycle.items():
            ch = chans.get(cid) or {}
            name = ch.get("channel_name") or next(
                (r["channel"] for r in rows if r["channel_id"] == cid), ""
            )
            pid = ch.get("provider_id", "")
            cycles.append(
                {
                    "channel_id": cid,
                    "channel": name,
                    "provider": ch.get("provider_name") or providers.get(pid, ""),
                    "method": ch.get("method_name", ""),
                    "regions": channel_regions(name),
                    "toSail": c.get("toSail"),
                    "voyage": c.get("voyage"),
                    "days": c.get("days"),
                    "src": c.get("src"),
                    "sps": sum(1 for r in rows if r["channel_id"] == cid),
                }
            )
        contracts = [
            {
                **c,
                "provider": providers.get(c["provider_id"], c["provider_id"]),
                "channel": (chans.get(c["channel_id"]) or {}).get("channel_name", ""),
                "sps": sum(
                    1
                    for r in rows
                    if r["provider_id"] == c["provider_id"]
                    and r["channel_id"] == c["channel_id"]
                    and r["region"] == c["region"]
                ),
            }
            for c in rules.contract
        ]
        fcs = sorted(snap.inputs.fcs.values(), key=lambda f: f["fc"])
        return {"cycles": cycles, "contracts": contracts, "fcs": fcs}

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
            walmart=[_wm_public(snap.wm[c], c) for c in cargo_codes if c in snap.wm],
        )


def _wm_public(w: dict[str, Any], code: str) -> dict[str, Any]:
    return {k: v for k, v in w.items() if k not in ("byGtin", "itemsRecv")} | {"code": code}

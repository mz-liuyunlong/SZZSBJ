"""WFS arrival / sellable rules (8088 ``arrival_rules.py``, business owner confirmed 2026-09-25).

Pure functions shared by the WFS shipment board, the exception centre and the logistics
page. The algorithm is a straight port of the demo rules; do not change a threshold or the
order of the fallback chain here without a new owner decision (rule ids below).

Arrival (per SP shipping list, whole container):
  actual = earliest of carrier "签收完成" and Walmart ``actualDeliveryDate`` of its cargos;
  otherwise plan chain: carrier "预计…派送入仓" > actual port arrival + cycle >
  actual sailing + voyage + cycle > ETA + cycle > Lingxing ``arrival_time`` >
  ship date + region fallback (West 50 / Central 60 / East 80).
Cargo arrival: earliest actual over its shipped SPs and its own Walmart signing; else the
latest plan over its shipped SPs.
Sellable (cargo × SKU): first Walmart Receipt date; otherwise arrival + ``BUFFER_DAYS``.
Bucket: sellable − data date: <0 / 0–15 / 16–30 / 31–60 / >60 / none.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Final

RULE_VERSION: Final = "WFS-ARRIVAL-20260925"
BUFFER_DAYS: Final = 10
SHIPPED_STATUS: Final = "已发货"
PENDING_DETAILS_STATUSES: Final = frozenset({"PENDING_SHIPMENT_DETAILS", "0", "待发货"})

BUCKET_OVERDUE: Final = "overdue"
BUCKET_15: Final = "d15"
BUCKET_30: Final = "d30"
BUCKET_60: Final = "d60"
BUCKET_60_PLUS: Final = "d60_plus"
BUCKET_NONE: Final = "none"
BUCKET_LABELS: Final[dict[str, str]] = {
    BUCKET_OVERDUE: "已过预计可售日未上架",
    BUCKET_15: "15 天内可售",
    BUCKET_30: "15–30 天可售",
    BUCKET_60: "30–60 天可售",
    BUCKET_60_PLUS: "超过 60 天可售",
    BUCKET_NONE: "无预计日期",
}

REGION_WEST: Final = "美西"
REGION_CENTRAL: Final = "美中"
REGION_EAST: Final = "美东"
REGION_UNKNOWN: Final = "待定"
REGION_BY_STATE: Final[dict[str, str]] = {
    **dict.fromkeys(("CA", "WA", "OR", "NV", "AZ", "UT"), REGION_WEST),
    **dict.fromkeys(
        (
            "TX", "IN", "MS", "AR", "LA", "IL", "KY", "OH", "MO", "TN",
            "WI", "MN", "KS", "OK", "CO",
        ),
        REGION_CENTRAL,
    ),
    **dict.fromkeys(
        ("NJ", "PA", "FL", "GA", "NY", "VA", "NC", "SC", "MD", "MA", "CT"), REGION_EAST
    ),
}  # fmt: skip
REGION_CYCLE: Final = {REGION_WEST: 7, REGION_CENTRAL: 10, REGION_EAST: 12}
REGION_STAGE: Final = {REGION_WEST: (7, 16), REGION_CENTRAL: (6, 20), REGION_EAST: (8, 40)}
REGION_TOTAL: Final = {REGION_WEST: 50, REGION_CENTRAL: 60, REGION_EAST: 80}

SRC_CARRIER_SIGNED: Final = "众壹签收"
SRC_WALMART_SIGNED: Final = "Walmart 签收"
SRC_CARRIER_EST: Final = "众壹预计派送入仓"
SRC_ATA: Final = "实际到港+周期"
SRC_ATD: Final = "实际开船+航程+周期"
SRC_ETA: Final = "预计到港+周期"
SRC_LX_ARRIVAL: Final = "领星预计到货"
SRC_REGION: Final = "发货日+地区兜底"
SRC_NONE: Final = "无"


def parse_date(value: str | date | None) -> date | None:
    """First ten characters as an ISO date; years before 2000 are provider placeholders."""

    if value is None:
        return None
    if isinstance(value, date):
        return value
    text_value = value.strip()
    if len(text_value) < 10 or text_value[:4] < "2000":
        return None
    try:
        return date.fromisoformat(text_value[:10])
    except ValueError:
        return None


def _add(day: date | None, days: int) -> date | None:
    return day + timedelta(days=days) if day else None


def region_of_state(state: str | None) -> str:
    return REGION_BY_STATE.get((state or "").strip().upper(), REGION_UNKNOWN)


def state_from_address(address: str | None) -> str | None:
    """Lingxing ``distribution_addresses``: ``line1, city, STATE, …`` (third part)."""

    parts = [part.strip() for part in (address or "").split(",")]
    return parts[2] if len(parts) > 2 else None


def channel_regions(name: str | None) -> list[str]:
    name = name or ""
    if "COSCO、EMC" in name:
        return [REGION_WEST]
    if "美东" in name or "萨凡纳" in name or "NY" in name:
        return [REGION_EAST]
    if "芝加哥" in name or "休斯顿" in name or "HOU" in name:
        return [REGION_CENTRAL]
    if "洛杉矶" in name or "LALB" in name:
        return [REGION_WEST]
    return [REGION_WEST, REGION_CENTRAL, REGION_EAST]


def cycle_days(name: str | None) -> int | None:
    name = name or ""
    if "美东直航" in name:
        return 12
    if "美东限时达" in name:
        return 15
    if "芝加哥" in name:
        return 18
    if "休斯顿" in name or "萨凡纳专线" in name:
        return 10
    return 7 if channel_regions(name) == [REGION_WEST] else None


def voyage_days(name: str | None) -> int | None:
    name = name or ""
    for keyword, days in (
        ("COSCO、EMC", 16),
        ("美东限时达", 13),
        ("美东直航", 44),
        ("芝加哥", 13),
        ("休斯顿", 32),
    ):
        if keyword in name:
            return days
    return None


def is_its_node(fc_code: str | None) -> bool:
    """Walmart node codes ending in ``T`` are ITS hubs (owner-confirmed 12/12, 2026-09-23)."""

    return bool(fc_code) and fc_code.strip().endswith("T")


@dataclass(frozen=True, slots=True)
class CarrierNodes:
    delivered: date | None = None
    atd: date | None = None
    eta: date | None = None
    ata: date | None = None
    est_delivery: date | None = None


@dataclass(frozen=True, slots=True)
class ShippingFacts:
    shipping_code: str
    status: str | None
    region: str
    channel_name: str | None = None
    delivery_time: str | None = None
    actual_delivery_time: str | None = None
    sail_time: str | None = None
    arrival_time: str | None = None
    expected_arrival_time: str | None = None
    cargo_codes: tuple[str, ...] = ()
    carrier: CarrierNodes | None = None


@dataclass(frozen=True, slots=True)
class SpArrival:
    status: str | None
    actual: date | None
    actual_source: str
    plan: date | None
    plan_source: str

    @property
    def arrival(self) -> date | None:
        return self.actual or self.plan

    @property
    def source(self) -> str:
        return self.actual_source or self.plan_source


@dataclass(frozen=True, slots=True)
class CargoArrival:
    date: date | None
    source: str
    real: bool
    shipped: bool


@dataclass(slots=True)
class WalmartFacts:
    """Walmart inbound facts keyed by shipment id (per-GTIN maps nested under the shipment)."""

    signed: dict[str, date] = field(default_factory=dict)
    first_receipt: dict[str, date] = field(default_factory=dict)
    last_receipt: dict[str, date] = field(default_factory=dict)
    first_receipt_by_gtin: dict[str, dict[str, date]] = field(default_factory=dict)
    receipt_units: dict[str, int] = field(default_factory=dict)
    receipt_units_by_gtin: dict[str, dict[str, int]] = field(default_factory=dict)
    shipments: set[str] = field(default_factory=set)
    received_units: dict[str, int] = field(default_factory=dict)
    item_received: dict[str, dict[str, int]] = field(default_factory=dict)
    item_damaged: dict[str, dict[str, int]] = field(default_factory=dict)
    stores: set[str] = field(default_factory=set)


def sp_arrival(sp: ShippingFacts, today: date, walmart_signed: Mapping[str, date]) -> SpArrival:
    nodes = sp.carrier or CarrierNodes()
    wm_signed = min(
        (walmart_signed[c] for c in sp.cargo_codes if c in walmart_signed), default=None
    )
    actuals = [d for d in (nodes.delivered, wm_signed) if d]
    actual = min(actuals) if actuals else None
    actual_source = ""
    if actual:
        actual_source = SRC_CARRIER_SIGNED if actual == nodes.delivered else SRC_WALMART_SIGNED
    sail = parse_date(sp.sail_time)
    atd = nodes.atd or (sail if sail and sail <= today else None)
    eta = parse_date(sp.expected_arrival_time) or nodes.eta
    ata = nodes.ata
    cycle = cycle_days(sp.channel_name)
    if cycle is None:
        cycle = REGION_CYCLE.get(sp.region)
    voyage = voyage_days(sp.channel_name) or (REGION_STAGE.get(sp.region) or (None, None))[1]
    delivery = parse_date(sp.delivery_time) or parse_date(sp.actual_delivery_time)
    lx_arrival = parse_date(sp.arrival_time)
    plan: date | None
    if nodes.est_delivery:
        plan, source = nodes.est_delivery, SRC_CARRIER_EST
    elif ata and cycle is not None:
        plan, source = _add(ata, cycle), SRC_ATA
    elif atd and voyage is not None and cycle is not None:
        plan, source = _add(atd, voyage + cycle), SRC_ATD
    elif eta and cycle is not None:
        plan, source = _add(eta, cycle), SRC_ETA
    elif lx_arrival:
        plan, source = lx_arrival, SRC_LX_ARRIVAL
    elif delivery and sp.region in REGION_TOTAL:
        plan, source = _add(delivery, REGION_TOTAL[sp.region]), SRC_REGION
    else:
        plan, source = None, SRC_NONE
    return SpArrival(
        status=sp.status,
        actual=actual,
        actual_source=actual_source,
        plan=plan,
        plan_source=source,
    )


def cargo_arrival(
    *,
    cargo_code: str,
    cargo_status: str | None,
    shipping_codes: Iterable[str],
    sp_map: Mapping[str, SpArrival],
    walmart_signed: Mapping[str, date],
) -> CargoArrival:
    codes = [code for code in shipping_codes if code]
    shipped_sps = [
        sp_map[code] for code in codes if code in sp_map and sp_map[code].status == SHIPPED_STATUS
    ]
    shipped = bool(shipped_sps) or (not codes and cargo_status not in PENDING_DETAILS_STATUSES)
    own_signed = walmart_signed.get(cargo_code)
    actuals = [sp.actual for sp in shipped_sps if sp.actual] + ([own_signed] if own_signed else [])
    if actuals:
        sources = sorted({sp.actual_source for sp in shipped_sps if sp.actual}) or [
            SRC_WALMART_SIGNED
        ]
        return CargoArrival(
            date=min(actuals),
            source="实际（" + "/".join(sources) + "）",
            real=True,
            shipped=shipped,
        )
    plans = [sp for sp in shipped_sps if sp.plan]
    if plans:
        latest = max(plans, key=lambda sp: sp.plan or date.min)
        return CargoArrival(
            date=latest.plan, source=latest.plan_source, real=False, shipped=shipped
        )
    return CargoArrival(date=None, source=SRC_NONE, real=False, shipped=shipped)


def sellable_date(first_receipt: date | None, arrival: date | None) -> tuple[date | None, bool]:
    """(date, real): first Walmart Receipt is real; else arrival + buffer days (plan)."""

    if first_receipt:
        return first_receipt, True
    return _add(arrival, BUFFER_DAYS), False


def bucket_of(sellable: date | None, today: date) -> str:
    if not sellable:
        return BUCKET_NONE
    days = (sellable - today).days
    if days < 0:
        return BUCKET_OVERDUE
    if days <= 15:
        return BUCKET_15
    if days <= 30:
        return BUCKET_30
    if days <= 60:
        return BUCKET_60
    return BUCKET_60_PLUS

"""8088 read-time shipment view and exception rules (``app-a.jsx`` ``enrich`` / ``itemRows`` /
``buildExceptions``, Rocky 2026-10-10 rules ``WFS-RULES-20261010``).

Everything here is relative to ``today`` and is therefore computed when the board is read,
from the published row (Lingxing cargo + goods) and its ``payload_json["derived"]`` facts.
Pure functions only: no database, no external call.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final

from app.modules.pmc_wfs.arrival_rules import (
    BUCKET_LABELS,
    BUFFER_DAYS,
    bucket_of,
    parse_date,
)

RULE_VERSION: Final = "WFS-RULES-20261010"
REGION_FALLBACK_SOURCE: Final = "发货日+地区兜底"
EXTERNAL_SINCE: Final = "2026-08-01"
APPEAL_OPEN_DAY: Final = 10
APPEAL_LAST_DAY: Final = 50
D0_GUESS_DAYS: Final = 2

TYPE_CLOSED_SHORT: Final = "已关闭短少"
TYPE_ETA_OVERDUE: Final = "预计到仓已过未签收"
TYPE_CARRIER_SIGNED: Final = "货代已签收 · WFS未收货"
TYPE_SIGNED_NO_RECEIPT: Final = "沃尔玛签收·未开始上架"
TYPE_RECEIVING_STUCK: Final = "收货长期未完成"
TYPE_PENDING_NO_SHIP: Final = "创建后长期未发货"
TYPE_APPEAL_OPEN: Final = "申诉期内未处理"
TYPE_APPEAL_URGENT: Final = "申诉临近期限"
TYPE_APPEAL_EXPIRED: Final = "申诉已过期"

RULE_FAMILY_BY_TYPE: Final[dict[str, str]] = {
    TYPE_CLOSED_SHORT: "closed_shortage_damage",
    TYPE_ETA_OVERDUE: "arrival_overdue",
    TYPE_CARRIER_SIGNED: "carrier_delivered_unreceived",
    TYPE_SIGNED_NO_RECEIPT: "arrival_no_receiving",
    TYPE_RECEIVING_STUCK: "receiving_incomplete",
    TYPE_PENDING_NO_SHIP: "create_long_unshipped",
    TYPE_APPEAL_OPEN: "appeal_deadline",
    TYPE_APPEAL_URGENT: "appeal_deadline",
    TYPE_APPEAL_EXPIRED: "appeal_deadline",
}


@dataclass(frozen=True, slots=True)
class WfsRules:
    """8088 exception thresholds (days / units); defaults = Rocky 2026-10-10."""

    diff_tol: int = 10
    eta_overdue: int = 7
    delivered_not_signed: int = 3
    sign_no_receipt: int = 10
    receiving_stuck: int = 15
    pending_no_ship: int = 7
    dispute_urgent: int = 5


@dataclass(slots=True)
class ItemView:
    msku: str
    sku: str
    name: str
    gtin: str
    item_id: str | None
    declare: int
    shipped: int
    lx_shipped: int
    lx_received: int
    wm_received: int | None
    put_away: int | None
    damaged: int
    normal: int
    over: int
    abnormal: int | None


@dataclass(slots=True)
class ShipmentView:
    code: str
    store_id: str
    store_name: str
    status: str
    created: str
    closed_at: str
    is_test: bool
    shipping_codes: list[str]
    declare: int
    shipped: int
    received: int
    baseline: int
    baseline_from: str
    diff: int
    boxes: int
    eta: str
    eta_source: str
    eta_source_label: str
    eta_passed: int | None
    sellable: str
    sellable_real: bool
    arrival_bucket: str
    shipped_out: bool
    d0: str
    d0_real: str
    d_n: int | None
    external: bool
    age_days: int | None
    region: str
    its_inferred: bool
    carrier_delivered_at: str
    wm_first: str
    wm_last: str
    wm_receipt_units: int
    wm_receiving: bool
    wm_done: bool
    items: list[ItemView] = field(default_factory=list)


@dataclass(slots=True)
class WfsException:
    type: str
    rule_family: str
    code: str
    store_id: str
    store_name: str
    severity: str  # high / mid / low (8088)
    found: str
    desc: str
    source: str  # real / calc / demo
    qty: int | None = None
    d0: str | None = None
    d_n: int | None = None
    item_keys: tuple[str, ...] = ()


def _days(a: str, b: str) -> int | None:
    da, db = parse_date(a), parse_date(b)
    return (db - da).days if da and db else None


def _add(day: str, n: int) -> str:
    parsed = parse_date(day)
    return (parsed + timedelta(days=n)).isoformat() if parsed else ""


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _utc_minute(value: Any) -> str:
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=UTC)
        return aware.astimezone(UTC).strftime("%Y-%m-%d %H:%M")
    return str(value or "")[:16]


def _fmt(n: int) -> str:
    return f"{n:,}"


def build_view(
    *,
    cargo_code: str,
    store_id: str,
    store_name: str,
    status: str,
    created: str,
    to_closed_at: Any,
    in_bound_order_id: str,
    shipping_codes: Sequence[str],
    goods: Sequence[Mapping[str, Any]],
    derived: Mapping[str, Any],
    today: date,
    item_ids: Mapping[str, str] | None = None,
) -> ShipmentView:
    """Port of 8088 ``enrich`` + ``itemRows`` for one published board row."""

    today_s = today.isoformat()
    sp_goods = [g for g in derived.get("sp_goods") or [] if isinstance(g, dict)]
    shipped_sp = sum(_int(g.get("shipped")) for g in sp_goods)
    declare = sum(_int(g.get("declare_num")) for g in goods)
    shipped_lx = sum(_int(g.get("shipments_num")) for g in goods)
    received = sum(_int(g.get("received_num")) for g in goods)
    shipped = shipped_sp if shipped_sp > 0 else shipped_lx
    baseline = shipped if shipped > 0 else declare
    eta = derived.get("arrival_date") or ""
    source_label = derived.get("arrival_source") or ""
    eta_source = ""
    if eta:
        if derived.get("arrival_real"):
            eta_source = "real"
        elif source_label == REGION_FALLBACK_SOURCE:
            eta_source = "region"
        else:
            eta_source = "plan"
    eta_passed = _days(eta, today_s) if eta and eta <= today_s else None
    wm_first = derived.get("walmart_first_receipt") or ""
    wm_last = derived.get("walmart_last_receipt") or ""
    receipt_units = _int(derived.get("walmart_receipt_units"))
    received_units = _int(derived.get("walmart_received_units"))
    sellable = wm_first or (_add(eta, BUFFER_DAYS) if eta else "")
    d0_real = derived.get("walmart_signed_date") or ""
    d0 = d0_real or (
        _add(eta, D0_GUESS_DAYS) if eta and (_days(eta, today_s) or 0) >= D0_GUESS_DAYS else ""
    )
    sellable_day = parse_date(sellable)
    view = ShipmentView(
        code=cargo_code,
        store_id=store_id,
        store_name=store_name,
        status=status,
        created=created[:16],
        closed_at=_utc_minute(to_closed_at) if to_closed_at else "",
        is_test=bool(derived.get("is_test")) or (in_bound_order_id or "").startswith("PMC-TEST-"),
        shipping_codes=list(shipping_codes),
        declare=declare,
        shipped=shipped,
        received=received,
        baseline=baseline,
        baseline_from="SP" if shipped_sp > 0 else "declare",
        diff=received - baseline,
        boxes=sum(_int(g.get("boxes")) for g in sp_goods),
        eta=eta,
        eta_source=eta_source,
        eta_source_label=source_label,
        eta_passed=eta_passed,
        sellable=sellable,
        sellable_real=bool(wm_first),
        arrival_bucket=bucket_of(sellable_day, today),
        shipped_out=bool(derived.get("shipped_out")),
        d0=d0,
        d0_real=d0_real,
        d_n=_days(d0, today_s) if d0 else None,
        external=not shipping_codes and status != "CANCELLED" and created >= EXTERNAL_SINCE,
        age_days=_days(created, today_s),
        region=derived.get("region") or "待定",
        its_inferred=bool(derived.get("its_inferred")),
        carrier_delivered_at=derived.get("carrier_delivered_at") or "",
        wm_first=wm_first,
        wm_last=wm_last,
        wm_receipt_units=receipt_units,
        wm_receiving=bool(wm_first) and status != "CLOSED",
        wm_done=bool(wm_last)
        and (status == "CLOSED" or (received_units > 0 and receipt_units >= received_units)),
    )
    view.items = _items(goods, sp_goods, derived, item_ids or {})
    return view


def _items(
    goods: Sequence[Mapping[str, Any]],
    sp_goods: Sequence[Mapping[str, Any]],
    derived: Mapping[str, Any],
    item_ids: Mapping[str, str],
) -> list[ItemView]:
    wm_recv = derived.get("walmart_item_received") or {}
    wm_dmg = derived.get("walmart_item_damaged") or {}
    put_units = derived.get("walmart_receipt_units_by_gtin") or {}
    rows: list[ItemView] = []
    for good in goods:
        msku = str(good.get("msku") or "")
        gtin = str(good.get("gtin") or "")
        sp = next((g for g in sp_goods if g.get("msku") == msku), None)
        declare = _int(good.get("declare_num"))
        shipped = (
            (_int(sp.get("shipped")) if sp else 0) or _int(good.get("shipments_num")) or declare
        )
        lx_received = _int(good.get("received_num"))
        damaged = max(_int(good.get("damaged_qty")), _int(wm_dmg.get(gtin)))
        normal = max(0, min(lx_received, shipped) - damaged)
        rows.append(
            ItemView(
                msku=msku,
                sku=str(good.get("sku") or ""),
                name=str(good.get("product_name") or ""),
                gtin=gtin,
                item_id=item_ids.get(msku),
                declare=declare,
                shipped=shipped,
                lx_shipped=_int(good.get("shipments_num")),
                lx_received=lx_received,
                wm_received=_int(wm_recv[gtin]) if gtin in wm_recv else None,
                put_away=_int(put_units[gtin]) if gtin in put_units else None,
                damaged=damaged,
                normal=normal,
                over=lx_received - shipped if lx_received > shipped else 0,
                abnormal=max(0, shipped - normal) if shipped > 0 else None,
            )
        )
    return rows


def big_gaps(view: ShipmentView, rules: WfsRules) -> list[ItemView]:
    return [i for i in view.items if i.abnormal is not None and i.abnormal > rules.diff_tol]


def _gap_qty(gaps: Sequence[ItemView]) -> int:
    return sum(i.abnormal or 0 for i in gaps)


def _keys(gaps: Sequence[ItemView]) -> tuple[str, ...]:
    return tuple(i.msku or i.sku for i in gaps)


def build_exceptions(
    views: Sequence[ShipmentView], rules: WfsRules, today: date
) -> list[WfsException]:
    """Port of 8088 ``buildExceptions``: one stage rule per shipment plus the appeal window."""

    today_s = today.isoformat()
    out: list[WfsException] = []

    def push(kind: str, v: ShipmentView, **extra: Any) -> None:
        out.append(
            WfsException(
                type=kind,
                rule_family=RULE_FAMILY_BY_TYPE[kind],
                code=v.code,
                store_id=v.store_id,
                store_name=v.store_name,
                severity=extra.pop("severity", "mid"),
                found=extra.pop("found", today_s),
                **extra,
            )
        )

    for v in views:
        if v.is_test:
            continue
        big = big_gaps(v, rules)
        if v.status == "CLOSED" and big:
            q = _gap_qty(big)
            detail = "；".join(
                f"{i.msku or i.sku} 发 {i.shipped} / 正常 {i.normal}（异常 {i.abnormal}）"
                for i in big
            )
            push(
                TYPE_CLOSED_SHORT,
                v,
                severity="high" if q >= 25 else "mid",
                qty=-q,
                found=v.closed_at[:10] if v.closed_at else today_s,
                desc=f"已关闭，{len(big)} 个 SKU 差异超过 {rules.diff_tol} 件：{detail}",
                source="calc",
                item_keys=_keys(big),
            )
        if (
            v.status == "AWAITING_DELIVERY"
            and v.eta_source != "real"
            and v.eta_passed is not None
            and v.eta_passed >= rules.eta_overdue
        ):
            push(
                TYPE_ETA_OVERDUE,
                v,
                severity="high" if v.eta_passed >= rules.eta_overdue * 3 else "mid",
                found=_add(v.eta, rules.eta_overdue),
                desc=(
                    f"预计到仓 {v.eta}（{v.eta_source_label or '领星预计到仓时间'}）已过 "
                    f"{v.eta_passed} 天，沃尔玛仍为在途待收货"
                ),
                source="calc",
            )
        sign_day = v.d0_real or v.wm_first
        sign_real = bool(v.d0_real)
        done = v.status == "CLOSED" or (v.baseline > 0 and v.received >= v.baseline)
        if v.status != "CANCELLED" and not done:
            if not sign_day:
                if v.carrier_delivered_at and v.received == 0:
                    n = _days(v.carrier_delivered_at, today_s)
                    if n is not None and n >= rules.delivered_not_signed:
                        push(
                            TYPE_CARRIER_SIGNED,
                            v,
                            severity="high",
                            found=_add(v.carrier_delivered_at, rules.delivered_not_signed),
                            desc=(
                                f"众壹签收 {v.carrier_delivered_at}，已 {n} 天；"
                                "沃尔玛未签收、领星已收 = 0"
                            ),
                            source="real",
                        )
            elif not v.wm_first and v.received == 0:
                n = _days(sign_day, today_s)
                if n is not None and n >= rules.sign_no_receipt and big:
                    push(
                        TYPE_SIGNED_NO_RECEIPT,
                        v,
                        severity="high",
                        qty=-_gap_qty(big),
                        found=_add(sign_day, rules.sign_no_receipt),
                        desc=(
                            f"沃尔玛签收 {sign_day} 起 {n} 天仍未开始上架"
                            "（沃尔玛无入库记录，领星已收 0）"
                        ),
                        source="real" if sign_real else "calc",
                        item_keys=_keys(big),
                    )
            else:
                n = _days(sign_day, today_s)
                if n is not None and n >= rules.receiving_stuck and big:
                    gaps = "、".join(f"{i.msku or i.sku} 差 {i.abnormal}" for i in big)
                    note = "" if sign_real else "（无签收日，以首批上架日视同签收）"
                    push(
                        TYPE_RECEIVING_STUCK,
                        v,
                        severity="high",
                        qty=-_gap_qty(big),
                        found=_add(sign_day, rules.receiving_stuck),
                        desc=(
                            f"自沃尔玛签收 {sign_day}{note} 起 {n} 天仍未收完"
                            f"（已收 {v.received}/{v.baseline}；{len(big)} 个 SKU 差异超过 "
                            f"{rules.diff_tol} 件：{gaps}）"
                        ),
                        source="real" if sign_real else "calc",
                        item_keys=_keys(big),
                    )
        if (
            v.status == "PENDING_SHIPMENT_DETAILS"
            and v.age_days is not None
            and v.age_days >= rules.pending_no_ship
        ):
            push(
                TYPE_PENDING_NO_SHIP,
                v,
                severity="low",
                found=_add(v.created, rules.pending_no_ship),
                desc=f"创建 {v.age_days} 天仍未补发货信息 / 未关联发货单",
                source="calc",
            )
    for v in views:
        if v.is_test or v.status != "CLOSED" or not v.d0_real:
            continue
        big = big_gaps(v, rules)
        if not big or v.d_n is None:
            continue
        n = v.d_n
        stage = (
            "未到可申诉"
            if n < APPEAL_OPEN_DAY
            else ("申诉期内" if n <= APPEAL_LAST_DAY else "申诉已过期")
        )
        remain = APPEAL_LAST_DAY - n if n <= APPEAL_LAST_DAY else None
        if n > APPEAL_LAST_DAY:
            kind, sev = TYPE_APPEAL_EXPIRED, "low"
        elif remain is not None and remain <= rules.dispute_urgent:
            kind, sev = TYPE_APPEAL_URGENT, "high"
        else:
            kind, sev = TYPE_APPEAL_OPEN, "mid"
        q = _gap_qty(big)
        tail = (
            f"，距申诉截止（签收后第 {APPEAL_LAST_DAY} 天）剩 {remain} 天"
            if remain is not None
            else ""
        )
        push(
            kind,
            v,
            severity=sev,
            found=_add(v.d0, APPEAL_OPEN_DAY),
            qty=-q,
            desc=(
                f"沃尔玛签收日 {v.d0}，今天是签收后第 {n} 天，{stage}{tail}；"
                f"短少（单 SKU > {rules.diff_tol} 件）{q} 件"
            ),
            source="real",
            d0=v.d0,
            d_n=n,
            item_keys=_keys(big),
        )
    return out


BUCKET_RECEIVING: Final = "receiving"


@dataclass(slots=True)
class ProductLine:
    code: str
    status: str
    msku: str
    shipped: int
    signed: int
    shelved: int
    eta: str
    eta_source: str
    sellable: str
    sellable_real: bool
    bucket: str
    region: str


@dataclass(slots=True)
class ProductView:
    """8088 产品维度 row: store × Item ID, units not yet sellable by sellable-date bucket."""

    store_id: str
    store_name: str
    item_id: str
    mskus: list[str]
    skus: list[str]
    name: str
    ships: int = 0
    in_transit: int = 0
    buckets: dict[str, int] = field(default_factory=dict)
    signed_not_put: int = 0
    receiving: int = 0
    arrived_shipped: int = 0
    arrived_signed: int = 0
    arrived_shelved: int = 0
    signed_zero_shelved: int = 0
    next_eta: str = ""
    next_sellable: str = ""
    lines: list[ProductLine] = field(default_factory=list)


def product_views(views: Sequence[ShipmentView], today: date) -> list[ProductView]:
    """Port of 8088 ``app-c.jsx`` product dimension (no item without an Item ID)."""

    out: dict[tuple[str, str], ProductView] = {}
    mskus: dict[tuple[str, str], set[str]] = {}
    skus: dict[tuple[str, str], set[str]] = {}
    for v in views:
        for i in v.items:
            if not i.item_id or v.status == "CANCELLED" or v.is_test:
                continue
            key = (v.store_id, i.item_id)
            row = out.get(key)
            if row is None:
                row = out[key] = ProductView(
                    store_id=v.store_id,
                    store_name=v.store_name,
                    item_id=i.item_id,
                    mskus=[],
                    skus=[],
                    name=i.name,
                    buckets=dict.fromkeys(BUCKET_LABELS, 0),
                )
                mskus[key], skus[key] = set(), set()
            mskus[key].add(i.msku)
            skus[key].add(i.sku)
            signed = i.wm_received if i.wm_received is not None else i.lx_received
            shelved = i.put_away or 0
            if v.status == "CLOSED" or not v.shipped_out or i.lx_shipped <= 0:
                continue
            line = dict(
                code=v.code,
                status=v.status,
                msku=i.msku,
                shipped=i.lx_shipped,
                signed=signed,
                eta=v.eta,
                eta_source=v.eta_source,
                region=v.region,
            )
            if shelved > 0:
                row.receiving += i.lx_shipped - signed
                row.arrived_shipped += i.lx_shipped
                row.arrived_signed += signed
                row.arrived_shelved += shelved
                if signed == 0:
                    row.signed_zero_shelved += 1
                row.lines.append(
                    ProductLine(
                        **line,
                        shelved=shelved,
                        sellable=v.wm_first,
                        sellable_real=bool(v.wm_first),
                        bucket=BUCKET_RECEIVING,
                    )
                )
                continue
            sell = _add(v.eta, BUFFER_DAYS) if v.eta else ""
            bucket = bucket_of(parse_date(sell), today)
            row.ships += 1
            row.in_transit += i.lx_shipped
            row.buckets[bucket] = row.buckets.get(bucket, 0) + i.lx_shipped
            if signed > 0:
                row.signed_not_put += signed
            row.lines.append(
                ProductLine(**line, shelved=0, sellable=sell, sellable_real=False, bucket=bucket)
            )
            if v.eta and (not row.next_eta or v.eta < row.next_eta):
                row.next_eta = v.eta
            if sell and (not row.next_sellable or sell < row.next_sellable):
                row.next_sellable = sell
    result = []
    for key, row in out.items():
        if row.in_transit > 0 or row.arrived_shipped > 0:
            row.mskus = sorted(mskus[key])
            row.skus = sorted(skus[key])
            result.append(row)
    result.sort(key=lambda r: -r.in_transit)
    return result

"""Pure business-rule calculations for the PMC purchase board (Gate 3, PR G3-C).

Every function here is deterministic, side-effect free and database free, so
the rules in ``docs/business-rules/pmc-purchase-rules.md`` (v3) can be tested
one clause at a time. The DWD publisher and the DWS refresh call these
functions; nothing here knows about SQLAlchemy sessions or provider clients.

Section references (``§``) point at the business-rules document. Thresholds
are never hard-coded inside a rule: they arrive through ``PurchaseThresholds``,
whose defaults mirror the v3 document and are the seed values of
``rule_purchase_thresholds`` (G3-A).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Final, Literal

# --- constants ------------------------------------------------------------------------

FOUR_PLACES: Final = Decimal("0.0001")
ONE: Final = Decimal("1")

# §5.1 row 1: ``ITEMID:19051502014`` in the plan remark; exactly eleven digits.
ITEMID_REMARK_PATTERN: Final = re.compile(r"ITEMID:\s*(\d{11})(?!\d)", re.IGNORECASE)

# Provider status codes (contract docs + §2 table).
PLAN_STATUS_PENDING_APPROVAL: Final = 121
PLAN_STATUS_PENDING_PURCHASE: Final = 2
PLAN_STATUS_REJECTED: Final = 122
PLAN_STATUS_COMPLETED: Final = -2
PLAN_STATUS_VOID: Final = frozenset({-3, 124})

ORDER_STATUS_PENDING_ORDER: Final = 1
ORDER_STATUS_ORDERED: Final = 2
ORDER_STATUS_COMPLETED: Final = 9
ORDER_STATUS_VOID: Final = -1

# §5.6: Walmart fulfillment type as stored on dim_walmart_listings.fulfillment_type.
FULFILLMENT_WFS: Final = "1"
FULFILLMENT_NOT_READY: Final = frozenset({"0", "2"})

type StageCode = Literal["S1", "S2", "S3", "S4", "S9", "S0", "UNKNOWN"]
type ItemIdSource = Literal[
    "manual", "from_system_plan", "from_plan_remark", "from_shipment", "unresolved"
]
type SkuCycleSource = Literal["samples", "baseline_mix", "lingxing_default", "no_baseline"]
type SampleExclusion = Literal["auto_short", "manual", "before_baseline", "outside_window"]


@dataclass(frozen=True, slots=True)
class PurchaseThresholds:
    """Rule parameters (§2 table, §3.2, §4.2, §4.4). Defaults = business rules v3."""

    s1_approval_days: int = 2
    s2_pending_days: int = 7
    default_cycle_days: int = 7
    arrival_ratio: Decimal = Decimal("0.5")
    auto_exclude_below_days: int = 2
    sample_window: int = 5
    min_samples_for_average: int = 2
    unstable_min_samples: int = 5
    unstable_range_days: int = 3
    # §4.2 人工基准: "新有效样本满 4 张时基准被挤出". Kept as a parameter because the
    # sentence admits two readings (4 vs. window-1); see .planning findings.
    baseline_evict_at_samples: int = 4

    def __post_init__(self) -> None:
        if not 0 < self.arrival_ratio <= ONE:
            raise ValueError("arrival_ratio must be within (0, 1]")
        for name in (
            "s1_approval_days",
            "s2_pending_days",
            "default_cycle_days",
            "auto_exclude_below_days",
            "sample_window",
            "min_samples_for_average",
            "unstable_min_samples",
            "unstable_range_days",
            "baseline_evict_at_samples",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.sample_window < 1:
            raise ValueError("sample_window must be at least 1")


# --- provider value normalisation (§1.1, §3.2, §7) -----------------------------------


def parse_provider_date(value: object) -> date | None:
    """Return the Beijing calendar date of a Lingxing time string.

    Lingxing returns ``YYYY-MM-DD HH:MM:SS`` (or a bare date) in Asia/Shanghai with no
    zone marker. All board metrics use the date only (§3.2), so the time part is
    dropped rather than converted. Empty / zero / malformed values become ``None``.
    """

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text.startswith("0000-00-00"):
        return None
    head = text[:10]
    try:
        return date.fromisoformat(head)
    except ValueError:
        return None


def normalize_store_id(value: object) -> str | None:
    """Store ids are strings end to end (§1.1); ``0`` / blank means unattributed (§1.3)."""

    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text or text == "0":
        return None
    return text


def days_between(start: date | None, end: date | None) -> int | None:
    """Whole days ``end - start``; same day = 0 (§4). ``None`` when either side is missing."""

    if start is None or end is None:
        return None
    return (end - start).days


# --- ItemID attribution (§5.1) -------------------------------------------------------


def parse_itemid_remark(remark: object) -> str | None:
    """Extract the first ``ITEMID:<11 digits>`` marker from a plan remark."""

    if not isinstance(remark, str):
        return None
    match = ITEMID_REMARK_PATTERN.search(remark)
    return match.group(1) if match else None


@dataclass(frozen=True, slots=True)
class ItemIdAttribution:
    item_id: str | None
    source: ItemIdSource


def resolve_item_id(
    *,
    manual_item_id: str | None = None,
    system_plan_item_id: str | None = None,
    plan_remark_item_id: str | None = None,
) -> ItemIdAttribution:
    """Apply the §5.1 priority: manual > from_system_plan > from_plan_remark > unresolved.

    ``from_shipment`` (§5.3) is reserved for the WFS shipment module and is never
    produced here. Blank strings count as absent.
    """

    if _nonblank(manual_item_id):
        return ItemIdAttribution(str(manual_item_id).strip(), "manual")
    if _nonblank(system_plan_item_id):
        return ItemIdAttribution(str(system_plan_item_id).strip(), "from_system_plan")
    if _nonblank(plan_remark_item_id):
        return ItemIdAttribution(str(plan_remark_item_id).strip(), "from_plan_remark")
    return ItemIdAttribution(None, "unresolved")


def wfs_not_ready(item_id_source: ItemIdSource, fulfillment_type: object) -> bool | None:
    """§5.6: flag rows whose attributed listing is not Walmart Fulfilled.

    Returns ``None`` when the check does not apply (unresolved attribution) or the
    fulfillment type is unknown, ``True`` for ``0`` (eligible, not converted) and
    ``2`` (seller fulfilled), ``False`` for ``1`` (WFS).
    """

    if item_id_source == "unresolved":
        return None
    if fulfillment_type is None or isinstance(fulfillment_type, bool):
        return None
    text = str(fulfillment_type).strip()
    if text == FULFILLMENT_WFS:
        return False
    if text in FULFILLMENT_NOT_READY:
        return True
    return None


# --- merged purchase orders (§5.2) ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlanShare:
    plan_sn: str
    quantity_plan: int | None


@dataclass(frozen=True, slots=True)
class PlanAllocation:
    plan_sn: str
    ratio: Decimal
    quantity: int
    amount: Decimal | None


def allocate_by_plan_quantity(
    *,
    quantity: int,
    amount: Decimal | None,
    plans: list[PlanShare],
) -> list[PlanAllocation]:
    """Split one purchase-order line across its plans by ``quantity_plan`` ratio.

    Integer quantities use largest-remainder rounding so the parts always sum to the
    line quantity; the amount is split with the same ratios (4 dp) and the rounding
    remainder lands on the last plan. Plans without a usable ``quantity_plan`` share
    equally when none has one; otherwise they receive ratio 0 (§5.2: 按各计划
    quantity_plan 比例). A single plan gets everything.
    """

    if not plans:
        raise ValueError("allocation requires at least one plan")
    if quantity < 0:
        raise ValueError("quantity must be non-negative")
    seen: set[str] = set()
    for plan in plans:
        if not plan.plan_sn or plan.plan_sn in seen:
            raise ValueError("plan_sn values must be non-empty and unique")
        seen.add(plan.plan_sn)

    weights = [max(p.quantity_plan or 0, 0) for p in plans]
    total_weight = sum(weights)
    if total_weight == 0:
        weights = [1] * len(plans)
        total_weight = len(plans)

    ratios = [
        (Decimal(w) / Decimal(total_weight)).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
        for w in weights
    ]

    raw = [Decimal(quantity) * Decimal(w) / Decimal(total_weight) for w in weights]
    floors = [int(r) for r in raw]
    shortfall = quantity - sum(floors)
    remainders = sorted(range(len(plans)), key=lambda i: (raw[i] - floors[i], -i), reverse=True)
    for i in remainders[:shortfall]:
        floors[i] += 1

    amounts: list[Decimal | None]
    if amount is None:
        amounts = [None] * len(plans)
    else:
        parts = [
            (amount * Decimal(w) / Decimal(total_weight)).quantize(
                FOUR_PLACES, rounding=ROUND_HALF_UP
            )
            for w in weights
        ]
        parts[-1] = parts[-1] + (amount - sum(parts))
        amounts = list(parts)

    return [
        PlanAllocation(plan_sn=p.plan_sn, ratio=ratios[i], quantity=floors[i], amount=amounts[i])
        for i, p in enumerate(plans)
    ]


# --- arrival and progress (§3) ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReceiptEvent:
    receive_date: date
    quantity: int
    receipt_order_sn: str | None = None


@dataclass(frozen=True, slots=True)
class ArrivalResult:
    quantity_total: int
    quantity_received: int
    progress_ratio: Decimal | None
    arrival_date: date | None
    arrival_receipt_order_sn: str | None
    remaining_quantity: int


def compute_arrival(
    *,
    quantity_total: int,
    receipts: list[ReceiptEvent],
    thresholds: PurchaseThresholds,
) -> ArrivalResult:
    """§3.2 whole-order arrival: first receipt at which the cumulative received quantity
    reaches ``quantity_total × arrival_ratio``; §3.3 progress ratio (may exceed 1);
    §3.4 remaining quantity (never negative).
    """

    if quantity_total < 0:
        raise ValueError("quantity_total must be non-negative")
    ordered = sorted(receipts, key=lambda r: (r.receive_date, r.receipt_order_sn or ""))
    received = 0
    arrival: date | None = None
    arrival_sn: str | None = None
    target = Decimal(quantity_total) * thresholds.arrival_ratio
    for event in ordered:
        if event.quantity < 0:
            raise ValueError("receipt quantity must be non-negative")
        received += event.quantity
        if arrival is None and quantity_total > 0 and Decimal(received) >= target:
            arrival = event.receive_date
            arrival_sn = event.receipt_order_sn
    progress = (
        (Decimal(received) / Decimal(quantity_total)).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
        if quantity_total > 0
        else None
    )
    return ArrivalResult(
        quantity_total=quantity_total,
        quantity_received=received,
        progress_ratio=progress,
        arrival_date=arrival,
        arrival_receipt_order_sn=arrival_sn,
        remaining_quantity=max(quantity_total - received, 0),
    )


# --- stage and overdue (§2) ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StageResult:
    stage_code: StageCode
    stage_start: date | None
    threshold_days: int | None
    due_date: date | None
    overdue_days: int
    alert_due_since: date | None
    start_estimated: bool = False


def _overdue(
    *, start: date | None, threshold_days: int | None, today: date, suppress: bool
) -> tuple[date | None, int, date | None]:
    if suppress or start is None or threshold_days is None:
        return None, 0, None
    due = date.fromordinal(start.toordinal() + threshold_days)
    overdue = max((today - due).days, 0)
    return due, overdue, (date.fromordinal(due.toordinal() + 1) if overdue > 0 else None)


def classify_plan_stage(
    *,
    plan_status: int | None,
    plan_create_date: date | None,
    first_seen_pending_date: date | None,
    has_purchase_order: bool,
    store_attributed: bool,
    today: date,
    thresholds: PurchaseThresholds,
) -> StageResult:
    """Stage of a purchase *plan* that has not yet become a purchase order.

    S1 = 待审批 (status 121) from plan create date, S2 = 待采购 (status 2) from the date
    the system first observed the pending state (§2, with create date as an estimated
    fallback for back-filled history), S0 = void/rejected. Plans already converted
    into a purchase order are classified through the order instead. Overdue is never
    computed for unattributed-store rows (§1.3).
    """

    if plan_status in PLAN_STATUS_VOID or plan_status == PLAN_STATUS_REJECTED:
        return StageResult("S0", None, None, None, 0, None)
    if has_purchase_order or plan_status == PLAN_STATUS_COMPLETED:
        return StageResult("S9", None, None, None, 0, None)
    if plan_status == PLAN_STATUS_PENDING_APPROVAL:
        due, overdue, since = _overdue(
            start=plan_create_date,
            threshold_days=thresholds.s1_approval_days,
            today=today,
            suppress=not store_attributed,
        )
        return StageResult("S1", plan_create_date, thresholds.s1_approval_days, due, overdue, since)
    if plan_status == PLAN_STATUS_PENDING_PURCHASE:
        start = first_seen_pending_date or plan_create_date
        due, overdue, since = _overdue(
            start=start,
            threshold_days=thresholds.s2_pending_days,
            today=today,
            suppress=not store_attributed,
        )
        return StageResult(
            "S2",
            start,
            thresholds.s2_pending_days,
            due,
            overdue,
            since,
            start_estimated=first_seen_pending_date is None,
        )
    return StageResult("UNKNOWN", None, None, None, 0, None)


def classify_order_stage(
    *,
    order_status: int | None,
    order_create_date: date | None,
    order_date: date | None,
    arrival: ArrivalResult,
    sku_cycle_days: int | None,
    store_attributed: bool,
    today: date,
    thresholds: PurchaseThresholds,
) -> StageResult:
    """Stage of a purchase order (§2 table rows S2/S3/S4/S9/S0).

    S2 = status 1 待下单 from the order create date (7 d); S3 = status 2 with nothing
    received, S4 = status 2 with something received but arrival (50 %) not reached,
    both from ``order_time`` with the SKU actual cycle as threshold (default 7 d when
    unknown); S9 = status 9 or arrival reached; S0 = status -1. ``expect_arrive_time``
    is never a threshold (§2.1).
    """

    if order_status == ORDER_STATUS_VOID:
        return StageResult("S0", None, None, None, 0, None)
    if order_status == ORDER_STATUS_COMPLETED or arrival.arrival_date is not None:
        return StageResult("S9", None, None, None, 0, None)
    if order_status == ORDER_STATUS_PENDING_ORDER:
        due, overdue, since = _overdue(
            start=order_create_date,
            threshold_days=thresholds.s2_pending_days,
            today=today,
            suppress=not store_attributed,
        )
        return StageResult("S2", order_create_date, thresholds.s2_pending_days, due, overdue, since)
    if order_status == ORDER_STATUS_ORDERED:
        threshold = sku_cycle_days if sku_cycle_days is not None else thresholds.default_cycle_days
        start = order_date or order_create_date
        due, overdue, since = _overdue(
            start=start,
            threshold_days=threshold,
            today=today,
            suppress=not store_attributed,
        )
        code: StageCode = "S3" if arrival.quantity_received == 0 else "S4"
        return StageResult(
            code, start, threshold, due, overdue, since, start_estimated=order_date is None
        )
    return StageResult("UNKNOWN", None, None, None, 0, None)


# --- SKU actual purchase cycle (§4.2, §4.4) --------------------------------------------


@dataclass(frozen=True, slots=True)
class CycleSample:
    """One arrived purchase order of a SKU. ``arrival_date`` already reflects a manual
    arrival-date correction when one exists (§4.2 人工修正单次交期)."""

    purchase_order_sn: str
    order_date: date
    arrival_date: date
    manually_excluded: bool = False

    @property
    def cycle_days(self) -> int:
        return (self.arrival_date - self.order_date).days


@dataclass(frozen=True, slots=True)
class ManualBaseline:
    value_days: int
    set_on: date


@dataclass(frozen=True, slots=True)
class ConsideredSample:
    purchase_order_sn: str
    order_date: date
    arrival_date: date
    cycle_days: int
    used: bool
    exclusion: SampleExclusion | None


@dataclass(frozen=True, slots=True)
class SkuCycleResult:
    value_days: Decimal | None
    source: SkuCycleSource
    sample_count: int
    baseline_days: int | None
    unstable: bool
    range_days: int | None
    considered: list[ConsideredSample] = field(default_factory=list)


def compute_sku_cycle(
    *,
    samples: list[CycleSample],
    baseline: ManualBaseline | None,
    lingxing_default_days: int | None,
    thresholds: PurchaseThresholds,
) -> SkuCycleResult:
    """§4.2 SKU actual purchase cycle.

    Candidates = arrived orders, newest ``order_date`` first (caller already dropped
    void and ``sid=0`` orders). Auto-excluded when cycle < ``auto_exclude_below_days``;
    manually excluded rows are skipped too. Valid = the newest ``sample_window`` of the
    rest. With a manual baseline, orders placed on/before ``set_on`` no longer take
    part; the baseline occupies one slot until ``baseline_evict_at_samples`` newer valid
    orders exist, after which the pure calculation resumes. Fewer than
    ``min_samples_for_average`` valid samples (and no baseline) fall back to the
    Lingxing default delivery days. §4.4 unstable = ``unstable_min_samples`` or more
    real samples used and max − min ≥ ``unstable_range_days``.
    """

    ordered = sorted(samples, key=lambda s: (s.order_date, s.purchase_order_sn), reverse=True)
    considered: list[ConsideredSample] = []
    valid: list[CycleSample] = []
    for sample in ordered:
        exclusion: SampleExclusion | None = None
        if baseline is not None and sample.order_date <= baseline.set_on:
            exclusion = "before_baseline"
        elif sample.manually_excluded:
            exclusion = "manual"
        elif sample.cycle_days < thresholds.auto_exclude_below_days:
            exclusion = "auto_short"
        elif len(valid) >= thresholds.sample_window:
            exclusion = "outside_window"
        used = exclusion is None
        if used:
            valid.append(sample)
        considered.append(
            ConsideredSample(
                purchase_order_sn=sample.purchase_order_sn,
                order_date=sample.order_date,
                arrival_date=sample.arrival_date,
                cycle_days=sample.cycle_days,
                used=used,
                exclusion=exclusion,
            )
        )

    values = [Decimal(s.cycle_days) for s in valid]
    baseline_active = baseline is not None and len(valid) < thresholds.baseline_evict_at_samples
    if baseline_active:
        assert baseline is not None
        room = max(thresholds.sample_window - 1, 0)
        values = values[:room]
        pooled = [Decimal(baseline.value_days), *values]
        return SkuCycleResult(
            value_days=_average(pooled),
            source="baseline_mix",
            sample_count=len(values),
            baseline_days=baseline.value_days,
            unstable=False,
            range_days=_range(values),
            considered=considered,
        )

    if len(values) >= thresholds.min_samples_for_average:
        return SkuCycleResult(
            value_days=_average(values),
            source="samples",
            sample_count=len(values),
            baseline_days=None,
            unstable=(
                len(values) >= thresholds.unstable_min_samples
                and (_range(values) or 0) >= thresholds.unstable_range_days
            ),
            range_days=_range(values),
            considered=considered,
        )
    if lingxing_default_days is not None:
        return SkuCycleResult(
            value_days=Decimal(lingxing_default_days),
            source="lingxing_default",
            sample_count=len(values),
            baseline_days=None,
            unstable=False,
            range_days=_range(values),
            considered=considered,
        )
    return SkuCycleResult(
        value_days=None,
        source="no_baseline",
        sample_count=len(values),
        baseline_days=None,
        unstable=False,
        range_days=_range(values),
        considered=considered,
    )


def cycle_threshold_days(result: SkuCycleResult) -> int | None:
    """Integer threshold for S3/S4 derived from a SKU cycle (rounded half up)."""

    if result.value_days is None:
        return None
    return int(result.value_days.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# --- helpers ---------------------------------------------------------------------------


def _nonblank(value: str | None) -> bool:
    return value is not None and bool(str(value).strip())


def _average(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return (sum(values, Decimal(0)) / Decimal(len(values))).quantize(
        FOUR_PLACES, rounding=ROUND_HALF_UP
    )


def _range(values: list[Decimal]) -> int | None:
    if not values:
        return None
    return int(max(values) - min(values))

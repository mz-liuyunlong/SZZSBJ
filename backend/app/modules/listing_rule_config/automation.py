"""WFS Listing lifecycle auto-evaluation, opt-in publication and immutable audit.

This is independent from the Listing profitability grade publisher.  It uses
Los Angeles daily WFS facts, sales facts and successful Walmart observations.
Missing evidence is unknown, never a zero-sales/healthy-monitor assumption.
Manual lifecycle, clearance and archive states have higher authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.modules.clearance.lifecycle import can_resume_lifecycle
from app.modules.data_pages.models import (
    DailySalesItemDayMart,
    ListingArchiveState,
    ListingManagementCurrentMart,
    WalmartListingInventoryDailyFact,
)
from app.modules.listing_rule_config.evaluation import BusinessDay, lifecycle_listing
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig
from app.modules.walmart_monitor.models import (
    RawWalmartMonitorEvent,
    StandardizedWalmartMonitorListingObservation,
)

LA = ZoneInfo("America/Los_Angeles")
PROTECTED = frozenset({"测品期", "打品期", "清货期", "已归档"})
AUTO_STAGES = frozenset({"启动期", "上升期", "稳定期", "下滑期", "断货期", "修复期"})
REQUIRED_TABLES = (
    "listing_wfs_first_stock_la_locked",
    "biz_listing_lifecycle_manual_states",
    "biz_listing_lifecycle_auto_history",
    "biz_listing_lifecycle_auto_runs",
)


@dataclass(frozen=True)
class LifecycleDecision:
    stage: str | None
    reason: str
    valid_stock_days_30: int = 0
    consecutive_low_stock_days: int = 0
    evidence_complete: bool = False
    first_positive_date_la: date | None = None


@dataclass(frozen=True)
class LifecycleBatchOutcome:
    examined: int
    updated: int
    unchanged: int
    skipped: int
    skipped_reasons: dict[str, int]
    cutoff_la: date


def _safe_monitor_observation(
    row: StandardizedWalmartMonitorListingObservation,
    *,
    has_strikethrough: bool | None = None,
) -> tuple[bool | None, bool | None]:
    """NORMAL means a visible purchase button, not proof of OUR Buy Box."""
    price_abnormal = None
    if has_strikethrough is False:
        # The successful RAW explicitly says there is no strikethrough price.
        # Do not fall back to old ERP pricing evidence.
        price_abnormal = True
    elif row.strike_price_amount is not None and row.sale_price_amount is not None:
        price_abnormal = row.strike_price_amount <= row.sale_price_amount
    status = (row.buybox_status or "").strip().upper()
    if status in {"LOST", "NOT_OWNED", "NOT_FOUND", "SECONDARY", "OTHER", "未拥有", "未拥有购物车"}:
        buybox_abnormal = True
    elif status in {"PRIMARY", "OWNED", "WON", "WINNING", "拥有"}:
        buybox_abnormal = False
    else:
        # NORMAL means a functioning purchase box, not seller ownership proof.
        # NOT_FOUND is a verified purchase-box absence (abnormal, not proof of loss).
        buybox_abnormal = None
    return price_abnormal, buybox_abnormal


def decide_lifecycle(
    *,
    previous_stage: str | None,
    first_positive: date | None,
    cutoff: date,
    days: list[BusinessDay],
    config: ListingGradeRuleConfig,
    stockout_previous_stage: str | None = None,
    stockout_days_before_recovery: int | None = None,
    repair_stock_valid_days: int | None = None,
    repair_reasons: tuple[str, ...] = (),
    first_positive_source: str = "wfs_daily_observation",
) -> LifecycleDecision:
    """Conservative initial state and existing 4-week state machine."""
    if previous_stage in PROTECTED:
        return LifecycleDecision(None, "WORKFLOW_STAGE_PROTECTED")
    if first_positive is None or first_positive > cutoff:
        return LifecycleDecision(None, "FIRST_WFS_POSITIVE_NOT_VERIFIED")
    today = next((row for row in days if row.day == cutoff), None)
    if today is None or today.wfs_qty is None:
        return LifecycleDecision(None, "CUTOFF_WFS_SNAPSHOT_MISSING")
    if previous_stage is not None and previous_stage not in AUTO_STAGES:
        return LifecycleDecision(None, "UNRECOGNIZED_EXISTING_STAGE")

    baseline = previous_stage or "启动期"
    result = lifecycle_listing(
        cutoff=cutoff,
        previous_stage=baseline,
        days=days,
        first_effective_stock=True,
        config=config,
        stockout_previous_stage=stockout_previous_stage,
        stockout_days_before_recovery=stockout_days_before_recovery,
        repair_stock_valid_days=repair_stock_valid_days,
        repair_reasons=repair_reasons,
    )
    if previous_stage is None and first_positive_source == "historical_wfs_snapshot":
        # Migration 0072 backfills the EARLIEST OBSERVED positive WFS date, not
        # the real launch date.  A legacy Listing must not be labelled newly
        # launched from this truncated historical observation.
        # Independently proven trends, stockout and monitor repairs may publish.
        if result.evidence_complete and result.stage in {
            "上升期",
            "稳定期",
            "下滑期",
            "断货期",
            "修复期",
        }:
            return LifecycleDecision(
                result.stage,
                "HISTORICAL_WFS_TREND_ONLY:" + result.reason,
                result.valid_stock_days_30,
                result.consecutive_stockout,
                True,
                first_positive,
            )
        return LifecycleDecision(
            None,
            "HISTORICAL_FIRST_WFS_NOT_LAUNCH_VERIFIED",
            result.valid_stock_days_30,
            result.consecutive_stockout,
            False,
            first_positive,
        )
    if result.evidence_complete:
        return LifecycleDecision(
            result.stage,
            result.reason,
            result.valid_stock_days_30,
            result.consecutive_stockout,
            True,
            first_positive,
        )
    if previous_stage is None:
        # Never label a currently zero-stock Listing as newly launched when
        # the history is too sparse to prove a seven-day stockout.
        if today.wfs_qty <= 0:
            return LifecycleDecision(
                None,
                "ZERO_WFS_AND_STOCKOUT_EVIDENCE_INCOMPLETE",
                result.valid_stock_days_30,
                result.consecutive_stockout,
                False,
                first_positive,
            )
        # Launch is known and cutoff WFS stock is positive; missing daily
        # sales forbids growth/stability but not a conservative starting stage.
        return LifecycleDecision(
            "启动期",
            "首次有货已核实；趋势数据尚不足，初始化为启动期",
            result.valid_stock_days_30,
            result.consecutive_stockout,
            True,
            first_positive,
        )
    return LifecycleDecision(
        None,
        "EVIDENCE_INCOMPLETE:" + result.reason,
        result.valid_stock_days_30,
        result.consecutive_stockout,
        False,
        first_positive,
    )


def verify_schema(session: Session) -> None:
    """Publication fails closed unless ALL previously approved migrations exist."""
    missing = [
        name
        for name in REQUIRED_TABLES
        if session.scalar(text("SELECT to_regclass(:name)"), {"name": "public." + name}) is None
    ]
    if missing:
        raise RuntimeError("LIFECYCLE_SCHEMA_NOT_READY:" + ",".join(missing))


def _first_wfs_date(
    session: Session,
    listing: ListingManagementCurrentMart,
) -> tuple[date | None, str | None]:
    """Return first OBSERVED date and provenance; never imply historical launch."""
    row = (
        session.execute(
            text("""
        SELECT first_wfs_available_date_la, date_source
        FROM public.listing_wfs_first_stock_la_locked
        WHERE source_account_ref=:account AND store_id=:store AND item_id=:item
    """),
            {
                "account": listing.source_account_ref,
                "store": listing.store_id,
                "item": listing.item_id,
            },
        )
        .mappings()
        .first()
    )
    if row is None:
        return None, None
    return row["first_wfs_available_date_la"], row["date_source"]


def _manual_override_exists(session: Session, listing: ListingManagementCurrentMart) -> bool:
    return bool(
        session.scalar(
            text("""
        SELECT EXISTS (
          SELECT 1 FROM public.biz_listing_lifecycle_manual_states
          WHERE source_account_ref=:account AND store_id=:store AND item_id=:item
        )
    """),
            {
                "account": listing.source_account_ref,
                "store": listing.store_id,
                "item": listing.item_id,
            },
        )
    )


def _stockout_history(
    session: Session, listing: ListingManagementCurrentMart
) -> tuple[str | None, tuple[str, ...], date | None]:
    row = (
        session.execute(
            text("""
        SELECT previous_stage, reason, cutoff_date_la
        FROM public.biz_listing_lifecycle_auto_history
        WHERE source_account_ref=:account AND store_id=:store AND item_id=:item
          AND new_stage = CASE WHEN :stage='断货期' THEN '断货期' ELSE '修复期' END
        ORDER BY cutoff_date_la DESC
        LIMIT 1
    """),
            {
                "account": listing.source_account_ref,
                "store": listing.store_id,
                "item": listing.item_id,
                "stage": listing.lifecycle_status,
            },
        )
        .mappings()
        .first()
    )
    if not row:
        return None, (), None
    reason = str(row["reason"] or "")
    reasons = (
        ("stockout",)
        if "断货" in reason
        else (
            ("buybox_abnormal",)
            if "购物车" in reason
            else (("strike_price_abnormal",) if "划线价" in reason else ())
        )
    )
    return row["previous_stage"], reasons, row["cutoff_date_la"]


# LIFECYCLE_ITEM_DAILY_SALES_MULTI_MSKU_V1
def _daily_item_sales(samples: list[tuple[str | None, Decimal]]) -> Decimal | None:
    """Sum distinct MSKU sales contributing to the same scoped Item/day.

    The caller filters by source account, store, Item ID and LA date first.
    A missing row means unknown, not zero. Repeated or null MSKU identity
    among multiple rows is ambiguous, so do not infer a sales total.
    """
    if not samples:
        return None
    if any(qty is None or qty < 0 for _, qty in samples):
        return None
    if len(samples) == 1:
        return samples[0][1]
    msuks = [msku.strip() if isinstance(msku, str) else "" for msku, _ in samples]
    if not all(msuks) or len(msuks) != len(set(msuks)):
        return None
    return sum((qty for _, qty in samples), Decimal("0"))


def evaluate_listing(
    session: Session,
    listing: ListingManagementCurrentMart,
    *,
    cutoff: date,
    config: ListingGradeRuleConfig,
) -> LifecycleDecision:
    """Read-only evaluation. Item identity intentionally ignores mutable MSKU."""
    # LIFECYCLE_WFS_INVENTORY_ONLY_V1: actual daily WFS stock evidence is the
    # eligibility signal. ERP fulfillment_type may be stale or different.
    # Even if today's stock is zero, a previously positive WFS series must
    # remain eligible for stockout and recovery evaluation.
    if listing.lifecycle_status in PROTECTED:
        if listing.lifecycle_status != "清货期" or not can_resume_lifecycle(session, listing):
            return LifecycleDecision(None, "WORKFLOW_STAGE_PROTECTED")
    if _manual_override_exists(session, listing):
        return LifecycleDecision(None, "MANUAL_STAGE_PROTECTED")
    archived = session.scalar(
        select(ListingArchiveState.is_archived).where(
            ListingArchiveState.listing_id == listing.id,
        )
    )
    if archived:
        return LifecycleDecision(None, "ARCHIVED_PROTECTED")

    first_positive, first_positive_source = _first_wfs_date(session, listing)
    if first_positive is None or first_positive > cutoff:
        return LifecycleDecision(None, "FIRST_WFS_POSITIVE_NOT_VERIFIED")
    start = cutoff - timedelta(days=29)
    common = (
        WalmartListingInventoryDailyFact.source_account_ref == listing.source_account_ref,
        WalmartListingInventoryDailyFact.store_id == listing.store_id,
        WalmartListingInventoryDailyFact.item_id == listing.item_id,
    )
    stocks = list(
        session.scalars(
            select(WalmartListingInventoryDailyFact).where(
                *common,
                WalmartListingInventoryDailyFact.snapshot_date_la.between(start, cutoff),
            )
        ).all()
    )
    stock_by_day = {row.snapshot_date_la: row.wfs_available_quantity for row in stocks}

    sales = list(
        session.scalars(
            select(DailySalesItemDayMart).where(
                DailySalesItemDayMart.source_account_ref == listing.source_account_ref,
                DailySalesItemDayMart.store_id == listing.store_id,
                DailySalesItemDayMart.item_id == listing.item_id,
                DailySalesItemDayMart.business_date_la.between(start, cutoff),
            )
        ).all()
    )
    # Account/store/Item/date are filtered above. Distinct MSKUs are
    # independent daily contributions; duplicate or missing identities
    # remain unknown rather than silently double counted.
    sales_by_day: dict[date, list[tuple[str | None, Decimal]]] = {}
    for item in sales:
        sales_by_day.setdefault(item.business_date_la, []).append((item.msku, item.sales_qty))

    monitor_start = datetime.combine(start, time.min, LA).astimezone(UTC)
    monitor_end = datetime.combine(cutoff + timedelta(days=1), time.min, LA).astimezone(UTC)
    monitors = list(
        session.scalars(
            select(StandardizedWalmartMonitorListingObservation)
            .where(
                StandardizedWalmartMonitorListingObservation.source_account_ref
                == listing.source_account_ref,
                StandardizedWalmartMonitorListingObservation.store_id == listing.store_id,
                StandardizedWalmartMonitorListingObservation.item_id == listing.item_id,
                func.lower(StandardizedWalmartMonitorListingObservation.monitor_outcome).in_(
                    ("success", "check_ok")
                ),
                StandardizedWalmartMonitorListingObservation.captured_at >= monitor_start,
                StandardizedWalmartMonitorListingObservation.captured_at < monitor_end,
            )
            .order_by(StandardizedWalmartMonitorListingObservation.captured_at)
        ).all()
    )
    monitor_by_day = {row.captured_at.astimezone(LA).date(): row for row in monitors}
    raw_ids = {row.raw_event_id for row in monitors}
    raw_events = (
        list(
            session.scalars(
                select(RawWalmartMonitorEvent).where(RawWalmartMonitorEvent.id.in_(raw_ids))
            ).all()
        )
        if raw_ids
        else []
    )
    parsed_by_id: dict[UUID, dict] = {}
    for raw in raw_events:
        payload = raw.payload_json or {}
        observation = payload.get("final_observation") or {}
        parsed = observation.get("parsed_result") or {}
        parsed_by_id[raw.id] = parsed if isinstance(parsed, dict) else {}

    days = []
    for i in range(30):
        d = start + timedelta(days=i)
        monitor = monitor_by_day.get(d)
        has_strike = None
        if monitor is not None:
            parsed = parsed_by_id.get(monitor.raw_event_id, {})
            diagnostic = parsed.get("diagnostic") or {}
            signal = diagnostic.get("matchedSignal") if isinstance(diagnostic, dict) else None
            if signal is not None and signal != "ITEM_" + listing.item_id:
                # One provider response cannot prove a different Item ID.
                monitor = None
            elif isinstance(parsed.get("hasStrikethrough"), bool):
                has_strike = parsed["hasStrikethrough"]
        price_bad, buybox_bad = (
            _safe_monitor_observation(monitor, has_strikethrough=has_strike)
            if monitor is not None
            else (None, None)
        )
        sale_samples = sales_by_day.get(d, [])
        days.append(
            BusinessDay(
                day=d,
                wfs_qty=stock_by_day.get(d),
                sales_qty=_daily_item_sales(sale_samples),
                strike_price_abnormal=price_bad,
                buybox_abnormal=buybox_bad,
            )
        )

    stockout_previous = None
    stockout_days = None
    repair_days = None
    repair_reasons: tuple[str, ...] = ()
    if listing.lifecycle_status in {"断货期", "修复期"}:
        stockout_previous, repair_reasons, entered_at = _stockout_history(session, listing)
        if listing.lifecycle_status == "断货期":
            if stockout_previous is None:
                return LifecycleDecision(None, "STOCKOUT_PREVIOUS_STAGE_UNKNOWN")
            if (
                stock_by_day.get(cutoff) is not None
                and stock_by_day[cutoff] > config.inventory_repair.low_stock_max_units
            ):
                previous_day = cutoff - timedelta(days=1)
                streak = 0
                while (
                    previous_day in stock_by_day
                    and stock_by_day[previous_day] is not None
                    and stock_by_day[previous_day] <= config.inventory_repair.low_stock_max_units
                ):
                    streak += 1
                    previous_day -= timedelta(days=1)
                stockout_days = streak if streak > 0 else None
        else:
            if entered_at is None or not repair_reasons:
                return LifecycleDecision(None, "REPAIR_HISTORY_UNKNOWN")
            if "stockout" in repair_reasons:
                repair_days = sum(
                    1
                    for day in days
                    if day.day > entered_at
                    and day.wfs_qty is not None
                    and day.wfs_qty > config.inventory_repair.low_stock_max_units
                    and day.sales_qty is not None
                )
    return decide_lifecycle(
        previous_stage=(
            None
            if listing.lifecycle_status == "清货期" and can_resume_lifecycle(session, listing)
            else listing.lifecycle_status
        ),
        first_positive=first_positive,
        cutoff=cutoff,
        days=days,
        config=config,
        stockout_previous_stage=stockout_previous,
        stockout_days_before_recovery=stockout_days,
        repair_stock_valid_days=repair_days,
        repair_reasons=repair_reasons,
        first_positive_source=first_positive_source or "unknown",
    )


def process_lifecycle_batch(
    session: Session,
    *,
    cutoff: date,
    config: ListingGradeRuleConfig,
    rule_version: int,
    dry_run: bool = True,
    max_listings: int | None = None,
) -> LifecycleBatchOutcome:
    """Evaluate all WFS Listing ids, publish ONLY with dry_run=False.

    One Listing row lock is held during its decision and update, serializing
    against manual editing's own SELECT ... FOR UPDATE on the same MART row.
    """
    verify_schema(session)
    # WFS scope is defined by positive inventory FACT history, not the ERP
    # fulfillment label.  Historical stock evidence includes currently
    # zero-stock items, which must still be evaluated for stockout/recovery.
    wfs_stock_evidence = (
        select(WalmartListingInventoryDailyFact.id)
        .where(
            WalmartListingInventoryDailyFact.source_account_ref
            == ListingManagementCurrentMart.source_account_ref,
            WalmartListingInventoryDailyFact.store_id == ListingManagementCurrentMart.store_id,
            WalmartListingInventoryDailyFact.item_id == ListingManagementCurrentMart.item_id,
            WalmartListingInventoryDailyFact.snapshot_date_la <= cutoff,
            WalmartListingInventoryDailyFact.wfs_available_quantity > 0,
        )
        .exists()
    )
    candidates = (
        select(ListingManagementCurrentMart.id)
        .where(
            wfs_stock_evidence,
        )
        .order_by(ListingManagementCurrentMart.id)
    )
    if max_listings is not None:
        candidates = candidates.limit(max_listings)
    ids = list(session.scalars(candidates).all())
    # A new transaction per Listing makes progress recoverable and prevents
    # a slow batch from locking the entire Listing table.
    session.commit()
    processed = updated = unchanged = skipped = 0
    reasons: dict[str, int] = {}
    for listing_id in ids:
        try:
            with session.begin():
                listing = session.scalar(
                    select(ListingManagementCurrentMart)
                    .where(
                        ListingManagementCurrentMart.id == listing_id,
                    )
                    .with_for_update()
                )
                if listing is None:
                    continue
                result = evaluate_listing(session, listing, cutoff=cutoff, config=config)
                processed += 1
                if result.stage is None:
                    skipped += 1
                    reasons[result.reason] = reasons.get(result.reason, 0) + 1
                    continue
                if result.stage == listing.lifecycle_status:
                    unchanged += 1
                    continue
                if dry_run:
                    updated += 1
                    continue
                # Exactly one automatic change per business date; historical
                # rows are immutable and retries cannot duplicate events.
                already = session.scalar(
                    text("""
                    SELECT EXISTS (SELECT 1 FROM biz_listing_lifecycle_auto_history
                    WHERE source_account_ref=:account AND store_id=:store
                      AND item_id=:item AND cutoff_date_la=:cutoff)
                """),
                    {
                        "account": listing.source_account_ref,
                        "store": listing.store_id,
                        "item": listing.item_id,
                        "cutoff": cutoff,
                    },
                )
                if already:
                    skipped += 1
                    reasons["ALREADY_PUBLISHED_FOR_CUTOFF"] = (
                        reasons.get("ALREADY_PUBLISHED_FOR_CUTOFF", 0) + 1
                    )
                    continue
                session.execute(
                    text("""
                    INSERT INTO biz_listing_lifecycle_auto_history (
                      id, source_account_ref, store_id, item_id, listing_id,
                      msku, cutoff_date_la, previous_stage, new_stage, reason,
                      valid_stock_days_30, consecutive_low_stock_days,
                      first_positive_date_la, rule_version, created_at
                    ) VALUES (
                      :id, :account, :store, :item, :listing, :msku, :cutoff,
                      :previous, :new, :reason, :valid30, :streak,
                      :first_positive, :version, :created
                    )
                """),
                    {
                        "id": uuid4(),
                        "account": listing.source_account_ref,
                        "store": listing.store_id,
                        "item": listing.item_id,
                        "listing": listing.id,
                        "msku": listing.msku,
                        "cutoff": cutoff,
                        "previous": listing.lifecycle_status,
                        "new": result.stage,
                        "reason": result.reason,
                        "valid30": result.valid_stock_days_30,
                        "streak": result.consecutive_low_stock_days,
                        "first_positive": result.first_positive_date_la,
                        "version": rule_version,
                        "created": datetime.now(UTC),
                    },
                )
                listing.lifecycle_status = result.stage
                updated += 1
        except Exception:
            session.rollback()
            raise
    return LifecycleBatchOutcome(processed, updated, unchanged, skipped, reasons, cutoff)

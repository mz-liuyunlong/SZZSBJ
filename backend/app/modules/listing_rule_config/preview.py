"""Read-only, provisional Listing evaluation from existing daily MARTs.

This module intentionally does not initialize lifecycle state, confirm upstream
advertising, publish grades, or persist any calculation.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.data_pages.models import (
    DailySalesItemDayMart,
    ListingArchiveState,
    ListingManagementCurrentMart,
    WalmartAdItemSpDailyFact,
    WalmartListingInventoryDailyFact,
)
from app.modules.integration_sync.models import IntegrationSyncRun, IntegrationSyncRunEvent
from app.modules.listing_rule_config.evaluation import (
    BusinessDay,
    FinancialDay,
    grade_listing,
    lifecycle_listing,
)
from app.modules.listing_rule_config.models import (
    ListingEvaluationSnapshot,
    ListingGradeRuleVersion,
    ListingLifecycleAdjustment,
)
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig
from app.modules.walmart_monitor.models import StandardizedWalmartMonitorListingObservation

ZERO = Decimal("0")
LOS_ANGELES = ZoneInfo("America/Los_Angeles")


def lifecycle_allows_grade(
    stage: str | None,
    *,
    archived: bool,
    config: ListingGradeRuleConfig,
) -> bool:
    return not archived and stage in config.included_stages


class ListingEvaluationPreview(BaseModel):
    """Diagnostic candidate only; no result is a published lifecycle or grade."""

    listing_id: UUID
    cutoff_la: date
    current_lifecycle: str | None
    current_grade: str | None
    lifecycle_evidence_reason: str | None = None
    valid_stock_days_30: int = 0
    grade_publication_status: str = "upstream_unconfirmed"
    lifecycle_candidate: str | None = None
    grade_candidate: str | None = None
    valid_short: int = 0
    valid_medium: int = 0
    weighted_margin_percent: Decimal | None = None
    observed_stock_days_7: int = 0
    low_stock_days_7: int = 0
    prior_effective_stock: bool = False
    currently_archived: bool = False
    rule_version: int = 0
    rule_source: str = "default"
    missing_evidence: list[str] = Field(default_factory=list)
    published: bool = False


def basic_financial_candidate(
    days: list[DailySalesItemDayMart],
    *,
    cutoff: date,
    config: ListingGradeRuleConfig,
    unconfirmed_account_ad_days: frozenset[date],
) -> tuple[str | None, int, int, Decimal | None]:
    """Diagnostic margin *only*, never proof that Daily Sales finished syncing.

    The MART contains no trusted zero-business-day publication marker: absent
    rows do not become zero dates. Missing currency is excluded, not assumed USD.
    """
    result = grade_listing(
        cutoff=cutoff,
        stage=None,
        days=[
            FinancialDay(
                day=day.business_date_la,
                sales=day.sales_amount if day.sales_amount is not None else ZERO,
                profit=day.gross_profit_amount,
                cost_status=day.cost_status,
                missing_cost_codes=tuple(day.missing_cost_codes_json or ()),
                upstream_confirmed=(
                    day.sales_amount is not None
                    and day.sales_currency_code == "USD"
                    and day.gross_profit_currency_code == "USD"
                ),
            )
            for day in days
        ],
        unconfirmed_account_ad_days=unconfirmed_account_ad_days,
        config=config,
        ignore_stage=True,
    )
    grade = result.grade if result.grade in {"A", "B", "C", "D"} else None
    return grade, result.valid_short, result.valid_medium, result.weighted_margin


def stockout_candidate(
    inventory: list[WalmartListingInventoryDailyFact],
    *,
    cutoff: date,
    prior_effective_stock: bool,
    fulfillment_type: str | None,
    currently_archived: bool,
    consecutive_days: int = 7,
) -> tuple[str | None, int, int]:
    """Never infer WFS stockout from seller-fulfilled or missing snapshots."""
    since = cutoff - timedelta(days=consecutive_days - 1)
    recent = {
        row.snapshot_date_la: row for row in inventory if since <= row.snapshot_date_la <= cutoff
    }
    observed = sum(row.wfs_available_quantity is not None for row in recent.values())
    zero_days = sum(
        row.wfs_available_quantity is not None and row.wfs_available_quantity == 0
        for row in recent.values()
    )
    candidate = (
        "断货期"
        if (
            fulfillment_type == "1"
            and not currently_archived
            and prior_effective_stock
            and observed == consecutive_days
            and zero_days == consecutive_days
        )
        else None
    )
    return candidate, observed, zero_days


def archive_has_post_cutoff_event(
    *, archived_at: datetime | None, restored_at: datetime | None, cutoff: date
) -> bool:
    """Current archive state cannot prove a historical cutoff after a later transition."""
    return any(
        timestamp is not None and timestamp.astimezone(LOS_ANGELES).date() > cutoff
        for timestamp in (archived_at, restored_at)
    )


class ListingEvaluationPreviewService:
    """Account-scoped, exact-identity, read-only diagnostic for one Listing."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._unconfirmed_ad_days_cache: dict[tuple[str, date, int], frozenset[date]] = {}

    def _stage_entries(
        self, listings: Sequence[ListingManagementCurrentMart], *, cutoff: date
    ) -> dict[UUID, tuple[str | None, date | None, tuple[str, ...]]]:
        """Use only immutable, non-reverted published transitions after rollout."""
        target_ids = [row.id for row in listings if row.lifecycle_status in {"断货期", "修复期"}]
        if not target_ids:
            return {}
        entries = self.session.scalars(
            select(ListingEvaluationSnapshot)
            .where(
                ListingEvaluationSnapshot.listing_id.in_(target_ids),
                ListingEvaluationSnapshot.published.is_(True),
                ListingEvaluationSnapshot.reverted_at.is_(None),
                ListingEvaluationSnapshot.cutoff_date_la <= cutoff,
                ListingEvaluationSnapshot.lifecycle_candidate.in_(("断货期", "修复期")),
                ListingEvaluationSnapshot.current_lifecycle.is_distinct_from(
                    ListingEvaluationSnapshot.lifecycle_candidate
                ),
            )
            .order_by(
                ListingEvaluationSnapshot.listing_id,
                ListingEvaluationSnapshot.cutoff_date_la.desc(),
            )
        ).all()
        latest: dict[tuple[UUID, str], ListingEvaluationSnapshot] = {}
        for row in entries:
            latest.setdefault((row.listing_id, row.lifecycle_candidate), row)
        result: dict[UUID, tuple[str | None, date | None, tuple[str, ...]]] = {}
        for listing in listings:
            stockout = latest.get((listing.id, "断货期"))
            repair = latest.get((listing.id, "修复期"))
            repair_reasons: tuple[str, ...] = ()
            if repair is not None:
                repair_reasons = {
                    "长期断货恢复，进入修复验收": ("stockout",),
                    "划线价异常持续超过门槛": ("strike_price_abnormal",),
                    "购物车异常持续超过门槛": ("buybox_abnormal",),
                }.get(repair.lifecycle_evidence_reason, ())
            result[listing.id] = (
                stockout.current_lifecycle if stockout is not None else None,
                repair.cutoff_date_la if repair is not None else None,
                repair_reasons,
            )
        return result

    def _confirmed_lifecycle_states(
        self, listings: Sequence[ListingManagementCurrentMart], *, cutoff: date
    ) -> tuple[set[UUID], set[UUID]]:
        """Current state is historical evidence only when its event predates cutoff."""
        tracked = {row.id: row.lifecycle_status for row in listings if row.lifecycle_status}
        if not tracked:
            return set(), set()
        cutoff_end = datetime.combine(
            cutoff + timedelta(days=1), datetime.min.time(), LOS_ANGELES
        ).astimezone(UTC)
        approved = self.session.execute(
            select(
                ListingLifecycleAdjustment.listing_id,
                ListingLifecycleAdjustment.requested_stage,
            )
            .where(
                ListingLifecycleAdjustment.listing_id.in_(tracked),
                ListingLifecycleAdjustment.status == "approved",
                ListingLifecycleAdjustment.decided_at < cutoff_end,
            )
            .order_by(
                ListingLifecycleAdjustment.listing_id,
                ListingLifecycleAdjustment.decided_at.desc(),
            )
        ).all()
        last_manual: dict[UUID, str] = {}
        for listing_id, stage in approved:
            last_manual.setdefault(listing_id, stage)
        confirmed = {
            listing_id for listing_id, stage in last_manual.items() if tracked[listing_id] == stage
        }
        manual = set(confirmed)
        prior = self.session.execute(
            select(
                ListingEvaluationSnapshot.listing_id, ListingEvaluationSnapshot.lifecycle_candidate
            )
            .where(
                ListingEvaluationSnapshot.listing_id.in_(tracked),
                ListingEvaluationSnapshot.published.is_(True),
                ListingEvaluationSnapshot.reverted_at.is_(None),
                ListingEvaluationSnapshot.published_at < cutoff_end,
            )
            .order_by(
                ListingEvaluationSnapshot.listing_id,
                ListingEvaluationSnapshot.published_at.desc(),
            )
        ).all()
        last_published: dict[UUID, str | None] = {}
        for listing_id, stage in prior:
            last_published.setdefault(listing_id, stage)
        confirmed.update(
            listing_id
            for listing_id, stage in last_published.items()
            if listing_id not in last_manual and tracked[listing_id] == stage
        )
        return confirmed, manual

    def _confirmed_daily_sales_days(
        self, accounts: set[str], *, start: date, cutoff: date
    ) -> dict[str, set[date]]:
        date_text = IntegrationSyncRunEvent.safe_details["business_date"].astext
        rows = self.session.execute(
            select(
                IntegrationSyncRun.source_account_ref,
                date_text,
                IntegrationSyncRunEvent.message_code,
                IntegrationSyncRunEvent.occurred_at,
                IntegrationSyncRun.status,
            )
            .join(IntegrationSyncRun, IntegrationSyncRun.id == IntegrationSyncRunEvent.run_id)
            .where(
                IntegrationSyncRun.source_account_ref.in_(accounts),
                IntegrationSyncRun.interface_key == "saleStatPageList",
                IntegrationSyncRunEvent.message_code.in_(
                    ("SYNC_SALESTAT_DAY_PENDING", "SYNC_SALESTAT_DAY_VALIDATED")
                ),
                date_text.between(start.isoformat(), cutoff.isoformat()),
            )
            .order_by(
                IntegrationSyncRun.source_account_ref,
                date_text,
                IntegrationSyncRunEvent.occurred_at.desc(),
                IntegrationSyncRunEvent.id.desc(),
            )
        ).all()
        confirmed: dict[str, set[date]] = {account: set() for account in accounts}
        seen: set[tuple[str, date]] = set()
        for account, day_text, message_code, occurred_at, run_status in rows:
            business_day = date.fromisoformat(day_text)
            key = (account, business_day)
            if key in seen:
                continue
            seen.add(key)
            if (
                message_code == "SYNC_SALESTAT_DAY_VALIDATED"
                and run_status == "succeeded"
                and occurred_at.astimezone(LOS_ANGELES).date() > business_day
            ):
                confirmed[account].add(business_day)
        return confirmed

    def _confirmed_wfs_days(
        self, accounts: set[str], *, start: date, cutoff: date
    ) -> dict[str, set[date]]:
        """Only finalized, complete Listing captures can certify a WFS business day."""
        date_text = IntegrationSyncRunEvent.safe_details["business_date"].astext
        rows = self.session.execute(
            select(IntegrationSyncRun.source_account_ref, date_text)
            .join(IntegrationSyncRun, IntegrationSyncRun.id == IntegrationSyncRunEvent.run_id)
            .where(
                IntegrationSyncRun.source_account_ref.in_(accounts),
                IntegrationSyncRun.interface_key == "walmartListingList",
                IntegrationSyncRun.status == "succeeded",
                IntegrationSyncRunEvent.message_code == "SYNC_WFS_INVENTORY_DAY_VALIDATED",
                date_text.between(start.isoformat(), cutoff.isoformat()),
            )
        ).all()
        confirmed: dict[str, set[date]] = {account: set() for account in accounts}
        for account, day_text in rows:
            if account not in confirmed or not day_text:
                continue
            try:
                confirmed[account].add(date.fromisoformat(day_text))
            except ValueError:
                continue
        return confirmed

    def _confirmed_ad_report_days(
        self, accounts: set[str], *, start: date, cutoff: date
    ) -> dict[str, set[date]]:
        """A positive ad sum is usable only after the account-day report was captured."""
        date_text = IntegrationSyncRunEvent.safe_details["business_date"].astext
        rows = self.session.execute(
            select(
                IntegrationSyncRun.source_account_ref,
                date_text,
                IntegrationSyncRunEvent.message_code,
                IntegrationSyncRunEvent.occurred_at,
                IntegrationSyncRun.status,
            )
            .join(IntegrationSyncRun, IntegrationSyncRun.id == IntegrationSyncRunEvent.run_id)
            .where(
                IntegrationSyncRun.source_account_ref.in_(accounts),
                IntegrationSyncRun.interface_key == "walmartAdItemSpList",
                IntegrationSyncRunEvent.message_code.in_(
                    ("SYNC_AD_REPORT_DAY_PENDING", "SYNC_AD_REPORT_DAY_VALIDATED")
                ),
                date_text.between(start.isoformat(), cutoff.isoformat()),
            )
            .order_by(
                IntegrationSyncRun.source_account_ref,
                date_text,
                IntegrationSyncRunEvent.occurred_at.desc(),
                IntegrationSyncRunEvent.id.desc(),
            )
        ).all()
        confirmed: dict[str, set[date]] = {account: set() for account in accounts}
        seen: set[tuple[str, date]] = set()
        for account, day_text, message_code, occurred_at, run_status in rows:
            if account not in confirmed or not day_text:
                continue
            try:
                business_day = date.fromisoformat(day_text)
            except ValueError:
                continue
            key = (account, business_day)
            if key in seen:
                continue
            seen.add(key)
            if (
                message_code == "SYNC_AD_REPORT_DAY_VALIDATED"
                and run_status == "succeeded"
                and occurred_at.astimezone(LOS_ANGELES).date() > business_day
            ):
                confirmed[account].add(business_day)
        return confirmed

    def _unconfirmed_account_ad_days(
        self,
        accounts: set[str],
        *,
        cutoff: date,
        window_days: int,
        confirmed_sales_days: dict[str, set[date]] | None = None,
    ) -> dict[str, frozenset[date]]:
        missing = {
            account
            for account in accounts
            if (account, cutoff, window_days) not in self._unconfirmed_ad_days_cache
        }
        if missing:
            start = cutoff - timedelta(days=window_days - 1)
            rows = self.session.execute(
                select(
                    WalmartAdItemSpDailyFact.source_account_ref,
                    WalmartAdItemSpDailyFact.business_date_la,
                    func.sum(func.coalesce(WalmartAdItemSpDailyFact.ad_spend_amount, ZERO)),
                )
                .where(
                    WalmartAdItemSpDailyFact.source_account_ref.in_(missing),
                    WalmartAdItemSpDailyFact.business_date_la.between(start, cutoff),
                )
                .group_by(
                    WalmartAdItemSpDailyFact.source_account_ref,
                    WalmartAdItemSpDailyFact.business_date_la,
                )
            ).all()
            days_in_window = {start + timedelta(days=offset) for offset in range(window_days)}
            positive_by_account: dict[str, set[date]] = {account: set() for account in missing}
            for account, business_day, total in rows:
                if total is not None and total > ZERO:
                    positive_by_account[account].add(business_day)
            confirmed_by_account = (
                confirmed_sales_days
                if confirmed_sales_days is not None
                else self._confirmed_daily_sales_days(missing, start=start, cutoff=cutoff)
            )
            confirmed_ad_days = self._confirmed_ad_report_days(missing, start=start, cutoff=cutoff)
            for account in missing:
                unconfirmed_days = days_in_window - (
                    positive_by_account[account]
                    & confirmed_by_account[account]
                    & confirmed_ad_days[account]
                )
                self._unconfirmed_ad_days_cache[(account, cutoff, window_days)] = frozenset(
                    unconfirmed_days
                )
        return {
            account: self._unconfirmed_ad_days_cache[(account, cutoff, window_days)]
            for account in accounts
        }

    def evaluate(
        self,
        *,
        listing_id: UUID,
        account_refs: frozenset[str],
        cutoff: date,
        config: ListingGradeRuleConfig | None = None,
        rule_version: int | None = None,
    ) -> ListingEvaluationPreview:
        listing = self.session.scalar(
            select(ListingManagementCurrentMart).where(
                ListingManagementCurrentMart.id == listing_id,
                ListingManagementCurrentMart.source_account_ref.in_(account_refs),
            )
        )
        if listing is None:
            # Hidden records and unknown identifiers share the same response.
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)

        if config is None:
            now = datetime.now(UTC)
            version = self.session.scalar(
                select(ListingGradeRuleVersion)
                .where(ListingGradeRuleVersion.effective_from <= now)
                .order_by(ListingGradeRuleVersion.version.desc())
                .limit(1)
            )
            config = (
                ListingGradeRuleConfig.model_validate(version.config_json)
                if version is not None
                else ListingGradeRuleConfig()
            )
            rule_version = version.version if version is not None else 0
        elif rule_version is None:
            raise ValueError("rule_version is required when config is provided")

        start = cutoff - timedelta(days=max(30, config.medium_days) - 1)
        sales = list(
            self.session.scalars(
                select(DailySalesItemDayMart).where(
                    DailySalesItemDayMart.source_account_ref == listing.source_account_ref,
                    DailySalesItemDayMart.store_id == listing.store_id,
                    DailySalesItemDayMart.item_id == listing.item_id,
                    DailySalesItemDayMart.msku.is_not_distinct_from(listing.msku),
                    DailySalesItemDayMart.business_date_la.between(start, cutoff),
                )
            ).all()
        )
        stock = list(
            self.session.scalars(
                select(WalmartListingInventoryDailyFact).where(
                    WalmartListingInventoryDailyFact.source_account_ref
                    == listing.source_account_ref,
                    WalmartListingInventoryDailyFact.store_id == listing.store_id,
                    WalmartListingInventoryDailyFact.item_id == listing.item_id,
                    WalmartListingInventoryDailyFact.msku.is_not_distinct_from(listing.msku),
                    WalmartListingInventoryDailyFact.snapshot_date_la.between(
                        cutoff
                        - timedelta(
                            days=max(
                                30,
                                config.inventory_repair.long_stockout_days + 2,
                                config.inventory_repair.stockout_repair_valid_days,
                            )
                            - 1
                        ),
                        cutoff,
                    ),
                )
            ).all()
        )
        confirmed_wfs_days = self._confirmed_wfs_days(
            {listing.source_account_ref},
            start=cutoff
            - timedelta(
                days=max(
                    30,
                    config.inventory_repair.long_stockout_days + 2,
                    config.inventory_repair.stockout_repair_valid_days,
                )
                - 1
            ),
            cutoff=cutoff,
        )[listing.source_account_ref]
        stock = [row for row in stock if row.snapshot_date_la in confirmed_wfs_days]
        prior = self.session.scalar(
            select(WalmartListingInventoryDailyFact.snapshot_date_la)
            .where(
                WalmartListingInventoryDailyFact.source_account_ref == listing.source_account_ref,
                WalmartListingInventoryDailyFact.store_id == listing.store_id,
                WalmartListingInventoryDailyFact.item_id == listing.item_id,
                WalmartListingInventoryDailyFact.msku.is_not_distinct_from(listing.msku),
                WalmartListingInventoryDailyFact.snapshot_date_la
                < cutoff - timedelta(days=config.inventory_repair.stockout_consecutive_days - 1),
                WalmartListingInventoryDailyFact.wfs_available_quantity
                > config.inventory_repair.low_stock_max_units,
            )
            .limit(1)
        )
        if (
            prior is not None
            and prior
            not in self._confirmed_wfs_days(
                {listing.source_account_ref}, start=prior, cutoff=prior
            )[listing.source_account_ref]
        ):
            prior = None
        archive = self.session.scalar(
            select(ListingArchiveState).where(ListingArchiveState.listing_id == listing.id)
        )
        monitor_start = datetime.combine(start, datetime.min.time(), LOS_ANGELES).astimezone(UTC)
        monitor_end = datetime.combine(
            cutoff + timedelta(days=1),
            datetime.min.time(),
            LOS_ANGELES,
        ).astimezone(UTC)
        monitor_rows = list(
            self.session.scalars(
                select(StandardizedWalmartMonitorListingObservation)
                .where(
                    StandardizedWalmartMonitorListingObservation.source_account_ref
                    == listing.source_account_ref,
                    StandardizedWalmartMonitorListingObservation.store_id == listing.store_id,
                    StandardizedWalmartMonitorListingObservation.item_id == listing.item_id,
                    func.lower(StandardizedWalmartMonitorListingObservation.monitor_outcome)
                    == "success",
                    StandardizedWalmartMonitorListingObservation.captured_at >= monitor_start,
                    StandardizedWalmartMonitorListingObservation.captured_at < monitor_end,
                )
                .order_by(StandardizedWalmartMonitorListingObservation.captured_at)
            ).all()
        )
        confirmed_sales_days = self._confirmed_daily_sales_days(
            {listing.source_account_ref},
            start=cutoff - timedelta(days=max(30, config.medium_days) - 1),
            cutoff=cutoff,
        )
        confirmed_lifecycle, manual_lifecycle = self._confirmed_lifecycle_states(
            [listing], cutoff=cutoff
        )
        stockout_previous_stage, repair_entry_date, repair_reasons = self._stage_entries(
            [listing], cutoff=cutoff
        ).get(listing.id, (None, None, ()))
        return self._from_evidence(
            listing=listing,
            cutoff=cutoff,
            config=config,
            rule_version=rule_version,
            sales=sales,
            stock=stock,
            prior=prior,
            archive=archive,
            monitor_rows=monitor_rows,
            unconfirmed_account_ad_days=self._unconfirmed_account_ad_days(
                {listing.source_account_ref},
                cutoff=cutoff,
                window_days=config.medium_days,
                confirmed_sales_days=confirmed_sales_days,
            )[listing.source_account_ref],
            confirmed_sales_days=frozenset(confirmed_sales_days[listing.source_account_ref]),
            lifecycle_history_confirmed=listing.id in confirmed_lifecycle,
            manual_stage_protected=listing.id in manual_lifecycle,
            stockout_previous_stage=stockout_previous_stage,
            repair_entry_date=repair_entry_date,
            repair_reasons=repair_reasons,
        )

    def evaluate_page(
        self,
        *,
        listings: Sequence[ListingManagementCurrentMart],
        cutoff: date,
        config: ListingGradeRuleConfig,
        rule_version: int,
    ) -> dict[UUID, ListingEvaluationPreview]:
        """Read exact-identity evidence plus all account-day ad report rows."""
        if not listings:
            return {}
        if len(listings) > 200 or len({row.id for row in listings}) != len(listings):
            raise ValueError("Listing evaluation page must contain 1-200 distinct listings")

        keys = {(row.source_account_ref, row.store_id, row.item_id, row.msku) for row in listings}
        monitor_keys = {(key[0], key[1], key[2]) for key in keys}

        def matching_facts(model):
            return or_(
                *(
                    and_(
                        model.source_account_ref == account,
                        model.store_id == store,
                        model.item_id == item,
                        model.msku.is_not_distinct_from(msku),
                    )
                    for account, store, item, msku in keys
                )
            )

        start = cutoff - timedelta(days=max(30, config.medium_days) - 1)
        stock_start = cutoff - timedelta(
            days=max(
                30,
                config.inventory_repair.long_stockout_days + 2,
                config.inventory_repair.stockout_repair_valid_days,
            )
            - 1
        )
        prior_cutoff = cutoff - timedelta(
            days=config.inventory_repair.stockout_consecutive_days - 1
        )
        sales_rows = self.session.scalars(
            select(DailySalesItemDayMart).where(
                matching_facts(DailySalesItemDayMart),
                DailySalesItemDayMart.business_date_la.between(start, cutoff),
            )
        ).all()
        stock_rows = self.session.scalars(
            select(WalmartListingInventoryDailyFact).where(
                matching_facts(WalmartListingInventoryDailyFact),
                WalmartListingInventoryDailyFact.snapshot_date_la.between(stock_start, cutoff),
            )
        ).all()
        confirmed_wfs_days_by_account = self._confirmed_wfs_days(
            {listing.source_account_ref for listing in listings},
            start=stock_start,
            cutoff=cutoff,
        )
        prior_rows = self.session.execute(
            select(
                WalmartListingInventoryDailyFact.source_account_ref,
                WalmartListingInventoryDailyFact.store_id,
                WalmartListingInventoryDailyFact.item_id,
                WalmartListingInventoryDailyFact.msku,
                func.max(WalmartListingInventoryDailyFact.snapshot_date_la),
            )
            .where(
                matching_facts(WalmartListingInventoryDailyFact),
                WalmartListingInventoryDailyFact.snapshot_date_la < prior_cutoff,
                WalmartListingInventoryDailyFact.wfs_available_quantity
                > config.inventory_repair.low_stock_max_units,
            )
            .group_by(
                WalmartListingInventoryDailyFact.source_account_ref,
                WalmartListingInventoryDailyFact.store_id,
                WalmartListingInventoryDailyFact.item_id,
                WalmartListingInventoryDailyFact.msku,
            )
        ).all()
        archive_rows = self.session.scalars(
            select(ListingArchiveState).where(
                ListingArchiveState.listing_id.in_([row.id for row in listings])
            )
        ).all()
        monitor_start = datetime.combine(start, datetime.min.time(), LOS_ANGELES).astimezone(UTC)
        monitor_end = datetime.combine(
            cutoff + timedelta(days=1), datetime.min.time(), LOS_ANGELES
        ).astimezone(UTC)
        monitor_rows = self.session.scalars(
            select(StandardizedWalmartMonitorListingObservation)
            .where(
                or_(
                    *(
                        and_(
                            StandardizedWalmartMonitorListingObservation.source_account_ref
                            == account,
                            StandardizedWalmartMonitorListingObservation.store_id == store,
                            StandardizedWalmartMonitorListingObservation.item_id == item,
                        )
                        for account, store, item in monitor_keys
                    )
                ),
                func.lower(StandardizedWalmartMonitorListingObservation.monitor_outcome)
                == "success",
                StandardizedWalmartMonitorListingObservation.captured_at >= monitor_start,
                StandardizedWalmartMonitorListingObservation.captured_at < monitor_end,
            )
            .order_by(StandardizedWalmartMonitorListingObservation.captured_at)
        ).all()

        sales_by_key = defaultdict(list)
        for row in sales_rows:
            sales_by_key[(row.source_account_ref, row.store_id, row.item_id, row.msku)].append(row)
        stock_by_key = defaultdict(list)
        for row in stock_rows:
            if row.snapshot_date_la in confirmed_wfs_days_by_account[row.source_account_ref]:
                stock_by_key[(row.source_account_ref, row.store_id, row.item_id, row.msku)].append(
                    row
                )
        prior_by_key = {(row[0], row[1], row[2], row[3]): row[4] for row in prior_rows}
        prior_dates = [row[4] for row in prior_rows if row[4] is not None]
        confirmed_prior_days_by_account = (
            self._confirmed_wfs_days(
                {listing.source_account_ref for listing in listings},
                start=min(prior_dates),
                cutoff=max(prior_dates),
            )
            if prior_dates
            else {}
        )
        prior_by_key = {
            key: business_day
            for key, business_day in prior_by_key.items()
            if business_day in confirmed_prior_days_by_account.get(key[0], set())
        }
        archive_by_id = {row.listing_id: row for row in archive_rows}
        monitor_by_key = defaultdict(list)
        for row in monitor_rows:
            monitor_by_key[(row.source_account_ref, row.store_id, row.item_id)].append(row)
        accounts = {listing.source_account_ref for listing in listings}
        confirmed_lifecycle, manual_lifecycle = self._confirmed_lifecycle_states(
            listings, cutoff=cutoff
        )
        stage_entries = self._stage_entries(listings, cutoff=cutoff)
        confirmed_sales_days_by_account = self._confirmed_daily_sales_days(
            accounts, start=start, cutoff=cutoff
        )
        unconfirmed_ad_days_by_account = self._unconfirmed_account_ad_days(
            accounts,
            cutoff=cutoff,
            window_days=config.medium_days,
            confirmed_sales_days=confirmed_sales_days_by_account,
        )

        return {
            listing.id: self._from_evidence(
                listing=listing,
                cutoff=cutoff,
                config=config,
                rule_version=rule_version,
                sales=sales_by_key.get(
                    (listing.source_account_ref, listing.store_id, listing.item_id, listing.msku),
                    [],
                ),
                stock=stock_by_key.get(
                    (listing.source_account_ref, listing.store_id, listing.item_id, listing.msku),
                    [],
                ),
                prior=prior_by_key.get(
                    (listing.source_account_ref, listing.store_id, listing.item_id, listing.msku)
                ),
                archive=archive_by_id.get(listing.id),
                monitor_rows=monitor_by_key.get(
                    (listing.source_account_ref, listing.store_id, listing.item_id), []
                ),
                unconfirmed_account_ad_days=unconfirmed_ad_days_by_account[
                    listing.source_account_ref
                ],
                confirmed_sales_days=frozenset(
                    confirmed_sales_days_by_account[listing.source_account_ref]
                ),
                lifecycle_history_confirmed=listing.id in confirmed_lifecycle,
                manual_stage_protected=listing.id in manual_lifecycle,
                stockout_previous_stage=stage_entries.get(listing.id, (None, None, ()))[0],
                repair_entry_date=stage_entries.get(listing.id, (None, None, ()))[1],
                repair_reasons=stage_entries.get(listing.id, (None, None, ()))[2],
            )
            for listing in listings
        }

    @staticmethod
    def _from_evidence(
        *,
        listing: ListingManagementCurrentMart,
        cutoff: date,
        config: ListingGradeRuleConfig,
        rule_version: int | None,
        sales: list[DailySalesItemDayMart],
        stock: list[WalmartListingInventoryDailyFact],
        prior: date | None,
        archive: ListingArchiveState | None,
        monitor_rows: list[StandardizedWalmartMonitorListingObservation],
        unconfirmed_account_ad_days: frozenset[date],
        confirmed_sales_days: frozenset[date] = frozenset(),
        lifecycle_history_confirmed: bool = False,
        manual_stage_protected: bool = False,
        stockout_previous_stage: str | None = None,
        repair_entry_date: date | None = None,
        repair_reasons: tuple[str, ...] = (),
    ) -> ListingEvaluationPreview:
        archive_state_known = archive is not None
        archived = bool(archive is not None and archive.is_archived)
        # Current archive state is not proof of a prior historical cutoff.
        archive_event_after_cutoff = bool(
            archive is not None
            and archive_has_post_cutoff_event(
                archived_at=archive.archived_at,
                restored_at=archive.restored_at,
                cutoff=cutoff,
            )
        )
        if archive_event_after_cutoff:
            archived = False
        if listing.fulfillment_type != "1":
            return ListingEvaluationPreview(
                listing_id=listing.id,
                cutoff_la=cutoff,
                current_lifecycle=listing.lifecycle_status,
                current_grade=listing.product_grade,
                currently_archived=archived,
                rule_version=rule_version or 0,
                rule_source="database" if rule_version else "default",
                missing_evidence=["NON_WFS_EXCLUDED"],
            )
        monitor_by_day = {
            row.captured_at.astimezone(LOS_ANGELES).date(): row for row in monitor_rows
        }
        grade, n_short, n_medium, margin = basic_financial_candidate(
            sales,
            cutoff=cutoff,
            config=config,
            unconfirmed_account_ad_days=unconfirmed_account_ad_days,
        )
        stage, observed, low = stockout_candidate(
            stock,
            cutoff=cutoff,
            prior_effective_stock=prior is not None,
            fulfillment_type=listing.fulfillment_type,
            currently_archived=archived,
            consecutive_days=config.inventory_repair.stockout_consecutive_days,
        )
        lifecycle_reason = None
        lifecycle_complete = False
        stock_valid30 = 0
        sales_by_day = {row.business_date_la: row for row in sales}
        known_stages = {
            "测品期",
            "打品期",
            "启动期",
            "上升期",
            "稳定期",
            "下滑期",
            "断货期",
            "修复期",
            "清货期",
            "已归档",
        }
        if not archived:
            stock_by_day = {row.snapshot_date_la: row for row in stock}
            stockout_days_before_recovery = None
            if listing.lifecycle_status == "断货期" and stockout_previous_stage is not None:
                today_stock = stock_by_day.get(cutoff)
                if today_stock is not None and (today_stock.wfs_available_quantity or ZERO) > ZERO:
                    cursor = cutoff - timedelta(days=1)
                    count = 0
                    while (
                        cursor in stock_by_day
                        and stock_by_day[cursor].wfs_available_quantity == ZERO
                    ):
                        count += 1
                        cursor -= timedelta(days=1)
                    preceding = stock_by_day.get(cursor)
                    if count > config.inventory_repair.long_stockout_days or (
                        count >= config.inventory_repair.stockout_consecutive_days
                        and preceding is not None
                        and (preceding.wfs_available_quantity or ZERO) > ZERO
                    ):
                        stockout_days_before_recovery = count
            repair_stock_valid_days = (
                sum(
                    row.snapshot_date_la >= repair_entry_date
                    and (row.wfs_available_quantity or ZERO) > ZERO
                    for row in stock
                )
                if repair_entry_date is not None
                else None
            )
            business_days = []
            for business_date in sorted(
                set(sales_by_day) | set(stock_by_day) | set(monitor_by_day)
            ):
                stock_row = stock_by_day.get(business_date)
                monitor_row = monitor_by_day.get(business_date)
                sales_row = sales_by_day.get(business_date)
                sales_qty = (
                    sales_row.sales_qty
                    if sales_row is not None
                    else ZERO
                    if stock_row is not None and business_date in confirmed_sales_days
                    else None
                )
                strike_abnormal = None
                buybox_abnormal = None
                if monitor_row is not None:
                    if (
                        monitor_row.strike_price_amount is not None
                        and monitor_row.sale_price_amount is not None
                    ):
                        strike_abnormal = (
                            monitor_row.strike_price_amount <= monitor_row.sale_price_amount
                        )
                    if monitor_row.buybox_status in {
                        "未拥有",
                        "LOST",
                        "NOT_OWNED",
                        "secondary",
                        "other",
                    }:
                        buybox_abnormal = True
                    elif monitor_row.buybox_status in {
                        "拥有",
                        "PRIMARY",
                        "primary",
                        "WON",
                        "WINNING",
                    }:
                        buybox_abnormal = False
                business_days.append(
                    BusinessDay(
                        day=business_date,
                        wfs_qty=stock_row.wfs_available_quantity if stock_row else None,
                        sales_qty=sales_qty,
                        available_qty=stock_row.available_quantity if stock_row else None,
                        strike_price_abnormal=strike_abnormal,
                        buybox_abnormal=buybox_abnormal,
                    )
                )
            lifecycle_result = lifecycle_listing(
                cutoff=cutoff,
                previous_stage=listing.lifecycle_status,
                days=business_days,
                first_effective_stock=prior is not None,
                config=config,
                stockout_previous_stage=stockout_previous_stage,
                stockout_days_before_recovery=stockout_days_before_recovery,
                repair_stock_valid_days=repair_stock_valid_days,
                repair_reasons=repair_reasons,
                fulfillment_type=listing.fulfillment_type or "",
            )
            lifecycle_reason = lifecycle_result.reason
            lifecycle_complete = lifecycle_result.evidence_complete
            stock_valid30 = lifecycle_result.valid_stock_days_30
            # This is a diagnostic based on current stage, not a proven stage as of cutoff.
            if lifecycle_result.evidence_complete:
                stage = lifecycle_result.stage
        if manual_stage_protected:
            stage = listing.lifecycle_status
            lifecycle_reason = "已批准的人工生命周期优先"
            lifecycle_complete = True
        missing: list[str] = []
        if listing.lifecycle_status is not None and not lifecycle_history_confirmed:
            missing.append("HISTORICAL_LIFECYCLE_APPROVAL_EVENTS_UNVERIFIED")
        if not lifecycle_complete:
            missing.append("LIFECYCLE_TRANSITION_EVIDENCE_INCOMPLETE")
        valid_sales_dates_30 = {
            row.business_date_la
            for row in sales
            if row.sales_qty is not None
            and row.business_date_la in confirmed_sales_days
            and row.business_date_la >= cutoff - timedelta(days=29)
        }
        valid_sales_dates_30.update(
            row.snapshot_date_la
            for row in stock
            if row.snapshot_date_la in confirmed_sales_days
            and row.snapshot_date_la >= cutoff - timedelta(days=29)
            and row.snapshot_date_la not in sales_by_day
        )
        sales_valid30 = len(valid_sales_dates_30)
        if sales_valid30 < 30:
            missing.append("ZERO_SALES_DAY_COMPLETENESS_UNVERIFIED")
        if sales_valid30 < config.lifecycle.growth_min_valid_days_30:
            missing.append("SALES_TREND_VALID_DAYS_INSUFFICIENT")
        if unconfirmed_account_ad_days:
            missing.append("DAILY_SALES_ACCOUNT_DAY_AD_SPEND_UNCONFIRMED")
        if listing.lifecycle_status not in known_stages and stage not in known_stages:
            missing.append("LIFECYCLE_INITIAL_STATE_PENDING")
        if not archive_state_known or archive_event_after_cutoff:
            missing.append("ARCHIVE_STATE_AS_OF_CUTOFF_UNVERIFIED")
        if not rule_version:
            missing.append("RULE_VERSION_NOT_PUBLISHED")
        if not lifecycle_allows_grade(
            stage if stage in known_stages else listing.lifecycle_status,
            archived=archived,
            config=config,
        ):
            grade = None
            margin = None
            missing.append("LIFECYCLE_EXCLUDED_FROM_GRADING")
        if grade is None and "LIFECYCLE_EXCLUDED_FROM_GRADING" not in missing:
            missing.append("BASIC_FINANCIAL_SAMPLE_INSUFFICIENT_OR_UNCALCULABLE")
        if listing.fulfillment_type == "1" and observed < 7:
            missing.append("LATEST_WFS_SNAPSHOT_INCOMPLETE")
        if listing.fulfillment_type == "0" and sales_valid30 == 0:
            missing.append("FBM_SALES_EVIDENCE_MISSING")
        if listing.fulfillment_type not in {"0", "1"}:
            missing.append("NON_WFS_OR_UNKNOWN_FULFILLMENT")
        if archived:
            missing.append("CURRENT_ARCHIVE_STATE_NOT_AS_OF_CUTOFF")
        if stage is None and listing.lifecycle_status is None:
            missing.append("LIFECYCLE_INITIAL_STATE_UNVERIFIED")

        return ListingEvaluationPreview(
            listing_id=listing.id,
            cutoff_la=cutoff,
            current_lifecycle=listing.lifecycle_status,
            current_grade=listing.product_grade,
            lifecycle_evidence_reason=lifecycle_reason,
            valid_stock_days_30=stock_valid30,
            lifecycle_candidate=stage,
            grade_candidate=grade,
            valid_short=n_short,
            valid_medium=n_medium,
            weighted_margin_percent=margin,
            observed_stock_days_7=observed,
            low_stock_days_7=low,
            prior_effective_stock=prior is not None,
            currently_archived=archived,
            rule_version=rule_version or 0,
            rule_source="database" if rule_version else "default",
            missing_evidence=missing,
        )

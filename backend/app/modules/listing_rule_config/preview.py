"""Read-only, provisional Listing evaluation from existing daily MARTs.

This module intentionally does not initialize lifecycle state, confirm upstream
advertising, publish grades, or persist any calculation.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.data_pages.models import (
    DailySalesItemDayMart,
    ListingArchiveState,
    ListingManagementCurrentMart,
    WalmartListingInventoryDailyFact,
)
from app.modules.listing_rule_config.evaluation import BusinessDay, lifecycle_listing
from app.modules.listing_rule_config.models import ListingGradeRuleVersion
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig

ZERO = Decimal("0")


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
) -> tuple[str | None, int, int, Decimal | None]:
    """Diagnostic margin *only*, never evidence of ad/fee finalization.

    The MART contains no trusted zero-business-day publication marker: absent
    rows do not become zero dates. Missing currency is excluded, not assumed USD.
    """
    start_medium = cutoff - timedelta(days=config.medium_days - 1)
    start_short = cutoff - timedelta(days=config.short_days - 1)
    qualified: dict[date, DailySalesItemDayMart] = {}
    for day in days:
        if not start_medium <= day.business_date_la <= cutoff:
            continue
        if (
            day.cost_status != "complete"
            or day.gross_profit_amount is None
            or day.sales_amount is None
            or day.sales_amount < ZERO
            or day.missing_cost_codes_json
            or day.sales_currency_code != "USD"
            or day.gross_profit_currency_code != "USD"
        ):
            continue
        qualified[day.business_date_la] = day

    medium = list(qualified.values())
    short = [row for row in medium if row.business_date_la >= start_short]
    n_short, n_medium = len(short), len(medium)
    if n_short < config.short_min_valid_days or n_medium < config.medium_min_valid_days:
        return None, n_short, n_medium, None

    sales_short = sum((row.sales_amount for row in short), ZERO)
    profit_short = sum((row.gross_profit_amount for row in short), ZERO)
    sales_medium = sum((row.sales_amount for row in medium), ZERO)
    profit_medium = sum((row.gross_profit_amount for row in medium), ZERO)

    if sales_short == ZERO and profit_short < ZERO:
        return "D", n_short, n_medium, None
    if sales_short <= ZERO or sales_medium <= ZERO:
        return None, n_short, n_medium, None

    margin = (
        (profit_short / sales_short * 100) * Decimal(config.short_weight_percent)
        + (profit_medium / sales_medium * 100) * Decimal(config.medium_weight_percent)
    ) / 100
    if margin > config.a_above_percent:
        grade = "A"
    elif margin >= config.b_min_percent:
        grade = "B"
    elif margin >= config.c_min_percent:
        grade = "C"
    else:
        grade = "D"
    return grade, n_short, n_medium, margin


def stockout_candidate(
    inventory: list[WalmartListingInventoryDailyFact],
    *,
    cutoff: date,
    low_limit: int,
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
    low = sum(
        row.wfs_available_quantity is not None and row.wfs_available_quantity <= low_limit
        for row in recent.values()
    )
    candidate = (
        "断货期"
        if (
            fulfillment_type in {"0", "1"}
            and not currently_archived
            and prior_effective_stock
            and observed == consecutive_days
            and low == consecutive_days
        )
        else None
    )
    return candidate, observed, low


class ListingEvaluationPreviewService:
    """Account-scoped, exact-identity, read-only diagnostic for one Listing."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def evaluate(
        self,
        *,
        listing_id: UUID,
        account_refs: frozenset[str],
        cutoff: date,
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
                            days=max(30, config.inventory_repair.stockout_consecutive_days) - 1
                        ),
                        cutoff,
                    ),
                )
            ).all()
        )
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
        archive = self.session.scalar(
            select(ListingArchiveState).where(ListingArchiveState.listing_id == listing.id)
        )
        archived = archive is not None and archive.is_archived
        grade, n_short, n_medium, margin = basic_financial_candidate(
            sales, cutoff=cutoff, config=config
        )
        stage, observed, low = stockout_candidate(
            stock,
            cutoff=cutoff,
            low_limit=config.inventory_repair.low_stock_max_units,
            prior_effective_stock=prior is not None,
            fulfillment_type=listing.fulfillment_type,
            currently_archived=archived,
            consecutive_days=config.inventory_repair.stockout_consecutive_days,
        )
        lifecycle_reason = None
        stock_valid30 = 0
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
        if (
            listing.fulfillment_type == "1"
            and not archived
            and listing.lifecycle_status in known_stages
        ):
            sales_by_day = {row.business_date_la: row for row in sales}
            business_days = [
                BusinessDay(
                    day=row.snapshot_date_la,
                    wfs_qty=row.wfs_available_quantity,
                    sales_qty=(
                        sales_by_day[row.snapshot_date_la].sales_qty
                        if row.snapshot_date_la in sales_by_day
                        else None
                    ),
                )
                for row in stock
            ]
            lifecycle_result = lifecycle_listing(
                cutoff=cutoff,
                previous_stage=listing.lifecycle_status,
                days=business_days,
                first_effective_stock=prior is not None,
                config=config,
            )
            lifecycle_reason = lifecycle_result.reason
            stock_valid30 = lifecycle_result.valid_stock_days_30
            # This is a diagnostic based on current stage, not a proven stage as of cutoff.
            if lifecycle_result.evidence_complete:
                stage = lifecycle_result.stage
        missing = [
            "ADS_COST_PUBLICATION_PROOF_MISSING",
            "HISTORICAL_LIFECYCLE_APPROVAL_EVENTS_UNVERIFIED",
            "ZERO_SALES_DAY_COMPLETENESS_UNVERIFIED",
        ]
        if stock_valid30 < config.lifecycle.growth_min_valid_days_30:
            missing.append("SALES_TREND_VALID_STOCK_DAYS_INSUFFICIENT")
        if listing.lifecycle_status not in known_stages:
            missing.append("PREVIOUS_LIFECYCLE_STAGE_UNVERIFIED")
        if version is None:
            missing.append("RULE_VERSION_NOT_PUBLISHED")
        if grade is None:
            missing.append("BASIC_FINANCIAL_SAMPLE_INSUFFICIENT_OR_UNCALCULABLE")
        if observed < 7:
            missing.append("LATEST_WFS_SNAPSHOT_INCOMPLETE")
        if listing.fulfillment_type == "0":
            missing.append("WFS_ELIGIBLE_ACTIVE_FULFILLMENT_UNVERIFIED")
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
            rule_version=version.version if version is not None else 0,
            rule_source="database" if version is not None else "default",
            missing_evidence=missing,
        )

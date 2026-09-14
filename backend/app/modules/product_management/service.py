from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, Never, cast
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.modules.product_management.calculations import (
    SIX_PLACES,
    IdentityWfsOverride,
    PricingRule,
    SkuPricingResult,
    SkuPricingRule,
    WfsFulfillmentRate,
    calculate_pricing,
    calculate_sku_pricing,
    calculate_storage,
    is_sku_pricing_rule_valid,
    select_wfs_fee,
)
from app.modules.product_management.models import (
    ManualProductTag,
    ProductManagementPricingCurrent,
    ProductPricingRecalculationRun,
    ProductPricingRuleVersion,
    UserTableView,
)
from app.modules.product_management.repository import (
    ProductManagementProjection,
    ProductManagementRepository,
)
from app.modules.product_management.schemas import (
    DEFAULT_PRODUCT_MANAGEMENT_COLUMNS,
    CostComponentRead,
    ExportRequest,
    ExportResult,
    IdentityWfsOverrideConfig,
    InternalTagRead,
    PricingBreakdownRead,
    PricingRuleRead,
    PricingRulesData,
    PricingRuleWrite,
    ProductCoreRead,
    ProductImageRead,
    ProductManagementDetailData,
    ProductManagementListData,
    ProductManagementListItem,
    ProductManagementListQuery,
    ProductManagementOptionsData,
    ProductManagementSummaryData,
    ProductManagementSummaryQuery,
    RecalculatePricingRequest,
    RecalculatePricingResult,
    SourceTagRead,
    SyncedProductDetailRead,
    UserTableViewRead,
    UserTableViewWrite,
    WfsFulfillmentRateConfig,
    WfsStorageRateConfig,
)
from app.modules.products.models import Product
from app.modules.sku_detail.models import (
    LingxingSkuGlobalTag,
    LingxingSkuProductInfoCurrent,
    SkuBaseProfileCurrent,
)

RULE_VERSION_CONFLICT = "RULE_VERSION_CONFLICT"
RULE_NOT_AVAILABLE = "RULE_NOT_AVAILABLE"
CALCULATION_INPUT_INCOMPLETE = "CALCULATION_INPUT_INCOMPLETE"
PRICING_RULE_BACKDATING_NOT_ALLOWED = "PRICING_RULE_BACKDATING_NOT_ALLOWED"
FAILED_RECALCULATION_HTTP_STATUS = {
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "DATA_SCOPE_DENIED": 403,
    "RECALCULATION_NOT_AUTHORIZED": 403,
    "NOT_FOUND": 404,
    "RULE_VERSION_CONFLICT": 409,
    "IDEMPOTENCY_CONFLICT": 409,
    "INVALID_REQUEST": 422,
    "VALIDATION_ERROR": 422,
    "RULE_NOT_AVAILABLE": 424,
    "CALCULATION_INPUT_INCOMPLETE": 424,
}
audit_logger = logging.getLogger("app.audit.product_management")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ProductManagementService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ProductManagementRepository(session)

    def list_skus(
        self,
        query: ProductManagementListQuery,
        account_refs: frozenset[str],
        *,
        include_costs: bool,
    ) -> tuple[ProductManagementListData, int, datetime | None, datetime | None]:
        now = datetime.now(UTC)
        effective_rules = self.repository.list_effective_rules(now, account_refs)
        sku_rules = {
            account_ref: self._sku_pricing_rule(rule)
            for account_ref, rule in effective_rules.items()
        }
        ready_accounts, invalid_accounts = self._sku_rule_account_sets(account_refs, sku_rules)
        rows, total = self.repository.list_projections(
            account_refs=account_refs,
            page=query.page,
            page_size=query.page_size,
            sku=query.sku,
            sku_batch=query.sku_batch,
            product_name=query.product_name,
            category=query.category,
            internal_tag=query.internal_tag,
            product_grade=query.product_grade,
            calculation_status=query.calculation_status,
            sort_by=query.sort_by,
            sort_order=query.sort_order,
            pricing_ready_account_refs=ready_accounts,
            invalid_pricing_rule_account_refs=invalid_accounts,
        )
        product_ids = [row[1].id for row in rows if row[1] is not None]
        snapshot_ids = [row[2].source_snapshot_id for row in rows if row[2] is not None]
        tags = self.repository.list_internal_tags(product_ids, datetime.now(UTC))
        source_tags = self.repository.list_source_tags_for_snapshots(snapshot_ids)
        image_counts = self.repository.image_counts_for_snapshots(snapshot_ids)
        listing_counts = self.repository.listing_counts(product_ids)
        items = [
            self._list_item(
                row,
                tags.get(row[1].id, []) if row[1] is not None else [],
                listing_counts.get(row[1].id, 0) if row[1] is not None else 0,
                include_costs=include_costs,
                source_tags=(
                    source_tags.get(row[2].source_snapshot_id, []) if row[2] is not None else []
                ),
                image_count=(
                    image_counts.get(row[2].source_snapshot_id, 0) if row[2] is not None else 0
                ),
                calculation=self._sku_pricing_calculation(
                    row[2],
                    row[3],
                    image_counts.get(row[2].source_snapshot_id, 0) if row[2] is not None else 0,
                    sku_rules.get(row[0].source_account_ref, SkuPricingRule()),
                ),
                calculation_rule_version=(
                    effective_rules[row[0].source_account_ref].version
                    if row[0].source_account_ref in effective_rules
                    else "sku-pricing-defaults-v1"
                ),
            )
            for row in rows
        ]
        observed_at = [
            row[2].source_observed_at if row[2] is not None else row[0].last_seen_at for row in rows
        ]
        return (
            ProductManagementListData(items=items),
            total,
            min(observed_at, default=None),
            max(observed_at, default=None),
        )

    def summary(
        self,
        query: ProductManagementSummaryQuery,
        account_refs: frozenset[str],
    ) -> ProductManagementSummaryData:
        now = datetime.now(UTC)
        sku_rules = {
            account_ref: self._sku_pricing_rule(rule)
            for account_ref, rule in self.repository.list_effective_rules(now, account_refs).items()
        }
        ready_accounts, invalid_accounts = self._sku_rule_account_sets(account_refs, sku_rules)
        (
            total,
            synced,
            completeness,
            images,
            tags,
            incomplete,
            missing_purchase,
            missing_weight,
            missing_dimensions,
            missing_dimension_image,
            invalid_pricing_rule,
            pricing_ok,
        ) = self.repository.summarize_projections(
            account_refs=account_refs,
            sku=query.sku,
            sku_batch=query.sku_batch,
            product_name=query.product_name,
            category=query.category,
            internal_tag=query.internal_tag,
            product_grade=query.product_grade,
            calculation_status=query.calculation_status,
            pricing_ready_account_refs=ready_accounts,
            invalid_pricing_rule_account_refs=invalid_accounts,
        )
        return ProductManagementSummaryData(
            total=total,
            synced_detail_count=synced,
            data_completeness_rate=completeness.quantize(SIX_PLACES, rounding=ROUND_HALF_UP),
            with_image_count=images,
            with_source_tag_count=tags,
            incomplete_count=incomplete,
            missing_purchase_cost_count=missing_purchase,
            missing_gross_weight_count=missing_weight,
            missing_package_dimensions_count=missing_dimensions,
            missing_dimension_image_count=missing_dimension_image,
            invalid_pricing_rule_count=invalid_pricing_rule,
            pricing_ok_count=pricing_ok,
        )

    def get_sku(
        self,
        sku_id: UUID,
        account_refs: frozenset[str],
        *,
        include_costs: bool,
    ) -> ProductManagementDetailData:
        row = self._require_projection(sku_id, account_refs)
        identity, product, current, profile, pricing, _, _ = row
        tags = (
            self.repository.list_internal_tags([product.id], datetime.now(UTC)).get(product.id, [])
            if product is not None
            else []
        )
        images = [] if current is None else self.repository.list_images(current.source_snapshot_id)
        source_tags = (
            [] if current is None else self.repository.list_source_tags(current.source_snapshot_id)
        )
        effective_rule = self.repository.get_effective_rule(
            datetime.now(UTC), identity.source_account_ref
        )
        sku_rule = self._sku_pricing_rule(effective_rule)
        calculation = self._sku_pricing_calculation(current, profile, len(images), sku_rule)
        return ProductManagementDetailData(
            sku_id=identity.id,
            core=(
                ProductCoreRead(
                    product_id=product.id,
                    sku=product.sku,
                    product_name=product.product_name,
                    category=product.category,
                    product_type=product.product_type,
                    status=product.status,
                    manual_grade=product.grade,
                )
                if product is not None
                else None
            ),
            synced_detail=(
                SyncedProductDetailRead.model_validate(current) if current is not None else None
            ),
            images=[
                ProductImageRead(
                    ordinal=image.ordinal, url=image.pic_url, is_primary=image.is_primary
                )
                for image in images
            ],
            source_tags=[
                SourceTagRead(
                    source_tag_id=tag.global_tag_id,
                    label=tag.tag_name,
                    color=tag.color,
                )
                for tag in source_tags
            ],
            internal_tags=[self._tag(tag) for tag in tags],
            pricing=self._sku_pricing_read(
                identity.id,
                calculation,
                sku_rule,
                include_costs=include_costs,
                rule_version=(
                    effective_rule.version
                    if effective_rule is not None
                    else "sku-pricing-defaults-v1"
                ),
                product_grade=(pricing.product_grade if pricing is not None else "exception"),
                grade_reason=(
                    pricing.grade_reason if pricing is not None else "pricing_only_not_graded"
                ),
            ),
        )

    def options(self) -> ProductManagementOptionsData:
        return ProductManagementOptionsData(
            product_grades=["A", "B", "C", "exception"],
            calculation_statuses=[
                "ok",
                "pricing_unavailable",
                "storage_unavailable",
                "invalid_denominator",
                "missing_fx_rate",
                "missing_purchase_cost",
                "missing_weight",
                "missing_wfs_rate",
                "missing_storage_rate",
                "invalid_revenue",
                "invalid_pricing_denominator",
                "invalid_pricing_rule_config",
                "invalid_roi_base",
                "needs_confirm",
            ],
            internal_tags=[self._tag(tag) for tag in self.repository.list_active_tags()],
        )

    @staticmethod
    def export(payload: ExportRequest) -> ExportResult:
        return ExportResult(row_limit=payload.max_rows)

    def list_rules(
        self,
        source_account_ref: str,
        account_refs: frozenset[str],
        at: datetime | None = None,
    ) -> PricingRulesData:
        self._require_source_account(source_account_ref, account_refs)
        rules = self.repository.list_rule_versions(source_account_ref)
        effective = self.repository.get_effective_rule(at or datetime.now(UTC), source_account_ref)
        return PricingRulesData(
            items=[self._rule_read(rule) for rule in rules],
            active_rule_id=effective.id if effective is not None else None,
        )

    def publish_rule(
        self,
        payload: PricingRuleWrite,
        account_refs: frozenset[str],
        *,
        actor_ref: str,
        request_id: str,
    ) -> PricingRuleRead:
        self._require_source_account(payload.source_account_ref, account_refs)
        now = _utc_now()
        if payload.effective_from < now:
            self._error(PRICING_RULE_BACKDATING_NOT_ALLOWED, 422)
        versions = self.repository.lock_rule_versions(payload.source_account_ref)
        if any(rule.version == payload.version for rule in versions):
            self._error(RULE_VERSION_CONFLICT, 409)
        latest = versions[-1] if versions else None
        if latest is not None and payload.effective_from <= latest.effective_from:
            self._error(RULE_VERSION_CONFLICT, 409)
        if (
            latest is not None
            and latest.effective_to is not None
            and payload.effective_from < latest.effective_to
        ):
            self._error(RULE_VERSION_CONFLICT, 409)
        open_rules = [rule for rule in versions if rule.is_active and rule.effective_to is None]
        if len(open_rules) > 1 or (open_rules and open_rules[0] is not latest):
            self._error(RULE_VERSION_CONFLICT, 409)
        if open_rules:
            self.repository.update_record(
                open_rules[0],
                {"effective_to": payload.effective_from, "updated_at": now},
            )
        values = payload.model_dump(
            exclude={
                "wfs_fulfillment_rates",
                "wfs_storage_rates",
                "identity_wfs_overrides",
            }
        )
        rule = ProductPricingRuleVersion(
            id=uuid4(),
            rule_key="product_management",
            **values,
            wfs_fulfillment_rates_json=[
                item.model_dump(mode="json", context={"preserve_decimal_places": True})
                for item in payload.wfs_fulfillment_rates
            ],
            wfs_storage_rates_json=[
                item.model_dump(mode="json", context={"preserve_decimal_places": True})
                for item in payload.wfs_storage_rates
            ],
            identity_wfs_overrides_json=[
                item.model_dump(mode="json", context={"preserve_decimal_places": True})
                for item in payload.identity_wfs_overrides
            ],
            is_active=True,
            approved_by=actor_ref,
            approved_at=now,
            actor_ref=actor_ref,
            request_id=request_id,
            action="publish_pricing_rule",
            status="succeeded",
            created_at=now,
            updated_at=now,
        )
        try:
            self.repository.add_rule(rule)
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            self._error(RULE_VERSION_CONFLICT, 409)
        audit_logger.info(
            "pricing_rule_published actor_ref=%s request_id=%s source_account_ref=%s "
            "pricing_rule_version_id=%s action=publish_pricing_rule status=succeeded",
            actor_ref,
            request_id,
            payload.source_account_ref,
            rule.id,
        )
        return self._rule_read(rule)

    def recalculate(
        self,
        payload: RecalculatePricingRequest,
        account_refs: frozenset[str],
        *,
        actor_ref: str,
        request_id: str,
    ) -> RecalculatePricingResult:
        self._require_source_account(payload.source_account_ref, account_refs)
        mode: Literal["preview", "execute"] = "preview" if payload.preview_only else "execute"
        request_digest = self._recalculation_request_digest(payload)
        replay = self.repository.get_recalculation_run(
            principal_ref=actor_ref,
            source_account_ref=payload.source_account_ref,
            mode=mode,
            idempotency_key=payload.idempotency_key,
        )
        if replay is not None:
            return self._recalculation_replay(replay, request_digest)
        effective_at = payload.effective_at or datetime.now(UTC)
        rule = (
            self.repository.get_rule(payload.rule_version_id, payload.source_account_ref)
            if payload.rule_version_id is not None
            else self.repository.get_effective_rule(effective_at, payload.source_account_ref)
        )
        if rule is None or not rule.is_active:
            self._error(RULE_NOT_AVAILABLE, 424)
        now = datetime.now(UTC)
        run = ProductPricingRecalculationRun(
            id=uuid4(),
            principal_ref=actor_ref,
            actor_ref=actor_ref,
            source_account_ref=payload.source_account_ref,
            request_digest=request_digest,
            request_id=request_id,
            action="recalculate_pricing",
            page_key="product_management",
            capability="products:pricing:recalculate",
            mode=mode,
            status="running",
            scope=payload.scope,
            selected_count=len(payload.sku_ids),
            matched_count=0,
            eligible_count=0,
            affected_count=0,
            skipped_count=0,
            failed_count=0,
            pricing_rule_version_id=rule.id,
            idempotency_key=payload.idempotency_key,
            error_code=None,
            created_at=now,
            started_at=now,
            finished_at=None,
        )
        try:
            self.repository.add_recalculation_run(run)
        except IntegrityError:
            self.session.rollback()
            replay = self.repository.get_recalculation_run(
                principal_ref=actor_ref,
                source_account_ref=payload.source_account_ref,
                mode=mode,
                idempotency_key=payload.idempotency_key,
            )
            if replay is None:
                self._error("IDEMPOTENCY_CONFLICT", 409)
            return self._recalculation_replay(replay, request_digest)

        rows, matched_count = self.repository.list_recalculation_candidates(
            account_refs=frozenset({payload.source_account_ref}),
            scope=payload.scope,
            sku_ids=payload.sku_ids,
            limit=payload.max_items,
        )
        eligible_count = len(rows)
        skipped_count = max(matched_count - eligible_count, 0)
        if payload.scope == "selected" and matched_count != len(payload.sku_ids):
            self.repository.update_record(
                run,
                {
                    "status": "failed",
                    "matched_count": matched_count,
                    "eligible_count": eligible_count,
                    "skipped_count": skipped_count,
                    "error_code": "DATA_SCOPE_DENIED",
                    "finished_at": datetime.now(UTC),
                },
            )
            self.session.commit()
            self._error("DATA_SCOPE_DENIED", 403)

        if payload.preview_only:
            status = "previewed" if rows else "no_items"
            self.repository.update_record(
                run,
                {
                    "status": status,
                    "matched_count": matched_count,
                    "eligible_count": eligible_count,
                    "skipped_count": skipped_count,
                    "finished_at": datetime.now(UTC),
                },
            )
            self.session.commit()
            self._log_recalculation_run(run)
            return self._recalculation_result(run, idempotent_replay=False)

        failed = 0
        try:
            for row in rows:
                failed += self._recalculate_one(
                    row,
                    rule,
                    pricing_effective_at=effective_at,
                    business_month=effective_at.month,
                    run_id=run.id,
                    idempotency_key=payload.idempotency_key,
                    reason=payload.reason,
                    actor_ref=actor_ref,
                )
            status = "no_items" if not rows else "partial" if failed else "succeeded"
            self.repository.update_record(
                run,
                {
                    "status": status,
                    "matched_count": matched_count,
                    "eligible_count": eligible_count,
                    "affected_count": eligible_count,
                    "skipped_count": skipped_count,
                    "failed_count": failed,
                    "finished_at": datetime.now(UTC),
                },
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            run.status = "failed"
            run.error_code = "RECALCULATION_FAILED"
            run.finished_at = datetime.now(UTC)
            try:
                self.repository.add_recalculation_run(run)
                self.session.commit()
            except Exception:
                self.session.rollback()
            raise
        self._log_recalculation_run(run)
        return self._recalculation_result(run, idempotent_replay=False)

    def pricing_breakdown(
        self,
        sku_id: UUID,
        account_refs: frozenset[str],
        *,
        include_costs: bool,
    ) -> PricingBreakdownRead:
        row = self._require_projection(sku_id, account_refs)
        identity, _, current, profile, pricing, _, _ = row
        images = [] if current is None else self.repository.list_images(current.source_snapshot_id)
        now = datetime.now(UTC)
        rule = self.repository.get_effective_rule(now, identity.source_account_ref)
        sku_rule = self._sku_pricing_rule(rule)
        return self._sku_pricing_read(
            sku_id,
            self._sku_pricing_calculation(current, profile, len(images), sku_rule),
            sku_rule,
            include_costs=include_costs,
            rule_version=rule.version if rule is not None else "sku-pricing-defaults-v1",
            product_grade=pricing.product_grade if pricing is not None else "exception",
            grade_reason=pricing.grade_reason if pricing is not None else "pricing_only_not_graded",
        )

    def get_table_view(self, principal_ref: str) -> UserTableViewRead:
        view = self.repository.get_table_view(principal_ref)
        if view is None:
            return UserTableViewRead(
                applied_column_keys=list(DEFAULT_PRODUCT_MANAGEMENT_COLUMNS),
                column_widths={},
                schema_version=1,
                view_key="default",
                updated_at=None,
            )
        return UserTableViewRead(
            applied_column_keys=view.applied_column_keys_json,
            column_widths=view.column_widths_json,
            schema_version=view.schema_version,
            view_key=view.view_key,
            updated_at=view.updated_at,
        )

    def save_table_view(
        self,
        payload: UserTableViewWrite,
        *,
        principal_ref: str,
    ) -> UserTableViewRead:
        now = datetime.now(UTC)
        view = self.repository.get_table_view(principal_ref)
        values: dict[str, object] = {
            "schema_version": 1,
            "applied_column_keys_json": payload.applied_column_keys,
            "column_widths_json": payload.column_widths,
            "updated_at": now,
        }
        if view is None:
            view = UserTableView(
                id=uuid4(),
                principal_ref=principal_ref,
                page_key="product_management",
                view_key="default",
                created_at=now,
                **values,
            )
            self.repository.add_table_view(view)
        else:
            self.repository.update_record(view, values)
        self.session.commit()
        audit_logger.info("product_table_view_saved actor_ref=%s", principal_ref)
        return self.get_table_view(principal_ref)

    def _recalculate_one(
        self,
        row: ProductManagementProjection,
        rule: ProductPricingRuleVersion,
        *,
        pricing_effective_at: datetime,
        business_month: int,
        run_id: UUID,
        idempotency_key: str,
        reason: str,
        actor_ref: str,
    ) -> int:
        identity, product, current, profile, existing, _, _ = row
        assert product is not None
        fulfillment_rates = tuple(
            self._fulfillment_rate(item) for item in rule.wfs_fulfillment_rates_json
        )
        identity_overrides = tuple(
            self._identity_override(item) for item in rule.identity_wfs_overrides_json
        )
        wfs = select_wfs_fee(
            identity_id=identity.id,
            identity_overrides=identity_overrides,
            # Product listings have no source_account_ref in V1, so their overrides fail closed.
            listing_overrides=(),
            rates=fulfillment_rates,
            gross_weight_kg=profile.product_gross_weight_kg if profile is not None else None,
            dimensions_cm=(
                current.package_length_cm if current is not None else None,
                current.package_width_cm if current is not None else None,
                current.package_height_cm if current is not None else None,
            ),
        )
        storage_rate = self._storage_rate(rule, business_month)
        storage = calculate_storage(
            dimensions_cm=(
                current.package_length_cm if current is not None else None,
                current.package_width_cm if current is not None else None,
                current.package_height_cm if current is not None else None,
            ),
            monthly_rate_usd_per_cuft=storage_rate,
            storage_month_basis_days=rule.storage_month_basis_days,
            pricing_storage_days=rule.pricing_storage_days,
        )
        purchase_cost_cny, purchase_cost_source = self._purchase_cost_cny(
            product, profile, rule.usd_cny_rate
        )
        result = calculate_pricing(
            purchase_cost_cny=purchase_cost_cny,
            gross_weight_kg=profile.product_gross_weight_kg if profile is not None else None,
            wfs=wfs,
            storage=storage,
            rule=self._calculation_rule(rule),
            purchase_cost_source=purchase_cost_source,
        )
        fx = rule.usd_cny_rate
        now = datetime.now(UTC)
        values: dict[str, object] = {
            "product_id": product.id,
            "source_snapshot_id": current.source_snapshot_id if current is not None else None,
            "rule_version_id": rule.id,
            "pricing_effective_at": pricing_effective_at,
            "input_hash": self._input_hash(
                identity.id,
                product,
                current,
                profile,
                rule,
                pricing_effective_at,
            ),
            "calc_version": "product_management_pricing_v1",
            "calculation_status": result.status,
            "wfs_calc_status": wfs.status,
            "wfs_calc_reason": wfs.reason,
            "wfs_fee_source": wfs.source,
            "wfs_fulfillment_fee_usd": wfs.amount if wfs.currency_code == "USD" else None,
            "wfs_fulfillment_fee_cny": (
                wfs.amount
                if wfs.currency_code == "CNY"
                else wfs.amount * fx
                if wfs.amount is not None and fx is not None
                else None
            ),
            "storage_calc_status": storage.status,
            "package_volume_cuft": storage.package_volume_cuft,
            "daily_storage_fee_per_unit_usd": storage.daily_fee_usd,
            "daily_storage_fee_per_unit_cny": (
                storage.daily_fee_usd * fx
                if storage.daily_fee_usd is not None and fx is not None
                else None
            ),
            "estimated_storage_fee_usd": storage.estimated_fee_usd,
            "estimated_storage_fee_cny": (
                storage.estimated_fee_usd * fx
                if storage.estimated_fee_usd is not None and fx is not None
                else None
            ),
            "first_leg_calc_status": result.first_leg_status,
            "first_leg_fee_cny": result.first_leg_fee_cny,
            "suggested_target_margin_rate": rule.suggested_gross_margin_rate,
            "minimum_target_margin_rate": rule.minimum_gross_margin_rate,
            "clearance_target_margin_rate": rule.clearance_gross_margin_rate,
            "suggested_price_usd": result.suggested_price_usd,
            "minimum_price_usd": result.minimum_price_usd,
            "clearance_price_usd": result.clearance_price_usd,
            "price_currency_code": "USD",
            "suggested_gross_margin_rate": result.suggested_gross_margin_rate,
            "suggested_roi": result.suggested_roi,
            "product_grade": result.product_grade,
            "grade_reason": result.grade_reason,
            "commission_source": result.commission_source,
            "pricing_breakdown_json": result.breakdown,
            "recalculation_run_id": run_id,
            "recalculation_idempotency_key": idempotency_key,
            "recalculation_reason": reason,
            "recalculated_by": actor_ref,
            "calculated_at": now,
            "updated_at": now,
        }
        if existing is None:
            self.repository.add_pricing(
                ProductManagementPricingCurrent(
                    id=uuid4(), identity_id=identity.id, created_at=now, **values
                )
            )
        else:
            self.repository.update_record(existing, values)
        return int(result.status != "ok")

    @staticmethod
    def _sku_pricing_rule(rule: ProductPricingRuleVersion | None) -> SkuPricingRule:
        defaults = SkuPricingRule()
        if rule is None:
            return defaults
        return SkuPricingRule(
            usd_cny_rate=(
                rule.usd_cny_rate if rule.usd_cny_rate is not None else defaults.usd_cny_rate
            ),
            first_leg_cost_per_kg_cny=rule.first_leg_cost_per_kg_cny,
            commission_rate=(
                rule.platform_commission_rate
                if rule.platform_commission_rate is not None
                else defaults.commission_rate
            ),
            suggested_margin_rate=rule.suggested_gross_margin_rate,
            minimum_margin_rate=rule.minimum_gross_margin_rate,
            monthly_storage_rate_usd_per_cuft=defaults.monthly_storage_rate_usd_per_cuft,
            storage_month_basis_days=defaults.storage_month_basis_days,
            pricing_storage_days=defaults.pricing_storage_days,
        )

    @staticmethod
    def _sku_rule_account_sets(
        account_refs: frozenset[str], rules: dict[str, SkuPricingRule]
    ) -> tuple[frozenset[str], frozenset[str]]:
        ready: set[str] = set()
        invalid: set[str] = set()
        for account_ref in account_refs:
            rule = rules.get(account_ref, SkuPricingRule())
            if not is_sku_pricing_rule_valid(rule):
                invalid.add(account_ref)
            elif rule.monthly_storage_rate_usd_per_cuft is not None:
                ready.add(account_ref)
        return frozenset(ready), frozenset(invalid)

    @staticmethod
    def _sku_pricing_calculation(
        current: LingxingSkuProductInfoCurrent | None,
        profile: SkuBaseProfileCurrent | None,
        image_count: int,
        rule: SkuPricingRule,
    ) -> SkuPricingResult:
        return calculate_sku_pricing(
            purchase_cost_cny=(
                profile.purchase_cost_cny
                if profile is not None and profile.purchase_cost_cny is not None
                else current.purchase_cost_cny
                if current is not None
                else None
            ),
            product_gross_weight_g=(
                current.product_gross_weight_g if current is not None else None
            ),
            dimensions_cm=(
                current.package_length_cm if current is not None else None,
                current.package_width_cm if current is not None else None,
                current.package_height_cm if current is not None else None,
            ),
            image_count=image_count,
            rule=rule,
        )

    @staticmethod
    def _list_item(
        row: ProductManagementProjection,
        tags: list[ManualProductTag],
        listing_count: int,
        *,
        include_costs: bool,
        source_tags: list[LingxingSkuGlobalTag] | None = None,
        image_count: int = 0,
        calculation: SkuPricingResult | None = None,
        calculation_rule_version: str = "sku-pricing-defaults-v1",
    ) -> ProductManagementListItem:
        identity, product, current, profile, pricing, _, image = row
        calculation = calculation or ProductManagementService._sku_pricing_calculation(
            current, profile, image_count, SkuPricingRule()
        )
        manual_grade = product.grade if product is not None else None
        effective_manual_grade = (
            manual_grade if manual_grade in {"A", "B", "C", "exception"} else "exception"
        )
        return ProductManagementListItem(
            sku_id=identity.id,
            sku=(product.sku if product is not None else identity.lingxing_sku_code),
            product_name=(
                product.product_name
                if product is not None
                else current.product_name
                if current is not None
                else None
            ),
            primary_image=(
                image.pic_url
                if image is not None
                else current.main_image_url
                if current is not None
                else None
            ),
            internal_tags=[ProductManagementService._tag(tag) for tag in tags],
            source_tags=[
                SourceTagRead(
                    source_tag_id=tag.global_tag_id,
                    label=tag.tag_name,
                    color=tag.color,
                )
                for tag in source_tags or []
            ],
            category=product.category if product is not None else None,
            purchase_cost_cny=(calculation.purchase_cost_cny if include_costs else None),
            unit_first_leg_cost=(calculation.first_leg_fee_cny if include_costs else None),
            unit_first_leg_currency_code=(
                "CNY" if include_costs and calculation.first_leg_fee_cny is not None else None
            ),
            purchase_delivery_days=(
                current.purchase_delivery_days if current is not None else None
            ),
            data_quality_score=(profile.data_quality_score if profile is not None else None),
            linked_platform_sku_count=listing_count,
            source_observed_at=(
                current.source_observed_at if current is not None else identity.last_seen_at
            ),
            product_grade=cast(
                Literal["A", "B", "C", "exception"] | None,
                (
                    effective_manual_grade
                    if manual_grade is not None
                    else pricing.product_grade
                    if pricing is not None
                    else None
                ),
            ),
            grade_reason=(
                "manual_product_grade"
                if manual_grade in {"A", "B", "C", "exception"}
                else "invalid_manual_product_grade"
                if manual_grade is not None
                else pricing.grade_reason
                if pricing is not None
                else None
            ),
            wfs_fulfillment_fee=(calculation.wfs_fulfillment_fee_usd if include_costs else None),
            wfs_fulfillment_fee_currency_code=(
                "USD" if include_costs and calculation.wfs_fulfillment_fee_usd is not None else None
            ),
            wfs_daily_storage_fee=(
                calculation.daily_storage_fee_per_unit_usd if include_costs else None
            ),
            wfs_daily_storage_fee_currency_code=(
                "USD"
                if include_costs and calculation.daily_storage_fee_per_unit_usd is not None
                else None
            ),
            suggested_price_usd=(calculation.suggested_price_usd if include_costs else None),
            minimum_price_usd=(calculation.minimum_price_usd if include_costs else None),
            clearance_price_usd=(calculation.clearance_price_usd if include_costs else None),
            price_currency_code=(
                "USD" if include_costs and calculation.suggested_price_usd is not None else None
            ),
            calculation_status=calculation.calculation_status,
            calculated_at=None,
            rule_version=calculation_rule_version,
            costs_visible=include_costs,
            image_count=image_count,
            product_gross_weight_g=(
                current.product_gross_weight_g if current is not None else None
            ),
            gross_weight_kg=calculation.gross_weight_kg,
            package_length_cm=current.package_length_cm if current is not None else None,
            package_width_cm=current.package_width_cm if current is not None else None,
            package_height_cm=current.package_height_cm if current is not None else None,
            first_leg_volume_weight_kg=calculation.first_leg_volume_weight_kg,
            first_leg_chargeable_weight_kg=calculation.first_leg_chargeable_weight_kg,
            first_leg_fee_cny=calculation.first_leg_fee_cny if include_costs else None,
            wfs_actual_weight_lb=calculation.wfs_actual_weight_lb,
            wfs_dimensional_weight_lb=calculation.wfs_dimensional_weight_lb,
            wfs_chargeable_weight_lb=calculation.wfs_chargeable_weight_lb,
            wfs_base_fee_usd=calculation.wfs_base_fee_usd if include_costs else None,
            fixed_cost_usd=calculation.fixed_cost_usd if include_costs else None,
            storage_fee_usd=calculation.storage_fee_usd if include_costs else None,
            root_missing_codes=list(calculation.root_missing_codes),
            pricing_available=calculation.pricing_available,
            billing_root_complete=calculation.billing_root_complete,
            wfs_calc_status=calculation.wfs_calc_status,
            wfs_calc_reason=calculation.wfs_calc_reason,
            storage_calc_status=calculation.storage_calc_status,
            first_leg_calc_status=calculation.first_leg_calc_status,
            formula_version=calculation.formula_version,
            wfs_formula_version=calculation.wfs_formula_version,
        )

    @staticmethod
    def _tag(tag: ManualProductTag) -> InternalTagRead:
        return InternalTagRead(
            key=tag.tag_key,
            label=tag.label,
            color=tag.color,
        )

    @staticmethod
    def _pricing_read(
        sku_id: UUID,
        pricing: ProductManagementPricingCurrent,
        rule: ProductPricingRuleVersion,
        *,
        include_costs: bool,
    ) -> PricingBreakdownRead:
        raw_components = pricing.pricing_breakdown_json.get("components", [])
        components = (
            [CostComponentRead.model_validate(item) for item in raw_components]
            if include_costs and isinstance(raw_components, list)
            else None
        )
        return PricingBreakdownRead(
            sku_id=sku_id,
            calculation_status=pricing.calculation_status,
            wfs_calc_status=pricing.wfs_calc_status,
            wfs_calc_reason=pricing.wfs_calc_reason,
            wfs_fee_source=pricing.wfs_fee_source,
            storage_calc_status=pricing.storage_calc_status,
            first_leg_calc_status=pricing.first_leg_calc_status,
            product_grade=cast(Literal["A", "B", "C", "exception"], pricing.product_grade),
            grade_reason=pricing.grade_reason,
            commission_source=pricing.commission_source,
            rule_version=rule.version,
            calc_version=pricing.calc_version,
            pricing_effective_at=pricing.pricing_effective_at,
            calculated_at=pricing.calculated_at,
            wfs_fulfillment_fee_usd=(pricing.wfs_fulfillment_fee_usd if include_costs else None),
            wfs_fulfillment_fee_cny=(pricing.wfs_fulfillment_fee_cny if include_costs else None),
            package_volume_cuft=pricing.package_volume_cuft if include_costs else None,
            daily_storage_fee_per_unit_usd=(
                pricing.daily_storage_fee_per_unit_usd if include_costs else None
            ),
            daily_storage_fee_per_unit_cny=(
                pricing.daily_storage_fee_per_unit_cny if include_costs else None
            ),
            estimated_storage_fee_usd=(
                pricing.estimated_storage_fee_usd if include_costs else None
            ),
            estimated_storage_fee_cny=(
                pricing.estimated_storage_fee_cny if include_costs else None
            ),
            suggested_price_usd=pricing.suggested_price_usd if include_costs else None,
            minimum_price_usd=pricing.minimum_price_usd if include_costs else None,
            clearance_price_usd=pricing.clearance_price_usd if include_costs else None,
            price_currency_code=(
                cast(Literal["USD"], pricing.price_currency_code) if include_costs else None
            ),
            suggested_gross_margin_rate=(
                pricing.suggested_gross_margin_rate if include_costs else None
            ),
            suggested_roi=pricing.suggested_roi if include_costs else None,
            components=components,
        )

    @staticmethod
    def _sku_pricing_read(
        sku_id: UUID,
        calculation: SkuPricingResult,
        rule: SkuPricingRule,
        *,
        include_costs: bool,
        rule_version: str,
        product_grade: str,
        grade_reason: str,
    ) -> PricingBreakdownRead:
        now = datetime.now(UTC)
        grade = product_grade if product_grade in {"A", "B", "C", "exception"} else "exception"
        return PricingBreakdownRead(
            sku_id=sku_id,
            calculation_status=calculation.calculation_status,
            wfs_calc_status=calculation.wfs_calc_status,
            wfs_calc_reason=calculation.wfs_calc_reason,
            wfs_fee_source="excel_formula",
            storage_calc_status=calculation.storage_calc_status,
            first_leg_calc_status=calculation.first_leg_calc_status,
            product_grade=cast(Literal["A", "B", "C", "exception"], grade),
            grade_reason=grade_reason,
            commission_source="default_business_parameter",
            rule_version=rule_version,
            calc_version=calculation.formula_version,
            pricing_effective_at=now,
            calculated_at=now,
            wfs_fulfillment_fee_usd=(
                calculation.wfs_fulfillment_fee_usd if include_costs else None
            ),
            wfs_fulfillment_fee_cny=None,
            package_volume_cuft=calculation.package_volume_cuft,
            daily_storage_fee_per_unit_usd=(
                calculation.daily_storage_fee_per_unit_usd if include_costs else None
            ),
            daily_storage_fee_per_unit_cny=None,
            estimated_storage_fee_usd=(calculation.storage_fee_usd if include_costs else None),
            estimated_storage_fee_cny=None,
            suggested_price_usd=(calculation.suggested_price_usd if include_costs else None),
            minimum_price_usd=(calculation.minimum_price_usd if include_costs else None),
            clearance_price_usd=(calculation.clearance_price_usd if include_costs else None),
            price_currency_code=(
                "USD" if include_costs and calculation.suggested_price_usd is not None else None
            ),
            suggested_gross_margin_rate=(
                rule.suggested_margin_rate if calculation.pricing_available else None
            ),
            suggested_roi=None,
            components=None,
            purchase_cost_cny=(calculation.purchase_cost_cny if include_costs else None),
            purchase_cost_currency_code=(
                "CNY" if include_costs and calculation.purchase_cost_cny is not None else None
            ),
            product_gross_weight_g=calculation.product_gross_weight_g,
            gross_weight_kg=calculation.gross_weight_kg,
            package_length_cm=calculation.package_length_cm,
            package_width_cm=calculation.package_width_cm,
            package_height_cm=calculation.package_height_cm,
            first_leg_volume_weight_kg=calculation.first_leg_volume_weight_kg,
            first_leg_chargeable_weight_kg=calculation.first_leg_chargeable_weight_kg,
            first_leg_cost_per_kg_cny=(rule.first_leg_cost_per_kg_cny if include_costs else None),
            first_leg_fee_cny=calculation.first_leg_fee_cny if include_costs else None,
            wfs_actual_weight_lb=calculation.wfs_actual_weight_lb,
            wfs_dimensional_weight_lb=calculation.wfs_dimensional_weight_lb,
            wfs_chargeable_weight_lb=calculation.wfs_chargeable_weight_lb,
            wfs_weight_padding_lb=rule.wfs_weight_padding_lb,
            wfs_base_fee_usd=calculation.wfs_base_fee_usd if include_costs else None,
            storage_fee_usd=calculation.storage_fee_usd if include_costs else None,
            fixed_cost_usd=calculation.fixed_cost_usd if include_costs else None,
            usd_cny_rate=rule.usd_cny_rate if include_costs else None,
            commission_rate=rule.commission_rate,
            after_sales_rate=rule.after_sales_rate,
            ad_cost_rate=rule.ad_cost_rate,
            suggested_margin_rate=rule.suggested_margin_rate,
            minimum_margin_rate=rule.minimum_margin_rate,
            root_missing_codes=list(calculation.root_missing_codes),
            pricing_available=calculation.pricing_available,
            billing_root_complete=calculation.billing_root_complete,
            detail_messages=list(calculation.detail_messages),
            formula_version=calculation.formula_version,
            wfs_formula_version=calculation.wfs_formula_version,
        )

    @staticmethod
    def _rule_read(rule: ProductPricingRuleVersion) -> PricingRuleRead:
        return PricingRuleRead(
            id=rule.id,
            rule_key=rule.rule_key,
            source_account_ref=rule.source_account_ref,
            version=rule.version,
            effective_from=rule.effective_from,
            effective_to=rule.effective_to,
            is_active=rule.is_active,
            wfs_source_url=cast(
                Literal["https://marketplace.walmart.com/walmart-fulfillment-services-pricing/"],
                rule.wfs_source_url,
            ),
            wfs_confirmed_at=rule.wfs_confirmed_at,
            wfs_confirmed_by=rule.wfs_confirmed_by,
            wfs_fulfillment_rates=[
                WfsFulfillmentRateConfig.model_validate(item)
                for item in rule.wfs_fulfillment_rates_json
            ],
            wfs_storage_rates=[
                WfsStorageRateConfig.model_validate(item) for item in rule.wfs_storage_rates_json
            ],
            identity_wfs_overrides=[
                IdentityWfsOverrideConfig.model_validate(item)
                for item in rule.identity_wfs_overrides_json
            ],
            storage_month_basis_days=rule.storage_month_basis_days,
            pricing_storage_days=rule.pricing_storage_days,
            include_first_leg_fee=rule.include_first_leg_fee,
            include_wfs_fulfillment_fee=rule.include_wfs_fulfillment_fee,
            include_storage_fee=rule.include_storage_fee,
            other_fixed_cost_cny=rule.other_fixed_cost_cny,
            usd_cny_rate=rule.usd_cny_rate,
            fx_date=rule.fx_date,
            fx_source=rule.fx_source,
            platform_commission_rate=rule.platform_commission_rate,
            first_leg_cost_per_kg_cny=rule.first_leg_cost_per_kg_cny,
            suggested_gross_margin_rate=rule.suggested_gross_margin_rate,
            minimum_gross_margin_rate=rule.minimum_gross_margin_rate,
            clearance_gross_margin_rate=rule.clearance_gross_margin_rate,
            roi_base=cast(Literal["purchase_cost", "total_cost"], rule.roi_base),
            grade_a_min_margin_rate=rule.grade_a_min_margin_rate,
            grade_a_min_roi=rule.grade_a_min_roi,
            grade_b_min_margin_rate=rule.grade_b_min_margin_rate,
            grade_b_min_roi=rule.grade_b_min_roi,
            rounding_mode=cast(Literal["none"], rule.rounding_mode),
            change_reason=rule.change_reason,
            approval_ref=rule.approval_ref,
            approved_by=rule.approved_by,
            approved_at=rule.approved_at,
            actor_ref=rule.actor_ref,
            request_id=rule.request_id,
            action=cast(Literal["publish_pricing_rule"], rule.action),
            status=cast(Literal["succeeded"], rule.status),
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )

    @staticmethod
    def _calculation_rule(rule: ProductPricingRuleVersion) -> PricingRule:
        return PricingRule(
            usd_cny_rate=rule.usd_cny_rate,
            platform_commission_rate=rule.platform_commission_rate,
            first_leg_cost_per_kg_cny=rule.first_leg_cost_per_kg_cny,
            suggested_margin=rule.suggested_gross_margin_rate,
            minimum_margin=rule.minimum_gross_margin_rate,
            clearance_margin=rule.clearance_gross_margin_rate,
            storage_month_basis_days=rule.storage_month_basis_days,
            pricing_storage_days=rule.pricing_storage_days,
            include_first_leg_fee=rule.include_first_leg_fee,
            include_wfs_fulfillment_fee=rule.include_wfs_fulfillment_fee,
            include_storage_fee=rule.include_storage_fee,
            other_fixed_cost_cny=rule.other_fixed_cost_cny,
            roi_base=rule.roi_base,  # type: ignore[arg-type]
            grade_a_min_margin=rule.grade_a_min_margin_rate,
            grade_a_min_roi=rule.grade_a_min_roi,
            grade_b_min_margin=rule.grade_b_min_margin_rate,
            grade_b_min_roi=rule.grade_b_min_roi,
            rounding_mode=rule.rounding_mode,  # type: ignore[arg-type]
        )

    @staticmethod
    def _fulfillment_rate(item: dict[str, object]) -> WfsFulfillmentRate:
        parsed = WfsFulfillmentRateConfig.model_validate(item)
        return WfsFulfillmentRate(
            rate_key=parsed.rate_key,
            amount=parsed.amount,
            currency_code=parsed.currency_code,
            min_weight_kg=parsed.min_weight_kg,
            max_weight_kg=parsed.max_weight_kg,
            max_longest_side_cm=parsed.max_longest_side_cm,
        )

    @staticmethod
    def _identity_override(item: dict[str, object]) -> IdentityWfsOverride:
        parsed = IdentityWfsOverrideConfig.model_validate(item)
        return IdentityWfsOverride(
            identity_id=parsed.identity_id,
            amount=parsed.amount,
            currency_code=parsed.currency_code,
            is_active=parsed.is_active,
        )

    @staticmethod
    def _storage_rate(rule: ProductPricingRuleVersion, month: int) -> Decimal | None:
        matches = [
            parsed.monthly_rate_usd_per_cuft
            for item in rule.wfs_storage_rates_json
            if (parsed := WfsStorageRateConfig.model_validate(item)).month_start
            <= month
            <= parsed.month_end
        ]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _purchase_cost_cny(
        product: Product,
        profile: SkuBaseProfileCurrent | None,
        usd_cny_rate: Decimal | None,
    ) -> tuple[Decimal | None, str]:
        if product.purchase_price is not None:
            if product.currency_code == "CNY":
                return product.purchase_price, "product_core_manual"
            if product.currency_code == "USD" and usd_cny_rate is not None:
                return product.purchase_price * usd_cny_rate, "product_core_manual"
            return None, "product_core_manual_unsupported_currency"
        if profile is not None and profile.purchase_cost_cny is not None:
            return profile.purchase_cost_cny, "lingxing_profile"
        return None, "missing"

    @staticmethod
    def _input_hash(
        identity: UUID,
        product: Product,
        current: LingxingSkuProductInfoCurrent | None,
        profile: SkuBaseProfileCurrent | None,
        rule: ProductPricingRuleVersion,
        pricing_effective_at: datetime,
    ) -> str:
        values = {
            "identity_id": str(identity),
            "product_id": str(product.id),
            "product_updated_at": str(product.updated_at),
            "source_snapshot_id": str(current.source_snapshot_id if current is not None else ""),
            "profile_snapshot_id": str(profile.source_snapshot_id if profile is not None else ""),
            "rule_version_id": str(rule.id),
            "pricing_effective_at": pricing_effective_at.isoformat(),
        }
        return hashlib.sha256(
            json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _recalculation_request_digest(payload: RecalculatePricingRequest) -> str:
        normalized = {
            "source_account_ref": payload.source_account_ref,
            "scope": payload.scope,
            "sku_ids": sorted(str(value) for value in payload.sku_ids),
            "rule_version_id": (
                str(payload.rule_version_id) if payload.rule_version_id is not None else None
            ),
            "effective_at": (
                payload.effective_at.isoformat() if payload.effective_at is not None else None
            ),
            "reason": payload.reason,
            "preview_only": payload.preview_only,
            "max_items": payload.max_items,
        }
        return hashlib.sha256(
            json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _recalculation_replay(
        self,
        run: ProductPricingRecalculationRun,
        request_digest: str,
    ) -> RecalculatePricingResult:
        if run.request_digest != request_digest:
            self._error("IDEMPOTENCY_CONFLICT", 409)
        if run.status == "failed":
            error_code = run.error_code or "RECALCULATION_FAILED"
            status_code = FAILED_RECALCULATION_HTTP_STATUS.get(error_code)
            if status_code is None:
                self._error("RECALCULATION_FAILED", 500)
            self._error(error_code, status_code)
        return self._recalculation_result(run, idempotent_replay=True)

    @staticmethod
    def _recalculation_result(
        run: ProductPricingRecalculationRun,
        *,
        idempotent_replay: bool,
    ) -> RecalculatePricingResult:
        return RecalculatePricingResult(
            run_id=run.id,
            mode=cast(Literal["preview", "execute"], run.mode),
            status=cast(
                Literal["running", "previewed", "succeeded", "partial", "no_items", "failed"],
                run.status,
            ),
            matched_count=run.matched_count,
            eligible_count=run.eligible_count,
            skipped_count=run.skipped_count,
            estimated_affected_count=run.eligible_count,
            affected_count=run.affected_count,
            failed_count=run.failed_count,
            idempotent_replay=idempotent_replay,
        )

    @staticmethod
    def _log_recalculation_run(run: ProductPricingRecalculationRun) -> None:
        audit_logger.info(
            "pricing_recalculation actor_ref=%s request_id=%s source_account_ref=%s "
            "run_id=%s action=%s mode=%s status=%s matched_count=%s eligible_count=%s "
            "affected_count=%s skipped_count=%s failed_count=%s rule_id=%s",
            run.actor_ref,
            run.request_id,
            run.source_account_ref,
            run.id,
            run.action,
            run.mode,
            run.status,
            run.matched_count,
            run.eligible_count,
            run.affected_count,
            run.skipped_count,
            run.failed_count,
            run.pricing_rule_version_id,
        )

    @staticmethod
    def _require_source_account(
        source_account_ref: str,
        account_refs: frozenset[str],
    ) -> None:
        if source_account_ref not in account_refs:
            ProductManagementService._error("DATA_SCOPE_DENIED", 403)

    def _require_projection(
        self, sku_id: UUID, account_refs: frozenset[str]
    ) -> ProductManagementProjection:
        row = self.repository.get_projection(sku_id, account_refs)
        if row is None:
            self._error("NOT_FOUND", 404)
        return row

    @staticmethod
    def _error(code: str, status_code: int) -> Never:
        raise ApiError(code=code, status_code=status_code)

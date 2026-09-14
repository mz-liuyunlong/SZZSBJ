from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, and_, case, func, nulls_last, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.modules.product_management.models import (
    ManualProductTag,
    ManualProductTagAssignment,
    ProductManagementPricingCurrent,
    ProductPricingRecalculationRun,
    ProductPricingRuleVersion,
    UserTableView,
)
from app.modules.products.models import Product, ProductPlatformListing
from app.modules.sku_detail.models import (
    LingxingSkuGlobalTag,
    LingxingSkuIdentity,
    LingxingSkuProductImage,
    LingxingSkuProductInfoCurrent,
    SkuBaseProfileCurrent,
)

type ProductManagementProjection = tuple[
    LingxingSkuIdentity,
    Product | None,
    LingxingSkuProductInfoCurrent | None,
    SkuBaseProfileCurrent | None,
    ProductManagementPricingCurrent | None,
    ProductPricingRuleVersion | None,
    LingxingSkuProductImage | None,
]


class ProductManagementRepository:
    """Scoped persistence boundary; services own permissions and transactions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_projections(
        self,
        *,
        account_refs: frozenset[str],
        page: int,
        page_size: int,
        sku: str | None,
        sku_batch: Sequence[str],
        product_name: str | None,
        category: str | None,
        internal_tag: str | None,
        product_grade: str | None,
        calculation_status: str | None,
        sort_by: str,
        sort_order: str,
        pricing_ready_account_refs: frozenset[str] = frozenset(),
        invalid_pricing_rule_account_refs: frozenset[str] = frozenset(),
    ) -> tuple[list[ProductManagementProjection], int]:
        statement = self._filtered_projection(
            account_refs=account_refs,
            sku=sku,
            sku_batch=sku_batch,
            product_name=product_name,
            category=category,
            internal_tag=internal_tag,
            product_grade=product_grade,
            calculation_status=calculation_status,
            pricing_ready_account_refs=pricing_ready_account_refs,
            invalid_pricing_rule_account_refs=invalid_pricing_rule_account_refs,
        )
        effective_grade = case(
            (Product.grade.in_(("A", "B", "C", "exception")), Product.grade),
            (Product.grade.is_not(None), "exception"),
            else_=ProductManagementPricingCurrent.product_grade,
        )
        effective_sku = func.coalesce(Product.sku, LingxingSkuIdentity.lingxing_sku_code)
        effective_name = func.coalesce(
            Product.product_name,
            LingxingSkuProductInfoCurrent.product_name,
        )
        total = self.session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        sort_columns = {
            "sku": effective_sku,
            "product_name": effective_name,
            "product_grade": effective_grade,
            "calculated_at": ProductManagementPricingCurrent.calculated_at,
        }
        direction = (
            sort_columns[sort_by].desc() if sort_order == "desc" else sort_columns[sort_by].asc()
        )
        rows = self.session.execute(
            statement.order_by(nulls_last(direction), LingxingSkuIdentity.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [tuple(row) for row in rows], int(total or 0)

    def summarize_projections(
        self,
        *,
        account_refs: frozenset[str],
        sku: str | None,
        sku_batch: Sequence[str],
        product_name: str | None,
        category: str | None,
        internal_tag: str | None,
        product_grade: str | None,
        calculation_status: str | None,
        pricing_ready_account_refs: frozenset[str] = frozenset(),
        invalid_pricing_rule_account_refs: frozenset[str] = frozenset(),
    ) -> tuple[int, int, Decimal, int, int, int, int, int, int, int, int, int]:
        missing_purchase, missing_weight, missing_dimensions = self._root_missing_conditions()
        image_count = (
            select(func.count(LingxingSkuProductImage.id))
            .where(
                LingxingSkuProductImage.source_snapshot_id
                == LingxingSkuProductInfoCurrent.source_snapshot_id
            )
            .correlate(LingxingSkuProductInfoCurrent)
            .scalar_subquery()
        )
        has_image = (
            select(LingxingSkuProductImage.id)
            .where(
                LingxingSkuProductImage.source_snapshot_id
                == LingxingSkuProductInfoCurrent.source_snapshot_id
            )
            .correlate(LingxingSkuProductInfoCurrent)
            .exists()
        )
        has_source_tag = (
            select(LingxingSkuGlobalTag.id)
            .where(
                LingxingSkuGlobalTag.source_snapshot_id
                == LingxingSkuProductInfoCurrent.source_snapshot_id
            )
            .correlate(LingxingSkuProductInfoCurrent)
            .exists()
        )
        filtered = self._filtered_projection(
            account_refs=account_refs,
            sku=sku,
            sku_batch=sku_batch,
            product_name=product_name,
            category=category,
            internal_tag=internal_tag,
            product_grade=product_grade,
            calculation_status=calculation_status,
            pricing_ready_account_refs=pricing_ready_account_refs,
            invalid_pricing_rule_account_refs=invalid_pricing_rule_account_refs,
        )
        projections = (
            filtered.with_only_columns(
                LingxingSkuIdentity.id.label("identity_id"),
                LingxingSkuIdentity.source_account_ref.label("source_account_ref"),
                LingxingSkuProductInfoCurrent.id.label("current_id"),
                SkuBaseProfileCurrent.data_quality_score.label("data_quality_score"),
                has_image.label("has_image"),
                has_source_tag.label("has_source_tag"),
                missing_purchase.label("missing_purchase"),
                missing_weight.label("missing_weight"),
                missing_dimensions.label("missing_dimensions"),
                image_count.label("image_count"),
            )
            .order_by(None)
            .distinct()
            .subquery()
        )
        row = self.session.execute(
            select(
                func.count(),
                func.sum(case((projections.c.current_id.is_not(None), 1), else_=0)),
                func.coalesce(func.avg(func.coalesce(projections.c.data_quality_score, 0)), 0),
                func.sum(case((projections.c.has_image.is_(True), 1), else_=0)),
                func.sum(case((projections.c.has_source_tag.is_(True), 1), else_=0)),
                func.sum(
                    case(
                        (
                            or_(
                                projections.c.data_quality_score.is_(None),
                                projections.c.data_quality_score < 100,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                func.sum(case((projections.c.missing_purchase.is_(True), 1), else_=0)),
                func.sum(case((projections.c.missing_weight.is_(True), 1), else_=0)),
                func.sum(case((projections.c.missing_dimensions.is_(True), 1), else_=0)),
                func.sum(case((projections.c.image_count < 2, 1), else_=0)),
                func.sum(
                    case(
                        (
                            projections.c.source_account_ref.in_(invalid_pricing_rule_account_refs),
                            1,
                        ),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (
                            and_(
                                projections.c.missing_purchase.is_(False),
                                projections.c.missing_weight.is_(False),
                                projections.c.missing_dimensions.is_(False),
                                projections.c.source_account_ref.in_(pricing_ready_account_refs),
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
            ).select_from(projections)
        ).one()
        return (
            int(row[0] or 0),
            int(row[1] or 0),
            Decimal(str(row[2] or 0)),
            int(row[3] or 0),
            int(row[4] or 0),
            int(row[5] or 0),
            int(row[6] or 0),
            int(row[7] or 0),
            int(row[8] or 0),
            int(row[9] or 0),
            int(row[10] or 0),
            int(row[11] or 0),
        )

    def get_projection(
        self, sku_id: UUID, account_refs: frozenset[str]
    ) -> ProductManagementProjection | None:
        row = self.session.execute(
            self._projection().where(
                LingxingSkuIdentity.id == sku_id,
                LingxingSkuIdentity.source_account_ref.in_(account_refs),
                LingxingSkuIdentity.is_active.is_(True),
                or_(Product.id.is_(None), Product.deleted_at.is_(None)),
            )
        ).first()
        return None if row is None else tuple(row)

    def list_internal_tags(
        self, product_ids: Sequence[UUID], at: datetime
    ) -> dict[UUID, list[ManualProductTag]]:
        if not product_ids:
            return {}
        rows = self.session.execute(
            select(ManualProductTagAssignment.product_id, ManualProductTag)
            .join(ManualProductTag, ManualProductTag.id == ManualProductTagAssignment.tag_id)
            .where(
                ManualProductTagAssignment.product_id.in_(product_ids),
                ManualProductTagAssignment.effective_from <= at,
                or_(
                    ManualProductTagAssignment.effective_to.is_(None),
                    ManualProductTagAssignment.effective_to > at,
                ),
                ManualProductTag.is_active.is_(True),
            )
            .order_by(ManualProductTag.label, ManualProductTag.id)
        ).all()
        result: dict[UUID, list[ManualProductTag]] = {}
        for product_id, tag in rows:
            result.setdefault(product_id, []).append(tag)
        return result

    def listing_counts(self, product_ids: Sequence[UUID]) -> dict[UUID, int]:
        if not product_ids:
            return {}
        rows = self.session.execute(
            select(ProductPlatformListing.product_id, func.count())
            .where(
                ProductPlatformListing.product_id.in_(product_ids),
                ProductPlatformListing.deleted_at.is_(None),
            )
            .group_by(ProductPlatformListing.product_id)
        ).all()
        return {product_id: int(count) for product_id, count in rows}

    def list_images(self, snapshot_id: UUID) -> list[LingxingSkuProductImage]:
        return list(
            self.session.scalars(
                select(LingxingSkuProductImage)
                .where(LingxingSkuProductImage.source_snapshot_id == snapshot_id)
                .order_by(LingxingSkuProductImage.ordinal, LingxingSkuProductImage.id)
            ).all()
        )

    def list_source_tags(self, snapshot_id: UUID) -> list[LingxingSkuGlobalTag]:
        return list(
            self.session.scalars(
                select(LingxingSkuGlobalTag)
                .where(LingxingSkuGlobalTag.source_snapshot_id == snapshot_id)
                .order_by(LingxingSkuGlobalTag.ordinal, LingxingSkuGlobalTag.id)
            ).all()
        )

    def list_source_tags_for_snapshots(
        self, snapshot_ids: Sequence[UUID]
    ) -> dict[UUID, list[LingxingSkuGlobalTag]]:
        if not snapshot_ids:
            return {}
        rows = self.session.scalars(
            select(LingxingSkuGlobalTag)
            .where(LingxingSkuGlobalTag.source_snapshot_id.in_(snapshot_ids))
            .order_by(
                LingxingSkuGlobalTag.source_snapshot_id,
                LingxingSkuGlobalTag.ordinal,
                LingxingSkuGlobalTag.id,
            )
        ).all()
        result: dict[UUID, list[LingxingSkuGlobalTag]] = {}
        for tag in rows:
            result.setdefault(tag.source_snapshot_id, []).append(tag)
        return result

    def image_counts_for_snapshots(self, snapshot_ids: Sequence[UUID]) -> dict[UUID, int]:
        if not snapshot_ids:
            return {}
        rows = self.session.execute(
            select(LingxingSkuProductImage.source_snapshot_id, func.count())
            .where(LingxingSkuProductImage.source_snapshot_id.in_(snapshot_ids))
            .group_by(LingxingSkuProductImage.source_snapshot_id)
        ).all()
        return {snapshot_id: int(count) for snapshot_id, count in rows}

    def list_active_tags(self) -> list[ManualProductTag]:
        return list(
            self.session.scalars(
                select(ManualProductTag)
                .where(ManualProductTag.is_active.is_(True))
                .order_by(ManualProductTag.label, ManualProductTag.id)
                .limit(500)
            ).all()
        )

    def list_rule_versions(self, source_account_ref: str) -> list[ProductPricingRuleVersion]:
        return list(
            self.session.scalars(
                select(ProductPricingRuleVersion)
                .where(
                    ProductPricingRuleVersion.rule_key == "product_management",
                    ProductPricingRuleVersion.source_account_ref == source_account_ref,
                )
                .order_by(
                    ProductPricingRuleVersion.effective_from.desc(),
                    ProductPricingRuleVersion.created_at.desc(),
                )
                .limit(100)
            ).all()
        )

    def get_rule(self, rule_id: UUID, source_account_ref: str) -> ProductPricingRuleVersion | None:
        return self.session.scalar(
            select(ProductPricingRuleVersion).where(
                ProductPricingRuleVersion.id == rule_id,
                ProductPricingRuleVersion.source_account_ref == source_account_ref,
            )
        )

    def get_effective_rule(
        self, at: datetime, source_account_ref: str
    ) -> ProductPricingRuleVersion | None:
        return self.session.scalar(
            select(ProductPricingRuleVersion)
            .where(
                ProductPricingRuleVersion.rule_key == "product_management",
                ProductPricingRuleVersion.source_account_ref == source_account_ref,
                ProductPricingRuleVersion.is_active.is_(True),
                ProductPricingRuleVersion.effective_from <= at,
                or_(
                    ProductPricingRuleVersion.effective_to.is_(None),
                    ProductPricingRuleVersion.effective_to > at,
                ),
            )
            .order_by(ProductPricingRuleVersion.effective_from.desc())
            .limit(1)
        )

    def list_effective_rules(
        self, at: datetime, account_refs: frozenset[str]
    ) -> dict[str, ProductPricingRuleVersion]:
        rules = self.session.scalars(
            select(ProductPricingRuleVersion)
            .where(
                ProductPricingRuleVersion.rule_key == "product_management",
                ProductPricingRuleVersion.source_account_ref.in_(account_refs),
                ProductPricingRuleVersion.is_active.is_(True),
                ProductPricingRuleVersion.effective_from <= at,
                or_(
                    ProductPricingRuleVersion.effective_to.is_(None),
                    ProductPricingRuleVersion.effective_to > at,
                ),
            )
            .order_by(
                ProductPricingRuleVersion.source_account_ref,
                ProductPricingRuleVersion.effective_from.desc(),
            )
        ).all()
        result: dict[str, ProductPricingRuleVersion] = {}
        for rule in rules:
            result.setdefault(rule.source_account_ref, rule)
        return result

    def lock_rule_versions(self, source_account_ref: str) -> list[ProductPricingRuleVersion]:
        return list(
            self.session.scalars(
                select(ProductPricingRuleVersion)
                .where(
                    ProductPricingRuleVersion.rule_key == "product_management",
                    ProductPricingRuleVersion.source_account_ref == source_account_ref,
                )
                .order_by(ProductPricingRuleVersion.effective_from)
                .with_for_update()
            ).all()
        )

    def add_rule(self, rule: ProductPricingRuleVersion) -> ProductPricingRuleVersion:
        self.session.add(rule)
        self.session.flush()
        return rule

    def get_pricing(self, identity_id: UUID) -> ProductManagementPricingCurrent | None:
        return self.session.scalar(
            select(ProductManagementPricingCurrent).where(
                ProductManagementPricingCurrent.identity_id == identity_id
            )
        )

    def add_pricing(
        self, pricing: ProductManagementPricingCurrent
    ) -> ProductManagementPricingCurrent:
        self.session.add(pricing)
        self.session.flush()
        return pricing

    def update_record[ModelT](self, record: ModelT, values: Mapping[str, object]) -> ModelT:
        for name, value in values.items():
            setattr(record, name, value)
        self.session.flush()
        return record

    def list_recalculation_candidates(
        self,
        *,
        account_refs: frozenset[str],
        scope: str,
        sku_ids: Sequence[UUID],
        limit: int,
    ) -> tuple[list[ProductManagementProjection], int]:
        statement = self._projection().where(
            LingxingSkuIdentity.source_account_ref.in_(account_refs),
            LingxingSkuIdentity.is_active.is_(True),
            LingxingSkuIdentity.mapping_status == "confirmed",
            LingxingSkuIdentity.product_id.is_not(None),
            Product.deleted_at.is_(None),
        )
        if scope == "selected":
            statement = statement.where(LingxingSkuIdentity.id.in_(sku_ids))
        elif scope == "missing_price":
            statement = statement.where(
                or_(
                    ProductManagementPricingCurrent.id.is_(None),
                    ProductManagementPricingCurrent.suggested_price_usd.is_(None),
                )
            )
        elif scope == "pricing_failed":
            statement = statement.where(ProductManagementPricingCurrent.calculation_status != "ok")
        total = self.session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        rows = self.session.execute(statement.order_by(LingxingSkuIdentity.id).limit(limit)).all()
        return [tuple(row) for row in rows], int(total or 0)

    def get_recalculation_run(
        self,
        *,
        principal_ref: str,
        source_account_ref: str,
        mode: str,
        idempotency_key: str,
    ) -> ProductPricingRecalculationRun | None:
        return self.session.scalar(
            select(ProductPricingRecalculationRun).where(
                ProductPricingRecalculationRun.principal_ref == principal_ref,
                ProductPricingRecalculationRun.source_account_ref == source_account_ref,
                ProductPricingRecalculationRun.page_key == "product_management",
                ProductPricingRecalculationRun.capability == "products:pricing:recalculate",
                ProductPricingRecalculationRun.mode == mode,
                ProductPricingRecalculationRun.idempotency_key == idempotency_key,
            )
        )

    def add_recalculation_run(
        self, run: ProductPricingRecalculationRun
    ) -> ProductPricingRecalculationRun:
        self.session.add(run)
        self.session.flush()
        return run

    def get_table_view(self, principal_ref: str) -> UserTableView | None:
        return self.session.scalar(
            select(UserTableView).where(
                UserTableView.principal_ref == principal_ref,
                UserTableView.page_key == "product_management",
                UserTableView.view_key == "default",
            )
        )

    def add_table_view(self, view: UserTableView) -> UserTableView:
        self.session.add(view)
        self.session.flush()
        return view

    @staticmethod
    def _filtered_projection(
        *,
        account_refs: frozenset[str],
        sku: str | None,
        sku_batch: Sequence[str],
        product_name: str | None,
        category: str | None,
        internal_tag: str | None,
        product_grade: str | None,
        calculation_status: str | None,
        pricing_ready_account_refs: frozenset[str] = frozenset(),
        invalid_pricing_rule_account_refs: frozenset[str] = frozenset(),
    ) -> Select[
        tuple[
            LingxingSkuIdentity,
            Product,
            LingxingSkuProductInfoCurrent,
            SkuBaseProfileCurrent,
            ProductManagementPricingCurrent,
            ProductPricingRuleVersion,
            LingxingSkuProductImage,
        ]
    ]:
        effective_grade = case(
            (Product.grade.in_(("A", "B", "C", "exception")), Product.grade),
            (Product.grade.is_not(None), "exception"),
            else_=ProductManagementPricingCurrent.product_grade,
        )
        effective_sku = func.coalesce(Product.sku, LingxingSkuIdentity.lingxing_sku_code)
        effective_name = func.coalesce(
            Product.product_name,
            LingxingSkuProductInfoCurrent.product_name,
        )
        statement = ProductManagementRepository._projection().where(
            LingxingSkuIdentity.source_account_ref.in_(account_refs),
            LingxingSkuIdentity.is_active.is_(True),
            or_(Product.id.is_(None), Product.deleted_at.is_(None)),
        )
        if sku is not None:
            statement = statement.where(effective_sku.contains(sku, autoescape=True))
        if sku_batch:
            statement = statement.where(effective_sku.in_(sku_batch))
        if product_name is not None:
            statement = statement.where(effective_name.contains(product_name, autoescape=True))
        if category is not None:
            statement = statement.where(Product.category.contains(category, autoescape=True))
        if internal_tag is not None:
            tagged_product_ids = (
                select(ManualProductTagAssignment.product_id)
                .join(ManualProductTag)
                .where(
                    or_(
                        ManualProductTag.tag_key == internal_tag,
                        ManualProductTag.label == internal_tag,
                    ),
                    ManualProductTag.is_active.is_(True),
                )
            )
            statement = statement.where(Product.id.in_(tagged_product_ids))
        if product_grade is not None:
            statement = statement.where(effective_grade == product_grade)
        if calculation_status is not None:
            missing_purchase, missing_weight, missing_dimensions = (
                ProductManagementRepository._root_missing_conditions()
            )
            billing_root_complete = and_(
                missing_purchase.is_(False),
                missing_weight.is_(False),
                missing_dimensions.is_(False),
            )
            if calculation_status == "ok":
                statement = statement.where(
                    billing_root_complete,
                    LingxingSkuIdentity.source_account_ref.in_(pricing_ready_account_refs),
                )
            elif calculation_status == "invalid_denominator":
                statement = statement.where(
                    LingxingSkuIdentity.source_account_ref.in_(invalid_pricing_rule_account_refs)
                )
            elif calculation_status == "pricing_unavailable":
                statement = statement.where(
                    or_(missing_purchase, missing_weight, missing_dimensions)
                )
            elif calculation_status == "storage_unavailable":
                statement = statement.where(
                    billing_root_complete,
                    LingxingSkuIdentity.source_account_ref.not_in(pricing_ready_account_refs),
                    LingxingSkuIdentity.source_account_ref.not_in(
                        invalid_pricing_rule_account_refs
                    ),
                )
            else:
                statement = statement.where(
                    ProductManagementPricingCurrent.calculation_status == calculation_status
                )
        return statement

    @staticmethod
    def _root_missing_conditions() -> tuple[
        ColumnElement[bool], ColumnElement[bool], ColumnElement[bool]
    ]:
        return (
            or_(
                func.coalesce(
                    SkuBaseProfileCurrent.purchase_cost_cny,
                    LingxingSkuProductInfoCurrent.purchase_cost_cny,
                ).is_(None),
                func.coalesce(
                    SkuBaseProfileCurrent.purchase_cost_cny,
                    LingxingSkuProductInfoCurrent.purchase_cost_cny,
                )
                <= 0,
            ),
            or_(
                LingxingSkuProductInfoCurrent.product_gross_weight_g.is_(None),
                LingxingSkuProductInfoCurrent.product_gross_weight_g <= 0,
            ),
            or_(
                LingxingSkuProductInfoCurrent.package_length_cm.is_(None),
                LingxingSkuProductInfoCurrent.package_length_cm <= 0,
                LingxingSkuProductInfoCurrent.package_width_cm.is_(None),
                LingxingSkuProductInfoCurrent.package_width_cm <= 0,
                LingxingSkuProductInfoCurrent.package_height_cm.is_(None),
                LingxingSkuProductInfoCurrent.package_height_cm <= 0,
            ),
        )

    @staticmethod
    def _projection() -> Select[
        tuple[
            LingxingSkuIdentity,
            Product,
            LingxingSkuProductInfoCurrent,
            SkuBaseProfileCurrent,
            ProductManagementPricingCurrent,
            ProductPricingRuleVersion,
            LingxingSkuProductImage,
        ]
    ]:
        return (
            select(
                LingxingSkuIdentity,
                Product,
                LingxingSkuProductInfoCurrent,
                SkuBaseProfileCurrent,
                ProductManagementPricingCurrent,
                ProductPricingRuleVersion,
                LingxingSkuProductImage,
            )
            .outerjoin(Product, Product.id == LingxingSkuIdentity.product_id)
            .outerjoin(
                LingxingSkuProductInfoCurrent,
                LingxingSkuProductInfoCurrent.identity_id == LingxingSkuIdentity.id,
            )
            .outerjoin(
                SkuBaseProfileCurrent,
                SkuBaseProfileCurrent.identity_id == LingxingSkuIdentity.id,
            )
            .outerjoin(
                ProductManagementPricingCurrent,
                ProductManagementPricingCurrent.identity_id == LingxingSkuIdentity.id,
            )
            .outerjoin(
                ProductPricingRuleVersion,
                ProductPricingRuleVersion.id == ProductManagementPricingCurrent.rule_version_id,
            )
            .outerjoin(
                LingxingSkuProductImage,
                and_(
                    LingxingSkuProductImage.source_snapshot_id
                    == LingxingSkuProductInfoCurrent.source_snapshot_id,
                    LingxingSkuProductImage.is_primary.is_(True),
                ),
            )
        )

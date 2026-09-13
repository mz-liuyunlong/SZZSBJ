from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, and_, case, func, nulls_last, or_, select
from sqlalchemy.orm import Session

from app.modules.product_management.models import (
    ManualProductTag,
    ManualProductTagAssignment,
    ProductManagementPricingCurrent,
    ProductPricingRecalculationRun,
    ProductPricingRuleVersion,
    UserTableView,
)
from app.modules.products.models import Product
from app.modules.sku_detail.models import (
    LingxingSkuIdentity,
    LingxingSkuProductImage,
    LingxingSkuProductInfoCurrent,
    SkuBaseProfileCurrent,
)

type ProductManagementProjection = tuple[
    LingxingSkuIdentity,
    Product,
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
        product_grade: str | None,
        calculation_status: str | None,
        sort_by: str,
        sort_order: str,
    ) -> tuple[list[ProductManagementProjection], int]:
        effective_grade = case(
            (Product.grade.in_(("A", "B", "C", "exception")), Product.grade),
            (Product.grade.is_not(None), "exception"),
            else_=ProductManagementPricingCurrent.product_grade,
        )
        statement = self._projection().where(
            LingxingSkuIdentity.source_account_ref.in_(account_refs),
            LingxingSkuIdentity.is_active.is_(True),
            LingxingSkuIdentity.mapping_status == "confirmed",
            LingxingSkuIdentity.product_id.is_not(None),
            Product.deleted_at.is_(None),
        )
        if sku is not None:
            statement = statement.where(Product.sku.contains(sku, autoescape=True))
        if sku_batch:
            statement = statement.where(Product.sku.in_(sku_batch))
        if product_name is not None:
            statement = statement.where(
                Product.product_name.contains(product_name, autoescape=True)
            )
        if product_grade is not None:
            statement = statement.where(effective_grade == product_grade)
        if calculation_status is not None:
            statement = statement.where(
                ProductManagementPricingCurrent.calculation_status == calculation_status
            )
        total = self.session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        sort_columns = {
            "sku": Product.sku,
            "product_name": Product.product_name,
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

    def get_projection(
        self, sku_id: UUID, account_refs: frozenset[str]
    ) -> ProductManagementProjection | None:
        row = self.session.execute(
            self._projection().where(
                LingxingSkuIdentity.id == sku_id,
                LingxingSkuIdentity.source_account_ref.in_(account_refs),
                LingxingSkuIdentity.is_active.is_(True),
                LingxingSkuIdentity.mapping_status == "confirmed",
                LingxingSkuIdentity.product_id.is_not(None),
                Product.deleted_at.is_(None),
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

    def list_images(self, snapshot_id: UUID) -> list[LingxingSkuProductImage]:
        return list(
            self.session.scalars(
                select(LingxingSkuProductImage)
                .where(LingxingSkuProductImage.source_snapshot_id == snapshot_id)
                .order_by(LingxingSkuProductImage.ordinal, LingxingSkuProductImage.id)
            ).all()
        )

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
            .join(Product, Product.id == LingxingSkuIdentity.product_id)
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

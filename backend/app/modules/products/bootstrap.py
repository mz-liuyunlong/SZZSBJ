from collections import Counter
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.modules.products.models import Product
from app.modules.products.repository import ProductRepository
from app.modules.sku_detail.models import (
    LingxingSkuIdentity,
    LingxingSkuProductInfoCurrent,
    LingxingSkuProductInfoSnapshot,
    utc_now,
)
from app.modules.sku_detail.repository import SkuDetailRepository

MAPPING_EVIDENCE_REF_MAX_LENGTH = 255


class ProductInfoProductBootstrapError(RuntimeError):
    """Safe bootstrap error containing no source business values."""


@dataclass(frozen=True, slots=True)
class ProductInfoProductBootstrapResult:
    dry_run: bool
    candidates_evaluated: int
    would_create: int
    would_link: int
    created: int
    linked: int
    skipped_missing_sku_code: int
    skipped_missing_product_name: int
    skipped_duplicate_sku_code: int
    skipped_existing_deleted_product: int


class ProductInfoProductBootstrapService:
    """One-time minimal Product bootstrap; Product Core remains manual authority."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.sku_repository = SkuDetailRepository(session)
        self.product_repository = ProductRepository(session)

    def plan(self, source_account_ref: str) -> ProductInfoProductBootstrapResult:
        return self._run(source_account_ref, write=False)

    def execute(
        self,
        source_account_ref: str,
        *,
        authorized: bool = False,
    ) -> ProductInfoProductBootstrapResult:
        if not authorized:
            raise ProductInfoProductBootstrapError("PRODUCT_INFO_BOOTSTRAP_NOT_AUTHORIZED")
        try:
            result = self._run(source_account_ref, write=True)
            self.session.commit()
            return result
        except Exception:
            self.session.rollback()
            raise

    def _run(self, source_account_ref: str, *, write: bool) -> ProductInfoProductBootstrapResult:
        if not source_account_ref or source_account_ref != source_account_ref.strip():
            raise ProductInfoProductBootstrapError("PRODUCT_INFO_BOOTSTRAP_SCOPE_INVALID")
        rows = self.sku_repository.list_product_bootstrap_rows(source_account_ref)
        code_counts = Counter(
            code
            for _, current, _ in rows
            if current is not None and (code := _normalized(current.lingxing_sku_code)) is not None
        )
        counts = {
            "candidates_evaluated": 0,
            "would_create": 0,
            "would_link": 0,
            "created": 0,
            "linked": 0,
            "skipped_missing_sku_code": 0,
            "skipped_missing_product_name": 0,
            "skipped_duplicate_sku_code": 0,
            "skipped_existing_deleted_product": 0,
        }
        for identity, current, snapshot in rows:
            if identity.mapping_status == "confirmed" or identity.product_id is not None:
                continue
            counts["candidates_evaluated"] += 1
            sku_code = None if current is None else _normalized(current.lingxing_sku_code)
            product_name = None if current is None else _normalized(current.product_name)
            if sku_code is None:
                counts["skipped_missing_sku_code"] += 1
                continue
            if product_name is None:
                counts["skipped_missing_product_name"] += 1
                continue
            if len(sku_code) > 128 or len(product_name) > 255:
                raise ProductInfoProductBootstrapError(
                    "PRODUCT_INFO_BOOTSTRAP_FIELD_LENGTH_INVALID"
                )
            if code_counts[sku_code] > 1:
                counts["skipped_duplicate_sku_code"] += 1
                continue
            if snapshot is None:
                raise ProductInfoProductBootstrapError("PRODUCT_INFO_BOOTSTRAP_EVIDENCE_MISSING")
            assert current is not None
            product = self.product_repository.find_product_by_sku(sku_code)
            if product is not None and product.deleted_at is not None:
                counts["skipped_existing_deleted_product"] += 1
                continue
            if product is None:
                counts["would_create"] += 1
                if not write:
                    continue
                product = self.product_repository.add_product(
                    Product(sku=sku_code, product_name=product_name)
                )
                counts["created"] += 1
            else:
                counts["would_link"] += 1
                if not write:
                    continue
                counts["linked"] += 1
            self._confirm_mapping(identity, product, current, snapshot)
        return ProductInfoProductBootstrapResult(dry_run=not write, **counts)

    def _confirm_mapping(
        self,
        identity: LingxingSkuIdentity,
        product: Product,
        current: LingxingSkuProductInfoCurrent,
        snapshot: LingxingSkuProductInfoSnapshot,
    ) -> None:
        evidence_ref = (
            "productinfo_bootstrap:"
            f"{identity.source_account_ref}:{current.source_run_id}:"
            f"{snapshot.id}:{snapshot.parser_version}"
        )
        if len(evidence_ref) > MAPPING_EVIDENCE_REF_MAX_LENGTH:
            raise ProductInfoProductBootstrapError("PRODUCT_INFO_BOOTSTRAP_EVIDENCE_REF_TOO_LONG")
        self.sku_repository.update_record(
            identity,
            {
                "product_id": product.id,
                "mapping_status": "confirmed",
                "mapping_evidence_ref": evidence_ref,
                "updated_at": utc_now(),
            },
        )


def _normalized(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None

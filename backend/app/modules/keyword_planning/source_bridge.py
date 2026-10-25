"""Import already-stored Decodo evidence into scoped keyword snapshots.

No network calls. A Decodo response is source evidence, not a product fact:
the operator must confirm each field and the account/product/listing identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.products.models import Product

from .analysis_execution import _digest
from .models import (
    AiKwProductFactSnapshot,
    BizSkuAsinReference,
    RawKwAsinImage,
    RawKwAsinSnapshot,
    RawKwWalmartPageSnapshot,
)
from .rule_gates import (
    REQUIRED_PRODUCT_FIELDS,
    ProductConfirmation,
    ProductField,
    is_real_text,
    product_confirmation_errors,
)
from .semantic_classifier import parse_reviewed_phrases


class SourceBridgeBlocked(ValueError):
    """Only a safe status code may be exposed by the HTTP boundary."""


@dataclass(frozen=True)
class ConfirmedFieldInput:
    value: str
    source: str


def _stored_decodo(
    session: Session, snapshot_id: UUID, target: str, product_id: UUID, identifier: str
) -> tuple[dict, datetime]:
    row = session.execute(
        text("""
        SELECT payload, fetched_at FROM decodo_product_snapshots
         WHERE id = :snapshot_id AND target = :target
           AND sku_id = :product_id AND identifier = :identifier
    """),
        {
            "snapshot_id": snapshot_id,
            "target": target,
            "product_id": str(product_id),
            "identifier": identifier,
        },
    ).first()
    if row is None:
        raise SourceBridgeBlocked("STORED_SOURCE_DATA_UNAVAILABLE")
    payload = row.payload
    if not isinstance(payload, dict) or payload.get("verified") is not True:
        raise SourceBridgeBlocked("STORED_SOURCE_NOT_VERIFIED")
    return payload, row.fetched_at


def _product_listing(
    session: Session, account: str, product_id: UUID, item_id: str
) -> tuple[Product, ListingManagementCurrentMart]:
    product = session.get(Product, product_id)
    if product is None or product.deleted_at is not None:
        raise SourceBridgeBlocked("PRODUCT_NOT_FOUND")
    matches = list(
        session.scalars(
            select(ListingManagementCurrentMart)
            .where(
                ListingManagementCurrentMart.source_account_ref == account,
                ListingManagementCurrentMart.item_id == item_id,
                ListingManagementCurrentMart.local_sku == product.sku,
            )
            .limit(2)
        )
    )
    if len(matches) != 1:
        raise SourceBridgeBlocked("ACCOUNT_PRODUCT_ITEM_IDENTITY_UNVERIFIED")
    return product, matches[0]


def _walmart_source_fields(payload: dict) -> dict[str, str]:
    attributes = payload.get("attributes")
    attrs = (
        {str(k).casefold(): str(v).strip() for k, v in attributes.items()}
        if isinstance(attributes, dict)
        else {}
    )
    category = payload.get("category_path")
    item_type = category[-1] if isinstance(category, list) and category else ""

    def attr(*keys: str) -> str:
        return next((attrs[key.casefold()] for key in keys if attrs.get(key.casefold())), "")

    return {
        "title": str(payload.get("title") or "").strip(),
        "item_type": str(item_type).strip(),
        "brand": str(payload.get("brand") or "").strip(),
        "material": attr("Material"),
        "color": attr("Color"),
        "pack": attr("Pack Size", "Pack Quantity", "Package Quantity"),
        "size": attr("Dimensions", "Product Dimensions", "Size"),
        "structure": attr("Included Components", "Package Contents"),
        "use": attr("Recommended Uses", "Recommended Uses for Product", "Usage", "Uses"),
    }


def confirm_stored_walmart_product(
    session: Session,
    *,
    account: str,
    product_id: UUID,
    item_id: str,
    decodo_snapshot_id: UUID,
    fields: dict[str, ConfirmedFieldInput],
    risk_mode: str,
    risk_acknowledged: bool,
    actor: str,
    semantic_phrases: list[dict] | None = None,
) -> tuple[UUID, UUID]:
    """Freeze independently matched page text and operator-confirmed facts."""
    if not account or not actor or set(fields) != set(REQUIRED_PRODUCT_FIELDS):
        raise SourceBridgeBlocked("PRODUCT_CONFIRMATION_INCOMPLETE")
    if risk_mode not in ("provided", "none") or not risk_acknowledged:
        raise SourceBridgeBlocked("RISK_BOUNDARY_NOT_REVIEWED")
    if not item_id.isascii() or not item_id.isdigit():
        raise SourceBridgeBlocked("WALMART_ITEM_ID_INVALID")
    phrases = parse_reviewed_phrases(semantic_phrases or [])
    if len(phrases) != len(semantic_phrases or []):
        raise SourceBridgeBlocked("SEMANTIC_PHRASE_EVIDENCE_INVALID")
    with session.begin():
        product, listing = _product_listing(session, account, product_id, item_id)
        payload, observed_at = _stored_decodo(
            session,
            decodo_snapshot_id,
            "walmart_product",
            product_id,
            item_id,
        )
        if payload.get("item_id") != item_id or payload.get("sku_id") != str(product_id):
            raise SourceBridgeBlocked("STORED_ITEM_ID_MISMATCH")
        source_values = _walmart_source_fields(payload)
        mapped: dict[str, ProductField] = {}
        for name in REQUIRED_PRODUCT_FIELDS:
            field = fields[name]
            if field.source not in ("walmart", "operator", "product_management"):
                raise SourceBridgeBlocked("PRODUCT_FIELD_SOURCE_INVALID")
            if not is_real_text(field.value):
                raise SourceBridgeBlocked("PRODUCT_REQUIRED_FIELD_MISSING")
            if field.source == "walmart" and field.value.strip() != source_values.get(name):
                raise SourceBridgeBlocked("WALMART_FIELD_NOT_IN_SOURCE")
            if field.source == "product_management":
                allowed = {
                    "title": product.product_name,
                    "item_type": product.product_type,
                    "material": product.material_en,
                }
                if field.value.strip() != allowed.get(name):
                    raise SourceBridgeBlocked("PRODUCT_FIELD_NOT_IN_SOURCE")
            mapped[name] = ProductField(
                field.value.strip(),
                field.source,
                f"decodo:{decodo_snapshot_id}:{name}"
                if field.source == "walmart"
                else f"product:{product_id}:{name}"
                if field.source == "product_management"
                else f"operator:{actor}:decodo:{decodo_snapshot_id}:{name}",
            )
        confirmation = ProductConfirmation(
            item_id,
            True,
            item_id,
            mapped,
            risk_acknowledged,
            risk_mode,
        )
        if product_confirmation_errors(confirmation):
            raise SourceBridgeBlocked("PRODUCT_CONFIRMATION_INVALID")
        page = RawKwWalmartPageSnapshot(
            source_account_ref=account,
            product_id=product_id,
            item_id=item_id,
            store_id=listing.store_id,
            verification_status="verified",
            fetch_provider="decodo_stored",
            provider_observed_at=observed_at,
            page_title=payload.get("title"),
            description_text=payload.get("description"),
            features_json=[],
            attributes_json=payload.get("attributes") or {},
            page_images_json=[
                url
                for url in [payload.get("main_image"), *(payload.get("gallery_images") or [])]
                if isinstance(url, str)
            ],
            raw_object_key=f"decodo-snapshot://{decodo_snapshot_id}",
            evidence_hash=_digest(payload),
        )
        session.add(page)
        session.flush()
        document: dict[str, object] = {
            name: {"value": field.value, "source": field.source, "evidence_ref": field.evidence_ref}
            for name, field in mapped.items()
        }
        document["risk_boundary"] = {
            "mode": risk_mode,
            "acknowledged": risk_acknowledged,
        }
        document["semantic_phrases"] = [
            {
                "phrase": phrase.phrase,
                "keyword_type": phrase.keyword_type,
                "evidence_ref": f"operator:{actor}:{phrase.evidence_ref}",
                "hard_risk_proven": phrase.hard_risk_proven,
                "page_phrase": phrase.page_phrase,
            }
            for phrase in phrases
        ]
        fact = AiKwProductFactSnapshot(
            source_account_ref=account,
            product_id=product_id,
            walmart_page_snapshot_id=page.id,
            item_id=item_id,
            item_verified=True,
            status="confirmed",
            facts_with_sources_json=document,
            facts_sha256=_digest(document),
            missing_required_json=[],
            confirmed_by=actor,
            confirmed_at=datetime.now(UTC),
        )
        session.add(fact)
        session.flush()
        return fact.id, page.id


def import_stored_asin(
    session: Session,
    *,
    account: str,
    product_id: UUID,
    asin: str,
    decodo_snapshot_id: UUID,
    actor: str,
) -> tuple[UUID, int]:
    """Append one normalized ASIN snapshot and every available image in order."""
    if not asin.isascii() or len(asin) != 10 or not asin.isalnum():
        raise SourceBridgeBlocked("ASIN_FORMAT_INVALID")
    asin = asin.upper()
    with session.begin():
        if not session.scalar(
            select(AiKwProductFactSnapshot.id)
            .where(
                AiKwProductFactSnapshot.product_id == product_id,
                AiKwProductFactSnapshot.source_account_ref == account,
                AiKwProductFactSnapshot.status == "confirmed",
            )
            .limit(1)
        ):
            raise SourceBridgeBlocked("PRODUCT_FACT_NOT_VERIFIED")
        payload, fetched_at = _stored_decodo(
            session,
            decodo_snapshot_id,
            "amazon_product",
            product_id,
            asin,
        )
        if payload.get("asin") != asin:
            raise SourceBridgeBlocked("STORED_ASIN_MISMATCH")
        if not is_real_text(payload.get("title")):
            raise SourceBridgeBlocked("STORED_ASIN_TITLE_MISSING")
        item = RawKwAsinSnapshot(
            source_account_ref=account,
            asin=asin,
            fetch_status="succeeded",
            fetch_provider="decodo_stored",
            title=payload["title"],
            brand=payload.get("brand"),
            features_json=payload.get("bullet_points") or [],
            description_text=payload.get("description"),
            raw_object_key=f"decodo-snapshot://{decodo_snapshot_id}",
            response_hash=_digest(payload),
            fetched_at=fetched_at,
        )
        session.add(item)
        session.flush()
        images = [payload.get("main_image"), *(payload.get("gallery_images") or [])]
        for index, url in enumerate(images):
            if isinstance(url, str) and url.startswith("https://"):
                session.add(
                    RawKwAsinImage(
                        source_account_ref=account,
                        asin_snapshot_id=item.id,
                        image_index=index,
                        image_url=url,
                    )
                )
        prior = session.scalar(
            select(BizSkuAsinReference)
            .where(
                BizSkuAsinReference.product_id == product_id,
                BizSkuAsinReference.asin == asin,
                BizSkuAsinReference.reference_role == "competitor",
            )
            .with_for_update()
        )
        if prior is None:
            session.add(
                BizSkuAsinReference(
                    source_account_ref=account,
                    product_id=product_id,
                    asin=asin,
                    reference_role="competitor",
                    is_active=True,
                    latest_snapshot_id=item.id,
                    selected_by=actor,
                )
            )
        else:
            if prior.source_account_ref != account:
                raise SourceBridgeBlocked("ASIN_ACCOUNT_CONFLICT")
            prior.latest_snapshot_id = item.id
            prior.is_active = True
        session.flush()
        return item.id, sum(isinstance(url, str) and url.startswith("https://") for url in images)

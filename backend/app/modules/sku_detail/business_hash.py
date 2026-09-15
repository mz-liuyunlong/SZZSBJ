"""Deterministic business-content hash for Lingxing ProductInfo.

Only normalized business fields participate. Execution metadata such as run IDs,
RAW references, timestamps, database UUIDs, and lineage IDs are intentionally
excluded.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from app.modules.integration_sync.parsers.lingxing_product_info import ParsedSkuDetail

BUSINESS_HASH_SCHEMA = "lingxing.product-info.business.v1"

type CanonicalScalar = str | int | bool | None
type CanonicalValue = CanonicalScalar | list[CanonicalValue] | dict[str, CanonicalValue]


def product_info_business_hash(parsed: ParsedSkuDetail) -> str:
    payload = _business_payload(parsed)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _business_payload(parsed: ParsedSkuDetail) -> dict[str, CanonicalValue]:
    detail = parsed.model_dump(mode="python", exclude={"images", "tags"})
    images = [
        {
            "ordinal": image.ordinal,
            "pic_url": image.pic_url,
            "is_primary": image.is_primary,
        }
        for image in sorted(parsed.images, key=lambda item: item.ordinal)
    ]
    tags = [
        {
            "global_tag_id": tag.global_tag_id,
            "tag_name": tag.tag_name,
            "color": tag.color,
        }
        for tag in parsed.tags
    ]
    tags.sort(key=_canonical_sort_key)
    return {
        "schema": BUSINESS_HASH_SCHEMA,
        "detail": _canonicalize(detail),
        "images": _canonicalize(images),
        "tags": _canonicalize(tags),
    }


def _canonical_sort_key(value: object) -> str:
    return json.dumps(
        _canonicalize(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _canonicalize(value: object) -> CanonicalValue:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Decimal):
        return _canonical_decimal(value)
    if isinstance(value, dict):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    raise TypeError(f"Unsupported business hash value type: {type(value).__name__}")


def _canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("ProductInfo business hash requires finite Decimal values")
    if value.is_zero():
        return "0"
    return format(value.normalize(), "f")

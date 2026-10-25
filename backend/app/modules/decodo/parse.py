"""Map two Decodo structured-JSON formats into narrow product evidence DTOs."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any

from app.modules.decodo.schemas import AmazonEvidenceRead, WalmartFactRead


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("li", "p", "br", "ul"):
            self.parts.append("\n")


def clean_text(raw: Any) -> str:
    if not isinstance(raw, str):
        return ""
    parser = _TextParser()
    parser.feed(raw)
    return re.sub(r"\n{3,}", "\n\n", unescape("".join(parser.parts))).strip()


def product_images(raw: Any) -> tuple[str | None, list[str]]:
    if not isinstance(raw, list):
        return None, []
    urls = list(dict.fromkeys(x for x in raw if isinstance(x, str) and x.startswith("https://")))
    return (urls[0] if urls else None), urls[1:]


def amazon_document(result: dict[str, Any], requested_asin: str) -> AmazonEvidenceRead:
    asin = str(result.get("asin") or "").strip().upper()
    if asin != requested_asin.upper() or str(result.get("asin_in_url") or asin).upper() != asin:
        raise ValueError("IDENTIFIER_MISMATCH")
    title = clean_text(result.get("title"))
    if not title:
        raise ValueError("TITLE_MISSING")
    raw_bullets = result.get("bullet_points")
    if isinstance(raw_bullets, list):
        bullets = [clean_text(x) for x in raw_bullets]
    else:
        bullets = [clean_text(x) for x in str(raw_bullets or "").splitlines()]
    bullets = [x for x in bullets if x]
    category = result.get("category") or []
    path: list[str] = []
    for group in category if isinstance(category, list) else []:
        if isinstance(group, dict):
            ladder = group.get("ladder") or []
            names = [str(x["name"]) for x in ladder if isinstance(x, dict) and x.get("name")]
            if len(names) > len(path):
                path = names
    details = result.get("product_details") or {}
    attrs = (
        {
            str(k): str(v)
            for k, v in details.items()
            if isinstance(v, (str, int, float)) and v not in ("", None)
        }
        if isinstance(details, dict)
        else {}
    )
    # Exclude explicitly unneeded commerce metrics from standardized output.
    attrs = {
        k: v for k, v in attrs.items() if k not in {"best_sellers_rank", "customer_reviews", "asin"}
    }
    main, gallery = product_images(result.get("images"))
    return AmazonEvidenceRead(
        asin=asin,
        title=title,
        brand=result.get("brand"),
        manufacturer=result.get("manufacturer"),
        bullet_points=bullets,
        description=clean_text(result.get("description")) or None,
        category_path=path,
        attributes=attrs,
        main_image=main,
        gallery_images=gallery,
        url=result.get("url"),
        fetched_at=datetime.now(UTC),
    )


def walmart_document(result: dict[str, Any], requested_item: str, sku_id: str) -> WalmartFactRead:
    general = result.get("general") or {}
    if not isinstance(general, dict):
        raise ValueError("PRODUCT_MISSING")
    meta = general.get("meta") or {}
    actual = str(meta.get("sku") or "").strip() if isinstance(meta, dict) else ""
    url = str(general.get("url") or "")
    url_id = re.search(r"/([0-9]+)(?:[/?#]|$)", url)
    if actual != requested_item or (url_id and url_id.group(1) != requested_item):
        raise ValueError("IDENTIFIER_MISMATCH")
    title = clean_text(general.get("title"))
    if not title:
        raise ValueError("TITLE_MISSING")
    attributes = {}
    for spec in result.get("specifications") or []:
        if isinstance(spec, dict) and spec.get("key") is not None and spec.get("value") is not None:
            attributes[str(spec["key"]).strip()] = str(spec["value"]).strip()
    category = [
        str(x["category_name"])
        for x in result.get("breadcrumbs") or []
        if isinstance(x, dict) and x.get("category_name")
    ]
    images = general.get("images") or []
    main = general.get("main_image")
    if not isinstance(main, str) or not main.startswith("https://"):
        main = None
    gallery = list(
        dict.fromkeys(
            x for x in images if isinstance(x, str) and x.startswith("https://") and x != main
        )
    )
    seller = result.get("seller") or {}
    return WalmartFactRead(
        item_id=requested_item,
        sku_id=sku_id,
        title=title,
        brand=general.get("brand"),
        gtin=str(meta.get("gtin")) if isinstance(meta, dict) and meta.get("gtin") else None,
        seller_name=str(seller.get("name"))
        if isinstance(seller, dict) and seller.get("name")
        else None,
        description=clean_text(general.get("description")) or None,
        category_path=category,
        attributes=attributes,
        main_image=main,
        gallery_images=gallery,
        url=url,
        fetched_at=datetime.now(UTC),
    )

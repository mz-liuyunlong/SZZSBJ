"""Exact-value Listing facets; read-only, shared by options and row predicates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import (
    Date,
    Numeric,
    String,
    and_,
    case,
    cast,
    column,
    exists,
    func,
    literal,
    literal_column,
    not_,
    or_,
    select,
    true,
    union_all,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.modules.data_pages.models import (
    ListingArchiveState,
    ListingGptAnalysisLink,
    ProductCustomTag,
    ProductCustomTagAssignment,
)

FACET_FIELDS = (
    "store",
    "owner",
    "archiveStatus",
    "productTags",
    "tags",
    "lifecycle",
    "productGrade",
    "image",
    "productId",
    "productName",
    "sku",
    "msku",
    "title",
    "imageCount",
    "category",
    "keyFeatures",
    "listPrice",
    "hasStrikethrough",
    "salePrice",
    "wfsAvailableInventory",
    "inboundInventory",
    "listedAt",
    "sales90Days",
    "adSpend30Days",
    "disabledReason",
    "listingStatus",
    "buyBoxStatus",
    "rating",
    "reviewCount",
    "brand",
    "walmartSeller",
    "sellerOfferCount",
    "sellerNames",
    "resold",
    "checkedAt",
    "fulfillmentMethod",
    "gtin",
    "gptAnalysis",
    "archiveReason",
)
MISSING = "n:"
VALUE_PREFIX = "v:"
NUMERIC_FIELDS = frozenset(
    {
        "imageCount",
        "listPrice",
        "salePrice",
        "wfsAvailableInventory",
        "inboundInventory",
        "sales90Days",
        "adSpend30Days",
        "rating",
        "reviewCount",
        "sellerOfferCount",
    }
)
DATE_FIELDS = frozenset({"listedAt", "checkedAt"})
MISSING_LABELS = {
    "listPrice": "无划线价或待检测",
    "salePrice": "无售价",
    "listedAt": "未上架",
    "checkedAt": "未检测",
    "rating": "无评分",
    "reviewCount": "无评论数据",
    "sellerOfferCount": "待检测",
    "imageCount": "待检测",
    "sellerNames": "无卖家数据",
    "keyFeatures": "无五点描述数据",
    "productTags": "无产品标签",
    "tags": "无自定义标签",
    "disabledReason": "无停用原因",
    "archiveReason": "无归档原因",
}


def parse_exact_filters(raw: str) -> dict[str, list[str]]:
    if not raw:
        return {}
    if len(raw) > 1_000_000:
        raise ValueError("exact filters exceed 1 MB")
    try:
        obj = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("exact filters must be a JSON object") from exc
    if not isinstance(obj, dict) or len(obj) > len(FACET_FIELDS):
        raise ValueError("invalid exact filter object")
    result = {}
    for field, values in obj.items():
        if field not in FACET_FIELDS or not isinstance(values, list) or len(values) > 20000:
            raise ValueError("invalid exact filter field or selection count")
        if any(
            not isinstance(value, str)
            or len(value) > 32768
            or (value != MISSING and not value.startswith(VALUE_PREFIX))
            for value in values
        ):
            raise ValueError("invalid exact filter value")
        for value in values:
            if value == MISSING:
                continue
            try:
                decoded = json.loads(value[len(VALUE_PREFIX) :])
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid exact value token") from exc
            if not isinstance(decoded, str) or "\x00" in decoded:
                raise ValueError("invalid exact value token")
        if values:
            result[field] = list(dict.fromkeys(values))
    if sum(len(values) for values in result.values()) > 20000:
        raise ValueError("too many selected exact values")
    return result


def _nonblank(value: Any) -> Any:
    # Preserve the actual stored text, including internal spaces and commas.
    return case((func.trim(value) != "", value), else_=None)


def _array(raw: Any, name: str | None = None) -> Any:
    val = func.jsonb_extract_path(raw, name) if name else raw
    return case((func.jsonb_typeof(val) == "array", val), else_=cast(literal("[]"), JSONB))


def _json_strings(raw: Any, name: str | None = None, key: str | None = None) -> Any:
    items = (
        func.jsonb_array_elements(_array(raw, name)).table_valued(column("value", JSONB)).alias()
    )
    item = items.c.value
    if key:
        value = func.jsonb_extract_path_text(item, key)
        kind = func.jsonb_typeof(func.jsonb_extract_path(item, key))
    else:
        value = item.op("#>>")(literal_column("'{}'::text[]"))
        kind = func.jsonb_typeof(item)
    value = func.trim(cast(value, String))
    return select(value.label("value")).select_from(items).where(kind == "string", value != "")


def _raw_integer(raw: Any, key: str) -> Any:
    value = func.trim(func.jsonb_extract_path_text(raw, key))
    # Match non-negative integer strings/numbers only, not booleans/decimals.
    return case(
        (
            and_(
                func.jsonb_typeof(func.jsonb_extract_path(raw, key)).in_(["number", "string"]),
                value.op("~")(r"^\+?[0-9]+$"),
                func.length(value) <= 30,
            ),
            cast(value, Numeric),
        ),
        else_=None,
    )


def _boolean(raw: Any, key: str, yes: str, no: str) -> Any:
    value = func.jsonb_extract_path_text(raw, key)
    return case(
        (
            func.jsonb_typeof(func.jsonb_extract_path(raw, key)) == "boolean",
            case((value == "true", yes), (value == "false", no), else_=None),
        ),
        else_=None,
    )


def _archive_value(c: Any, name: str) -> Any:
    return (
        select(getattr(ListingArchiveState, name))
        .where(
            ListingArchiveState.listing_id == c["id"],
            ListingArchiveState.source_account_ref == c["source_account_ref"],
        )
        .correlate_except(ListingArchiveState)
        .scalar_subquery()
    )


@dataclass(frozen=True)
class Facet:
    scalar: Any = None
    members: Any = None


def listing_facet(
    c: Any,
    field: str,
    exception_condition: Any,
    cart_exception_condition: Any,
    no_strike_condition: Any,
) -> Facet:
    raw = c["monitor_raw_parsed"]
    if field == "sellerNames":
        return Facet(members=_json_strings(raw, "sellerNames"))
    if field == "keyFeatures":
        return Facet(members=_json_strings(raw, "keyFeatures"))
    if field == "productTags":
        return Facet(members=_json_strings(c["product_tags_json"], key="label"))
    if field == "tags":
        a, t = ProductCustomTagAssignment, ProductCustomTag
        return Facet(
            members=select(t.name.label("value"))
            .select_from(a)
            .join(t, t.id == a.tag_id)
            .where(
                a.source_account_ref == c["source_account_ref"],
                a.item_id == c["item_id"],
                t.deleted_at.is_(None),
                t.is_active.is_(True),
            )
            .correlate_except(a, t)
        )

    # Compute only the requested scalar; avoid unnecessary subqueries for other fields.
    direct = {
        "productId": "item_id",
        "sku": "local_sku",
        "msku": "msku",
        "category": "effective_category",
        "listedAt": "first_wfs_available_date_la",
        "disabledReason": "disabled_reason",
        "brand": "effective_brand",
        "walmartSeller": "effective_walmart_seller",
        "gtin": "gtin",
        "reviewCount": "effective_review_count",
    }
    if field in direct:
        val = c[direct[field]]
        return Facet(scalar=_nonblank(val) if field not in {"listedAt", "reviewCount"} else val)
    money = {
        "listPrice": "effective_strike_price_amount",
        "salePrice": "effective_sale_price_amount",
        "adSpend30Days": "ad_spend_30d_amount",
        "rating": "effective_average_rating",
        "sales90Days": "sales_30d",
        "inboundInventory": "inbound_quantity",
        "wfsAvailableInventory": "wfs_available_quantity",
    }
    if field in money:
        # Exact persisted value: do not round, bucket or turn missing data into zero.
        return Facet(scalar=c[money[field]])
    if field == "store":
        return Facet(scalar=func.coalesce(c["store_name"], c["store_id"]))
    if field == "owner":
        return Facet(scalar=func.coalesce(c["owner_name"], c["owner_ref"], "未分配"))
    if field == "archiveStatus":
        return Facet(
            scalar=case((_archive_value(c, "is_archived").is_(True), "已归档"), else_="未归档")
        )
    if field == "archiveReason":
        return Facet(scalar=_nonblank(_archive_value(c, "archive_reason")))
    if field == "lifecycle":
        return Facet(scalar=func.coalesce(c["effective_lifecycle_status"], "待判定"))
    if field == "productGrade":
        return Facet(
            scalar=case(
                (c["product_grade"] == "", "待评级"),
                else_=func.coalesce(c["product_grade"], "未分级"),
            )
        )
    if field == "productName":
        return Facet(scalar=func.coalesce(c["local_name"], c["effective_title"]))
    if field == "title":
        return Facet(scalar=func.coalesce(c["effective_title"], c["local_name"]))
    if field in {"image", "imageCount"}:
        images = _json_strings(raw, "productImageUrls")
        observed = func.jsonb_typeof(func.jsonb_extract_path(raw, "productImageUrls")) == "array"
        if field == "image":
            return Facet(
                scalar=case(
                    (observed, case((exists(images), "有"), else_="无")),
                    (_nonblank(c["picture_url"]).is_not(None), "有"),
                    else_="无",
                )
            )
        raw_count = _raw_integer(raw, "productImageCount")
        count = images.with_only_columns(func.count(), maintain_column_froms=True).scalar_subquery()
        return Facet(scalar=func.coalesce(raw_count, case((observed, count), else_=None)))
    if field == "sellerOfferCount":
        return Facet(scalar=_raw_integer(raw, "sellerOfferCount"))
    if field == "hasStrikethrough":
        return Facet(scalar=func.coalesce(_boolean(raw, "hasStrikethrough", "有", "无"), "待检测"))
    if field == "resold":
        return Facet(
            scalar=case(
                (c["effective_is_hijacked"].is_(True), "是"),
                (c["effective_is_hijacked"].is_(False), "否"),
                else_="待检测",
            )
        )
    if field in {"buyBoxStatus", "listingStatus"}:
        cart = c["effective_buybox_status"]
        key = func.upper(func.trim(func.coalesce(cart, "")))
        if field == "buyBoxStatus":
            return Facet(
                scalar=case(
                    (key.in_(["NORMAL", "正常"]), "正常"),
                    (key.in_(["PRIMARY", "WON", "WINNING", "OWNED", "拥有"]), "拥有"),
                    (key == "LOST", "购物车丢失"),
                    (key.in_(["NOT_OWNED", "SECONDARY", "OTHER", "未拥有"]), "未拥有购物车"),
                    (key.in_(["NOT_FOUND", "CART_NOT_FOUND"]), "未找到购物车"),
                    (key == "OUT_OF_STOCK", "缺货"),
                    (key == "UNAVAILABLE", "不可购买"),
                    (key.in_(["FETCH_ERROR", "ERROR", "TIMEOUT"]), "检测失败"),
                    else_="待确认",
                )
            )
        stock = c["wfs_available_quantity"]
        hijacked = c["effective_is_hijacked"]
        bad = exception_condition(
            no_strike_condition(raw), cart_exception_condition(cart), hijacked, stock
        )
        good = and_(
            _boolean(raw, "hasStrikethrough", "有", "无") == "有",
            hijacked.is_(False),
            key.in_(
                ["NORMAL", "正常", "PRIMARY", "WON", "WINNING", "OWNED", "拥有", "OUT_OF_STOCK"]
            ),
        )
        return Facet(
            scalar=case(
                (func.coalesce(stock, 0) <= 0, "无库存"),
                (bad, "异常"),
                (good, "正常"),
                else_="待确认",
            )
        )
    if field == "checkedAt":
        return Facet(scalar=cast(func.timezone("Asia/Shanghai", c["monitor_checked_at"]), Date))
    if field == "fulfillmentMethod":
        return Facet(
            scalar=func.coalesce(
                _nonblank(func.trim(c["fulfillment_type_name"])),
                _nonblank(func.trim(c["fulfillment_type"])),
                "待确认",
            )
        )
    if field == "gptAnalysis":
        link = ListingGptAnalysisLink
        configured = exists(
            select(1)
            .where(
                link.listing_id == c["id"],
                link.source_account_ref == c["source_account_ref"],
                or_(
                    func.trim(link.keyword_analysis_url) != "",
                    func.trim(link.ad_analysis_url) != "",
                ),
            )
            .correlate_except(link)
        )
        return Facet(scalar=case((configured, "已配置"), else_="未配置"))
    raise ValueError("unknown exact facet field")


def facet_predicate(facet: Facet, selected: list[str]) -> Any:
    values = [json.loads(v[len(VALUE_PREFIX) :]) for v in selected if v.startswith(VALUE_PREFIX)]
    conditions = []
    if facet.members is not None:
        if values:
            value = facet.members.selected_columns["value"]
            conditions.append(exists(facet.members.where(value.in_(values))))
        if MISSING in selected:
            conditions.append(not_(exists(facet.members)))
    else:
        if values:
            conditions.append(cast(facet.scalar, String).in_(values))
        if MISSING in selected:
            conditions.append(facet.scalar.is_(None))
    return or_(*conditions) if conditions else true()


def facet_option_statement(base: Any, facet: Facet, field: str) -> Any:
    if facet.members is not None:
        members = facet.members.correlate(base).distinct().lateral("listing_facet_members")
        values = (
            select(base.c.id.label("listing_id"), members.c.value.label("facet_value"))
            .select_from(base)
            .outerjoin(members, true())
            .subquery()
        )
    else:
        values = (
            select(base.c.id.label("listing_id"), facet.scalar.label("facet_value"))
            .select_from(base)
            .subquery()
        )
    # Group the resolved value, not correlated subqueries or a raw joined row.
    value = values.c.facet_value
    direction = value.desc() if field in DATE_FIELDS else value.asc()
    return (
        select(cast(value, String), func.count(values.c.listing_id.distinct()))
        .select_from(values)
        .group_by(value)
        .order_by(direction.nulls_last())
    )


def facet_option(field: str, value: Any, count: int) -> dict[str, Any]:
    if value is None:
        return {"value": MISSING, "label": MISSING_LABELS.get(field, "无数据"), "count": int(count)}
    raw = str(value)
    label = raw
    if field in NUMERIC_FIELDS:
        if "." in raw:
            label = raw.rstrip("0").rstrip(".")
        if field in {"salePrice", "listPrice", "adSpend30Days"}:
            whole, _, fraction = label.partition(".")
            label = "$" + whole + "." + fraction.ljust(2, "0")
    return {
        "value": VALUE_PREFIX + json.dumps(raw, ensure_ascii=False),
        "label": label,
        "count": int(count),
    }


# A complete response is bounded, never silently truncated. The scoped base is
# evaluated once; each field excludes only its own exact selections.
COMPLETE_FACET_OPTION_LIMIT = 50_000
COMPLETE_FACET_RESPONSE_BYTES = 16 * 1024 * 1024


# Keep the shared CTE narrow: never materialize the full Listing ORM row,
# including unused source lineage, tags and other large JSON columns.
_BATCH_FACET_COLUMNS = {
    "store": ("store_name", "store_id"),
    "owner": ("owner_name", "owner_ref"),
    "archiveStatus": ("source_account_ref",),
    "productTags": ("product_tags_json",),
    "tags": ("source_account_ref", "item_id"),
    "lifecycle": ("effective_lifecycle_status",),
    "productGrade": ("product_grade",),
    "image": ("picture_url",),
    "productId": ("item_id",),
    "productName": ("local_name", "effective_title"),
    "sku": ("local_sku",),
    "msku": ("msku",),
    "title": ("effective_title", "local_name"),
    "imageCount": (),
    "category": ("effective_category",),
    "keyFeatures": (),
    "listPrice": ("effective_strike_price_amount",),
    "hasStrikethrough": (),
    "salePrice": ("effective_sale_price_amount",),
    "wfsAvailableInventory": ("wfs_available_quantity",),
    "inboundInventory": ("inbound_quantity",),
    "listedAt": ("first_wfs_available_date_la",),
    "sales90Days": ("sales_30d",),
    "adSpend30Days": ("ad_spend_30d_amount",),
    "disabledReason": ("disabled_reason",),
    "listingStatus": ("effective_buybox_status", "wfs_available_quantity", "effective_is_hijacked"),
    "buyBoxStatus": ("effective_buybox_status",),
    "rating": ("effective_average_rating",),
    "reviewCount": ("effective_review_count",),
    "brand": ("effective_brand",),
    "walmartSeller": ("effective_walmart_seller",),
    "sellerOfferCount": (),
    "sellerNames": (),
    "resold": ("effective_is_hijacked",),
    "checkedAt": ("monitor_checked_at",),
    "fulfillmentMethod": ("fulfillment_type_name", "fulfillment_type"),
    "gtin": ("gtin",),
    "gptAnalysis": ("source_account_ref",),
    "archiveReason": ("source_account_ref",),
}


def batch_facet_projection(statement, fields, selected):
    needed = {"id", "monitor_raw_parsed"}
    for field in set(fields).union(selected):
        needed.update(_BATCH_FACET_COLUMNS[field])
    columns = statement.selected_columns
    return statement.with_only_columns(
        *(columns[name] for name in sorted(needed)),
        maintain_column_froms=True,
    ).order_by(None)


def complete_facet_batch_statement(
    statement, fields, selected, exception_condition, cart_exception_condition, no_strike_condition
):
    base = (
        batch_facet_projection(statement, fields, selected)
        .cte("listing_facet_batch_base")
        .prefix_with("MATERIALIZED", dialect="postgresql")
    )
    predicates = {
        field: facet_predicate(
            listing_facet(
                base.c, field, exception_condition, cart_exception_condition, no_strike_condition
            ),
            values,
        )
        for field, values in selected.items()
    }
    branches = []
    for field in fields:
        scoped = (
            select(base)
            .where(*(predicate for key, predicate in predicates.items() if key != field))
            .subquery()
        )
        facet = listing_facet(
            scoped.c, field, exception_condition, cart_exception_condition, no_strike_condition
        )
        options = facet_option_statement(scoped, facet, field).order_by(None).subquery()
        value, count = list(options.c)
        branches.append(
            select(
                literal(field).label("field_name"),
                value.label("facet_value"),
                count.label("listing_count"),
            )
        )
    combined = branches[0] if len(branches) == 1 else union_all(*branches)
    return combined.limit(COMPLETE_FACET_OPTION_LIMIT + 1)


def complete_facet_batch_items(fields, rows):
    from decimal import Decimal

    items = {field: {"options": [], "has_more": False} for field in fields}
    if len(rows) > COMPLETE_FACET_OPTION_LIMIT:
        raise ValueError("Too many facet options; narrow the main Listing filters")
    for field, value, count in rows:
        items[field]["options"].append(facet_option(field, value, count))
    for field, data in items.items():
        present = [option for option in data["options"] if option["value"] != MISSING]
        missing = [option for option in data["options"] if option["value"] == MISSING]

        def raw(option):
            return json.loads(option["value"][len(VALUE_PREFIX) :])

        if field in NUMERIC_FIELDS:
            present.sort(key=lambda option: Decimal(raw(option)))
        else:
            present.sort(key=raw, reverse=field in DATE_FIELDS)
        data["options"] = present + missing
    if len(json.dumps(items, ensure_ascii=False).encode("utf-8")) > COMPLETE_FACET_RESPONSE_BYTES:
        raise ValueError("Facet response too large; narrow the main Listing filters")
    return items


def compact_facet_label(value: str, label: str) -> str:
    """Only omit redundant long labels; the exact-value token is unchanged."""
    if len(label) >= 64 and value == VALUE_PREFIX + json.dumps(label, ensure_ascii=False):
        return ""
    return label

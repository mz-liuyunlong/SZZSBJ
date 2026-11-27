"""Read-only, allowlisted ordering over the existing Listing filtered projection."""

from typing import Any

from sqlalchemy import case, func

from app.modules.data_pages.listing_exact_facets import listing_facet

LISTING_SORT_FIELDS = frozenset(
    {
        "productIdName",
        "skuMsku",
        "imageCount",
        "listPrice",
        "hasStrikethrough",
        "salePrice",
        "wfsAvailableInventory",
        "inboundInventory",
        "listedAt",
        "sales90Days",
        "adSpend30Days",
        "lifecycle",
        "productGrade",
        "listingStatus",
        "buyBoxStatus",
        "sellerOfferCount",
        "resold",
        "checkedAt",
        "rating",
        "reviewCount",
    }
)

STATUS_RANKS = {
    "hasStrikethrough": {"无": 0, "有": 1},
    "lifecycle": {
        "断货期": 0,
        "下滑期": 1,
        "修复期": 2,
        "清货期": 3,
        "测品期": 4,
        "打品期": 5,
        "启动期": 6,
        "稳定期": 7,
        "上升期": 8,
    },
    "productGrade": {"A": 0, "B": 1, "C": 2, "D": 3},
    "listingStatus": {"异常": 0, "正常": 1},
    "buyBoxStatus": {
        "购物车丢失": 0,
        "未拥有购物车": 0,
        "未找到购物车": 0,
        "不可购买": 0,
        "缺货": 1,
        "正常": 2,
        "拥有": 2,
    },
    "resold": {"是": 0, "否": 1},
}


def parse_listing_sort(value: str) -> list[tuple[str, str]]:
    if not value:
        return []
    entries = value.split(",")
    if len(entries) > len(LISTING_SORT_FIELDS):
        raise ValueError("too many Listing sort fields")
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for entry in entries:
        field, separator, direction = entry.partition(":")
        if (
            not separator
            or field not in LISTING_SORT_FIELDS
            or direction not in {"asc", "desc"}
            or field in seen
        ):
            raise ValueError("invalid or duplicate Listing sort field/direction")
        seen.add(field)
        result.append((field, direction))
    return result


def listing_order_columns(
    c: Any,
    sort_by: str,
    exception_condition: Any,
    cart_exception_condition: Any,
    no_strike_condition: Any,
) -> list[Any]:
    """Sort actual numeric/date values and explicit business ranks, not text tokens."""
    sorts = parse_listing_sort(sort_by)
    if not sorts:
        return [
            func.coalesce(c["wfs_available_quantity"], 0).desc(),
            c["store_name"].asc(),
            c["local_sku"].asc(),
            c["item_id"].asc(),
            c["id"].asc(),
        ]
    order: list[Any] = []
    for key, direction in sorts:
        fields = (
            ("productId",)
            if key == "productIdName"
            else (("sku", "msku") if key == "skuMsku" else (key,))
        )
        for field in fields:
            value = listing_facet(
                c,
                field,
                exception_condition,
                cart_exception_condition,
                no_strike_condition,
            ).scalar
            if field in STATUS_RANKS:
                value = case(STATUS_RANKS[field], value=value, else_=None)
            order.append((value.asc() if direction == "asc" else value.desc()).nulls_last())
    return [*order, c["id"].asc()]

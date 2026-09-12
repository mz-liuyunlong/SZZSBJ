from dataclasses import dataclass


class ProductListParseError(ValueError):
    """Safe parse failure without source values."""


@dataclass(frozen=True, slots=True)
class ProductListSkuIds:
    values: tuple[str, ...]
    response_count: int
    duplicate_count: int


def inspect_productlist_sku_ids(payload: object) -> ProductListSkuIds:
    if not isinstance(payload, dict):
        raise ProductListParseError("PRODUCTLIST_DATA_INVALID")
    container: object = payload
    if not isinstance(payload.get("data"), list):
        container = payload.get("productList")
    if not isinstance(container, dict) or not isinstance(container.get("data"), list):
        raise ProductListParseError("PRODUCTLIST_DATA_INVALID")
    result: list[str] = []
    seen: set[str] = set()
    duplicate_count = 0
    for item in container["data"]:
        if not isinstance(item, dict):
            raise ProductListParseError("PRODUCTLIST_ITEM_INVALID")
        value = item.get("id")
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ProductListParseError("PRODUCTLIST_SKU_ID_INVALID")
        normalized = str(value).strip()
        if not normalized:
            raise ProductListParseError("PRODUCTLIST_SKU_ID_INVALID")
        if normalized in seen:
            duplicate_count += 1
            continue
        seen.add(normalized)
        result.append(normalized)
    return ProductListSkuIds(
        values=tuple(result),
        response_count=len(container["data"]),
        duplicate_count=duplicate_count,
    )


def parse_productlist_sku_ids(payload: object) -> list[str]:
    inspected = inspect_productlist_sku_ids(payload)
    if inspected.duplicate_count:
        raise ProductListParseError("PRODUCTLIST_SKU_ID_DUPLICATE")
    return list(inspected.values)

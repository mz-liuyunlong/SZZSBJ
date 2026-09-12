class ProductListParseError(ValueError):
    """Safe parse failure without source values."""


def parse_productlist_sku_ids(payload: object) -> list[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ProductListParseError("PRODUCTLIST_DATA_INVALID")
    result: list[str] = []
    seen: set[str] = set()
    for item in payload["data"]:
        if not isinstance(item, dict):
            raise ProductListParseError("PRODUCTLIST_ITEM_INVALID")
        value = item.get("id")
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ProductListParseError("PRODUCTLIST_SKU_ID_INVALID")
        normalized = str(value).strip()
        if not normalized:
            raise ProductListParseError("PRODUCTLIST_SKU_ID_INVALID")
        if normalized in seen:
            raise ProductListParseError("PRODUCTLIST_SKU_ID_DUPLICATE")
        seen.add(normalized)
        result.append(normalized)
    return result

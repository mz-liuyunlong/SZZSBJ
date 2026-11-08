"""V16 exact Product Management name; do not infer name from Walmart title."""
from types import SimpleNamespace
from app.modules.clearance.read_only_listings import _product_data_for_listings


class _QueryResult:
    def __init__(self, rows):
        self.rows = rows
    def all(self):
        return self.rows


class _ReadOnlySession:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0
    def execute(self, query):
        self.calls += 1
        return _QueryResult(self.rows)


def _listing(store="STORE_A", msku="MSKU_A", sku="SKU_A"):
    return SimpleNamespace(store_name=store, msku=msku, local_sku=sku)


def test_exact_listing_product_name_mapping_not_listing_title():
    session=_ReadOnlySession([("STORE_A", "MSKU_A", "SKU_A", "内部真实品名", 3, "USD", 1, "USD")])
    result=_product_data_for_listings(session, [_listing()])
    assert result[("STORE_A","MSKU_A","SKU_A")]["product_name"] == "内部真实品名"
    assert result[("STORE_A","MSKU_A","SKU_A")]["purchase"] == 3
    assert result[("STORE_A","MSKU_A","SKU_A")]["wfs_fee"] == 1
    assert session.calls == 1


def test_wrong_store_sku_product_is_not_used():
    session=_ReadOnlySession([("STORE_B", "MSKU_A", "SKU_A", "错误店铺品名", 3, "USD", 1, "USD")])
    assert _product_data_for_listings(session, [_listing()]) == {}


def test_duplicate_business_mapping_returns_no_name():
    row=("STORE_A", "MSKU_A", "SKU_A", "品名", 3, "USD", 1, "USD")
    session=_ReadOnlySession([row, row])
    assert _product_data_for_listings(session, [_listing()]) == {}


def test_missing_name_stays_unknown_instead_of_fabricating_one():
    session=_ReadOnlySession([("STORE_A", "MSKU_A", "SKU_A", "", 3, "USD", 1, "USD")])
    result=_product_data_for_listings(session, [_listing()])
    assert result[("STORE_A","MSKU_A","SKU_A")]["product_name"] is None

from app.modules.integration_sync.data_pages_business_rules_v3 import _unique_identity_pair


def test_unique_identity_pair_accepts_one_distinct_pair() -> None:
    rows = [
        {"store_id": "store-a", "msku": "sku-a"},
        {"store_id": "store-a", "msku": "sku-a"},
    ]

    assert _unique_identity_pair(rows) == ("store-a", "sku-a")


def test_unique_identity_pair_rejects_ambiguous_pairs() -> None:
    rows = [
        {"store_id": "store-a", "msku": "sku-a"},
        {"store_id": "store-b", "msku": "sku-b"},
    ]

    assert _unique_identity_pair(rows) is None


def test_unique_identity_pair_ignores_incomplete_rows() -> None:
    rows = [
        {"store_id": None, "msku": "sku-a"},
        {"store_id": "store-a", "msku": ""},
    ]

    assert _unique_identity_pair(rows) is None

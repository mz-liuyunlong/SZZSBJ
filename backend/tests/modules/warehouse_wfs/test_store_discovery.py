import pytest

from app.modules.warehouse_wfs.store_discovery import (
    WfsStoreDiscoveryError,
    settlement_store_scope,
    validate_walmart_stores,
)


def store(store_id="store-a", sid="123456", name="Shop A", account="account-a"):
    return {
        "source_account_ref": account,
        "store_id": store_id,
        "store_name": name,
        "sid": sid,
    }


def test_discovers_store_without_manual_sid():
    result = validate_walmart_stores(
        [store()],
        source_account_ref="account-a",
    )
    assert result[0].sid == "123456"
    assert settlement_store_scope(result) == ({"sids": "store-a", "store_id": "store-a"},)


def test_multiple_stores_are_kept_separate():
    result = validate_walmart_stores(
        [
            store("store-b", "222", "Shop B"),
            store("store-a", "111", "Shop A"),
        ],
        source_account_ref="account-a",
    )
    assert len(result) == 2
    assert [item.sid for item in result] == ["111", "222"]


@pytest.mark.parametrize(
    ("records", "error"),
    [
        ([store(store_id="")], "WFS_STORE_ID_MISSING"),
        ([store(name="")], "WFS_STORE_NAME_MISSING"),
        ([store(account="other")], "WFS_CROSS_ACCOUNT_STORE"),
        (
            [store(), store("store-b", "789", "Shop A")],
            "WFS_AMBIGUOUS_STORE_NAME",
        ),
        (
            [store(), store("store-a", "789", "Shop B")],
            "WFS_DUPLICATE_STORE_ID",
        ),
        ([], "WFS_NO_WALMART_STORES"),
    ],
)
def test_invalid_store_scope_is_rejected(records, error):
    with pytest.raises(WfsStoreDiscoveryError, match=error):
        validate_walmart_stores(
            records,
            source_account_ref="account-a",
        )


def test_walmart_empty_sid_supported():
    result = validate_walmart_stores(
        [
            {
                "source_account_ref": "account-a",
                "store_id": "11084132377310001",
                "store_name": "Walmart Test",
                "sid": "",
            }
        ],
        source_account_ref="account-a",
    )
    assert settlement_store_scope(result)[0]["sids"] == "11084132377310001"

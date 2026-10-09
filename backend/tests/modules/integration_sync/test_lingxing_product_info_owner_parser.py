import pytest

from app.modules.integration_sync.parsers.lingxing_product_info import (
    ProductInfoParseError,
    parse_batch_product_info_fixture,
)


def _payload(permission_user_info, **extra):
    item = {
        "id": "1001",
        "sku": "SKU-1001",
        "permission_user_info": permission_user_info,
        **extra,
    }
    return {"code": 0, "data": [item]}


def _parse(payload):
    return parse_batch_product_info_fixture(
        payload,
        expected_lingxing_sku_ids=("1001",),
    )[0].detail


def test_multiple_owners_filters_creator_by_name():
    parsed = _parse(
        _payload(
            [
                {"permission_uid": "creator-uid", "permission_user_name": "创建人"},
                {"permission_uid": "owner-uid", "permission_user_name": "真实负责人"},
            ],
            create_user_name=" 创建人 ",
        )
    )

    assert parsed.owner_uid == "owner-uid"
    assert parsed.owner_name == "真实负责人"


def test_multiple_owners_filters_creator_by_uid():
    parsed = _parse(
        _payload(
            [
                {"permission_uid": "creator-uid", "permission_user_name": "创建人"},
                {"permission_uid": "owner-uid", "permission_user_name": "真实负责人"},
            ],
            create_user_id="creator-uid",
        )
    )

    assert parsed.owner_uid == "owner-uid"
    assert parsed.owner_name == "真实负责人"


def test_multiple_owners_with_only_creator_left_empty():
    parsed = _parse(
        _payload(
            [
                {"permission_uid": "creator-uid", "permission_user_name": "创建人"},
                {"permission_uid": "creator-uid", "permission_user_name": "创建人"},
            ],
            create_user_name="创建人",
        )
    )

    assert parsed.owner_uid is None
    assert parsed.owner_name is None


def test_multiple_owners_still_fails_when_multiple_non_creators_remain():
    payload = _payload(
        [
            {"permission_uid": "creator-uid", "permission_user_name": "创建人"},
            {"permission_uid": "owner-a", "permission_user_name": "负责人A"},
            {"permission_uid": "owner-b", "permission_user_name": "负责人B"},
        ],
        create_user_name="创建人",
    )

    with pytest.raises(ProductInfoParseError) as exc:
        _parse(payload)

    assert str(exc.value) == "PRODUCT_INFO_OWNER_CARDINALITY"


def test_multiple_owners_still_fails_when_creator_missing():
    payload = _payload(
        [
            {"permission_uid": "owner-a", "permission_user_name": "负责人A"},
            {"permission_uid": "owner-b", "permission_user_name": "负责人B"},
        ]
    )

    with pytest.raises(ProductInfoParseError) as exc:
        _parse(payload)

    assert str(exc.value) == "PRODUCT_INFO_OWNER_CARDINALITY"


def test_owner_non_list_still_fails():
    payload = _payload({"permission_uid": "owner-a", "permission_user_name": "负责人A"})

    with pytest.raises(ProductInfoParseError) as exc:
        _parse(payload)

    assert str(exc.value) == "CONTRACT_FIELD_MISMATCH"


def test_multiple_owners_filters_cg_opt_username_as_creator_operator():
    parsed = _parse(
        _payload(
            [
                {"permission_uid": "developer-uid", "permission_user_name": "产品负责人"},
                {"permission_uid": "operator-uid", "permission_user_name": "创建操作人"},
            ],
            product_developer="产品负责人",
            product_developer_uid="developer-uid",
            cg_opt_username="创建操作人",
        )
    )

    assert parsed.owner_uid == "developer-uid"
    assert parsed.owner_name == "产品负责人"


def test_multiple_owners_prefers_product_developer_when_operator_is_not_in_owner_list():
    parsed = _parse(
        _payload(
            [
                {"permission_uid": "developer-uid", "permission_user_name": "产品负责人"},
                {"permission_uid": "other-uid", "permission_user_name": "其他人员"},
            ],
            product_developer="产品负责人",
            product_developer_uid="developer-uid",
            cg_opt_username="创建操作人",
        )
    )

    assert parsed.owner_uid == "developer-uid"
    assert parsed.owner_name == "产品负责人"


def test_multiple_owners_prefers_product_developer_before_creator_filter():
    parsed = _parse(
        _payload(
            [
                {"permission_uid": "developer-uid", "permission_user_name": "产品负责人"},
                {"permission_uid": "operator-uid", "permission_user_name": "创建操作人"},
            ],
            product_developer="产品负责人",
            product_developer_uid="developer-uid",
            cg_opt_username="创建操作人",
        )
    )

    assert parsed.owner_uid == "developer-uid"
    assert parsed.owner_name == "产品负责人"

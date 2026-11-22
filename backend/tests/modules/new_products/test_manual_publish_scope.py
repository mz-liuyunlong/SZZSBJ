import pytest

from app.modules.new_products.unified_publish import (
    manual_single_product_write_allowed,
)

IDENTITY = ("primary", "110711149920800256", "20881463249")


@pytest.mark.parametrize(
    ("item_ids", "limit", "auto_only", "identity", "expected"),
    [
        ({"20881463249"}, 1, True, IDENTITY, False),
        (None, 1, True, IDENTITY, False),
        ({"20881463249"}, 500, True, IDENTITY, False),
        ({"20881463249"}, 1, False, IDENTITY, False),
        ({"20881463249"}, 1, True, None, False),
        ({"20881463249", "20874953767"}, 1, True, IDENTITY, False),
        ({"20874953767"}, 1, True, IDENTITY, False),
        ({"20881463249"}, 1, True, ("", "store", "item"), False),
    ],
)
def test_production_manual_scope(monkeypatch, item_ids, limit, auto_only, identity, expected):
    monkeypatch.setenv("APP_ENV", "production")
    assert (
        manual_single_product_write_allowed(
            item_ids=item_ids,
            limit=limit,
            auto_only=auto_only,
            manual_identity=identity,
        )
        is expected
    )


@pytest.mark.parametrize("env", ["local", "dev", "development", ""])
def test_manual_exception_never_bypasses_local_write_guard(monkeypatch, env):
    monkeypatch.setenv("APP_ENV", env)
    assert not manual_single_product_write_allowed(
        item_ids={"20881463249"},
        limit=1,
        auto_only=True,
        manual_identity=IDENTITY,
    )


def test_authenticated_api_scope_allows_one_item(monkeypatch):
    from app.modules.new_products.unified_publish import (
        authenticated_manual_publish,
    )

    monkeypatch.setenv("APP_ENV", "production")
    with authenticated_manual_publish(IDENTITY):
        assert manual_single_product_write_allowed(
            item_ids={IDENTITY[2]},
            limit=1,
            auto_only=True,
            manual_identity=IDENTITY,
        )
        assert not manual_single_product_write_allowed(
            item_ids={IDENTITY[2]},
            limit=500,
            auto_only=True,
            manual_identity=IDENTITY,
        )
        assert not manual_single_product_write_allowed(
            item_ids={"20874953767"},
            limit=1,
            auto_only=True,
            manual_identity=IDENTITY,
        )

    assert not manual_single_product_write_allowed(
        item_ids={IDENTITY[2]},
        limit=1,
        auto_only=True,
        manual_identity=IDENTITY,
    )


def test_global_batch_stays_blocked(monkeypatch):
    from app.modules.new_products import unified_publish as publisher

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SZZSBJ_PR337_UNIFIED_PUBLISH_ENABLED", "0")
    monkeypatch.setenv("SZZSBJ_PR337_UNIFIED_PRODUCTION_WRITE_APPROVED", "0")

    with pytest.raises(PermissionError, match="PR337_UNIFIED_PUBLISH_NOT_AUTHORIZED"):
        publisher.publish_unified(None, None, apply=True, auto_only=True)

    with publisher.authenticated_manual_publish(IDENTITY):
        with pytest.raises(PermissionError, match="PR337_UNIFIED_PUBLISH_NOT_AUTHORIZED"):
            publisher.publish_unified(None, None, apply=True, auto_only=True)


def test_forged_identity_cannot_publish(monkeypatch):
    from app.modules.new_products import unified_publish as publisher

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SZZSBJ_PR337_UNIFIED_PUBLISH_ENABLED", "0")
    monkeypatch.setenv("SZZSBJ_PR337_UNIFIED_PRODUCTION_WRITE_APPROVED", "0")

    with pytest.raises(PermissionError, match="PR337_UNIFIED_PUBLISH_NOT_AUTHORIZED"):
        publisher.publish_unified(
            None,
            None,
            item_ids={IDENTITY[2]},
            limit=1,
            apply=True,
            auto_only=True,
            manual_identity=IDENTITY,
        )

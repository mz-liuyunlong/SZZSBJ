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


def test_local_manual_tunnel_scope_does_not_open_batch(monkeypatch):
    from types import SimpleNamespace

    from app.db import session as db_session
    from app.modules.new_products import read_source
    from app.modules.new_products import unified_publish as publisher

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("SZZSBJ_PR337_UNIFIED_PUBLISH_ENABLED", "0")

    def target(database):
        return SimpleNamespace(url=SimpleNamespace(database=database, host="configured-tunnel"))

    monkeypatch.setattr(db_session, "get_engine", lambda: target("szzsbj_app"))

    class ReachedReadSource(Exception):
        pass

    def no_database_access():
        raise ReachedReadSource()

    monkeypatch.setattr(read_source, "get_new_product_read_session", no_database_access)

    kwargs = dict(
        item_ids={IDENTITY[2]},
        limit=1,
        apply=True,
        auto_only=True,
        manual_identity=IDENTITY,
    )

    with pytest.raises(PermissionError, match="PR337_WRITE_TARGET_NOT_LOCAL_DEV_OR_HYBRID"):
        publisher.execute_unified_job(**kwargs)

    with publisher.authenticated_manual_publish(IDENTITY):
        assert publisher.manual_single_product_write_allowed(
            item_ids={IDENTITY[2]},
            limit=1,
            auto_only=True,
            manual_identity=IDENTITY,
        )

        # The exact authorized item passes both guards. The source is
        # intercepted before any database connection or write.
        with pytest.raises(ReachedReadSource):
            publisher.execute_unified_job(**kwargs)

        for changed in (
            {"item_ids": None, "limit": 500},
            {"item_ids": {"another_item"}},
            {"auto_only": False},
            {"limit": 500},
        ):
            invalid = {**kwargs, **changed}
            with pytest.raises(
                PermissionError,
                match="PR337_WRITE_TARGET_NOT_LOCAL_DEV_OR_HYBRID",
            ):
                publisher.execute_unified_job(**invalid)

        monkeypatch.setattr(db_session, "get_engine", lambda: target("unexpected_db"))
        with pytest.raises(PermissionError, match="PR337_WRITE_TARGET_NOT_LOCAL_DEV_OR_HYBRID"):
            publisher.execute_unified_job(**kwargs)


def test_pending_market_daily_refresh_only_before_final_grade():
    from types import SimpleNamespace

    from app.modules.new_products.unified_publish import (
        _pending_market_daily_refresh_allowed,
    )

    perf = SimpleNamespace(grade=None, score=None)
    completed = {"evaluation_formal_trigger": {"status": "completed"}}

    assert _pending_market_daily_refresh_allowed(perf, completed)
    assert not _pending_market_daily_refresh_allowed(perf, {})
    assert not _pending_market_daily_refresh_allowed(
        perf, {"evaluation_formal_trigger": {"status": "pending"}}
    )
    assert not _pending_market_daily_refresh_allowed(
        SimpleNamespace(grade="A", score=None), completed
    )
    assert not _pending_market_daily_refresh_allowed(
        SimpleNamespace(grade=None, score=8), completed
    )

"""Operation-log safety, history, permissions and transaction behavior (synthetic data)."""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.core.api import ApiError
from app.modules.operation_logs import service


def test_account_mapping_rejects_ambiguous_stores_and_items() -> None:
    session = MagicMock()
    session.execute.side_effect = [
        MagicMock(
            all=lambda: [
                ("store-a", "account-1"),
                ("store-a", "account-2"),
                ("store-b", "account-3"),
            ]
        ),
        MagicMock(
            all=lambda: [
                ("store-a", "item-1", "account-1"),
                ("store-a", "item-2", "account-1"),
                ("store-a", "item-2", "account-2"),
            ]
        ),
    ]
    stores, items = service.account_mapping(session)
    assert stores == {"store-b": "account-3"}
    assert items == {("store-a", "item-1"): "account-1"}
    assert (
        service._account((stores, items), {"store_id": "store-a", "item_id": "item-1"})
        == "account-1"
    )
    assert service._account((stores, items), {"store_id": "store-a", "item_id": "item-2"}) is None


def test_history_dry_run_never_writes() -> None:
    session = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value = []
    with patch.object(service, "account_mapping", return_value=({}, {})):
        result = service.import_history(session)
    assert result == {"system_scanned": 0, "manual_scanned": 0, "unresolved": 0, "affected": 0}
    session.commit.assert_not_called()


@pytest.mark.parametrize("batch_size", [0, -1, 1001])
def test_import_batch_size_validation(batch_size: int) -> None:
    with pytest.raises(ValueError):
        service.import_history(MagicMock(), batch_size=batch_size)


def test_event_import_uses_stable_legacy_id() -> None:
    session = MagicMock()
    session.execute.return_value.rowcount = 1
    row = {
        "id": 100,
        "store_id": "store",
        "item_id": "item",
        "event_date": date(2026, 10, 16),
        "msku": "sku",
        "action_type": "bid_changed",
        "object_name": "keyword",
        "log_content": "bid change",
        "highlight": 1,
        "verify_status": "",
        "updated_at": datetime(2026, 10, 17),
        "detected_at": datetime(2026, 10, 17),
    }
    affected = service._import_batch(
        session,
        kind="system",
        rows=[row],
        mapping=({"store": "account"}, {}),
    )
    assert affected == 1
    sql = str(session.execute.call_args.args[0])
    assert "on conflict (legacy_id)" in sql
    assert "ops_system_operation_events" in sql
    assert "legacy_mirror." not in sql


def test_legacy_manual_import_never_overwrites_body() -> None:
    session = MagicMock()
    session.execute.return_value.rowcount = 1
    row = {
        "id": 200,
        "store_id": "store",
        "item_id": "item",
        "log_date": date(2026, 10, 16),
        "msku": "sku",
        "log_content": "old record",
        "updated_at": datetime(2026, 10, 17),
    }
    service._import_batch(
        session,
        kind="manual",
        rows=[row],
        mapping=({"store": "account"}, {}),
    )
    sql = str(session.execute.call_args.args[0]).lower()
    assert "on conflict (legacy_id)" in sql
    assert "set" in sql
    assert "log_content = excluded.log_content" not in sql
    assert (
        "update set source_account_ref" in sql
        or "source_account_ref = excluded.source_account_ref" in sql
    )


def test_scope_rejects_cross_account_before_db_lookup() -> None:
    session = MagicMock()
    with pytest.raises(ApiError) as err:
        service.read_detail(
            session,
            accounts=frozenset({"allow"}),
            account="deny",
            day=date(2026, 10, 16),
            store="store",
            item="item",
            msku="sku",
        )
    assert err.value.status_code == 403
    session.execute.assert_not_called()


def test_batch_write_duplicate_identity_is_refused() -> None:
    session = MagicMock()
    row = {
        "account": "account",
        "day": date(2026, 10, 16),
        "store": "store",
        "item": "item",
        "msku": "",
        "content": "Log",
        "work_type": "广告调整",
        "status": "draft",
        "revision": 0,
    }
    with pytest.raises(ApiError) as err:
        service.save_batch(
            session, accounts=frozenset({"account"}), rows=[row, row], actor="operator"
        )
    assert err.value.status_code == 422
    session.commit.assert_not_called()


def test_batch_write_rollback_on_stale_revision() -> None:
    session = MagicMock()
    row = {
        "account": "account",
        "day": date(2026, 10, 16),
        "store": "store",
        "item": "item",
        "msku": "",
        "content": "Log",
        "work_type": "广告调整",
        "status": "submitted",
        "revision": 0,
    }
    with patch.object(
        service,
        "_save_one",
        side_effect=ApiError(
            code="OPERATION_LOG_EDIT_CONFLICT",
            status_code=409,
        ),
    ):
        with pytest.raises(ApiError):
            service.save_batch(
                session, accounts=frozenset({"account"}), rows=[row], actor="operator"
            )
    session.rollback.assert_called_once()
    session.commit.assert_not_called()


def test_batch_success_commits_once() -> None:
    session = MagicMock()
    row = {
        "account": "account",
        "day": date(2026, 10, 16),
        "store": "store",
        "item": "item",
        "msku": "",
        "content": "Log",
        "work_type": "其他",
        "status": "draft",
        "revision": 0,
    }
    with patch.object(service, "_save_one", return_value=1):
        revisions = service.save_batch(
            session,
            accounts=frozenset({"account"}),
            rows=[row],
            actor="operator",
        )
    assert revisions == [1]
    session.commit.assert_called_once()


def test_empty_submitted_note_is_rejected() -> None:
    session = MagicMock()
    with patch.object(service, "_identity"):
        with pytest.raises(ApiError) as err:
            service._save_one(
                session,
                accounts=frozenset({"account"}),
                account="account",
                day=date(2026, 10, 16),
                store="store",
                item="item",
                msku="",
                content="  ",
                work_type="其他",
                status="submitted",
                revision=0,
                actor="operator",
            )
    assert err.value.status_code == 422


def test_celery_sync_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.operation_logs.tasks import _active

    for key in (
        "OPERATION_LOG_MIRROR_SYNC_ENABLED",
        "OPERATION_LOG_HISTORICAL_IMPORT_VERIFIED",
        "OPERATION_LOG_DB_WRITE_AUTHORIZED",
    ):
        monkeypatch.delenv(key, raising=False)
    assert _active() is False


def test_app_registers_operation_log_endpoints() -> None:
    from app.main import create_app

    routes = set(create_app().openapi()["paths"])
    assert "/api/operations/logs" in routes
    assert "/api/operations/logs/manual/batch" in routes
    assert "/api/operations/logs/links" in routes
    assert "/api/operations/logs/rows" in routes


def test_operation_log_access_refuses_cross_account() -> None:
    from app.modules.operation_logs.access import LogAccess, require_owned_identity

    access = LogAccess(
        user_id=2,
        accounts=frozenset({"account-a"}),
        is_admin=False,
        display_name="owner-a",
    )
    session = MagicMock()
    with pytest.raises(ApiError) as error:
        require_owned_identity(
            session,
            access,
            account="account-b",
            store="store",
            item="item",
            msku="",
            day=date(2026, 10, 17),
        )
    assert error.value.status_code == 403
    session.scalar.assert_not_called()


def test_operation_log_access_checks_product_owner() -> None:
    from app.modules.operation_logs.access import LogAccess, require_owned_identity

    access = LogAccess(
        user_id=2,
        accounts=frozenset({"account-a"}),
        is_admin=False,
        display_name="owner-a",
    )
    session = MagicMock()
    session.scalar.return_value = False
    with pytest.raises(ApiError) as error:
        require_owned_identity(
            session,
            access,
            account="account-a",
            store="store",
            item="item",
            msku="",
            day=date(2026, 10, 17),
        )
    assert error.value.status_code == 403
    sql = str(session.scalar.call_args_list[0].args[0])
    assert "ops_lingxing_owner_user_mappings" in sql
    assert "map.app_user_id = :user_id" in sql


def test_operation_log_super_admin_bypasses_owner_match() -> None:
    from app.modules.operation_logs.access import LogAccess, require_owned_identity

    access = LogAccess(
        user_id=1,
        accounts=frozenset({"account-a"}),
        is_admin=True,
        display_name="admin",
    )
    session = MagicMock()
    require_owned_identity(
        session,
        access,
        account="account-a",
        store="store",
        item="item",
        msku="",
        day=date(2026, 10, 17),
    )
    session.scalar.assert_not_called()


def test_owner_uid_mapping_has_no_fallback_to_display_names() -> None:
    from app.modules.operation_logs.access import owns_sku_sql

    sql = owns_sku_sql("l")
    assert "pi.owner_uid" in sql
    assert "map.app_user_id = :user_id" in sql
    assert "ops_lingxing_owner_user_mappings" in sql
    assert "display_name" not in sql and "feishu_name" not in sql
    assert "owner_ref" not in sql


def test_unknown_ownership_is_denied() -> None:
    from app.modules.operation_logs.access import LogAccess, require_owned_identity

    access = LogAccess(
        user_id=9, accounts=frozenset({"account-a"}), is_admin=False, display_name="demo"
    )
    session = MagicMock()
    session.scalar.return_value = False
    with pytest.raises(ApiError) as err:
        require_owned_identity(
            session,
            access,
            account="account-a",
            store="s",
            item="x",
            msku="m",
            day=date(2026, 10, 17),
        )
    assert err.value.status_code == 403

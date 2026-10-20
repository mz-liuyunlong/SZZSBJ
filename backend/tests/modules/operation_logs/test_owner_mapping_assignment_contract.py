"""Unit-level contracts for explicit owner-UID binding; never access a DB."""

from unittest.mock import MagicMock

import pytest
from starlette.requests import Request

from app.core.api import ApiError
from app.modules.iam.rbac_repository import RbacRepository
from app.modules.operation_logs.access import LogAccess
from app.modules.operation_logs.router import (
    OwnerMappingWrite,
    assign_owner_mapping,
    put_owner_mapping,
)


def request(method="POST"):
    return Request(
        {
            "type": "http",
            "path": "/api/operations/logs/owner-mappings/assign",
            "method": method,
            "headers": [],
        }
    )


def access(*, is_admin=True, accounts=frozenset({"primary"})):
    return LogAccess(user_id=1, accounts=accounts, is_admin=is_admin, display_name="test admin")


def payload(*, target=42, account="primary"):
    return OwnerMappingWrite(
        source_account_ref=account, owner_uid="lingxing-test-uid", app_user_id=target
    )


def session_with_source(monkeypatch, *, owner_scope=None, source=None):
    if owner_scope is None:
        owner_scope = {"primary"}
    monkeypatch.setattr(
        RbacRepository,
        "resolve_user_data_scope",
        lambda self, *, user_id, scope_type: owner_scope,
    )
    session = MagicMock()
    source_row = source or {"rows": 2, "names": 1, "blanks": 0}
    session.execute.return_value.mappings.return_value.one.return_value = source_row
    return session


def test_assignment_rejects_existing_other_user_without_upsert(monkeypatch):
    session = session_with_source(monkeypatch)
    session.scalar.side_effect = [True, None, 99]
    with pytest.raises(ApiError) as error:
        assign_owner_mapping(request(), payload(), session, None, access())
    assert error.value.status_code == 409
    assert error.value.code == "OWNER_MAPPING_CONFLICT"
    session.commit.assert_not_called()
    session.rollback.assert_called_once()
    statements = [str(call.args[0]) for call in session.execute.call_args_list]
    assert not any("ops_lingxing_owner_mapping_audit" in sql for sql in statements)


def test_legacy_put_cannot_reassign_another_user(monkeypatch):
    session = session_with_source(monkeypatch)
    session.scalar.side_effect = [True, None, 99]
    with pytest.raises(ApiError) as error:
        put_owner_mapping(request("PUT"), payload(), session, None, access())
    assert error.value.status_code == 409
    session.commit.assert_not_called()


def test_new_uid_records_assign_audit(monkeypatch):
    session = session_with_source(monkeypatch)
    session.scalar.side_effect = [True, 123]
    result = assign_owner_mapping(request(), payload(), session, None, access())
    assert result.data == {"saved": True, "created": True}
    session.commit.assert_called_once()
    audit_sql = [str(call.args[0]) for call in session.execute.call_args_list]
    assert any("insert into ops_lingxing_owner_mapping_audit" in sql for sql in audit_sql)


def test_existing_same_uid_is_idempotent(monkeypatch):
    session = session_with_source(monkeypatch)
    session.scalar.side_effect = [True, None, 42]
    result = assign_owner_mapping(request(), payload(), session, None, access())
    assert result.data == {"saved": True, "created": False}
    session.commit.assert_called_once()
    assert not any(
        "ops_lingxing_owner_mapping_audit" in str(call.args[0])
        for call in session.execute.call_args_list
    )


def test_target_must_have_source_account_scope(monkeypatch):
    session = session_with_source(monkeypatch, owner_scope=set())
    session.scalar.return_value = True
    with pytest.raises(ApiError) as error:
        assign_owner_mapping(request(), payload(), session, None, access())
    assert error.value.status_code == 403
    session.execute.assert_not_called()
    session.commit.assert_not_called()


def test_actor_must_be_admin(monkeypatch):
    session = session_with_source(monkeypatch)
    with pytest.raises(ApiError) as error:
        assign_owner_mapping(request(), payload(), session, None, access(is_admin=False))
    assert error.value.status_code == 403
    session.scalar.assert_not_called()


def test_actor_must_have_source_account(monkeypatch):
    session = session_with_source(monkeypatch)
    with pytest.raises(ApiError) as error:
        assign_owner_mapping(request(), payload(account="secondary"), session, None, access())
    assert error.value.status_code == 403
    session.scalar.assert_not_called()


def test_uncertain_source_identity_denied(monkeypatch):
    session = session_with_source(monkeypatch, source={"rows": 2, "names": 2, "blanks": 0})
    session.scalar.return_value = True
    with pytest.raises(ApiError) as error:
        assign_owner_mapping(request(), payload(), session, None, access())
    assert error.value.status_code == 422
    session.commit.assert_not_called()

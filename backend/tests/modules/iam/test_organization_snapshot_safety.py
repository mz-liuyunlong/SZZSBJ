"""Snapshot application remains atomic under reduced Feishu visibility."""

from unittest.mock import MagicMock

import pytest

from app.modules.iam.feishu_directory_service import FeishuDirectoryUser
from app.modules.iam.organization_snapshot import apply_snapshot, canonical_snapshot


def _source():
    return (
        ({"department_id": "od-a", "parent_department_id": "0", "name": "运营部"},),
        (FeishuDirectoryUser(name="A", open_id="ou-a", department_ids=("od-a",)),),
    )


def test_multi_department_partial_visibility_refused() -> None:
    departments, _ = _source()
    users = (
        FeishuDirectoryUser(name="A", open_id="ou-a", department_ids=("od-a", "od-invisible")),
    )
    with pytest.raises(ValueError, match="outside"):
        canonical_snapshot(departments, users)


def test_identical_snapshot_returns_previous_run_without_writes() -> None:
    departments, users = _source()
    digest, _, _ = canonical_snapshot(departments, users)
    session = MagicMock()
    session.execute.return_value.mappings.return_value.first.return_value = {
        "id": "existing-run",
        "snapshot_hash": digest,
        "department_count": 1,
        "employee_count": 1,
    }
    run_id = apply_snapshot(
        session,
        expected_hash=digest,
        departments=departments,
        users=users,
        requested_by="admin",
    )
    assert run_id == "existing-run"
    assert session.execute.call_count == 2


def test_applied_snapshot_revokes_only_ineligible_feishu_linked_sessions() -> None:
    departments, users = _source()
    digest, _, _ = canonical_snapshot(departments, users)
    session = MagicMock()
    session.execute.return_value.mappings.return_value.first.return_value = None

    run_id = apply_snapshot(
        session,
        expected_hash=digest,
        departments=departments,
        users=users,
        requested_by="admin",
    )

    calls = session.execute.call_args_list
    statements = [str(call.args[0]) for call in calls]
    assert "INSERT INTO iam_feishu_employees" in statements[-2]
    assert "UPDATE app_sessions AS s" in statements[-1]
    assert "s.revoked_at IS NULL" in statements[-1]
    assert "u.feishu_open_id IS NOT NULL" in statements[-1]
    assert "e.last_seen_run_id = :run_id" in statements[-1]
    for eligibility in (
        "e.is_active IS TRUE",
        "e.is_resigned IS NOT TRUE",
        "e.is_frozen IS NOT TRUE",
    ):
        assert eligibility in statements[-1]
    assert str(calls[-1].args[1]["run_id"]) == run_id
    session.commit.assert_not_called()


def test_identity_replacement_requires_explicit_confirmation() -> None:
    departments, users = _source()
    digest, _, _ = canonical_snapshot(departments, users)
    session = MagicMock()
    previous = {
        "id": "old-run",
        "snapshot_hash": "a" * 64,
        "department_count": 1,
        "employee_count": 1,
    }
    session.execute.return_value.mappings.return_value.first.return_value = previous
    session.execute.return_value.scalars.return_value = ["different-id"]
    with pytest.raises(ValueError, match="identity set changed"):
        apply_snapshot(
            session,
            expected_hash=digest,
            departments=departments,
            users=users,
            requested_by="admin",
        )


def test_large_visibility_drop_requires_explicit_confirmation() -> None:
    departments, users = _source()
    digest, _, _ = canonical_snapshot(departments, users)
    session = MagicMock()
    session.execute.return_value.mappings.return_value.first.return_value = {
        "id": "old-run",
        "snapshot_hash": "a" * 64,
        "department_count": 5,
        "employee_count": 10,
    }
    with pytest.raises(ValueError, match="over 20%"):
        apply_snapshot(
            session,
            expected_hash=digest,
            departments=departments,
            users=users,
            requested_by="admin",
        )
    assert session.execute.call_count == 2


@pytest.mark.parametrize(
    "change_flag",
    ["allow_large_reduction", "allow_identity_replacement"],
)
def test_high_risk_sync_requires_independent_confirmation(change_flag: str) -> None:
    from unittest.mock import MagicMock, patch

    from starlette.requests import Request

    from app.core.api import ApiError
    from app.core.auth import Principal
    from app.modules.iam.organization_sync_router import (
        ApplySnapshotRequest,
        apply_organization_sync,
    )

    payload = ApplySnapshotRequest(
        expected_hash="0" * 64,
        **{change_flag: True},
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/settings/organization/sync-apply",
            "headers": [],
        }
    )
    session = MagicMock()
    principal = Principal(user_id="1", permissions=frozenset({"*"}))
    with patch("app.modules.iam.organization_sync_router._read_feishu") as external:
        with pytest.raises(ApiError) as error:
            apply_organization_sync(request, payload, principal, session)
    assert error.value.status_code == 422
    external.assert_not_called()
    session.execute.assert_not_called()
    session.commit.assert_not_called()

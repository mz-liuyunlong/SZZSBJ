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
        FeishuDirectoryUser(
            name="A", open_id="ou-a", department_ids=("od-a", "od-invisible")
        ),
    )
    with pytest.raises(ValueError, match="outside"):
        canonical_snapshot(departments, users)


def test_identical_snapshot_returns_previous_run_without_writes() -> None:
    departments, users = _source()
    digest, _, _ = canonical_snapshot(departments, users)
    session = MagicMock()
    session.execute.return_value.mappings.return_value.first.return_value = {
        "id": "existing-run", "snapshot_hash": digest, "department_count": 1,
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


def test_large_visibility_drop_requires_explicit_confirmation() -> None:
    departments, users = _source()
    digest, _, _ = canonical_snapshot(departments, users)
    session = MagicMock()
    session.execute.return_value.mappings.return_value.first.return_value = {
        "id": "old-run", "snapshot_hash": "a" * 64, "department_count": 5,
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

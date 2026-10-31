"""Organization snapshot safety: deterministic identity and fail-closed writes."""

import pytest

from app.modules.iam.feishu_directory_service import FeishuDirectoryUser
from app.modules.iam.organization_snapshot import apply_snapshot, canonical_snapshot


def _source():
    departments = (
        {
            "department_id": "od-a",
            "parent_department_id": "0",
            "name": "运营部",
            "leader_user_id": "",
        },
    )
    users = (FeishuDirectoryUser(name="员工", open_id="ou-1", department_ids=("od-a",)),)
    return departments, users


def test_preview_hash_is_stable() -> None:
    departments, users = _source()
    digest, dept_rows, user_rows = canonical_snapshot(departments, users)
    assert len(digest) == 64
    assert len(dept_rows) == len(user_rows) == 1
    assert canonical_snapshot(departments, users)[0] == digest


def test_snapshot_duplicate_department_rejected() -> None:
    departments, users = _source()
    with pytest.raises(ValueError, match="duplicate"):
        canonical_snapshot(departments + departments, users)


def test_snapshot_duplicate_employee_rejected() -> None:
    departments, users = _source()
    with pytest.raises(ValueError, match="duplicate"):
        canonical_snapshot(departments, users + users)


def test_changed_hash_does_not_write(monkeypatch) -> None:
    departments, users = _source()

    class NoWriteSession:
        def execute(self, *args, **kwargs):
            raise AssertionError("No database writes allowed on stale preview")

    with pytest.raises(ValueError, match="changed"):
        apply_snapshot(
            NoWriteSession(),
            expected_hash="0" * 64,
            departments=departments,
            users=users,
            requested_by="1",
        )

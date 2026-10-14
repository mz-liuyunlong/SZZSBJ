from __future__ import annotations

import pytest

from app.modules.iam.feishu_directory_service import (
    FeishuDirectoryError,
    FeishuDirectoryService,
    FeishuDirectoryUser,
)


class FakeFeishuDirectoryService(FeishuDirectoryService):
    def __init__(self) -> None:
        super().__init__(
            base_url="https://open.feishu.cn",
            app_id="app-id",
            app_secret="app-secret",
        )

    def _fetch_tenant_access_token(self) -> str:
        return "tenant-token"

    def _list_visible_department_ids(self, token: str) -> tuple[str, ...]:
        assert token == "tenant-token"
        return ("0", "od-sales", "od-finance")

    def _list_users_by_department(
        self,
        token: str,
        department_id: str,
    ) -> tuple[dict[str, object], ...]:
        assert token == "tenant-token"

        if department_id == "0":
            return (
                {
                    "name": "陈佳聪",
                    "open_id": "ou-root",
                    "user_id": "root-user",
                    "union_id": "on-root",
                    "status": {"is_active": True},
                },
            )

        if department_id == "od-sales":
            return (
                {
                    "name": "刘云龙",
                    "open_id": "ou-liu",
                    "user_id": "liu-user",
                    "union_id": "on-liu",
                    "department_ids": ["od-sales"],
                    "status": {
                        "is_active": True,
                        "is_frozen": False,
                        "is_resigned": False,
                    },
                },
                {
                    "name": "张三",
                    "open_id": "ou-duplicate",
                    "user_id": "dup-user",
                    "union_id": "on-dup",
                    "department_ids": ["od-sales"],
                    "status": {"is_active": True},
                },
            )

        if department_id == "od-finance":
            return (
                {
                    "name": "张三",
                    "open_id": "ou-duplicate",
                    "user_id": "dup-user",
                    "union_id": "on-dup",
                    "department_ids": ["od-finance"],
                    "status": {"is_active": True},
                },
                {
                    "name": "离职用户",
                    "open_id": "ou-resigned",
                    "user_id": "resigned-user",
                    "union_id": "on-resigned",
                    "department_ids": ["od-finance"],
                    "status": {"is_resigned": True},
                },
            )

        return ()

    def get_user_by_open_id(self, open_id: str) -> FeishuDirectoryUser | None:
        if open_id == "ou-liu":
            return FeishuDirectoryUser(
                name="刘云龙",
                open_id="ou-liu",
                user_id="liu-user",
                union_id="on-liu",
                department_ids=("od-sales",),
                is_active=True,
            )

        return None


def test_normalize_user_preserves_feishu_identity_fields() -> None:
    user = FeishuDirectoryService.normalize_user(
        {
            "name": " 刘云龙 ",
            "open_id": " ou-liu ",
            "user_id": "liu-user",
            "union_id": "on-liu",
            "employee_id": None,
            "department_ids": ["od-sales"],
            "status": {
                "is_active": True,
                "is_frozen": False,
                "is_resigned": False,
            },
        }
    )

    assert user.name == "刘云龙"
    assert user.open_id == "ou-liu"
    assert user.user_id == "liu-user"
    assert user.union_id == "on-liu"
    assert user.employee_id is None
    assert user.department_ids == ("od-sales",)
    assert user.is_active is True
    assert user.is_frozen is False
    assert user.is_resigned is False


def test_normalize_user_uses_fallback_department_id() -> None:
    user = FeishuDirectoryService.normalize_user(
        {
            "name": "陈佳聪",
            "open_id": "ou-root",
            "user_id": "root-user",
        },
        fallback_department_id="0",
    )

    assert user.department_ids == ("0",)


def test_list_visible_users_dedupes_users_across_departments() -> None:
    service = FakeFeishuDirectoryService()

    users = service.list_visible_users()

    assert [user.name for user in users] == ["刘云龙", "张三", "离职用户", "陈佳聪"]

    duplicate = next(user for user in users if user.name == "张三")
    assert duplicate.open_id == "ou-duplicate"
    assert duplicate.department_ids == ("od-sales", "od-finance")


def test_find_users_by_name_returns_unique_match() -> None:
    service = FakeFeishuDirectoryService()

    result = service.find_users_by_name("刘云龙")

    assert result.query_name == "刘云龙"
    assert result.is_unique is True
    assert result.single_user is not None
    assert result.single_user.open_id == "ou-liu"


def test_find_users_by_name_excludes_resigned_users_by_default() -> None:
    service = FakeFeishuDirectoryService()

    result = service.find_users_by_name("离职用户")

    assert result.matched_count == 0
    assert result.single_user is None


def test_find_users_by_name_can_include_resigned_users() -> None:
    service = FakeFeishuDirectoryService()

    result = service.find_users_by_name("离职用户", active_only=False)

    assert result.matched_count == 1
    assert result.single_user is not None
    assert result.single_user.open_id == "ou-resigned"


def test_find_users_by_name_detects_duplicate_real_names() -> None:
    users = (
        FeishuDirectoryUser(name="张三", open_id="ou-a"),
        FeishuDirectoryUser(name="张三", open_id="ou-b"),
    )
    service = FakeFeishuDirectoryService()

    result = service.find_users_by_name("张三", users=users)

    assert result.is_unique is False
    assert result.matched_count == 2
    assert result.single_user is None


def test_get_user_by_open_id_returns_user() -> None:
    service = FakeFeishuDirectoryService()

    user = service.get_user_by_open_id("ou-liu")

    assert user is not None
    assert user.name == "刘云龙"
    assert user.user_id == "liu-user"


def test_missing_credentials_raise_directory_error() -> None:
    service = FeishuDirectoryService(
        base_url="https://open.feishu.cn",
        app_id=None,
        app_secret=None,
    )

    with pytest.raises(FeishuDirectoryError, match="credentials"):
        service.list_visible_users()

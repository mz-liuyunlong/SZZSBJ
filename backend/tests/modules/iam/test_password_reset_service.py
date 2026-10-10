from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.api import ApiError
from app.modules.iam import password_reset_service as service
from app.modules.iam.feishu_service import FeishuPasswordMessage


class FakeMappingResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, object]]:
        return self.rows

    def one_or_none(self) -> dict[str, object] | None:
        if len(self.rows) == 0:
            return None
        if len(self.rows) == 1:
            return self.rows[0]
        raise AssertionError("FakeMappingResult expected at most one row")


class FakeResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def mappings(self) -> FakeMappingResult:
        return FakeMappingResult(self.rows)


class FakeSession:
    def __init__(
        self,
        *,
        lookup_rows: list[dict[str, object]] | None = None,
        reset_token_row: dict[str, object] | None = None,
        user_row: dict[str, object] | None = None,
    ) -> None:
        self.lookup_rows = lookup_rows or []
        self.reset_token_row = reset_token_row
        self.user_row = user_row
        self.executed: list[tuple[str, dict[str, object] | None]] = []
        self.commits = 0

    def execute(self, statement: object, params: dict[str, object] | None = None) -> FakeResult:
        sql = str(statement)
        self.executed.append((sql, params))

        if ":real_name" in sql and "from app_users" in sql:
            return FakeResult(self.lookup_rows)
        if "from iam_password_reset_tokens" in sql:
            return FakeResult([] if self.reset_token_row is None else [self.reset_token_row])
        if f"from {service.IAM_USER_TABLE}" in sql and "where id = :user_id" in sql:
            return FakeResult([] if self.user_row is None else [self.user_row])

        return FakeResult([])

    def commit(self) -> None:
        self.commits += 1


class FakeFeishuService:
    def __init__(self) -> None:
        self.messages: list[FeishuPasswordMessage] = []

    def send_password_setup_message(self, message: FeishuPasswordMessage) -> None:
        self.messages.append(message)


def test_request_password_reset_is_uniform_when_no_unique_active_user() -> None:
    session = FakeSession()
    feishu = FakeFeishuService()

    message = service.request_password_reset(
        session,
        real_name="不存在",
        setup_base_url="https://system.example.com",
        context=service.PasswordResetContext(
            request_ip="127.0.0.1",
            user_agent="test",
        ),
        feishu_service=feishu,
    )

    assert message == service.PUBLIC_RESET_MESSAGE
    assert session.commits == 0
    assert feishu.messages == []


def test_request_password_reset_creates_one_time_token_and_sends_feishu_message() -> None:
    session = FakeSession(
        lookup_rows=[
            {
                "id": 1001,
                "username": "liuyunlong",
                "display_name": "刘云龙",
                "feishu_name": "刘云龙",
                "feishu_open_id": "ou_test",
                "feishu_user_id": None,
                "is_active": 1,
            }
        ],
    )
    feishu = FakeFeishuService()

    message = service.request_password_reset(
        session,
        real_name="刘云龙",
        setup_base_url="https://system.example.com/#/password/setup",
        context=service.PasswordResetContext(
            request_ip="127.0.0.1",
            user_agent="test-agent",
        ),
        feishu_service=feishu,
    )

    assert message == service.PUBLIC_RESET_MESSAGE
    assert session.commits == 1
    insert_sql, insert_params = next(
        item for item in session.executed if "insert into iam_password_reset_tokens" in item[0]
    )
    assert "insert into iam_password_reset_tokens" in insert_sql
    assert insert_params is not None
    assert insert_params["user_id"] == 1001
    assert insert_params["delivery_target"] == "ou_test"
    assert insert_params["request_ip"] == "127.0.0.1"
    assert insert_params["user_agent"] == "test-agent"
    assert len(feishu.messages) == 1
    assert feishu.messages[0].recipient_open_id == "ou_test"
    assert feishu.messages[0].real_name == "刘云龙"
    assert feishu.messages[0].setup_url.startswith(
        "https://system.example.com/#/password/setup?token=",
    )
    assert feishu.messages[0].expires_at == insert_params["expires_at"]
    assert feishu.messages[0].expires_at > datetime.now(UTC)


def test_confirm_password_reset_sets_hash_and_consumes_token() -> None:
    now = datetime.now(UTC)
    session = FakeSession(
        reset_token_row={
            "id": "token-id",
            "user_id": 1001,
            "purpose": service.PASSWORD_RESET_PURPOSE,
            "expires_at": now + timedelta(minutes=10),
            "used_at": None,
            "is_revoked": False,
        },
        user_row={"id": 1001, "is_active": 1},
    )

    message = service.confirm_password_reset(
        session,
        token="reset-token",
        new_password="new-password-123456",
    )

    assert message == "登录密码设置成功，请使用新密码登录。"
    update_user = next(
        params for sql, params in session.executed if f"update {service.IAM_USER_TABLE}" in sql
    )
    update_token = next(
        params for sql, params in session.executed if "update iam_password_reset_tokens" in sql
    )
    assert update_user is not None
    assert update_user["user_id"] == 1001
    assert update_user["password_hash"] != "new-password-123456"
    assert update_token is not None
    assert update_token["token_id"] == "token-id"
    assert session.commits == 1


@pytest.mark.parametrize(
    ("token", "new_password", "expected_message"),
    [
        ("reset-token", "short", "密码至少 12 位"),
        ("missing-token", "new-password-123456", "密码设置链接无效或已过期"),
    ],
)
def test_confirm_password_reset_rejects_invalid_inputs(
    token: str,
    new_password: str,
    expected_message: str,
) -> None:
    session = FakeSession()

    with pytest.raises(ApiError) as exc_info:
        service.confirm_password_reset(
            session,
            token=token,
            new_password=new_password,
        )

    assert exc_info.value.message == expected_message
    assert session.commits == 0

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.iam.feishu_service import (
    FeishuEmployeeOnboardingMessage,
    FeishuPasswordMessage,
    FeishuService,
)
from app.modules.iam.security import hash_password

IAM_USER_TABLE = "app_users"
RESET_TOKEN_TTL_MINUTES = 10
PASSWORD_MIN_LENGTH = 12
PUBLIC_RESET_MESSAGE = "如果姓名匹配到在职员工，系统会通过飞书发送设置密码通知。"

PASSWORD_RESET_PURPOSE = "password_reset"
EMPLOYEE_ONBOARDING_PURPOSE = "employee_onboarding"
LEGACY_PASSWORD_SETUP_PURPOSE = "password_setup"


@dataclass(frozen=True, slots=True)
class PasswordResetContext:
    request_ip: str | None = None
    user_agent: str | None = None


def build_password_setup_url(setup_base_url: str, token: str) -> str:
    """Build a password setup URL from a public frontend password setup page base URL."""

    base_url = setup_base_url.strip().rstrip("/")
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}token={token}"


def build_onboarding_guide_url(setup_base_url: str) -> str:
    """Build the public onboarding guide URL from the password setup frontend URL."""

    origin = setup_base_url.strip().split("#", 1)[0].rstrip("/")
    if not origin:
        return ""
    return f"{origin}/#/help/onboarding"


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _find_unique_active_user_by_real_name(
    session: Session,
    real_name: str,
) -> dict[str, Any] | None:
    name = real_name.strip()
    if not name:
        return None

    rows = (
        session.execute(
            text(
                f"""
                select
                    id,
                    username,
                    display_name,
                    feishu_name,
                    feishu_open_id,
                    feishu_user_id,
                    is_active
                from {IAM_USER_TABLE}
                where is_active = 1
                  and feishu_open_id is not null
                  and (
                    display_name = :real_name
                    or feishu_name = :real_name
                  )
                """
            ),
            {"real_name": name},
        )
        .mappings()
        .all()
    )

    if len(rows) != 1:
        return None

    return dict(rows[0])


def _insert_password_setup_token(
    session: Session,
    *,
    user_id: int,
    purpose: str,
    delivery_target: str | None,
    expires_at: datetime | None,
    context: PasswordResetContext,
) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hash_reset_token(token)

    session.execute(
        text(
            """
            insert into iam_password_reset_tokens (
                id,
                user_id,
                token_hash,
                purpose,
                delivery_channel,
                delivery_target,
                expires_at,
                request_ip,
                user_agent,
                is_revoked
            )
            values (
                gen_random_uuid(),
                :user_id,
                :token_hash,
                :purpose,
                'feishu',
                :delivery_target,
                :expires_at,
                :request_ip,
                :user_agent,
                false
            )
            """
        ),
        {
            "user_id": user_id,
            "token_hash": token_hash,
            "purpose": purpose,
            "delivery_target": delivery_target,
            "expires_at": expires_at,
            "request_ip": context.request_ip,
            "user_agent": context.user_agent,
        },
    )

    return token


def request_password_reset(
    session: Session,
    *,
    real_name: str,
    setup_base_url: str,
    context: PasswordResetContext,
    feishu_service: FeishuService | None = None,
) -> str:
    user = _find_unique_active_user_by_real_name(session, real_name)

    if user is None:
        return PUBLIC_RESET_MESSAGE

    expires_at = _now() + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)
    user_id = int(user["id"])
    recipient_open_id = str(user["feishu_open_id"])
    recipient_user_id = user.get("feishu_user_id")

    token = _insert_password_setup_token(
        session,
        user_id=user_id,
        purpose=PASSWORD_RESET_PURPOSE,
        delivery_target=recipient_open_id,
        expires_at=expires_at,
        context=context,
    )
    session.commit()

    setup_url = build_password_setup_url(setup_base_url, token)
    service = feishu_service or FeishuService.from_settings()
    service.send_password_setup_message(
        FeishuPasswordMessage(
            recipient_open_id=recipient_open_id,
            recipient_user_id=str(recipient_user_id) if recipient_user_id else None,
            real_name=str(user.get("feishu_name") or user.get("display_name") or real_name),
            setup_url=setup_url,
            expires_at=expires_at,
            purpose=PASSWORD_RESET_PURPOSE,
        )
    )

    return PUBLIC_RESET_MESSAGE


def create_employee_onboarding_password_setup(
    session: Session,
    *,
    user_id: int,
    username: str,
    real_name: str,
    setup_base_url: str,
    recipient_open_id: str | None,
    recipient_user_id: str | None,
    onboarding_guide_url: str | None = None,
    feishu_service: FeishuService | None = None,
) -> str:
    if not recipient_open_id and not recipient_user_id:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST,
            status_code=400,
            message="新员工未绑定飞书用户，无法发送入职设置密码通知",
        )

    token = _insert_password_setup_token(
        session,
        user_id=user_id,
        purpose=EMPLOYEE_ONBOARDING_PURPOSE,
        delivery_target=recipient_open_id or recipient_user_id,
        expires_at=None,
        context=PasswordResetContext(),
    )
    session.commit()

    setup_url = build_password_setup_url(setup_base_url, token)
    service = feishu_service or FeishuService.from_settings()
    service.send_employee_onboarding_card(
        FeishuEmployeeOnboardingMessage(
            recipient_open_id=recipient_open_id,
            recipient_user_id=recipient_user_id,
            real_name=real_name,
            username=username,
            setup_url=setup_url,
            onboarding_guide_url=onboarding_guide_url,
        )
    )

    return setup_url


def confirm_password_reset(
    session: Session,
    *,
    token: str,
    new_password: str,
) -> str:
    if len(new_password) < PASSWORD_MIN_LENGTH:
        raise ApiError(
            code=ErrorCode.VALIDATION_ERROR,
            status_code=422,
            message="密码至少 12 位",
        )

    now = _now()
    token_hash = hash_reset_token(token)
    reset_token = (
        session.execute(
            text(
                """
                select
                    id,
                    user_id,
                    purpose,
                    expires_at,
                    used_at,
                    is_revoked
                from iam_password_reset_tokens
                where token_hash = :token_hash
                """
            ),
            {"token_hash": token_hash},
        )
        .mappings()
        .one_or_none()
    )

    valid_purposes = {
        PASSWORD_RESET_PURPOSE,
        EMPLOYEE_ONBOARDING_PURPOSE,
        LEGACY_PASSWORD_SETUP_PURPOSE,
    }

    token_purpose = (
        str(reset_token.get("purpose") or LEGACY_PASSWORD_SETUP_PURPOSE)
        if reset_token is not None
        else ""
    )

    if (
        reset_token is None
        or bool(reset_token["is_revoked"])
        or reset_token["used_at"] is not None
        or token_purpose not in valid_purposes
        or (reset_token["expires_at"] is not None and reset_token["expires_at"] <= now)
    ):
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST,
            status_code=400,
            message="密码设置链接无效或已过期",
        )

    user = (
        session.execute(
            text(
                f"""
                select id, is_active
                from {IAM_USER_TABLE}
                where id = :user_id
                """
            ),
            {"user_id": reset_token["user_id"]},
        )
        .mappings()
        .one_or_none()
    )

    if user is None or int(user["is_active"]) != 1:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST,
            status_code=400,
            message="密码设置链接无效或已过期",
        )

    session.execute(
        text(
            f"""
            update {IAM_USER_TABLE}
            set password_hash = :password_hash,
                password_updated_at = :now,
                updated_at = :now
            where id = :user_id
            """
        ),
        {
            "password_hash": hash_password(new_password),
            "now": now,
            "user_id": reset_token["user_id"],
        },
    )
    session.execute(
        text(
            """
            update iam_password_reset_tokens
            set used_at = :now
            where id = :token_id
            """
        ),
        {"now": now, "token_id": reset_token["id"]},
    )
    session.commit()

    return "登录密码设置成功，请使用新密码登录。"

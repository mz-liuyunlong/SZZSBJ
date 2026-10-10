from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from pydantic import SecretStr

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FeishuPasswordMessage:
    """Password setup message sent through the app bot."""

    recipient_user_id: str | None
    recipient_open_id: str | None
    real_name: str
    setup_url: str
    expires_at: datetime | None
    purpose: str = "password_reset"
    username: str | None = None
    onboarding_guide_url: str | None = None


@dataclass(frozen=True, slots=True)
class FeishuEmployeeOnboardingMessage:
    """New employee onboarding message sent through Feishu."""

    recipient_user_id: str | None
    recipient_open_id: str | None
    real_name: str
    username: str
    setup_url: str
    onboarding_guide_url: str | None = None


@dataclass(frozen=True, slots=True)
class FeishuEmployeeOffboardingNotice:
    """Offboarding notice sent to the responsible person."""

    recipient_user_id: str | None
    recipient_open_id: str | None
    departed_username: str
    departed_name: str


@dataclass(frozen=True, slots=True)
class FeishuDeliveryResult:
    """Safe delivery result without tokens or secrets."""

    sent: bool
    reason: str
    receive_id_type: str | None = None
    message_id: str | None = None


class FeishuDeliveryError(RuntimeError):
    """Raised when Feishu rejects or fails a message delivery request."""


class FeishuService:
    """Send IAM workflow cards through a Feishu/Lark app bot."""

    def __init__(
        self,
        *,
        enabled: bool,
        base_url: str,
        app_id: str | None,
        app_secret: str | None,
        timeout_seconds: float,
    ) -> None:
        self.enabled = enabled
        self.base_url = base_url.rstrip("/")
        self.app_id = app_id
        self.app_secret = app_secret
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_settings(cls) -> FeishuService:
        settings = get_settings()
        app_secret = settings.feishu_app_secret

        return cls(
            enabled=settings.feishu_bot_enabled,
            base_url=settings.feishu_base_url,
            app_id=settings.feishu_app_id,
            app_secret=app_secret.get_secret_value()
            if isinstance(app_secret, SecretStr)
            else app_secret,
            timeout_seconds=settings.feishu_request_timeout_ms / 1000,
        )

    def send_employee_onboarding_card(
        self,
        message: FeishuEmployeeOnboardingMessage,
    ) -> FeishuDeliveryResult:
        return self.send_password_setup_message(
            FeishuPasswordMessage(
                recipient_user_id=message.recipient_user_id,
                recipient_open_id=message.recipient_open_id,
                real_name=message.real_name,
                setup_url=message.setup_url,
                expires_at=None,
                purpose="employee_onboarding",
                username=message.username,
                onboarding_guide_url=message.onboarding_guide_url,
            )
        )

    def send_employee_offboarding_notice(
        self,
        message: FeishuEmployeeOffboardingNotice,
    ) -> FeishuDeliveryResult:
        card = self._build_employee_offboarding_card(message)
        return self._send_interactive_card(
            recipient_user_id=message.recipient_user_id,
            recipient_open_id=message.recipient_open_id,
            card=card,
            action="send employee offboarding notice",
        )

    def send_password_setup_message(
        self,
        message: FeishuPasswordMessage,
    ) -> FeishuDeliveryResult:
        card = self._build_password_setup_card(message)
        return self._send_interactive_card(
            recipient_user_id=message.recipient_user_id,
            recipient_open_id=message.recipient_open_id,
            card=card,
            action="send password setup card",
        )

    def _send_interactive_card(
        self,
        *,
        recipient_user_id: str | None,
        recipient_open_id: str | None,
        card: dict[str, Any],
        action: str,
    ) -> FeishuDeliveryResult:
        if not self.enabled:
            logger.info("Feishu bot delivery skipped because FEISHU_BOT_ENABLED is false.")
            return FeishuDeliveryResult(sent=False, reason="disabled")

        receive_id_type, receive_id = self._resolve_receiver_ids(
            recipient_user_id=recipient_user_id,
            recipient_open_id=recipient_open_id,
        )
        tenant_access_token = self._fetch_tenant_access_token()

        response = self._post_json(
            f"{self.base_url}/open-apis/im/v1/messages?"
            f"{urlencode({'receive_id_type': receive_id_type})}",
            {
                "receive_id": receive_id,
                "msg_type": "interactive",
                "content": json.dumps(card, ensure_ascii=False),
            },
            headers={
                "Authorization": f"Bearer {tenant_access_token}",
            },
        )

        self._ensure_success(response, action=action)

        data = response.get("data")
        message_id = data.get("message_id") if isinstance(data, dict) else None

        logger.info(
            "Feishu interactive card sent.",
            extra={
                "action": action,
                "receive_id_type": receive_id_type,
                "message_id": message_id,
            },
        )

        return FeishuDeliveryResult(
            sent=True,
            reason="sent",
            receive_id_type=receive_id_type,
            message_id=str(message_id) if message_id else None,
        )

    def _resolve_receiver_ids(
        self,
        *,
        recipient_user_id: str | None,
        recipient_open_id: str | None,
    ) -> tuple[str, str]:
        if recipient_open_id:
            return "open_id", recipient_open_id

        if recipient_user_id:
            if recipient_user_id.startswith("ou_"):
                return "open_id", recipient_user_id
            return "user_id", recipient_user_id

        raise FeishuDeliveryError("Feishu recipient is missing")

    def _fetch_tenant_access_token(self) -> str:
        if not self.app_id or not self.app_secret:
            raise FeishuDeliveryError("Feishu app credentials are missing")

        response = self._post_json(
            f"{self.base_url}/open-apis/auth/v3/tenant_access_token/internal",
            {
                "app_id": self.app_id,
                "app_secret": self.app_secret,
            },
            headers={},
        )

        self._ensure_success(response, action="fetch tenant access token")

        token = response.get("tenant_access_token")
        if not isinstance(token, str) or not token:
            raise FeishuDeliveryError("Feishu tenant access token is missing")

        return token

    def _build_password_setup_card(self, message: FeishuPasswordMessage) -> dict[str, Any]:
        is_onboarding = message.purpose == "employee_onboarding"
        header_title = "掌上便捷系统入职账号设置" if is_onboarding else "掌上便捷系统密码设置"
        intro_text = (
            f"你好 {message.real_name}，欢迎加入掌上便捷，请先设置你的系统登录密码。"
            if is_onboarding
            else f"你好 {message.real_name}，请设置你的掌上便捷系统登录密码。"
        )
        validity_text = (
            "入职设置链接长期有效，设置成功后自动失效。" if is_onboarding else "有效期：10 分钟。"
        )

        elements: list[dict[str, Any]] = [
            {"tag": "div", "text": {"tag": "lark_md", "content": intro_text}},
        ]

        if message.username:
            elements.append(
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"系统账号：**{message.username}**",
                    },
                }
            )

        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": validity_text}})

        actions: list[dict[str, Any]] = [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "设置登录密码"},
                "type": "primary",
                "url": message.setup_url,
            }
        ]

        if is_onboarding and message.onboarding_guide_url:
            actions.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看入职指引"},
                    "type": "default",
                    "url": message.onboarding_guide_url,
                }
            )

        elements.append({"tag": "action", "actions": actions})

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": header_title},
            },
            "elements": elements,
        }

    def _build_employee_offboarding_card(
        self,
        message: FeishuEmployeeOffboardingNotice,
    ) -> dict[str, Any]:
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "red",
                "title": {"tag": "plain_text", "content": "掌上便捷系统账号停用通知"},
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            "以下员工系统账号已停用，请确认交接事项：\n"
                            f"姓名：**{message.departed_name}**\n"
                            f"账号：**{message.departed_username}**"
                        ),
                    },
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "系统已执行：账号停用、登录会话撤销、未使用的设置密码链接作废。",
                    },
                },
            ],
        }

    def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                **headers,
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            raise FeishuDeliveryError(
                f"Feishu HTTP error status={exc.code} body={response_body[:500]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise FeishuDeliveryError(f"Feishu network error: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise FeishuDeliveryError("Feishu response is not valid JSON") from exc

    def _ensure_success(self, response: dict[str, Any], *, action: str) -> None:
        code = response.get("code")
        if code == 0:
            return

        msg = response.get("msg")
        raise FeishuDeliveryError(f"Feishu failed to {action}: code={code} msg={msg}")

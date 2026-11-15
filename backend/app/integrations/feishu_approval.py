"""飞书审批只读客户端：只调取 token、实例列表、实例详情。

错误里只带接口名、HTTP 状态和飞书错误码，不带凭证、不带返回内容。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from app.core.config import Settings

TOKEN_PATH = "/open-apis/auth/v3/tenant_access_token/internal"
LIST_PATH = "/open-apis/approval/v4/instances"
DETAIL_PATH = "/open-apis/approval/v4/instances/{instance_code}"
USER_PATH = "/open-apis/contact/v3/users/{user_id}"
TOKEN_REFRESH_SECONDS = 5400
MAX_ATTEMPTS = 3


class FeishuApprovalError(RuntimeError):
    """code 形如 FEISHU_APPROVAL_LIST_HTTP_400_CODE_1390001，可以直接写进运行记录。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class InstancePage:
    instance_codes: list[str]
    page_token: str
    has_more: bool


class FeishuApprovalClient(Protocol):
    def list_instances(
        self,
        *,
        approval_code: str,
        start_ms: int,
        end_ms: int,
        page_size: int,
        page_token: str,
    ) -> InstancePage: ...

    def get_instance(self, instance_code: str) -> dict[str, Any]: ...

    def close(self) -> None: ...


class FeishuUserDirectory(Protocol):
    """能按 user_id 查姓名的客户端（第二家公司用；查不到返回空）。"""

    def get_user_name(self, user_id: str) -> str: ...


class HttpFeishuApprovalClient:
    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.Client | None = None,
        second_company: bool = False,
    ) -> None:
        """second_company=True：用第二家公司飞书的 YC_FEISHU_* 凭证（另一个飞书企业）。"""
        if second_company:
            app_id, secret, base_url = (
                settings.yc_feishu_app_id,
                settings.yc_feishu_app_secret,
                settings.yc_feishu_base_url,
            )
        else:
            app_id, secret, base_url = (
                settings.feishu_app_id,
                settings.feishu_app_secret,
                settings.feishu_base_url,
            )
        if not app_id or secret is None:
            raise FeishuApprovalError(
                "FEISHU_APPROVAL_YC_CREDENTIALS_MISSING"
                if second_company
                else "FEISHU_APPROVAL_CREDENTIALS_MISSING"
            )
        self._app_id = app_id
        self._secret = secret.get_secret_value()
        self._http = http_client or httpx.Client(
            base_url=base_url,
            timeout=settings.feishu_request_timeout_ms / 1000,
        )
        self._token = ""
        self._token_at = 0.0

    def close(self) -> None:
        self._http.close()

    def _call(
        self,
        label: str,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        response: httpx.Response | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = self._http.request(
                    method, path, params=params, json=json_body, headers=headers
                )
            except httpx.HTTPError:
                raise FeishuApprovalError(f"FEISHU_APPROVAL_{label}_TRANSPORT") from None
            if response.status_code != 429 or attempt == MAX_ATTEMPTS - 1:
                break
            time.sleep(2 * (attempt + 1))
        assert response is not None
        body: Any
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        provider_code = body.get("code")
        if response.status_code != 200 or provider_code != 0:
            raise FeishuApprovalError(
                f"FEISHU_APPROVAL_{label}_HTTP_{response.status_code}_CODE_{provider_code}"
            )
        return dict(body)

    def _bearer(self) -> str:
        if not self._token or time.monotonic() - self._token_at > TOKEN_REFRESH_SECONDS:
            body = self._call(
                "TOKEN",
                "POST",
                TOKEN_PATH,
                json_body={"app_id": self._app_id, "app_secret": self._secret},
            )
            token = body.get("tenant_access_token")
            if not isinstance(token, str) or not token:
                raise FeishuApprovalError("FEISHU_APPROVAL_TOKEN_EMPTY")
            self._token, self._token_at = token, time.monotonic()
        return self._token

    def list_instances(
        self,
        *,
        approval_code: str,
        start_ms: int,
        end_ms: int,
        page_size: int,
        page_token: str,
    ) -> InstancePage:
        params: dict[str, Any] = {
            "approval_code": approval_code,
            "start_time": start_ms,
            "end_time": end_ms,
            "page_size": page_size,
        }
        if page_token:
            params["page_token"] = page_token
        body = self._call("LIST", "GET", LIST_PATH, params=params, token=self._bearer())
        data = body.get("data") or {}
        return InstancePage(
            instance_codes=[str(item) for item in data.get("instance_code_list") or []],
            page_token=str(data.get("page_token") or ""),
            has_more=bool(data.get("has_more")),
        )

    def get_instance(self, instance_code: str) -> dict[str, Any]:
        body = self._call(
            "DETAIL",
            "GET",
            DETAIL_PATH.format(instance_code=quote(instance_code, safe="")),
            params={"user_id_type": "user_id", "locale": "zh-CN"},
            token=self._bearer(),
        )
        data = body.get("data")
        return data if isinstance(data, dict) else {}

    def get_user_name(self, user_id: str) -> str:
        """通讯录里这个人的姓名（第二家公司的人不在系统员工表里，靠这个显示姓名）；查不到返回空。"""
        body = self._call(
            "USER",
            "GET",
            USER_PATH.format(user_id=quote(user_id, safe="")),
            params={"user_id_type": "user_id"},
            token=self._bearer(),
        )
        user = (body.get("data") or {}).get("user") or {}
        name = user.get("name") if isinstance(user, dict) else None
        return name.strip() if isinstance(name, str) else ""

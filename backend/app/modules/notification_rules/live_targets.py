"""Resolve draft notification recipients from an existing Feishu app.

Read-only Feishu API. Does not write to DB, create tables or dispatch messages.
Only super-admins should be allowed to invoke this module via the HTTP route.
"""

from __future__ import annotations

from threading import Lock
from time import monotonic
from typing import Any

from app.core.config import get_settings
from app.modules.iam.feishu_directory_service import FeishuDirectoryService

_TTL_SECONDS = 180
_LOCK = Lock()
_CACHED_UNTIL = 0.0
_CACHED: dict[str, Any] | None = None


class FeishuTargetsError(Exception):
    """Safe reason without provider response bodies, tokens, or personal identifiers."""


def fetch_live_targets() -> dict[str, Any]:
    global _CACHED_UNTIL, _CACHED
    now = monotonic()
    with _LOCK:
        if _CACHED is not None and now < _CACHED_UNTIL:
            return {"groups": list(_CACHED["groups"]), "people": list(_CACHED["people"])}

    try:
        settings = get_settings()
    except Exception:
        raise FeishuTargetsError("FEISHU_BACKEND_SETTINGS_UNAVAILABLE") from None
    if (
        not settings.feishu_bot_enabled
        or not settings.feishu_app_id
        or not settings.feishu_app_secret
    ):
        raise FeishuTargetsError("FEISHU_APP_NOT_CONFIGURED_IN_CURRENT_BACKEND")

    client = FeishuDirectoryService.from_settings(settings)
    try:
        token = client._fetch_tenant_access_token()
        groups = _list_groups(client, token)
        users = client.list_visible_users()
    except Exception:
        # Existing directory service exceptions may contain remote response bodies.
        # NEVER expose them to clients and NEVER include tokens in logs.
        raise FeishuTargetsError("FEISHU_DIRECTORY_READ_FAILED") from None

    people = []
    seen_people = set()
    for user in users:
        if (
            not user.open_id
            or not user.name
            or user.is_resigned
            or user.is_frozen
            or user.is_active is False
        ):
            continue
        if user.open_id in seen_people:
            continue
        seen_people.add(user.open_id)
        people.append(
            {
                "id": user.open_id,
                "name": user.name,
                "employee_key": user.user_id or user.employee_id or user.open_id,
                "enabled": True,
                "mapped": True,
            }
        )
    people.sort(key=lambda x: x["name"])
    result = {"groups": groups, "people": people}
    with _LOCK:
        _CACHED = result
        _CACHED_UNTIL = monotonic() + _TTL_SECONDS
    return {"groups": list(groups), "people": list(people)}


def _list_groups(client: FeishuDirectoryService, token: str) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    page_token = ""
    seen_pages = set()
    for _ in range(40):
        params = {"page_size": "50"}
        if page_token:
            params["page_token"] = page_token
        body = client._get_json("/open-apis/im/v1/chats", params, token)
        client._ensure_success(body)
        data = body.get("data") or {}
        if not isinstance(data, dict):
            raise FeishuTargetsError("FEISHU_GROUP_RESPONSE_INVALID")
        items = data.get("items") or []
        if not isinstance(items, list):
            raise FeishuTargetsError("FEISHU_GROUP_RESPONSE_INVALID")
        for chat in items:
            if not isinstance(chat, dict):
                continue
            chat_id = str(chat.get("chat_id") or "")
            name = str(chat.get("name") or "").strip()
            if not chat_id.startswith("oc_") or not name:
                continue
            if chat.get("chat_mode") not in (None, "group"):
                continue
            groups[chat_id] = {"id": chat_id, "name": name, "enabled": True}
        next_page = str(data.get("page_token") or data.get("next_page_token") or "")
        if not bool(data.get("has_more")):
            return sorted(groups.values(), key=lambda g: g["name"])
        if not next_page or next_page in seen_pages:
            raise FeishuTargetsError("FEISHU_GROUP_PAGINATION_INVALID")
        seen_pages.add(next_page)
        page_token = next_page
    raise FeishuTargetsError("FEISHU_GROUP_PAGINATION_LIMIT")

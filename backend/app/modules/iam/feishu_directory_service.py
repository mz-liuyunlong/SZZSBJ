"""Feishu directory integration for IAM user binding.

This module reads visible Feishu users and normalizes identity fields used by
the account, onboarding, password reset, and offboarding workflows.

It intentionally does not require department names. Department IDs are stored as
optional context because department name permissions may be unavailable in early
stages.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class FeishuDirectoryError(RuntimeError):
    """Raised when Feishu directory APIs return an unrecoverable error."""


@dataclass(frozen=True, slots=True)
class FeishuDirectoryUser:
    """Normalized Feishu user identity for local IAM binding."""

    name: str
    open_id: str
    user_id: str | None = None
    union_id: str | None = None
    employee_id: str | None = None
    department_ids: tuple[str, ...] = ()
    is_active: bool | None = None
    is_frozen: bool | None = None
    is_resigned: bool | None = None


@dataclass(frozen=True, slots=True)
class FeishuNameLookupResult:
    """Result for exact real-name lookups.

    The caller should only auto-send password setup messages when exactly one
    active user is matched. Multiple matches must be handled by an administrator
    to avoid sending account links to the wrong person.
    """

    query_name: str
    matches: tuple[FeishuDirectoryUser, ...]

    @property
    def matched_count(self) -> int:
        return len(self.matches)

    @property
    def is_unique(self) -> bool:
        return len(self.matches) == 1

    @property
    def single_user(self) -> FeishuDirectoryUser | None:
        if len(self.matches) != 1:
            return None
        return self.matches[0]


class FeishuDirectoryService:
    """Read Feishu contact users visible to the current app."""

    def __init__(
        self,
        *,
        base_url: str,
        app_id: str | None,
        app_secret: str | None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.app_id = app_id
        self.app_secret = app_secret
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_settings(cls, settings: Any) -> FeishuDirectoryService:
        """Build service from app settings without importing concrete settings type."""

        timeout_ms = int(getattr(settings, "feishu_request_timeout_ms", 10_000) or 10_000)
        return cls(
            base_url=str(getattr(settings, "feishu_base_url", "https://open.feishu.cn")),
            app_id=_optional_secret_to_str(getattr(settings, "feishu_app_id", None)),
            app_secret=_optional_secret_to_str(getattr(settings, "feishu_app_secret", None)),
            timeout_seconds=max(timeout_ms / 1000, 1),
        )

    def get_user_by_open_id(self, open_id: str) -> FeishuDirectoryUser | None:
        """Fetch one Feishu user by open_id."""

        normalized_open_id = open_id.strip()
        if not normalized_open_id:
            return None

        token = self._fetch_tenant_access_token()
        response = self._get_json(
            f"/open-apis/contact/v3/users/{urllib.parse.quote(normalized_open_id, safe='')}",
            {
                "user_id_type": "open_id",
                "department_id_type": "open_department_id",
            },
            token,
        )
        self._ensure_success(response)

        user = (response.get("data") or {}).get("user") or {}
        if not isinstance(user, dict) or not user:
            return None

        return self.normalize_user(user)

    def list_visible_users(self) -> tuple[FeishuDirectoryUser, ...]:
        """List all Feishu users visible to the current app.

        The Feishu contact API is department based. We first list visible
        departments, then list users under each department, and finally de-dupe
        by open_id/user_id/union_id/name.
        """

        token = self._fetch_tenant_access_token()
        department_ids = self._list_visible_department_ids(token)
        users_by_key: dict[str, FeishuDirectoryUser] = {}

        for department_id in department_ids:
            raw_users = self._list_users_by_department(token, department_id)
            for raw_user in raw_users:
                user = self.normalize_user(raw_user, fallback_department_id=department_id)
                if not user.name and not user.open_id:
                    continue

                dedupe_key = user.open_id or user.user_id or user.union_id or user.name
                existing = users_by_key.get(dedupe_key)
                if existing is None:
                    users_by_key[dedupe_key] = user
                    continue

                users_by_key[dedupe_key] = self.merge_users(existing, user)

        return tuple(sorted(users_by_key.values(), key=lambda item: (item.name, item.open_id)))

    def find_users_by_name(
        self,
        real_name: str,
        *,
        users: tuple[FeishuDirectoryUser, ...] | None = None,
        active_only: bool = True,
    ) -> FeishuNameLookupResult:
        """Find Feishu users by exact real-name match."""

        query_name = real_name.strip()
        if not query_name:
            return FeishuNameLookupResult(query_name=query_name, matches=())

        source_users = users if users is not None else self.list_visible_users()
        matches = []

        for user in source_users:
            if user.name.strip() != query_name:
                continue
            if active_only and user.is_resigned is True:
                continue
            if active_only and user.is_frozen is True:
                continue
            matches.append(user)

        return FeishuNameLookupResult(query_name=query_name, matches=tuple(matches))

    @staticmethod
    def normalize_user(
        raw_user: dict[str, Any],
        *,
        fallback_department_id: str | None = None,
    ) -> FeishuDirectoryUser:
        """Normalize raw Feishu user payload into local IAM identity shape."""

        department_ids = raw_user.get("department_ids")
        if not isinstance(department_ids, list):
            department_ids = []

        normalized_department_ids = tuple(
            str(item).strip() for item in department_ids if str(item).strip()
        )

        if not normalized_department_ids and fallback_department_id:
            normalized_department_ids = (fallback_department_id,)

        status = raw_user.get("status")
        if not isinstance(status, dict):
            status = {}

        return FeishuDirectoryUser(
            name=str(raw_user.get("name") or "").strip(),
            open_id=str(raw_user.get("open_id") or "").strip(),
            user_id=_optional_str(raw_user.get("user_id")),
            union_id=_optional_str(raw_user.get("union_id")),
            employee_id=_optional_str(raw_user.get("employee_id")),
            department_ids=normalized_department_ids,
            is_active=_optional_bool(status.get("is_active")),
            is_frozen=_optional_bool(status.get("is_frozen")),
            is_resigned=_optional_bool(status.get("is_resigned")),
        )

    @staticmethod
    def merge_users(
        old: FeishuDirectoryUser,
        new: FeishuDirectoryUser,
    ) -> FeishuDirectoryUser:
        """Merge duplicate user rows returned from multiple departments."""

        department_ids = tuple(dict.fromkeys((*old.department_ids, *new.department_ids)))
        return FeishuDirectoryUser(
            name=old.name or new.name,
            open_id=old.open_id or new.open_id,
            user_id=old.user_id or new.user_id,
            union_id=old.union_id or new.union_id,
            employee_id=old.employee_id or new.employee_id,
            department_ids=department_ids,
            is_active=old.is_active if old.is_active is not None else new.is_active,
            is_frozen=old.is_frozen if old.is_frozen is not None else new.is_frozen,
            is_resigned=old.is_resigned if old.is_resigned is not None else new.is_resigned,
        )

    def _list_visible_department_ids(self, token: str) -> tuple[str, ...]:
        departments = self._get_paged_items(
            "/open-apis/contact/v3/departments/0/children",
            {
                "user_id_type": "open_id",
                "department_id_type": "open_department_id",
                "fetch_child": "true",
            },
            token,
            item_keys=("items", "departments"),
        )

        department_ids = ["0"]
        for department in departments:
            if not isinstance(department, dict):
                continue

            department_id = (
                department.get("open_department_id")
                or department.get("department_id")
                or department.get("id")
            )
            if (
                isinstance(department_id, str)
                and department_id
                and department_id not in department_ids
            ):
                department_ids.append(department_id)

        return tuple(department_ids)

    def _list_users_by_department(
        self,
        token: str,
        department_id: str,
    ) -> tuple[dict[str, Any], ...]:
        users = self._get_paged_items(
            "/open-apis/contact/v3/users/find_by_department",
            {
                "user_id_type": "open_id",
                "department_id_type": "open_department_id",
                "department_id": department_id,
            },
            token,
            item_keys=("items", "users"),
        )
        return tuple(user for user in users if isinstance(user, dict))

    def _get_paged_items(
        self,
        path: str,
        params: dict[str, str],
        token: str,
        *,
        item_keys: tuple[str, ...],
    ) -> list[Any]:
        page_token = ""
        items: list[Any] = []

        while True:
            request_params = {
                **params,
                "page_size": "50",
            }
            if page_token:
                request_params["page_token"] = page_token

            response = self._get_json(path, request_params, token)
            self._ensure_success(response)

            data = response.get("data") or {}
            page_items: list[Any] = []

            if isinstance(data, dict):
                for key in item_keys:
                    value = data.get(key)
                    if isinstance(value, list):
                        page_items = value
                        break

            items.extend(page_items)

            has_more = bool(data.get("has_more")) if isinstance(data, dict) else False
            next_page_token = ""
            if isinstance(data, dict):
                next_page_token = str(data.get("page_token") or data.get("next_page_token") or "")

            if not has_more and not next_page_token:
                break

            page_token = next_page_token

        return items

    def _fetch_tenant_access_token(self) -> str:
        if not self.app_id or not self.app_secret:
            raise FeishuDirectoryError("Feishu credentials are not configured.")

        response = self._post_json(
            "/open-apis/auth/v3/tenant_access_token/internal",
            {
                "app_id": self.app_id,
                "app_secret": self.app_secret,
            },
            token=None,
        )
        self._ensure_success(response)

        token = response.get("tenant_access_token")
        if not isinstance(token, str) or not token:
            raise FeishuDirectoryError("Feishu tenant_access_token is missing.")

        return token

    def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        token: str | None,
    ) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method="POST",
            headers=headers,
        )
        return self._send_request(request)

    def _get_json(
        self,
        path: str,
        params: dict[str, str],
        token: str,
    ) -> dict[str, Any]:
        query = urllib.parse.urlencode(params)
        request = urllib.request.Request(
            f"{self.base_url}{path}?{query}",
            method="GET",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {token}",
            },
        )
        return self._send_request(request)

    def _send_request(self, request: urllib.request.Request) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise FeishuDirectoryError(f"Feishu HTTP error {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise FeishuDirectoryError(f"Feishu URL error: {exc}") from exc

        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise FeishuDirectoryError("Feishu returned invalid JSON.") from exc

        if not isinstance(decoded, dict):
            raise FeishuDirectoryError("Feishu returned an unexpected JSON payload.")

        return decoded

    @staticmethod
    def _ensure_success(response: dict[str, Any]) -> None:
        if response.get("code") == 0:
            return

        raise FeishuDirectoryError(
            f"Feishu API failed: code={response.get('code')!r} msg={response.get('msg')!r}"
        )


def _optional_secret_to_str(value: Any) -> str | None:
    if value is None:
        return None

    if hasattr(value, "get_secret_value"):
        secret = value.get_secret_value()
        return str(secret) if secret else None

    return str(value) if value else None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value

    return None

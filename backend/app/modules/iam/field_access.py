from __future__ import annotations

from collections.abc import Iterable

from app.core.auth import Principal
from app.core.permissions import has_permission
from app.modules.iam.schemas import UserRead

USER_PHONE_PERMISSION = "field:settings:user-management:phone"
USER_EMAIL_PERMISSION = "field:settings:user-management:email"


def filter_user_read(principal: Principal, user: UserRead) -> UserRead:
    """Remove protected user fields from a management response.

    The frontend also hides columns, but the backend remains the security boundary so
    direct API calls and exports cannot recover fields that were not granted.
    """

    updates: dict[str, object] = {}
    if not has_permission(principal, USER_PHONE_PERMISSION):
        updates["phone"] = None
    if not has_permission(principal, USER_EMAIL_PERMISSION):
        updates["email"] = None
    return user.model_copy(update=updates) if updates else user


def filter_user_reads(principal: Principal, users: Iterable[UserRead]) -> list[UserRead]:
    return [filter_user_read(principal, user) for user in users]

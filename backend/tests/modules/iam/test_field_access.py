from datetime import UTC, datetime

from app.core.auth import Principal
from app.modules.iam.field_access import filter_user_read, filter_user_reads
from app.modules.iam.schemas import UserRead


def _user() -> UserRead:
    now = datetime.now(UTC)
    return UserRead(
        id=7,
        username="operator",
        display_name="运营",
        phone="13800000000",
        email="operator@example.test",
        is_active=True,
        is_super_admin=False,
        role_keys=["operations"],
        role_names=["运营"],
        created_at=now,
        updated_at=now,
    )


def test_user_fields_are_redacted_without_field_permissions() -> None:
    filtered = filter_user_read(
        Principal(
            user_id="7",
            permissions=frozenset({"page:settings:user-management:view"}),
        ),
        _user(),
    )

    assert filtered.phone is None
    assert filtered.email is None
    assert filtered.username == "operator"


def test_user_fields_are_independently_granted() -> None:
    filtered = filter_user_read(
        Principal(
            user_id="7",
            permissions=frozenset({"field:settings:user-management:phone"}),
        ),
        _user(),
    )

    assert filtered.phone == "13800000000"
    assert filtered.email is None


def test_super_admin_wildcard_preserves_all_fields() -> None:
    principal = Principal(user_id="1", permissions=frozenset({"*"}))

    assert filter_user_reads(principal, [_user()]) == [_user()]

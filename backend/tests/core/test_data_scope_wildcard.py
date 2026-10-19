from app.core.auth import Principal
from app.core.data_scope import StoreDataScope, resolve_store_scope


def test_store_scope_accepts_trusted_super_admin_wildcard() -> None:
    principal = Principal(user_id="1", permissions=frozenset({"*"}))

    resolved = resolve_store_scope(
        principal=principal,
        resource_key="synthetic-resource",
        permission_key="page:synthetic:view",
        requested_store_id="store-a",
        provider=lambda *_args: StoreDataScope.all(),
    )

    assert resolved == StoreDataScope.selected({"store-a"})

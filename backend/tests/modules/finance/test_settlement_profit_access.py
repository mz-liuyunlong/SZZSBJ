"""Settlement profit permissions / data scope without a database (PRP §5)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.finance.settlement_profit import access as acc
from app.modules.finance.settlement_profit.access import (
    ScopeGrants,
    get_settlement_access,
    load_scope_grants,
)
from app.modules.finance.settlement_profit.keys import UNMAPPED_STORE_ID

BASE = "/api/finance/settlement-profit"
FINANCE = frozenset({acc.VIEW, acc.ADJUST, acc.REVIEW_FIRST})


def access_for(
    permissions: frozenset[str], stores: set[str], owners: set[str] | None = None
) -> acc.SettlementAccess:
    principal = Principal(user_id="201", permissions=permissions)
    return get_settlement_access(principal, ScopeGrants(frozenset(stores), frozenset(owners or ())))


@pytest.mark.parametrize(
    ("permissions", "stores", "owners", "sees"),
    [
        (FINANCE, {"*"}, None, True),
        (frozenset({"*"}), {"*"}, None, True),
        (FINANCE, {"store-a", "store-b"}, None, False),
        (frozenset({acc.VIEW}), {"*"}, None, False),  # management: all stores, not finance
        (frozenset({acc.VIEW}), {"*"}, {"owner-x"}, False),
        (FINANCE, {"*", UNMAPPED_STORE_ID}, None, True),
        (FINANCE, {"store-a", UNMAPPED_STORE_ID}, None, False),  # a grant cannot add it
    ],
)
def test_unmapped_visible_only_to_all_store_finance(permissions, stores, owners, sees) -> None:
    a = access_for(permissions, stores, owners)
    assert a.sees_unmapped is sees
    assert a.store_visible(UNMAPPED_STORE_ID) is sees
    assert UNMAPPED_STORE_ID not in a.store_ids


def test_unmapped_is_never_a_store_filter() -> None:
    a = access_for(FINANCE, {"*"})
    with pytest.raises(ApiError) as err:
        a.requested_stores([UNMAPPED_STORE_ID])
    assert err.value.status_code == 422
    with pytest.raises(ApiError):
        a.requested_stores(["store-a", UNMAPPED_STORE_ID])
    assert a.requested_stores(None) is None
    limited = access_for(FINANCE, {"store-a"})
    assert limited.requested_stores(None) == ["store-a"]
    with pytest.raises(ApiError) as err:
        limited.requested_stores(["store-b"])
    assert err.value.status_code == 403


def test_scope_rules() -> None:
    with pytest.raises(ApiError) as err:
        access_for(FINANCE, set())
    assert err.value.code == "DATA_SCOPE_DENIED"
    owner = access_for(frozenset({acc.VIEW}), {"*"}, {"owner-x"})
    assert owner.owner_ids == frozenset({"owner-x"}) and owner.actor_role == "owner"
    assert owner.owner_visible("owner-x") and not owner.owner_visible("owner-y")
    assert not owner.owner_visible(None)
    # finance roles are never owner-limited
    assert access_for(FINANCE, {"*"}, {"owner-x"}).owner_ids is None
    assert access_for(frozenset({acc.VIEW}), {"*"}, {"*"}).owner_ids is None
    lead = access_for(frozenset({acc.VIEW, acc.CLOSE_MONTH}), {"*"})
    assert lead.actor_role == "finance_lead"


def test_preview_and_non_numeric_principals_are_denied() -> None:
    session = MagicMock(spec=Session)
    for user_id in (PREVIEW_PRINCIPAL_ID, "not-a-number"):
        with pytest.raises(ApiError) as err:
            load_scope_grants(
                Principal(user_id=user_id, permissions=frozenset({acc.VIEW})), session
            )
        assert err.value.code == "DATA_SCOPE_DENIED"
    session.assert_not_called()


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="202", permissions=frozenset({acc.VIEW, acc.ADJUST})
    )
    app.dependency_overrides[load_scope_grants] = lambda: ScopeGrants(frozenset({"*"}), frozenset())
    app.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    return TestClient(app)


@pytest.mark.parametrize("path", ["summary", "orders", "inventory", "reconcile"])
def test_unmapped_store_filter_rejected_before_any_query(client: TestClient, path: str) -> None:
    res = client.get(f"{BASE}/{path}", params={"store_ids": UNMAPPED_STORE_ID})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_routes_require_page_permission() -> None:
    app = create_app()
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="203", permissions=frozenset({"page:finance:other:view"})
    )
    app.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    client = TestClient(app)
    for method, path in [
        ("GET", "/summary"),
        ("GET", "/stores"),
        ("POST", "/orders/review"),
        ("POST", "/months/2030-01/close"),
        ("PUT", "/config/net-profit"),
    ]:
        res = client.request(method, BASE + path, json={}, headers={"Idempotency-Key": "k"})
        assert res.status_code in (403, 422), (method, path)
        if res.status_code == 422:  # body validation runs first; still never a 2xx
            continue
        assert res.json()["error"]["code"] == "FORBIDDEN"


def test_write_routes_need_idempotency_key(client: TestClient) -> None:
    res = client.post(
        f"{BASE}/orders/00000000-0000-0000-0000-000000000001/adjustments",
        json={"kind": "note", "reason": "r", "expected_version": 1},
    )
    assert res.status_code == 422


def test_openapi_lists_every_route_with_response_models() -> None:
    spec = create_app().openapi()
    paths = {p: v for p, v in spec["paths"].items() if p.startswith(BASE)}
    writes = [
        ("post", f"{BASE}/orders/{{line_id}}/adjustments"),
        ("post", f"{BASE}/orders/review"),
        ("post", f"{BASE}/adjustments/{{adjustment_id}}/revoke"),
        ("post", f"{BASE}/months/{{month}}/close"),
        ("post", f"{BASE}/months/{{month}}/reopen"),
        ("put", f"{BASE}/config/net-profit"),
    ]
    for method, path in writes:
        op = paths[path][method]
        assert "$ref" in str(op["responses"]["200"]["content"]), path
        headers = [p["name"] for p in op["parameters"] if p["in"] == "header"]
        assert "Idempotency-Key" in headers, path
    assert len(paths) == 13

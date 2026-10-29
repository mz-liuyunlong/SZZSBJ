"""Store authorization is independent of the shared Lingxing account."""

from types import SimpleNamespace

import pytest

from app.core.api import ApiError
from app.modules.walmart_scf import store_scope


class FakeScalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeSession:
    def __init__(self, values):
        self.values = values

    def scalars(self, _query):
        return FakeScalars(self.values)


def test_verified_store_identity():
    store_scope.verify_store(
        session=FakeSession([SimpleNamespace(store_name="HK2613-Test")]),
        source_account_ref="primary",
        store_id="110711149541688320",
        store_code="HK2613",
    )


@pytest.mark.parametrize("values", [[], [SimpleNamespace(store_name="OTHER-Test")]])
def test_missing_or_mismatched_store_fails_closed(values):
    with pytest.raises(ApiError):
        store_scope.verify_store(
            session=FakeSession(values),
            source_account_ref="primary",
            store_id="110711149541688320",
            store_code="HK2613",
        )


def test_no_implicit_store_grant(monkeypatch):
    monkeypatch.setattr(
        store_scope.RbacRepository,
        "resolve_user_data_scope",
        lambda *a, **kw: {"110704872940532224"},
    )
    principal = SimpleNamespace(user_id="17", permissions=frozenset({"*"}))
    with pytest.raises(ApiError, match="DATA_SCOPE_DENIED"):
        store_scope.verify_store_grant(
            principal=principal,
            session=FakeSession([]),
            store_id="110711149541688320",
        )


def test_explicit_store_grant(monkeypatch):
    monkeypatch.setattr(
        store_scope.RbacRepository,
        "resolve_user_data_scope",
        lambda *a, **kw: {"110711149541688320"},
    )
    principal = SimpleNamespace(user_id="17", permissions=frozenset())
    store_scope.verify_store_grant(
        principal=principal,
        session=FakeSession([]),
        store_id="110711149541688320",
    )

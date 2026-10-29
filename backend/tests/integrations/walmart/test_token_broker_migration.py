"""Pure offline tests. No SSM, SCF, Walmart or SSH connections."""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.integrations.walmart.https_transport import ClientCredentials
from app.integrations.walmart.token_broker import TokenBrokerRejected, issue_store_token
from app.integrations.walmart.token_client import TokenClientRejected, request_store_token


class Secrets:
    def __init__(self):
        self.calls = []

    def get_store_credentials(self, store):
        self.calls.append(store)
        return ClientCredentials("dummy-client", "dummy-secret")


def response(token="dummy-short-token", seconds=900):
    return Mock(
        status_code=200, content=b"{}", json=lambda: {"access_token": token, "expires_in": seconds}
    )


def test_issue_only_bound_store():
    secrets = Secrets()
    calls = []
    def post(url, **kwargs):
        calls.append(url)
        assert kwargs["headers"]["Authorization"].startswith("Basic ")
        return response()

    item = issue_store_token(
        {"version": 1, "operation": "issue_store_token", "store_code": "CN2502"},
        bound_store="CN2502",
        secret_resolver=secrets,
        post=post,
    )
    assert item["store_code"] == "CN2502"
    assert secrets.calls == ["CN2502"]
    assert len(calls) == 1


def test_cross_store_denied_before_secret_read():
    secrets = Secrets()
    with pytest.raises(TokenBrokerRejected, match="TOKEN_CROSS_STORE_DENIED"):
        issue_store_token(
            {"version": 1, "operation": "issue_store_token", "store_code": "HK2613"},
            bound_store="CN2502",
            secret_resolver=secrets,
            post=lambda *a, **k: response(),
        )
    assert secrets.calls == []


@pytest.mark.parametrize(
    "event",
    [
        {},
        {"version": 1, "operation": "marketplace_call", "store_code": "CN2502"},
        {"version": 1, "operation": "issue_store_token", "store_code": "CN2502", "debug": 1},
    ],
)
def test_unapproved_event_denied(event):
    with pytest.raises(TokenBrokerRejected):
        issue_store_token(event, bound_store="CN2502", secret_resolver=Secrets())


def test_provider_failure_has_no_secret():
    with pytest.raises(TokenBrokerRejected) as err:
        issue_store_token(
            {"version": 1, "operation": "issue_store_token", "store_code": "CN2502"},
            bound_store="CN2502",
            secret_resolver=Secrets(),
            post=lambda *a, **k: response(seconds=9999),
        )
    assert "dummy" not in str(err.value)


def test_main_client_rejects_cross_store_and_forged_reply():
    gateway = Mock()
    with pytest.raises(TokenClientRejected, match="TOKEN_STORE_NOT_AUTHORIZED"):
        request_store_token("HK2612", invoker=gateway, authorized_stores=frozenset({"CN2502"}))
    gateway.invoke.assert_not_called()
    gateway.invoke.return_value = {
        "success": True,
        "operation": "issue_store_token",
        "store_code": "HK2612",
        "access_token": "dummy",
        "expires_in": 900,
    }
    with pytest.raises(TokenClientRejected, match="TOKEN_ISSUE_UNAVAILABLE"):
        request_store_token("CN2502", invoker=gateway, authorized_stores=frozenset({"CN2502"}))


def test_main_client_token_not_printed():
    gateway = Mock()
    gateway.invoke.return_value = {
        "success": True,
        "operation": "issue_store_token",
        "store_code": "CN2502",
        "access_token": "dummy-sensitive-token",
        "expires_in": 900,
    }
    token = request_store_token("CN2502", invoker=gateway, authorized_stores=frozenset({"CN2502"}))
    assert token.access_token == "dummy-sensitive-token"
    assert "dummy-sensitive-token" not in repr(token)

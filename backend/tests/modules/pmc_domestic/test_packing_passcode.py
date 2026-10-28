import hashlib
from types import SimpleNamespace

import pytest

from app.core.api import ApiError
from app.modules.pmc_domestic.packing_passcode import _limiter as configured_limiter
from app.modules.pmc_domestic.packing_passcode import verify_domestic_passcode

PASSPHRASE = "sample-passphrase"
DIGEST = hashlib.sha256(PASSPHRASE.encode("utf-8")).hexdigest()


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    counts = {}

    def evaluate(script, count, key):
        current = counts.get(key, 0)
        if "INCR" in script:
            if current >= 10:
                return 0
            counts[key] = current + 1
            return 1
        counts[key] = max(0, current - 1)
        return counts[key]

    monkeypatch.setattr(
        "app.modules.pmc_domestic.packing_passcode._limiter", lambda: SimpleNamespace(eval=evaluate)
    )
    monkeypatch.setenv("PMC_DOMESTIC_PASSCODE_SHA256", DIGEST)
    yield


def test_matching_passphrase_and_approver_is_accepted():
    verify_domestic_passcode("吴贤玲", PASSPHRASE, "actor-1")


def test_wrong_passphrase_is_rejected_without_echoing_it():
    with pytest.raises(ApiError) as err:
        verify_domestic_passcode("吴贤玲", "wrong-passphrase", "actor-2")
    assert err.value.code == "PASSCODE_REJECTED"
    assert err.value.message == "口令不对"
    assert PASSPHRASE not in str(err.value.details)
    assert "wrong-passphrase" not in str(err.value.details)


def test_display_name_is_not_an_authorization_source():
    verify_domestic_passcode("其他人", PASSPHRASE, "actor-3")


@pytest.mark.parametrize("value", [None, "", "  "])
def test_missing_passphrase_is_always_rejected(value):
    with pytest.raises(ApiError) as err:
        verify_domestic_passcode(None, value, "actor-missing")
    assert err.value.code == "PASSCODE_REQUIRED"


def test_ten_failures_lock_the_actor_for_the_window():
    for _ in range(10):
        with pytest.raises(ApiError):
            verify_domestic_passcode("吴贤玲", "wrong-passphrase", "actor-4")
    with pytest.raises(ApiError) as err:
        verify_domestic_passcode("吴贤玲", PASSPHRASE, "actor-4")
    assert err.value.code == "PASSCODE_LOCKED"


def test_missing_hash_does_not_accept_any_passphrase(monkeypatch):
    monkeypatch.delenv("PMC_DOMESTIC_PASSCODE_SHA256", raising=False)
    with pytest.raises(ApiError) as err:
        verify_domestic_passcode("吴贤玲", PASSPHRASE, "actor-5")
    assert err.value.code == "PASSCODE_UNSET"


def test_shared_limiter_failure_cannot_bypass_confirmation(monkeypatch):
    from redis.exceptions import ConnectionError

    def unavailable():
        raise ConnectionError("synthetic unavailable limiter")

    monkeypatch.setattr("app.modules.pmc_domestic.packing_passcode._limiter", unavailable)
    with pytest.raises(ApiError) as err:
        verify_domestic_passcode(None, PASSPHRASE, "actor-offline")
    assert err.value.code == "PASSCODE_LIMITER_UNAVAILABLE"


def test_unconfigured_shared_limiter_is_rejected(monkeypatch):
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    with pytest.raises(ApiError) as err:
        configured_limiter()
    assert err.value.code == "PASSCODE_LIMITER_UNAVAILABLE"


def test_approve_route_cannot_omit_confirmation_before_writing(monkeypatch):
    from unittest.mock import Mock
    from uuid import uuid4

    from app.core.auth import Principal
    from app.modules.pmc_domestic import packing_router
    from app.modules.pmc_domestic.packing_schemas import ApproveCommand

    service = Mock()
    monkeypatch.setattr(packing_router, "PackingService", service)
    command = ApproveCommand(
        source_account_ref="synthetic",
        candidate_version="a" * 64,
        idempotency_key=uuid4(),
        qty=1,
    )
    with pytest.raises(ApiError) as err:
        packing_router.approve(
            None, uuid4(), command, None, Principal("actor"), frozenset({"synthetic"})
        )
    assert err.value.code == "PASSCODE_REQUIRED"
    service.assert_not_called()

import hashlib
from types import SimpleNamespace

import pytest

from app.core.api import ApiError
from app.modules.pmc_domestic.packing_passcode import reset_passcode_failures, verify_domestic_passcode

PASSPHRASE = "sample-passphrase"
DIGEST = hashlib.sha256(PASSPHRASE.encode("utf-8")).hexdigest()


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    reset_passcode_failures()
    monkeypatch.setattr(
        "app.modules.pmc_domestic.packing_passcode.get_settings",
        lambda: SimpleNamespace(pmc_domestic_passcode_sha256=SimpleNamespace(get_secret_value=lambda: DIGEST)),
    )
    yield
    reset_passcode_failures()


def test_matching_passphrase_and_approver_is_accepted():
    verify_domestic_passcode("吴贤玲", PASSPHRASE, "actor-1")


def test_wrong_passphrase_is_rejected_without_echoing_it():
    with pytest.raises(ApiError) as err:
        verify_domestic_passcode("吴贤玲", "wrong-passphrase", "actor-2")
    assert err.value.code == "PASSCODE_REJECTED"
    assert err.value.message == "口令不对"
    assert PASSPHRASE not in str(err.value.details)
    assert "wrong-passphrase" not in str(err.value.details)


def test_other_names_are_rejected_after_the_passphrase_matches():
    with pytest.raises(ApiError) as err:
        verify_domestic_passcode("其他人", PASSPHRASE, "actor-3")
    assert err.value.code == "OPERATOR_NOT_ALLOWED"


def test_ten_failures_lock_the_actor_for_the_window():
    for _ in range(10):
        with pytest.raises(ApiError):
            verify_domestic_passcode("吴贤玲", "wrong-passphrase", "actor-4")
    with pytest.raises(ApiError) as err:
        verify_domestic_passcode("吴贤玲", PASSPHRASE, "actor-4")
    assert err.value.code == "PASSCODE_LOCKED"


def test_missing_hash_does_not_accept_any_passphrase(monkeypatch):
    monkeypatch.setattr(
        "app.modules.pmc_domestic.packing_passcode.get_settings",
        lambda: SimpleNamespace(pmc_domestic_passcode_sha256=None),
    )
    with pytest.raises(ApiError) as err:
        verify_domestic_passcode("吴贤玲", PASSPHRASE, "actor-5")
    assert err.value.code == "PASSCODE_UNSET"

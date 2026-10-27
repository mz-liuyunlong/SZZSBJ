"""Decodo uses the central protected key without breaking legacy ciphertext."""

from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.modules.decodo.service import DecodoError, _cipher


def test_decodo_reuses_shared_key(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.delenv("DECODO_CONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("BUSINESS_CONFIG_ENCRYPTION_KEY", key)
    monkeypatch.delenv("BUSINESS_CONFIG_ENCRYPTION_KEY_FILE", raising=False)
    assert _cipher().decrypt(Fernet(key).encrypt(b"synthetic")) == b"synthetic"


def test_decodo_legacy_key_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = Fernet.generate_key().decode()
    monkeypatch.setenv("DECODO_CONFIG_ENCRYPTION_KEY", legacy)
    monkeypatch.setenv("BUSINESS_CONFIG_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("BUSINESS_CONFIG_ENCRYPTION_KEY_FILE", raising=False)
    assert _cipher().decrypt(Fernet(legacy).encrypt(b"existing")) == b"existing"


def test_decodo_bad_legacy_never_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECODO_CONFIG_ENCRYPTION_KEY", "bad")
    monkeypatch.setenv("BUSINESS_CONFIG_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("BUSINESS_CONFIG_ENCRYPTION_KEY_FILE", raising=False)
    with pytest.raises(DecodoError) as raised:
        _cipher()
    assert raised.value.code == "DECODO_ENCRYPTION_KEY_INVALID"


def test_decodo_fail_closed_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "DECODO_CONFIG_ENCRYPTION_KEY",
        "BUSINESS_CONFIG_ENCRYPTION_KEY",
        "BUSINESS_CONFIG_ENCRYPTION_KEY_FILE",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(DecodoError) as raised:
        _cipher()
    assert raised.value.code == "DECODO_SHARED_ENCRYPTION_KEY_UNAVAILABLE"
    assert raised.value.status == 503


def test_decodo_accepts_shared_protected_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    key = Fernet.generate_key()
    path = tmp_path / "business.key"
    path.write_bytes(key)
    path.chmod(0o600)
    monkeypatch.delenv("DECODO_CONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("BUSINESS_CONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("BUSINESS_CONFIG_ENCRYPTION_KEY_FILE", str(path))
    assert _cipher().decrypt(Fernet(key).encrypt(b"synthetic")) == b"synthetic"

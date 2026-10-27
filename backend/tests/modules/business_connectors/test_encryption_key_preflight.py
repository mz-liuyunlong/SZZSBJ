"""Safe configuration regression checks; no production values or database."""
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.modules.business_connectors.encryption_key import (
    EncryptionKeyUnavailable,
    get_business_fernet,
)
from app.modules.business_connectors.router import ConfigError, _decrypt, _encrypt


def test_missing_key_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BUSINESS_CONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("BUSINESS_CONFIG_ENCRYPTION_KEY_FILE", raising=False)
    with pytest.raises(ConfigError) as raised:
        _encrypt("synthetic")
    assert raised.value.code == "BUSINESS_ENCRYPTION_KEY_MISSING"
    assert raised.value.status == 503


def test_file_key_encrypts_across_restart(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key_file = tmp_path / "business.key"
    key_file.write_bytes(Fernet.generate_key() + b"\n")
    key_file.chmod(0o600)
    monkeypatch.delenv("BUSINESS_CONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("BUSINESS_CONFIG_ENCRYPTION_KEY_FILE", str(key_file))
    ciphertext = _encrypt("synthetic")
    assert _decrypt(ciphertext) == "synthetic"
    assert _decrypt(ciphertext) == "synthetic"


def test_reject_world_readable_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key_file = tmp_path / "business.key"
    key_file.write_bytes(Fernet.generate_key())
    key_file.chmod(0o644)
    monkeypatch.delenv("BUSINESS_CONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("BUSINESS_CONFIG_ENCRYPTION_KEY_FILE", str(key_file))
    with pytest.raises(ConfigError) as raised:
        _encrypt("synthetic")
    assert raised.value.code == "BUSINESS_ENCRYPTION_KEY_FILE_INSECURE"


def test_conflicting_sources_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key_file = tmp_path / "business.key"
    key_file.write_bytes(Fernet.generate_key())
    key_file.chmod(0o600)
    monkeypatch.setenv("BUSINESS_CONFIG_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("BUSINESS_CONFIG_ENCRYPTION_KEY_FILE", str(key_file))
    with pytest.raises(EncryptionKeyUnavailable):
        get_business_fernet()

"""Unit tests for connector secrets and outbound fail-closed controls."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from app.modules.business_connectors.router import (
    ConfigError,
    ConnectorWrite,
    _config,
    _decrypt,
    _encrypt,
    _endpoint,
    _public,
    dispatch_pending,
)


def test_only_official_feishu_webhook_urls_are_accepted() -> None:
    valid = "https://open.feishu.cn/open-apis/bot/v2/hook/abcdefgh12345678"
    assert _endpoint("feishu_webhook", valid) == valid
    for candidate in (
        "http://open.feishu.cn/open-apis/bot/v2/hook/abcdefgh12345678",
        "https://localhost/open-apis/bot/v2/hook/abcdefgh12345678",
        "https://open.feishu.cn.attacker.example/open-apis/bot/v2/hook/abcdefgh12345678",
        "https://open.feishu.cn@other.example/open-apis/bot/v2/hook/abcdefgh12345678",
        "https://open.feishu.cn/open-apis/bot/v2/hook/abcdefgh12345678?token=secret",
    ):
        with pytest.raises(ConfigError):
            _endpoint("feishu_webhook", candidate)


def test_public_connector_never_returns_secret_or_ciphertext() -> None:
    row = {
        "id": uuid4(),
        "kind": "feishu_webhook",
        "name": "Synthetic group",
        "enabled": False,
        "ciphertext": "synthetic-encrypted-api-key",
        "secret_ciphertext": "synthetic-encrypted-signing-secret",
        "config": {
            "webhook_endpoint_ciphertext": "synthetic-encrypted-webhook",
            "daily_limit": 100,
            "monthly_budget_usd": "0",
        },
        "last_test_at": None,
        "last_test_ok": None,
        "updated_at": datetime.now(UTC),
    }
    public = _public(row)
    assert "webhook_endpoint_ciphertext" not in public["config"]
    assert "ciphertext" not in public
    assert "secret_ciphertext" not in public
    assert public["credential_configured"]
    assert public["signing_configured"]


def test_encrypted_secret_requires_protected_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BUSINESS_CONFIG_ENCRYPTION_KEY", raising=False)
    with pytest.raises(ConfigError):
        _encrypt("synthetic-nonproduction-key")
    monkeypatch.setenv("BUSINESS_CONFIG_ENCRYPTION_KEY", Fernet.generate_key().decode())
    ciphertext = _encrypt("synthetic-nonproduction-key")
    assert ciphertext
    assert "synthetic-nonproduction-key" not in ciphertext
    assert _decrypt(ciphertext) == "synthetic-nonproduction-key"


def test_model_cannot_escape_configured_whitelist() -> None:
    payload = ConnectorWrite(
        kind="openai",
        name="Synthetic AI",
        enabled=False,
        default_model="model-unlisted",
        model_allowlist=["model-allowed"],
    )
    with pytest.raises(ConfigError):
        _config(payload)


def test_outbound_notification_worker_is_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BUSINESS_NOTIFICATIONS_OUTBOUND_ENABLED", raising=False)
    assert dispatch_pending(limit=5, actor="synthetic") == {"sent": 0, "failed": 0}

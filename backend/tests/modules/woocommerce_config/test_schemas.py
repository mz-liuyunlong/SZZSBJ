from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.woocommerce_config.schemas import (
    WooCommerceStoreCreate,
    WooCommerceStoreUpdate,
    normalize_store_url,
)
from app.modules.woocommerce_config.service import _read


def test_store_url_normalizes_https_origin() -> None:
    assert normalize_store_url(" HTTPS://WWW.Example.com/ ") == "https://www.example.com"


@pytest.mark.parametrize(
    "value",
    [
        "http://store.example.com",
        "https://store.example.com/wp-admin",
        "https://store.example.com/?consumer_key=secret",
        "https://user:pass@store.example.com",
        "https://127.0.0.1",
        "https://localhost",
        "https://store.example.com:8443",
    ],
)
def test_store_url_rejects_unsafe_or_non_origin_values(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_store_url(value)


def test_create_requires_both_credentials_and_defaults_disabled() -> None:
    payload = WooCommerceStoreCreate(
        name="RINIMA",
        store_url="https://rinima.example.com",
        consumer_key="ck_synthetic",
        consumer_secret="cs_synthetic",
    )
    assert payload.enabled is False
    assert payload.store_url == "https://rinima.example.com"
    assert payload.consumer_key.get_secret_value() == "ck_synthetic"


def test_update_blank_credentials_mean_keep_existing_values() -> None:
    payload = WooCommerceStoreUpdate(
        name="RINIMA",
        store_url="https://rinima.example.com",
        consumer_key="  ",
        consumer_secret="",
        enabled=False,
    )
    assert payload.consumer_key is None
    assert payload.consumer_secret is None


def test_secret_values_are_not_in_model_repr() -> None:
    payload = WooCommerceStoreCreate(
        name="RINIMA",
        store_url="https://rinima.example.com",
        consumer_key="ck_do_not_print",
        consumer_secret="cs_do_not_print",
    )
    rendered = repr(payload)
    assert "ck_do_not_print" not in rendered
    assert "cs_do_not_print" not in rendered


def test_create_rejects_blank_credentials() -> None:
    with pytest.raises(ValidationError):
        WooCommerceStoreCreate(
            name="RINIMA",
            store_url="https://rinima.example.com",
            consumer_key=" ",
            consumer_secret="cs_synthetic",
        )


def test_public_store_read_never_contains_secret_or_ciphertext() -> None:
    row: dict[str, object] = {
        "id": uuid4(),
        "name": "RINIMA",
        "store_url": "https://rinima.example.com",
        "enabled": False,
        "consumer_key_ciphertext": "synthetic-key-ciphertext",
        "consumer_secret_ciphertext": "synthetic-secret-ciphertext",
        "last_test_at": None,
        "last_test_ok": None,
        "last_test_code": None,
        "updated_at": datetime.now(UTC),
    }
    public = _read(row).model_dump()
    assert public["consumer_key_configured"] is True
    assert public["consumer_secret_configured"] is True
    assert "consumer_key_ciphertext" not in public
    assert "consumer_secret_ciphertext" not in public
    assert "synthetic-key-ciphertext" not in repr(public)
    assert "synthetic-secret-ciphertext" not in repr(public)

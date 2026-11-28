from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.exc import IntegrityError

from app.db.session import get_session_factory
from app.modules.business_connectors.encryption_key import (
    EncryptionKeyUnavailable,
    get_business_fernet,
)

from . import repository
from .client import probe_connection
from .schemas import (
    WooCommerceStoreCreate,
    WooCommerceStoreRead,
    WooCommerceStoreUpdate,
    WooCommerceTestResult,
)


class WooCommerceConfigError(Exception):
    def __init__(self, code: str, status: int = 422) -> None:
        self.code = code
        self.status = status
        super().__init__(code)


def _cipher() -> Fernet:
    try:
        return get_business_fernet()
    except EncryptionKeyUnavailable:
        raise WooCommerceConfigError("WOO_ENCRYPTION_KEY_UNAVAILABLE", 503) from None


def _encrypt(value: str) -> str:
    return _cipher().encrypt(value.encode("utf-8")).decode("ascii")


def _decrypt(value: str) -> str:
    try:
        return _cipher().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError):
        raise WooCommerceConfigError("WOO_CREDENTIAL_UNAVAILABLE", 503) from None


def _read(row: Mapping[str, Any]) -> WooCommerceStoreRead:
    return WooCommerceStoreRead(
        id=str(row["id"]),
        name=row["name"],
        store_url=row["store_url"],
        enabled=bool(row["enabled"]),
        consumer_key_configured=bool(
            row.get("consumer_key_configured", row.get("consumer_key_ciphertext"))
        ),
        consumer_secret_configured=bool(
            row.get("consumer_secret_configured", row.get("consumer_secret_ciphertext"))
        ),
        last_test_at=row["last_test_at"],
        last_test_ok=row["last_test_ok"],
        last_test_code=row["last_test_code"],
        updated_at=row["updated_at"],
    )


def list_stores() -> list[WooCommerceStoreRead]:
    with get_session_factory()() as session:
        rows = repository.list_stores(session)
    return [_read(row) for row in rows]


def create_store(payload: WooCommerceStoreCreate, *, actor: str) -> WooCommerceStoreRead:
    if payload.enabled:
        raise WooCommerceConfigError("WOO_TEST_REQUIRED", 409)
    store_id = uuid4()
    try:
        with get_session_factory()() as session:
            row = repository.insert_store(
                session,
                store_id=store_id,
                name=payload.name,
                store_url=payload.store_url,
                consumer_key_ciphertext=_encrypt(payload.consumer_key.get_secret_value()),
                consumer_secret_ciphertext=_encrypt(payload.consumer_secret.get_secret_value()),
                actor=actor,
            )
            repository.add_audit(
                session, actor=actor, action="woocommerce.store.create", store_id=store_id
            )
            session.commit()
    except IntegrityError:
        raise WooCommerceConfigError("WOO_STORE_DOMAIN_EXISTS", 409) from None
    return _read(row)


def update_store(
    store_id: UUID,
    payload: WooCommerceStoreUpdate,
    *,
    actor: str,
) -> WooCommerceStoreRead:
    key_value = payload.consumer_key.get_secret_value() if payload.consumer_key else None
    secret_value = payload.consumer_secret.get_secret_value() if payload.consumer_secret else None
    key_ciphertext = _encrypt(key_value) if key_value else None
    secret_ciphertext = _encrypt(secret_value) if secret_value else None

    try:
        with get_session_factory()() as session:
            current = repository.get_store(session, store_id, for_update=True)
            if current is None:
                raise WooCommerceConfigError("WOO_STORE_NOT_FOUND", 404)

            # A configured store UUID is part of persisted product identity. Do not
            # repoint it to a different website once it has recorded catalog data.
            if payload.store_url != current["store_url"]:
                from sqlalchemy import text as sql_text

                has_catalog = session.execute(
                    sql_text("SELECT to_regclass('dim_woocommerce_products') IS NOT NULL")
                ).scalar_one()
                if (
                    has_catalog
                    and session.execute(
                        sql_text(
                            "SELECT EXISTS (SELECT 1 FROM dim_woocommerce_products "
                            "WHERE store_id = :id)"
                        ),
                        {"id": store_id},
                    ).scalar_one()
                ):
                    raise WooCommerceConfigError("WOO_STORE_ORIGIN_IMMUTABLE", 409)

            # Never reuse credentials automatically across a different origin.
            if payload.store_url != current["store_url"] and not (key_value and secret_value):
                raise WooCommerceConfigError("WOO_DOMAIN_REQUIRES_NEW_CREDENTIALS", 422)

            config_changed = (
                payload.store_url != current["store_url"]
                or key_ciphertext is not None
                or secret_ciphertext is not None
            )
            if payload.enabled and config_changed:
                raise WooCommerceConfigError("WOO_TEST_REQUIRED", 409)
            if payload.enabled and current["last_test_ok"] is not True:
                raise WooCommerceConfigError("WOO_TEST_REQUIRED", 409)

            updated = repository.update_store(
                session,
                store_id=store_id,
                name=payload.name,
                store_url=payload.store_url,
                enabled=payload.enabled,
                consumer_key_ciphertext=key_ciphertext,
                consumer_secret_ciphertext=secret_ciphertext,
                reset_test=config_changed,
                actor=actor,
            )
            if updated is None:
                raise WooCommerceConfigError("WOO_STORE_NOT_FOUND", 404)

            if current["enabled"] != payload.enabled:
                action = (
                    "woocommerce.store.enable" if payload.enabled else "woocommerce.store.disable"
                )
            else:
                action = "woocommerce.store.update"
            repository.add_audit(session, actor=actor, action=action, store_id=store_id)
            from app.modules.woocommerce_products.task_center import register_store

            register_store(
                session, store_id, enabled=bool(updated["enabled"] and updated["last_test_ok"])
            )
            session.commit()
    except IntegrityError:
        raise WooCommerceConfigError("WOO_STORE_DOMAIN_EXISTS", 409) from None
    return _read(updated)


def test_store(store_id: UUID, *, actor: str) -> WooCommerceTestResult:
    # Explicit authenticated action; never scheduled or triggered by saving.
    with get_session_factory()() as session:
        row = repository.get_store(session, store_id)
        if row is None:
            raise WooCommerceConfigError("WOO_STORE_NOT_FOUND", 404)
        store_url = row["store_url"]
        key_ciphertext = row["consumer_key_ciphertext"]
        secret_ciphertext = row["consumer_secret_ciphertext"]

    consumer_key = _decrypt(key_ciphertext)
    consumer_secret = _decrypt(secret_ciphertext)
    code = probe_connection(store_url, consumer_key, consumer_secret)
    ok = code == "OK"

    with get_session_factory()() as session:
        updated = repository.update_test_result(
            session,
            store_id=store_id,
            store_url=store_url,
            consumer_key_ciphertext=key_ciphertext,
            consumer_secret_ciphertext=secret_ciphertext,
            ok=ok,
            code=code,
        )
        if not updated:
            raise WooCommerceConfigError("WOO_CONFIG_CHANGED_DURING_TEST", 409)
        repository.add_audit(
            session, actor=actor, action="woocommerce.store.test", store_id=store_id
        )
        if not ok:
            from app.modules.woocommerce_products.task_center import register_store

            register_store(session, store_id, enabled=False)
        session.commit()

    return WooCommerceTestResult(ok=ok, code=code)

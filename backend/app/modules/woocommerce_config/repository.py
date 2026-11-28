from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

_PUBLIC_COLUMNS = """
    id, name, store_url, enabled,
    consumer_key_ciphertext IS NOT NULL AS consumer_key_configured,
    consumer_secret_ciphertext IS NOT NULL AS consumer_secret_configured,
    last_test_at, last_test_ok, last_test_code, updated_at
"""


def list_stores(session: Session) -> list[Any]:
    return (
        session.execute(
            text(
                f"SELECT {_PUBLIC_COLUMNS} FROM sys_woocommerce_stores ORDER BY created_at DESC, id"
            )
        )
        .mappings()
        .all()
    )


def get_store(
    session: Session,
    store_id: UUID,
    *,
    for_update: bool = False,
) -> Any | None:
    lock_clause = " FOR UPDATE" if for_update else ""
    return (
        session.execute(
            text(f"SELECT * FROM sys_woocommerce_stores WHERE id = :id{lock_clause}"),
            {"id": store_id},
        )
        .mappings()
        .first()
    )


def insert_store(
    session: Session,
    *,
    store_id: UUID,
    name: str,
    store_url: str,
    consumer_key_ciphertext: str,
    consumer_secret_ciphertext: str,
    actor: str,
) -> Any:
    return (
        session.execute(
            text("""
                INSERT INTO sys_woocommerce_stores
                    (id, name, store_url, enabled, consumer_key_ciphertext,
                     consumer_secret_ciphertext, created_by, updated_by)
                VALUES
                    (:id, :name, :store_url, false, :consumer_key_ciphertext,
                     :consumer_secret_ciphertext, :actor, :actor)
                RETURNING *
            """),
            {
                "id": store_id,
                "name": name,
                "store_url": store_url,
                "consumer_key_ciphertext": consumer_key_ciphertext,
                "consumer_secret_ciphertext": consumer_secret_ciphertext,
                "actor": actor,
            },
        )
        .mappings()
        .one()
    )


def update_store(
    session: Session,
    *,
    store_id: UUID,
    name: str,
    store_url: str,
    enabled: bool,
    consumer_key_ciphertext: str | None,
    consumer_secret_ciphertext: str | None,
    reset_test: bool,
    actor: str,
) -> Any | None:
    return (
        session.execute(
            text("""
                UPDATE sys_woocommerce_stores
                   SET name = :name,
                       store_url = :store_url,
                       enabled = :enabled,
                       consumer_key_ciphertext = COALESCE(
                           :consumer_key_ciphertext, consumer_key_ciphertext
                       ),
                       consumer_secret_ciphertext = COALESCE(
                           :consumer_secret_ciphertext, consumer_secret_ciphertext
                       ),
                       last_test_at = CASE WHEN :reset_test THEN NULL ELSE last_test_at END,
                       last_test_ok = CASE WHEN :reset_test THEN NULL ELSE last_test_ok END,
                       last_test_code = CASE WHEN :reset_test THEN NULL ELSE last_test_code END,
                       updated_by = :actor,
                       updated_at = now()
                 WHERE id = :id
                RETURNING *
            """),
            {
                "id": store_id,
                "name": name,
                "store_url": store_url,
                "enabled": enabled,
                "consumer_key_ciphertext": consumer_key_ciphertext,
                "consumer_secret_ciphertext": consumer_secret_ciphertext,
                "reset_test": reset_test,
                "actor": actor,
            },
        )
        .mappings()
        .first()
    )


def update_test_result(
    session: Session,
    *,
    store_id: UUID,
    store_url: str,
    consumer_key_ciphertext: str,
    consumer_secret_ciphertext: str,
    ok: bool,
    code: str,
) -> bool:
    result = session.execute(
        text("""
            UPDATE sys_woocommerce_stores
               SET last_test_at = now(), last_test_ok = :ok, last_test_code = :code
             WHERE id = :id
               AND store_url = :store_url
               AND consumer_key_ciphertext = :consumer_key_ciphertext
               AND consumer_secret_ciphertext = :consumer_secret_ciphertext
        """),
        {
            "id": store_id,
            "store_url": store_url,
            "consumer_key_ciphertext": consumer_key_ciphertext,
            "consumer_secret_ciphertext": consumer_secret_ciphertext,
            "ok": ok,
            "code": code,
        },
    )
    return result.rowcount == 1


def add_audit(session: Session, *, actor: str, action: str, store_id: UUID) -> None:
    session.execute(
        text("""
            INSERT INTO biz_config_audit (id, actor, action, object_id)
            VALUES (:id, :actor, :action, :object_id)
        """),
        {"id": uuid4(), "actor": actor, "action": action, "object_id": str(store_id)},
    )

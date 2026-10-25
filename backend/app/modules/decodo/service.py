"""Backend-only Decodo requests with encrypted configuration and usage accounting."""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
from datetime import UTC, datetime, timedelta
from time import monotonic
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text

from app.db.session import get_session_factory
from app.modules.decodo import local_test
from app.modules.decodo.schemas import DecodoConfigRead, DecodoUsageRead, DecodoUsageRow

SCRAPE_URL = "https://scraper-api.decodo.com/v2/scrape"
US_ZONE = ZoneInfo("America/New_York")


class DecodoError(Exception):
    def __init__(self, code: str, status: int = 502):
        self.code = code
        self.status = status
        super().__init__(code)


def _cipher() -> Fernet:
    key = os.getenv("DECODO_CONFIG_ENCRYPTION_KEY", "")
    if not key:
        raise DecodoError("DECODO_ENCRYPTION_KEY_NOT_CONFIGURED", 503)
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError):
        raise DecodoError("DECODO_ENCRYPTION_KEY_INVALID", 503) from None


def _validate_basic(value: str) -> str:
    header = value.strip()
    if not header.startswith("Basic "):
        raise DecodoError("DECODO_AUTH_MUST_BE_BASIC", 422)
    try:
        decoded = base64.b64decode(header[6:], validate=True)
    except (ValueError, binascii.Error):
        raise DecodoError("DECODO_AUTH_INVALID", 422) from None
    if b":" not in decoded or not decoded.split(b":", 1)[0]:
        raise DecodoError("DECODO_AUTH_INVALID", 422)
    return header


def config_read() -> DecodoConfigRead:
    if local_test.is_enabled():
        return local_test.config_read()
    with get_session_factory()() as session:
        row = (
            session.execute(
                text("""
            SELECT authorization_ciphertext IS NOT NULL AS configured,
                   enabled, us_zip, updated_at, updated_by
              FROM decodo_connector_settings WHERE id = 1
        """)
            )
            .mappings()
            .first()
        )
    return (
        DecodoConfigRead(**dict(row))
        if row
        else DecodoConfigRead(configured=False, enabled=False, us_zip="10001")
    )


def config_write(
    *, authorization: str | None, zip_code: str, enabled: bool, actor: str
) -> DecodoConfigRead:
    if local_test.is_enabled():
        raise DecodoError("DECODO_LOCAL_CONFIG_IS_ENV_ONLY", 409)
    if len(zip_code) != 5 or not zip_code.isascii() or not zip_code.isdigit():
        raise DecodoError("US_ZIP_INVALID", 422)
    encoded = None
    if authorization is not None and authorization.strip():
        encoded = _cipher().encrypt(_validate_basic(authorization).encode("utf-8")).decode("ascii")
    with get_session_factory()() as session:
        # Passing a nullable value does not remove the existing encrypted secret.
        session.execute(
            text("""
            INSERT INTO decodo_connector_settings
                (id, authorization_ciphertext, us_zip, enabled, updated_by, updated_at)
            VALUES (1, :ciphertext, :zip_code, :enabled, :actor, now())
            ON CONFLICT (id) DO UPDATE SET
                authorization_ciphertext = COALESCE(
                    EXCLUDED.authorization_ciphertext,
                    decodo_connector_settings.authorization_ciphertext
                ),
                us_zip = EXCLUDED.us_zip, enabled = EXCLUDED.enabled,
                updated_by = EXCLUDED.updated_by, updated_at = now()
        """),
            {"ciphertext": encoded, "zip_code": zip_code, "enabled": enabled, "actor": actor},
        )
        session.commit()
    return config_read()


def usage_read(days: int = 7) -> DecodoUsageRead:
    if local_test.is_enabled():
        return local_test.usage_read(days)
    today = datetime.now(US_ZONE).date()
    first = today - timedelta(days=days - 1)
    with get_session_factory()() as session:
        records = (
            session.execute(
                text("""
            SELECT request_date_us, target, status, count(*) AS n
              FROM decodo_request_logs
             WHERE request_date_us BETWEEN :start AND :end
             GROUP BY request_date_us, target, status
        """),
                {"start": first, "end": today},
            )
            .mappings()
            .all()
        )
    result = {
        first + timedelta(days=i): DecodoUsageRow(date=first + timedelta(days=i))
        for i in range(days)
    }
    for row in records:
        item = result[row["request_date_us"]]
        n = int(row["n"])
        item.total += n
        if row["target"] == "amazon_product":
            item.amazon_requests += n
        else:
            item.walmart_requests += n
        if row["status"] == "success":
            item.success += n
        elif row["status"] == "failed":
            item.failed += n
        else:
            item.pending += n
    return DecodoUsageRead(today=today, days=list(reversed(result.values())))


def _load_settings() -> tuple[str, str]:
    if local_test.is_enabled():
        try:
            authorization, zip_code = local_test.load_settings()
        except ValueError as exc:
            raise DecodoError(str(exc), 409) from None
        return _validate_basic(authorization), zip_code
    with get_session_factory()() as session:
        row = (
            session.execute(
                text("""
            SELECT enabled, us_zip, authorization_ciphertext
              FROM decodo_connector_settings WHERE id = 1
        """)
            )
            .mappings()
            .first()
        )
    if not row or not row["enabled"] or not row["authorization_ciphertext"]:
        raise DecodoError("DECODO_NOT_CONFIGURED", 409)
    try:
        token = _cipher().decrypt(row["authorization_ciphertext"].encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError):
        raise DecodoError("DECODO_CREDENTIAL_UNAVAILABLE", 503) from None
    return token, row["us_zip"]


def _start_log(target: str, identifier: str, actor: str) -> str:
    if local_test.is_enabled():
        return local_test.start_log(target, identifier, actor)
    event_id = str(uuid4())
    now = datetime.now(UTC)
    with get_session_factory()() as session:
        session.execute(
            text("""
            INSERT INTO decodo_request_logs
              (id, target, identifier, actor_ref, request_date_us, status, started_at)
            VALUES (CAST(:id AS uuid), :target, :identifier, :actor, :us_day, 'pending', :now)
        """),
            {
                "id": event_id,
                "target": target,
                "identifier": identifier,
                "actor": actor,
                "us_day": now.astimezone(US_ZONE).date(),
                "now": now,
            },
        )
        session.commit()
    return event_id


def _finish_log(
    event_id: str, status: str, ms: int, http_status: int | None, code: str | None
) -> None:
    if local_test.is_enabled():
        local_test.finish_log(event_id, status, ms, http_status, code)
        return
    with get_session_factory()() as session:
        session.execute(
            text("""
            UPDATE decodo_request_logs
               SET status = :status, duration_ms = :duration,
                   http_status = :http_status, error_code = :code, finished_at = now()
             WHERE id = CAST(:id AS uuid)
        """),
            {
                "id": event_id,
                "status": status,
                "duration": ms,
                "http_status": http_status,
                "code": code,
            },
        )
        session.commit()


async def scrape(*, target: str, identifier: str, actor: str) -> dict:
    """Exactly one outbound attempt per call; each attempt is durably counted."""
    if target not in ("amazon_product", "walmart_product"):
        raise DecodoError("TARGET_INVALID", 422)
    authorization, zip_code = _load_settings()
    payload = {"target": target, "parse": True}
    if target == "amazon_product":
        payload.update({"query": identifier, "geo": zip_code})
    else:
        payload.update({"product_id": identifier, "delivery_zip": zip_code})
    event_id = _start_log(target, identifier, actor)
    started = monotonic()
    status = "failed"
    http_status: int | None = None
    code: str | None = "DECODO_REQUEST_FAILED"
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(50.0, connect=10.0), follow_redirects=False
        ) as client:
            response = await client.post(
                SCRAPE_URL,
                json=payload,
                headers={
                    "accept": "application/json",
                    "content-type": "application/json",
                    "authorization": authorization,
                },
            )
        http_status = response.status_code
        if response.status_code != 200:
            raise DecodoError("DECODO_UPSTREAM_HTTP_ERROR")
        if len(response.content) > 5_000_000:
            raise DecodoError("DECODO_RESPONSE_TOO_LARGE")
        try:
            body = response.json()
        except ValueError:
            raise DecodoError("DECODO_INVALID_JSON") from None
        if not isinstance(body, dict) or body.get("errors"):
            raise DecodoError("DECODO_PARSE_FAILED")

        root_code = body.get("status_code")
        if root_code is not None and str(root_code) not in {"200", "12000"}:
            raise DecodoError("DECODO_PARSE_FAILED")

        result = body.get("results")

        if isinstance(result, list):
            if len(result) != 1 or not isinstance(result[0], dict):
                raise DecodoError("DECODO_PARSE_FAILED")

            wrapper = result[0]
            wrapper_code = wrapper.get("status_code")

            if wrapper_code is not None and str(wrapper_code) not in {"200", "12000"}:
                raise DecodoError("DECODO_PARSE_FAILED")

            result = wrapper.get("content")

            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except ValueError:
                    raise DecodoError("DECODO_PARSE_FAILED") from None

        for _ in range(4):
            if not isinstance(result, dict):
                raise DecodoError("DECODO_PARSE_FAILED")

            parse_code = result.get("parse_status_code")
            if parse_code is not None and str(parse_code) != "12000":
                raise DecodoError("DECODO_PARSE_FAILED")

            nested = result.get("results")
            if not isinstance(nested, dict):
                break

            result = nested

        if not isinstance(result, dict):
            raise DecodoError("DECODO_PARSE_FAILED")

        if target == "amazon_product":
            if str(result.get("asin") or "").upper() != identifier.upper():
                raise DecodoError("IDENTIFIER_MISMATCH")
        else:
            general = result.get("general") or {}
            if (
                not isinstance(general, dict)
                or str((general.get("meta") or {}).get("sku") or "") != identifier
            ):
                raise DecodoError("IDENTIFIER_MISMATCH")
            url_match = re.search(r"/([0-9]+)(?:[/?#]|$)", str(general.get("url") or ""))
            if url_match is not None and url_match.group(1) != identifier:
                raise DecodoError("IDENTIFIER_MISMATCH")
        title = (
            result.get("title")
            if target == "amazon_product"
            else (result.get("general") or {}).get("title")
        )
        if not title:
            raise DecodoError("TITLE_MISSING")
        status = "success"
        code = None
        return result
    except httpx.TimeoutException:
        code = "DECODO_TIMEOUT"
        raise DecodoError(code) from None
    except httpx.RequestError:
        code = "DECODO_NETWORK_ERROR"
        raise DecodoError(code) from None
    except DecodoError as exc:
        code = exc.code
        raise
    finally:
        _finish_log(event_id, status, int((monotonic() - started) * 1000), http_status, code)


def save_snapshot(*, target: str, sku_id: str, identifier: str, data: dict, actor: str) -> str:
    """Append-only normalized evidence snapshot; never store raw Decodo response."""
    if local_test.is_enabled():
        return local_test.save_snapshot(
            target=target, sku_id=sku_id, identifier=identifier, data=data, actor=actor
        )
    snapshot_id = str(uuid4())
    with get_session_factory()() as session:
        session.execute(
            text("""
            INSERT INTO decodo_product_snapshots
              (id, target, sku_id, identifier, payload, fetched_at, actor_ref, version)
            VALUES (CAST(:id AS uuid), :target, :sku_id, :identifier,
                    CAST(:payload AS jsonb), now(), :actor, 1)
        """),
            {
                "id": snapshot_id,
                "target": target,
                "sku_id": sku_id,
                "identifier": identifier,
                "payload": json.dumps(data, ensure_ascii=False),
                "actor": actor,
            },
        )
        session.commit()
    return snapshot_id

"""Server-side business connector control plane. Secret values are never returned or logged."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, Query, Request
from app.integrations.llm.openai_provider import generate_text
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.api import ApiError, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission, require_super_admin
from app.db.session import get_session_factory

router = APIRouter(prefix="/api/business-rules/connectors", tags=["Business connectors"])
read_perm = Annotated[Principal, Depends(require_permission("business-rules:read"))]
admin_perm = Annotated[Principal, Depends(require_super_admin)]
EVENT_KEYS = frozenset(
    {
        "inventory_alert",
        "sync_failed",
        "ads_alert",
        "approval_pending",
        "ai_completed",
        "finance_completed",
    }
)
VALID_MODELS = re.compile(r"^[a-zA-Z0-9_.:/-]{2,100}$")
VALID_EVENT = re.compile(r"^[a-z][a-z0-9_]{2,79}$")


class ConnectorWrite(BaseModel):
    kind: str
    name: str = Field(min_length=2, max_length=100)
    enabled: bool = False
    endpoint: str | None = None
    credential: str | None = Field(default=None, max_length=4096, repr=False)
    signing_secret: str | None = Field(default=None, max_length=4096, repr=False)
    default_model: str | None = None
    backup_model: str | None = None
    model_allowlist: list[str] = Field(default_factory=list, max_length=30)
    daily_limit: int = Field(default=100, ge=1, le=100000)
    monthly_budget_usd: Decimal = Field(default=Decimal("0"), ge=0, le=1000000)
    max_output_tokens: int = Field(default=1024, ge=1, le=16384)
    input_price_per_million: Decimal = Field(default=Decimal("0"), ge=0, le=100000)
    output_price_per_million: Decimal = Field(default=Decimal("0"), ge=0, le=100000)


class RouteWrite(BaseModel):
    event_key: str
    connector_id: UUID
    enabled: bool = False
    cooldown_seconds: int = Field(default=60, ge=0, le=86400)
    daily_limit: int = Field(default=100, ge=1, le=10000)


class TemplateWrite(BaseModel):
    event_key: str
    title: str = Field(min_length=1, max_length=120)
    body_template: str = Field(min_length=1, max_length=2000)
    enabled: bool = True


class NotifyRequest(BaseModel):
    event_key: str
    source_event_id: str = Field(min_length=8, max_length=128)
    text: str = Field(min_length=1, max_length=2000)


class AIRequest(BaseModel):
    connector_id: UUID
    prompt: str = Field(min_length=1, max_length=10000, repr=False)
    model: str | None = None
    prompt_version: str = Field(min_length=1, max_length=64)


class ConfigError(Exception):
    def __init__(self, code: str, status: int = 422) -> None:
        self.code = code
        self.status = status


def _fail(exc: ConfigError) -> ApiError:
    return ApiError(code=exc.code, status_code=exc.status)


def _key() -> Fernet:
    value = os.getenv("BUSINESS_CONFIG_ENCRYPTION_KEY", "")
    try:
        return Fernet(value.encode("ascii"))
    except (ValueError, TypeError):
        raise ConfigError("BUSINESS_ENCRYPTION_KEY_MISSING", 503) from None


def _encrypt(value: str | None) -> str | None:
    return _key().encrypt(value.encode("utf-8")).decode("ascii") if value else None


def _decrypt(value: str | None) -> str:
    if not value:
        raise ConfigError("CREDENTIAL_NOT_CONFIGURED", 409)
    try:
        return _key().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError):
        raise ConfigError("CREDENTIAL_UNAVAILABLE", 503) from None


def _endpoint(kind: str, value: str | None) -> str:
    if kind == "feishu_webhook":
        if not value:
            raise ConfigError("FEISHU_ENDPOINT_REQUIRED")
        parsed = urlparse(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "open.feishu.cn"
            or parsed.port not in (None, 443)
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not re.fullmatch(r"/open-apis/bot/v2/hook/[A-Za-z0-9_-]{8,160}", parsed.path)
        ):
            raise ConfigError("FEISHU_ENDPOINT_INVALID")
        return value
    if kind == "openai":
        if value and value != "https://api.openai.com/v1":
            raise ConfigError("AI_ENDPOINT_NOT_ALLOWLISTED")
        return "https://api.openai.com/v1"
    raise ConfigError("CONNECTOR_KIND_UNSUPPORTED")


def _config(value: ConnectorWrite) -> dict[str, Any]:
    if value.kind not in ("feishu_webhook", "openai"):
        raise ConfigError("CONNECTOR_KIND_UNSUPPORTED")
    endpoint = (
        _endpoint(value.kind, value.endpoint) if value.kind == "openai" or value.endpoint else None
    )
    if value.kind == "openai":
        models = [value.default_model, value.backup_model, *value.model_allowlist]
        if any(v and not VALID_MODELS.fullmatch(v) for v in models):
            raise ConfigError("AI_MODEL_INVALID")
        if not value.default_model or value.default_model not in value.model_allowlist:
            raise ConfigError("AI_DEFAULT_MODEL_NOT_ALLOWED")
        if value.backup_model and value.backup_model not in value.model_allowlist:
            raise ConfigError("AI_BACKUP_MODEL_NOT_ALLOWED")
    return {
        "endpoint": endpoint if value.kind == "openai" else None,
        "default_model": value.default_model if value.kind == "openai" else None,
        "backup_model": value.backup_model if value.kind == "openai" else None,
        "model_allowlist": value.model_allowlist if value.kind == "openai" else [],
        "daily_limit": value.daily_limit,
        "monthly_budget_usd": str(value.monthly_budget_usd),
        "max_output_tokens": value.max_output_tokens,
        "input_price_per_million": str(value.input_price_per_million),
        "output_price_per_million": str(value.output_price_per_million),
    }


def _public(row: Any) -> dict[str, Any]:
    raw = row["config"] if isinstance(row["config"], dict) else json.loads(row["config"])
    c = {key: value for key, value in raw.items() if key != "webhook_endpoint_ciphertext"}
    return {
        "id": str(row["id"]),
        "kind": row["kind"],
        "name": row["name"],
        "enabled": row["enabled"],
        "credential_configured": bool(row["ciphertext"]),
        "signing_configured": bool(row["secret_ciphertext"]),
        "config": c,
        "last_test_at": row["last_test_at"],
        "last_test_ok": row["last_test_ok"],
        "updated_at": row["updated_at"],
    }


def _audit(session: Any, actor: str, action: str, target: str) -> None:
    session.execute(
        text("""
        INSERT INTO biz_config_audit (id, actor, action, object_id)
        VALUES (:id, :actor, :action, :target)
    """),
        {"id": uuid4(), "actor": actor, "action": action, "target": target},
    )


def _get(session: Any, connector_id: UUID) -> Any:
    row = (
        session.execute(text("SELECT * FROM biz_connectors WHERE id=:id"), {"id": connector_id})
        .mappings()
        .first()
    )
    if row is None:
        raise ConfigError("CONNECTOR_NOT_FOUND", 404)
    return row


@router.get("")
def list_connectors(request: Request, _: read_perm) -> SuccessEnvelope[list[dict[str, Any]], None]:
    with get_session_factory()() as session:
        rows = (
            session.execute(text("SELECT * FROM biz_connectors ORDER BY created_at DESC"))
            .mappings()
            .all()
        )
    return success_response(request, data=[_public(r) for r in rows])


@router.post("")
def create_connector(
    request: Request, payload: ConnectorWrite, principal: admin_perm
) -> SuccessEnvelope[dict[str, Any], None]:
    try:
        cfg = _config(payload)
        if payload.kind == "feishu_webhook" and not payload.endpoint:
            raise ConfigError("FEISHU_ENDPOINT_REQUIRED")
        if payload.kind == "openai" and payload.enabled and not payload.credential:
            raise ConfigError("CREDENTIAL_REQUIRED")
        uid = uuid4()
        with get_session_factory()() as session:
            session.execute(
                text("""
                INSERT INTO biz_connectors (id, kind, name, enabled, ciphertext, secret_ciphertext,
                  config, created_by, updated_by)
                VALUES (:id,:kind,:name,:enabled,:credential,:secret,CAST(:config AS jsonb),:actor,:actor)
            """),
                {
                    "id": uid,
                    "kind": payload.kind,
                    "name": payload.name,
                    "enabled": payload.enabled,
                    "credential": _encrypt(payload.credential),
                    "secret": _encrypt(payload.signing_secret),
                    "config": json.dumps(
                        {
                            **cfg,
                            "webhook_endpoint_ciphertext": _encrypt(
                                _endpoint(payload.kind, payload.endpoint)
                            )
                            if payload.kind == "feishu_webhook"
                            else None,
                        }
                    ),
                    "actor": principal.user_id,
                },
            )
            _audit(session, principal.user_id, "connector.create", str(uid))
            session.commit()
            row = _get(session, uid)
        return success_response(request, data=_public(row))
    except ConfigError as exc:
        raise _fail(exc) from None


@router.put("/{connector_id}")
def update_connector(
    connector_id: UUID, request: Request, payload: ConnectorWrite, principal: admin_perm
) -> SuccessEnvelope[dict[str, Any], None]:
    try:
        with get_session_factory()() as session:
            old = _get(session, connector_id)
            if old["kind"] != payload.kind:
                raise ConfigError("CONNECTOR_KIND_IMMUTABLE")
            cfg = _config(payload)
            old_config = old["config"]
            if isinstance(old_config, str):
                old_config = json.loads(old_config)
            if payload.kind == "feishu_webhook":
                cfg["webhook_endpoint_ciphertext"] = (
                    _encrypt(_endpoint(payload.kind, payload.endpoint))
                    if payload.endpoint
                    else old_config.get("webhook_endpoint_ciphertext")
                )
            if (
                payload.kind == "openai"
                and payload.enabled
                and not (payload.credential or old["ciphertext"])
            ):
                raise ConfigError("CREDENTIAL_REQUIRED")
            session.execute(
                text("""
                UPDATE biz_connectors SET name=:name, enabled=:enabled,
                    ciphertext=COALESCE(:credential,ciphertext),
                    secret_ciphertext=COALESCE(:secret,secret_ciphertext),
                    config=CAST(:config AS jsonb), updated_by=:actor, updated_at=now()
                WHERE id=:id
            """),
                {
                    "id": connector_id,
                    "name": payload.name,
                    "enabled": payload.enabled,
                    "credential": _encrypt(payload.credential),
                    "secret": _encrypt(payload.signing_secret),
                    "config": json.dumps(cfg),
                    "actor": principal.user_id,
                },
            )
            _audit(session, principal.user_id, "connector.update", str(connector_id))
            session.commit()
            row = _get(session, connector_id)
        return success_response(request, data=_public(row))
    except ConfigError as exc:
        raise _fail(exc) from None


@router.delete("/{connector_id}")
def disable_connector(
    connector_id: UUID, request: Request, principal: admin_perm
) -> SuccessEnvelope[dict[str, Any], None]:
    with get_session_factory()() as session:
        _get(session, connector_id)
        session.execute(
            text("UPDATE biz_connectors SET enabled=false, updated_at=now() WHERE id=:id"),
            {"id": connector_id},
        )
        _audit(session, principal.user_id, "connector.disable", str(connector_id))
        session.commit()
        row = _get(session, connector_id)
    return success_response(request, data=_public(row))


@router.post("/{connector_id}/test")
def test_connector(
    connector_id: UUID, request: Request, principal: admin_perm
) -> SuccessEnvelope[dict[str, Any], None]:
    # Explicit user action. Never send on save, list, page load, or migration.
    if os.getenv("BUSINESS_CONNECTOR_TEST_CALLS_ENABLED", "").lower() != "true":
        raise ApiError(code="CONNECTOR_TESTS_DISABLED", status_code=409)
    try:
        with get_session_factory()() as session:
            row = _get(session, connector_id)
            if not row["enabled"]:
                raise ConfigError("CONNECTOR_NOT_ENABLED", 409)
            if row["kind"] == "feishu_webhook":
                try:
                    _post_feishu(row, "SZZSBJ 业务配置中心：飞书群机器人测试消息")
                    success = True
                except ConfigError:
                    success = False
                except httpx.HTTPError:
                    success = False
            else:
                # OpenAI model validation uses an explicit no-generation model lookup.
                # No paid generation or access to business data occurs here.
                credential = _decrypt(row["ciphertext"])
                cfg = row["config"]
                if not isinstance(cfg, dict):
                    cfg = json.loads(cfg)
                model = cfg.get("default_model")
                if not model:
                    raise ConfigError("AI_DEFAULT_MODEL_MISSING", 409)
                try:
                    from openai import OpenAI

                    with OpenAI(api_key=credential, timeout=8.0, max_retries=0) as client:
                        client.models.retrieve(model)
                    success = True
                except Exception:
                    success = False
            session.execute(
                text("""
                    UPDATE biz_connectors SET last_test_at=now(), last_test_ok=:ok,
                        updated_at=now() WHERE id=:id
                """),
                {"id": connector_id, "ok": success},
            )
            _audit(session, principal.user_id, "connector.test", str(connector_id))
            session.commit()
        return success_response(request, data={"ok": success})
    except ConfigError as exc:
        raise _fail(exc) from None


@router.get("/routes/list")
def list_routes(request: Request, _: read_perm) -> SuccessEnvelope[list[dict[str, Any]], None]:
    with get_session_factory()() as session:
        rows = (
            session.execute(text("SELECT * FROM biz_notification_routes ORDER BY created_at DESC"))
            .mappings()
            .all()
        )
    return success_response(request, data=[dict(r) for r in rows])


@router.post("/routes")
def save_route(
    request: Request, payload: RouteWrite, principal: admin_perm
) -> SuccessEnvelope[dict[str, Any], None]:
    if payload.event_key not in EVENT_KEYS:
        raise ApiError(code="EVENT_NOT_ALLOWED", status_code=422)
    with get_session_factory()() as session:
        row = _get(session, payload.connector_id)
        if row["kind"] != "feishu_webhook":
            raise ApiError(code="ROUTE_REQUIRES_FEISHU_CONNECTOR", status_code=422)
        rid = uuid4()
        session.execute(
            text("""
            INSERT INTO biz_notification_routes
              (id,event_key,connector_id,enabled,cooldown_seconds,daily_limit,created_by)
            VALUES (:id,:event,:connector,:enabled,:cooldown,:limit,:actor)
            ON CONFLICT (event_key,connector_id) DO UPDATE SET enabled=EXCLUDED.enabled,
              cooldown_seconds=EXCLUDED.cooldown_seconds,daily_limit=EXCLUDED.daily_limit
        """),
            {
                "id": rid,
                "event": payload.event_key,
                "connector": payload.connector_id,
                "enabled": payload.enabled,
                "cooldown": payload.cooldown_seconds,
                "limit": payload.daily_limit,
                "actor": principal.user_id,
            },
        )
        _audit(session, principal.user_id, "route.save", payload.event_key)
        session.commit()
    return success_response(request, data=payload.model_dump(mode="json"))


@router.get("/templates/list")
def list_templates(request: Request, _: read_perm) -> SuccessEnvelope[list[dict[str, Any]], None]:
    with get_session_factory()() as session:
        rows = (
            session.execute(text("SELECT * FROM biz_notification_templates ORDER BY event_key"))
            .mappings()
            .all()
        )
    return success_response(request, data=[dict(r) for r in rows])


@router.post("/templates")
def save_template(
    request: Request, payload: TemplateWrite, principal: admin_perm
) -> SuccessEnvelope[dict[str, Any], None]:
    if payload.event_key not in EVENT_KEYS:
        raise ApiError(code="EVENT_NOT_ALLOWED", status_code=422)
    with get_session_factory()() as session:
        session.execute(
            text("""
            INSERT INTO biz_notification_templates (id,event_key,title,body_template,enabled,updated_by)
            VALUES (:id,:event,:title,:body,:enabled,:actor)
            ON CONFLICT (event_key) DO UPDATE SET title=EXCLUDED.title,body_template=EXCLUDED.body_template,
                enabled=EXCLUDED.enabled,updated_by=EXCLUDED.updated_by,updated_at=now(),
                version=biz_notification_templates.version + 1
        """),
            {
                "id": uuid4(),
                "event": payload.event_key,
                "title": payload.title,
                "body": payload.body_template,
                "enabled": payload.enabled,
                "actor": principal.user_id,
            },
        )
        _audit(session, principal.user_id, "template.save", payload.event_key)
        session.commit()
    return success_response(request, data=payload.model_dump())


@router.get("/deliveries/list")
def list_deliveries(
    request: Request, _: read_perm, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> SuccessEnvelope[list[dict[str, Any]], None]:
    with get_session_factory()() as session:
        rows = (
            session.execute(
                text("""
            SELECT id, route_id,connector_id,event_key,source_event_id,status,attempts,error_code,template_version,created_at,
                   last_attempt_at,next_retry_at FROM biz_notification_deliveries ORDER BY created_at DESC LIMIT :lim
        """),
                {"lim": limit},
            )
            .mappings()
            .all()
        )
    return success_response(request, data=[dict(r) for r in rows])


@router.get("/audit/list")
def list_audit(request: Request, _: read_perm) -> SuccessEnvelope[list[dict[str, Any]], None]:
    with get_session_factory()() as session:
        rows = (
            session.execute(
                text("SELECT * FROM biz_config_audit ORDER BY created_at DESC LIMIT 100")
            )
            .mappings()
            .all()
        )
    return success_response(request, data=[dict(r) for r in rows])


@router.get("/usage/ai")
def ai_usage_rows(
    request: Request, _: read_perm, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> SuccessEnvelope[list[dict[str, Any]], None]:
    with get_session_factory()() as session:
        rows = session.execute(
            text("""
                SELECT id,connector_id,model,prompt_version,input_tokens,output_tokens,
                       cost_usd,status,error_code,duration_ms,created_by,created_at
                  FROM biz_ai_usage ORDER BY created_at DESC LIMIT :lim
            """),
            {"lim": limit},
        ).mappings().all()
    return success_response(request, data=[dict(row) for row in rows])


@router.get("/usage/summary")
def usage_summary(request: Request, _: read_perm) -> SuccessEnvelope[dict[str, Any], None]:
    with get_session_factory()() as session:
        deliveries = (
            session.execute(
                text("""
            SELECT status, count(*) AS n FROM biz_notification_deliveries
            WHERE created_at >= now() - interval '30 days' GROUP BY status
        """)
            )
            .mappings()
            .all()
        )
        ai = (
            session.execute(
                text("""
            SELECT connector_id, model, sum(input_tokens) AS input_tokens, sum(output_tokens) AS output_tokens,
                   count(*) AS requests, sum(cost_usd) AS cost_usd
            FROM biz_ai_usage WHERE created_at >= now() - interval '30 days'
            GROUP BY connector_id,model
        """)
            )
            .mappings()
            .all()
        )
    return success_response(
        request, data={"notifications": [dict(r) for r in deliveries], "ai": [dict(r) for r in ai]}
    )


def _post_feishu(row: Any, text_value: str) -> None:
    cfg = row["config"] if isinstance(row["config"], dict) else json.loads(row["config"])
    url = _decrypt(cfg.get("webhook_endpoint_ciphertext"))
    # Strict runtime validation also closes the gap on legacy config rows.
    _endpoint("feishu_webhook", url)
    body: dict[str, Any] = {"msg_type": "text", "content": {"text": text_value}}
    if row["secret_ciphertext"]:
        import base64

        timestamp = str(int(time.time()))
        secret = _decrypt(row["secret_ciphertext"])
        signature = base64.b64encode(
            hmac.new(f"{timestamp}\n{secret}".encode(), b"", hashlib.sha256).digest()
        ).decode()
        body.update({"timestamp": timestamp, "sign": signature})
    with httpx.Client(timeout=8, follow_redirects=False, trust_env=False) as client:
        response = client.post(url, json=body)
        if response.status_code != 200:
            raise ConfigError("FEISHU_HTTP_FAILURE", 502)
        try:
            accepted = response.json()
        except ValueError:
            raise ConfigError("FEISHU_INVALID_RESPONSE", 502) from None
        if not isinstance(accepted, dict) or accepted.get("code") != 0:
            raise ConfigError("FEISHU_REJECTED", 502)


@router.post("/notifications/queue")
def enqueue_notification(
    request: Request, payload: NotifyRequest, principal: admin_perm
) -> SuccessEnvelope[dict[str, int], None]:
    if payload.event_key not in EVENT_KEYS:
        raise ApiError(code="EVENT_NOT_ALLOWED", status_code=422)
    # No outgoing action here. A scheduled worker can dispatch explicitly queued deliveries.
    created = 0
    with get_session_factory()() as session:
        template = (
            session.execute(
                text("""
                SELECT title,body_template,enabled,version FROM biz_notification_templates
                 WHERE event_key=:event
            """),
                {"event": payload.event_key},
            )
            .mappings()
            .first()
        )
        if template is not None and not template["enabled"]:
            return success_response(request, data={"queued": 0})
        rendered = payload.text
        if template:
            rendered = (
                template["title"]
                + "\n"
                + (
                    template["body_template"]
                    .replace("{{message}}", payload.text)
                    .replace("{{event_key}}", payload.event_key)
                )
            )
        routes = (
            session.execute(
                text("""
            SELECT r.*,c.enabled AS connector_enabled FROM biz_notification_routes r
            JOIN biz_connectors c ON c.id=r.connector_id AND c.kind='feishu_webhook'
            WHERE r.enabled=true AND c.enabled=true AND r.event_key=:event
        """),
                {"event": payload.event_key},
            )
            .mappings()
            .all()
        )
        for route in routes:
            # Serialize per-route limit/cooldown checks with the eventual insert.
            # Competing event producers cannot bypass thresholds concurrently.
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:route))"),
                {"route": str(route["id"])},
            )
            day_count = session.execute(
                text("""
                SELECT count(*) FROM biz_notification_deliveries WHERE route_id=:id
                AND created_at >= date_trunc('day',now())
            """),
                {"id": route["id"]},
            ).scalar_one()
            if day_count >= route["daily_limit"]:
                continue
            cooldown_count = session.execute(
                text("""
                SELECT count(*) FROM biz_notification_deliveries WHERE route_id=:id
                AND created_at >= now() - (:secs * interval '1 second')
            """),
                {"id": route["id"], "secs": route["cooldown_seconds"]},
            ).scalar_one()
            if cooldown_count:
                continue
            result = session.execute(
                text("""
                INSERT INTO biz_notification_deliveries
                  (id,route_id,connector_id,event_key,source_event_id,rendered_text,status,template_version)
                VALUES (:id,:route,:connector,:event,:source,:body,'queued',:version)
                ON CONFLICT (connector_id,event_key,source_event_id) DO NOTHING
                RETURNING id
            """),
                {
                    "id": uuid4(),
                    "route": route["id"],
                    "connector": route["connector_id"],
                    "event": payload.event_key,
                    "source": payload.source_event_id,
                    "body": rendered,
                    "version": template["version"] if template else None,
                },
            )
            if result.first():
                created += 1
        _audit(session, principal.user_id, "notification.enqueue", payload.event_key)
        session.commit()
    return success_response(request, data={"queued": created})


def dispatch_pending(*, limit: int, actor: str) -> dict[str, int]:
    # Disabled by default, including on production. Activation requires explicit
    # environment authorization as well as enabled connector and route states.
    if os.getenv("BUSINESS_NOTIFICATIONS_OUTBOUND_ENABLED", "").lower() != "true":
        return {"sent": 0, "failed": 0}
    counts = {"sent": 0, "failed": 0}
    with get_session_factory()() as session:
        rows = (
            session.execute(
                text("""
            SELECT d.* FROM biz_notification_deliveries d
            WHERE d.status IN ('queued','failed') AND d.attempts<3
              AND (d.next_retry_at IS NULL OR d.next_retry_at<=now())
            ORDER BY d.created_at FOR UPDATE SKIP LOCKED LIMIT :lim
        """),
                {"lim": limit},
            )
            .mappings()
            .all()
        )
        for delivery in rows:
            row = _get(session, delivery["connector_id"])
            error_code: str | None = None
            ok = False
            if row["enabled"] and delivery["route_id"] is not None:
                active_route = session.execute(
                    text("SELECT enabled FROM biz_notification_routes WHERE id=:id"),
                    {"id": delivery["route_id"]},
                ).scalar_one_or_none()
                if active_route:
                    try:
                        _post_feishu(row, delivery["rendered_text"])
                        ok = True
                    except ConfigError as error:
                        error_code = error.code
                    except httpx.HTTPError:
                        error_code = "FEISHU_NETWORK_FAILURE"
            if not ok and error_code is None:
                error_code = "CONNECTOR_OR_ROUTE_DISABLED"
            attempts = delivery["attempts"] + 1
            session.execute(
                text("""
                UPDATE biz_notification_deliveries SET status=:status,attempts=:attempts,
                  error_code=:error,last_attempt_at=now(),next_retry_at=:retry WHERE id=:id
            """),
                {
                    "id": delivery["id"],
                    "status": "sent" if ok else "failed",
                    "attempts": attempts,
                    "error": error_code,
                    "retry": None
                    if ok or attempts >= 3
                    else datetime.now(UTC) + timedelta(minutes=2**attempts),
                },
            )
            counts["sent" if ok else "failed"] += 1
        _audit(session, actor, "notification.dispatch", str(len(rows)))
        session.commit()
    return counts


@router.post("/notifications/dispatch")
def dispatch_notifications(
    request: Request, principal: admin_perm, limit: Annotated[int, Query(ge=1, le=10)] = 5
) -> SuccessEnvelope[dict[str, int], None]:
    # Explicit manual dispatch, subject to the same outbound guard as Celery.
    return success_response(request, data=dispatch_pending(limit=limit, actor=principal.user_id))


@router.post("/ai/generate")
async def ai_generate(
    request: Request, payload: AIRequest, principal: admin_perm
) -> SuccessEnvelope[dict[str, Any], None]:
    try:
        # Prices must be explicitly checked against the model provider's current pricing.
        # Reserve an upper-bound budget atomically BEFORE creating an outbound request.
        started = time.monotonic()
        reservation_id = uuid4()
        with get_session_factory()() as session:
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": str(payload.connector_id)},
            )
            row = _get(session, payload.connector_id)
            if row["kind"] != "openai" or not row["enabled"]:
                raise ConfigError("AI_CONNECTOR_NOT_ENABLED", 409)
            cfg = row["config"] if isinstance(row["config"], dict) else json.loads(row["config"])
            model = payload.model or cfg.get("default_model")
            if model not in cfg.get("model_allowlist", []):
                raise ConfigError("AI_MODEL_NOT_ALLOWED")
            daily_count = session.execute(
                text("""
                    SELECT count(*) FROM biz_ai_usage
                     WHERE connector_id=:id AND created_at>=date_trunc('day',now())
                """),
                {"id": payload.connector_id},
            ).scalar_one()
            if daily_count >= int(cfg["daily_limit"]):
                raise ConfigError("AI_DAILY_QUOTA_EXCEEDED", 429)
            monthly_budget = Decimal(str(cfg.get("monthly_budget_usd", "0")))
            input_rate = Decimal(str(cfg.get("input_price_per_million", "0")))
            output_rate = Decimal(str(cfg.get("output_price_per_million", "0")))
            if min(monthly_budget, input_rate, output_rate) <= 0:
                raise ConfigError("AI_PRICING_NOT_CONFIGURED", 409)
            # UTF-8 byte count is used as a conservative prompt-token bound.
            max_input_tokens = len(payload.prompt.encode("utf-8"))
            max_output_tokens = int(cfg["max_output_tokens"])
            reserved_cost = (
                Decimal(max_input_tokens) * input_rate + Decimal(max_output_tokens) * output_rate
            ) / Decimal(1000000)
            previous_spend = session.execute(
                text("""
                    SELECT coalesce(sum(cost_usd),0) FROM biz_ai_usage
                     WHERE connector_id=:id AND created_at>=date_trunc('month',now())
                """),
                {"id": payload.connector_id},
            ).scalar_one()
            if Decimal(str(previous_spend)) + reserved_cost > monthly_budget:
                raise ConfigError("AI_MONTHLY_BUDGET_EXCEEDED", 429)
            credential = _decrypt(row["ciphertext"])
            session.execute(
                text("""
                    INSERT INTO biz_ai_usage
                        (id,connector_id,model,prompt_version,input_tokens,output_tokens,
                         cost_usd,status,created_by)
                    VALUES (:id,:connector,:model,:version,0,0,:cost,'pending',:actor)
                """),
                {
                    "id": reservation_id,
                    "connector": payload.connector_id,
                    "model": model,
                    "version": payload.prompt_version,
                    "cost": reserved_cost,
                    "actor": principal.user_id,
                },
            )
            session.commit()

        try:
            content, input_tokens, output_tokens = await generate_text(
                api_key=credential,
                model=model,
                prompt=payload.prompt,
                max_output_tokens=max_output_tokens,
            )
        except Exception:
            # Keep the reserved amount after an indeterminate provider failure;
            # a provider may have billed the call even without returning usage.
            with get_session_factory()() as session:
                session.execute(
                    text("""
                        UPDATE biz_ai_usage
                           SET status='failed',error_code='AI_PROVIDER_FAILURE',
                               duration_ms=:duration WHERE id=:id
                    """),
                    {"id": reservation_id, "duration": int((time.monotonic() - started) * 1000)},
                )
                session.commit()
            raise ConfigError("AI_PROVIDER_FAILURE", 502) from None

        actual_cost = (
            Decimal(input_tokens) * input_rate + Decimal(output_tokens) * output_rate
        ) / Decimal(1000000)
        # Do not reduce accounted usage below zero and do not overstate certainty
        # of the provider's final invoice.
        with get_session_factory()() as session:
            session.execute(
                text("""
                    UPDATE biz_ai_usage
                       SET input_tokens=:input,output_tokens=:output,
                           cost_usd=:cost,status='success',duration_ms=:duration
                     WHERE id=:id
                """),
                {
                    "id": reservation_id,
                    "input": input_tokens,
                    "output": output_tokens,
                    "cost": max(actual_cost, reserved_cost),
                    "duration": int((time.monotonic() - started) * 1000),
                },
            )
            session.commit()
        return success_response(
            request,
            data={
                "text": content,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "estimated_cost_usd": str(actual_cost),
                "billing_note": "configured_rate_estimate",
            },
        )
    except ConfigError as exc:
        raise _fail(exc) from None

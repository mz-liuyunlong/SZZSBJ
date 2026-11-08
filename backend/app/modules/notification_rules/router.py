# ruff: noqa: E501
"""Migration-free rule editor API.

Only existing biz_notification_templates and biz_connectors tables are read/written.
The reserved nr2_/nc2_ key namespaces do not overlap six legacy events.
No event dispatch is offered until a durable, separately approved execution store exists.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.api import ApiError, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_session_factory
from app.modules.business_connectors.encryption_key import (
    EncryptionKeyUnavailable,
    get_business_fernet,
)

from .engine import FIELDS, RuleSpec, simulate
from .live_targets import FeishuTargetsError, fetch_live_targets

router = APIRouter(prefix="/api/business-rules/notification-rules", tags=["Notification rules"])
read_perm = Annotated[Principal, Depends(require_permission("business-rules:read"))]
write_perm = Annotated[Principal, Depends(require_permission("action:settings:business-config:manage-notifications"))]
RULE_PREFIX = "nr2_"
PERSON_PREFIX = "nc2_"
FORMAT = "SZZSBJ_NO_DDL_NOTIFICATION_RULE_V2"
MAX_DOC_BYTES = 256_000
MAX_HISTORY = 25


def fail(code: str, status: int = 409) -> ApiError:
    return ApiError(code=code, status_code=status)


def encode_document(document: dict[str, Any]) -> str:
    blob = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
    if len(blob.encode("utf-8")) > MAX_DOC_BYTES:
        raise fail("RULE_DOCUMENT_TOO_LARGE", 422)
    return blob


def decode_rule(row: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    mapping = dict(row)
    try:
        data = json.loads(mapping["body_template"])
        if data["format"] != FORMAT or not isinstance(data["history"], list):
            raise ValueError("Bad rule envelope")
        spec = RuleSpec.model_validate(data["spec"]).model_dump(mode="json")
        UUID(mapping["event_key"][len(RULE_PREFIX) :])
        return data, spec
    except (ValueError, TypeError, KeyError, AttributeError):
        raise fail("RULE_STORAGE_CORRUPT", 500) from None


def public_rule(row: Any) -> dict[str, Any]:
    _, spec = decode_rule(row)
    return {
        "id": str(UUID(row["event_key"][len(RULE_PREFIX) :])),
        "name": spec["name"],
        "event_key": spec["event_key"],
        "enabled": spec["enabled"],
        "spec": spec,
        "version": int(row["version"]),
        "updated_at": str(row["updated_at"]),
    }


def read_rule(session: Any, ident: UUID, lock: bool = False) -> Any:
    suffix = " FOR UPDATE" if lock else ""
    return (
        session.execute(
            text(
                "SELECT event_key,body_template,version,updated_at FROM biz_notification_templates "
                "WHERE event_key=:key" + suffix
            ),
            {"key": RULE_PREFIX + ident.hex},
        )
        .mappings()
        .first()
    )


def new_history_entry(version: int, actor: str, spec: RuleSpec) -> dict[str, Any]:
    return {
        "version": version,
        "actor": actor,
        "created_at": datetime.now(UTC).isoformat(),
        "spec": spec.model_dump(mode="json"),
    }


def save_rule(rule: RuleSpec, ident: UUID | None, actor: str) -> dict[str, Any]:
    if rule.enabled:
        raise fail("RULE_ACTIVATION_BLOCKED_NO_DDL_RUNTIME")
    new_id = ident or uuid4()
    key = RULE_PREFIX + new_id.hex
    with get_session_factory()() as session:
        if ident is None:
            doc = {
                "format": FORMAT,
                "spec": rule.model_dump(mode="json"),
                "history": [new_history_entry(1, actor, rule)],
            }
            result = session.execute(
                text("""
                INSERT INTO biz_notification_templates
                    (id,event_key,title,body_template,enabled,updated_by)
                VALUES (:id,:key,:title,:document,:enabled,:actor)
                RETURNING event_key,body_template,version,updated_at
            """),
                {
                    "id": uuid4(),
                    "key": key,
                    "title": rule.name,
                    "document": encode_document(doc),
                    "enabled": rule.enabled,
                    "actor": actor,
                },
            )
        else:
            existing = read_rule(session, ident, lock=True)
            if existing is None:
                raise fail("RULE_NOT_FOUND", 404)
            doc, _ = decode_rule(existing)
            version = int(existing["version"]) + 1
            doc["spec"] = rule.model_dump(mode="json")
            doc["history"] = (doc["history"] + [new_history_entry(version, actor, rule)])[
                -MAX_HISTORY:
            ]
            result = session.execute(
                text("""
                UPDATE biz_notification_templates
                SET title=:title,body_template=:document,enabled=:enabled,
                    updated_by=:actor,updated_at=now(),version=version+1
                WHERE event_key=:key
                RETURNING event_key,body_template,version,updated_at
            """),
                {
                    "key": key,
                    "title": rule.name,
                    "document": encode_document(doc),
                    "enabled": rule.enabled,
                    "actor": actor,
                },
            )
        saved = result.mappings().one()
        session.commit()
    return public_rule(saved)


class PersonWrite(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    employee_key: str = Field(min_length=1, max_length=100)
    feishu_open_id: str = Field(min_length=4, max_length=128, repr=False)
    enabled: bool = True


class SimulateBody(BaseModel):
    rule: RuleSpec
    samples: list[dict[str, Any]] = Field(default_factory=list, max_length=300)


@router.get("/mode")
def mode(request: Request, _: read_perm) -> SuccessEnvelope[dict[str, Any], None]:
    return success_response(
        request,
        data={
            "storage": "existing_biz_notification_templates",
            "schema_migration": False,
            "rule_editing": True,
            "simulation": True,
            "automatic_evaluation": False,
            "outbound": False,
        },
    )


@router.get("/fields")
def fields(request: Request, _: read_perm) -> SuccessEnvelope[dict[str, Any], None]:
    return success_response(request, data=FIELDS)


# FEISHU_LIVE_TARGETS_V1: Existing Feishu app, no DB migrations or outbound messages.
@router.get("/targets")
def targets(request: Request, _: write_perm) -> SuccessEnvelope[dict[str, Any], None]:
    try:
        live = fetch_live_targets()
    except FeishuTargetsError as exc:
        raise fail(str(exc), 503) from None

    # Legacy connector options remain valid for existing saved drafts.
    with get_session_factory()() as session:
        existing_groups = (
            session.execute(
                text("""
            SELECT id::text AS id,name,enabled FROM biz_connectors
            WHERE kind='feishu_webhook' ORDER BY name
        """)
            )
            .mappings()
            .all()
        )
        existing_people = (
            session.execute(
                text("""
            SELECT event_key,title,body_template,enabled
            FROM biz_notification_templates WHERE left(event_key,4)='nc2_'
            ORDER BY title LIMIT 1000
        """)
            )
            .mappings()
            .all()
        )

    groups = list(live["groups"])
    known_groups = {g["id"] for g in groups}
    for row in existing_groups:
        if row["id"] not in known_groups:
            groups.append(
                {"id": row["id"], "name": row["name"] + "（旧 Webhook）", "enabled": row["enabled"]}
            )
    people = list(live["people"])
    known_people = {p["id"] for p in people}
    for row in existing_people:
        try:
            doc = json.loads(row["body_template"])
            if doc.get("format") != "SZZSBJ_NO_DDL_PERSON_V2":
                continue
            ident = str(UUID(row["event_key"][4:]))
            if ident not in known_people:
                people.append(
                    {
                        "id": ident,
                        "name": row["title"] + "（旧映射）",
                        "employee_key": doc["employee_key"],
                        "enabled": row["enabled"],
                        "mapped": bool(doc.get("ciphertext")),
                    }
                )
        except (ValueError, TypeError, KeyError, AttributeError):
            raise fail("PERSON_MAPPING_STORAGE_CORRUPT", 500) from None
    return success_response(
        request,
        data={
            "groups": groups,
            "people": people,
            "source": "feishu_app_live",
            "runtime_dispatch": False,
        },
    )


@router.post("/people")
def save_person(
    request: Request, body: PersonWrite, principal: write_perm
) -> SuccessEnvelope[dict[str, Any], None]:
    try:
        encrypted = get_business_fernet().encrypt(body.feishu_open_id.encode()).decode("ascii")
    except EncryptionKeyUnavailable:
        raise fail("BUSINESS_ENCRYPTION_KEY_NOT_AVAILABLE", 503) from None
    with get_session_factory()() as session:
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": "nc2_" + body.employee_key}
        )
        contacts = (
            session.execute(
                text("""
            SELECT event_key,body_template FROM biz_notification_templates
            WHERE left(event_key,4)='nc2_' FOR UPDATE
        """)
            )
            .mappings()
            .all()
        )
        old_key = None
        for row in contacts:
            try:
                doc = json.loads(row["body_template"])
                if doc.get("employee_key") == body.employee_key:
                    old_key = row["event_key"]
                    break
            except (ValueError, TypeError, AttributeError):
                raise fail("PERSON_MAPPING_STORAGE_CORRUPT", 500) from None
        key = old_key or PERSON_PREFIX + uuid4().hex
        payload = encode_document(
            {
                "format": "SZZSBJ_NO_DDL_PERSON_V2",
                "employee_key": body.employee_key,
                "ciphertext": encrypted,
            }
        )
        if old_key:
            session.execute(
                text("""
                UPDATE biz_notification_templates SET title=:name,body_template=:body,
                enabled=:enabled,updated_by=:actor,version=version+1,updated_at=now()
                WHERE event_key=:key
            """),
                {
                    "name": body.name,
                    "body": payload,
                    "enabled": body.enabled,
                    "actor": str(principal.user_id),
                    "key": key,
                },
            )
        else:
            session.execute(
                text("""
                INSERT INTO biz_notification_templates
                (id,event_key,title,body_template,enabled,updated_by)
                VALUES (:id,:key,:name,:body,:enabled,:actor)
            """),
                {
                    "id": uuid4(),
                    "key": key,
                    "name": body.name,
                    "body": payload,
                    "enabled": body.enabled,
                    "actor": str(principal.user_id),
                },
            )
        session.commit()
    return success_response(
        request,
        data={
            "id": str(UUID(key[4:])),
            "name": body.name,
            "employee_key": body.employee_key,
            "enabled": body.enabled,
        },
    )


@router.get("")
def list_rules(request: Request, _: read_perm) -> SuccessEnvelope[list[dict[str, Any]], None]:
    with get_session_factory()() as session:
        rows = (
            session.execute(
                text("""
            SELECT event_key,body_template,version,updated_at
            FROM biz_notification_templates
            WHERE left(event_key,4)='nr2_' ORDER BY updated_at DESC LIMIT 2000
        """)
            )
            .mappings()
            .all()
        )
    return success_response(request, data=[public_rule(r) for r in rows])


@router.post("")
def create_rule(
    request: Request, body: RuleSpec, principal: write_perm
) -> SuccessEnvelope[dict[str, Any], None]:
    return success_response(request, data=save_rule(body, None, str(principal.user_id)))


@router.put("/{rule_id}")
def update_rule(
    rule_id: UUID, request: Request, body: RuleSpec, principal: write_perm
) -> SuccessEnvelope[dict[str, Any], None]:
    return success_response(request, data=save_rule(body, rule_id, str(principal.user_id)))


@router.get("/{rule_id}/versions")
def revisions(
    rule_id: UUID, request: Request, _: read_perm
) -> SuccessEnvelope[list[dict[str, Any]], None]:
    with get_session_factory()() as session:
        row = read_rule(session, rule_id)
        if row is None:
            raise fail("RULE_NOT_FOUND", 404)
        doc, _ = decode_rule(row)
    return success_response(
        request,
        data=[
            {k: item[k] for k in ("version", "actor", "created_at")}
            for item in reversed(doc["history"])
        ],
    )


@router.post("/{rule_id}/restore/{version}")
def restore(
    rule_id: UUID, version: int, request: Request, principal: write_perm
) -> SuccessEnvelope[dict[str, Any], None]:
    with get_session_factory()() as session:
        row = read_rule(session, rule_id)
        if row is None:
            raise fail("RULE_NOT_FOUND", 404)
        doc, _ = decode_rule(row)
        item = next((v for v in doc["history"] if v["version"] == version), None)
        if item is None:
            raise fail("RULE_VERSION_NOT_FOUND", 404)
        rule = RuleSpec.model_validate(item["spec"])
    rule.enabled = False
    return success_response(request, data=save_rule(rule, rule_id, str(principal.user_id)))


@router.post("/simulate")
def simulate_endpoint(
    request: Request, body: SimulateBody, _: read_perm
) -> SuccessEnvelope[dict[str, Any], None]:
    return success_response(request, data=simulate(body.rule, body.samples))


@router.get("/instances")
def instances(
    request: Request, _: read_perm, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> SuccessEnvelope[list[dict[str, Any]], None]:
    raise fail("NOTIFICATION_RUNTIME_STORAGE_NOT_AVAILABLE")


@router.get("/deliveries")
def deliveries(
    request: Request, _: read_perm, limit: Annotated[int, Query(ge=1, le=200)] = 100
) -> SuccessEnvelope[list[dict[str, Any]], None]:
    raise fail("NOTIFICATION_RUNTIME_STORAGE_NOT_AVAILABLE")


@router.post("/evaluate")
def evaluate_endpoint(request: Request, _: write_perm) -> SuccessEnvelope[dict[str, Any], None]:
    raise fail("NOTIFICATION_RUNTIME_DISABLED_NO_DDL")


@router.post("/dispatch")
def dispatch_endpoint(request: Request, _: write_perm) -> SuccessEnvelope[dict[str, Any], None]:
    raise fail("NOTIFICATION_RUNTIME_DISABLED_NO_DDL")


@router.post("/{rule_id}/instances/{object_key}/ack")
def ack_endpoint(
    rule_id: UUID, object_key: str, request: Request, _: write_perm
) -> SuccessEnvelope[dict[str, Any], None]:
    raise fail("NOTIFICATION_RUNTIME_STORAGE_NOT_AVAILABLE")

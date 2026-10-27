"""Isolated PostgreSQL acceptance for AI Skill and keyword task persistence.

Requires AI_RUNTIME_PG_TESTS=1 and a synthetic loopback TEST_DATABASE_URL.
Never connects to a live business database or calls OpenAI.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.modules.ai_runtime import keyword_routes
from app.modules.ai_runtime.provider import (
    resolve_runtime_instructions,
    select_active_connector,
    select_published_skill,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("AI_RUNTIME_PG_TESTS") != "1",
    reason="Requires explicitly opted-in, isolated AI-runtime PostgreSQL test service",
)


@pytest.fixture
def db():
    url = os.environ["TEST_DATABASE_URL"]
    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql"
    assert parsed.host in ("127.0.0.1", "localhost")
    assert parsed.database == "ai_runtime_ci"
    engine = create_engine(url)
    conn = engine.connect()
    transaction = conn.begin()
    session = Session(bind=conn)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        conn.close()
        engine.dispose()


def _connector(db, name: str):
    identifier = uuid4()
    cfg = {
        "default_model": "gpt-6-luna",
        "model_allowlist": ["gpt-6-luna"],
        "application_scenes": ["keyword_launch", "listing_optimization"],
    }
    db.execute(
        text("""INSERT INTO biz_connectors(id,kind,name,enabled,config,created_by,updated_by)
                VALUES (:id,'openai',:name,true,CAST(:config AS jsonb),'synthetic','synthetic')"""),
        {"id": identifier, "name": name, "config": json.dumps(cfg)},
    )
    return identifier


def test_new_migrations_and_skill_connector_isolation(db) -> None:
    from sqlalchemy import inspect

    assert db.scalar(text("SELECT version_num FROM alembic_version")) == (
        "20261027_0061_ai_runtime_skill_context"
    )
    inspector = inspect(db.bind)
    assert "runtime_instructions" in {
        col["name"] for col in inspector.get_columns("ai_runtime_skill_versions")
    }
    one, two = _connector(db, "AI isolation A"), _connector(db, "AI isolation B")
    assert select_active_connector(db, "keyword_launch", one)["id"] == one
    assert select_active_connector(db, "keyword_launch", two)["id"] == two
    reference = "x" * 118_322
    for connector, instructions in [(one, "run A"), (two, "run B")]:
        db.execute(
            text("""INSERT INTO ai_runtime_skill_versions
                (id,connector_id,scene,version,status,instructions,runtime_instructions,created_by)
                VALUES (
                    :id,:connector,'keyword_launch',1,'published',
                    :reference,:runtime,'synthetic'
                )"""),
            {
                "id": uuid4(),
                "connector": connector,
                "reference": reference,
                "runtime": instructions,
            },
        )
    assert (
        resolve_runtime_instructions(
            select_published_skill(db, one, "keyword_launch")["instructions"],
            select_published_skill(db, one, "keyword_launch")["runtime_instructions"],
        )
        == "run A"
    )
    assert select_published_skill(db, two, "keyword_launch")["runtime_instructions"] == "run B"
    assert select_published_skill(db, one, "ai_assistant") is None


def test_job_account_and_owner_isolation_and_idempotency(db, monkeypatch) -> None:
    monkeypatch.setattr(keyword_routes, "has_permission", lambda *_: False)
    account = "synthetic-account-A"
    product = uuid4()
    job_id = uuid4()
    job = {"source_account_ref": account, "product_id": str(product), "request_key": "unique"}
    db.execute(
        text("""INSERT INTO ai_runtime_jobs
            (id,source_account_ref,product_id,requested_by,request_key,input_json)
            VALUES (:id,:account,:product,'operator-a',:key,CAST(:payload AS jsonb))"""),
        {
            "id": job_id,
            "account": account,
            "product": product,
            "key": "unique",
            "payload": json.dumps(job),
        },
    )
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(
                text("""INSERT INTO ai_runtime_jobs
                    (id,source_account_ref,product_id,requested_by,request_key,input_json)
                    VALUES (:id,:account,:product,'operator-b',:key,CAST(:payload AS jsonb))"""),
                {
                    "id": uuid4(),
                    "account": account,
                    "product": product,
                    "key": "unique",
                    "payload": json.dumps(job),
                },
            )

    assert keyword_routes._job(db, job_id, account, SimpleNamespace(user_id="operator-a"))
    with pytest.raises(ApiError):
        keyword_routes._job(db, job_id, account, SimpleNamespace(user_id="operator-b"))
    with pytest.raises(ApiError):
        keyword_routes._job(
            db, job_id, "synthetic-account-B", SimpleNamespace(user_id="operator-a")
        )

    db.execute(
        text("""UPDATE ai_runtime_jobs SET status='cancelled',phase='cancelled'
                WHERE id=:id AND status='queued'"""),
        {"id": job_id},
    )
    assert (
        db.scalar(text("SELECT status FROM ai_runtime_jobs WHERE id=:id"), {"id": job_id})
        == "cancelled"
    )
    db.execute(
        text("""UPDATE ai_runtime_jobs SET status='queued',phase='queued'
                WHERE id=:id AND status='failed'"""),
        {"id": job_id},
    )
    assert db.scalar(text("SELECT status FROM ai_runtime_jobs WHERE id=:id"), {"id": job_id}) == (
        "cancelled"
    )

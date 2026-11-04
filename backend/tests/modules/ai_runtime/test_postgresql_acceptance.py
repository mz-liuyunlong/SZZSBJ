"""Isolated PostgreSQL acceptance for AI Skill and keyword task persistence.

Requires AI_RUNTIME_PG_TESTS=1 and a synthetic loopback TEST_DATABASE_URL.
Never connects to a live business database or calls OpenAI.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.modules.ai_runtime import keyword_routes
from app.modules.ai_runtime.provider import (
    resolve_runtime_instructions,
    select_active_connector,
    select_pinned_skill,
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

    expected_head = ScriptDirectory.from_config(
        Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"))
    )
    assert (
        db.scalar(text("SELECT version_num FROM alembic_version"))
        == expected_head.get_current_head()
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


def test_library_revision_pins_never_cross_connector(db) -> None:
    from app.modules.ai_runtime.provider import AIUnavailable

    first = _connector(db, "Pin scope A")
    second = _connector(db, "Pin scope B")
    skill_id, revision_id = uuid4(), uuid4()
    db.execute(
        text("""INSERT INTO ai_skill_library(id,slug,name,scene,description,created_by)
          VALUES (:id,:slug,'Pinned','keyword_launch','synthetic','synthetic')"""),
        {"id": skill_id, "slug": "test-" + skill_id.hex},
    )
    db.execute(
        text("""INSERT INTO ai_skill_revisions
          (id,skill_id,version,status,instructions,runtime_instructions,created_by)
          VALUES (:id,:sid,1,'retired','historical','run A','synthetic')"""),
        {"id": revision_id, "sid": skill_id},
    )
    db.execute(
        text("""INSERT INTO ai_skill_revision_grants(revision_id,connector_id)
          VALUES (:id,:connector)"""),
        {"id": revision_id, "connector": first},
    )
    assert (
        select_pinned_skill(db, str(revision_id), "keyword_launch", first)["runtime_instructions"]
        == "run A"
    )
    with pytest.raises(AIUnavailable) as denied:
        select_pinned_skill(db, str(revision_id), "keyword_launch", second)
    assert denied.value.code == "AI_SKILL_VERSION_INVALID"


def test_0071_real_historical_migration_preserves_jobs_and_blocks_populated_rollback() -> None:
    """Upgrade an owned disposable PostgreSQL DB seeded at 0070, not a mocked session."""
    import subprocess
    import sys

    import psycopg
    from psycopg import sql

    parsed = make_url(os.environ["TEST_DATABASE_URL"])
    assert os.environ.get("APP_ENV") == "test"
    assert parsed.drivername == "postgresql+psycopg"
    assert parsed.host in ("127.0.0.1", "localhost")
    assert parsed.database == "ai_runtime_ci"
    assert parsed.username == "ai_runtime_ci"
    name = "szzsbj_ai_hist_" + uuid4().hex[:18]
    admin = dict(
        host=parsed.host,
        port=parsed.port,
        user=parsed.username,
        password=parsed.password,
        dbname=parsed.database,
    )
    with psycopg.connect(**admin, autocommit=True) as cx:
        cx.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))

    target = parsed.set(database=name)
    env = os.environ.copy()
    env["APP_ENV"] = "test"
    env["TEST_DATABASE_URL"] = target.render_as_string(hide_password=False)
    env.pop("PRODUCTION_MIGRATIONS_AUTHORIZED", None)
    root = Path(__file__).resolve().parents[3]

    def migrate(operation: str, revision: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", operation, revision],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    try:
        migrate("upgrade", "20261102_0070_ai_skill_soft_delete")
        engine = create_engine(target, hide_parameters=True)
        connector = uuid4()
        other = uuid4()
        job_id = uuid4()
        ids = [uuid4() for _ in range(4)]
        statuses = ["published", "draft", "retired", "published"]
        with engine.begin() as cx:
            for cid, name_value in ((connector, "historical-A"), (other, "historical-B")):
                cx.execute(
                    text("""INSERT INTO biz_connectors
                      (id,kind,name,enabled,config,created_by,updated_by)
                      VALUES (:id,'openai',:name,true,'{}'::jsonb,'test','test')"""),
                    {"id": cid, "name": name_value},
                )
            for n, (ident, status) in enumerate(zip(ids, statuses, strict=True), 1):
                cx.execute(
                    text("""INSERT INTO ai_runtime_skill_versions
                      (id,connector_id,scene,version,status,instructions,
                       runtime_instructions,created_by,deleted_at)
                      VALUES (:id,:connector,'keyword_launch',:v,:status,
                       :instructions,:runtime,'test',:deleted)"""),
                    {
                        "id": ident,
                        "connector": connector,
                        "v": n,
                        "status": status,
                        "instructions": "historical " + str(n),
                        "runtime": "execute " + str(n),
                        "deleted": "2026-10-30 00:00:00+00" if n == 4 else None,
                    },
                )
            cx.execute(
                text("""INSERT INTO ai_runtime_jobs
                  (id,source_account_ref,product_id,requested_by,request_key,input_json)
                  VALUES (:id,'synthetic',:product,'test','historical-queued',
                    CAST(:payload AS jsonb))"""),
                {
                    "id": job_id,
                    "product": uuid4(),
                    "payload": json.dumps(
                        {
                            "connector_id": str(connector),
                            "skill_version_id": str(ids[0]),
                        }
                    ),
                },
            )
        migrate("upgrade", "head")
        with engine.begin() as cx:
            rows = cx.execute(
                text("""SELECT v.version,v.status
              FROM ai_skill_revisions v JOIN ai_skill_library s ON v.skill_id=s.id
              WHERE s.scene='keyword_launch' ORDER BY v.version""")
            ).all()
            assert rows == [(1, "published"), (2, "draft"), (3, "retired")]
            assert cx.scalar(text("SELECT count(*) FROM ai_skill_revision_grants")) == 2
            assert cx.scalar(text("SELECT count(*) FROM ai_skill_bindings")) == 1
            assert cx.scalar(text("SELECT count(*) FROM ai_runtime_skill_versions")) == 4
            job = cx.execute(
                text("SELECT status,input_json FROM ai_runtime_jobs WHERE id=:id"), {"id": job_id}
            ).one()
            assert job.status == "queued"
            assert job.input_json["skill_version_id"] == str(ids[0])
            assert job.input_json["connector_id"] == str(connector)
            pinned = cx.execute(
                text("""SELECT count(*) FROM ai_skill_revision_grants
              WHERE connector_id=:connector"""),
                {"connector": other},
            ).scalar_one()
            assert pinned == 0
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "20261102_0070_ai_skill_soft_delete"],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        with engine.begin() as cx:
            assert (
                cx.scalar(text("SELECT version_num FROM alembic_version"))
                == "20261104_0073_clearance_daily"
            )
            assert cx.scalar(text("SELECT count(*) FROM ai_skill_revisions")) == 3
        engine.dispose()
    finally:
        with psycopg.connect(**admin, autocommit=True) as cx:
            cx.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_publishing_updates_only_existing_bindings_and_keeps_old_grants(db, monkeypatch) -> None:
    from contextlib import nullcontext

    from app.modules.ai_runtime import skill_library_routes

    first = _connector(db, "Subscribed A")
    second = _connector(db, "Subscribed B")
    unbound = _connector(db, "Unsubscribed C")
    sid, old, new = uuid4(), uuid4(), uuid4()
    db.execute(
        text("""INSERT INTO ai_skill_library(id,slug,name,scene,description,created_by)
          VALUES (:id,:slug,'Published','keyword_launch','synthetic','synthetic')"""),
        {"id": sid, "slug": "publication-" + sid.hex},
    )
    for rid, version, status in ((old, 1, "published"), (new, 2, "draft")):
        db.execute(
            text("""INSERT INTO ai_skill_revisions
              (id,skill_id,version,status,instructions,runtime_instructions,created_by)
              VALUES (:id,:sid,:version,:status,'instructions','short','test')"""),
            {"id": rid, "sid": sid, "version": version, "status": status},
        )
    for connector in (first, second):
        db.execute(
            text("""INSERT INTO ai_skill_bindings(connector_id,scene,revision_id)
              VALUES (:connector,'keyword_launch',:revision)"""),
            {"connector": connector, "revision": old},
        )
        db.execute(
            text("""INSERT INTO ai_skill_revision_grants(revision_id,connector_id)
              VALUES (:revision,:connector)"""),
            {"revision": old, "connector": connector},
        )
    monkeypatch.setattr(
        skill_library_routes,
        "get_session_factory",
        lambda: lambda: nullcontext(db),
    )
    monkeypatch.setattr(
        skill_library_routes,
        "success_response",
        lambda request, data: data,
    )
    skill_library_routes.publish(
        sid, new, request=None, principal=SimpleNamespace(user_id="synthetic")
    )
    for connector in (first, second):
        assert (
            db.scalar(
                text("""SELECT revision_id FROM ai_skill_bindings
              WHERE connector_id=:connector AND scene='keyword_launch'"""),
                {"connector": connector},
            )
            == new
        )
        for rid in (old, new):
            assert select_pinned_skill(db, str(rid), "keyword_launch", connector)
    assert (
        db.scalar(
            text("SELECT count(*) FROM ai_skill_bindings WHERE connector_id=:id"),
            {"id": unbound},
        )
        == 0
    )
    from app.modules.ai_runtime.provider import AIUnavailable

    with pytest.raises(AIUnavailable):
        select_pinned_skill(db, str(new), "keyword_launch", unbound)


def test_skill_binding_null_unbind_rebind_keeps_historical_grants(db, monkeypatch) -> None:
    from contextlib import nullcontext

    from app.modules.ai_runtime import skill_library_routes
    from app.modules.ai_runtime.provider import AIUnavailable
    from app.modules.ai_runtime.skill_library_routes import BindingsWrite

    connector = _connector(db, "Skill binding lifecycle A")
    foreign = _connector(db, "Skill binding lifecycle B")
    skill_id, first_revision, next_revision = uuid4(), uuid4(), uuid4()
    db.execute(
        text("""INSERT INTO ai_skill_library(id,slug,name,scene,description,created_by)
          VALUES (:id,:slug,'Lifecycle','keyword_launch','synthetic','synthetic')"""),
        {"id": skill_id, "slug": "binding-" + skill_id.hex},
    )
    for rev, version in ((first_revision, 1), (next_revision, 2)):
        db.execute(
            text("""INSERT INTO ai_skill_revisions
              (id,skill_id,version,status,instructions,runtime_instructions,created_by)
              VALUES (:id,:skill,:version,'published','historical','short','synthetic')"""),
            {"id": rev, "skill": skill_id, "version": version},
        )
    monkeypatch.setattr(
        skill_library_routes,
        "get_session_factory",
        lambda: lambda: nullcontext(db),
    )
    monkeypatch.setattr(
        skill_library_routes,
        "success_response",
        lambda request, data: data,
    )

    def bind(revision):
        return skill_library_routes.save_bindings(
            connector,
            BindingsWrite(bindings={"keyword_launch": revision}),
            request=None,
            principal=SimpleNamespace(user_id="synthetic"),
        )

    def assigned():
        return db.scalar(
            text("""SELECT revision_id FROM ai_skill_bindings
              WHERE connector_id=:connector AND scene='keyword_launch'"""),
            {"connector": connector},
        )

    def granted(revision):
        return db.scalar(
            text("""SELECT count(*) FROM ai_skill_revision_grants
              WHERE revision_id=:revision AND connector_id=:connector"""),
            {"revision": revision, "connector": connector},
        )

    # Empty initial assignment stores NULL only in the binding table.
    assert bind(None) == {"ok": True}
    assert assigned() is None
    assert db.scalar(text("SELECT count(*) FROM ai_skill_revision_grants")) == 0

    # A published revision can be assigned, then unassigned without revocation.
    assert bind(first_revision) == {"ok": True}
    assert assigned() == first_revision
    assert granted(first_revision) == 1
    db.execute(
        text("UPDATE ai_skill_revisions SET status='retired' WHERE id=:revision"),
        {"revision": first_revision},
    )
    assert bind(None) == {"ok": True}
    assert assigned() is None
    assert granted(first_revision) == 1
    assert select_pinned_skill(db, str(first_revision), "keyword_launch", connector)

    # Reassignment follows currently published revisions; no legacy grant is deleted.
    assert bind(next_revision) == {"ok": True}
    assert assigned() == next_revision
    assert granted(next_revision) == 1
    assert granted(first_revision) == 1
    assert bind(None) == {"ok": True}
    assert bind(next_revision) == {"ok": True}
    assert assigned() == next_revision
    assert granted(next_revision) == 1
    assert select_pinned_skill(db, str(first_revision), "keyword_launch", connector)

    for revision in (first_revision, next_revision):
        with pytest.raises(AIUnavailable) as denied:
            select_pinned_skill(db, str(revision), "keyword_launch", foreign)
        assert denied.value.code == "AI_SKILL_VERSION_INVALID"

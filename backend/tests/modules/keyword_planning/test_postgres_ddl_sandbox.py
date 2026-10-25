"""Opt-in PostgreSQL DDL smoke test for V1.1 keyword planning.

Run only with RUN_KW_POSTGRES_SANDBOX=1. This uses an ephemeral Docker
PostgreSQL container with no network, published ports, or mounted volumes.
It never reads DATABASE_URL, never calls Alembic upgrade, and destroys
only its own randomly named container.

Scope: frozen 0055 TABLE_DDL/INDEX_DDL/GUARD_DDL against minimal synthetic
parent tables, NOT the historical 0054->0056 Alembic migration chain.
"""

from __future__ import annotations

import ast
import json
import os
import re
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest

MIGRATION_FILE = (
    Path(__file__).resolve().parents[3] / "alembic/versions/20261023_0055_keyword_planning_core.py"
)


def _read_literal_ddl() -> dict[str, tuple[str, ...]]:
    source = MIGRATION_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MIGRATION_FILE))
    names = {"TABLE_DDL", "INDEX_DDL", "GUARD_DDL", "NEW_TABLES", "REQUIRED_EXISTING"}
    result: dict[str, tuple[str, ...]] = {}
    for statement in tree.body:
        if not isinstance(statement, ast.Assign):
            continue
        for target in statement.targets:
            if isinstance(target, ast.Name) and target.id in names:
                value = ast.literal_eval(statement.value)
                if not isinstance(value, tuple) or not all(isinstance(x, str) for x in value):
                    raise AssertionError(f"Unexpected migration literal: {target.id}")
                result[target.id] = value
    assert set(result) == names, f"Missing literal migration data: {names - set(result)}"
    assert "SET LOCAL search_path TO public" in source, "Missing public schema scope fix"
    assert "NEW.status = 'retired'" in source, "Missing reviewed rule retirement fix"
    assert len(result["TABLE_DDL"]) == 21
    assert len(result["INDEX_DDL"]) == 13
    assert len(result["GUARD_DDL"]) == 20  # 3 functions and 17 triggers
    functions = [ddl for ddl in result["GUARD_DDL"] if ddl.startswith("CREATE FUNCTION ")]
    assert len(functions) == 3
    assert all(ddl.rstrip().endswith("END;\n$$") for ddl in functions), (
        "PL/pgSQL function body must close with END; before $$"
    )
    assert result["REQUIRED_EXISTING"] == ("products", "product_platform_listings")
    assert len(result["NEW_TABLES"]) == 21
    for name in result["NEW_TABLES"]:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", name)
    assert len(set(result["NEW_TABLES"])) == 21
    return result


def _quoted_list(values: tuple[str, ...]) -> str:
    for value in values:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", value)
    return ",".join(f"'{value}'" for value in values)


def _rejected(sql: str, *, contains: str = "", state: str = "") -> str:
    """Inside a PL/pgSQL subtransaction, expect the SQL to fail safely."""
    assert (contains != "") != (state != "")
    condition = f"position('{contains}' in err) = 0" if contains else f"code <> '{state}'"
    return f"""
DO $kw_test$
DECLARE err text; code text;
BEGIN
    BEGIN
        {sql};
        RAISE EXCEPTION 'KW_UNEXPECTED_ACCEPTANCE';
    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS err = MESSAGE_TEXT, code = RETURNED_SQLSTATE;
        IF err = 'KW_UNEXPECTED_ACCEPTANCE' OR {condition} THEN
            RAISE EXCEPTION 'KW_WRONG_GUARD_RESPONSE: %, %', code, err;
        END IF;
    END;
END
$kw_test$;
"""


def _build_smoke_sql(data: dict[str, tuple[str, ...]]) -> str:
    tables = _quoted_list(data["NEW_TABLES"])
    indexes = _quoted_list(
        tuple(re.search(r"\bCREATE INDEX\s+(\w+)", ddl).group(1) for ddl in data["INDEX_DDL"])
    )
    functions = _quoted_list(
        tuple(
            re.search(r"\bCREATE FUNCTION\s+(\w+)", ddl).group(1)
            for ddl in data["GUARD_DDL"]
            if "CREATE FUNCTION" in ddl
        )
    )
    triggers = _quoted_list(
        tuple(
            re.search(r"\bCREATE TRIGGER\s+(\w+)", ddl).group(1)
            for ddl in data["GUARD_DDL"]
            if "CREATE TRIGGER" in ddl
        )
    )

    product = "00000000-0000-0000-0000-000000000001"
    rule_set = "00000000-0000-0000-0000-000000000002"
    rule_version = "00000000-0000-0000-0000-000000000003"
    asin_snapshot = "00000000-0000-0000-0000-000000000004"
    upload = "00000000-0000-0000-0000-000000000005"

    statements = [
        "BEGIN;",
        "SET LOCAL search_path TO public;",
        "CREATE TABLE products (id UUID PRIMARY KEY);",
        "CREATE TABLE product_platform_listings (id UUID PRIMARY KEY);",
    ]
    statements.extend(
        s.rstrip("; ") + ";"
        for section in ("TABLE_DDL", "INDEX_DDL", "GUARD_DDL")
        for s in data[section]
    )
    statements.append(f"""
SELECT 'KW_COUNTS|' ||
  (SELECT COUNT(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND c.relkind='r' AND c.relname IN ({tables})) || '|' ||
  (SELECT COUNT(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND c.relkind='i' AND c.relname IN ({indexes})) || '|' ||
  (SELECT COUNT(*) FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
   JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND c.relname IN ({tables})) || '|' ||
  (SELECT COUNT(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
   WHERE n.nspname='public' AND p.proname IN ({functions})) || '|' ||
  (SELECT COUNT(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
   JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE NOT t.tgisinternal AND n.nspname='public' AND t.tgname IN ({triggers}));
""")
    statements.extend(
        [
            f"INSERT INTO products(id) VALUES ('{product}');",
            (
                "INSERT INTO ai_kw_rule_set (rule_key,rule_type,display_name,created_by,id) "
                f"VALUES ('kw-smoke','scoring','QA','qa','{rule_set}');"
            ),
            (
                "INSERT INTO ai_kw_rule_version "
                "(rule_set_id,version_number,status,config_json,config_sha256,"
                "schema_version,engine_version,id) "
                f"VALUES ('{rule_set}',1,'draft','{{}}'::jsonb,repeat('a',64),"
                f"'1','engine','{rule_version}');"
            ),
            (
                "UPDATE ai_kw_rule_version SET status='published',"
                f"published_by='qa',published_at=now() WHERE id='{rule_version}';"
            ),
            _rejected(
                "UPDATE ai_kw_rule_version SET config_json="
                f"'{{\"modified\":true}}'::jsonb WHERE id='{rule_version}'",
                contains="KW_PUBLISHED_RULE_IMMUTABLE",
            ),
            f"UPDATE ai_kw_rule_version SET status='retired' WHERE id='{rule_version}';",
            _rejected(
                f"UPDATE ai_kw_rule_version SET status='draft' WHERE id='{rule_version}'",
                contains="KW_PUBLISHED_RULE_IMMUTABLE",
            ),
            _rejected(
                f"DELETE FROM ai_kw_rule_version WHERE id='{rule_version}'",
                contains="KW_FINALIZED_RECORD_DELETE_FORBIDDEN",
            ),
            (
                "INSERT INTO raw_kw_asin_snapshot "
                "(asin,fetch_status,fetch_provider,id,source_account_ref) "
                f"VALUES ('B012345678','succeeded','qa','{asin_snapshot}','account-a');"
            ),
            _rejected(
                f"UPDATE raw_kw_asin_snapshot SET title='forbidden' WHERE id='{asin_snapshot}'",
                contains="KW_IMMUTABLE_SOURCE",
            ),
            _rejected(
                "INSERT INTO raw_kw_asin_snapshot "
                "(asin,fetch_status,fetch_provider,id,source_account_ref) "
                f"VALUES ('BAD','succeeded','qa','{uuid4()}','account-a')",
                state="23514",  # check_violation
            ),
            _rejected(
                "INSERT INTO raw_kw_asin_image "
                "(asin_snapshot_id,image_index,image_url,id,source_account_ref) "
                f"VALUES ('{asin_snapshot}',0,'https://example.invalid/image.jpg','{uuid4()}','account-b')",
                state="23503",  # cross-account foreign_key_violation
            ),
            (
                "INSERT INTO raw_kw_upload_file "
                "(product_id,original_filename,object_key,sha256,file_size_bytes,"
                "uploaded_by,id,source_account_ref) "
                f"VALUES ('{product}','qa.csv','qa/source',repeat('a',64),1,"
                f"'qa','{upload}','account-a');"
            ),
            f"UPDATE raw_kw_upload_file SET status='parsed' WHERE id='{upload}';",
            _rejected(
                f"UPDATE raw_kw_upload_file SET sha256=repeat('b',64) WHERE id='{upload}'",
                contains="KW_UPLOAD_ORIGINAL_CANNOT_CHANGE",
            ),
            "SELECT 'KW_GUARDS_OK|1';",
            "ROLLBACK;",
            "SELECT 'KW_ROLLBACK|' || CASE WHEN "
            "to_regclass('public.ai_kw_rule_set') IS NULL THEN '1' ELSE '0' END;",
        ]
    )
    return "\n".join(statements) + "\n"


def _docker(
    *args: str, input_text: str | None = None, timeout: int = 180
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _require_local_docker() -> None:
    if shutil.which("docker") is None:
        pytest.fail("Docker CLI unavailable; PostgreSQL DDL has NOT been tested", pytrace=False)
    host_override = os.environ.get("DOCKER_HOST", "")
    if host_override and not host_override.startswith("unix://"):
        pytest.fail("Refusing non-local DOCKER_HOST; PostgreSQL DDL not tested", pytrace=False)
    context = _docker("context", "inspect", "--format", "{{json .Endpoints}}", timeout=15)
    if context.returncode != 0:
        pytest.fail(f"Cannot verify local Docker context: {context.stderr[:300]}", pytrace=False)
    try:
        endpoints = json.loads(context.stdout.strip())
        socket = endpoints["docker"]["Host"]
    except (ValueError, KeyError, TypeError) as exc:
        pytest.fail(f"Cannot parse Docker endpoint: {type(exc).__name__}", pytrace=False)
    if not isinstance(socket, str) or not socket.startswith("unix://"):
        pytest.fail("Refusing remote Docker context; PostgreSQL DDL not tested", pytrace=False)
    info = _docker("info", "--format", "{{.ServerVersion}}", timeout=20)
    if info.returncode != 0:
        pytest.fail("Local Docker daemon unavailable; PostgreSQL DDL not tested", pytrace=False)


@pytest.mark.skipif(
    os.environ.get("RUN_KW_POSTGRES_SANDBOX") != "1",
    reason="Explicit opt-in required: RUN_KW_POSTGRES_SANDBOX=1",
)
def test_0055_postgres_sql_and_guards_rollback() -> None:
    """Test current local 0055 DDL in a disposable PostgreSQL without networking."""
    data = _read_literal_ddl()
    _require_local_docker()
    name = "szzsbj-kw-qa-" + secrets.token_hex(6)
    # Password is for the sandbox container only and is never logged.
    password = secrets.token_urlsafe(24)
    started = False
    try:
        launch = _docker(
            "run",
            "--rm",
            "--detach",
            "--network=none",
            "--name",
            name,
            "--memory=512m",
            "--pids-limit=128",
            "-e",
            f"POSTGRES_PASSWORD={password}",
            "postgres:16-alpine",
            timeout=180,
        )
        if launch.returncode != 0:
            pytest.fail(f"Cannot start isolated PostgreSQL: {launch.stderr[:500]}", pytrace=False)
        started = True
        for _ in range(60):
            ready = _docker("exec", name, "pg_isready", "-U", "postgres", timeout=10)
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            pytest.fail("Isolated PostgreSQL did not become ready", pytrace=False)

        result = _docker(
            "exec",
            "-i",
            name,
            "psql",
            "-X",
            "-q",
            "-A",
            "-t",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            "postgres",
            input_text=_build_smoke_sql(data),
            timeout=120,
        )
        if result.returncode != 0:
            pytest.fail(
                "PostgreSQL DDL/guard validation FAILED; container will be removed. "
                f"psql stderr (last 2500 chars): {result.stderr[-2500:]}",
                pytrace=False,
            )
        lines = set(result.stdout.splitlines())
        assert "KW_COUNTS|21|13|113|3|17" in lines, (
            f"Catalog count mismatch: {result.stdout[-1200:]}"
        )
        assert "KW_GUARDS_OK|1" in lines, f"Guard checks not completed: {result.stdout[-1200:]}"
        assert "KW_ROLLBACK|1" in lines, f"Transaction rollback failed: {result.stdout[-1200:]}"
        print(
            "PASS: PostgreSQL 16: 21 tables, 13 explicit indexes, "
            "113 constraints, 3 functions, 17 triggers"
        )
        print("PASS: guard checks, cross-account FK, and transactional rollback")
    finally:
        if started:
            _docker("rm", "-f", name, timeout=30)

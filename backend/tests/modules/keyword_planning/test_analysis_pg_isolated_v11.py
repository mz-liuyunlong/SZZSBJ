"""Opt-in, real SQLAlchemy 2 + PostgreSQL persistence acceptance for V1.1.

Security: fresh Docker-only disposable DB, random loopback port, no volumes,
never reads DATABASE_URL, never runs Alembic or connects to the production tunnel.
Requires a LOCAL unix-socket Docker context and RUN_KW_ANALYSIS_PG_SANDBOX=1.
"""

from __future__ import annotations

import ast
import json
import os
import re
import runpy
import secrets
import shutil
import subprocess
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.modules.keyword_planning.analysis_execution import (
    AnalysisBlocked,
    AnalysisCommand,
    ReviewedCandidate,
    _digest,
    calculate_input_sha256,
    execute_reviewed_analysis,
)
from app.modules.keyword_planning.models import (
    AiKwAnalysisRun,
    AiKwProductFactSnapshot,
    AiKwRuleSet,
    AiKwRuleVersion,
    AiKwRunKeyword,
    DimKwTerm,
    RawKwUploadFile,
    RawKwUploadRow,
    RawKwWalmartPageSnapshot,
)
from app.modules.keyword_planning.rule_gates import (
    ALGORITHM_VERSION,
    NORMALIZER_VERSION,
    REQUIRED_PRODUCT_FIELDS,
    ColdStartLimits,
    ProductConfirmation,
    ProductField,
)
from app.modules.keyword_planning.rule_governance import (
    RuleGovernanceBlocked,
    create_scoring_draft,
    create_scoring_ruleset,
    publish_scoring_rule,
    review_rule_decision,
    submit_rule_decision,
)
from app.modules.keyword_planning.runtime_rules import KeywordInput, PublishedPolicy, VerifiedLabel
from app.modules.products import models as product_models  # noqa: F401 - register FK targets


@pytest.mark.skipif(
    os.environ.get("RUN_KW_ANALYSIS_PG_SANDBOX") != "1",
    reason="Explicit opt-in required: RUN_KW_ANALYSIS_PG_SANDBOX=1",
)
def test_real_postgres_analysis_idempotency_and_rollback() -> None:
    if shutil.which("docker") is None:
        pytest.fail("Docker CLI required for isolated analysis test", pytrace=False)
    if os.environ.get("DOCKER_HOST", "").strip() and not os.environ["DOCKER_HOST"].startswith(
        "unix://"
    ):
        pytest.fail("Remote Docker daemon is not allowed", pytrace=False)

    def docker(*args: str, timeout: int = 30):
        return subprocess.run(
            ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
        )

    context = docker("context", "inspect", "--format", "{{json .Endpoints}}")
    try:
        host = json.loads(context.stdout)["docker"]["Host"] if context.returncode == 0 else ""
    except (KeyError, ValueError, TypeError):
        host = ""
    if not isinstance(host, str) or not host.startswith("unix://"):
        pytest.fail("Refusing unverified nonlocal Docker Context", pytrace=False)
    assert docker("info", "--format", "{{.ServerVersion}}").returncode == 0

    migration = (
        Path(__file__).resolve().parents[3]
        / "alembic/versions/20261023_0055_keyword_planning_core.py"
    )
    tree = ast.parse(migration.read_text(encoding="utf-8"))
    ddl: dict[str, tuple[str, ...]] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if getattr(target, "id", "") in {"TABLE_DDL", "INDEX_DDL", "GUARD_DDL"}:
                    ddl[target.id] = ast.literal_eval(node.value)
    assert len(ddl["TABLE_DDL"]) == 21 and len(ddl["GUARD_DDL"]) == 20
    name = "szzsbj-analysis-qa-" + secrets.token_hex(6)
    password = secrets.token_urlsafe(32)
    started = False
    engine = None
    try:
        launch = docker(
            "run",
            "--rm",
            "--detach",
            "--name",
            name,
            "--publish",
            "127.0.0.1::5432",
            "--memory=512m",
            "--pids-limit=128",
            "-e",
            f"POSTGRES_PASSWORD={password}",
            "postgres:16-alpine",
            timeout=180,
        )
        if launch.returncode:
            pytest.fail(f"Cannot start disposable PostgreSQL: {launch.stderr[:250]}", pytrace=False)
        started = True
        published_port = docker("port", name, "5432/tcp")
        port_line = published_port.stdout.strip()
        if published_port.returncode or not re.fullmatch(r"127\.0\.0\.1:\d{4,5}", port_line):
            pytest.fail("Container was not bound to a verified loopback port", pytrace=False)
        port = int(port_line.rsplit(":", 1)[1])
        if port in (5432, 15432):
            pytest.fail("Refusing production or pre-existing local tunnel port", pytrace=False)
        for _ in range(60):
            if docker("exec", name, "pg_isready", "-U", "postgres", timeout=5).returncode == 0:
                break
            time.sleep(0.5)
        else:
            pytest.fail("Disposable PostgreSQL did not become healthy", pytrace=False)

        engine = create_engine(
            f"postgresql+psycopg://postgres:{password}@127.0.0.1:{port}/postgres",
            hide_parameters=True,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 2},
        )
        # Wait for real host TCP connectivity, not just container pg_isready.
        for _ in range(60):
            try:
                with engine.connect() as probe:
                    probe.exec_driver_sql("SELECT 1")
                break
            except OperationalError:
                time.sleep(0.5)
        else:
            state = docker("inspect", "--format", "{{.State.Status}}", name)
            status = state.stdout.strip() if state.returncode == 0 else "unavailable"
            pytest.fail(
                f"Disposable PostgreSQL TCP not ready; container={status}",
                pytrace=False,
            )

        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE products (id UUID PRIMARY KEY)")
            connection.exec_driver_sql(
                "CREATE TABLE product_platform_listings (id UUID PRIMARY KEY)"
            )
            for section in ("TABLE_DDL", "INDEX_DDL", "GUARD_DDL"):
                for statement in ddl[section]:
                    connection.execute(text(statement))
            approval_migration = runpy.run_path(
                str(
                    Path(__file__).resolve().parents[3]
                    / "alembic/versions/20261024_0057_keyword_rule_decisions.py"
                )
            )
            upgrade = approval_migration["upgrade"]
            upgrade.__globals__["op"] = Operations(MigrationContext.configure(connection))
            upgrade()

        product_id = uuid4()
        page_id = uuid4()
        fact_id = uuid4()
        ruleset_id = uuid4()
        rule_id = uuid4()
        file_id = uuid4()
        row_id = uuid4()
        term_id = uuid4()
        account = "sandbox-account"
        item = "12345678"
        actor = "isolated-test"
        facts = {
            key: {
                "value": f"confirmed {key}",
                "source": "operator",
                "evidence_ref": f"operator-check:{key}",
            }
            for key in REQUIRED_PRODUCT_FIELDS
        }
        facts["risk_boundary"] = {"mode": "none", "acknowledged": True}
        config = {
            "limits": asdict(ColdStartLimits()),
            "confirmed_brands": {},
            "suspected_brands": {},
        }
        now = datetime.now(UTC)
        with Session(engine) as session, session.begin():
            session.connection().exec_driver_sql(
                "INSERT INTO products(id) VALUES (%s)",
                (product_id,),
            )
            session.add_all(
                [
                    RawKwWalmartPageSnapshot(
                        id=page_id,
                        source_account_ref=account,
                        product_id=product_id,
                        item_id=item,
                        verification_status="verified",
                        fetch_provider="fixture",
                        page_title="Pantry organizer",
                        features_json=[],
                        attributes_json={},
                        page_images_json=[],
                    ),
                    AiKwRuleSet(
                        id=ruleset_id,
                        rule_key="qa_scoring",
                        scope_key=account,
                        rule_type="scoring",
                        display_name="QA",
                        created_by=actor,
                        is_enabled=True,
                    ),
                    DimKwTerm(
                        id=term_id,
                        canonical_keyword="pantry organizer",
                        normalized_keyword="pantry organizer",
                        normalization_version=NORMALIZER_VERSION,
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    AiKwProductFactSnapshot(
                        id=fact_id,
                        source_account_ref=account,
                        product_id=product_id,
                        walmart_page_snapshot_id=page_id,
                        item_id=item,
                        item_verified=True,
                        status="confirmed",
                        facts_with_sources_json=facts,
                        facts_sha256=_digest(facts),
                        missing_required_json=[],
                        confirmed_by=actor,
                        confirmed_at=now,
                    ),
                    AiKwRuleVersion(
                        id=rule_id,
                        rule_set_id=ruleset_id,
                        version_number=1,
                        status="published",
                        config_json=config,
                        config_sha256=_digest(config),
                        schema_version="fixture",
                        engine_version=ALGORITHM_VERSION,
                        published_by=actor,
                        published_at=now,
                    ),
                    RawKwUploadFile(
                        id=file_id,
                        source_account_ref=account,
                        product_id=product_id,
                        original_filename="qa.xlsx",
                        object_key="test://qa.xlsx",
                        sha256="a" * 64,
                        file_size_bytes=500,
                        uploaded_by=actor,
                        parser_version="fixture",
                        status="parsed",
                    ),
                ]
            )
            session.flush()
            session.add(
                RawKwUploadRow(
                    id=row_id,
                    source_account_ref=account,
                    upload_id=file_id,
                    sheet_name="Keywords",
                    row_number=2,
                    source_cells=["pantry organizer"],
                    keyword_raw="pantry organizer",
                    keyword_normalized="pantry organizer",
                    parse_errors=[],
                )
            )

        product = ProductConfirmation(
            item_id=item,
            source_item_id=item,
            item_verified=True,
            facts={
                key: ProductField(
                    value=value["value"], source="operator", evidence_ref=value["evidence_ref"]
                )
                for key, value in facts.items()
                if key != "risk_boundary"
            },
            risk_boundary_acknowledged=True,
            risk_boundary_mode="none",
        )
        policy = PublishedPolicy(
            version_id=str(rule_id),
            status="published",
            source_account_ref=account,
            product_id=str(product_id),
            limits=ColdStartLimits(),
            confirmed_brands={},
            suspected_brands={},
        )
        cmd = AnalysisCommand(
            source_account_ref=account,
            product_id=product_id,
            product_fact_snapshot_id=fact_id,
            walmart_page_snapshot_id=page_id,
            rule_version_id=rule_id,
            item_id=item,
            request_key="safe-qa-request",
            input_sha256="0" * 64,
            actor_ref=actor,
            engine_version=ALGORITHM_VERSION,
            parser_version="fixture",
            normalizer_version=NORMALIZER_VERSION,
            source_total_rows=1,
            candidates=(
                ReviewedCandidate(
                    term_id,
                    KeywordInput(
                        keyword="pantry organizer",
                        source_rank=1,
                        source_row_refs=(str(row_id),),
                        labels=(VerifiedLabel("人工确认词", str(row_id)),),
                        match=None,
                        intent=None,
                        root=None,
                        data=None,
                    ),
                ),
            ),
        )
        cmd = replace(cmd, input_sha256=calculate_input_sha256(cmd, product, policy))
        with Session(engine) as session:
            first = execute_reviewed_analysis(session, command=cmd, policy=policy, product=product)
            assert first.created is True and first.status == "blocked"
            assert first.keyword_count == 1
        with Session(engine) as session:
            again = execute_reviewed_analysis(session, command=cmd, policy=policy, product=product)
            assert again.created is False and again.run_id == first.run_id
        # The actor is audit metadata, not an analysis input.
        with Session(engine) as session:
            changed_actor = replace(cmd, actor_ref="different-test-actor")
            changed_actor = replace(
                changed_actor,
                input_sha256=calculate_input_sha256(
                    changed_actor,
                    product,
                    policy,
                ),
            )
            assert changed_actor.input_sha256 == cmd.input_sha256
            replay = execute_reviewed_analysis(
                session, command=changed_actor, policy=policy, product=product
            )
            assert replay.created is False and replay.run_id == first.run_id

        # Changing actual analysis inputs must invalidate request-key reuse.
        with Session(engine) as session:
            conflicting = replace(cmd, source_total_rows=2)
            conflicting = replace(
                conflicting,
                input_sha256=calculate_input_sha256(
                    conflicting,
                    product,
                    policy,
                ),
            )
            assert conflicting.input_sha256 != cmd.input_sha256
            with pytest.raises(
                AnalysisBlocked, match="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_INPUT"
            ):
                execute_reviewed_analysis(
                    session, command=conflicting, policy=policy, product=product
                )
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(AiKwAnalysisRun)) == 1
            assert session.scalar(select(func.count()).select_from(AiKwRunKeyword)) == 1
        with Session(engine) as session:
            approval_set = create_scoring_ruleset(
                session,
                account="approval-synthetic",
                actor="maker",
                rule_key="synthetic_review",
                display_name="Synthetic Review",
            )
        with Session(engine) as session:
            draft = create_scoring_draft(
                session,
                account="approval-synthetic",
                rule_set_id=approval_set,
                actor="maker",
                limits=ColdStartLimits(),
                confirmed_brands={},
                suspected_brands={},
            )
        with Session(engine) as session:
            with pytest.raises(
                RuleGovernanceBlocked, match="INDEPENDENT_D01_D08_APPROVAL_REQUIRED"
            ):
                publish_scoring_rule(
                    session, account="approval-synthetic", version_id=draft.id, actor="publisher"
                )
        for index in range(1, 9):
            key = f"D{index:02d}"
            with Session(engine) as session:
                submit_rule_decision(
                    session,
                    account="approval-synthetic",
                    version_id=draft.id,
                    decision_key=key,
                    actor="maker",
                    proposal={"strategy": "null_review"}
                    if key == "D04"
                    else {"choice": "synthetic-only"},
                    evidence_ref="test:proposal",
                )
            with Session(engine) as session:
                review_rule_decision(
                    session,
                    account="approval-synthetic",
                    version_id=draft.id,
                    decision_key=key,
                    actor="reviewer-a" if index <= 4 else "reviewer-b",
                    approved=True,
                    evidence_ref="test:review",
                )
        with Session(engine) as session:
            published = publish_scoring_rule(
                session,
                account="approval-synthetic",
                version_id=draft.id,
                actor="publisher",
            )
            assert published.status == "published"
        with engine.connect() as connection:
            assert (
                connection.exec_driver_sql("SELECT count(*) FROM ai_kw_rule_decision").scalar_one()
                == 8
            )
            assert (
                connection.exec_driver_sql(
                    "SELECT count(*) FROM ai_kw_rule_decision_event"
                ).scalar_one()
                == 16
            )
        print("PASS: real PostgreSQL run write, immutable blocked result and idempotency")
    finally:
        if engine is not None:
            engine.dispose()
        if started:
            docker("rm", "-f", name, timeout=30)

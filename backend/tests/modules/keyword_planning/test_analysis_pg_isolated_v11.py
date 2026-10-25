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
import socket
import subprocess
import tempfile
import threading
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

from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.keyword_planning.analysis_entrypoint import (
    create_analysis_from_stored_sources,
    prepare_verified_analysis,
)
from app.modules.keyword_planning.analysis_execution import (
    AnalysisBlocked,
    AnalysisCommand,
    ReviewedCandidate,
    _digest,
    calculate_input_sha256,
    execute_reviewed_analysis,
)
from app.modules.keyword_planning.effective_rule import effective_scoring_rule
from app.modules.keyword_planning.models import (
    AiKwAnalysisRun,
    AiKwProductFactSnapshot,
    AiKwRuleSet,
    AiKwRuleVersion,
    AiKwRunAsin,
    AiKwRunFile,
    AiKwRunKeyword,
    BizKwSourceEvent,
    BizSkuAsinReference,
    BizSkuKeyword,
    DimKwTerm,
    RawKwAsinSnapshot,
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
    update_scoring_draft,
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
            product_models.Product.__table__.create(connection)
            connection.exec_driver_sql(
                "CREATE TABLE product_platform_listings (id UUID PRIMARY KEY)"
            )
            ListingManagementCurrentMart.__table__.create(connection)
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
            default_migration = runpy.run_path(
                str(
                    Path(__file__).resolve().parents[3]
                    / "alembic/versions/20261025_0058_keyword_internal_default.py"
                )
            )
            install_default = default_migration["upgrade"]
            install_default.__globals__["op"] = Operations(MigrationContext.configure(connection))
            install_default()
            install_default()  # Idempotent even when retried.

        with Session(engine) as session:
            baseline = effective_scoring_rule(session, "fresh-synthetic-account")
            assert baseline is not None
            assert baseline.version_number == 1
            assert baseline.config_json["purpose"] == "internal_analysis_and_manual_review_only"
            assert baseline.config_json["editor_config"]["bid"]["dailyBudget"] == 0
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(AiKwRuleSet)
                    .where(AiKwRuleSet.rule_key == "keyword_v11_internal_default")
                )
                == 1
            )

        product_id = uuid4()
        second_product_id = uuid4()
        other_product_id = uuid4()
        page_id = uuid4()
        fact_id = uuid4()
        ruleset_id = uuid4()
        rule_id = uuid4()
        file_id = uuid4()
        row_id = uuid4()
        term_id = uuid4()
        asin_snapshot_id = uuid4()
        extra_asin_snapshot_ids = (uuid4(), uuid4())
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
            "editor_config": default_migration["CONFIG"]["editor_config"],
        }
        now = datetime.now(UTC)
        with Session(engine) as session, session.begin():
            session.add_all(
                [
                    product_models.Product(id=row_id, sku=sku, product_name=sku)
                    for row_id, sku in (
                        (product_id, "SYNTHETIC-A"),
                        (second_product_id, "SYNTHETIC-B"),
                        (other_product_id, "OTHER-ACCOUNT"),
                    )
                ]
            )
            session.flush()
            session.add(
                ListingManagementCurrentMart(
                    source_account_ref=account,
                    store_id="synthetic-store",
                    item_id=item,
                    local_sku="SYNTHETIC-A",
                    calculated_at=now,
                )
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
                    RawKwAsinSnapshot(
                        id=asin_snapshot_id,
                        source_account_ref=account,
                        asin="B000000001",
                        fetch_status="succeeded",
                        fetch_provider="fixture",
                        title="Synthetic organizer comparison",
                    ),
                    *(
                        RawKwAsinSnapshot(
                            id=snapshot_id,
                            source_account_ref=account,
                            asin=asin,
                            fetch_status="succeeded",
                            fetch_provider="fixture",
                            title="Synthetic organizer comparison",
                        )
                        for asin, snapshot_id in zip(
                            ("B000000002", "B000000003"), extra_asin_snapshot_ids, strict=True
                        )
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
                    BizSkuAsinReference(
                        source_account_ref=account,
                        product_id=product_id,
                        asin="B000000001",
                        reference_role="competitor",
                        is_active=True,
                        latest_snapshot_id=asin_snapshot_id,
                        selected_by=actor,
                    ),
                    *(
                        BizSkuAsinReference(
                            source_account_ref=account,
                            product_id=product_id,
                            asin=asin,
                            reference_role="competitor",
                            is_active=True,
                            latest_snapshot_id=snapshot_id,
                            selected_by=actor,
                        )
                        for asin, snapshot_id in zip(
                            ("B000000002", "B000000003"), extra_asin_snapshot_ids, strict=True
                        )
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    BizSkuKeyword(
                        source_account_ref=account,
                        product_id=product_id,
                        term_id=term_id,
                        status="review",
                    ),
                    BizSkuKeyword(
                        source_account_ref=account,
                        product_id=second_product_id,
                        term_id=term_id,
                        status="active",
                    ),
                    BizSkuKeyword(
                        source_account_ref="other-account",
                        product_id=other_product_id,
                        term_id=term_id,
                        status="active",
                    ),
                    BizKwSourceEvent(
                        source_account_ref=account,
                        product_id=product_id,
                        term_id=term_id,
                        source_kind="excel",
                        source_event_key="synthetic-file-1",
                        evidence_json={},
                        discovered_at=now,
                    ),
                    BizKwSourceEvent(
                        source_account_ref=account,
                        product_id=second_product_id,
                        term_id=term_id,
                        source_kind="operator_manual",
                        source_event_key="synthetic-manual-1",
                        evidence_json={},
                        discovered_at=now,
                    ),
                ]
            )
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

        with Session(engine) as session:
            assert effective_scoring_rule(session, account).id == rule_id
            assert effective_scoring_rule(session, "fresh-synthetic-account").id != rule_id
            prepared, _, _ = prepare_verified_analysis(
                session,
                account=account,
                product_id=product_id,
                item_id=item,
                fact_id=fact_id,
                rule_version_id=rule_id,
                upload_id=file_id,
                request_key="selected-asin-provenance",
                actor=actor,
                selected_asins=("B000000001",),
            )
            assert prepared.asin_snapshot_ids == (asin_snapshot_id,)
            session.rollback()

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
            asin_snapshot_ids=(asin_snapshot_id,),
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
            assert session.scalar(select(func.count()).select_from(AiKwRunFile)) == 1
            assert session.scalar(select(func.count()).select_from(AiKwRunAsin)) == 1
        # Exercise the real FastAPI read/export contract against the same
        # disposable PostgreSQL rows used by the write transaction above.
        from fastapi.testclient import TestClient

        from app.core.auth import Principal, get_optional_principal
        from app.db.session import get_db_session
        from app.main import create_app
        from app.modules.integration_sync.dependencies import require_source_account_scope

        app = create_app()

        def sandbox_session():
            with Session(engine) as db_session:
                yield db_session

        app.dependency_overrides[get_db_session] = sandbox_session
        app.dependency_overrides[require_source_account_scope] = lambda: frozenset({account})
        app.dependency_overrides[get_optional_principal] = lambda: Principal(
            user_id=actor, permissions=frozenset({"*"})
        )
        try:
            client = TestClient(app)
            base = "/api/v1/keyword-planning"
            params = {"source_account_ref": account}
            runs = client.get(f"{base}/products/{product_id}/runs", params=params)
            assert runs.status_code == 200
            assert runs.json()["data"]["total"] == 1
            assert runs.json()["data"]["items"][0]["run_id"] == str(first.run_id)
            keywords = client.get(
                f"{base}/runs/{first.run_id}/keywords",
                params={**params, "limit": 1, "offset": 0},
            )
            assert keywords.status_code == 200
            assert keywords.json()["data"]["total"] == 1
            assert keywords.json()["data"]["items"][0]["keyword"] == "pantry organizer"
            assert keywords.json()["data"]["items"][0]["score"] is None
            global_read = client.get(f"{base}/library", params=params)
            assert global_read.status_code == 200
            assert global_read.json()["data"]["total"] == 1
            assert global_read.json()["data"]["items"][0]["sku_count"] == 2
            assert {a["sku"] for a in global_read.json()["data"]["items"][0]["associations"]} == {
                "SYNTHETIC-A",
                "SYNTHETIC-B",
            }
            manual_read = client.get(
                f"{base}/library", params={**params, "source": "operator_manual"}
            )
            assert manual_read.status_code == 200
            assert manual_read.json()["data"]["total"] == 1
            assert (
                client.get(
                    f"{base}/library", params={"source_account_ref": "other-account"}
                ).status_code
                == 403
            )
            workbook = client.get(f"{base}/runs/{first.run_id}/internal-workbook", params=params)
            assert workbook.status_code == 200
            assert workbook.headers["content-type"].startswith(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            from io import BytesIO
            from xml.etree import ElementTree as ET
            from zipfile import ZipFile

            from app.modules.keyword_planning.internal_export import SHEET_NAMES

            with ZipFile(BytesIO(workbook.content)) as archive:
                document = ET.fromstring(archive.read("xl/workbook.xml"))
            sheet_tag = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet"
            assert [node.get("name") for node in document.iter(sheet_tag)] == list(SHEET_NAMES)
            denied = client.get(
                f"{base}/runs/{first.run_id}/keywords",
                params={"source_account_ref": "other-account"},
            )
            assert denied.status_code == 403
            previous_write_flag = os.environ.get("KEYWORD_V11_WRITE_ENABLED")
            os.environ["KEYWORD_V11_WRITE_ENABLED"] = "1"
            try:
                created_set = client.post(
                    f"{base}/rulesets",
                    json={
                        "source_account_ref": account,
                        "rule_key": "keyword_v11_ui",
                        "display_name": "Synthetic UI",
                    },
                )
                assert created_set.status_code == 200
                ui_set_id = created_set.json()["data"]["rule_set_id"]
                created_draft = client.post(
                    f"{base}/rulesets/{ui_set_id}/drafts",
                    json={
                        "source_account_ref": account,
                        "editor_config": {"riskWords": "synthetic"},
                    },
                )
                assert created_draft.status_code == 200
                ui_version_id = created_draft.json()["data"]["version_id"]
                saved_draft = client.patch(
                    f"{base}/rules/{ui_version_id}/draft",
                    json={
                        "source_account_ref": account,
                        "editor_config": {"riskWords": "synthetic review"},
                    },
                )
                assert saved_draft.status_code == 200
                reopened = client.get(f"{base}/rulesets/{ui_set_id}/versions", params=params)
                assert reopened.status_code == 200
                assert (
                    reopened.json()["data"]["items"][0]["config"]["editor_config"]["riskWords"]
                    == "synthetic review"
                )
                app.dependency_overrides[get_optional_principal] = lambda: Principal(
                    user_id="ordinary-operator",
                    permissions=frozenset({"products:read", "products:write"}),
                )
                visible = client.get(f"{base}/rulesets", params=params)
                assert visible.status_code == 200
                assert any(
                    row["rule_key"] == "keyword_v11_internal_default"
                    for row in visible.json()["data"]["items"]
                )
                assert (
                    client.post(
                        f"{base}/rulesets",
                        json={
                            "source_account_ref": account,
                            "rule_key": "unauthorized_rule",
                            "display_name": "Unauthorized",
                        },
                    ).status_code
                    == 403
                )
                assert (
                    client.post(
                        f"{base}/rules/{ui_version_id}/publish",
                        json={"source_account_ref": account},
                    ).status_code
                    == 403
                )
            finally:
                app.dependency_overrides[get_optional_principal] = lambda: Principal(
                    user_id=actor, permissions=frozenset({"*"})
                )
                if previous_write_flag is None:
                    os.environ.pop("KEYWORD_V11_WRITE_ENABLED", None)
                else:
                    os.environ["KEYWORD_V11_WRITE_ENABLED"] = previous_write_flag
            if os.environ.get("RUN_KW_BROWSER_SANDBOX") == "1":
                import uvicorn

                frontend = Path(__file__).resolve().parents[4] / "frontend"
                playwright = frontend / "node_modules/.bin/playwright"
                assert playwright.is_file(), "Install locked frontend dependencies first"
                with Session(engine) as session:
                    listing_id = session.scalar(
                        select(ListingManagementCurrentMart.id).where(
                            ListingManagementCurrentMart.source_account_ref == account,
                            ListingManagementCurrentMart.item_id == item,
                        )
                    )
                assert listing_id is not None
                listener = socket.socket()
                listener.bind(("127.0.0.1", 0))
                listener.listen(128)
                api_port = listener.getsockname()[1]
                server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
                thread = threading.Thread(
                    target=server.run, kwargs={"sockets": [listener]}, daemon=True
                )
                prior_write_flag = os.environ.get("KEYWORD_V11_WRITE_ENABLED")
                prior_private_root = os.environ.get("SZZSBJ_KEYWORD_PRIVATE_ROOT")
                private_root = Path(tempfile.mkdtemp(prefix="szzsbj-keyword-qa-"))
                private_root.chmod(0o700)
                os.environ["KEYWORD_V11_WRITE_ENABLED"] = "1"
                os.environ["SZZSBJ_KEYWORD_PRIVATE_ROOT"] = str(private_root)
                thread.start()
                try:
                    for _ in range(100):
                        if server.started:
                            break
                        time.sleep(0.05)
                    assert server.started, "Disposable FastAPI server did not start"
                    browser = subprocess.run(
                        [
                            str(playwright),
                            "test",
                            "e2e/keyword-live-postgres.spec.ts",
                            "--workers=1",
                        ],
                        cwd=frontend,
                        env={
                            **os.environ,
                            "KW_LIVE_API_BASE": f"http://127.0.0.1:{api_port}",
                            "KW_LIVE_PRODUCT_ID": str(product_id),
                            "KW_LIVE_LISTING_ID": str(listing_id),
                        },
                        capture_output=True,
                        text=True,
                        timeout=150,
                        check=False,
                    )
                    assert browser.returncode == 0, (browser.stdout + browser.stderr)[-6000:]
                finally:
                    server.should_exit = True
                    thread.join(timeout=10)
                    listener.close()
                    if prior_write_flag is None:
                        os.environ.pop("KEYWORD_V11_WRITE_ENABLED", None)
                    else:
                        os.environ["KEYWORD_V11_WRITE_ENABLED"] = prior_write_flag
                    if prior_private_root is None:
                        os.environ.pop("SZZSBJ_KEYWORD_PRIVATE_ROOT", None)
                    else:
                        os.environ["SZZSBJ_KEYWORD_PRIVATE_ROOT"] = prior_private_root
                    shutil.rmtree(private_root)
        finally:
            app.dependency_overrides.clear()
        with Session(engine) as session, session.begin():
            old_runs = {
                row.id: row.rule_version_id
                for row in session.scalars(
                    select(AiKwAnalysisRun).where(AiKwAnalysisRun.source_account_ref == account)
                )
            }
            session.get(AiKwRuleSet, ruleset_id).is_enabled = False
        with Session(engine) as session:
            baseline = effective_scoring_rule(session, account)
            assert baseline is not None and baseline.id != rule_id
            baseline_id = baseline.id
            session.rollback()
            receipt = create_analysis_from_stored_sources(
                session,
                account=account,
                product_id=product_id,
                item_id=item,
                fact_id=fact_id,
                rule_version_id=baseline_id,
                upload_id=file_id,
                request_key="system-default-internal-analysis",
                actor="ordinary-operator",
                selected_asins=("B000000001", "B000000002", "B000000003"),
            )
            assert receipt.created
        with Session(engine) as session:
            new_run = session.get(AiKwAnalysisRun, receipt.run_id)
            assert new_run.rule_version_id == baseline_id
            assert {
                row.id: row.rule_version_id
                for row in session.scalars(
                    select(AiKwAnalysisRun).where(AiKwAnalysisRun.id.in_(old_runs))
                )
            } == old_runs
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
            saved = update_scoring_draft(
                session,
                account="approval-synthetic",
                version_id=draft.id,
                actor="maker",
                limits=ColdStartLimits(max_p0=4),
                confirmed_brands={},
                suspected_brands={},
                editor_config={"riskWords": "synthetic"},
            )
            assert saved.status == "draft"
        with Session(engine) as session:
            persisted = session.get(AiKwRuleVersion, draft.id)
            assert persisted is not None
            assert persisted.config_json["editor_config"]["riskWords"] == "synthetic"
            assert persisted.config_json["limits"]["max_p0"] == 4
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
        with Session(engine) as session:
            assert effective_scoring_rule(session, "approval-synthetic").id == draft.id
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

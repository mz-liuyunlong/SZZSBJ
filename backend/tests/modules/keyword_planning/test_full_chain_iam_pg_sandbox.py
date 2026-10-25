"""Opt-in V1.1 acceptance against a disposable, fully migrated local PostgreSQL.

No dependency overrides, external API calls, production URL, or persistent volumes.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import dispose_engine
from app.main import create_app
from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.iam.rbac_repository import RbacRepository
from app.modules.iam.repository import IamRepository
from app.modules.iam.security import hash_password
from app.modules.integration_sync.models import IntegrationInterface, IntegrationSyncConfig
from app.modules.products.models import Product

BACKEND = Path(__file__).resolve().parents[3]
BASE = "/api/v1/keyword-planning"
READ_PERMISSION = "page:ai-center:keyword-launch:view"
WRITE_PERMISSION = "action:ai-center:keyword-launch:manage"


def _docker(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
    )


@pytest.mark.skipif(
    os.environ.get("RUN_KW_FULL_CHAIN_SANDBOX") != "1",
    reason="Explicit opt-in required: RUN_KW_FULL_CHAIN_SANDBOX=1",
)
def test_full_migrations_and_real_iam_keyword_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    if shutil.which("docker") is None:
        pytest.fail("Local Docker CLI required", pytrace=False)
    if os.environ.get("DOCKER_HOST", "").strip() and not os.environ["DOCKER_HOST"].startswith(
        "unix://"
    ):
        pytest.fail("Remote Docker daemon is not allowed", pytrace=False)
    context = _docker("context", "inspect", "--format", "{{json .Endpoints}}")
    try:
        host = json.loads(context.stdout)["docker"]["Host"] if context.returncode == 0 else ""
    except (KeyError, TypeError, ValueError):
        host = ""
    if not isinstance(host, str) or not host.startswith("unix://"):
        pytest.fail("Refusing unverified nonlocal Docker context", pytrace=False)

    name = "szzsbj-kw-fullchain-" + secrets.token_hex(6)
    password = secrets.token_urlsafe(32)
    started = False
    engine = None
    try:
        launch = _docker(
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
            pytest.fail("Cannot start disposable PostgreSQL", pytrace=False)
        started = True
        published = _docker("port", name, "5432/tcp")
        address = published.stdout.strip()
        if published.returncode or not re.fullmatch(r"127\.0\.0\.1:\d{4,5}", address):
            pytest.fail("PostgreSQL was not bound to verified loopback", pytrace=False)
        port = int(address.rsplit(":", 1)[1])
        if port in (5432, 15432):
            pytest.fail("Refusing application or tunnel port", pytrace=False)
        url = URL.create(
            "postgresql+psycopg",
            username="postgres",
            password=password,
            host="127.0.0.1",
            port=port,
            database="postgres",
        )
        engine = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 2})
        for _ in range(60):
            try:
                with engine.connect() as connection:
                    identity = connection.execute(
                        text("select current_database(), inet_server_addr()::text")
                    ).one()
                assert identity[0] == "postgres" and identity[1]
                break
            except OperationalError:
                time.sleep(0.5)
        else:
            pytest.fail("Disposable PostgreSQL did not become ready", pytrace=False)

        rendered_url = url.render_as_string(hide_password=False)
        migration_env = {
            key: os.environ[key] for key in ("PATH", "HOME", "LANG", "TMPDIR") if key in os.environ
        }
        migration_env.update(APP_ENV="test", TEST_DATABASE_URL=rendered_url)
        for target in (
            "20261022_0054_merge_walmart_identity_and_domestic_packing",
            "20261025_0058_keyword_internal_default",
        ):
            migrated = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", target],
                cwd=BACKEND,
                env=migration_env,
                capture_output=True,
                text=True,
                timeout=240,
                check=False,
            )
            assert migrated.returncode == 0, f"Full Alembic upgrade failed at {target}"
            with engine.connect() as connection:
                assert connection.scalar(text("select version_num from alembic_version")) == target
                if target.endswith("0054_merge_walmart_identity_and_domestic_packing"):
                    assert connection.scalar(text("select to_regclass('ai_kw_rule_set')")) is None

        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.setenv("TEST_DATABASE_URL", rendered_url)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        get_settings.cache_clear()
        dispose_engine()

        account = "synthetic-account-one"
        other_account = "synthetic-account-two"
        product_id = uuid4()
        missing_listing_id = uuid4()
        with Session(engine) as session:
            session.add_all(
                [
                    IntegrationInterface(
                        provider="synthetic",
                        interface_key="keyword_sandbox",
                        display_name="Synthetic source",
                        method="POST",
                        endpoint_path="/synthetic/keyword",
                        request_kind="offset_page",
                        handler_key="synthetic",
                        contract_version="v1",
                    ),
                    Product(id=product_id, sku="SYNTHETIC-SKU", product_name="Synthetic product"),
                    Product(
                        id=missing_listing_id,
                        sku="SYNTHETIC-NO-LISTING",
                        product_name="Synthetic missing listing",
                    ),
                    ListingManagementCurrentMart(
                        source_account_ref=account,
                        store_id="synthetic-store",
                        item_id="10000000001",
                        local_sku="SYNTHETIC-SKU",
                        calculated_at=datetime.now(UTC),
                    ),
                ]
            )
            session.flush()
            interface_id = session.scalar(
                select(IntegrationInterface.id).where(
                    IntegrationInterface.interface_key == "keyword_sandbox"
                )
            )
            assert interface_id is not None
            session.add_all(
                [
                    IntegrationSyncConfig(interface_id=interface_id, source_account_ref=account),
                    IntegrationSyncConfig(
                        interface_id=interface_id, source_account_ref=other_account
                    ),
                ]
            )
            iam = IamRepository(session)
            iam.create_role(
                role_key="synthetic-keyword-operator",
                name="Synthetic keyword operator",
                description=None,
            )
            user_id = iam.create_user(
                username="synthetic-keyword-user",
                password_hash=hash_password("synthetic-password"),
                display_name="Synthetic operator",
                phone=None,
                email=None,
                feishu_name=None,
                feishu_open_id=None,
                feishu_user_id=None,
                feishu_union_id=None,
                feishu_employee_id=None,
                feishu_department_ids=None,
            )
            iam.set_user_roles(user_id=user_id, role_keys=["synthetic-keyword-operator"])
            rbac = RbacRepository(session)
            assert {READ_PERMISSION, WRITE_PERMISSION} <= rbac.existing_permission_keys(
                [READ_PERMISSION, WRITE_PERMISSION]
            )
            assert rbac.set_role_permissions(
                role_key="synthetic-keyword-operator",
                permission_keys=[READ_PERMISSION],
                expected_version=1,
            )
            rbac.set_user_data_scopes(user_id=user_id, scopes=[("source_account", account)])
            session.commit()

        app = create_app()
        with TestClient(app) as client:
            login = client.post(
                "/api/auth/login",
                json={"username": "synthetic-keyword-user", "password": "synthetic-password"},
            )
            assert login.status_code == 200
            token = login.json()["data"]["access_token"]
            client.headers["Authorization"] = f"Bearer {token}"
            me = client.get("/api/auth/me")
            assert me.status_code == 200
            assert READ_PERMISSION in me.json()["data"]["permissions"]
            assert WRITE_PERMISSION not in me.json()["data"]["permissions"]

            rules = client.get(f"{BASE}/rulesets", params={"source_account_ref": account})
            assert rules.status_code == 200
            assert any(
                row["rule_key"] == "keyword_v11_internal_default"
                for row in rules.json()["data"]["items"]
            )
            source = client.get(
                f"{BASE}/products/{product_id}/source-state",
                params={"source_account_ref": account},
            )
            assert source.status_code == 200
            assert source.json()["data"]["source_status"] == "ready_for_import"
            runs = client.get(
                f"{BASE}/products/{product_id}/runs",
                params={"source_account_ref": account},
            )
            assert runs.status_code == 200
            assert runs.json()["data"]["items"] == []
            library = client.get(f"{BASE}/library", params={"source_account_ref": account})
            assert library.status_code == 200
            assert library.json()["data"]["total"] == 0
            assert (
                client.get(
                    f"{BASE}/rulesets", params={"source_account_ref": other_account}
                ).status_code
                == 403
            )
            assert (
                client.get(
                    f"{BASE}/products/{missing_listing_id}/source-state",
                    params={"source_account_ref": account},
                ).status_code
                == 404
            )
            assert (
                client.post(f"{BASE}/analyses", json={"source_account_ref": account}).status_code
                == 403
            )
    finally:
        dispose_engine()
        get_settings.cache_clear()
        if engine is not None:
            engine.dispose()
        if started:
            _docker("stop", name, timeout=60)

"""HTTP authorization and fail-closed tests. No database or external network."""

from __future__ import annotations

from types import SimpleNamespace as NS
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.integration_sync.dependencies import require_source_account_scope

BASE = "/api/v1/keyword-planning"
RUN = UUID("00000000-0000-0000-0000-000000000011")
PRODUCT = UUID("00000000-0000-0000-0000-000000000012")
FACT = UUID("00000000-0000-0000-0000-000000000013")
RULE = UUID("00000000-0000-0000-0000-000000000014")
UPLOAD = UUID("00000000-0000-0000-0000-000000000015")


class Spy:
    def __init__(self):
        self.statements = []

    def scalar(self, stmt):
        c = stmt.compile(dialect=postgresql.dialect())
        self.statements.append((str(c), c.params))
        return NS(id=RUN, status="blocked", source_account_ref="tenant")

    def execute(self, stmt):
        c = stmt.compile(dialect=postgresql.dialect())
        self.statements.append((str(c), c.params))
        return []


@pytest.fixture
def protected_app(monkeypatch):
    monkeypatch.delenv("KEYWORD_V11_WRITE_ENABLED", raising=False)
    monkeypatch.delenv("SZZSBJ_KEYWORD_PRIVATE_ROOT", raising=False)
    app = create_app()
    spy = Spy()
    app.dependency_overrides[get_db_session] = lambda: spy
    app.dependency_overrides[require_source_account_scope] = lambda: frozenset({"tenant"})
    yield app, spy
    app.dependency_overrides.clear()


def _login(app, user="owner", permissions=("products:read", "products:write")):
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id=user, permissions=frozenset(permissions)
    )


def payload(account="tenant"):
    return dict(
        source_account_ref=account,
        product_id=str(PRODUCT),
        item_id="123",
        product_fact_snapshot_id=str(FACT),
        rule_version_id=str(RULE),
        upload_file_id=str(UPLOAD),
        request_key="unique-request",
    )


def test_new_routes_registered(protected_app):
    app, _ = protected_app
    assert app.url_path_for("create_analysis") == BASE + "/analyses"
    assert app.url_path_for("upload_keyword_xlsx") == BASE + "/imports/xlsx"
    assert (
        app.url_path_for("download_internal_workbook", run_id=RUN)
        == BASE + f"/runs/{RUN}/internal-workbook"
    )


@pytest.mark.parametrize("endpoint", ["/analyses", "/imports/xlsx"])
def test_unauthenticated_write_denied_before_storage(protected_app, endpoint):
    app, spy = protected_app
    app.dependency_overrides[get_optional_principal] = lambda: None
    params = {
        "source_account_ref": "tenant",
        "product_id": str(PRODUCT),
        "product_fact_snapshot_id": str(FACT),
        "filename": "input.xlsx",
    }
    response = (
        TestClient(app).post(BASE + endpoint, json=payload())
        if endpoint == "/analyses"
        else TestClient(app).post(BASE + endpoint, params=params, content=b"junk")
    )
    assert response.status_code == 401
    assert spy.statements == []


@pytest.mark.parametrize("endpoint", ["/analyses", "/imports/xlsx"])
def test_writes_default_disabled(protected_app, endpoint):
    app, spy = protected_app
    _login(app)
    params = {
        "source_account_ref": "tenant",
        "product_id": str(PRODUCT),
        "product_fact_snapshot_id": str(FACT),
        "filename": "input.xlsx",
    }
    response = (
        TestClient(app).post(BASE + endpoint, json=payload())
        if endpoint == "/analyses"
        else TestClient(app).post(BASE + endpoint, params=params, content=b"junk")
    )
    assert response.status_code == 403
    assert spy.statements == []


def test_cross_tenant_run_blocked(protected_app):
    app, spy = protected_app
    _login(app)
    assert TestClient(app).post(BASE + "/analyses", json=payload("other")).status_code == 403
    assert spy.statements == []


def test_preview_internal_export_denied(protected_app):
    app, spy = protected_app
    _login(app, user=PREVIEW_PRINCIPAL_ID)
    response = TestClient(app).get(
        BASE + f"/runs/{RUN}/internal-workbook", params={"source_account_ref": "tenant"}
    )
    assert response.status_code == 403
    assert spy.statements == []


def test_cross_tenant_internal_export_denied(protected_app):
    app, spy = protected_app
    _login(app)
    response = TestClient(app).get(
        BASE + f"/runs/{RUN}/internal-workbook", params={"source_account_ref": "other"}
    )
    assert response.status_code == 403
    assert spy.statements == []


def test_internal_export_never_claims_bulk_template(protected_app):
    app, spy = protected_app
    _login(app)
    response = TestClient(app).get(
        BASE + f"/runs/{RUN}/internal-workbook", params={"source_account_ref": "tenant"}
    )
    assert response.status_code == 200
    assert response.content[:2] == b"PK"
    assert "application/vnd.openxmlformats" in response.headers["content-type"]
    assert "no-store" == response.headers["cache-control"]
    assert response.headers["content-disposition"].startswith("attachment;")
    assert len(spy.statements) == 2
    assert all("source_account_ref" in sql for sql, _ in spy.statements)

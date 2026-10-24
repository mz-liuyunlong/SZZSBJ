"""Real FastAPI HTTP boundary tests using an in-memory SQL query spy.

No database engine, migration, external API, credentials or network I/O.
The dependencies exercise the production authentication, permission, scoped
service and response-envelope chain; only principal/account universe/DB are faked.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.integration_sync.dependencies import require_source_account_scope

BASE = "/api/v1/keyword-planning"
RUN = UUID("00000000-0000-0000-0000-000000000001")
PRODUCT = UUID("00000000-0000-0000-0000-000000000002")
RULE = UUID("00000000-0000-0000-0000-000000000003")
TERM = UUID("00000000-0000-0000-0000-000000000004")
NOW = datetime(2026, 10, 23, tzinfo=UTC)


def _run():
    return SimpleNamespace(
        id=RUN,
        product_id=PRODUCT,
        rule_version_id=RULE,
        source_account_ref="tenant-one",
        item_id="123456",
        status="succeeded",
        created_at=NOW,
        finished_at=NOW,
    )


def _keyword():
    return SimpleNamespace(
        term_id=TERM,
        keyword_primary_type="core_product",
        page_coverage="title_exact",
        core_root="drawer organizer",
        score=88,
        base_grade="P0",
        allocation_grade="P0",
        exact_selected=True,
        broad_selected=False,
        broad_role=None,
        suggested_optimization_bid=Decimal("0.420000"),
        decision_status="ready",
        risk_reasons_json=[],
        exact_reason=None,
        broad_reason="no evidence",
        quality_note="verified",
        rank_index=1,
    )


class SqlSpy:
    """SQLAlchemy query compiler spy. Any real database access would fail here."""

    def __init__(self, *, exists: bool = True):
        self.exists = exists
        self.queries: list[tuple[str, dict[str, object]]] = []

    def _observe(self, statement):
        compiled = statement.compile(dialect=postgresql.dialect())
        self.queries.append((str(compiled), dict(compiled.params)))
        return str(compiled)

    def scalar(self, statement):
        sql = self._observe(statement)
        if "count(" in sql.lower():
            return 1
        return _run() if self.exists else None

    def scalars(self, statement):
        self._observe(statement)
        return [_run()] if self.exists else []

    def execute(self, statement):
        self._observe(statement)
        return [(_keyword(), "drawer organizer")] if self.exists else []


@pytest.fixture
def test_app():
    app = create_app()
    spy = SqlSpy()
    app.dependency_overrides[get_db_session] = lambda: spy
    app.dependency_overrides[require_source_account_scope] = lambda: frozenset({"tenant-one"})
    yield app, spy
    app.dependency_overrides.clear()


def _as(app, user="101", permissions=frozenset({"products:read"})):
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id=user, permissions=permissions
    )


def _assert_scoped_sql(spy):
    assert spy.queries, "Expected SQL SELECTs"
    for sql, parameters in spy.queries:
        assert "source_account_ref" in sql, sql
        assert "tenant-one" in parameters.values(), parameters
        assert not any(verb in sql.upper() for verb in ("INSERT INTO", "UPDATE ", "DELETE FROM"))


def test_app_exposes_three_readonly_routes(test_app):
    app, _ = test_app
    cases = {
        "list_product_runs": {"product_id": PRODUCT},
        "get_analysis_run": {"run_id": RUN},
        "list_analysis_keywords": {"run_id": RUN},
    }
    for endpoint, params in cases.items():
        assert str(app.url_path_for(endpoint, **params)).startswith(BASE + "/")


def test_missing_auth_is_401_without_queries(test_app):
    app, spy = test_app
    app.dependency_overrides[get_optional_principal] = lambda: None
    response = TestClient(app).get(
        f"{BASE}/runs/{RUN}",
        params={"source_account_ref": "tenant-one"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert spy.queries == []


def test_missing_permission_is_403_without_queries(test_app):
    app, spy = test_app
    _as(app, permissions=frozenset())
    response = TestClient(app).get(
        f"{BASE}/runs/{RUN}",
        params={"source_account_ref": "tenant-one"},
    )
    assert response.status_code == 403
    assert spy.queries == []


def test_preview_user_denied_even_if_permission_was_granted(test_app):
    app, spy = test_app
    _as(app, user=PREVIEW_PRINCIPAL_ID)
    response = TestClient(app).get(
        f"{BASE}/runs/{RUN}",
        params={"source_account_ref": "tenant-one"},
    )
    assert response.status_code == 403
    assert spy.queries == []


@pytest.mark.parametrize(
    "suffix",
    [
        f"/products/{PRODUCT}/runs",
        f"/runs/{RUN}",
        f"/runs/{RUN}/keywords",
    ],
)
def test_cross_account_denied_before_sql(test_app, suffix):
    app, spy = test_app
    _as(app)
    response = TestClient(app).get(
        BASE + suffix,
        params={"source_account_ref": "tenant-two"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "DATA_SCOPE_DENIED"
    assert spy.queries == []


def test_allowed_keyword_results_use_scoped_sql_and_safe_envelope(test_app):
    app, spy = test_app
    _as(app)
    response = TestClient(app).get(
        f"{BASE}/runs/{RUN}/keywords",
        params={"source_account_ref": "tenant-one", "limit": 2, "offset": 0},
    )
    assert response.status_code == 200, response.text
    envelope = response.json()
    assert envelope["success"] is True
    assert envelope["request_id"]
    data = envelope["data"]
    assert data["total"] == 1 and data["limit"] == 2
    assert data["items"][0]["keyword"] == "drawer organizer"
    assert data["items"][0]["allocation_grade"] == "P0"
    assert data["official_export_authorized"] is False
    assert not any(
        key in response.text
        for key in (
            "source_cells",
            "raw_object_key",
            "access_token",
            "authorization",
        )
    )
    _assert_scoped_sql(spy)


def test_allowed_run_history_queries_are_scoped(test_app):
    app, spy = test_app
    _as(app)
    response = TestClient(app).get(
        f"{BASE}/products/{PRODUCT}/runs",
        params={"source_account_ref": "tenant-one", "limit": 5, "offset": 0},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["items"][0]["run_id"] == str(RUN)
    _assert_scoped_sql(spy)


def test_missing_run_is_404_and_does_not_return_other_tenant_data(test_app):
    app, _ = test_app
    spy = SqlSpy(exists=False)
    app.dependency_overrides[get_db_session] = lambda: spy
    _as(app)
    response = TestClient(app).get(
        f"{BASE}/runs/{RUN}/keywords",
        params={"source_account_ref": "tenant-one"},
    )
    assert response.status_code == 404
    assert len(spy.queries) == 1
    _assert_scoped_sql(spy)


@pytest.mark.parametrize(
    "suffix,params",
    [
        (f"/runs/{RUN}/keywords", {"source_account_ref": "tenant-one", "limit": 201}),
        (f"/products/{PRODUCT}/runs", {"source_account_ref": "tenant-one", "limit": 101}),
        (f"/runs/{RUN}/keywords", {"source_account_ref": "tenant-one", "limit": 0}),
        (f"/runs/{RUN}/keywords", {"source_account_ref": "tenant-one", "offset": -1}),
        (f"/runs/{RUN}", {}),
        ("/runs/not-a-uuid", {"source_account_ref": "tenant-one"}),
    ],
)
def test_invalid_pagination_or_identifier_returns_422(test_app, suffix, params):
    app, spy = test_app
    _as(app)
    response = TestClient(app).get(BASE + suffix, params=params)
    assert response.status_code == 422, response.text
    assert spy.queries == []

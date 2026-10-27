"""Read-only integration boundary tests; never access an actual database."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from app.core.api import ApiError
from app.modules.keyword_planning.repository import KeywordPlanningRepository
from app.modules.keyword_planning.service import KeywordPlanningService

RUN_ID = UUID("00000000-0000-0000-0000-000000000001")
PROD_ID = UUID("00000000-0000-0000-0000-000000000002")
RULE_ID = UUID("00000000-0000-0000-0000-000000000003")
TERM_ID = UUID("00000000-0000-0000-0000-000000000004")
NOW = datetime(2026, 10, 23, tzinfo=UTC)


def _run():
    return SimpleNamespace(
        id=RUN_ID,
        product_id=PROD_ID,
        rule_version_id=RULE_ID,
        source_account_ref="allowed",
        item_id="123456",
        status="succeeded",
        created_at=NOW,
        finished_at=NOW,
    )


class FakeRepository:
    def __init__(self, exists=True):
        self.calls = []
        self.exists = exists

    def get_run(self, **kwargs):
        self.calls.append(("get_run", kwargs))
        return _run() if self.exists else None

    def count_runs(self, **kwargs):
        self.calls.append(("count_runs", kwargs))
        return 1

    def list_runs(self, **kwargs):
        self.calls.append(("list_runs", kwargs))
        return [_run()]

    def count_keywords(self, **kwargs):
        self.calls.append(("count_keywords", kwargs))
        return 1

    def list_keywords(self, **kwargs):
        self.calls.append(("list_keywords", kwargs))
        row = SimpleNamespace(
            term_id=TERM_ID,
            keyword_primary_type="核心本体词",
            page_coverage="标题已埋词",
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
        return [(row, "drawer organizer")]


def test_cross_account_denied_before_any_query():
    repo = FakeRepository()
    service = KeywordPlanningService(repo, frozenset({"allowed"}))
    with pytest.raises(ApiError) as exc:
        service.get_run(run_id=RUN_ID, account="other")
    assert exc.value.status_code == 403
    assert not repo.calls


def test_missing_scoped_run_does_not_fall_back_to_global_lookup():
    repo = FakeRepository(exists=False)
    service = KeywordPlanningService(repo, frozenset({"allowed"}))
    with pytest.raises(ApiError) as exc:
        service.list_keywords(run_id=RUN_ID, account="allowed", limit=10, offset=0)
    assert exc.value.status_code == 404
    assert repo.calls == [("get_run", {"run_id": RUN_ID, "source_account_ref": "allowed"})]


def test_list_runs_and_keyword_projections_are_scoped_and_non_mutating():
    repo = FakeRepository()
    service = KeywordPlanningService(repo, frozenset({"allowed"}))
    runs = service.list_runs(product_id=PROD_ID, account="allowed", limit=10, offset=0)
    assert runs.total == 1 and runs.items[0].rule_version_id == RULE_ID
    result = service.list_keywords(run_id=RUN_ID, account="allowed", limit=20, offset=0)
    assert result.total == 1 and result.items[0].keyword == "drawer organizer"
    assert result.items[0].suggested_optimization_bid == Decimal("0.420000")
    assert result.official_export_authorized is False
    assert all(call[1].get("source_account_ref") == "allowed" for call in repo.calls)
    assert not hasattr(repo, "commit")
    payload = result.model_dump(mode="json")
    assert "source_cells" not in str(payload)
    assert "raw_object_key" not in str(payload)


def test_repository_requires_both_run_id_and_account_in_all_run_queries():
    class CaptureSession:
        def __init__(self):
            self.sql = []

        def scalar(self, query):
            self.sql.append(str(query.compile(dialect=postgresql.dialect())))
            return None

        def execute(self, query):
            self.sql.append(str(query.compile(dialect=postgresql.dialect())))
            return []

    session = CaptureSession()
    repo = KeywordPlanningRepository(session)  # type: ignore[arg-type]
    repo.get_run(run_id=RUN_ID, source_account_ref="allowed")
    repo.count_keywords(run_id=RUN_ID, source_account_ref="allowed")
    repo.list_keywords(run_id=RUN_ID, source_account_ref="allowed", limit=5, offset=0)
    assert len(session.sql) == 3
    for sql in session.sql:
        assert (
            "source_account_ref" in sql
            and "run_id" in sql
            or ("source_account_ref" in sql and "ai_kw_analysis_run.id" in sql)
        )


def test_reject_preview_principal_even_with_read_permissions():
    from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal
    from app.modules.keyword_planning.router import get_service

    principal = Principal(PREVIEW_PRINCIPAL_ID, frozenset({"products:read"}))
    with pytest.raises(ApiError) as exc:
        get_service(None, frozenset({"allowed"}), principal)  # type: ignore[arg-type]
    assert exc.value.status_code == 403


def test_http_read_api_envelope_and_account_guard():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.modules.keyword_planning.router import get_service, router

    app = FastAPI()
    app.include_router(router)
    repo = FakeRepository()
    app.dependency_overrides[get_service] = lambda: KeywordPlanningService(
        repo, frozenset({"allowed"})
    )
    client = TestClient(app)
    success = client.get(
        f"/api/v1/keyword-planning/runs/{RUN_ID}/keywords",
        params={"source_account_ref": "allowed", "limit": 2, "offset": 0},
    )
    assert success.status_code == 200
    assert success.json()["data"]["items"][0]["keyword"] == "drawer organizer"
    assert success.json()["data"]["official_export_authorized"] is False
    with pytest.raises(ApiError) as exc:
        client.get(
            f"/api/v1/keyword-planning/runs/{RUN_ID}",
            params={"source_account_ref": "other"},
        )
    assert exc.value.status_code == 403


def test_http_pagination_validation_prevents_unbounded_reads():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.modules.keyword_planning.router import get_service, router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_service] = lambda: KeywordPlanningService(
        FakeRepository(), frozenset({"allowed"})
    )
    response = TestClient(app).get(
        f"/api/v1/keyword-planning/runs/{RUN_ID}/keywords",
        params={"source_account_ref": "allowed", "limit": 99999},
    )
    assert response.status_code == 422

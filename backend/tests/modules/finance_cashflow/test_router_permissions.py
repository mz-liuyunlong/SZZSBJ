"""权限和上传限制：只有超级管理员能用；不需要数据库。"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.auth import Principal, get_optional_principal
from app.core.config import get_settings
from app.db.session import get_db_session
from app.main import create_app
from app.modules.finance_cashflow import journal as J
from app.modules.finance_cashflow.service import (
    CashflowService,
    ImportHasReviewedLinesError,
    ImportNotFoundError,
    ImportVoidedError,
    LineNotFoundError,
)

UID = "0123456789abcdef"
IMPORT_ID = "00000000-0000-0000-0000-0000000000a1"
ACCOUNT_KEY = "manual_CNY_0000"
ENDPOINTS = [
    ("POST", "/api/finance/cashflow/imports"),
    ("GET", "/api/finance/cashflow/imports"),
    ("GET", f"/api/finance/cashflow/imports/{IMPORT_ID}"),
    ("POST", f"/api/finance/cashflow/imports/{IMPORT_ID}/void"),
    ("GET", "/api/finance/cashflow/accounts"),
    ("GET", "/api/finance/cashflow/categories"),
    ("GET", "/api/finance/cashflow/fx-rates"),
    ("GET", "/api/finance/cashflow/fx-rates/sync"),
    ("POST", "/api/finance/cashflow/fx-rates/sync"),
    ("GET", "/api/finance/cashflow/lines"),
    ("GET", "/api/finance/cashflow/anomalies"),
    ("GET", "/api/finance/cashflow/approvals"),
    ("GET", "/api/finance/cashflow/approvals/sync"),
    ("POST", "/api/finance/cashflow/approvals/sync"),
    ("POST", f"/api/finance/cashflow/lines/{UID}/events"),
    ("POST", "/api/finance/cashflow/lines/pair-events"),
    ("GET", "/api/finance/cashflow/accounts/admin"),
    ("POST", "/api/finance/cashflow/accounts"),
    ("PATCH", f"/api/finance/cashflow/accounts/{ACCOUNT_KEY}"),
    ("POST", "/api/finance/cashflow/manual-lines"),
]


@pytest.fixture
def client_for(monkeypatch: pytest.MonkeyPatch) -> Iterator:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+psycopg://synthetic@db.invalid/synthetic")
    monkeypatch.setenv("FINANCE_CASHFLOW_MAX_UPLOAD_BYTES", "10")
    monkeypatch.delenv("MEDIA_STORAGE_ROOT", raising=False)
    get_settings.cache_clear()

    def build(principal: Principal | None) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_optional_principal] = lambda: principal
        app.dependency_overrides[get_db_session] = lambda: MagicMock()
        return TestClient(app, raise_server_exceptions=False)

    yield build
    get_settings.cache_clear()


@pytest.mark.parametrize(("method", "path"), ENDPOINTS)
def test_anonymous_gets_401(client_for, method, path):
    assert client_for(None).request(method, path).status_code == 401


@pytest.mark.parametrize(("method", "path"), ENDPOINTS)
def test_other_users_get_403_even_with_finance_page_permission(client_for, method, path):
    finance_user = Principal(
        user_id="u1", permissions=frozenset({"page:finance:cash-flow:view", "finance:read"})
    )
    assert client_for(finance_user).request(method, path).status_code == 403


def test_undo_first_review_needs_the_review_permission(client_for):
    finance_user = Principal(
        user_id="u1", permissions=frozenset({"page:finance:cash-flow:view", "finance:read"})
    )
    response = client_for(finance_user).post(
        f"/api/finance/cashflow/lines/{UID}/events",
        json={"kind": "review1_undo", "expected_version": 1},
    )
    assert response.status_code == 403


def super_admin() -> Principal:
    return Principal(user_id="admin", permissions=frozenset({"*"}))


def test_upload_over_limit_is_413(client_for):
    response = client_for(super_admin()).post(
        "/api/finance/cashflow/imports", content=b"x" * 11, headers={"X-File-Name": "a.xlsx"}
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "CASHFLOW_UPLOAD_TOO_LARGE"


def test_empty_upload_is_422(client_for):
    response = client_for(super_admin()).post("/api/finance/cashflow/imports", content=b"")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CASHFLOW_EMPTY_UPLOAD"


def test_upload_without_storage_root_is_503_and_writes_nothing(client_for):
    response = client_for(super_admin()).post(
        "/api/finance/cashflow/imports", content=b"abc", headers={"X-File-Name": "a.xlsx"}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CASHFLOW_STORAGE_NOT_CONFIGURED"


def test_default_upload_limit_is_20_mb(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+psycopg://synthetic@db.invalid/synthetic")
    monkeypatch.delenv("FINANCE_CASHFLOW_MAX_UPLOAD_BYTES", raising=False)
    get_settings.cache_clear()
    assert get_settings().finance_cashflow_max_upload_bytes == 20 * 1024 * 1024
    get_settings.cache_clear()


def test_event_without_expected_version_is_422(client_for):
    response = client_for(super_admin()).post(
        f"/api/finance/cashflow/lines/{UID}/events", json={"kind": "review1_pass"}
    )
    assert response.status_code == 422


def test_pair_event_without_expected_version_is_422(client_for):
    response = client_for(super_admin()).post(
        "/api/finance/cashflow/lines/pair-events",
        json={"kind": "pair", "lines": [{"line_uid": UID}, {"line_uid": UID}]},
    )
    assert response.status_code == 422


def test_pair_event_refusal_returns_its_code(client_for, monkeypatch):
    def refuse(self, payload, *, actor, request_id):
        raise J.EventRejectedError(409, "有一笔已被别人改过", J.ERR_VERSION_CONFLICT)

    monkeypatch.setattr(CashflowService, "post_pair_event", refuse)
    response = client_for(super_admin()).post(
        "/api/finance/cashflow/lines/pair-events",
        json={"kind": "pair", "lines": [{"line_uid": UID, "expected_version": 0}]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == J.ERR_VERSION_CONFLICT


def test_void_blocked_returns_code_count_and_line_ids(client_for, monkeypatch):
    def refuse(self, import_id, *, reason, actor):
        raise ImportHasReviewedLinesError([UID])

    monkeypatch.setattr(CashflowService, "void_import", refuse)
    response = client_for(super_admin()).post(
        f"/api/finance/cashflow/imports/{IMPORT_ID}/void", json={"reason": "传错了"}
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "CASHFLOW_IMPORT_HAS_REVIEWED_LINES"
    assert error["details"] == {"count": 1, "line_ids": [UID]}


def _raise(error: Exception):
    def method(*_args, **_kwargs):
        raise error

    return method


@pytest.mark.parametrize(
    ("method_name", "error", "http", "path", "body", "status", "code"),
    [
        (
            "get_import",
            ImportNotFoundError(),
            "GET",
            f"imports/{IMPORT_ID}",
            None,
            404,
            "CASHFLOW_IMPORT_NOT_FOUND",
        ),
        (
            "void_import",
            ImportNotFoundError(),
            "POST",
            f"imports/{IMPORT_ID}/void",
            {"reason": "传错了"},
            404,
            "CASHFLOW_IMPORT_NOT_FOUND",
        ),
        (
            "void_import",
            ImportVoidedError(),
            "POST",
            f"imports/{IMPORT_ID}/void",
            {"reason": "传错了"},
            409,
            "CASHFLOW_IMPORT_VOIDED",
        ),
        ("upload", ImportVoidedError(), "POST", "imports", None, 409, "CASHFLOW_IMPORT_VOIDED"),
        (
            "post_event",
            LineNotFoundError(),
            "POST",
            f"lines/{UID}/events",
            "event",
            404,
            "CASHFLOW_LINE_NOT_FOUND",
        ),
        (
            "post_event",
            J.EventRejectedError(409, "x", J.ERR_VERSION_CONFLICT),
            "POST",
            f"lines/{UID}/events",
            "event",
            409,
            "CASHFLOW_VERSION_CONFLICT",
        ),
        (
            "post_event",
            J.EventRejectedError(409, "x", J.ERR_STAGE_NOT_ALLOWED),
            "POST",
            f"lines/{UID}/events",
            "event",
            409,
            "CASHFLOW_STAGE_NOT_ALLOWED",
        ),
        (
            "post_event",
            J.EventRejectedError(422, "x"),
            "POST",
            f"lines/{UID}/events",
            "event",
            422,
            "CASHFLOW_INVALID_EVENT",
        ),
        (
            "post_event",
            J.EventRejectedError(409, "x", J.ERR_IDEMPOTENCY_KEY_REUSED),
            "POST",
            f"lines/{UID}/events",
            "event",
            409,
            "CASHFLOW_IDEMPOTENCY_KEY_REUSED",
        ),
    ],
)
def test_service_errors_map_to_fixed_codes(
    client_for, monkeypatch, method_name, error, http, path, body, status, code
):
    monkeypatch.setattr(CashflowService, method_name, _raise(error))
    if http == "GET":
        response = client_for(super_admin()).get(f"/api/finance/cashflow/{path}")
    elif body == "event":
        response = client_for(super_admin()).post(
            f"/api/finance/cashflow/{path}",
            json={"kind": "review1_pass", "expected_version": 1, "idempotency_key": "k1"},
        )
    elif body is None:
        response = client_for(super_admin()).post(
            f"/api/finance/cashflow/{path}", content=b"abc", headers={"X-File-Name": "a.xlsx"}
        )
    else:
        response = client_for(super_admin()).post(f"/api/finance/cashflow/{path}", json=body)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_void_with_blank_reason_has_code(client_for):
    response = client_for(super_admin()).post(
        f"/api/finance/cashflow/imports/{IMPORT_ID}/void", json={"reason": "   "}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CASHFLOW_VOID_REASON_REQUIRED"

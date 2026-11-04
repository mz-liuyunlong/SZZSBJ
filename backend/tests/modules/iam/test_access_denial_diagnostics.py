"""IAM per-request 403 reason trace: strict sanitization and safe failure."""

from contextlib import nullcontext
from unittest.mock import MagicMock, patch

from app.modules.iam.access_denial_audit import record_access_denial


def test_denial_audit_records_only_canonical_fields_without_business_values() -> None:
    session = MagicMock()
    with patch(
        "app.modules.iam.access_denial_audit.get_session_factory",
        return_value=lambda: nullcontext(session),
    ):
        record_access_denial(
            request_id="synthetic-req",
            principal_id="42",
            method="GET",
            route_template="/api/sales/daily-sales",
            error_code="DATA_SCOPE_DENIED",
            stage="data_scope",
            permission_keys=("page:sales:daily-sales:view",),
            scope_reason="STORE_SCOPE_NOT_ENFORCED",
        )
    sql, params = session.execute.call_args.args
    assert "iam_access_denial_events" in str(sql)
    assert params["route_template"] == "/api/sales/daily-sales"
    assert params["scope_reason"] == "STORE_SCOPE_NOT_ENFORCED"
    assert "synthetic-req" == params["request_id"]
    assert "token" not in str(sql).lower()
    assert "query_string" not in str(sql)
    assert "body" not in str(sql)
    session.commit.assert_called_once()


def test_invalid_ids_and_unsanitized_routes_never_become_raw_audit_values() -> None:
    session = MagicMock()
    with patch(
        "app.modules.iam.access_denial_audit.get_session_factory",
        return_value=lambda: nullcontext(session),
    ):
        record_access_denial(
            request_id="req-01",
            principal_id="42",
            method="POST",
            route_template="/api/orders/secret?token=sensitive-value",
            error_code="FORBIDDEN",
            stage="permission",
            permission_keys=("raw token=value", "page:settings:role-management:view"),
            scope_reason="untrusted-account-data",
        )
    _sql, params = session.execute.call_args.args
    assert params["route_template"] == "unmatched"
    assert params["scope_reason"] is None
    assert "raw token" not in params["permissions"]
    assert "token" not in params["permissions"]


def test_audit_database_failure_never_changes_the_403_outcome() -> None:
    with patch(
        "app.modules.iam.access_denial_audit.get_session_factory",
        side_effect=RuntimeError("database unavailable"),
    ):
        # No raised exception: caller already returned a 403.
        record_access_denial(
            request_id="req-02",
            principal_id="42",
            method="GET",
            route_template="/api/sales/order-profit",
            error_code="FORBIDDEN",
            stage="permission",
            permission_keys=("page:sales:order-profit:view",),
            scope_reason=None,
        )


def test_iam_retention_is_limited_to_denial_table() -> None:
    from app.modules.iam.access_denial_audit import purge_expired_denials

    session = MagicMock()
    session.execute.return_value.rowcount = 5
    with patch(
        "app.modules.iam.access_denial_audit.get_session_factory",
        return_value=lambda: nullcontext(session),
    ):
        assert purge_expired_denials() == 5
    sql, params = session.execute.call_args.args
    assert "DELETE FROM iam_access_denial_events" in str(sql)
    assert params["days"] == 30
    session.commit.assert_called_once()


def test_denial_detail_endpoint_is_read_only_and_bounded() -> None:
    from starlette.requests import Request

    from app.core.auth import Principal
    from app.modules.iam.rbac_router import read_access_denial_diagnostics

    session = MagicMock()
    session.execute.return_value.mappings.return_value = [{
        "request_id": "req-42",
        "principal_id": "42",
        "method": "GET",
        "route_template": "/api/sales/order-profit",
        "denial_stage": "data_scope",
        "error_code": "DATA_SCOPE_DENIED",
        "required_permissions": [],
        "scope_reason": "UNENFORCED_DIMENSION",
        "created_at": "2026-11-04",
    }]
    request = Request({
        "type": "http", "method": "GET",
        "path": "/api/settings/rbac/access-denials", "headers": [],
    })
    response = read_access_denial_diagnostics(
        request,
        Principal(user_id="1", permissions=frozenset({"*"})),
        session,
        request_id="req-42",
        limit=50,
    )
    assert response.data["items"][0]["scope_reason"] == "UNENFORCED_DIMENSION"
    assert response.data["retention_days"] == 30
    session.commit.assert_not_called()

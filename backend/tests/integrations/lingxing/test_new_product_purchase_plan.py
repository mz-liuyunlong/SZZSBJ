"""Offline contract tests. No actual external calls or credentials."""

import pytest

from app.integrations.lingxing.new_product_purchase_plan import (
    API_PATH,
    INTERFACE_ID,
    PurchasePlanResponseError,
    build_purchase_plan_payload,
    parse_created_plan,
)
from app.integrations.lingxing.openapi import LingxingOpenApiClient, LingxingOpenApiError


def payload(**updates):
    values = dict(
        sku="TEST001", gtin="00465313943732", item_id="20347351964", sid="123", quantity=100
    )
    values.update(updates)
    return build_purchase_plan_payload(**values)


def test_exact_payload_and_registry():
    body = payload()
    assert body == {
        "remark": "00465313943732",
        "data": [
            {"sku": "TEST001", "quantity_plan": 100, "sid": "123", "remark": "ITEMID:20347351964"}
        ],
    }
    client = LingxingOpenApiClient()
    req = client.build_request(INTERFACE_ID, body)
    assert (req.method, req.api_path) == ("POST", API_PATH)
    with pytest.raises(LingxingOpenApiError):
        client.call(INTERFACE_ID, body, dry_run=False)


@pytest.mark.parametrize(
    "changes",
    [
        {"sku": None},
        {"gtin": 123},
        {"gtin": "123"},
        {"item_id": "123"},
        {"sid": "0"},
        {"sid": None},
        {"quantity": 0},
        {"quantity": True},
        {"quantity": 100001},
    ],
)
def test_bad_values(changes):
    with pytest.raises(ValueError):
        payload(**changes)


def good_response():
    return {
        "code": 0,
        "message": "success",
        "error_details": [],
        "request_id": "REQ-1",
        "data": {"plan_sn": ["PP123"], "ppg_sn": "PPG123"},
    }


def test_success_receipt():
    assert parse_created_plan(good_response()) == {
        "plan_sn": "PP123",
        "ppg_sn": "PPG123",
        "request_id": "REQ-1",
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"code": 500},
        {"code": True},
        {"data": {}},
        {"request_id": ""},
        {"error_details": ["error"]},
        {"data": {"plan_sn": ["PP1", "PP2"], "ppg_sn": "PPG1"}},
    ],
)
def test_unknown_or_failure_never_passes(changes):
    response = good_response()
    response.update(changes)
    with pytest.raises(PurchasePlanResponseError):
        parse_created_plan(response)


def test_mock_executor_records_exact_single_payload():
    captured = []

    def fake(request):
        captured.append(request)
        return good_response()

    client = LingxingOpenApiClient(
        executor=fake,
        enabled_interface_ids=frozenset({INTERFACE_ID}),
        owner_authorized_interface_ids=frozenset({INTERFACE_ID}),
    )
    receipt = parse_created_plan(client.call(INTERFACE_ID, payload(), dry_run=False))
    assert receipt["plan_sn"] == "PP123"
    assert len(captured) == 1
    assert dict(captured[0].parameters) == payload()


def test_v5_normal_approval_without_manual_scope(monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4

    from sqlalchemy.engine import make_url

    from app.core.config import AppEnvironment
    from app.modules.new_products import purchase_plan_service as module

    row = SimpleNamespace(id=uuid4(), source_account_ref="account-test")
    url = make_url("postgresql+psycopg://demo@db.example.invalid:5432/example")
    session = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(url=url),
        execute=lambda statement: SimpleNamespace(scalar_one=lambda: "off"),
    )
    settings = SimpleNamespace(app_env=AppEnvironment.PRODUCTION)
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(module, "get_database_url", lambda _settings: url)
    for name in (
        "SZZSBJ_NP_LINGXING_REAL_WRITE",
        "SZZSBJ_NP_LINGXING_REAL_APPLICATION_ID",
        "SZZSBJ_NP_LINGXING_CREDENTIAL_ACCOUNT_REF",
    ):
        monkeypatch.delenv(name, raising=False)
    assert module._local_settings(session, row) is settings
    row.id = uuid4()
    assert module._local_settings(session, row) is settings
    monkeypatch.setenv("SZZSBJ_NP_LINGXING_REAL_WRITE", "NO")
    with pytest.raises(module.ApiError) as exc:
        module._local_settings(session, row)
    assert exc.value.code == "NP_LX_WRITE_DISABLED"
    monkeypatch.delenv("SZZSBJ_NP_LINGXING_REAL_WRITE")
    session.execute = lambda statement: SimpleNamespace(scalar_one=lambda: "on")
    with pytest.raises(module.ApiError) as exc:
        module._local_settings(session, row)
    assert exc.value.code == "NP_LX_WRITE_DB_READONLY"
    settings.app_env = AppEnvironment.TEST
    with pytest.raises(module.ApiError) as exc:
        module._local_settings(session, row)
    assert exc.value.code == "NP_LX_TEST_ENV_DENIED"


def test_v4_reads_same_server_db_when_no_separate_source(monkeypatch):
    from app.modules.new_products import purchase_plan_service as module

    session, row = object(), object()
    calls = []
    monkeypatch.delenv("NEW_PRODUCTS_READ_DATABASE_URL", raising=False)
    monkeypatch.setattr(
        module, "_build_verified_payload", lambda *args: calls.append(args) or {"ok": True}
    )
    assert module._read_verified_payload(session, row, "store-test", 100) == {"ok": True}
    assert calls == [(session, row, "store-test", 100)]


def test_v5_credential_account_unique_and_optional_binding(monkeypatch):
    from app.modules.new_products import purchase_plan_service as module

    monkeypatch.delenv("SZZSBJ_NP_LINGXING_CREDENTIAL_ACCOUNT_REF", raising=False)
    module._verify_credential_account({"a"}, "a")
    for refs in (set(), {"b"}, {"a", "b"}):
        with pytest.raises(module.ApiError) as exc:
            module._verify_credential_account(refs, "a")
        assert exc.value.code == "NP_LX_ACCOUNT_UNVERIFIED"
    monkeypatch.setenv("SZZSBJ_NP_LINGXING_CREDENTIAL_ACCOUNT_REF", "b")
    with pytest.raises(module.ApiError) as exc:
        module._verify_credential_account({"a"}, "a")
    assert exc.value.code == "NP_LX_CREDENTIAL_ACCOUNT_UNCONFIRMED"


def test_v6_initial_token_failure_never_creates_attempt(monkeypatch):
    from types import SimpleNamespace

    from app.integrations.lingxing.token_manager import LingxingTokenError
    from app.modules.new_products import purchase_plan_service as module

    def no_token():
        raise LingxingTokenError("TOKEN_TRANSPORT_ERROR", retryable=True)

    monkeypatch.setattr(
        module,
        "get_shared_lingxing_token_manager",
        lambda settings: SimpleNamespace(get_access_token=no_token),
    )
    monkeypatch.setattr(module, "_local_settings", lambda *args: object())
    monkeypatch.setattr(module, "ensure_no_attempt", lambda *args: None)
    monkeypatch.setattr(module, "_read_verified_payload", lambda *args: {})
    monkeypatch.setattr(module, "validate_transport", lambda *args: None)

    def forbidden(*args, **kwargs):
        pytest.fail("No durable attempt, commit or purchase call allowed")

    monkeypatch.setattr(module, "_event", forbidden)
    monkeypatch.setattr(module, "create_purchase_plan", forbidden)
    with pytest.raises(module.ApiError) as exc:
        module.create_and_record_local_plan(
            SimpleNamespace(commit=forbidden), object(), "actor", "store", 100
        )
    assert exc.value.code == "NP_LX_TOKEN_PREFLIGHT_FAILED"


def test_v6_existing_attempt_still_blocks_before_auth(monkeypatch):
    from app.modules.new_products import purchase_plan_service as module

    monkeypatch.setattr(module, "_local_settings", lambda *args: object())

    def blocked(*args):
        module.fail("NP_LX_ALREADY_ATTEMPTED", "blocked")

    monkeypatch.setattr(module, "ensure_no_attempt", blocked)

    def forbidden(*args):
        pytest.fail("Existing attempt must block before authentication")

    monkeypatch.setattr(module, "_preflight_purchase_auth", forbidden)
    with pytest.raises(module.ApiError) as exc:
        module.create_and_record_local_plan(object(), object(), "actor", "store", 100)
    assert exc.value.code == "NP_LX_ALREADY_ATTEMPTED"

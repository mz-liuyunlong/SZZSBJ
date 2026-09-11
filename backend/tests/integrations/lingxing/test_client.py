import json

import httpx
import pytest
from pydantic import JsonValue, SecretStr, ValidationError

from app.core.config import Settings
from app.integrations.lingxing.client import (
    LingxingCaptureRequest,
    LingxingClientError,
    LingxingEndpoint,
    LingxingPageRequest,
    LingxingReadonlyClient,
)

SYNTHETIC_DATABASE_URL = "postgresql+psycopg://synthetic@db.invalid/synthetic"
WALMART_ENDPOINT: LingxingEndpoint = "/basicOpen/multiplatform/walmart/list"
SALE_ENDPOINT: LingxingEndpoint = "/basicOpen/platformStatisticsV2/saleStat/pageList"
PROFIT_ENDPOINT: LingxingEndpoint = "/basicOpen/multiplatform/profit/report/order"
SELLER_ENDPOINT: LingxingEndpoint = "/pb/mp/shop/v2/getSellerList"
BATCH_PRODUCT_ENDPOINT: LingxingEndpoint = (
    "/erp/sc/routing/data/local_inventory/batchGetProductInfo"
)


class _FakeTokenProvider:
    def __init__(
        self,
        access_token: str = "credential-fixture",
        recovered_access_token: str = "rotated-credential-fixture",
        *,
        recovery_error: Exception | None = None,
    ) -> None:
        self._access_token = SecretStr(access_token)
        self._recovered_access_token = SecretStr(recovered_access_token)
        self._recovery_error = recovery_error
        self.get_calls = 0
        self.recover_calls: list[int | str] = []

    def get_access_token(self) -> SecretStr:
        self.get_calls += 1
        return self._access_token

    def recover_from_access_error(self, provider_code: int | str) -> SecretStr:
        self.recover_calls.append(provider_code)
        if self._recovery_error is not None:
            raise self._recovery_error
        return self._recovered_access_token


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "APP_ENV": "test",
        "TEST_DATABASE_URL": SYNTHETIC_DATABASE_URL,
        "LINGXING_BASE_URL": "https://provider.invalid",
        "LINGXING_ENABLE_REAL_CALLS": True,
    }
    values.update(overrides)
    return Settings.model_validate(values)


def _capture(
    api_path: LingxingEndpoint = WALMART_ENDPOINT,
    *,
    body: JsonValue = None,
    params: dict[str, str | int | float | bool | None] | None = None,
    page_no: int = 1,
    page_size: int = 3,
    store_ids: tuple[str, ...] = ("scope-fixture",),
) -> LingxingCaptureRequest:
    if body is None:
        body = {
            "offset": 0,
            "length": page_size,
            "store_ids": list(store_ids),
        }
    return LingxingCaptureRequest(
        api_path=api_path,
        pages=(
            LingxingPageRequest(
                page_no=page_no,
                page_size=page_size,
                params=params,
                body=body,
            ),
        ),
        store_ids=store_ids,
        object_type="synthetic_object",
        trace_id="trace-fixture",
        run_id="run-fixture",
        batch_id="batch-fixture",
    )


def _is_success(
    endpoint: LingxingEndpoint,
    response: httpx.Response,
    payload: JsonValue,
) -> bool:
    del endpoint, response
    return isinstance(payload, dict) and payload.get("code") == 0


@pytest.mark.parametrize(
    ("endpoint", "body"),
    [
        (
            WALMART_ENDPOINT,
            {"offset": 0, "length": 3, "store_ids": ["scope-fixture"]},
        ),
        (
            SALE_ENDPOINT,
            {"page": 1, "length": 3, "sids": ["scope-fixture"]},
        ),
        (
            PROFIT_ENDPOINT,
            {"offset": 0, "length": 3, "sids": ["scope-fixture"]},
        ),
    ],
)
def test_enabled_endpoint_contracts_bind_the_actual_outbound_request(
    endpoint: LingxingEndpoint,
    body: JsonValue,
) -> None:
    marker = "credential-fixture"
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.method == "POST"
        assert request.url.path == endpoint
        assert not request.url.query
        assert request.headers["Authorization"] == marker
        assert json.loads(request.content) == body
        assert marker.encode() not in request.content
        return httpx.Response(200, json={"code": 0, "access_token": marker})

    settings = _settings()
    assert settings.lingxing_dry_run is True
    token_provider = _FakeTokenProvider(marker)
    client = LingxingReadonlyClient(
        settings,
        token_provider=token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    )
    try:
        envelope = client.fetch_pages(_capture(endpoint, body=body))[0]
    finally:
        client.close()

    assert envelope.is_success is True
    assert envelope.page_no == 1
    assert envelope.store_id == "scope-fixture"
    assert marker not in envelope.model_dump_json()
    assert marker not in repr(envelope)
    assert marker not in str(envelope)
    assert calls == 1
    assert token_provider.get_calls == 1
    assert token_provider.recover_calls == []


def test_http_and_provider_failures_are_safe_raw_envelopes() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del request
        calls += 1
        return httpx.Response(503, json={"message": "authorization=credential-fixture"})

    token_provider = _FakeTokenProvider()
    client = LingxingReadonlyClient(
        _settings(),
        token_provider=token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    )
    try:
        http_failure = client.fetch_pages(_capture())[0]
    finally:
        client.close()

    assert calls == 2
    assert http_failure.is_success is False
    assert http_failure.error_code == "HTTP_ERROR"
    assert http_failure.attempt_no == 2
    assert "credential-fixture" not in http_failure.model_dump_json()
    assert token_provider.get_calls == 2
    assert token_provider.recover_calls == []

    provider_token_provider = _FakeTokenProvider()
    provider_client = LingxingReadonlyClient(
        _settings(),
        token_provider=provider_token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"code": 1, "message": "rejected"})
        ),
    )
    try:
        provider_failure = provider_client.fetch_pages(_capture())[0]
    finally:
        provider_client.close()

    assert provider_failure.response_code == 200
    assert provider_failure.is_success is False
    assert provider_failure.error_code == "PROVIDER_ERROR"
    assert provider_token_provider.get_calls == 1
    assert provider_token_provider.recover_calls == []


@pytest.mark.parametrize("provider_code", [2001003, "2001003"])
def test_access_error_recovers_and_replays_once(provider_code: int | str) -> None:
    calls = 0
    original_body: JsonValue = {
        "offset": 0,
        "length": 3,
        "store_ids": ["scope-fixture"],
    }
    token_provider = _FakeTokenProvider()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.method == "POST"
        assert request.url.path == WALMART_ENDPOINT
        assert json.loads(request.content) == original_body
        expected_token = "credential-fixture" if calls == 1 else "rotated-credential-fixture"
        assert request.headers["Authorization"] == expected_token
        if calls == 1:
            return httpx.Response(200, json={"code": provider_code})
        return httpx.Response(200, json={"code": 0, "data": []})

    client = LingxingReadonlyClient(
        _settings(),
        token_provider=token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
    )
    try:
        envelope = client.fetch_pages(_capture(body=original_body))[0]
    finally:
        client.close()

    assert envelope.is_success is True
    assert envelope.attempt_no == 2
    assert calls == 2
    assert token_provider.get_calls == 1
    assert token_provider.recover_calls == [2001003]


def test_replayed_access_error_fails_closed_without_another_recovery() -> None:
    calls = 0
    token_provider = _FakeTokenProvider()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        expected_token = "credential-fixture" if calls == 1 else "rotated-credential-fixture"
        assert request.headers["Authorization"] == expected_token
        return httpx.Response(
            200,
            json={
                "code": 2001003,
                "access_token": "credential-fixture",
                "Authorization": "rotated-credential-fixture",
            },
        )

    client = LingxingReadonlyClient(
        _settings(),
        token_provider=token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
    )
    try:
        envelope = client.fetch_pages(_capture())[0]
    finally:
        client.close()

    dumped = envelope.model_dump_json()
    assert envelope.is_success is False
    assert envelope.error_code == "PROVIDER_ERROR"
    assert envelope.attempt_no == 2
    assert calls == 2
    assert token_provider.get_calls == 1
    assert token_provider.recover_calls == [2001003]
    assert "credential-fixture" not in dumped
    assert "rotated-credential-fixture" not in dumped


def test_access_error_recovery_failure_does_not_replay_or_leak_details() -> None:
    calls = 0
    token_provider = _FakeTokenProvider(
        recovery_error=RuntimeError("synthetic credential-fixture recovery failure")
    )

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.headers["Authorization"] == "credential-fixture"
        return httpx.Response(
            200,
            json={"code": 2001003, "access_token": "credential-fixture"},
        )

    client = LingxingReadonlyClient(
        _settings(),
        token_provider=token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
    )
    try:
        envelope = client.fetch_pages(_capture())[0]
    finally:
        client.close()

    assert envelope.is_success is False
    assert envelope.error_code == "AUTH_ERROR"
    assert envelope.error_message == "Lingxing authorization recovery failed"
    assert calls == 1
    assert token_provider.get_calls == 1
    assert token_provider.recover_calls == [2001003]
    assert "credential-fixture" not in envelope.model_dump_json()
    assert "credential-fixture" not in repr(envelope)
    assert "credential-fixture" not in str(envelope)


def test_transport_failure_is_bounded_and_recordable() -> None:
    calls = 0

    def timeout(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    token_provider = _FakeTokenProvider()
    client = LingxingReadonlyClient(
        _settings(),
        token_provider=token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(timeout),
        sleeper=lambda _: None,
    )
    try:
        envelope = client.fetch_pages(_capture())[0]
    finally:
        client.close()

    assert calls == 2
    assert envelope.is_success is False
    assert envelope.error_code == "TRANSPORT_ERROR"
    assert envelope.response_json is None
    assert token_provider.get_calls == 2
    assert token_provider.recover_calls == []


def test_endpoint_store_and_pagination_boundaries_fail_closed() -> None:
    with pytest.raises(ValidationError):
        LingxingCaptureRequest.model_validate(
            {
                **_capture().model_dump(),
                "api_path": "/unapproved/path",
            }
        )
    with pytest.raises(ValidationError):
        LingxingCaptureRequest.model_validate(
            {
                **_capture().model_dump(),
                "api_path": "https://provider.invalid/basicOpen/multiplatform/walmart/list",
            }
        )
    with pytest.raises(ValidationError):
        LingxingCaptureRequest.model_validate(
            {
                **_capture().model_dump(),
                "store_ids": [],
            }
        )
    with pytest.raises(ValidationError):
        LingxingPageRequest(page_no=1, page_size=4)

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"code": 0})

    token_provider = _FakeTokenProvider()
    client = LingxingReadonlyClient(
        _settings(LINGXING_SAMPLE_PAGE_SIZE=1),
        token_provider=token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(LingxingClientError, match="page size limit"):
        client.fetch_pages(_capture(page_size=2))
    client.close()
    assert calls == 0
    assert token_provider.get_calls == 0
    assert token_provider.recover_calls == []


@pytest.mark.parametrize(
    ("endpoint", "body", "page_no", "page_size", "message"),
    [
        (
            WALMART_ENDPOINT,
            {"offset": 0, "length": 3, "store_ids": ["other-scope"]},
            1,
            3,
            "store scope",
        ),
        (
            WALMART_ENDPOINT,
            {"offset": 0, "length": 4, "store_ids": ["scope-fixture"]},
            1,
            3,
            "page size",
        ),
        (
            SALE_ENDPOINT,
            {"page": 2, "length": 3, "sids": ["scope-fixture"]},
            1,
            3,
            "page number",
        ),
        (
            SALE_ENDPOINT,
            {"page": 1, "length": 3, "sids": ["other-scope"]},
            1,
            3,
            "store scope",
        ),
        (
            SALE_ENDPOINT,
            {"page": 1, "length": 4, "sids": ["scope-fixture"]},
            1,
            3,
            "page size",
        ),
        (
            PROFIT_ENDPOINT,
            {"offset": 0, "length": 3, "sids": ["other-scope"]},
            1,
            3,
            "store scope",
        ),
        (
            PROFIT_ENDPOINT,
            {"offset": 0, "length": 4, "sids": ["scope-fixture"]},
            1,
            3,
            "page size",
        ),
    ],
)
def test_endpoint_contracts_reject_unauthorized_store_and_pagination(
    endpoint: LingxingEndpoint,
    body: JsonValue,
    page_no: int,
    page_size: int,
    message: str,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"code": 0})

    token_provider = _FakeTokenProvider()
    client = LingxingReadonlyClient(
        _settings(),
        token_provider=token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(LingxingClientError, match=message):
            client.fetch_pages(
                _capture(
                    endpoint,
                    body=body,
                    page_no=page_no,
                    page_size=page_size,
                )
            )
    finally:
        client.close()
    assert calls == 0
    assert token_provider.get_calls == 0
    assert token_provider.recover_calls == []


@pytest.mark.parametrize(
    ("endpoint", "body"),
    [
        (
            WALMART_ENDPOINT,
            {
                "offset": 0,
                "length": 200,
                "store_ids": ["scope-fixture"],
                "pageSize": 3,
            },
        ),
        (
            WALMART_ENDPOINT,
            {
                "offset": 0,
                "length": 3,
                "store_ids": ["scope-fixture"],
                "storeIds": ["other-scope"],
            },
        ),
        (
            SALE_ENDPOINT,
            {
                "page": 1,
                "length": 200,
                "sids": ["scope-fixture"],
                "pageSize": 3,
            },
        ),
        (
            SALE_ENDPOINT,
            {
                "page": 1,
                "length": 3,
                "sids": ["scope-fixture"],
                "store_ids": ["other-scope"],
            },
        ),
        (
            SALE_ENDPOINT,
            {
                "page": 1,
                "length": 3,
                "sids": ["scope-fixture"],
                "storeIds": ["other-scope"],
            },
        ),
        (
            SALE_ENDPOINT,
            {
                "page": 1,
                "length": 3,
                "sids": ["scope-fixture"],
                "offset": 0,
            },
        ),
        (
            PROFIT_ENDPOINT,
            {
                "offset": 0,
                "length": 200,
                "sids": ["scope-fixture"],
                "pageSize": 3,
            },
        ),
        (
            PROFIT_ENDPOINT,
            {
                "offset": 0,
                "length": 3,
                "sids": ["scope-fixture"],
                "store_ids": ["other-scope"],
            },
        ),
        (
            PROFIT_ENDPOINT,
            {
                "offset": 0,
                "length": 3,
                "sids": ["scope-fixture"],
                "storeIds": ["other-scope"],
            },
        ),
        (
            PROFIT_ENDPOINT,
            {
                "offset": 0,
                "length": 3,
                "sids": ["scope-fixture"],
                "page": 1,
            },
        ),
        (
            WALMART_ENDPOINT,
            {"offset": 0, "store_ids": ["scope-fixture"]},
        ),
    ],
)
def test_endpoint_contracts_reject_invalid_body_shapes_before_transport(
    endpoint: LingxingEndpoint,
    body: JsonValue,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"code": 0})

    token_provider = _FakeTokenProvider()
    client = LingxingReadonlyClient(
        _settings(),
        token_provider=token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(LingxingClientError, match="endpoint contract"):
            client.fetch_pages(_capture(endpoint, body=body))
    finally:
        client.close()
    assert calls == 0
    assert token_provider.get_calls == 0
    assert token_provider.recover_calls == []


@pytest.mark.parametrize(
    ("endpoint", "body"),
    [
        (
            WALMART_ENDPOINT,
            {"offset": 0, "length": 3, "store_ids": ["scope-fixture"]},
        ),
        (
            SALE_ENDPOINT,
            {"page": 1, "length": 3, "sids": ["scope-fixture"]},
        ),
        (
            PROFIT_ENDPOINT,
            {"offset": 0, "length": 3, "sids": ["scope-fixture"]},
        ),
    ],
)
def test_endpoint_contracts_reject_query_body_confusion_before_transport(
    endpoint: LingxingEndpoint,
    body: JsonValue,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"code": 0})

    token_provider = _FakeTokenProvider()
    client = LingxingReadonlyClient(
        _settings(),
        token_provider=token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(LingxingClientError, match="query parameters"):
            client.fetch_pages(_capture(endpoint, body=body, params={"length": 200}))
    finally:
        client.close()
    assert calls == 0
    assert token_provider.get_calls == 0
    assert token_provider.recover_calls == []


def test_store_scope_may_be_a_nonempty_subset_of_the_capture_allowlist() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert json.loads(request.content)["store_ids"] == ["scope-fixture"]
        return httpx.Response(200, json={"code": 0})

    client = LingxingReadonlyClient(
        _settings(),
        token_provider=_FakeTokenProvider(),
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
    )
    try:
        envelope = client.fetch_pages(
            _capture(
                body={"offset": 0, "length": 3, "store_ids": ["scope-fixture"]},
                store_ids=("scope-fixture", "unused-scope"),
            )
        )[0]
    finally:
        client.close()

    assert envelope.is_success is True
    assert calls == 1


@pytest.mark.parametrize(
    "bypass_path",
    [
        "https://provider.invalid/basicOpen/multiplatform/walmart/list",
        "//provider.invalid/basicOpen/multiplatform/walmart/list",
        "/basicOpen/../multiplatform/walmart/list",
    ],
)
def test_client_rejects_endpoint_path_bypasses_before_transport(bypass_path: str) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"code": 0})

    token_provider = _FakeTokenProvider()
    client = LingxingReadonlyClient(
        _settings(),
        token_provider=token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(LingxingClientError, match="endpoint is not approved"):
            client.fetch_pages(_capture().model_copy(update={"api_path": bypass_path}))
    finally:
        client.close()
    assert calls == 0
    assert token_provider.get_calls == 0
    assert token_provider.recover_calls == []


@pytest.mark.parametrize(
    ("endpoint", "message"),
    [
        (SELLER_ENDPOINT, "pending_store_scope"),
        (BATCH_PRODUCT_ENDPOINT, "pending_endpoint_contract"),
    ],
)
def test_pending_endpoint_contracts_fail_closed_before_transport(
    endpoint: LingxingEndpoint,
    message: str,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"code": 0})

    token_provider = _FakeTokenProvider()
    client = LingxingReadonlyClient(
        _settings(),
        token_provider=token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(LingxingClientError, match=message):
            client.fetch_pages(_capture(endpoint, body={}))
    finally:
        client.close()
    assert calls == 0
    assert token_provider.get_calls == 0
    assert token_provider.recover_calls == []


def test_client_rejects_empty_store_allowlist_before_transport() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"code": 0})

    token_provider = _FakeTokenProvider()
    client = LingxingReadonlyClient(
        _settings(),
        token_provider=token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(LingxingClientError, match="store allowlist is required"):
            client.fetch_pages(_capture().model_copy(update={"store_ids": ()}))
    finally:
        client.close()
    assert calls == 0
    assert token_provider.get_calls == 0
    assert token_provider.recover_calls == []


def test_client_rejects_multiple_pages_before_transport() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"code": 0})

    capture = _capture()
    token_provider = _FakeTokenProvider()
    client = LingxingReadonlyClient(
        _settings(),
        token_provider=token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(LingxingClientError, match="page limit"):
            client.fetch_pages(capture.model_copy(update={"pages": capture.pages * 2}))
    finally:
        client.close()
    assert calls == 0
    assert token_provider.get_calls == 0
    assert token_provider.recover_calls == []


def test_response_size_limit_rejects_payload_before_json_or_raw_capture() -> None:
    oversized = b'{"code":0,"data":"' + (b"x" * 64) + b'"}'
    client = LingxingReadonlyClient(
        _settings(LINGXING_MAX_RESPONSE_BYTES=32),
        token_provider=_FakeTokenProvider(),
        success_evaluator=_is_success,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=oversized)),
    )
    try:
        envelope = client.fetch_pages(_capture())[0]
    finally:
        client.close()

    assert envelope.is_success is False
    assert envelope.error_code == "RESPONSE_TOO_LARGE"
    assert envelope.response_json is None
    assert "x" * 8 not in envelope.model_dump_json()


def test_real_call_switch_defaults_to_disabled() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"code": 0})

    settings = _settings(LINGXING_ENABLE_REAL_CALLS=False)
    token_provider = _FakeTokenProvider()
    client = LingxingReadonlyClient(
        settings,
        token_provider=token_provider,
        success_evaluator=_is_success,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(LingxingClientError, match="disabled"):
            client.fetch_pages(_capture())
    finally:
        client.close()
    assert calls == 0
    assert token_provider.get_calls == 0
    assert token_provider.recover_calls == []

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.integrations.lingxing.token_manager import (
    GET_TOKEN_PATH,
    REFRESH_TOKEN_PATH,
    LingxingTokenClient,
    LingxingTokenError,
    LingxingTokenManager,
)

SYNTHETIC_DATABASE_URL = "postgresql+psycopg://synthetic@db.invalid/synthetic"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "APP_ENV": "test",
        "TEST_DATABASE_URL": SYNTHETIC_DATABASE_URL,
        "LINGXING_BASE_URL": "https://provider.invalid",
        "LINGXING_APP_ID": "app-id-fixture",
        "LINGXING_APP_SECRET": "app-secret-fixture",
        "LINGXING_ENABLE_TOKEN_REQUESTS": True,
    }
    values.update(overrides)
    return Settings.model_validate(values)


def _success(
    *,
    code: int | str = 200,
    access_token: str = "access-token-fixture-1",
    refresh_token: str = "refresh-token-fixture-1",
    expires_in: int | str = 3_600,
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": code,
            "data": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": expires_in,
            },
        },
    )


def _multipart_body(request: httpx.Request) -> str:
    content_type = request.headers["content-type"]
    assert content_type.startswith("multipart/form-data; boundary=")
    return request.content.decode()


@pytest.mark.parametrize("provider_code", [200, "200"])
def test_get_token_uses_exact_multipart_fields_and_parses_string_ttl(
    provider_code: int | str,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.method == "POST"
        assert request.url.path == GET_TOKEN_PATH
        body = _multipart_body(request)
        assert 'name="appId"' in body
        assert 'name="appSecret"' in body
        assert 'name="refreshToken"' not in body
        assert "app-id-fixture" in body
        assert "app-secret-fixture" in body
        return _success(code=provider_code, expires_in="3600")

    client = LingxingTokenClient(_settings(), transport=httpx.MockTransport(handler))
    try:
        pair = client.get_token()
    finally:
        client.close()

    assert pair.access_token.get_secret_value() == "access-token-fixture-1"
    assert pair.refresh_token.get_secret_value() == "refresh-token-fixture-1"
    assert pair.expires_in == 3_600
    assert calls == 1


@pytest.mark.parametrize("provider_code", [200, "200"])
def test_refresh_token_uses_exact_multipart_fields(provider_code: int | str) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.method == "POST"
        assert request.url.path == REFRESH_TOKEN_PATH
        body = _multipart_body(request)
        assert 'name="appId"' in body
        assert 'name="refreshToken"' in body
        assert 'name="appSecret"' not in body
        assert "refresh-token-fixture-1" in body
        return _success(
            code=provider_code,
            access_token="access-token-fixture-2",
            refresh_token="refresh-token-fixture-2",
        )

    client = LingxingTokenClient(_settings(), transport=httpx.MockTransport(handler))
    try:
        pair = client.refresh_token(SecretStr("refresh-token-fixture-1"))
    finally:
        client.close()

    assert pair.access_token.get_secret_value() == "access-token-fixture-2"
    assert pair.refresh_token.get_secret_value() == "refresh-token-fixture-2"
    assert calls == 1


@pytest.mark.parametrize(
    ("payload", "expected_provider_code"),
    [
        ({"code": 0, "data": {}}, 0),
        ({"data": {}}, None),
    ],
)
def test_non_official_or_missing_success_code_fails_closed(
    payload: dict[str, object],
    expected_provider_code: int | None,
) -> None:
    client = LingxingTokenClient(
        _settings(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    )
    try:
        with pytest.raises(LingxingTokenError) as error:
            client.get_token()
    finally:
        client.close()

    assert error.value.category == "TOKEN_PROVIDER_ERROR"
    assert error.value.provider_code == expected_provider_code


@pytest.mark.parametrize(
    ("expires_in", "expected_refresh_after"),
    [
        (3_600, NOW + timedelta(seconds=3_000)),
        (300, NOW + timedelta(seconds=240)),
    ],
)
def test_expiry_uses_response_ttl_and_configured_early_refresh(
    expires_in: int,
    expected_refresh_after: datetime,
) -> None:
    client = LingxingTokenClient(
        _settings(),
        transport=httpx.MockTransport(lambda _: _success(expires_in=expires_in)),
    )
    manager = LingxingTokenManager(client, _settings(), clock=lambda: NOW)
    try:
        manager.get_access_token()
    finally:
        client.close()

    snapshot = manager._snapshot
    assert snapshot is not None
    assert snapshot.expires_at == NOW + timedelta(seconds=expires_in)
    assert snapshot.refresh_after == expected_refresh_after
    assert snapshot.expires_in == expires_in


def test_refresh_atomically_replaces_both_tokens() -> None:
    current_time = [NOW]
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == GET_TOKEN_PATH:
            return _success(expires_in=1_000)
        body = _multipart_body(request)
        assert "refresh-token-fixture-1" in body
        assert "refresh-token-fixture-2" not in body
        return _success(
            access_token="access-token-fixture-2",
            refresh_token="refresh-token-fixture-2",
            expires_in=2_000,
        )

    settings = _settings()
    client = LingxingTokenClient(settings, transport=httpx.MockTransport(handler))
    manager = LingxingTokenManager(client, settings, clock=lambda: current_time[0])
    try:
        first_access = manager.get_access_token()
        current_time[0] = NOW + timedelta(seconds=500)
        second_access = manager.get_access_token()
    finally:
        client.close()

    snapshot = manager._snapshot
    assert snapshot is not None
    assert first_access.get_secret_value() == "access-token-fixture-1"
    assert second_access.get_secret_value() == "access-token-fixture-2"
    assert snapshot.access_token.get_secret_value() == "access-token-fixture-2"
    assert snapshot.refresh_token.get_secret_value() == "refresh-token-fixture-2"
    assert snapshot.generation == 2
    assert paths == [GET_TOKEN_PATH, REFRESH_TOKEN_PATH]


@pytest.mark.parametrize("provider_code", [2001008, 2001009])
def test_invalid_refresh_token_falls_back_to_get_token(provider_code: int) -> None:
    current_time = [NOW]
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if paths == [GET_TOKEN_PATH]:
            return _success(expires_in=1_000)
        if request.url.path == REFRESH_TOKEN_PATH:
            return httpx.Response(200, json={"code": provider_code, "message": "rejected"})
        return _success(
            access_token="access-token-fixture-2",
            refresh_token="refresh-token-fixture-2",
        )

    settings = _settings()
    client = LingxingTokenClient(settings, transport=httpx.MockTransport(handler))
    manager = LingxingTokenManager(
        client,
        settings,
        clock=lambda: current_time[0],
        sleeper=lambda _: None,
    )
    try:
        manager.get_access_token()
        current_time[0] = NOW + timedelta(seconds=500)
        refreshed = manager.get_access_token()
    finally:
        client.close()

    assert refreshed.get_secret_value() == "access-token-fixture-2"
    assert paths == [GET_TOKEN_PATH, REFRESH_TOKEN_PATH, GET_TOKEN_PATH]


def test_access_token_error_2001003_triggers_one_refresh() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == GET_TOKEN_PATH:
            return _success()
        return _success(
            access_token="access-token-fixture-2",
            refresh_token="refresh-token-fixture-2",
        )

    settings = _settings()
    client = LingxingTokenClient(settings, transport=httpx.MockTransport(handler))
    manager = LingxingTokenManager(client, settings, clock=lambda: NOW)
    try:
        manager.get_access_token()
        recovered = manager.recover_from_access_error("2001003")
    finally:
        client.close()

    assert recovered.get_secret_value() == "access-token-fixture-2"
    assert paths == [GET_TOKEN_PATH, REFRESH_TOKEN_PATH]


def test_failed_refresh_token_is_never_submitted_twice() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if paths == [GET_TOKEN_PATH]:
            return _success()
        if request.url.path == REFRESH_TOKEN_PATH:
            return httpx.Response(200, json={"code": 2001002, "message": "rejected"})
        return _success(
            access_token="access-token-fixture-2",
            refresh_token="refresh-token-fixture-2",
        )

    settings = _settings()
    client = LingxingTokenClient(settings, transport=httpx.MockTransport(handler))
    manager = LingxingTokenManager(client, settings, clock=lambda: NOW)
    try:
        manager.get_access_token()
        with pytest.raises(LingxingTokenError):
            manager.refresh_access_token()
        recovered = manager.refresh_access_token()
    finally:
        client.close()

    assert recovered.get_secret_value() == "access-token-fixture-2"
    assert paths == [GET_TOKEN_PATH, REFRESH_TOKEN_PATH, GET_TOKEN_PATH]


def test_provider_retry_is_bounded_by_total_attempts() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del request
        calls += 1
        return httpx.Response(200, json={"code": 3001008, "message": "busy"})

    settings = _settings(LINGXING_TOKEN_MAX_ATTEMPTS=2)
    client = LingxingTokenClient(settings, transport=httpx.MockTransport(handler))
    manager = LingxingTokenManager(client, settings, sleeper=lambda _: None)
    try:
        with pytest.raises(LingxingTokenError) as error:
            manager.get_access_token()
    finally:
        client.close()

    assert error.value.category == "TOKEN_PROVIDER_ERROR"
    assert error.value.provider_code == 3001008
    assert calls == 2


def test_disabled_gate_stops_before_transport() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del request
        calls += 1
        return _success()

    client = LingxingTokenClient(
        _settings(LINGXING_ENABLE_TOKEN_REQUESTS=False),
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(LingxingTokenError, match="TOKEN_REQUESTS_DISABLED"):
            client.get_token()
    finally:
        client.close()

    assert calls == 0


def test_repr_and_errors_do_not_expose_synthetic_credentials() -> None:
    markers = {
        "app-secret-fixture",
        "access-token-fixture-1",
        "refresh-token-fixture-1",
    }
    settings = _settings()
    client = LingxingTokenClient(
        settings,
        transport=httpx.MockTransport(lambda _: _success()),
    )
    manager = LingxingTokenManager(client, settings, clock=lambda: NOW)
    try:
        manager.get_access_token()
    finally:
        client.close()

    snapshot = manager._snapshot
    assert snapshot is not None
    output = " ".join((repr(settings), repr(snapshot), repr(manager)))
    assert all(marker not in output for marker in markers)

    error_client = LingxingTokenClient(
        settings,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={"code": 2001002, "message": "app-secret-fixture"},
            )
        ),
    )
    try:
        with pytest.raises(LingxingTokenError) as error:
            error_client.get_token()
    finally:
        error_client.close()

    assert all(marker not in str(error.value) for marker in markers)


def test_concurrent_requests_share_one_token_request() -> None:
    entered = Event()
    release = Event()
    current_time = [NOW]
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == GET_TOKEN_PATH:
            return _success(expires_in=1_000)
        entered.set()
        assert release.wait(timeout=2)
        return _success(
            access_token="access-token-fixture-2",
            refresh_token="refresh-token-fixture-2",
        )

    settings = _settings()
    client = LingxingTokenClient(settings, transport=httpx.MockTransport(handler))
    manager = LingxingTokenManager(client, settings, clock=lambda: current_time[0])
    try:
        manager.get_access_token()
        current_time[0] = NOW + timedelta(seconds=500)
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(manager.get_access_token) for _ in range(5)]
            assert entered.wait(timeout=2)
            release.set()
            tokens = [future.result(timeout=2).get_secret_value() for future in futures]
    finally:
        client.close()

    assert tokens == ["access-token-fixture-2"] * 5
    assert paths == [GET_TOKEN_PATH, REFRESH_TOKEN_PATH]

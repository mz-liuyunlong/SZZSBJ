"""Reusable Lingxing business-API transport with official query-sign authentication."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast

import httpx
from pydantic import JsonValue, SecretStr

from app.core.config import Settings
from app.integrations.lingxing.official_contract_overrides import official_http_method
from app.integrations.lingxing.openapi import (
    LingxingOpenApiError,
    LingxingOpenApiRequest,
)
from app.integrations.lingxing.query_sign import (
    LingxingQuerySignError,
    build_query_auth_params,
    canonical_value,
)


class LingxingBusinessTokenProvider(Protocol):
    def get_access_token(self) -> SecretStr: ...

    def recover_from_access_error(self, provider_code: int | str) -> SecretStr: ...


def _provider_code(payload: JsonValue) -> int | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("code")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _query_business_params(parameters: Mapping[str, JsonValue]) -> dict[str, str]:
    """Encode GET business parameters exactly once so sent values match signing values."""

    return {
        key: canonical_value(value)
        for key, value in parameters.items()
        if value != ""
    }


class LingxingBusinessApiExecutor:
    """Execute approved Lingxing business requests using the official common auth contract.

    Security and authorization remain owned by ``LingxingOpenApiClient``. This class is only
    the transport adapter injected into that default-deny client. It never logs credentials,
    request values, response bodies, or signatures.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        token_provider: LingxingBusinessTokenProvider,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if settings.lingxing_base_url is None or not settings.lingxing_app_id:
            raise LingxingOpenApiError(
                "LINGXING_BUSINESS_API_CONFIG_UNAVAILABLE",
                "Lingxing business API configuration is unavailable",
            )
        self._settings = settings
        self._token_provider = token_provider
        self._client = httpx.Client(
            base_url=settings.lingxing_base_url,
            timeout=settings.lingxing_timeout_ms / 1_000,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __call__(self, request: LingxingOpenApiRequest) -> JsonValue:
        if not self._settings.lingxing_enable_real_calls:
            raise LingxingOpenApiError(
                "LINGXING_OPENAPI_OUTBOUND_NOT_AUTHORIZED",
                "Lingxing interface execution is not authorized",
            )

        token = self._safe_token()
        recovered = False
        for _ in range(2):
            payload = self._send(request, token)
            if _provider_code(payload) != 2001003:
                return payload
            if recovered:
                return payload
            try:
                token = self._token_provider.recover_from_access_error(2001003)
            except Exception as exc:
                raise LingxingOpenApiError(
                    "LINGXING_BUSINESS_API_AUTH_UNAVAILABLE",
                    "Lingxing authorization recovery is unavailable",
                ) from exc
            recovered = True
        raise AssertionError("unreachable")

    def _safe_token(self) -> SecretStr:
        try:
            return self._token_provider.get_access_token()
        except Exception as exc:
            raise LingxingOpenApiError(
                "LINGXING_BUSINESS_API_AUTH_UNAVAILABLE",
                "Lingxing authorization is unavailable",
            ) from exc

    def _send(self, request: LingxingOpenApiRequest, access_token: SecretStr) -> JsonValue:
        method = official_http_method(request.interface_id, request.method)
        if method not in {"GET", "POST"}:
            raise LingxingOpenApiError(
                "LINGXING_BUSINESS_API_METHOD_UNSUPPORTED",
                "Lingxing business API method is not supported by the verified transport",
            )

        business_params = cast(dict[str, JsonValue], dict(request.parameters))
        try:
            auth_params = build_query_auth_params(
                business_params,
                access_token=access_token,
                app_id=cast(str, self._settings.lingxing_app_id),
            )
        except LingxingQuerySignError as exc:
            raise LingxingOpenApiError(
                "LINGXING_BUSINESS_API_SIGN_UNAVAILABLE",
                "Lingxing query-sign authentication is unavailable",
            ) from exc

        query_params: dict[str, str] = dict(auth_params)
        json_body: JsonValue | None = None
        if method == "GET":
            query_params.update(_query_business_params(business_params))
        else:
            json_body = cast(JsonValue, business_params)

        headers = {"Accept": "application/json"}
        if method == "POST":
            headers["Content-Type"] = "application/json"

        try:
            response = self._client.request(
                method,
                request.api_path,
                headers=headers,
                params=query_params,
                json=json_body,
            )
        except httpx.HTTPError as exc:
            raise LingxingOpenApiError(
                "LINGXING_BUSINESS_API_TRANSPORT_ERROR",
                "Lingxing transport request failed",
            ) from exc

        if len(response.content) > self._settings.lingxing_max_response_bytes:
            raise LingxingOpenApiError(
                "LINGXING_BUSINESS_API_RESPONSE_TOO_LARGE",
                "Lingxing response exceeded the configured byte limit",
            )
        try:
            payload = cast(JsonValue, response.json())
        except ValueError as exc:
            raise LingxingOpenApiError(
                "LINGXING_BUSINESS_API_INVALID_JSON",
                "Lingxing response was not valid JSON",
            ) from exc
        if not response.is_success:
            raise LingxingOpenApiError(
                "LINGXING_BUSINESS_API_HTTP_ERROR",
                "Lingxing HTTP request failed",
            )
        return payload

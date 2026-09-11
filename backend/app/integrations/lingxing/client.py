from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from time import sleep
from typing import Literal, Protocol, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr, field_validator

from app.core.config import Settings
from app.integrations.lingxing.query_sign import LingxingQuerySignError, build_query_auth_params
from app.integrations.lingxing.security import redact_json

type LingxingEndpoint = Literal[
    "/basicOpen/multiplatform/walmart/list",
    "/basicOpen/platformStatisticsV2/saleStat/pageList",
    "/erp/sc/routing/data/local_inventory/batchGetProductInfo",
    "/pb/mp/shop/v2/getSellerList",
    "/basicOpen/multiplatform/profit/report/order",
    "/erp/sc/routing/data/local_inventory/productList",
]
type QueryValue = str | int | float | bool | None
type SuccessEvaluator = Callable[[LingxingEndpoint, httpx.Response, JsonValue], bool]
type AuthStrategy = Literal["authorization_header", "query_sign"]

MAX_ATTEMPTS = 2
RETRY_BACKOFF_SECONDS = 0.05


class LingxingClientError(RuntimeError):
    """Safe integration error that does not expose request details."""


class LingxingAccessTokenProvider(Protocol):
    def get_access_token(self) -> SecretStr: ...

    def recover_from_access_error(self, provider_code: int | str) -> SecretStr: ...


@dataclass(frozen=True)
class LingxingEndpointContract:
    method: Literal["POST"]
    outbound_enabled: bool
    allow_query_parameters: bool
    require_json_body: bool
    allowed_body_fields: frozenset[str]
    required_body_fields: frozenset[str]
    store_field: str | None
    page_size_field: str | None
    page_field: str | None = None
    offset_field: str | None = None
    rejection_reason: str | None = None
    auth_strategy: AuthStrategy = "authorization_header"


_ENDPOINT_CONTRACTS: dict[LingxingEndpoint, LingxingEndpointContract] = {
    "/basicOpen/multiplatform/walmart/list": LingxingEndpointContract(
        method="POST",
        outbound_enabled=True,
        allow_query_parameters=False,
        require_json_body=True,
        allowed_body_fields=frozenset({"offset", "length", "store_ids"}),
        required_body_fields=frozenset({"offset", "length", "store_ids"}),
        store_field="store_ids",
        page_size_field="length",
        offset_field="offset",
    ),
    "/basicOpen/platformStatisticsV2/saleStat/pageList": LingxingEndpointContract(
        method="POST",
        outbound_enabled=True,
        allow_query_parameters=False,
        require_json_body=True,
        allowed_body_fields=frozenset({"page", "length", "sids"}),
        required_body_fields=frozenset({"page", "length", "sids"}),
        store_field="sids",
        page_size_field="length",
        page_field="page",
    ),
    "/basicOpen/multiplatform/profit/report/order": LingxingEndpointContract(
        method="POST",
        outbound_enabled=True,
        allow_query_parameters=False,
        require_json_body=True,
        allowed_body_fields=frozenset({"offset", "length", "sids"}),
        required_body_fields=frozenset({"offset", "length", "sids"}),
        store_field="sids",
        page_size_field="length",
        offset_field="offset",
    ),
    "/pb/mp/shop/v2/getSellerList": LingxingEndpointContract(
        method="POST",
        outbound_enabled=False,
        allow_query_parameters=False,
        require_json_body=True,
        allowed_body_fields=frozenset(),
        required_body_fields=frozenset(),
        store_field=None,
        page_size_field=None,
        rejection_reason="pending_store_scope: endpoint outbound is disabled",
    ),
    "/erp/sc/routing/data/local_inventory/batchGetProductInfo": LingxingEndpointContract(
        method="POST",
        outbound_enabled=False,
        allow_query_parameters=False,
        require_json_body=True,
        allowed_body_fields=frozenset(),
        required_body_fields=frozenset(),
        store_field=None,
        page_size_field=None,
        rejection_reason="pending_endpoint_contract: endpoint outbound is disabled",
    ),
    "/erp/sc/routing/data/local_inventory/productList": LingxingEndpointContract(
        method="POST",
        outbound_enabled=True,
        allow_query_parameters=False,
        require_json_body=True,
        allowed_body_fields=frozenset({"offset", "length"}),
        required_body_fields=frozenset(),
        store_field=None,
        page_size_field="length",
        offset_field="offset",
        auth_strategy="query_sign",
    ),
}


def _required_integer(value: JsonValue, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise LingxingClientError("Lingxing outbound pagination scope is invalid")
    return value


def _required_store_ids(value: JsonValue) -> set[str]:
    if not isinstance(value, list) or not value:
        raise LingxingClientError("Lingxing outbound store scope is invalid")
    stores: set[str] = set()
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (str, int)):
            raise LingxingClientError("Lingxing outbound store scope is invalid")
        normalized = str(item).strip()
        if not normalized:
            raise LingxingClientError("Lingxing outbound store scope is invalid")
        stores.add(normalized)
    return stores


def _provider_code(value: JsonValue) -> int | None:
    if not isinstance(value, dict):
        return None
    code = value.get("code")
    if isinstance(code, bool):
        return None
    if isinstance(code, int):
        return code
    if isinstance(code, str):
        try:
            return int(code.strip())
        except ValueError:
            return None
    return None


class LingxingPageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    page_no: int = Field(ge=1)
    page_size: int = Field(ge=1, le=3)
    params: dict[str, QueryValue] | None = None
    body: JsonValue = None


class LingxingCaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    api_path: LingxingEndpoint
    pages: tuple[LingxingPageRequest, ...] = Field(min_length=1, max_length=1)
    store_ids: tuple[str, ...] = Field(min_length=1)
    object_type: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=255)
    run_id: str = Field(min_length=1, max_length=255)
    batch_id: str = Field(min_length=1, max_length=255)
    data_date: date | None = None
    store_name: str | None = Field(default=None, max_length=255)
    extra: JsonValue = None

    @field_validator("store_ids")
    @classmethod
    def validate_store_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(store_id.strip() for store_id in value)
        if any(not store_id for store_id in normalized) or len(set(normalized)) != len(normalized):
            raise ValueError("store_ids must be nonblank and unique")
        return normalized


class LingxingRawEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    api_path: LingxingEndpoint
    request_method: Literal["POST"] = "POST"
    request_params_json: JsonValue = None
    request_body_json: JsonValue = None
    response_json: JsonValue = None
    response_code: int | None = None
    is_success: bool
    error_code: str | None = None
    error_message: str | None = None
    data_date: date | None = None
    pulled_at: datetime
    page_no: int = Field(ge=1)
    page_size: int = Field(ge=1, le=3)
    store_id: str | None = Field(default=None, min_length=1)
    store_name: str | None = Field(default=None, min_length=1, max_length=255)
    object_type: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=255)
    run_id: str = Field(min_length=1, max_length=255)
    batch_id: str = Field(min_length=1, max_length=255)
    attempt_no: int = Field(ge=1)
    extra_json: JsonValue = None


class LingxingReadonlyClient:
    def __init__(
        self,
        settings: Settings,
        *,
        token_provider: LingxingAccessTokenProvider,
        success_evaluator: SuccessEvaluator,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if settings.lingxing_base_url is None:
            raise LingxingClientError("Lingxing client configuration is unavailable")
        self._settings = settings
        self._token_provider = token_provider
        self._success_evaluator = success_evaluator
        self._sleeper = sleeper
        self._client = httpx.Client(
            base_url=settings.lingxing_base_url,
            timeout=settings.lingxing_timeout_ms / 1_000,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def fetch_pages(self, request: LingxingCaptureRequest) -> list[LingxingRawEnvelope]:
        if not self._settings.lingxing_enable_real_calls:
            raise LingxingClientError("Lingxing calls are disabled")
        contract = _ENDPOINT_CONTRACTS.get(request.api_path)
        if contract is None:
            raise LingxingClientError("Lingxing endpoint is not approved")
        if not contract.outbound_enabled:
            raise LingxingClientError(contract.rejection_reason or "Lingxing endpoint is disabled")
        if not request.store_ids:
            raise LingxingClientError("Lingxing store allowlist is required")
        if len(request.pages) != 1 or len(request.pages) > self._settings.lingxing_max_sample_pages:
            raise LingxingClientError("Lingxing page limit exceeded")
        if any(page.page_size > self._settings.lingxing_sample_page_size for page in request.pages):
            raise LingxingClientError("Lingxing page size limit exceeded")
        # DRY_RUN controls RAW persistence only; outbound HTTP remains gated here.
        for page in request.pages:
            self._validate_outbound_contract(request, page, contract)
        return [self._fetch_page(request, page, contract) for page in request.pages]

    def _validate_outbound_contract(
        self,
        capture: LingxingCaptureRequest,
        page: LingxingPageRequest,
        contract: LingxingEndpointContract,
    ) -> None:
        if page.params and not contract.allow_query_parameters:
            raise LingxingClientError("Lingxing endpoint does not allow query parameters")
        body = page.body
        if not contract.require_json_body or not isinstance(body, dict):
            raise LingxingClientError("Lingxing endpoint requires a JSON object body")
        body_fields = frozenset(body)
        if not contract.required_body_fields.issubset(body_fields):
            raise LingxingClientError("Lingxing outbound body does not match endpoint contract")
        if not body_fields.issubset(contract.allowed_body_fields):
            raise LingxingClientError("Lingxing outbound body does not match endpoint contract")

        if contract.store_field is not None:
            stores = _required_store_ids(body[contract.store_field])
            if not stores.issubset(set(capture.store_ids)):
                raise LingxingClientError(
                    "Lingxing outbound store scope is missing or unauthorized"
                )
        if contract.page_size_field is not None and contract.page_size_field in body:
            length = _required_integer(body[contract.page_size_field], minimum=1)
            if length != page.page_size or length > self._settings.lingxing_sample_page_size:
                raise LingxingClientError("Lingxing outbound page size is missing or inconsistent")
        if page.page_no != 1:
            raise LingxingClientError("Lingxing outbound page number is inconsistent")
        if contract.page_field is not None:
            if _required_integer(body[contract.page_field], minimum=1) != 1:
                raise LingxingClientError("Lingxing outbound page number is inconsistent")
        if contract.offset_field is not None and contract.offset_field in body:
            _required_integer(body[contract.offset_field], minimum=0)
        if contract.auth_strategy == "query_sign" and not self._settings.lingxing_app_id:
            raise LingxingClientError("Lingxing query-sign configuration is unavailable")

    def _fetch_page(
        self,
        capture: LingxingCaptureRequest,
        page: LingxingPageRequest,
        contract: LingxingEndpointContract,
    ) -> LingxingRawEnvelope:
        last_status: int | None = None
        response_json: JsonValue = None
        next_access_token: SecretStr | None = None
        recovery_attempted = False
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                access_token = next_access_token or self._token_provider.get_access_token()
                next_access_token = None
            except Exception:
                return self._envelope(
                    capture,
                    page,
                    attempt=attempt,
                    response_code=last_status,
                    response_json=response_json,
                    error_code="AUTH_ERROR",
                    error_message="Lingxing authorization is unavailable",
                )
            try:
                headers: dict[str, str]
                query_params: dict[str, str] | None = None
                if contract.auth_strategy == "query_sign":
                    if not self._settings.lingxing_app_id:
                        raise LingxingClientError(
                            "Lingxing query-sign configuration is unavailable"
                        )
                    headers = {"Accept": "application/json"}
                    query_params = build_query_auth_params(
                        cast(dict[str, JsonValue], page.body),
                        access_token=access_token,
                        app_id=self._settings.lingxing_app_id,
                    )
                else:
                    headers = {"Authorization": access_token.get_secret_value()}
                outbound = self._client.build_request(
                    contract.method,
                    capture.api_path,
                    headers=headers,
                    params=query_params,
                    json=page.body,
                )
                response = self._client.send(outbound)
                last_status = response.status_code
                if len(response.content) > self._settings.lingxing_max_response_bytes:
                    return self._envelope(
                        capture,
                        page,
                        attempt=attempt,
                        response_code=last_status,
                        response_json=None,
                        error_code="RESPONSE_TOO_LARGE",
                        error_message="Lingxing response exceeded configured byte limit",
                    )
                try:
                    response_json = cast(JsonValue, response.json())
                except ValueError:
                    return self._envelope(
                        capture,
                        page,
                        attempt=attempt,
                        response_code=last_status,
                        response_json=None,
                        error_code="INVALID_JSON",
                        error_message="Lingxing response was not valid JSON",
                    )
                if response.status_code >= 500 and attempt < MAX_ATTEMPTS:
                    self._sleeper(RETRY_BACKOFF_SECONDS * attempt)
                    continue
                if not response.is_success:
                    return self._envelope(
                        capture,
                        page,
                        attempt=attempt,
                        response_code=last_status,
                        response_json=response_json,
                        error_code="HTTP_ERROR",
                        error_message="Lingxing HTTP request failed",
                    )
                provider_code = _provider_code(response_json)
                if provider_code == 2001003:
                    if recovery_attempted or attempt >= MAX_ATTEMPTS:
                        return self._envelope(
                            capture,
                            page,
                            attempt=attempt,
                            response_code=last_status,
                            response_json=response_json,
                            error_code="PROVIDER_ERROR",
                            error_message="Lingxing provider reported failure",
                        )
                    try:
                        next_access_token = self._token_provider.recover_from_access_error(
                            provider_code
                        )
                    except Exception:
                        return self._envelope(
                            capture,
                            page,
                            attempt=attempt,
                            response_code=last_status,
                            response_json=response_json,
                            error_code="AUTH_ERROR",
                            error_message="Lingxing authorization recovery failed",
                        )
                    recovery_attempted = True
                    continue
                try:
                    provider_succeeded = self._success_evaluator(
                        capture.api_path,
                        response,
                        response_json,
                    )
                except Exception:
                    provider_succeeded = False
                if not provider_succeeded:
                    return self._envelope(
                        capture,
                        page,
                        attempt=attempt,
                        response_code=last_status,
                        response_json=response_json,
                        error_code="PROVIDER_ERROR",
                        error_message="Lingxing provider reported failure",
                    )
                return self._envelope(
                    capture,
                    page,
                    attempt=attempt,
                    response_code=last_status,
                    response_json=response_json,
                )
            except (LingxingClientError, LingxingQuerySignError):
                return self._envelope(
                    capture,
                    page,
                    attempt=attempt,
                    response_code=last_status,
                    response_json=response_json,
                    error_code="AUTH_ERROR",
                    error_message="Lingxing query-sign authentication is unavailable",
                )
            except httpx.HTTPError:
                if attempt < MAX_ATTEMPTS:
                    self._sleeper(RETRY_BACKOFF_SECONDS * attempt)
                    continue
        return self._envelope(
            capture,
            page,
            attempt=MAX_ATTEMPTS,
            response_code=last_status,
            response_json=response_json,
            error_code="TRANSPORT_ERROR",
            error_message="Lingxing transport request failed",
        )

    @staticmethod
    def _envelope(
        capture: LingxingCaptureRequest,
        page: LingxingPageRequest,
        *,
        attempt: int,
        response_code: int | None,
        response_json: JsonValue,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> LingxingRawEnvelope:
        return LingxingRawEnvelope(
            api_path=capture.api_path,
            request_params_json=redact_json(cast(JsonValue, page.params)),
            request_body_json=redact_json(page.body),
            response_json=redact_json(response_json),
            response_code=response_code,
            is_success=error_code is None,
            error_code=error_code,
            error_message=error_message,
            data_date=capture.data_date,
            pulled_at=datetime.now(UTC),
            page_no=page.page_no,
            page_size=page.page_size,
            store_id=capture.store_ids[0] if len(capture.store_ids) == 1 else None,
            store_name=capture.store_name,
            object_type=capture.object_type,
            trace_id=capture.trace_id,
            run_id=capture.run_id,
            batch_id=capture.batch_id,
            attempt_no=attempt,
            extra_json=redact_json(capture.extra),
        )

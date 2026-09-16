"""Declarative Lingxing OpenAPI registry and default-deny callable stubs."""

from __future__ import annotations

import csv
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Literal, cast

from pydantic import JsonValue

from app.integrations.lingxing.official_contract_overrides import official_http_method

type HttpMethod = Literal["GET", "POST", "DELETE"]
type LingxingOpenApiExecutor = Callable[["LingxingOpenApiRequest"], JsonValue]

EXPECTED_INTERFACE_COUNT = 329
REGISTRY_PATH = Path(__file__).with_name("data") / "official_verified_interfaces.csv"


class LingxingOpenApiError(RuntimeError):
    """Safe error with a stable public code and no request values."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class LingxingOpenApiContract:
    interface_id: str
    verification_status: Literal["OFFICIAL_VERIFIED"]
    level_1_module: str
    level_2_module: str
    level_3_module: str
    interface_name: str
    method: HttpMethod
    api_path: str
    purpose: str
    token_bucket_capacity: int
    is_read: bool
    is_write: bool
    has_side_effect: bool
    pagination_method: str
    max_page_size_or_length: int | None
    returns_total: bool
    supports_incremental_sync: bool
    incremental_time_fields: tuple[str, ...]
    max_query_range: str
    recommended_sync_strategy: str
    request_param_count: int
    request_fields: tuple[str, ...]
    response_field_count: int
    response_top_fields: tuple[str, ...]
    directory_chain: str
    system_modules: tuple[str, ...]
    document_path: str

    @property
    def requires_owner_authorization(self) -> bool:
        return not self.is_read or self.is_write or self.has_side_effect or self.method == "DELETE"


@dataclass(frozen=True, slots=True)
class LingxingOpenApiRequest:
    interface_id: str
    method: HttpMethod
    api_path: str
    parameters: Mapping[str, JsonValue] = field(repr=False)


@dataclass(frozen=True, slots=True)
class LingxingOpenApiDryRun:
    interface_id: str
    method: HttpMethod
    api_path: str
    parameter_fields: tuple[str, ...]
    dry_run: Literal[True] = True
    outbound_attempted: Literal[False] = False


def _bool(value: str, *, field_name: str) -> bool:
    if value == "是":
        return True
    if value == "否":
        return False
    raise LingxingOpenApiError(
        "LINGXING_OPENAPI_REGISTRY_INVALID",
        f"Lingxing registry has an invalid {field_name} value",
    )


def _fields(value: str) -> tuple[str, ...]:
    return tuple(
        field_name
        for field_name in (item.strip() for item in value.split(","))
        if field_name and not field_name.startswith("...(+")
    )


def _optional_positive_int(value: str, *, field_name: str) -> int | None:
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise LingxingOpenApiError(
            "LINGXING_OPENAPI_REGISTRY_INVALID",
            f"Lingxing registry has an invalid {field_name} value",
        ) from exc
    if parsed < 1:
        raise LingxingOpenApiError(
            "LINGXING_OPENAPI_REGISTRY_INVALID",
            f"Lingxing registry has an invalid {field_name} value",
        )
    return parsed


def _nonnegative_int(value: str, *, field_name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise LingxingOpenApiError(
            "LINGXING_OPENAPI_REGISTRY_INVALID",
            f"Lingxing registry has an invalid {field_name} value",
        ) from exc
    if parsed < 0:
        raise LingxingOpenApiError(
            "LINGXING_OPENAPI_REGISTRY_INVALID",
            f"Lingxing registry has an invalid {field_name} value",
        )
    return parsed


def _contract(row: Mapping[str, str]) -> LingxingOpenApiContract:
    method = row["http_method"]
    if method not in {"GET", "POST", "DELETE"}:
        raise LingxingOpenApiError(
            "LINGXING_OPENAPI_REGISTRY_INVALID",
            "Lingxing registry has an invalid HTTP method",
        )
    if row["verification_status"] != "OFFICIAL_VERIFIED":
        raise LingxingOpenApiError(
            "LINGXING_OPENAPI_REGISTRY_INVALID",
            "Lingxing registry contains an unverified interface",
        )
    if row["page_interface_included"].lower() != "false":
        raise LingxingOpenApiError(
            "LINGXING_OPENAPI_REGISTRY_INVALID",
            "Lingxing registry contains a page interface",
        )
    api_path = row["api_path"]
    if not api_path.startswith("/"):
        raise LingxingOpenApiError(
            "LINGXING_OPENAPI_REGISTRY_INVALID",
            "Lingxing registry contains an invalid API path",
        )
    token_bucket_capacity = _optional_positive_int(
        row["token_bucket_capacity"], field_name="token_bucket_capacity"
    )
    if token_bucket_capacity is None:
        raise LingxingOpenApiError(
            "LINGXING_OPENAPI_REGISTRY_INVALID",
            "Lingxing registry is missing token_bucket_capacity",
        )
    verified_method = official_http_method(row["interface_id"], cast(HttpMethod, method))
    return LingxingOpenApiContract(
        interface_id=row["interface_id"],
        verification_status="OFFICIAL_VERIFIED",
        level_1_module=row["level_1_module"],
        level_2_module=row["level_2_module"],
        level_3_module=row["level_3_module"],
        interface_name=row["interface_name"],
        method=verified_method,
        api_path=api_path,
        purpose=row["purpose"],
        token_bucket_capacity=token_bucket_capacity,
        is_read=_bool(row["is_read"], field_name="is_read"),
        is_write=_bool(row["is_write"], field_name="is_write"),
        has_side_effect=_bool(row["has_side_effect"], field_name="has_side_effect"),
        pagination_method=row["pagination_method"],
        max_page_size_or_length=_optional_positive_int(
            row["max_page_size_or_length"], field_name="max_page_size_or_length"
        ),
        returns_total=_bool(row["returns_total"], field_name="returns_total"),
        supports_incremental_sync=_bool(
            row["supports_incremental_sync"], field_name="supports_incremental_sync"
        ),
        incremental_time_fields=_fields(row["incremental_time_fields"]),
        max_query_range=row["max_query_range"],
        recommended_sync_strategy=row["recommended_sync_strategy"],
        request_param_count=_nonnegative_int(
            row["request_param_count"], field_name="request_param_count"
        ),
        request_fields=_fields(row["request_fields"]),
        response_field_count=_nonnegative_int(
            row["response_field_count"], field_name="response_field_count"
        ),
        response_top_fields=_fields(row["response_top_fields"]),
        directory_chain=row["directory_chain"],
        system_modules=_fields(row["system_modules"]),
        document_path=row["document_path"],
    )


@lru_cache(maxsize=1)
def lingxing_openapi_registry() -> Mapping[str, LingxingOpenApiContract]:
    with REGISTRY_PATH.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        contracts = [_contract(row) for row in reader]

    by_id = {contract.interface_id: contract for contract in contracts}
    method_paths = {(contract.method, contract.api_path) for contract in contracts}
    if (
        len(contracts) != EXPECTED_INTERFACE_COUNT
        or len(by_id) != EXPECTED_INTERFACE_COUNT
        or len(method_paths) != EXPECTED_INTERFACE_COUNT
    ):
        raise LingxingOpenApiError(
            "LINGXING_OPENAPI_REGISTRY_INVALID",
            "Lingxing registry interface count or uniqueness is invalid",
        )
    return MappingProxyType(by_id)


class LingxingOpenApiClient:
    """Builds all verified requests but executes only explicitly enabled interfaces."""

    def __init__(
        self,
        *,
        executor: LingxingOpenApiExecutor | None = None,
        enabled_interface_ids: frozenset[str] = frozenset(),
        owner_authorized_interface_ids: frozenset[str] = frozenset(),
    ) -> None:
        self._registry = lingxing_openapi_registry()
        self._executor = executor
        self._enabled_interface_ids = enabled_interface_ids
        self._owner_authorized_interface_ids = owner_authorized_interface_ids

    @property
    def registry(self) -> Mapping[str, LingxingOpenApiContract]:
        return self._registry

    def build_request(
        self,
        interface_id: str,
        parameters: Mapping[str, JsonValue] | None = None,
    ) -> LingxingOpenApiRequest:
        contract = self._registry.get(interface_id)
        if contract is None:
            raise LingxingOpenApiError(
                "LINGXING_OPENAPI_INTERFACE_UNKNOWN",
                "Lingxing interface is not registered",
            )
        copied = dict(parameters or {})
        if set(copied) - set(contract.request_fields):
            raise LingxingOpenApiError(
                "CONTRACT_FIELD_MISMATCH",
                "Lingxing request contains fields outside the verified contract",
            )
        return LingxingOpenApiRequest(
            interface_id=contract.interface_id,
            method=contract.method,
            api_path=contract.api_path,
            parameters=MappingProxyType(copied),
        )

    def call(
        self,
        interface_id: str,
        parameters: Mapping[str, JsonValue] | None = None,
        *,
        dry_run: bool = True,
    ) -> JsonValue | LingxingOpenApiDryRun:
        request = self.build_request(interface_id, parameters)
        if dry_run:
            return LingxingOpenApiDryRun(
                interface_id=request.interface_id,
                method=request.method,
                api_path=request.api_path,
                parameter_fields=tuple(sorted(request.parameters)),
            )
        if interface_id not in self._enabled_interface_ids or self._executor is None:
            raise LingxingOpenApiError(
                "LINGXING_OPENAPI_OUTBOUND_NOT_AUTHORIZED",
                "Lingxing interface execution is not authorized",
            )
        contract = self._registry[interface_id]
        if (
            contract.requires_owner_authorization
            and interface_id not in self._owner_authorized_interface_ids
        ):
            raise LingxingOpenApiError(
                "LINGXING_OPENAPI_OWNER_AUTHORIZATION_REQUIRED",
                "Lingxing side-effect interface requires separate Owner authorization",
            )
        return self._executor(request)

    def stub(self, interface_id: str) -> LingxingOpenApiStub:
        if interface_id not in self._registry:
            raise LingxingOpenApiError(
                "LINGXING_OPENAPI_INTERFACE_UNKNOWN",
                "Lingxing interface is not registered",
            )
        return LingxingOpenApiStub(client=self, interface_id=interface_id)

    def stubs(self) -> tuple[LingxingOpenApiStub, ...]:
        return tuple(self.stub(interface_id) for interface_id in self._registry)


@dataclass(frozen=True, slots=True)
class LingxingOpenApiStub:
    client: LingxingOpenApiClient = field(repr=False)
    interface_id: str

    def __call__(
        self,
        parameters: Mapping[str, JsonValue] | None = None,
        *,
        dry_run: bool = True,
    ) -> JsonValue | LingxingOpenApiDryRun:
        return self.client.call(self.interface_id, parameters, dry_run=dry_run)

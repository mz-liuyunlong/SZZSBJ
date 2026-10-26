"""Offline OpenAPI contract importer and strict request builder.

Owner-supplied OpenAPI 3.x snapshots can describe many Walmart endpoints
without writing per-endpoint HTTP code. Import does not enable a real API:
the owner-controlled executor must separately authorize method and scope.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})
_PATH = re.compile(r"^/v3(?:/[a-zA-Z0-9_{}.-]+)+$")
_VAR = re.compile(r"\{([a-zA-Z][a-zA-Z0-9_]*)\}")
_IDENTIFIER = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{1,127}$")
_RESTRICTED = frozenset({"authorization", "wm_sec.access_token", "host", "cookie"})


class ContractError(ValueError):
    """Stable non-secret failure codes."""


@dataclass(frozen=True, slots=True)
class Field:
    name: str
    location: str
    required: bool = False
    kind: str = "string"
    enum: tuple[str, ...] = ()
    maximum: int | None = None


@dataclass(frozen=True, slots=True)
class Operation:
    key: str
    method: str
    path: str
    fields: tuple[Field, ...]
    has_body: bool = False
    source: str = "unverified"
    enabled: bool = False

    @property
    def is_write(self) -> bool:
        return self.method != "GET"


@dataclass(frozen=True, slots=True)
class PreparedRequest:
    key: str
    method: str
    path: str
    query: Mapping[str, str | int | bool]
    body: Any
    is_write: bool


def _path_valid(path: str) -> bool:
    return bool(_PATH.fullmatch(path) and ".." not in path and "//" not in path)


def _type_check(field: Field, value: Any) -> str | int | bool:
    if field.kind == "integer":
        if type(value) is not int or value < 0:
            raise ContractError("WALMART_FIELD_INVALID")
        if field.maximum is not None and value > field.maximum:
            raise ContractError("WALMART_FIELD_INVALID")
        return value
    if field.kind == "boolean":
        if type(value) is not bool:
            raise ContractError("WALMART_FIELD_INVALID")
        return value
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise ContractError("WALMART_FIELD_INVALID")
    if any(ord(char) < 32 for char in value):
        raise ContractError("WALMART_FIELD_INVALID")
    if field.enum and value not in field.enum:
        raise ContractError("WALMART_FIELD_INVALID")
    return value


class ContractRegistry:
    def __init__(self, operations: tuple[Operation, ...]) -> None:
        self._operations: dict[str, Operation] = {}
        for operation in operations:
            if (
                not _IDENTIFIER.fullmatch(operation.key)
                or operation.method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}
                or not _path_valid(operation.path)
                or operation.key in self._operations
            ):
                raise ContractError("WALMART_CONTRACT_INVALID")
            path_names = set(_VAR.findall(operation.path))
            declared = {field.name for field in operation.fields if field.location == "path"}
            if path_names != declared:
                raise ContractError("WALMART_CONTRACT_INVALID")
            if len(operation.fields) != len({(f.location, f.name) for f in operation.fields}):
                raise ContractError("WALMART_CONTRACT_INVALID")
            self._operations[operation.key] = operation

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._operations))

    def get(self, key: str) -> Operation:
        try:
            return self._operations[key]
        except KeyError:
            raise ContractError("WALMART_API_NOT_REGISTERED") from None

    def prepare(
        self,
        key: str,
        *,
        params: Mapping[str, Any] | None = None,
        body: Any = None,
        allow_writes: bool = False,
    ) -> PreparedRequest:
        operation = self.get(key)
        if not operation.enabled:
            raise ContractError("WALMART_OPERATION_NOT_APPROVED")
        if operation.is_write and not allow_writes:
            raise ContractError("WALMART_WRITE_NOT_AUTHORIZED")
        values = params if params is not None else {}
        if not isinstance(values, Mapping) or len(values) > 80:
            raise ContractError("WALMART_PARAMS_INVALID")
        known = {field.name: field for field in operation.fields}
        if any(name not in known or not isinstance(name, str) for name in values):
            raise ContractError("WALMART_PARAM_NOT_ALLOWED")
        if any(field.required and field.name not in values for field in operation.fields):
            raise ContractError("WALMART_PARAM_REQUIRED")
        if body is not None and not operation.has_body:
            raise ContractError("WALMART_BODY_NOT_ALLOWED")
        if operation.has_body and body is None:
            raise ContractError("WALMART_BODY_REQUIRED")
        if body is not None and (not isinstance(body, (dict, list)) or len(str(body)) > 2_000_000):
            raise ContractError("WALMART_BODY_INVALID")
        path = operation.path
        query: dict[str, str | int | bool] = {}
        for name, raw in values.items():
            field = known[name]
            value = _type_check(field, raw)
            if field.location == "path":
                path = path.replace("{" + name + "}", quote(str(value), safe=""))
            else:
                query[name] = value
        if _VAR.search(path) or not path.startswith("/v3/") or ".." in path or "//" in path:
            raise ContractError("WALMART_PATH_INVALID")
        return PreparedRequest(key, operation.method, path, query, body, operation.is_write)

    @classmethod
    def from_openapi(
        cls, document: Mapping[str, Any], *, approved_keys: frozenset[str] = frozenset()
    ) -> ContractRegistry:
        """Import operations from one reviewed spec; unknown ones remain disabled.

        A spec may be untrusted. It cannot set base hosts, auth headers, enabled
        status, or a method not in the allowlist. External $ref is rejected.
        """
        version = document.get("openapi", "")
        if not isinstance(version, str) or not version.startswith("3."):
            raise ContractError("WALMART_SPEC_VERSION_UNSUPPORTED")
        paths = document.get("paths")
        if not isinstance(paths, dict) or len(paths) > 3000:
            raise ContractError("WALMART_CONTRACT_INVALID")
        operations: list[Operation] = []
        for path, verbs in paths.items():
            if not isinstance(path, str) or not _path_valid(path) or not isinstance(verbs, dict):
                raise ContractError("WALMART_CONTRACT_INVALID")
            base_fields = verbs.get("parameters", [])
            for method, endpoint in verbs.items():
                if method not in _HTTP_METHODS:
                    continue
                if not isinstance(endpoint, dict):
                    raise ContractError("WALMART_CONTRACT_INVALID")
                key = endpoint.get("operationId")
                if not isinstance(key, str) or not _IDENTIFIER.fullmatch(key):
                    raise ContractError("WALMART_CONTRACT_INVALID")
                parameters = [*base_fields, *endpoint.get("parameters", [])]
                fields: list[Field] = []
                for param in parameters:
                    if not isinstance(param, dict) or "$ref" in param:
                        raise ContractError("WALMART_SPEC_REFERENCE_UNSUPPORTED")
                    name, place = param.get("name"), param.get("in")
                    if not isinstance(name, str) or place not in {"path", "query"}:
                        # Authentication and provider headers belong to the executor.
                        if place == "header" and isinstance(name, str):
                            continue
                        raise ContractError("WALMART_CONTRACT_INVALID")
                    if name.lower() in _RESTRICTED:
                        raise ContractError("WALMART_CONTRACT_INVALID")
                    schema = param.get("schema", {})
                    if not isinstance(schema, dict) or "$ref" in schema:
                        raise ContractError("WALMART_SPEC_REFERENCE_UNSUPPORTED")
                    kind = schema.get("type", "string")
                    if kind not in {"string", "integer", "boolean"}:
                        raise ContractError("WALMART_SCHEMA_UNSUPPORTED")
                    enum = schema.get("enum", [])
                    if not isinstance(enum, list):
                        raise ContractError("WALMART_CONTRACT_INVALID")
                    fields.append(
                        Field(
                            name=name,
                            location=place,
                            required=bool(param.get("required", False) or place == "path"),
                            kind=kind,
                            enum=tuple(str(x) for x in enum),
                            maximum=schema.get("maximum"),
                        )
                    )
                request_body = endpoint.get("requestBody")
                if request_body is not None and not isinstance(request_body, dict):
                    raise ContractError("WALMART_CONTRACT_INVALID")
                operations.append(
                    Operation(
                        key=key,
                        method=method.upper(),
                        path=path,
                        fields=tuple(fields),
                        has_body=request_body is not None,
                        source="imported-openapi-3",
                        enabled=key in approved_keys,
                    )
                )
        if approved_keys.difference({o.key for o in operations}):
            raise ContractError("WALMART_APPROVED_OPERATION_UNKNOWN")
        return cls(tuple(operations))

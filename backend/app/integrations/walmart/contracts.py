"""Strict OpenAPI 3.x contract registry for Walmart Marketplace operations.

Request preparation is offline. A protected executor must independently
authorize the caller, store, endpoint, and any write approval.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import quote

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})
_PATH = re.compile(r"^/v3(?:/[a-zA-Z0-9_{}.-]+)+$")
_VAR = re.compile(r"\{([a-zA-Z][a-zA-Z0-9_]*)\}")
_IDENTIFIER = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{1,127}$")
_RESTRICTED = frozenset({"authorization", "wm_sec.access_token", "host", "cookie"})
_SUPPORTED_BODY_TYPES = frozenset(
    {"application/json", "application/xml", "text/xml", "application/x-www-form-urlencoded"}
)


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
    schema: Mapping[str, Any] | None = None
    style: str = "form"
    explode: bool = True


@dataclass(frozen=True, slots=True)
class Operation:
    key: str
    method: str
    path: str
    fields: tuple[Field, ...]
    has_body: bool = False
    source: str = "unverified"
    enabled: bool = False
    request_schema: Mapping[str, Any] | None = None
    request_content_type: str = "application/json"
    body_required: bool = False
    media_supported: bool = True
    mutating: bool | None = None

    @property
    def is_write(self) -> bool:
        return self.method != "GET" if self.mutating is None else self.mutating


@dataclass(frozen=True, slots=True)
class PreparedRequest:
    key: str
    method: str
    path: str
    query: Mapping[str, Any]
    body: Any
    is_write: bool
    content_type: str = "application/json"


def _path_valid(path: str) -> bool:
    return bool(_PATH.fullmatch(path) and ".." not in path and "//" not in path)


def _resolve_local_refs(
    value: Any, document: Mapping[str, Any], stack: tuple[str, ...] = ()
) -> Any:
    """Resolve only local component references; reject external refs and cycles."""
    if isinstance(value, list):
        return [_resolve_local_refs(item, document, stack) for item in value]
    if not isinstance(value, dict):
        return value
    ref = value.get("$ref")
    if ref is not None:
        if not isinstance(ref, str) or not ref.startswith("#/components/") or ref in stack:
            raise ContractError("WALMART_SPEC_REFERENCE_UNSUPPORTED")
        current: Any = document
        try:
            for part in ref[2:].split("/"):
                current = current[part.replace("~1", "/").replace("~0", "~")]
        except (KeyError, TypeError):
            raise ContractError("WALMART_SPEC_REFERENCE_INVALID") from None
        if not isinstance(current, dict):
            raise ContractError("WALMART_SPEC_REFERENCE_INVALID")
        merged = dict(current)
        merged.update({key: child for key, child in value.items() if key != "$ref"})
        return _resolve_local_refs(merged, document, (*stack, ref))
    return {key: _resolve_local_refs(child, document, stack) for key, child in value.items()}


def _validate_schema(value: Any, schema: Mapping[str, Any], depth: int = 0) -> Any:
    if depth > 24:
        raise ContractError("WALMART_SCHEMA_DEPTH_EXCEEDED")
    if value is None:
        if schema.get("nullable") is True or schema.get("type") == "null":
            return None
        raise ContractError("WALMART_FIELD_INVALID")
    for part in schema.get("allOf", []):
        if not isinstance(part, dict):
            raise ContractError("WALMART_SCHEMA_INVALID")
        _validate_schema(value, part, depth + 1)
    for key in ("oneOf", "anyOf"):
        if key not in schema:
            continue
        choices = schema[key]
        if not isinstance(choices, list):
            raise ContractError("WALMART_SCHEMA_INVALID")
        valid = 0
        for choice in choices:
            try:
                if isinstance(choice, dict):
                    _validate_schema(value, choice, depth + 1)
                    valid += 1
            except ContractError:
                pass
        if valid == 0 or key == "oneOf" and valid != 1:
            raise ContractError("WALMART_FIELD_INVALID")
    kind = schema.get("type")
    if isinstance(kind, list):
        for option in kind:
            try:
                _validate_schema(value, {**schema, "type": option}, depth + 1)
                break
            except ContractError:
                continue
        else:
            raise ContractError("WALMART_FIELD_INVALID")
        return value
    if kind == "string":
        if not isinstance(value, str):
            raise ContractError("WALMART_FIELD_INVALID")
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get(
            "maxLength", 1_000_000
        ):
            raise ContractError("WALMART_FIELD_INVALID")
        if any(ord(char) < 32 for char in value):
            raise ContractError("WALMART_FIELD_INVALID")
        pattern = schema.get("pattern")
        if pattern is not None and (
            not isinstance(pattern, str) or len(pattern) > 512 or not re.search(pattern, value)
        ):
            raise ContractError("WALMART_FIELD_INVALID")
        try:
            if schema.get("format") == "date":
                date.fromisoformat(value)
            elif schema.get("format") == "date-time":
                datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ContractError("WALMART_FIELD_INVALID") from None
    elif kind == "integer":
        if type(value) is not int:
            raise ContractError("WALMART_FIELD_INVALID")
    elif kind == "number":
        if type(value) not in {int, float}:
            raise ContractError("WALMART_FIELD_INVALID")
    elif kind == "boolean":
        if type(value) is not bool:
            raise ContractError("WALMART_FIELD_INVALID")
    elif kind == "array":
        if not isinstance(value, list):
            raise ContractError("WALMART_FIELD_INVALID")
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 10000):
            raise ContractError("WALMART_FIELD_INVALID")
        item_schema = schema.get("items", {})
        if not isinstance(item_schema, dict):
            raise ContractError("WALMART_SCHEMA_INVALID")
        for item in value:
            _validate_schema(item, item_schema, depth + 1)
    elif kind == "object" or kind is None and isinstance(value, dict):
        if not isinstance(value, dict):
            raise ContractError("WALMART_FIELD_INVALID")
        props, required = schema.get("properties", {}), schema.get("required", [])
        if not isinstance(props, dict) or not isinstance(required, list):
            raise ContractError("WALMART_SCHEMA_INVALID")
        if any(name not in value for name in required):
            raise ContractError("WALMART_BODY_REQUIRED_FIELD")
        if len(value) < schema.get("minProperties", 0) or len(value) > schema.get(
            "maxProperties", 10000
        ):
            raise ContractError("WALMART_FIELD_INVALID")
        extra = schema.get("additionalProperties", True)
        for name, child in value.items():
            child_schema = props.get(name)
            if child_schema is None:
                if extra is False:
                    raise ContractError("WALMART_BODY_FIELD_NOT_ALLOWED")
                if isinstance(extra, dict):
                    child_schema = extra
                else:
                    continue
            if not isinstance(child_schema, dict):
                raise ContractError("WALMART_SCHEMA_INVALID")
            _validate_schema(child, child_schema, depth + 1)
    elif kind not in {None, "null"}:
        raise ContractError("WALMART_SCHEMA_UNSUPPORTED")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractError("WALMART_FIELD_INVALID")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ContractError("WALMART_FIELD_INVALID")
        if "maximum" in schema and value > schema["maximum"]:
            raise ContractError("WALMART_FIELD_INVALID")
    return value


def _validate_field(field: Field, value: Any) -> Any:
    if field.schema is not None:
        return _validate_schema(value, field.schema)
    schema: dict[str, Any] = {"type": field.kind}
    if field.enum:
        schema["enum"] = list(field.enum)
    if field.maximum is not None:
        schema["maximum"] = field.maximum
    return _validate_schema(value, schema)


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
            if len(operation.fields) != len(
                {(field.location, field.name) for field in operation.fields}
            ):
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
        if not operation.media_supported:
            raise ContractError("WALMART_MEDIA_TYPE_UNSUPPORTED")
        if operation.is_write and not allow_writes:
            raise ContractError("WALMART_WRITE_NOT_AUTHORIZED")
        values = params if params is not None else {}
        if not isinstance(values, Mapping) or len(values) > 80:
            raise ContractError("WALMART_PARAMS_INVALID")
        known = {field.name: field for field in operation.fields}
        if any(not isinstance(name, str) or name not in known for name in values):
            raise ContractError("WALMART_PARAM_NOT_ALLOWED")
        if any(field.required and field.name not in values for field in operation.fields):
            raise ContractError("WALMART_PARAM_REQUIRED")
        if body is not None and not operation.has_body:
            raise ContractError("WALMART_BODY_NOT_ALLOWED")
        if operation.body_required and body is None:
            raise ContractError("WALMART_BODY_REQUIRED")
        if body is not None:
            if (
                not isinstance(body, (dict, list, str))
                or len(json.dumps(body, ensure_ascii=False).encode()) > 2_000_000
            ):
                raise ContractError("WALMART_BODY_INVALID")
            if operation.request_schema is not None:
                _validate_schema(body, operation.request_schema)
            elif operation.request_content_type in {
                "application/json",
                "application/x-www-form-urlencoded",
            } and not isinstance(body, (dict, list)):
                raise ContractError("WALMART_BODY_INVALID")
            elif operation.request_content_type in {
                "application/xml",
                "text/xml",
            } and not isinstance(body, str):
                raise ContractError("WALMART_BODY_INVALID")
        path = operation.path
        query: dict[str, Any] = {}
        for name, raw in values.items():
            field = known[name]
            value = _validate_field(field, raw)
            if field.location == "path":
                if isinstance(value, (dict, list)):
                    raise ContractError("WALMART_PATH_PARAM_INVALID")
                path = path.replace("{" + name + "}", quote(str(value), safe=""))
            elif field.location == "query":
                if isinstance(value, list) and (field.style != "form" or not field.explode):
                    raise ContractError("WALMART_QUERY_SERIALIZATION_UNSUPPORTED")
                query[name] = value
        if _VAR.search(path) or not path.startswith("/v3/") or ".." in path or "//" in path:
            raise ContractError("WALMART_PATH_INVALID")
        return PreparedRequest(
            key=key,
            method=operation.method,
            path=path,
            query=query,
            body=body,
            is_write=operation.is_write,
            content_type=operation.request_content_type,
        )

    @classmethod
    def from_openapi(
        cls, document: Mapping[str, Any], *, approved_keys: frozenset[str] = frozenset()
    ) -> ContractRegistry:
        """Import a reviewed OpenAPI 3.x snapshot; only approved operationIds execute."""
        if not isinstance(document, Mapping):
            raise ContractError("WALMART_CONTRACT_INVALID")
        version = document.get("openapi", "")
        if not isinstance(version, str) or not version.startswith("3."):
            raise ContractError("WALMART_SPEC_VERSION_UNSUPPORTED")
        paths = document.get("paths")
        if not isinstance(paths, dict) or len(paths) > 3000:
            raise ContractError("WALMART_CONTRACT_INVALID")
        operations: list[Operation] = []
        for path, raw_verbs in paths.items():
            if (
                not isinstance(path, str)
                or not _path_valid(path)
                or not isinstance(raw_verbs, dict)
            ):
                raise ContractError("WALMART_CONTRACT_INVALID")
            verbs = _resolve_local_refs(raw_verbs, document)
            base_params = verbs.get("parameters", [])
            if not isinstance(base_params, list):
                raise ContractError("WALMART_CONTRACT_INVALID")
            for method, endpoint in verbs.items():
                if method not in _HTTP_METHODS:
                    continue
                if not isinstance(endpoint, dict):
                    raise ContractError("WALMART_CONTRACT_INVALID")
                key = endpoint.get("operationId")
                if not isinstance(key, str) or not _IDENTIFIER.fullmatch(key):
                    raise ContractError("WALMART_CONTRACT_INVALID")
                params = [*base_params, *endpoint.get("parameters", [])]
                fields_by_name: dict[tuple[str, str], Field] = {}
                for raw_param in params:
                    param = _resolve_local_refs(raw_param, document)
                    if not isinstance(param, dict):
                        raise ContractError("WALMART_CONTRACT_INVALID")
                    name, location = param.get("name"), param.get("in")
                    if not isinstance(name, str) or location not in {"path", "query"}:
                        if location == "header" and isinstance(name, str):
                            continue
                        raise ContractError("WALMART_CONTRACT_INVALID")
                    if name.lower() in _RESTRICTED:
                        raise ContractError("WALMART_CONTRACT_INVALID")
                    schema = _resolve_local_refs(param.get("schema", {"type": "string"}), document)
                    if not isinstance(schema, dict):
                        raise ContractError("WALMART_CONTRACT_INVALID")
                    kind = schema.get("type", "string")
                    if isinstance(kind, list):
                        kind = "union"
                    if kind not in {
                        "string",
                        "integer",
                        "number",
                        "boolean",
                        "array",
                        "object",
                        "null",
                        "union",
                    }:
                        raise ContractError("WALMART_SCHEMA_UNSUPPORTED")
                    style = param.get("style", "form")
                    explode = bool(param.get("explode", style == "form"))
                    fields_by_name[(name, location)] = Field(
                        name=name,
                        location=location,
                        required=bool(param.get("required", False) or location == "path"),
                        kind=kind,
                        enum=tuple(str(item) for item in schema.get("enum", [])),
                        maximum=schema.get("maximum"),
                        schema=schema,
                        style=style,
                        explode=explode,
                    )
                fields = tuple(fields_by_name.values())
                body = _resolve_local_refs(endpoint.get("requestBody"), document)
                has_body = body is not None
                body_required = (
                    bool(body.get("required", False)) if isinstance(body, dict) else False
                )
                body_schema: Mapping[str, Any] | None = None
                content_type = "application/json"
                media_supported = True
                if has_body:
                    if not isinstance(body, dict):
                        raise ContractError("WALMART_CONTRACT_INVALID")
                    content = body.get("content", {})
                    if not isinstance(content, dict) or not content:
                        media_supported = False
                    else:
                        candidates = (
                            "application/json",
                            "application/xml",
                            "text/xml",
                            "application/x-www-form-urlencoded",
                            "multipart/form-data",
                        )
                        content_type = next(
                            (item for item in candidates if item in content), next(iter(content))
                        )
                        media_supported = content_type in _SUPPORTED_BODY_TYPES
                        media = content.get(content_type)
                        if isinstance(media, dict) and media.get("schema") is not None:
                            schema = _resolve_local_refs(media["schema"], document)
                            if not isinstance(schema, dict):
                                raise ContractError("WALMART_CONTRACT_INVALID")
                            body_schema = schema
                operations.append(
                    Operation(
                        key=key,
                        method=method.upper(),
                        path=path,
                        fields=fields,
                        has_body=has_body,
                        source="imported-openapi-3",
                        enabled=key in approved_keys,
                        request_schema=body_schema,
                        request_content_type=content_type,
                        body_required=body_required,
                        media_supported=media_supported,
                        mutating=None,
                    )
                )
        if approved_keys.difference({operation.key for operation in operations}):
            raise ContractError("WALMART_APPROVED_OPERATION_UNKNOWN")
        return cls(tuple(operations))

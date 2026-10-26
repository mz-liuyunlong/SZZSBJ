"""Offline contracts and write-gate verification."""

import pytest

from app.integrations.walmart.contracts import ContractError, ContractRegistry


def document() -> dict[str, object]:
    return {
        "openapi": "3.0.3",
        "paths": {
            "/v3/items": {
                "get": {
                    "operationId": "listItems",
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer", "maximum": 100},
                        }
                    ],
                },
                "post": {
                    "operationId": "createItem",
                    "requestBody": {
                        "content": {"application/json": {"schema": {"type": "object"}}}
                    },
                },
            },
            "/v3/orders/{orderId}": {
                "get": {
                    "operationId": "getOrder",
                    "parameters": [
                        {
                            "name": "orderId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                    ],
                }
            },
        },
    }


def test_registers_operations_without_activating() -> None:
    registry = ContractRegistry.from_openapi(document())
    assert registry.keys() == ("createItem", "getOrder", "listItems")
    with pytest.raises(ContractError, match="WALMART_OPERATION_NOT_APPROVED"):
        registry.prepare("listItems")


def test_approved_read_contract() -> None:
    registry = ContractRegistry.from_openapi(
        document(), approved_keys=frozenset({"listItems", "getOrder"})
    )
    req = registry.prepare("listItems", params={"limit": 50})
    assert (req.method, req.path, req.query) == ("GET", "/v3/items", {"limit": 50})
    assert registry.prepare("getOrder", params={"orderId": "a/b"}).path == ("/v3/orders/a%2Fb")


def test_writes_require_second_gate() -> None:
    registry = ContractRegistry.from_openapi(document(), approved_keys=frozenset({"createItem"}))
    with pytest.raises(ContractError, match="WALMART_WRITE_NOT_AUTHORIZED"):
        registry.prepare("createItem", body={"sku": "fixture"})
    request = registry.prepare("createItem", body={"sku": "fixture"}, allow_writes=True)
    assert (request.method, request.is_write) == ("POST", True)


@pytest.mark.parametrize(
    ("parameters", "code"),
    [
        ({"unknown": "x"}, "WALMART_PARAM_NOT_ALLOWED"),
        ({"limit": True}, "WALMART_FIELD_INVALID"),
        ({"limit": 101}, "WALMART_FIELD_INVALID"),
    ],
)
def test_rejects_bad_inputs(parameters: dict[str, object], code: str) -> None:
    registry = ContractRegistry.from_openapi(document(), approved_keys=frozenset({"listItems"}))
    with pytest.raises(ContractError, match=code):
        registry.prepare("listItems", params=parameters)


def test_rejects_unapproved_contract_key() -> None:
    with pytest.raises(ContractError, match="WALMART_APPROVED_OPERATION_UNKNOWN"):
        ContractRegistry.from_openapi(document(), approved_keys=frozenset({"deleteAll"}))


def test_rejects_external_refs() -> None:
    doc = document()
    paths = doc["paths"]
    assert isinstance(paths, dict)
    items = paths["/v3/items"]
    assert isinstance(items, dict)
    operation = items["get"]
    assert isinstance(operation, dict)
    operation["parameters"] = [{"$ref": "https://not-trusted/param.yaml"}]
    with pytest.raises(ContractError, match="WALMART_SPEC_REFERENCE_UNSUPPORTED"):
        ContractRegistry.from_openapi(doc)

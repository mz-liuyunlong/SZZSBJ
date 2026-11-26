"""Dedicated single-plan contract; reuse existing default-deny signed transport."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from pydantic import JsonValue

from app.core.config import Settings
from app.integrations.lingxing.business_api import LingxingBusinessApiExecutor
from app.integrations.lingxing.openapi import LingxingOpenApiClient, LingxingOpenApiError
from app.integrations.lingxing.token_manager import get_shared_lingxing_token_manager

INTERFACE_ID = "LX-A4E9258A3B23"
API_PATH = "/erp/sc/routing/data/local_inventory/createPurchasePlan"
SAFE_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")


def _required(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is missing")
    return value.strip()


def build_purchase_plan_payload(
    *, sku: object, gtin: object, item_id: object, sid: object, quantity: int
) -> dict[str, JsonValue]:
    sku = _required(sku, "SKU")
    gtin = _required(gtin, "GTIN")
    item_id = _required(item_id, "Item ID")
    sid = _required(sid, "SID")
    if not gtin.isascii() or not gtin.isdigit() or len(gtin) not in (8, 12, 13, 14):
        raise ValueError("GTIN must retain its original digits and leading zeros")
    if not item_id.isascii() or not item_id.isdigit() or len(item_id) != 11:
        raise ValueError("Item ID must be a standalone 11-digit identifier")
    if not sid.isascii() or not sid.isdigit() or not int(sid):
        raise ValueError("Verified Lingxing SID must be a nonzero numeric string")
    if type(quantity) is not int or not 1 <= quantity <= 100000:
        raise ValueError("Approved quantity must be an integer between 1 and 100000")
    return {
        "remark": gtin,
        "data": [
            {"sku": sku, "quantity_plan": quantity, "sid": sid, "remark": f"ITEMID:{item_id}"}
        ],
    }


def safe_id(value: object) -> str | None:
    return value if isinstance(value, str) and SAFE_ID.fullmatch(value) else None


class PurchasePlanResponseError(RuntimeError):
    def __init__(self, code: str, request_id: str | None = None):
        self.code = code
        self.request_id = request_id
        super().__init__(code)


def parse_created_plan(payload: JsonValue) -> dict:
    if not isinstance(payload, dict):
        raise PurchasePlanResponseError("LX_PURCHASE_RESPONSE_INVALID")
    request_id = safe_id(payload.get("request_id"))
    code = payload.get("code")
    if type(code) is not int:
        raise PurchasePlanResponseError("LX_PURCHASE_CODE_UNKNOWN", request_id)
    if code != 0:
        # Never echo arbitrary provider messages, credentials or request body.
        raise PurchasePlanResponseError(f"LX_PURCHASE_PROVIDER_CODE_{code}", request_id)
    data = payload.get("data")
    if not isinstance(data, dict) or not request_id:
        raise PurchasePlanResponseError("LX_PURCHASE_RECEIPT_MISSING", request_id)
    plans = data.get("plan_sn")
    batch = safe_id(data.get("ppg_sn"))
    if (
        not isinstance(plans, list)
        or len(plans) != 1
        or not safe_id(plans[0])
        or not batch
        or payload.get("error_details") != []
    ):
        raise PurchasePlanResponseError("LX_PURCHASE_RECEIPT_UNCERTAIN", request_id)
    return {"plan_sn": plans[0], "ppg_sn": batch, "request_id": request_id}


def validate_transport(settings: Settings, payload: dict[str, JsonValue]) -> None:
    origin = urlsplit(settings.lingxing_base_url or "")
    if (
        origin.scheme != "https"
        or origin.netloc != "openapi.lingxing.com"
        or origin.path not in ("", "/")
        or origin.query
        or origin.fragment
    ):
        raise ValueError("Official Lingxing HTTPS origin is not configured")
    if (
        not settings.lingxing_enable_real_calls
        or not settings.lingxing_enable_token_requests
        or settings.lingxing_dry_run
        or not settings.lingxing_app_id
        or settings.lingxing_app_secret is None
    ):
        raise ValueError("Real Lingxing credentials/token/transport gates are not enabled")
    client = LingxingOpenApiClient()
    request = client.build_request(INTERFACE_ID, payload)
    if request.method != "POST" or request.api_path != API_PATH:
        raise ValueError("Registered purchase-plan endpoint mismatch")


def create_purchase_plan(settings: Settings, payload: dict[str, JsonValue]) -> dict:
    """One logical write attempt. Never retry ambiguous transport or response errors.

    Existing signed transport may recover from its explicit invalid-token code once.
    All other errors are left to the caller's durable attempt guard.
    """
    validate_transport(settings, payload)
    executor = LingxingBusinessApiExecutor(
        settings, token_provider=get_shared_lingxing_token_manager(settings)
    )
    try:
        client = LingxingOpenApiClient(
            executor=executor,
            enabled_interface_ids=frozenset({INTERFACE_ID}),
            owner_authorized_interface_ids=frozenset({INTERFACE_ID}),
        )
        response = client.call(INTERFACE_ID, payload, dry_run=False)
        return parse_created_plan(response)
    except LingxingOpenApiError as exc:
        raise PurchasePlanResponseError(exc.code) from None
    finally:
        executor.close()

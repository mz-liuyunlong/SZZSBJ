"""Production WFS creation adapter over the reviewed unified Walmart gateway.

Nothing here holds or reads a Walmart credential: every call goes through
``app.modules.walmart_scf.persistence.build_production_gateway`` (per-store cloud function,
persistent write ledger, audit rows). The adapter only

* builds the inbound-order body from the operation snapshot (our order id = ticket id),
* sends the reviewed write ``wfs_inbound_shipment_create`` with the business key
  ``create:<ticket id>`` so the ledger refuses a second POST while the first is open,
* reads back by ``inboundOrderId`` (``inbound_shipments``) to confirm or deny a shipment,
* fetches labels (``wfs_shipment_label``) and runs the optional preview.

The rollout switch (``WFS_CREATION_MODE``) decides which of these may run.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.core.api import ApiError
from app.modules.pmc_wfs.creation_config import CREATION_MODES, MODE_REASONS, PREVIEW_MODES

CREATE = "wfs_inbound_shipment_create"
LABEL = "wfs_shipment_label"
PREVIEW = "wfs_inbound_preview"
READ_BACK = "inbound_shipments"
OPERATIONS = frozenset({CREATE, LABEL, PREVIEW, READ_BACK})
ACTOR_UID = "pmc-wfs-creation"


class DefinitiveRejection(Exception):
    """Walmart answered and refused: no shipment was created. ``reason`` is shown to users."""

    def __init__(self, reason: str = "", code: str = "WFS_PLATFORM_REJECTED") -> None:
        super().__init__(reason or code)
        self.reason = reason
        self.code = code


class NotSent(Exception):
    """The request provably never left the server (config, scope, ledger refusal)."""

    def __init__(self, code: str, reason: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.reason = reason


class ResultUnknown(Exception):
    """The request may have reached Walmart; only a read-back can tell."""

    def __init__(self, code: str = "WFS_RESULT_UNKNOWN") -> None:
        super().__init__(code)
        self.code = code


# ----- body mapping (pure; unit tested) ---------------------------------------------


def gtin14(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    if not 8 <= len(digits) <= 14:
        raise NotSent("WFS_GTIN_INVALID", f"GTIN 不合法：{value or '空'}")
    return digits.zfill(14)


def walmart_date(value: str) -> str:
    """Walmart wants an ISO instant with milliseconds, e.g. 2026-11-30T00:00:00.000Z."""
    moment = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def inbound_order(ticket_id: str, snapshot: Mapping[str, Any], allocation: Mapping[str, Any]):
    """One planned shipment (ticket) -> one Walmart inbound order; SKU lines aggregated."""
    orders = {str(o["id"]): o for o in snapshot.get("orders") or [snapshot["order"]]}
    items: dict[str, dict[str, Any]] = {}
    for box_range in allocation["ranges"]:
        order = orders.get(str(box_range["order_id"]))
        if order is None:
            raise NotSent("WFS_SNAPSHOT_ORDER_MISSING", "快照里缺少打包单信息")
        seller_sku = order.get("msku") or order["sku"]
        item = items.get(seller_sku)
        pack = int(box_range["units_per_box"])
        if item is None:
            items[seller_sku] = {
                "productId": gtin14(order.get("gtin")),
                "productType": "GTIN",
                "sku": seller_sku,
                "itemDesc": (order.get("product_name") or order["sku"])[:500],
                "itemQty": int(box_range["units"]),
                "vendorPackQty": pack,
                "innerPackQty": pack,
                "expectedDeliveryDate": walmart_date(snapshot["expected_delivery_at"]),
            }
        elif item["vendorPackQty"] != pack:
            raise NotSent("WFS_PACK_QTY_MIXED", f"{seller_sku} 同一票里箱规不一致，请分开建票")
        else:
            item["itemQty"] += int(box_range["units"])
    address = snapshot["return_address"]
    body: dict[str, Any] = {
        "inboundOrderId": str(ticket_id),
        "returnAddress": {
            "addressLine1": address["address_line1"],
            "city": address["city"],
            "stateCode": address["state_code"],
            "countryCode": address.get("country_code", "US"),
            "postalCode": address["postal_code"],
        },
        "orderItems": list(items.values()),
    }
    if snapshot.get("its"):
        body["inboundServices"] = {"inventoryTransferService": "Y"}
    return body


def load_types(cartons: int, mixed_boxes: int) -> list[dict[str, str]]:
    """Label carton split; ``mixed_boxes`` comes from WFS 设置 · 创建默认值."""
    mixed = max(0, min(mixed_boxes, cartons))
    result = []
    if cartons - mixed:
        result.append({"loadType": "SINGLE SKU", "count": str(cartons - mixed)})
    if mixed:
        result.append({"loadType": "MIXED SKUS", "count": str(mixed)})
    return result


def _records(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for key in ("payload", "shipments", "elements", "data"):
            if key in data:
                return _records(data[key])
        if data.get("shipmentId"):
            return [data]
    return []


def shipments_from(data: Any, inbound_order_id: str | None = None) -> list[dict[str, Any]]:
    """Walmart shipment records -> our stored shape (shipment id, FC, address, status)."""
    result = []
    for row in _records(data):
        sid = row.get("shipmentId")
        if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9]{1,32}", sid):
            continue
        if inbound_order_id and row.get("inboundOrderId") not in (None, inbound_order_id):
            continue
        ship_to = row.get("shipToAddress") if isinstance(row.get("shipToAddress"), dict) else {}
        items = row.get("shipmentItems") if isinstance(row.get("shipmentItems"), list) else []
        cartons = 0
        for item in items:
            try:
                cartons += int(item.get("itemQty", 0)) // max(int(item.get("vendorPackQty", 1)), 1)
            except (TypeError, ValueError):
                cartons = 0
                break
        result.append(
            {
                "shipment_id": sid,
                "fc": ship_to.get("fcName") or row.get("shipNodeName"),
                "ship_to": {
                    k: ship_to.get(k)
                    for k in ("addressLine1", "city", "stateCode", "postalCode")
                    if ship_to.get(k)
                },
                "status": row.get("status"),
                "cartons": cartons or None,
            }
        )
    return result


def provider_reason(error: Any) -> str:
    """Walmart's error body -> one readable line (descriptions only, never raw bodies)."""
    found: list[str] = []

    def walk(node: Any) -> None:
        if len(found) >= 5:
            return
        if isinstance(node, dict):
            for key in ("description", "message", "info", "code"):
                value = node.get(key)
                if isinstance(value, str) and value.strip() and key != "code":
                    found.append(value.strip())
                    break
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str) and node.strip() and not found:
            found.append(node.strip())

    walk(error)
    text = "；".join(dict.fromkeys(found)) or "Walmart 拒绝了请求（未返回原因）"
    return text[:500]


# ----- adapter ----------------------------------------------------------------------


class WalmartCreationGateway:
    """Implements ``app.modules.pmc_wfs.gateway.CreationGateway`` for production."""

    def __init__(
        self,
        walmart: Any,
        *,
        mode: str,
        store_map: Mapping[str, str],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        from app.integrations.walmart.gateway import Actor

        self._walmart = walmart
        self._store_map = dict(store_map)
        self._clock = clock
        self.mode = mode
        self.enabled = mode in CREATION_MODES
        self.preview_enabled = mode in PREVIEW_MODES
        self.reason = MODE_REASONS.get(mode) or None
        self._actor = Actor.system(ACTOR_UID, operations=OPERATIONS)

    # -- helpers
    def _store(self, snapshot: Mapping[str, Any]) -> str:
        store_id = str((snapshot.get("order") or {}).get("store_id") or "")
        code = self._store_map.get(store_id)
        if not code:
            raise NotSent("WFS_STORE_NOT_MAPPED", f"店铺 {store_id or '空'} 没有配置 Walmart 通道")
        return code

    def _approval(self, snapshot: Mapping[str, Any]) -> str:
        ref = snapshot.get("approval_ref")
        if not isinstance(ref, str) or not ref:
            raise NotSent("WFS_APPROVAL_REQUIRED", "缺少人工批准编号")
        return ref[:128]

    def _call(self, store: str, operation: str, **kwargs: Any):
        from app.integrations.walmart.gateway import GatewayError

        key = kwargs.get("idempotency_key")
        try:
            return self._walmart.call(store, operation, actor=self._actor, **kwargs)
        except GatewayError as error:
            if key is None:
                raise ResultUnknown(error.code) from None
            status = None
            try:
                status = self._walmart.ledger.status(key)
            except Exception:
                status = "unknown"
            if error.code == "WALMART_WRITE_ALREADY_DONE":
                raise ResultUnknown(error.code) from None  # created before: read it back
            if status in (None, "failed", "provider_error") and error.code not in (
                "WALMART_GATEWAY_UNAVAILABLE",
            ):
                # The ledger never opened (or closed it as not sent): nothing left the server.
                raise NotSent(error.code, f"未发出：{error.code}") from None
            raise ResultUnknown(error.code) from None

    # -- CreationGateway
    def validate(self, snapshot: dict) -> None:
        if not self.enabled:
            raise ApiError(
                code="WFS_EXECUTION_DISABLED",
                status_code=503,
                message=(self.reason or "Walmart 创建未启用") + "；未创建货件，也未占用箱子",
            )
        if self.mode == "single" and int(snapshot.get("shipment_count", 1)) != 1:
            raise ApiError(
                code="WFS_SINGLE_MODE_ONE_SHIPMENT",
                status_code=409,
                message="单个测试模式下每次只能创建 1 个计划货件",
            )
        try:
            self._store(snapshot)
        except NotSent as error:
            raise ApiError(code=error.code, status_code=409, message=error.reason) from None

    def create(self, ticket_id: str, snapshot: dict, allocation: dict) -> list[dict]:
        store = self._store(snapshot)
        body = inbound_order(ticket_id, snapshot, allocation)
        result = self._call(
            store,
            CREATE,
            body=body,
            approval_ref=self._approval(snapshot),
            idempotency_key=f"create:{ticket_id}",
        )
        if result.ok:
            return shipments_from(result.data, str(ticket_id))
        status = result.status_code
        if status >= 500 or status in (408, 429):
            raise ResultUnknown(f"WALMART_HTTP_{status}")
        raise DefinitiveRejection(provider_reason(result.provider_error or result.data))

    def reconcile(self, ticket_id: str, snapshot: dict) -> list[dict] | None:
        store = self._store(snapshot)
        now = self._clock()
        params = {
            "inboundOrderId": str(ticket_id),
            "fromCreatedDate": int((now - timedelta(days=30)).timestamp() * 1000),
            "toCreatedDate": int((now + timedelta(days=1)).timestamp() * 1000),
            "limit": 50,
            "offset": 0,
        }
        result = self._call(store, READ_BACK, params=params)
        if not result.ok:
            raise ResultUnknown(f"WALMART_HTTP_{result.status_code}")
        found = shipments_from(result.data, str(ticket_id))
        return found or None

    def resolve(self, ticket_id: str, outcome: str, note: str) -> None:
        """Close the ledger key after a read-back (ok / failed); best effort."""
        try:
            if self._walmart.ledger.status(f"create:{ticket_id}") in ("attempting", "unknown"):
                self._walmart.ledger.resolve(f"create:{ticket_id}", outcome=outcome, note=note)
        except Exception:
            pass

    def label(self, shipment_id: str, snapshot: dict, cartons: int | None = None) -> bytes:
        store = self._store(snapshot)
        defaults = snapshot.get("creation_defaults") or {}
        count = cartons or int(snapshot.get("ticket_boxes") or 0)
        if count <= 0:
            raise ValueError("carton count unknown")
        body = {
            "shipmentId": shipment_id,
            "labelSize": "X4_6",
            "labelFormat": "PDF",
            "loadTypes": load_types(count, int(defaults.get("mixed_boxes") or 0)),
        }
        # Labels have no side effect at Walmart; a fresh key per attempt allows re-fetching.
        result = self._call(
            store,
            LABEL,
            body=body,
            approval_ref=self._approval(snapshot),
            idempotency_key=f"label:{shipment_id}:{uuid4().hex[:12]}",
        )
        if not result.ok or not isinstance(result.pdf, bytes):
            raise ValueError("label unavailable")
        return result.pdf

    def preview(self, snapshot: dict) -> dict:
        if not self.preview_enabled:
            raise ApiError(code="WFS_EXECUTION_DISABLED", status_code=503, message=self.reason)
        store = self._store(snapshot)
        allocation = snapshot["allocation"]["tickets"][0]
        payload = inbound_order(f"preview-{uuid4().hex[:20]}", snapshot, allocation)
        result = self._call(
            store,
            PREVIEW,
            body={"header": {"headerAttributes": {}}, "payload": payload},
            approval_ref=f"preview:{snapshot.get('source_account_ref', '')}"[:128],
            idempotency_key=f"preview:{uuid4().hex}",
        )
        if not result.ok:
            return {"ok": False, "reason": provider_reason(result.provider_error or result.data)}
        return {"ok": True, "shipments": shipments_from(result.data)}

    def probe(self, store_id: str) -> dict:
        """Read-only connectivity check: list inbound shipments of the last 7 days."""
        if not self.preview_enabled:
            raise ApiError(code="WFS_EXECUTION_DISABLED", status_code=503, message=self.reason)
        store = self._store({"order": {"store_id": store_id}})
        now = self._clock()
        params = {
            "fromCreatedDate": int((now - timedelta(days=7)).timestamp() * 1000),
            "toCreatedDate": int(now.timestamp() * 1000),
            "limit": 10,
            "offset": 0,
        }
        result = self._call(store, READ_BACK, params=params)
        return {
            "ok": result.ok,
            "status_code": result.status_code,
            "store_code": store,
            "recent_shipments": len(shipments_from(result.data)) if result.ok else 0,
        }

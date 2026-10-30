"""Walmart WFS creation adapter (handover chapter 74, part B).

Implements ``CreationGateway`` on top of the shared Walmart SCF read/write APIs:

    validate  -> store mapping + ITS capability + item identities (no network)
    create    -> precheck by inboundOrderId -> POST inbound-shipments -> read back shipments
    reconcile -> read back by inboundOrderId
    label     -> carton count from shipment items -> POST shipment-label (PDF)
    preview   -> POST inbound-preview

Owner decisions applied: ITS defaults to Y but the store must be marked ITS-capable;
return address is omitted unless the operator supplied one (Walmart fills the store
default); expected delivery = Beijing today + 30 days; a created shipment whose read-back
fails is left UNKNOWN (never auto-cancelled). Every Walmart call is recorded as an
immutable ``walmart_call`` event with status code and sanitized provider error only.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.api import ApiError
from app.modules.pmc_wfs.creation_models import WfsCreationEvent, WfsCreationTicket
from app.modules.pmc_wfs.creation_worker import DefinitiveRejection
from app.modules.pmc_wfs.gateway import DisabledGateway
from app.modules.pmc_wfs.store_settings_models import WfsStoreSetting

BEIJING = ZoneInfo("Asia/Shanghai")
STORE_CODE = re.compile(r"^(HK|CN)[0-9]{4}$")
GTIN = re.compile(r"^\d{14}$")
DELIVERY_DAYS = 30
READBACK_WINDOW_DAYS = 400
MAX_ITEMS_PER_SHIPMENT = 20
LABEL_MAX_BYTES = 10_000_000


class WalmartResultLike(Protocol):
    status_code: int
    data: Any
    provider_error: Any
    pdf: bytes | None


class ReadApiLike(Protocol):
    def call(
        self, store_code: str, operation: str, *, params: Mapping[str, Any] | None = None
    ) -> WalmartResultLike: ...


class WriteApiLike(Protocol):
    def call(
        self,
        store_code: str,
        operation: str,
        *,
        approval_ref: str,
        params: Mapping[str, Any] | None = None,
        body: Any = None,
    ) -> WalmartResultLike: ...


@dataclass(frozen=True, slots=True)
class StoreContext:
    store_code: str
    its_enabled: bool
    creation_enabled: bool


def inbound_order_id(store_code: str, ticket_id: str | UUID, *, test: bool) -> str:
    """Deterministic plan id so reconcile can find the shipment without extra state."""
    token = UUID(str(ticket_id)).hex[:12].upper()
    return f"PMC-{'TEST-' if test else ''}{store_code}-{token}"


def expected_delivery(clock: Callable[[], datetime], snapshot: Mapping[str, Any]) -> str:
    supplied = snapshot.get("expected_delivery_at")
    if supplied:
        day = datetime.fromisoformat(str(supplied).replace("Z", "+00:00")).astimezone(BEIJING)
    else:
        day = clock().astimezone(BEIJING) + timedelta(days=DELIVERY_DAYS)
    return f"{day.date().isoformat()}T00:00:00.000Z"


def _its_flag(snapshot: Mapping[str, Any]) -> str:
    return "Y" if snapshot.get("its", True) else "N"


def _return_address(snapshot: Mapping[str, Any]) -> dict[str, str] | None:
    address = snapshot.get("return_address")
    if not isinstance(address, Mapping):
        return None
    mapped = {
        "addressLine1": address.get("address_line1"),
        "city": address.get("city"),
        "stateCode": address.get("state_code"),
        "countryCode": address.get("country_code", "US"),
        "postalCode": address.get("postal_code"),
    }
    if any(not v for v in mapped.values()):
        return None
    if address.get("address_line2"):
        mapped["addressLine2"] = str(address["address_line2"])
    return {k: str(v) for k, v in mapped.items()}


def _identities(snapshot: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """sku -> {gtin, desc}; raises ApiError when a SKU has no usable Walmart identity."""
    out: dict[str, dict[str, str]] = {}
    orders = list(snapshot.get("orders") or [])
    if snapshot.get("order"):
        orders.append(snapshot["order"])
    for order in orders:
        sku = str(order.get("sku") or "")
        gtin = str(order.get("gtin") or "")
        desc = str(order.get("product_name") or order.get("msku") or sku or "").strip()
        if not sku or not GTIN.fullmatch(gtin):
            raise ApiError(
                code="WFS_ITEM_IDENTITY_MISSING",
                status_code=409,
                message=f"SKU {sku or '?'} 缺少 14 位 GTIN，不能创建 Walmart 货件",
            )
        out.setdefault(sku, {"gtin": gtin, "desc": desc[:500] or sku})
    return out


def _order_items(
    ranges: list[Mapping[str, Any]],
    identities: Mapping[str, Mapping[str, str]],
    delivery: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, int]] = {}
    for rng in ranges:
        sku = str(rng["sku"])
        per = int(rng["units_per_box"])
        boxes = int(rng["boxes"])
        entry = grouped.setdefault(sku, {"per": per, "boxes": 0})
        if entry["per"] != per:
            raise DefinitiveRejection("WFS_MIXED_PACK_SIZE_IN_TICKET")
        entry["boxes"] += boxes
    if not grouped or len(grouped) > MAX_ITEMS_PER_SHIPMENT:
        raise DefinitiveRejection("WFS_TICKET_ITEM_COUNT_INVALID")
    items = []
    for sku, entry in grouped.items():
        identity = identities.get(sku)
        if identity is None:
            raise DefinitiveRejection("WFS_ITEM_IDENTITY_MISSING")
        items.append(
            {
                "productId": identity["gtin"],
                "productType": "GTIN",
                "sku": sku,
                "itemDesc": identity["desc"],
                "itemQty": entry["boxes"] * entry["per"],
                "vendorPackQty": entry["boxes"],
                "innerPackQty": entry["per"],
                "expectedDeliveryDate": delivery,
            }
        )
    return items


def _shipment_ids(payload: Any) -> list[str]:
    records = payload.get("payload") if isinstance(payload, Mapping) else None
    if isinstance(records, Mapping):
        records = records.get("inboundShipments") or records.get("shipments")
    ids: list[str] = []
    for record in records or []:
        if isinstance(record, Mapping):
            sid = record.get("shipmentId")
            if isinstance(sid, str) and sid.strip() and sid not in ids:
                ids.append(sid.strip())
    return ids


class WalmartScfCreationGateway:
    enabled = True

    def __init__(
        self,
        *,
        session_factory: Callable[[], Any],
        read_api: ReadApiLike,
        write_api: WriteApiLike,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleeper: Callable[[float], None] = time.sleep,
        pace_seconds: float = 1.3,
        store_code_map: Mapping[str, str] | None = None,
    ) -> None:
        self._factory = session_factory
        self._read = read_api
        self._write = write_api
        self._clock = clock
        self._sleep = sleeper
        self._pace = pace_seconds
        # Server-reviewed Lingxing store_id -> Walmart store code (SZZSBJ_WALMART_SCF_STORE_ID_MAP).
        # When present it is authoritative; the settings row must agree with it.
        self._store_code_map = dict(store_code_map or {})

    # ------------------------------------------------------------------ store context

    def _store(self, snapshot: Mapping[str, Any]) -> StoreContext:
        account = str(snapshot.get("source_account_ref") or "")
        order = snapshot.get("order") or {}
        store_id = str(order.get("store_id") or "")
        with self._factory() as session:
            row = session.scalar(
                select(WfsStoreSetting).where(
                    WfsStoreSetting.source_account_ref == account,
                    WfsStoreSetting.store_id == store_id,
                )
            )
        if row is None or not STORE_CODE.fullmatch(row.walmart_store_code):
            raise ApiError(
                code="WFS_STORE_NOT_CONFIGURED",
                status_code=409,
                message="该店铺尚未配置 Walmart 店铺代码，请先在 WFS 设置中维护",
            )
        reviewed = self._store_code_map.get(store_id)
        if reviewed is not None and reviewed != row.walmart_store_code:
            raise ApiError(
                code="WFS_STORE_MAPPING_CONFLICT",
                status_code=409,
                message="WFS 设置中的 Walmart 店铺代码与服务器审核映射不一致，请先核对",
            )
        return StoreContext(
            store_code=row.walmart_store_code,
            its_enabled=bool(row.its_enabled),
            creation_enabled=bool(row.creation_enabled),
        )

    # ------------------------------------------------------------------ gateway protocol

    def validate(self, snapshot: dict) -> None:
        store = self._store(snapshot)
        if not store.creation_enabled:
            raise ApiError(
                code="WFS_STORE_CREATION_DISABLED",
                status_code=409,
                message="该店铺的 Walmart 货件创建未开启",
            )
        if snapshot.get("its", True) and not store.its_enabled:
            raise ApiError(
                code="WFS_ITS_NOT_AVAILABLE",
                status_code=409,
                message="该店铺未确认开通 ITS，请改为自行分拨或先在 WFS 设置中确认 ITS 可用",
            )
        _identities(snapshot)

    def create(self, ticket_id: str, snapshot: dict, allocation: dict) -> list[str]:
        store = self._store(snapshot)
        test = bool(snapshot.get("order", {}).get("business_test", snapshot.get("business_test")))
        order_id = inbound_order_id(store.store_code, ticket_id, test=test)
        existing = self._readback(store.store_code, order_id, ticket_id)
        if existing:
            return existing
        body: dict[str, Any] = {
            "inboundOrderId": order_id,
            "orderItems": _order_items(
                list(allocation.get("ranges") or []),
                _identities(snapshot),
                expected_delivery(self._clock, snapshot),
            ),
            "inboundServices": {
                "inventoryTransferService": "Y" if snapshot.get("its", True) else "N"
            },
        }
        address = _return_address(snapshot)
        if address:
            body["returnAddress"] = address
        self._sleep(self._pace)
        result = self._write.call(
            store.store_code,
            "wfs_inbound_shipment_create",
            approval_ref=f"wfs-ticket:{ticket_id}",
            body=body,
        )
        self._record(ticket_id, "wfs_inbound_shipment_create", result, order_id)
        if 200 <= result.status_code < 300:
            self._sleep(self._pace)
            ids = self._readback(store.store_code, order_id, ticket_id)
            if not ids:
                # Walmart accepted but nothing is visible yet: keep holds, let reconcile retry.
                raise RuntimeError("WFS_READBACK_EMPTY_AFTER_CREATE")
            return ids
        if 400 <= result.status_code < 500:
            # A client-side rejection may still mean "already exists": read back once more.
            self._sleep(self._pace)
            ids = self._readback(store.store_code, order_id, ticket_id)
            if ids:
                return ids
            raise DefinitiveRejection(f"WALMART_HTTP_{result.status_code}")
        raise RuntimeError(f"WALMART_HTTP_{result.status_code}")

    def reconcile(self, ticket_id: str, snapshot: dict) -> list[str] | None:
        store = self._store(snapshot)
        test = bool(snapshot.get("order", {}).get("business_test", snapshot.get("business_test")))
        order_id = inbound_order_id(store.store_code, ticket_id, test=test)
        ids = self._readback(store.store_code, order_id, ticket_id)
        return ids or None

    def label(self, shipment_id: str, snapshot: dict) -> bytes:
        store = self._store(snapshot)
        count = self._carton_count(store.store_code, shipment_id)
        self._sleep(self._pace)
        result = self._write.call(
            store.store_code,
            "wfs_shipment_label",
            approval_ref=f"wfs-label:{shipment_id}",
            body={
                "shipmentId": shipment_id,
                "labelSize": "X4_6",
                "labelFormat": "PDF",
                "loadTypes": [{"loadType": "SINGLE SKU", "count": str(count)}],
            },
        )
        self._record(None, "wfs_shipment_label", result, shipment_id)
        pdf = result.pdf
        if not (200 <= result.status_code < 300) or not isinstance(pdf, bytes):
            raise RuntimeError(f"WALMART_LABEL_HTTP_{result.status_code}")
        if not pdf.startswith(b"%PDF") or len(pdf) > LABEL_MAX_BYTES:
            raise RuntimeError("WALMART_LABEL_INVALID")
        return pdf

    def preview(self, snapshot: dict) -> dict:
        store = self._store(snapshot)
        allocation = snapshot.get("allocation") or {}
        ranges = [r for t in allocation.get("tickets") or [] for r in t.get("ranges") or []]
        body = {
            "header": {"headerAttributes": {}},
            "payload": {
                "inboundOrderId": "PMC-PREVIEW-" + store.store_code,
                "orderItems": _order_items(
                    ranges, _identities(snapshot), expected_delivery(self._clock, snapshot)
                ),
                "inboundServices": {"inventoryTransferService": _its_flag(snapshot)},
            },
        }
        self._sleep(self._pace)
        result = self._write.call(
            store.store_code, "wfs_inbound_preview", approval_ref="wfs-preview", body=body
        )
        if not 200 <= result.status_code < 300:
            raise ApiError(
                code="WFS_PREVIEW_REJECTED",
                status_code=502,
                message="Walmart 未返回分仓方案",
                details={
                    "status_code": result.status_code,
                    "provider_error": result.provider_error,
                },
            )
        return {"plans": _preview_plans(result.data), "raw_status": result.status_code}

    # ------------------------------------------------------------------ helpers

    def _readback(self, store_code: str, order_id: str, ticket_id: str | None) -> list[str]:
        now = self._clock()
        params = {
            "inboundOrderId": order_id,
            "fromCreatedDate": int((now - timedelta(days=READBACK_WINDOW_DAYS)).timestamp() * 1000),
            "toCreatedDate": int((now + timedelta(days=1)).timestamp() * 1000),
            "limit": 50,
            "offset": 0,
        }
        result = self._read.call(store_code, "inbound_shipments", params=params)
        self._record(ticket_id, "inbound_shipments", result, order_id)
        if not 200 <= result.status_code < 300:
            raise RuntimeError(f"WALMART_READBACK_HTTP_{result.status_code}")
        return _shipment_ids(result.data)

    def _carton_count(self, store_code: str, shipment_id: str) -> int:
        result = self._read.call(
            store_code,
            "inbound_shipment_items",
            params={"shipmentId": shipment_id, "limit": 50, "offset": 0},
        )
        self._record(None, "inbound_shipment_items", result, shipment_id)
        if not 200 <= result.status_code < 300:
            raise RuntimeError(f"WALMART_ITEMS_HTTP_{result.status_code}")
        items = result.data.get("payload") if isinstance(result.data, Mapping) else None
        if isinstance(items, Mapping):
            items = items.get("inboundShipmentItems") or items.get("items")
        total = 0
        for item in items or []:
            if isinstance(item, Mapping):
                try:
                    total += int(item.get("vendorPackQty") or 0)
                except (TypeError, ValueError):
                    continue
        if total <= 0:
            raise RuntimeError("WALMART_CARTON_COUNT_UNKNOWN")
        return total

    def _record(
        self, ticket_id: str | None, operation: str, result: WalmartResultLike, ref: str
    ) -> None:
        """Immutable audit row per Walmart call; never the token, never the full payload."""
        if ticket_id is None:
            return
        evidence: dict[str, Any] = {
            "ticket_id": str(ticket_id),
            "operation": operation,
            "ref": ref,
            "status_code": result.status_code,
            "at": self._clock().isoformat(),
        }
        if result.provider_error is not None:
            evidence["provider_error"] = result.provider_error
        try:
            with self._factory() as session:
                operation_id = session.scalar(
                    select(WfsCreationTicket.operation_id).where(
                        WfsCreationTicket.id == UUID(str(ticket_id))
                    )
                )
                if operation_id is None:
                    return
                session.add(
                    WfsCreationEvent(
                        operation_id=operation_id,
                        actor_uid="wfs-walmart-gateway",
                        kind="walmart_call",
                        evidence=evidence,
                    )
                )
                session.commit()
        except Exception:
            # Auditing must not change the business outcome of the call itself.
            return


def _preview_plans(data: Any) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    payload = data.get("payload") if isinstance(data, Mapping) else None
    for block in payload or []:
        for preview in (block or {}).get("previews") or []:
            kind = preview.get("previewType")
            for plan in preview.get("preview") or []:
                address = plan.get("shipToAddress") or {}
                plans.append(
                    {
                        "preview_type": kind,
                        "fc_name": address.get("fcName"),
                        "node_type": plan.get("nodeType"),
                        "charge": plan.get("totalNetTransferCharge"),
                        "units": sum(
                            int(i.get("itemQty") or 0) for i in plan.get("shipmentItems") or []
                        ),
                        "skus": [i.get("vendorSku") for i in plan.get("shipmentItems") or []],
                    }
                )
    return plans


# ---------------------------------------------------------------------- configuration


def _env_set(name: str) -> frozenset[str]:
    return frozenset(x.strip() for x in os.environ.get(name, "").split(",") if x.strip())


GATEWAY_SWITCH = "SZZSBJ_WFS_CREATION_GATEWAY"
STORE_MAP = "SZZSBJ_WALMART_SCF_STORE_ID_MAP"
CVM_ROLE = "SZZSBJ_WALMART_SCF_CVM_ROLE"
TARGET_ARN = "SZZSBJ_WALMART_SCF_TARGET_ROLE_ARN"
READ_KEYS = "SZZSBJ_WALMART_SCF_APPROVED_READ_KEYS"
WRITE_KEYS = "SZZSBJ_WALMART_SCF_APPROVED_WRITE_KEYS"
REQUIRED_READ_KEYS = frozenset({"inbound_shipments", "inbound_shipment_items"})


def reviewed_store_map() -> dict[str, str]:
    """Lingxing store_id -> Walmart store code from the server-reviewed JSON map, or {}."""
    try:
        raw = json.loads(os.environ.get(STORE_MAP, "{}"))
    except ValueError:
        return {}
    if not isinstance(raw, dict):
        return {}
    out = {
        str(k): str(v)
        for k, v in raw.items()
        if isinstance(k, str) and isinstance(v, str) and STORE_CODE.fullmatch(v)
    }
    return out if len(set(out.values())) == len(out) else {}


def build_gateway_from_env(session_factory: Callable[[], Any]) -> Any:
    """Select the adapter from environment; anything incomplete falls back to Disabled.

    Reuses the server's existing Walmart SCF variables (``/etc/szzsbj/walmart-scf.env``,
    loaded by the celery service) instead of introducing a second set:

      SZZSBJ_WFS_CREATION_GATEWAY=scf               the switch (anything else = disabled)
      SZZSBJ_WALMART_SCF_STORE_ID_MAP               reviewed store_id -> store code JSON
      SZZSBJ_WALMART_SCF_CVM_ROLE / _TARGET_ROLE_ARN identity (already present)
      SZZSBJ_WALMART_SCF_APPROVED_READ_KEYS         must include inbound_shipments,
                                                    inbound_shipment_items
      SZZSBJ_WALMART_SCF_APPROVED_WRITE_KEYS        reviewed WFS write keys (new)
    """
    if os.environ.get(GATEWAY_SWITCH, "disabled").strip().lower() != "scf":
        return DisabledGateway()
    store_map = reviewed_store_map()
    read_keys = _env_set(READ_KEYS)
    write_keys = _env_set(WRITE_KEYS)
    cvm_role = os.environ.get(CVM_ROLE, "").strip()
    role_arn = os.environ.get(TARGET_ARN, "").strip()
    if (
        not store_map
        or not write_keys
        or not REQUIRED_READ_KEYS <= read_keys
        or not cvm_role
        or not role_arn
    ):
        return DisabledGateway()
    stores = frozenset(store_map.values())
    functions = {store: f"szzsbj-walmart-{store.lower()}-executor" for store in stores}
    # Imported lazily: the Tencent identity helpers are only needed when the adapter is on.
    from app.integrations.walmart.scf_write_factory import make_walmart_write_api

    from app.integrations.walmart.scf_read_factory import make_walmart_read_api

    read_api = make_walmart_read_api(
        allowed_stores=stores,
        approved_read_keys=read_keys,
        function_by_store=functions,
        cvm_role=cvm_role,
        target_role_arn=role_arn,
        function_qualifier="stable",
    )
    write_api = make_walmart_write_api(
        allowed_stores=stores,
        approved_write_keys=write_keys,
        function_by_store=functions,
        cvm_role=cvm_role,
        target_role_arn=role_arn,
        function_qualifier="stable",
    )
    return WalmartScfCreationGateway(
        session_factory=session_factory,
        read_api=read_api,
        write_api=write_api,
        store_code_map=store_map,
    )

"""Walmart WFS creation adapter (handover chapter 74, part B; chapter 76.7 revision).

Implements ``CreationGateway`` on top of the unified ``WalmartGateway`` (one entry point,
server-side authorization, signed contracts, audit + write ledger):

    validate  -> store mapping + ITS capability + item identities (no network)
    create    -> precheck by inboundOrderId -> POST inbound-shipments -> read back shipments
    reconcile -> read back by inboundOrderId
    label     -> carton count from shipment items -> POST shipment-label (PDF)
    preview   -> POST inbound-preview

Owner decisions applied: ITS defaults to Y but the store must be marked ITS-capable;
return address is omitted unless the operator supplied one (Walmart fills the store
default); expected delivery = Beijing today + 30 days; a created shipment whose read-back
fails is left UNKNOWN (never auto-cancelled). Every Walmart call is recorded as an
immutable ``walmart_call`` event with status code and sanitized provider error only, and
by the gateway itself in ``integration_walmart_calls``.

Reviewer requirements folded in (76.13): read-back only accepts shipments whose
``inboundOrderId`` equals the plan id; shipment items are read with full pagination; a
created plan is verified (GTIN set, quantities, cartons) against the request; writes carry
business idempotency keys so an uncertain create is never repeated blindly.
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


class GatewayLike(Protocol):
    """The unified ``app.integrations.walmart.gateway.WalmartGateway`` surface we use."""

    def call(
        self,
        store_code: str,
        operation_key: str,
        *,
        actor: Any,
        params: Mapping[str, Any] | None = None,
        body: Any = None,
        approval_ref: str | None = None,
        idempotency_key: str | None = None,
    ) -> WalmartResultLike: ...

    @property
    def ledger(self) -> Any: ...


WORKER_ACTOR_UID = "pmc-wfs-creation"
# The only operations the creation worker may ever issue (system actor allowlist).
WORKER_OPERATIONS = frozenset(
    {
        "inbound_shipments",
        "inbound_shipment_items",
        "wfs_inbound_shipment_create",
        "wfs_shipment_label",
        "wfs_inbound_preview",
    }
)
ITEMS_PAGE_SIZE = 50
ITEMS_MAX_PAGES = 40
_LEDGER_BLOCKED = frozenset({"WALMART_WRITE_PENDING_REVIEW", "WALMART_WRITE_ALREADY_DONE"})


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


def _shipment_ids(payload: Any, order_id: str) -> list[str]:
    """Shipment ids of records whose inboundOrderId is exactly ``order_id``.

    Walmart filters by inboundOrderId, but the read-back must not trust the filter: a
    record for another plan (or a record without the id) means the answer is not ours.
    """
    records = payload.get("payload") if isinstance(payload, Mapping) else None
    if isinstance(records, Mapping):
        records = records.get("inboundShipments") or records.get("shipments")
    ids: list[str] = []
    for record in records or []:
        if not isinstance(record, Mapping):
            continue
        if str(record.get("inboundOrderId") or "") != order_id:
            raise RuntimeError("WFS_READBACK_MISMATCH")
        sid = record.get("shipmentId")
        if isinstance(sid, str) and sid.strip() and sid not in ids:
            ids.append(sid.strip())
    return ids


def _items_of(payload: Any) -> list[Mapping[str, Any]]:
    items = payload.get("payload") if isinstance(payload, Mapping) else None
    if isinstance(items, Mapping):
        items = items.get("inboundShipmentItems") or items.get("items")
    return [item for item in items or [] if isinstance(item, Mapping)]


def _total_count(payload: Any) -> int | None:
    headers = payload.get("headers") if isinstance(payload, Mapping) else None
    total = headers.get("totalCount") if isinstance(headers, Mapping) else None
    return total if type(total) is int and total >= 0 else None


def _error_code(error: BaseException) -> str:
    code = getattr(error, "code", None)
    if isinstance(code, str) and code:
        return code
    text = str(error)
    return text if re.fullmatch(r"[A-Z0-9_]{4,64}", text) else "WALMART_GATEWAY_UNAVAILABLE"


class WalmartScfCreationGateway:
    enabled = True

    def __init__(
        self,
        *,
        session_factory: Callable[[], Any],
        gateway: GatewayLike,
        actor: Any,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleeper: Callable[[float], None] = time.sleep,
        pace_seconds: float = 1.3,
        store_code_map: Mapping[str, str] | None = None,
    ) -> None:
        self._factory = session_factory
        self._gateway = gateway
        self._actor = actor
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
        key = f"wfs-create:{order_id}"
        try:
            result = self._gateway.call(
                store.store_code,
                "wfs_inbound_shipment_create",
                actor=self._actor,
                body=body,
                approval_ref=f"wfs-ticket:{ticket_id}",
                idempotency_key=key,
            )
        except Exception as error:
            code = _error_code(error)
            if code in _LEDGER_BLOCKED:
                # An earlier attempt is open/unknown or already succeeded: only a read-back
                # may decide. Found -> resolve the ledger and use it; not found -> stay
                # UNKNOWN for a human (never a second POST on our own).
                ids = self._readback(store.store_code, order_id, ticket_id)
                if ids:
                    self._resolve(key, "ok", f"read-back found {len(ids)} shipment(s)")
                    return ids
                raise RuntimeError("WFS_CREATE_PENDING_REVIEW") from None
            # Gateway refusal or transport failure before/while posting: holds stay.
            raise RuntimeError(code) from None
        self._record(ticket_id, "wfs_inbound_shipment_create", result, order_id)
        if 200 <= result.status_code < 300:
            self._sleep(self._pace)
            ids = self._readback(store.store_code, order_id, ticket_id)
            if not ids:
                # Walmart accepted but nothing is visible yet: keep holds, let reconcile retry.
                raise RuntimeError("WFS_READBACK_EMPTY_AFTER_CREATE")
            self._verify_created(store.store_code, ids, body["orderItems"])
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
        key = f"wfs-create:{order_id}"
        if ids:
            self._resolve(key, "ok", f"reconcile found {len(ids)} shipment(s)")
        return ids or None

    def label(self, shipment_id: str, snapshot: dict) -> bytes:
        store = self._store(snapshot)
        count = self._carton_count(store.store_code, shipment_id)
        self._sleep(self._pace)
        result = self._call(
            store.store_code,
            "wfs_shipment_label",
            approval_ref=f"wfs-label:{shipment_id}",
            idempotency_key=f"wfs-label:{shipment_id}:{int(self._clock().timestamp())}",
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
        stamp = int(self._clock().timestamp() * 1000)
        result = self._call(
            store.store_code,
            "wfs_inbound_preview",
            approval_ref=f"wfs-preview:{store.store_code}",
            idempotency_key=f"wfs-preview:{store.store_code}:{stamp}",
            body=body,
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
        result = self._call(store_code, "inbound_shipments", params=params)
        self._record(ticket_id, "inbound_shipments", result, order_id)
        if not 200 <= result.status_code < 300:
            raise RuntimeError(f"WALMART_READBACK_HTTP_{result.status_code}")
        return _shipment_ids(result.data, order_id)

    def _call(
        self,
        store_code: str,
        operation: str,
        *,
        params: Mapping[str, Any] | None = None,
        body: Any = None,
        approval_ref: str | None = None,
        idempotency_key: str | None = None,
    ) -> WalmartResultLike:
        """One gateway call; refusals and transport failures surface as stable codes."""
        try:
            return self._gateway.call(
                store_code,
                operation,
                actor=self._actor,
                params=params,
                body=body,
                approval_ref=approval_ref,
                idempotency_key=idempotency_key,
            )
        except Exception as error:
            raise RuntimeError(_error_code(error)) from None

    def _items(self, store_code: str, shipment_id: str) -> list[Mapping[str, Any]]:
        """Every item row of a shipment (offset pagination, all-or-nothing)."""
        collected: list[Mapping[str, Any]] = []
        offset = 0
        for _ in range(ITEMS_MAX_PAGES):
            result = self._call(
                store_code,
                "inbound_shipment_items",
                params={"shipmentId": shipment_id, "limit": ITEMS_PAGE_SIZE, "offset": offset},
            )
            self._record(None, "inbound_shipment_items", result, shipment_id)
            if not 200 <= result.status_code < 300:
                raise RuntimeError(f"WALMART_ITEMS_HTTP_{result.status_code}")
            page = _items_of(result.data)
            collected.extend(page)
            total = _total_count(result.data)
            offset += len(page)
            if total is not None:
                if len(collected) >= total:
                    return collected
                if not page:
                    raise RuntimeError("WALMART_ITEMS_PAGE_INCOMPLETE")
            elif len(page) < ITEMS_PAGE_SIZE:
                return collected
            self._sleep(self._pace)
        raise RuntimeError("WALMART_ITEMS_PAGE_LIMIT")

    def _carton_count(self, store_code: str, shipment_id: str) -> int:
        total = 0
        for item in self._items(store_code, shipment_id):
            try:
                total += int(item.get("vendorPackQty") or 0)
            except (TypeError, ValueError):
                continue
        if total <= 0:
            raise RuntimeError("WALMART_CARTON_COUNT_UNKNOWN")
        return total

    def _verify_created(
        self, store_code: str, shipment_ids: list[str], order_items: list[dict[str, Any]]
    ) -> None:
        """Walmart's shipments must add up to what we asked for (GTIN, units, cartons).

        Walmart may split one plan into several shipments; the sums across them are
        compared per GTIN. Any difference leaves the ticket UNKNOWN for a human.
        """
        planned = {
            item["productId"]: (int(item["itemQty"]), int(item["vendorPackQty"]))
            for item in order_items
        }
        seen: dict[str, list[int]] = {}
        for shipment_id in shipment_ids:
            for item in self._items(store_code, shipment_id):
                gtin = str(item.get("gtin") or item.get("productId") or "")
                sku = str(item.get("sku") or item.get("vendorSku") or "")
                if not gtin:
                    gtin = next(
                        (g for g, _ in planned.items() if _sku_of(order_items, g) == sku), ""
                    )
                try:
                    qty = int(item.get("itemQty") or 0)
                    cartons = int(item.get("vendorPackQty") or 0)
                except (TypeError, ValueError):
                    raise RuntimeError("WFS_SHIPMENT_ITEM_INVALID") from None
                totals = seen.setdefault(gtin, [0, 0])
                totals[0] += qty
                totals[1] += cartons
        if set(seen) != set(planned):
            raise RuntimeError("WFS_SHIPMENT_GTIN_MISMATCH")
        for gtin, (qty, cartons) in planned.items():
            if seen[gtin][0] != qty or seen[gtin][1] != cartons:
                raise RuntimeError("WFS_SHIPMENT_QUANTITY_MISMATCH")

    def _resolve(self, key: str, outcome: str, note: str) -> None:
        ledger = getattr(self._gateway, "ledger", None)
        if ledger is None:
            return
        try:
            if ledger.status(key) in ("attempting", "unknown"):
                ledger.resolve(key, outcome=outcome, note=note)
        except Exception:
            # The ledger is evidence; failing to annotate it must not hide a found shipment.
            return

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


def _sku_of(order_items: list[dict[str, Any]], gtin: str) -> str:
    return next((str(i["sku"]) for i in order_items if i["productId"] == gtin), "")


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


GATEWAY_SWITCH = "SZZSBJ_WFS_CREATION_GATEWAY"
STORE_MAP = "SZZSBJ_WALMART_SCF_STORE_ID_MAP"


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

    The unified gateway reads the server's existing Walmart SCF variables itself
    (``/etc/szzsbj/walmart-scf.env``: STORE_ID_MAP / CVM_ROLE / TARGET_ROLE_ARN, plus
    ``SZZSBJ_WALMART_SCF_PROTOCOL`` and the signing key for protocol 3). This module adds:

      SZZSBJ_WFS_CREATION_GATEWAY=scf   the switch (anything else = disabled)

    Audit rows and the write ledger go to ``integration_walmart_calls`` /
    ``integration_walmart_write_ledger`` (``walmart_audit``). The creation worker is a
    system actor limited to ``WORKER_OPERATIONS``.
    """
    if os.environ.get(GATEWAY_SWITCH, "disabled").strip().lower() != "scf":
        return DisabledGateway()
    store_map = reviewed_store_map()
    if not store_map:
        return DisabledGateway()
    try:
        # Lazy: the shared gateway (PR #283) and the Tencent identity helpers are only
        # needed when the adapter is on; an older checkout without them stays disabled.
        from app.integrations.walmart.gateway import Actor, WalmartGateway
    except ImportError:
        return DisabledGateway()
    from app.modules.pmc_wfs.walmart_audit import DbAuditSink, DbWriteLedger

    try:
        gateway = WalmartGateway.from_env(
            audit=DbAuditSink(session_factory), ledger=DbWriteLedger(session_factory)
        )
    except Exception:
        return DisabledGateway()
    actor = Actor.system(
        WORKER_ACTOR_UID,
        operations=WORKER_OPERATIONS,
        store_codes=frozenset(store_map.values()),
    )
    return WalmartScfCreationGateway(
        session_factory=session_factory,
        gateway=gateway,
        actor=actor,
        store_code_map=store_map,
    )

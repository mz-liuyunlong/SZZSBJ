"""待创建货件页签（Rocky 2026-11-04）：提交中 / 创建失败 / 已创建未发货，以及按店铺的创建默认值。

* 一行 = 一个计划货件（票）。提交中 = 待人工批准、已批准待执行、提交中、结果待核实；
  创建失败 = Walmart 拒绝 / 没发出 / 10 次查询仍未查到；已创建未发货 = Walmart 已建货件，
  且 SP 发货单还没变成「已发货」。
* 「已发货」来自 SP 发货单，服务器暂时没有这份数据：``shipped_shipment_ids`` 是接入位置，
  现在返回空集合，所以已创建的货件都留在「已创建未发货」。不做 30 天过滤。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field
from sqlalchemy import func, select

from app.core.api import ApiError
from app.modules.data_pages.models import LingxingStoreDimension as Store
from app.modules.pmc_domestic.warehouse_schemas import Strict
from app.modules.pmc_wfs.creation_config import POLL_MAX_ATTEMPTS
from app.modules.pmc_wfs.creation_models import WfsCreation, WfsCreationTicket
from app.modules.pmc_wfs.creation_schemas import ShipmentRead
from app.modules.pmc_wfs.schemas import ReturnAddress

Tab = Literal["submitting", "failed", "created"]
TAB_STATES: dict[str, tuple[str, ...]] = {
    "submitting": ("QUEUED", "RUNNING", "UNKNOWN"),
    "failed": ("FAILED",),
    "created": ("SUCCEEDED",),
}


def shipped_shipment_ids(session, shipment_ids: list[str]) -> set[str]:
    """SP 发货单已发货的 Walmart 货件号。

    接入位置：SP 发货单同步上服务器后，在这里按货件号查发货单状态，返回已发货的货件号；
    已创建未发货页签据此移出。现在服务器没有 SP 发货单数据，返回空集合。
    """
    return set()


class TicketRow(Strict):
    operation_id: str
    order_id: str
    ticket_id: str
    number: int
    tab: Tab
    state: str
    status_label: str
    pks: list[str]
    skus: list[str]
    store_id: str | None
    store_name: str | None
    source_account_ref: str
    boxes: int
    units: int
    error_code: str | None = None
    error_message: str | None = None
    submissions: int = 0
    polls: int | None = None
    max_polls: int | None = None
    next_poll_at: datetime | None = None
    shipments: list[ShipmentRead] = Field(default_factory=list)
    expected_delivery_at: str | None = None
    created_at: datetime
    created_by: str
    approved_at: datetime | None = None
    approved_by: str | None = None
    approval_ref: str | None = None
    awaiting_approval: bool = False


class TicketList(Strict):
    items: list[TicketRow]
    total: int


class TicketCounts(Strict):
    submitting: int
    failed: int
    created: int


def _label(op, ticket) -> str:
    if op.state == "AWAITING_APPROVAL":
        return "待人工批准"
    polling = ticket.result.get("polling")
    if ticket.state == "QUEUED":
        return "已批准待执行"
    if ticket.state == "RUNNING" and polling:
        return (
            f"提交中 · 已查询 {polling.get('count', 0)}/{polling.get('max', POLL_MAX_ATTEMPTS)} 次"
        )
    if ticket.state == "RUNNING":
        return "提交中"
    if ticket.state == "UNKNOWN":
        return "结果待核实"
    if ticket.state == "FAILED":
        return {
            "WFS_RESULT_TIMEOUT": "查询超时",
            "WFS_PLATFORM_REJECTED": "Walmart 拒绝",
        }.get(ticket.error_code or "", "创建失败")
    return "已创建未发货"


class CreationBoard:
    def __init__(self, session, accounts, stores):
        self.s, self.accounts, self.stores = session, accounts, stores

    def _pairs(self, tab: str, store_id: str | None):
        stmt = (
            select(WfsCreation, WfsCreationTicket)
            .join(WfsCreationTicket, WfsCreationTicket.operation_id == WfsCreation.id)
            .where(
                WfsCreation.source_account_ref.in_(self.accounts),
                WfsCreationTicket.state.in_(TAB_STATES[tab]),
            )
            .order_by(WfsCreation.created_at.desc(), WfsCreationTicket.number)
        )
        if self.stores is not None:
            stmt = stmt.where(WfsCreation.store_id.in_(self.stores))
        if store_id:
            stmt = stmt.where(WfsCreation.store_id == store_id)
        pairs = list(self.s.execute(stmt).all())
        if tab == "created":
            ids = [sid for _, t in pairs for sid in t.result.get("labels", {})]
            shipped = shipped_shipment_ids(self.s, ids) if ids else set()
            pairs = [
                (op, t)
                for op, t in pairs
                if not t.result.get("labels") or set(t.result["labels"]) - shipped
            ]
        return pairs

    @staticmethod
    def _row(tab, op, ticket) -> TicketRow:
        ranges = ticket.allocation.get("ranges", [])
        order = op.snapshot.get("order") or {}
        shipments = ticket.result.get("shipments", {})
        polling = ticket.result.get("polling") or {}
        return TicketRow(
            operation_id=str(op.id),
            order_id=str(op.order_id),
            ticket_id=str(ticket.id),
            number=ticket.number,
            tab=tab,
            state=ticket.state,
            status_label=_label(op, ticket),
            pks=list(dict.fromkeys(r.get("pk", "") for r in ranges if r.get("pk"))),
            skus=list(dict.fromkeys(r.get("sku", "") for r in ranges if r.get("sku"))),
            store_id=op.store_id,
            store_name=order.get("store_name"),
            source_account_ref=op.source_account_ref,
            boxes=int(ticket.allocation.get("boxes", 0)),
            units=int(ticket.allocation.get("units", 0)),
            error_code=ticket.error_code,
            error_message=ticket.result.get("error_message"),
            submissions=int(ticket.result.get("submissions", 0)),
            polls=polling.get("count") if polling else None,
            max_polls=polling.get("max", POLL_MAX_ATTEMPTS) if polling else None,
            next_poll_at=polling.get("next_at") if polling else None,
            shipments=[
                ShipmentRead(
                    shipment_id=sid,
                    label_state=value["state"],
                    fc=(shipments.get(sid) or {}).get("fc"),
                )
                for sid, value in ticket.result.get("labels", {}).items()
            ],
            expected_delivery_at=op.snapshot.get("expected_delivery_at"),
            created_at=op.created_at,
            created_by=op.actor_uid,
            approved_at=op.approved_at,
            approved_by=op.approved_by,
            approval_ref=op.approval_ref,
            awaiting_approval=op.state == "AWAITING_APPROVAL",
        )

    @staticmethod
    def _matches(row: TicketRow, keyword: str) -> bool:
        if not keyword:
            return True
        needle = keyword.strip().lower()
        haystack = [
            *row.pks,
            *row.skus,
            *(s.shipment_id for s in row.shipments),
            row.operation_id,
            row.store_name or "",
        ]
        return any(needle in value.lower() for value in haystack)

    def list(self, tab: str, store_id: str | None, keyword: str, page: int, size: int):
        rows = [self._row(tab, op, t) for op, t in self._pairs(tab, store_id)]
        rows = [r for r in rows if self._matches(r, keyword)]
        start = (page - 1) * size
        return TicketList(items=rows[start : start + size], total=len(rows))

    def counts(self, store_id: str | None, keyword: str):
        values = {}
        for tab in TAB_STATES:
            rows = [self._row(tab, op, t) for op, t in self._pairs(tab, store_id)]
            values[tab] = sum(self._matches(r, keyword) for r in rows)
        return TicketCounts(**values)


# ----- 创建默认值（按店铺） ---------------------------------------------------------------


class StoreDefaultsRow(Strict):
    store_id: str
    store_name: str | None
    source_account_ref: str
    transport: str
    ship_date_offset: int
    pallet_boxes: int
    mixed_boxes: int
    carrier_opt: str
    its: bool
    return_address: ReturnAddress | None = None
    level: Literal["store", "account", "default"]
    updated_by: str | None = None
    updated_at: datetime | None = None


class StoreDefaultsList(Strict):
    items: list[StoreDefaultsRow]


class StoreDefaultsUpdate(Strict):
    transport: Literal["LTL", "SMALL_PARCEL", "FTL"]
    ship_date_offset: int = Field(ge=0, le=120)
    pallet_boxes: int = Field(ge=1, le=100)
    mixed_boxes: int = Field(ge=0, le=1000)
    carrier_opt: Literal["own", "wm"]
    its: bool = False
    return_address: ReturnAddress | None = None
    reason: str = Field(default="", max_length=500)


class StoreDefaults:
    def __init__(self, session, accounts, stores):
        self.s, self.accounts, self.stores = session, accounts, stores

    def _stores(self) -> dict[str, tuple[str, str | None]]:
        name = func.nullif(func.trim(Store.store_name), "")
        stmt = (
            select(Store.store_id, func.max(Store.source_account_ref), func.max(name))
            .where(Store.source_account_ref.in_(self.accounts), func.trim(Store.store_id) != "")
            .group_by(Store.store_id)
            .order_by(Store.store_id)
        )
        if self.stores is not None:
            stmt = stmt.where(Store.store_id.in_(self.stores))
        return {sid: (account, label) for sid, account, label in self.s.execute(stmt).all()}

    def list(self) -> StoreDefaultsList:
        from app.modules.pmc_wfs.creation_service import creation_defaults
        from app.modules.pmc_wfs.settings_models import WfsStoreCreationDefaults

        saved = {
            (r.source_account_ref, r.store_id): r
            for r in self.s.scalars(
                select(WfsStoreCreationDefaults).where(
                    WfsStoreCreationDefaults.source_account_ref.in_(self.accounts)
                )
            )
        }
        items = []
        for sid, (account, label) in self._stores().items():
            values = creation_defaults(self.s, account, sid)
            row = saved.get((account, sid))
            items.append(
                StoreDefaultsRow(
                    store_id=sid,
                    store_name=label,
                    source_account_ref=account,
                    **{k: v for k, v in values.items() if k not in ("saved",)},
                    updated_by=row.updated_by if row else None,
                    updated_at=row.updated_at if row else None,
                )
            )
        return StoreDefaultsList(items=items)

    def update(self, store_id: str, cmd: StoreDefaultsUpdate, actor: str) -> StoreDefaultsRow:
        from app.modules.pmc_wfs.settings_models import WfsSettingsChange, WfsStoreCreationDefaults

        stores = self._stores()
        if store_id not in stores:
            raise ApiError(code="DATA_SCOPE_DENIED", status_code=403)
        account, _ = stores[store_id]
        values = cmd.model_dump(mode="json", exclude={"reason"})
        row = self.s.get(WfsStoreCreationDefaults, (account, store_id))
        before = None
        if row is None:
            self.s.add(
                WfsStoreCreationDefaults(
                    source_account_ref=account, store_id=store_id, updated_by=actor, **values
                )
            )
        else:
            before = {k: getattr(row, k) for k in values}
            for key, value in values.items():
                setattr(row, key, value)
            row.updated_by, row.updated_at = actor, datetime.now(UTC)
        self.s.add(
            WfsSettingsChange(
                entity="creation_defaults",
                entity_key=f"{account}:{store_id}"[:128],
                before_json=before,
                after_json=values,
                reason=cmd.reason or "按店铺设置创建默认值",
                actor=actor,
            )
        )
        self.s.commit()
        return next(r for r in self.list().items if r.store_id == store_id)

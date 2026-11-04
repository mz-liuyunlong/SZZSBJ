"""待创建货件页签（Rocky 2026-11-04）：提交中 / 创建失败 / 已创建未发货，以及按店铺的创建默认值。

* 一行 = 一个计划货件（票）。提交中 = 待人工批准、已批准待执行、提交中、结果待核实；
  创建失败 = Walmart 拒绝 / 没发出 / 10 次查询仍未查到；已创建未发货 = Walmart 已建货件，
  且 SP 发货单还没变成「已发货」。
* 「已发货」= 领星 SP 发货单里有这个货件号（``shipping_codes_for``：当前发布批次的
  ``ods_lingxing_wfs_shipping_lists.cargo_codes`` 反查），几票可以共用一张发货单。

单列表（Rocky 2026-11-04 第 12–16 条 + 拆票）：``CreationRows`` 把「待创建」（每个还有可用
箱子的打包单一行）和已提交的（每票每个货件一行）合成一个列表，每行带状态：
待创建 / 待批准 / 提交中 / 创建失败 / 已创建未发货 / 已发货。旧的页签接口保留。
"""

from __future__ import annotations

import typing
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import Field
from sqlalchemy import func, select

from app.core.api import ApiError
from app.modules.data_pages.models import LingxingStoreDimension as Store
from app.modules.pmc_domestic.warehouse_schemas import Strict
from app.modules.pmc_wfs.creation_config import POLL_MAX_ATTEMPTS
from app.modules.pmc_wfs.creation_models import WfsCreation, WfsCreationTicket
from app.modules.pmc_wfs.creation_schemas import ShipmentRead
from app.modules.pmc_wfs.schemas import PendingRow, ReturnAddress

Tab = Literal["submitting", "failed", "created"]
TAB_STATES: dict[str, tuple[str, ...]] = {
    "submitting": ("QUEUED", "RUNNING", "UNKNOWN"),
    "failed": ("FAILED",),
    "created": ("SUCCEEDED",),
}


DEMO_SEED_KEY = "demo_seed"  # 本机模拟数据（seed 脚本）写在操作快照里的标记
SIMULATED_SHIPPING = "simulated_shipping"  # 模拟数据的 SP 发货单号：{货件号: DEMO-SP…}


def shipping_codes_for(session, accounts, pairs) -> dict[str, str]:
    """货件号 → 领星 SP 发货单号（有发货单号 = 已发货）。

    来源：每个账号当前发布（``gov_wfs_board_publications.is_current``）所用的发货单批次
    ``shipping_run_id``，在 ``ods_lingxing_wfs_shipping_lists`` 里按 ``cargo_codes`` 反查。
    本机模拟数据（快照带 ``demo_seed``）另外认 ``result.simulated_shipping``；真实数据不认。
    """
    from app.modules.pmc_wfs.lingxing_models import (
        LingxingWfsShippingListOds,
        WfsBoardPublication,
    )

    wanted = {sid for _, t in pairs for sid in _shipment_ids(t)}
    found: dict[str, str] = {}
    if not wanted:
        return found
    runs = select(WfsBoardPublication.shipping_run_id).where(
        WfsBoardPublication.is_current.is_(True),
        WfsBoardPublication.shipping_run_id.is_not(None),
        WfsBoardPublication.source_account_ref.in_(accounts),
    )
    rows = session.execute(
        select(LingxingWfsShippingListOds.shipping_code, LingxingWfsShippingListOds.cargo_codes)
        .where(
            LingxingWfsShippingListOds.run_id.in_(runs),
            LingxingWfsShippingListOds.source_account_ref.in_(accounts),
        )
        .order_by(LingxingWfsShippingListOds.shipping_code)
    )
    for code, cargos in rows:
        for sid in cargos or []:
            if sid in wanted:
                found.setdefault(sid, code)
    for op, ticket in pairs:
        if op.snapshot.get(DEMO_SEED_KEY):
            for sid, code in (ticket.result.get(SIMULATED_SHIPPING) or {}).items():
                if sid in wanted and str(code).startswith("DEMO-SP"):
                    found[sid] = code
    return found


def shipped_shipment_ids(session, shipment_ids: list[str], accounts=None, pairs=None) -> set[str]:
    """SP 发货单已发货的 Walmart 货件号（旧页签用；有 SP 发货单号即已发货）。"""
    if accounts is None or pairs is None:
        return set()
    return set(shipping_codes_for(session, accounts, pairs)) & set(shipment_ids)


def _shipment_ids(ticket) -> list[str]:
    result = ticket.result or {}
    return list(dict.fromkeys([*(result.get("shipments") or {}), *(result.get("labels") or {})]))


class TicketRow(Strict):
    operation_id: str
    order_id: str
    ticket_id: str
    number: int
    inbound_order_id: str | None = None  # 我方单号 = Walmart inboundOrderId（提交后才有）
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
            shipped = shipped_shipment_ids(self.s, ids, self.accounts, pairs) if ids else set()
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
            inbound_order_id=ticket.inbound_order_id,
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
            row.inbound_order_id or "",
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


# ----- 单列表（一行 = 一个打包单 × 一个货件）----------------------------------------------

# Rocky 2026-11-04：取消「待批准」，5 种状态。之前提交、还在等批准的旧记录算「提交中」。
RowStatus = Literal["pending", "submitting", "failed", "created", "shipped"]
ROW_STATUSES: tuple[str, ...] = typing.get_args(RowStatus)
DEFAULT_STATUSES: tuple[str, ...] = ROW_STATUSES[:4]  # 已发货默认隐藏（「显示已发货」）
STATUS_TEXT = {
    "pending": "待创建",
    "submitting": "提交中",
    "failed": "创建失败",
    "created": "已创建未发货",
    "shipped": "已发货",
}


class BoardRow(Strict):
    key: str
    kind: Literal["pending", "shipment"]
    status: RowStatus
    status_label: str
    detail: str | None = None  # 提交中「已查询 x/10 次」、失败原因等
    sort_at: datetime | None = None
    order_id: str
    pk: str
    store_id: str | None = None
    store_name: str | None = None
    sku: str | None = None
    product_name: str | None = None
    item_id: str | None = None
    gtin: str | None = None
    business_test: bool = False
    # kind = pending：打包单（勾选后「创建 WFS 货件」，和原来的待创建页签一样）
    pending: PendingRow | None = None
    # kind = shipment：这一票（一票多个货件时每个货件一行，票的内容相同）
    ticket: TicketRow | None = None
    shipment_id: str | None = None
    fc: str | None = None
    label_state: str | None = None
    print_count: int = 0
    printed_at: datetime | None = None
    printed_by: str | None = None
    shipping_code: str | None = None  # 领星 SP 发货单号
    demo: bool = False  # 本机模拟数据（DEMO-）


class BoardRowCounts(Strict):
    pending: int = 0
    submitting: int = 0
    failed: int = 0
    created: int = 0
    shipped: int = 0


class BoardRowList(Strict):
    items: list[BoardRow]
    total: int
    counts: BoardRowCounts


def _ticket_status(op, ticket) -> str:
    if ticket.state == "FAILED":
        return "failed"
    if ticket.state == "SUCCEEDED":
        return "created"
    return "submitting"


def _completed_on(snapshot_order: dict):
    value = ((snapshot_order or {}).get("box_set") or {}).get("completed_at")
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


class CreationRows:
    """``GET /pending-packing/rows``：待创建行 + 货件行，合在一起按时间倒序、分页。"""

    def __init__(self, base):
        self.base = base
        self.s, self.accounts, self.stores = base.session, base.accounts, base.stores

    def _pending(self, query) -> list[BoardRow]:
        from app.modules.pmc_wfs.schemas import PendingFilter

        flt = PendingFilter(
            store_id=query.store_id,
            keyword=query.keyword,
            only_test=query.only_test,
            arrangement="open",
            completed_from=query.completed_from,
            completed_to=query.completed_to,
        )
        orders = list(self.s.scalars(self.base.repo.query(flt, self.accounts, self.stores)))
        rows = []
        for row in self.base._filter_rows(flt, orders):
            order = row.order
            rows.append(
                BoardRow(
                    key=f"pending:{order.id}",
                    kind="pending",
                    status="pending",
                    status_label=STATUS_TEXT["pending"],
                    detail=f"可建 {row.available_boxes} 箱 / {row.available_units} 件",
                    sort_at=order.box_set.completed_at if order.box_set else None,
                    order_id=str(order.id),
                    pk=order.pk,
                    store_id=order.store_id,
                    store_name=order.store_name,
                    sku=order.sku,
                    product_name=order.product_name,
                    item_id=order.item_id,
                    gtin=order.gtin,
                    business_test=row.business_test,
                    pending=row,
                    demo=order.pk.startswith("DEMO-"),
                )
            )
        return rows

    def _pairs(self, query):
        stmt = (
            select(WfsCreation, WfsCreationTicket)
            .join(WfsCreationTicket, WfsCreationTicket.operation_id == WfsCreation.id)
            .where(WfsCreation.source_account_ref.in_(self.accounts))
            .order_by(WfsCreation.created_at.desc(), WfsCreationTicket.number)
        )
        if self.stores is not None:
            stmt = stmt.where(WfsCreation.store_id.in_(self.stores))
        if query.store_id:
            stmt = stmt.where(WfsCreation.store_id == query.store_id)
        pairs = []
        for op, ticket in self.s.execute(stmt).all():
            order = op.snapshot.get("order") or {}
            if query.only_test and not order.get("is_test"):
                continue
            day = _completed_on(order)
            if query.completed_from and (day is None or day < query.completed_from):
                continue
            if query.completed_to and (day is None or day > query.completed_to):
                continue
            pairs.append((op, ticket))
        return pairs

    def _shipments(self, query) -> list[BoardRow]:
        pairs = self._pairs(query)
        codes = shipping_codes_for(self.s, self.accounts, pairs)
        rows = []
        for op, ticket in pairs:
            status = _ticket_status(op, ticket)
            tab = {"failed": "failed", "created": "created"}.get(status, "submitting")
            info = CreationBoard._row(tab, op, ticket)
            order = op.snapshot.get("order") or {}
            pk = info.pks[0] if info.pks else str(order.get("pk") or "")
            detail = None
            if status == "submitting":
                detail = info.status_label
            elif status == "failed":
                detail = info.error_message or info.error_code
            common = dict(
                kind="shipment",
                sort_at=op.created_at,
                order_id=str(op.order_id),
                pk=pk,
                store_id=op.store_id,
                store_name=order.get("store_name"),
                sku=", ".join(info.skus) or order.get("sku"),
                product_name=order.get("product_name"),
                item_id=order.get("item_id"),
                gtin=order.get("gtin"),
                business_test=bool(order.get("is_test")),
                ticket=info,
                demo=bool(op.snapshot.get(DEMO_SEED_KEY)),
            )
            sids = _shipment_ids(ticket) if status == "created" else []
            if not sids:
                rows.append(
                    BoardRow(
                        key=f"ticket:{ticket.id}",
                        status=status,
                        status_label=STATUS_TEXT[status],
                        detail=detail,
                        **common,
                    )
                )
                continue
            shipments = ticket.result.get("shipments") or {}
            labels = ticket.result.get("labels") or {}
            for sid in sids:
                label = labels.get(sid) or {}
                code = codes.get(sid)
                state = "shipped" if code else "created"
                fc = (shipments.get(sid) or {}).get("fc")
                rows.append(
                    BoardRow(
                        key=f"ticket:{ticket.id}:{sid}",
                        status=state,
                        status_label=STATUS_TEXT[state],
                        detail=None if fc else "FC 待返回",
                        shipment_id=sid,
                        fc=fc,
                        label_state=label.get("state"),
                        print_count=int(label.get("prints", 0)),
                        printed_at=label.get("printed_at"),
                        printed_by=label.get("printed_by"),
                        shipping_code=code,
                        **common,
                    )
                )
        return rows

    @staticmethod
    def _matches(row: BoardRow, keyword: str) -> bool:
        if not keyword or row.kind == "pending":  # pending rows: already filtered in SQL
            return True
        needle = keyword.strip().lower()
        values = [row.pk, row.shipment_id or "", row.shipping_code or ""]
        return any(needle in v.lower() for v in values) or CreationBoard._matches(
            row.ticket, keyword
        )

    def list(self, query) -> BoardRowList:
        rows = [*self._pending(query), *self._shipments(query)]
        rows = [r for r in rows if self._matches(r, query.keyword)]
        counts = BoardRowCounts(**{k: sum(r.status == k for r in rows) for k in ROW_STATUSES})
        wanted = set(query.statuses or DEFAULT_STATUSES)
        if query.show_shipped:
            wanted.add("shipped")
        else:
            wanted.discard("shipped")
        rows = [r for r in rows if r.status in wanted]
        floor = datetime.min.replace(tzinfo=UTC)
        rows.sort(key=lambda r: _aware(r.sort_at) or floor, reverse=True)
        start = (query.page - 1) * query.page_size
        return BoardRowList(
            items=rows[start : start + query.page_size], total=len(rows), counts=counts
        )


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class RowQuery(Strict):
    store_id: str | None = Field(default=None, max_length=64)
    keyword: str = Field(default="", max_length=200)
    only_test: bool = False
    completed_from: date | None = None
    completed_to: date | None = None
    statuses: list[RowStatus] = Field(default_factory=list)
    show_shipped: bool = False
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


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
    level: Literal["store", "common", "account", "default"]
    updated_by: str | None = None
    updated_at: datetime | None = None


class StoreDefaultsList(Strict):
    # 「全部店铺通用」：每个来源账号一行（store_id = "*"），排在抽屉第一行。
    common: list[StoreDefaultsRow] = Field(default_factory=list)
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
    # 只用于「全部店铺通用」（store_id = "*"）：能看到多个来源账号时指明是哪一个。
    source_account_ref: str | None = Field(default=None, max_length=128)


DEFAULT_REASONS = {True: "设置全部店铺通用的创建默认值", False: "按店铺设置创建默认值"}


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
        from app.modules.pmc_wfs.settings_models import COMMON_STORE

        stores = self._stores()
        common = []
        with_stores = {a for a, _ in stores.values()}
        for account in sorted(with_stores or set(self.accounts)):
            values = creation_defaults(self.s, account, None)
            row = saved.get((account, COMMON_STORE))
            common.append(
                StoreDefaultsRow(
                    store_id=COMMON_STORE,
                    store_name="全部店铺通用",
                    source_account_ref=account,
                    **{k: v for k, v in values.items() if k not in ("saved",)},
                    updated_by=row.updated_by if row else None,
                    updated_at=row.updated_at if row else None,
                )
            )
        items = []
        for sid, (account, label) in stores.items():
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
        return StoreDefaultsList(common=common, items=items)

    def update(self, store_id: str, cmd: StoreDefaultsUpdate, actor: str) -> StoreDefaultsRow:
        from app.modules.pmc_wfs.settings_models import (
            COMMON_STORE,
            WfsSettingsChange,
            WfsStoreCreationDefaults,
        )

        if store_id == COMMON_STORE:
            account = self._common_account(cmd.source_account_ref)
        else:
            stores = self._stores()
            if store_id not in stores:
                raise ApiError(code="DATA_SCOPE_DENIED", status_code=403)
            account, _ = stores[store_id]
        values = cmd.model_dump(mode="json", exclude={"reason", "source_account_ref"})
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
                reason=cmd.reason or DEFAULT_REASONS[store_id == COMMON_STORE],
                actor=actor,
            )
        )
        self.s.commit()
        listed = self.list()
        if store_id == COMMON_STORE:
            return next(r for r in listed.common if r.source_account_ref == account)
        return next(r for r in listed.items if r.store_id == store_id)

    def _common_account(self, requested: str | None) -> str:
        """「全部店铺通用」属于一个来源账号：只有一个时自动用它，多个时要指明。"""
        accounts = sorted(self.accounts)
        if requested:
            if requested not in accounts:
                raise ApiError(code="DATA_SCOPE_DENIED", status_code=403)
            return requested
        if len(accounts) != 1:
            raise ApiError(
                code="WFS_SETTINGS_ACCOUNT_REQUIRED",
                status_code=409,
                message="当前账号能看到多个来源账号，请指明「全部店铺通用」属于哪一个",
            )
        return accounts[0]

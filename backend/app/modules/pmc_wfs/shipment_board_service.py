"""M2 board: Lingxing-published cargos are the truth; creation facts are linked, not the source.

Rows come from the current ``mart_wfs_shipment_board`` version per account. A ticket this
system created whose shipment id has not yet appeared in Lingxing is shown as a
``creation_only`` row with ``lingxing_sync_status = PENDING`` so nothing disappears between
creation and the next Lingxing pull. Walmart receipt detail is a later slice.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text

from app.core.api import ApiError
from app.modules.data_pages.models import LingxingStoreDimension as Store
from app.modules.pmc_domestic.packing_models import PackingOrder
from app.modules.pmc_domestic.packing_service import missing
from app.modules.pmc_wfs.arrival_rules import BUCKET_LABELS, parse_date
from app.modules.pmc_wfs.board_lookups import item_ids_by_store_msku, owners_by_sku
from app.modules.pmc_wfs.board_view import (
    RULE_VERSION,
    ShipmentView,
    WfsException,
    WfsRules,
    big_gaps,
    build_exceptions,
    build_view,
    product_views,
)
from app.modules.pmc_wfs.creation_models import WfsCreation, WfsCreationTicket
from app.modules.pmc_wfs.lingxing_models import WfsBoardPublication
from app.modules.pmc_wfs.lingxing_models import WfsShipmentBoardRow as Mart
from app.modules.pmc_wfs.repository import require_creation_schema
from app.modules.pmc_wfs.shipment_board_schemas import (
    STATUS_LABELS,
    BoardFreshness,
    ProductBoardList,
    ProductBoardRow,
    ProductShipmentLine,
    ShipmentBoardDetail,
    ShipmentBoardFilter,
    ShipmentBoardList,
    ShipmentBoardOptions,
    ShipmentBoardQuery,
    ShipmentBoardRow,
    ShipmentBoardSummary,
    ShipmentException,
    ShipmentGoodsLine,
    ShipmentItemLine,
    StoreOption,
)

STALE_AFTER = timedelta(hours=24)
BUSINESS_TZ = ZoneInfo("Asia/Shanghai")
RULES = WfsRules()  # 8088 defaults; editable thresholds arrive with the WFS settings page.
BOARD_TABLES = ("gov_wfs_board_publications", "mart_wfs_shipment_board")


def require_board_schema(session) -> None:
    if not all(
        session.scalar(text("SELECT to_regclass(:name)"), {"name": n}) for n in BOARD_TABLES
    ):
        raise ApiError(
            code="WFS_BOARD_SCHEMA_NOT_READY",
            status_code=503,
            message="WFS 货件看板数据库结构尚未更新，请先完成迁移后重试",
        )


def business_today() -> date:
    return datetime.now(BUSINESS_TZ).date()


def _publication_data_day(pub: WfsBoardPublication) -> date | None:
    raw = (pub.quality_report or {}).get("as_of")
    try:
        return date.fromisoformat(raw) if isinstance(raw, str) else None
    except ValueError:
        return None


def _derived_fields(view: ShipmentView, owners: list[str], kinds: list[str]) -> dict[str, Any]:
    return {
        "owners": owners,
        "region": view.region,
        "its_inferred": view.its_inferred,
        "baseline_units": view.baseline,
        "baseline_from": view.baseline_from,
        "diff_units": view.diff,
        "boxes": view.boxes,
        "eta": parse_date(view.eta),
        "eta_source": view.eta_source or None,
        "eta_source_label": view.eta_source_label or None,
        "eta_passed_days": view.eta_passed,
        "sellable_date": parse_date(view.sellable),
        "sellable_real": view.sellable_real,
        "arrival_bucket": view.arrival_bucket,
        "shipped_out": view.shipped_out,
        "carrier_delivered_at": view.carrier_delivered_at or None,
        "walmart_signed_date": parse_date(view.d0_real),
        "walmart_first_receipt": parse_date(view.wm_first),
        "walmart_last_receipt": parse_date(view.wm_last),
        "walmart_receiving": view.wm_receiving,
        "walmart_done": view.wm_done,
        "d0": parse_date(view.d0),
        "d0_real": bool(view.d0_real),
        "days_since_d0": view.d_n,
        "external": view.external,
        "age_days": view.age_days,
        "exception_types": kinds,
    }


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class _Creation:
    """Creation facts keyed by shipment id (label key) for linkage."""

    def __init__(self, session, accounts, stores) -> None:
        self.by_shipment: dict[str, dict[str, Any]] = {}
        stmt = select(WfsCreation).where(WfsCreation.source_account_ref.in_(accounts))
        if stores is not None:
            stmt = stmt.where(WfsCreation.store_id.in_(stores))
        ops = list(session.scalars(stmt))
        if not ops:
            return
        tickets = list(
            session.scalars(
                select(WfsCreationTicket)
                .where(WfsCreationTicket.operation_id.in_([op.id for op in ops]))
                .order_by(WfsCreationTicket.operation_id, WfsCreationTicket.number)
            )
        )
        by_op = {op.id: op for op in ops}
        orders = {
            row.id: row
            for row in session.scalars(
                select(PackingOrder).where(PackingOrder.id.in_({op.order_id for op in ops}))
            )
        }
        for ticket in tickets:
            labels = ticket.result.get("labels") or {}
            op = by_op[ticket.operation_id]
            order = orders.get(op.order_id)
            snap = op.snapshot if isinstance(op.snapshot, dict) else {}
            snap_order = snap.get("order") or {}
            for shipment_id, meta in labels.items():
                if not isinstance(shipment_id, str) or not shipment_id.strip():
                    continue
                state = meta.get("state", "PENDING") if isinstance(meta, dict) else "PENDING"
                self.by_shipment[shipment_id] = {
                    "operation_id": op.id,
                    "ticket_id": ticket.id,
                    "ticket_number": ticket.number,
                    "order_id": op.order_id,
                    "store_id": op.store_id,
                    "store_name": snap_order.get("store_name"),
                    "pk": (order.pk if order else None) or snap_order.get("pk"),
                    "business_test": (
                        order.business_test if order else bool(snap_order.get("business_test"))
                    ),
                    "its": bool(snap.get("its")),
                    "sku": snap_order.get("sku"),
                    "product_name": snap_order.get("product_name"),
                    "item_id": snap_order.get("item_id"),
                    "gtin": snap_order.get("gtin"),
                    "msku": snap_order.get("msku"),
                    "label_state": state if state in {"PENDING", "READY", "FAILED"} else "PENDING",
                    "creation_state": op.state,
                    "ticket_state": ticket.state,
                    "created_at": op.created_at,
                    "return_address": snap.get("return_address"),
                    "expected_delivery_at": snap.get("expected_delivery_at"),
                    "allocation": ticket.allocation,
                }


class ShipmentBoardService:
    def __init__(self, session, accounts, stores):
        self.session = session
        self.accounts = accounts
        self.stores = stores
        self._publications: list[WfsBoardPublication] | None = None
        self._rows: list[ShipmentBoardRow] | None = None
        self._mart_by_id: dict[str, Mart] = {}
        self._creation_by_id: dict[str, dict[str, Any]] = {}
        self._view_by_id: dict[str, ShipmentView] = {}
        self._exceptions_by_code: dict[str, list[WfsException]] = {}
        self._owners_by_sku: dict[str, list[str]] = {}
        self._today: date | None = None

    @property
    def today(self) -> date:
        """Rule date, as in 8088 (``TODAY = 数据日``): the data day of the newest current
        publication; the Shanghai calendar day when nothing is published yet."""
        if self._today is None:
            days = [d for p in self._current_publications() if (d := _publication_data_day(p))]
            self._today = max(days) if days else business_today()
        return self._today

    @today.setter
    def today(self, value: date) -> None:
        self._today = value

    # ---- loading -------------------------------------------------------------------

    def _current_publications(self) -> list[WfsBoardPublication]:
        if self._publications is None:
            require_board_schema(self.session)
            self._publications = list(
                self.session.scalars(
                    select(WfsBoardPublication).where(
                        WfsBoardPublication.source_account_ref.in_(self.accounts),
                        WfsBoardPublication.is_current.is_(True),
                    )
                )
            )
        return self._publications

    def freshness(self) -> BoardFreshness:
        pubs = self._current_publications()
        if not pubs:
            return BoardFreshness(stale=True)
        latest = max(pubs, key=lambda p: p.source_observed_at)
        observed = _aware(latest.source_observed_at)
        return BoardFreshness(
            publication_id=latest.id,
            source_observed_at=observed,
            published_at=_aware(latest.published_at),
            coverage_start=latest.coverage_start,
            coverage_end=latest.coverage_end,
            stale=observed is None or datetime.now(UTC) - observed > STALE_AFTER,
        )

    def _expand(self) -> list[ShipmentBoardRow]:
        if self._rows is not None:
            return self._rows
        pubs = self._current_publications()
        require_creation_schema(self.session)
        creation = _Creation(self.session, self.accounts, self.stores)
        rows: list[ShipmentBoardRow] = []
        seen_shipments: set[str] = set()
        if pubs:
            stmt = select(Mart).where(Mart.publication_id.in_([p.id for p in pubs]))
            if self.stores is not None:
                stmt = stmt.where(Mart.store_id.in_(self.stores))
            marts = list(self.session.scalars(stmt))
            self._load_views(marts)
            for mart in marts:
                shipment_id = mart.cargo_code or mart.cargo_id
                link = creation.by_shipment.get(shipment_id)
                row_id = f"lx:{mart.publication_id}:{mart.cargo_id}"
                self._mart_by_id[row_id] = mart
                if link:
                    self._creation_by_id[row_id] = link
                goods = (mart.payload_json or {}).get("goods") or []
                first = goods[0] if goods else {}
                view = self._view_by_id[row_id]
                owners = sorted(
                    {o for g in goods for o in self._owners_by_sku.get(g.get("sku") or "", [])}
                )
                kinds = [e.type for e in self._exceptions_by_code.get(view.code, [])]
                first_item = view.items[0] if view.items else None
                rows.append(
                    ShipmentBoardRow(
                        id=row_id,
                        source="lingxing",
                        shipment_id=shipment_id,
                        inbound_order_id=mart.in_bound_order_id,
                        store_id=mart.store_id or (link or {}).get("store_id") or "",
                        store_name=mart.store_name or (link or {}).get("store_name"),
                        status=mart.status,
                        status_name=mart.status_name,
                        status_label=STATUS_LABELS.get(
                            mart.status or -1, mart.status_name or "未知"
                        ),
                        cargo_sync_status=mart.cargo_sync_status,
                        lingxing_sync_status="SYNCED",
                        business_test=bool((link or {}).get("business_test", False))
                        or view.is_test,
                        its=(link or {}).get("its", view.its_inferred),
                        pk=(link or {}).get("pk"),
                        sku=first.get("sku") or (link or {}).get("sku"),
                        product_name=first.get("product_name") or (link or {}).get("product_name"),
                        item_id=(first_item.item_id if first_item else None)
                        or (link or {}).get("item_id"),
                        gtin=first.get("gtin") or (link or {}).get("gtin"),
                        msku=first.get("msku") or (link or {}).get("msku"),
                        sku_count=mart.sku_count,
                        declared_units=mart.declared_units,
                        shipped_units=mart.shipped_units,
                        received_units=mart.received_units,
                        damaged_units=mart.damaged_units,
                        logistics_code=mart.logistics_code,
                        shipping_codes=list(mart.shipping_codes or []),
                        shipping_status=mart.shipping_status,
                        warehouse_id=mart.warehouse_id,
                        actual_delivery_date=mart.actual_delivery_date,
                        arrival_date=mart.arrival_date,
                        expected_arrival_date=mart.expected_arrival_date,
                        logistics_numbers=list(mart.logistics_numbers or []),
                        created_at=_aware(mart.cargo_created_at),
                        updated_at=_aware(mart.cargo_updated_at),
                        to_await_at=_aware(mart.to_await_at),
                        to_receive_at=_aware(mart.to_receive_at),
                        to_closed_at=_aware(mart.to_closed_at),
                        to_cancelled_at=_aware(mart.to_cancelled_at),
                        operation_id=(link or {}).get("operation_id"),
                        ticket_id=(link or {}).get("ticket_id"),
                        ticket_number=(link or {}).get("ticket_number"),
                        order_id=(link or {}).get("order_id"),
                        label_state=(link or {}).get("label_state"),
                        creation_state=(link or {}).get("creation_state"),
                        ticket_state=(link or {}).get("ticket_state"),
                        **_derived_fields(view, owners, kinds),
                    )
                )
                seen_shipments.add(shipment_id)
        for shipment_id, link in creation.by_shipment.items():
            if shipment_id in seen_shipments:
                continue
            row_id = f"cr:{link['ticket_id']}:{shipment_id}"
            self._creation_by_id[row_id] = link
            rows.append(
                ShipmentBoardRow(
                    id=row_id,
                    source="creation_only",
                    shipment_id=shipment_id,
                    inbound_order_id=None,
                    store_id=link["store_id"],
                    store_name=link.get("store_name"),
                    status=None,
                    status_name=None,
                    status_label="待领星同步",
                    lingxing_sync_status="PENDING",
                    business_test=bool(link.get("business_test")),
                    its=link.get("its"),
                    pk=link.get("pk"),
                    sku=link.get("sku"),
                    product_name=link.get("product_name"),
                    item_id=link.get("item_id"),
                    gtin=link.get("gtin"),
                    msku=link.get("msku"),
                    created_at=_aware(link.get("created_at")),
                    operation_id=link["operation_id"],
                    ticket_id=link["ticket_id"],
                    ticket_number=link["ticket_number"],
                    order_id=link["order_id"],
                    label_state=link["label_state"],
                    creation_state=link["creation_state"],
                    ticket_state=link["ticket_state"],
                )
            )
        self._rows = rows
        return rows

    def _load_views(self, marts: list[Mart]) -> None:
        """8088 ``enrich`` / ``itemRows`` / ``buildExceptions`` for every published row."""

        pairs: set[tuple[str, str]] = set()
        skus: set[str] = set()
        for mart in marts:
            for good in (mart.payload_json or {}).get("goods") or []:
                if mart.store_id and good.get("msku"):
                    pairs.add((mart.store_id, good["msku"]))
                if good.get("sku"):
                    skus.add(good["sku"])
        item_ids = item_ids_by_store_msku(self.session, self.accounts, pairs)
        self._owners_by_sku = owners_by_sku(self.session, self.accounts, skus)
        views: list[ShipmentView] = []
        for mart in marts:
            payload = mart.payload_json or {}
            goods = payload.get("goods") or []
            store_id = mart.store_id or ""
            view = build_view(
                cargo_code=mart.cargo_code or mart.cargo_id,
                store_id=store_id,
                store_name=mart.store_name or "",
                status=mart.status_name or "",
                created=str((payload.get("cargo") or {}).get("cargo_create_date") or ""),
                to_closed_at=mart.to_closed_at,
                in_bound_order_id=mart.in_bound_order_id or "",
                shipping_codes=list(mart.shipping_codes or []),
                goods=goods,
                derived=payload.get("derived") or {},
                today=self.today,
                item_ids={
                    g["msku"]: item_ids[(store_id, g["msku"])]
                    for g in goods
                    if g.get("msku") and (store_id, g["msku"]) in item_ids
                },
            )
            self._view_by_id[f"lx:{mart.publication_id}:{mart.cargo_id}"] = view
            views.append(view)
        for exc in build_exceptions(views, RULES, self.today):
            self._exceptions_by_code.setdefault(exc.code, []).append(exc)

    def list_rows(self) -> list[ShipmentBoardRow]:
        """Every row of the current version (creation-only rows included), unfiltered."""

        return self._expand()

    def exceptions_by_code(self) -> dict[str, list[WfsException]]:
        self._expand()
        return self._exceptions_by_code

    # ---- filtering / sorting -----------------------------------------------------------

    @staticmethod
    def _match_keyword(row: ShipmentBoardRow, field: str, word: str) -> bool:
        word = word.lower()
        if field == "shipping":
            return any(word in code.lower() for code in row.shipping_codes) or any(
                word in number.lower() for number in row.logistics_numbers
            )
        targets = {
            "shipment": row.shipment_id,
            "inbound": row.inbound_order_id,
            "pk": row.pk,
            "msku": row.msku,
            "sku": row.sku,
            "item": row.item_id,
            "gtin": row.gtin,
        }
        return word in (targets.get(field) or "").lower()

    def _filter(self, rows: list[ShipmentBoardRow], query: ShipmentBoardFilter):
        word = query.keyword.strip()
        return [
            row
            for row in rows
            if (not query.store_id or row.store_id == query.store_id)
            and (not query.only_test or row.business_test)
            and (query.status is None or row.status == query.status)
            and (query.sync is None or row.lingxing_sync_status == query.sync)
            and (not query.owner or query.owner in row.owners)
            and (not query.region or row.region == query.region)
            and (query.arrival_bucket is None or row.arrival_bucket == query.arrival_bucket)
            and (not query.only_exceptions or bool(row.exception_types))
            and (not query.only_external or row.external)
            and (not word or self._match_keyword(row, query.keyword_field, word))
        ]

    @staticmethod
    def _sort(rows: list[ShipmentBoardRow], query: ShipmentBoardQuery):
        reverse = query.sort_dir == "desc"
        floor = datetime.min.replace(tzinfo=UTC)

        def key(row: ShipmentBoardRow):
            value = row.updated_at if query.sort_by == "updated_at" else row.created_at
            return (value or floor, row.shipment_id)

        return sorted(rows, key=key, reverse=reverse)

    # ---- API -------------------------------------------------------------------------

    def list(self, query: ShipmentBoardQuery) -> ShipmentBoardList:
        filtered = self._sort(self._filter(self._expand(), query), query)
        start = (query.page - 1) * query.page_size
        freshness = self.freshness()
        return ShipmentBoardList(
            items=filtered[start : start + query.page_size],
            total=len(filtered),
            data_asof=freshness.source_observed_at or datetime.now(UTC),
            freshness=freshness,
        )

    def summary(self, query: ShipmentBoardFilter) -> ShipmentBoardSummary:
        rows = self._filter(self._expand(), query)
        by_status: dict[str, int] = defaultdict(int)
        by_bucket: dict[str, int] = dict.fromkeys(BUCKET_LABELS, 0)
        for row in rows:
            if row.status is not None:
                by_status[str(row.status)] += 1
            if (
                row.arrival_bucket
                and row.shipped_out
                and not row.business_test
                and row.status_name not in ("CLOSED", "CANCELLED")
                and not row.walmart_first_receipt
            ):
                by_bucket[row.arrival_bucket] += 1
        return ShipmentBoardSummary(
            total=len(rows),
            by_status=dict(by_status),
            pending_lingxing_sync=sum(r.lingxing_sync_status == "PENDING" for r in rows),
            test=sum(r.business_test for r in rows),
            received_short=sum(
                1
                for r in rows
                if r.status == 3
                and r.declared_units is not None
                and r.received_units is not None
                and r.received_units < r.declared_units
            ),
            by_arrival_bucket=by_bucket,
            with_exceptions=sum(bool(r.exception_types) for r in rows),
            external=sum(r.external for r in rows),
            rule_version=RULE_VERSION,
            rule_date=self.today,
            freshness=self.freshness(),
        )

    def options(self) -> ShipmentBoardOptions:
        require_board_schema(self.session)
        name = func.nullif(func.trim(Store.store_name), "")
        stmt = (
            select(Store.store_id, func.count(func.distinct(name)), func.max(name))
            .where(
                Store.source_account_ref.in_(self.accounts),
                func.trim(Store.store_id) != "",
            )
            .group_by(Store.store_id)
            .order_by(Store.store_id)
        )
        if self.stores is not None:
            stmt = stmt.where(Store.store_id.in_(self.stores))
        values = {
            store_id: (label if count == 1 and label else store_id)
            for store_id, count, label in self.session.execute(stmt).all()
        }
        rows = self._expand()
        for row in rows:
            if row.store_id:
                values.setdefault(row.store_id, row.store_name or row.store_id)
        return ShipmentBoardOptions(
            stores=[StoreOption(value=k, label=v) for k, v in sorted(values.items())],
            owners=sorted({o for r in rows for o in r.owners}),
            regions=sorted({r.region for r in rows if r.region}),
            arrival_buckets=[StoreOption(value=k, label=v) for k, v in BUCKET_LABELS.items()],
        )

    def detail(self, ident: str) -> ShipmentBoardDetail:
        row = next((r for r in self._expand() if r.id == ident), None)
        if row is None:
            missing()
        mart = self._mart_by_id.get(ident)
        link = self._creation_by_id.get(ident, {})
        payload = (mart.payload_json or {}) if mart else {}
        cargo = payload.get("cargo") or {}
        goods = [ShipmentGoodsLine(**g) for g in payload.get("goods") or []]
        view = self._view_by_id.get(ident)
        gaps = {id(i) for i in big_gaps(view, RULES)} if view else set()
        items = [
            ShipmentItemLine(
                msku=i.msku,
                sku=i.sku,
                product_name=i.name,
                gtin=i.gtin,
                item_id=i.item_id,
                owners=self._owners_by_sku.get(i.sku, []),
                declared_units=i.declare,
                shipped_units=i.shipped,
                lingxing_received_units=i.lx_received,
                walmart_received_units=i.wm_received,
                put_away_units=i.put_away,
                damaged_units=i.damaged,
                normal_units=i.normal,
                over_units=i.over,
                abnormal_units=i.abnormal,
                abnormal=id(i) in gaps,
            )
            for i in (view.items if view else [])
        ]
        exceptions = [
            ShipmentException(
                type=e.type,
                rule_family=e.rule_family,
                severity=e.severity,  # type: ignore[arg-type]
                found=parse_date(e.found),
                description=e.desc,
                source=e.source,  # type: ignore[arg-type]
                qty=e.qty,
            )
            for e in (self._exceptions_by_code.get(view.code, []) if view else [])
        ]
        return ShipmentBoardDetail(
            **row.model_dump(),
            goods=goods,
            items=items,
            exceptions=exceptions,
            shipping_lists=list(payload.get("shipping_lists") or []),
            distribution_addresses=cargo.get("distribution_addresses"),
            return_addresses=cargo.get("return_addresses"),
            creator=cargo.get("creator"),
            country_name=cargo.get("country_name"),
            return_address=link.get("return_address"),
            expected_delivery_at=link.get("expected_delivery_at"),
            allocation=link.get("allocation"),
            lingxing_note=(
                None
                if mart
                else "该货件由本系统创建，领星尚未同步到；下次领星拉数后显示发货 / 到仓 / 收货。"
            ),
        )

    def products(self, query: ShipmentBoardQuery) -> ProductBoardList:
        """8088 产品维度 over the filtered shipments (store × Item ID, sellable buckets)."""

        rows = self._filter(self._expand(), query)
        views = [self._view_by_id[r.id] for r in rows if r.id in self._view_by_id]
        items = [
            ProductBoardRow(
                id=f"{p.store_id}:{p.item_id}",
                store_id=p.store_id,
                store_name=p.store_name or None,
                item_id=p.item_id,
                mskus=p.mskus,
                skus=p.skus,
                product_name=p.name or None,
                shipments=p.ships,
                in_transit_units=p.in_transit,
                buckets=p.buckets,
                signed_not_put_units=p.signed_not_put,
                arrived_shipped_units=p.arrived_shipped,
                arrived_signed_units=p.arrived_signed,
                arrived_shelved_units=p.arrived_shelved,
                receiving_gap_units=p.receiving,
                signed_zero_shelved=p.signed_zero_shelved,
                next_eta=parse_date(p.next_eta),
                next_sellable=parse_date(p.next_sellable),
                lines=[
                    ProductShipmentLine(
                        shipment_id=line.code,
                        status_name=line.status,
                        msku=line.msku,
                        shipped_units=line.shipped,
                        signed_units=line.signed,
                        shelved_units=line.shelved,
                        eta=parse_date(line.eta),
                        eta_source=line.eta_source or None,  # type: ignore[arg-type]
                        sellable_date=parse_date(line.sellable),
                        sellable_real=line.sellable_real,
                        bucket=line.bucket,
                        region=line.region or None,
                    )
                    for line in p.lines
                ],
            )
            for p in product_views(views, self.today)
        ]
        start = (query.page - 1) * query.page_size
        freshness = self.freshness()
        return ProductBoardList(
            items=items[start : start + query.page_size],
            total=len(items),
            data_asof=freshness.source_observed_at or datetime.now(UTC),
            freshness=freshness,
        )

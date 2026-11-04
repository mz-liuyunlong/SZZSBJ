"""本机模拟数据（Rocky 2026-11-04：在 5173 造数据亲手走一遍待创建货件）。

只在 APP_ENV=local + 本机库 127.0.0.1:55432/szzsbj_dev 运行（``guard``），别处一律报错。
写入的都带测试标记，``clear`` 只删带标记的：

* 打包单号 ``DEMO-01`` … ``DEMO-07``，``is_test`` / ``business_test`` = true，操作人
  ``demo-seed:wfs-sim-20261104``（打包单快照是严格校验的候选结构，标记不能写进去）；
* 创建操作的快照里同样写 ``demo_seed``；模拟的 SP 发货单号以 ``DEMO-SP`` 开头。

打包单挂在本机已有的真实打包单所在的批次行上（真实 SKU / 店铺 / GTIN），``candidate_id`` 用
新的随机值，不写分配记录，所以批次看板的可用数量不变。创建走真实的 CreationService 和 worker，
Walmart 一侧用本机模拟通道（``local_simulator``），没有任何网络调用。
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, or_, select, text

from app.modules.pmc_wfs import local_simulator
from app.modules.pmc_wfs.local_simulator import LocalSimulatorGateway, SimulatorRefused

DEMO_SEED = "wfs-sim-20261104"
DEMO_PREFIX = "DEMO-"
ACTOR = f"demo-seed:{DEMO_SEED}"
RETURN_ADDRESS = {
    "address_line1": "14125 TELEPHONE AVE",
    "city": "CHINO",
    "state_code": "CA",
    "postal_code": "91710",
}

# pk, total boxes, units per box (DEMO-01 … 07, see the plan's table)
ORDERS = (
    ("DEMO-01", 10, 6),
    ("DEMO-02", 20, 6),
    ("DEMO-03", 12, 6),
    ("DEMO-04", 10, 6),
    ("DEMO-05", 8, 6),
    ("DEMO-06", 10, 6),
    ("DEMO-07", 6, 6),
)


def local_only_reason(session=None) -> str | None:
    """Same local-only rule as the simulator, without needing its switch. When a session is
    given, its own connection must be the local database too."""
    from app.core.config import get_settings

    try:
        settings = get_settings()
        env = settings.app_env.value
        url = settings.sqlalchemy_url()
    except Exception:
        return "读不到本机配置，拒绝"
    if env != "local":
        return f"只能在 APP_ENV=local 运行（当前 {env}）"
    urls = [url]
    if session is not None:
        urls.append(session.get_bind().url)
    for value in urls:
        if value.host not in {"127.0.0.1", "localhost"} or value.port != 55432:
            return "只能连本机库 127.0.0.1:55432"
        if value.database != "szzsbj_dev":
            return "只能连本机库 szzsbj_dev"
    return None


def guard(session=None) -> None:
    reason = local_only_reason(session)
    if reason:
        raise SimulatorRefused(f"本机模拟数据{reason}")


class _SeedGateway(LocalSimulatorGateway):
    """The simulator, used only by this seed (after ``guard``); can fake one rejection and
    one failed label fetch so the page shows those states."""

    def __init__(self, session) -> None:  # noqa: D401 - no simulator switch needed here
        guard(session)
        self.reject = False
        self.fail_label = False

    def create(self, order_id, snapshot, allocation):
        from app.modules.pmc_wfs.walmart_gateway import DefinitiveRejection

        if self.reject:
            raise DefinitiveRejection("Invalid returnAddress.postalCode")
        return super().create(order_id, snapshot, allocation)

    def label(self, shipment_id, snapshot, cartons=None):
        if self.fail_label:
            raise TimeoutError("simulated label failure")
        return super().label(shipment_id, snapshot, cartons)


# ----- 写入 -------------------------------------------------------------------------------


def demo_order_ids(session) -> list[UUID]:
    from app.modules.pmc_domestic.packing_models import PackingOrder

    return list(
        session.scalars(
            select(PackingOrder.id).where(
                PackingOrder.pk.like(f"{DEMO_PREFIX}%"),
                PackingOrder.actor_uid == ACTOR,
                PackingOrder.is_test.is_(True),
            )
        )
    )


def _sources(session, account: str | None):
    """Real approved packing orders to borrow SKU / store / GTIN / batch row from."""
    from app.modules.pmc_domestic.packing_models import PackingOrder

    stmt = (
        select(PackingOrder)
        .where(
            PackingOrder.status == "approved",
            PackingOrder.warehouse_id == "16168",
            PackingOrder.pk.not_like(f"{DEMO_PREFIX}%"),
        )
        .order_by(PackingOrder.created_at.desc())
    )
    if account:
        stmt = stmt.where(PackingOrder.source_account_ref == account)
    rows = list(session.scalars(stmt.limit(500)))
    if not rows:
        raise SimulatorRefused("本机没有可挂靠的真实打包单（先在仓库打包里有一条已审批的）")
    account = account or rows[0].source_account_ref
    seen, picked = set(), []
    for row in rows:
        if row.source_account_ref != account:
            continue
        key = (row.store_id, row.sku)
        if key not in seen:
            seen.add(key)
            picked.append(row)
    return account, picked


def _demo_order(session, source, pk: str, boxes: int, per: int, completed_at: datetime):
    from app.modules.pmc_domestic.packing_models import PackingOrder
    from app.modules.pmc_domestic.warehouse_models import PackingBoxLine, PackingBoxSet

    oid = uuid4()
    qty = boxes * per
    snapshot = {
        **(source.snapshot_json or {}),
        "id": str(oid),
        "candidate_version": hashlib.sha256(f"{DEMO_SEED}:{pk}".encode()).hexdigest(),
    }
    order = PackingOrder(
        id=oid,
        source_account_ref=source.source_account_ref,
        warehouse_id="16168",
        candidate_id=uuid4(),  # never a real candidate
        inbound_order_sn=source.inbound_order_sn,
        sku=source.sku,
        store_id=source.store_id,
        item_id=source.item_id,
        pk=pk,
        qty=qty,
        customs_value=source.customs_value if source.customs_value is not None else False,
        customs_src=source.customs_src,
        is_test=True,
        business_test=True,
        status="approved",
        version=1,
        source_publication_id=source.source_publication_id,
        source_board_id=source.source_board_id,
        snapshot_json=snapshot,
        final_identity_key=hashlib.sha256(f"{DEMO_SEED}:{pk}:{oid}".encode()).hexdigest(),
        actor_uid=ACTOR,
        note=f"本机模拟数据 {DEMO_SEED}（clear 一键清除）",
        created_at=completed_at,
        updated_at=completed_at,
    )
    session.add(order)
    session.flush()
    box = PackingBoxSet(
        id=uuid4(),
        order_id=oid,
        total_qty=qty,
        approved_qty_snapshot=qty,
        version=1,
        completed_at=completed_at,
        completed_by=ACTOR,
        actor_uid=ACTOR,
    )
    session.add(box)
    session.flush()
    session.add(
        PackingBoxLine(
            id=uuid4(),
            box_set_id=box.id,
            line_no=1,
            box_type="A",
            boxes=boxes,
            units_per_box=per,
            length_cm=58,
            width_cm=40,
            height_cm=45,
            gross_weight_kg=8,
        )
    )
    session.flush()
    return order


def seed(factory, account: str | None = None, now: datetime | None = None) -> dict:
    """Write DEMO-01 … 07 and their creation records. Refuses outside local, or when demo
    rows already exist (run ``clear`` first)."""
    from app.modules.pmc_wfs.creation_models import WfsCreation, WfsCreationTicket
    from app.modules.pmc_wfs.creation_schemas import (
        AllocationCommand,
        CreationCommand,
    )
    from app.modules.pmc_wfs.creation_service import CreationService
    from app.modules.pmc_wfs.creation_task import bootstrap
    from app.modules.pmc_wfs.creation_worker import run_operation
    from app.modules.pmc_wfs.service import WfsService

    now = now or datetime.now(UTC)
    guard()
    with factory() as session:
        guard(session)
        if demo_order_ids(session):
            raise SimulatorRefused("本机已有 DEMO 数据，先运行 clear")
        account, sources = _sources(session, account)
        orders = {}
        for index, (pk, boxes, per) in enumerate(ORDERS):
            source = sources[index % len(sources)]
            orders[pk] = _demo_order(
                session, source, pk, boxes, per, now - timedelta(hours=len(ORDERS) - index)
            )
        session.commit()
        ids = {pk: o.id for pk, o in orders.items()}
        bootstrap(session, account)  # 任务中心「WFS 创建结果拉取」（已有就不动，定时保持关闭）

    gateway = _SeedGateway(None)
    with factory() as session:
        guard(session)

        def dispatch(ident, action):
            return run_operation(factory, gateway, UUID(str(ident)), action)

        svc = CreationService(WfsService(session, frozenset({account}), None), gateway, dispatch)

        def submit(pk, counts, postal=RETURN_ADDRESS["postal_code"]):
            order = svc.base.detail(ids[pk]).order
            cmd = AllocationCommand(
                order_id=order.id,
                expected_version=order.version,
                expected_box_version=order.box_set.version,
                shipping_boxes=sum(counts),
                shipment_count=len(counts),
                shipment_boxes=list(counts),
            )
            op = svc.submit_and_send(  # 「确认创建」= 直接发出（已取消「待批准」）
                CreationCommand(
                    **cmd.model_dump(),
                    source_account_ref=account,
                    preview_hash=svc.preview(cmd).preview_hash,
                    idempotency_key=uuid4(),
                    return_address={**RETURN_ADDRESS, "postal_code": postal},
                    its=True,
                ),
                ACTOR,
            )
            row = session.get(WfsCreation, op.id)
            row.snapshot = {**row.snapshot, "demo_seed": DEMO_SEED}
            session.commit()
            session.expire_all()
            return op.id

        def tickets(op_id):
            session.expire_all()
            return list(
                session.scalars(
                    select(WfsCreationTicket)
                    .where(WfsCreationTicket.operation_id == op_id)
                    .order_by(WfsCreationTicket.number)
                    .with_for_update()
                )
            )

        made = {}
        # DEMO-02：拆成两票，一票已创建（箱唛已打印 2 次），一票提交中（已查询 3/10 次），剩 4 箱
        op = made["DEMO-02"] = submit("DEMO-02", (8, 8))
        first, second = tickets(op)
        labels = dict(first.result["labels"])
        sid = next(iter(labels))
        labels[sid] = {
            **labels[sid],
            "prints": 2,
            "printed_at": (now - timedelta(minutes=30)).isoformat(),
            "printed_by": ACTOR,
        }
        first.result = {**first.result, "labels": labels}
        second.state = "RUNNING"
        second.result = {
            k: v for k, v in second.result.items() if k not in ("shipments", "labels", "fc_check")
        } | {
            "polling": {
                "count": 3,
                "max": 10,
                "next_at": (now + timedelta(minutes=3)).isoformat(),
            },
            "submissions": 1,
        }
        session.get(WfsCreation, op).state = "RUNNING"
        session.commit()
        # DEMO-03：创建失败（Walmart 拒绝），可以点「重试」（重试时模拟通道会成功）
        gateway.reject = True
        made["DEMO-03"] = submit("DEMO-03", (12,))
        gateway.reject = False
        # DEMO-04：提交中，结果不明（邮编 99999）：点「立即拉取结果」后查到、变成已创建
        made["DEMO-04"] = submit("DEMO-04", (6,), local_simulator.UNKNOWN_POSTAL)
        # DEMO-05：已发货（一票一个 DEMO-SP 发货单）
        op = made["DEMO-05"] = submit("DEMO-05", (8,))
        _ship(tickets(op), {0: "DEMO-SP-0005"})
        session.commit()
        # DEMO-06：两票共用一张发货单
        op = made["DEMO-06"] = submit("DEMO-06", (5, 5))
        _ship(tickets(op), {0: "DEMO-SP-0006", 1: "DEMO-SP-0006"})
        session.commit()
        # DEMO-07：已创建未发货，箱唛取失败（显示「补取」）
        gateway.fail_label = True
        made["DEMO-07"] = submit("DEMO-07", (6,))
        gateway.fail_label = False
    return {
        "account": account,
        "orders": sorted(ids),
        "operations": {k: str(v) for k, v in made.items()},
    }


def _ship(tickets, codes: dict[int, str]) -> None:
    for index, code in codes.items():
        ticket = tickets[index]
        sids = list((ticket.result.get("labels") or {}) or (ticket.result.get("shipments") or {}))
        ticket.result = {**ticket.result, "simulated_shipping": {sid: code for sid in sids}}


# ----- 清除 -------------------------------------------------------------------------------


# Append-only audit tables (BEFORE UPDATE OR DELETE trigger raises). Only ``clear`` on the
# verified local database lifts the trigger, inside its own transaction, for DEMO rows only;
# the trigger is back on before the transaction commits.
AUDIT_TRIGGERS = {
    "evt_wfs_creation_events": "wfs_creation_event_immutable",
    "evt_domestic_packing_events": "domestic_packing_event_immutable",
}


def _delete_audit(session, statement) -> None:
    trigger = AUDIT_TRIGGERS.get(statement.table.name)
    if trigger is None:
        session.execute(statement)
        return
    guard(session)
    table = statement.table.name
    present = session.scalar(
        text("SELECT count(*) FROM pg_trigger WHERE tgrelid = to_regclass(:t) AND tgname = :g"),
        {"t": table, "g": trigger},
    )
    if not present:  # e.g. a test schema without the trigger
        session.execute(statement)
        return
    session.execute(text(f'ALTER TABLE "{table}" DISABLE TRIGGER "{trigger}"'))
    try:
        session.execute(statement)
    finally:
        session.execute(text(f'ALTER TABLE "{table}" ENABLE TRIGGER "{trigger}"'))


def clear(factory) -> dict:
    """Delete every row the seed wrote, plus anything created on a DEMO order during the demo
    (creation records on DEMO PKs). Real rows are never touched."""
    from app.db.base import Base
    from app.modules.pmc_domestic.packing_models import PackingOrder
    from app.modules.pmc_domestic.warehouse_models import PackingBoxLine, PackingBoxSet
    from app.modules.pmc_wfs.creation_models import (
        WfsBoxHold,
        WfsCreation,
        WfsCreationEvent,
        WfsCreationTicket,
    )

    guard()
    with factory() as session:
        guard(session)
        ids = demo_order_ids(session)
        op_ids = set(
            session.scalars(
                select(WfsCreation.id).where(
                    or_(
                        WfsCreation.order_id.in_(ids),
                        WfsCreation.snapshot["demo_seed"].as_string() == DEMO_SEED,
                    )
                )
            )
        )
        op_ids |= set(
            session.scalars(
                select(WfsCreationTicket.operation_id)
                .join(WfsBoxHold, WfsBoxHold.ticket_id == WfsCreationTicket.id)
                .where(WfsBoxHold.order_id.in_(ids))
            )
        )
        counts = {"orders": len(ids), "operations": len(op_ids)}
        if op_ids:
            ticket_ids = select(WfsCreationTicket.id).where(
                WfsCreationTicket.operation_id.in_(op_ids)
            )
            _delete_audit(
                session,
                delete(WfsCreationEvent).where(WfsCreationEvent.operation_id.in_(op_ids)),
            )
            session.execute(delete(WfsBoxHold).where(WfsBoxHold.ticket_id.in_(ticket_ids)))
            session.execute(
                delete(WfsCreationTicket).where(WfsCreationTicket.operation_id.in_(op_ids))
            )
            session.execute(delete(WfsCreation).where(WfsCreation.id.in_(op_ids)))
        if ids:
            sets = select(PackingBoxSet.id).where(PackingBoxSet.order_id.in_(ids))
            old = Base.metadata.tables.get("ops_pmc_wfs_box_allocations")
            if old is not None:
                session.execute(delete(old).where(old.c.order_id.in_(ids)))
            session.execute(delete(PackingBoxLine).where(PackingBoxLine.box_set_id.in_(sets)))
            for table in reversed(Base.metadata.sorted_tables):
                if table.name == PackingOrder.__tablename__ or table.name.startswith(
                    ("ops_wfs_", "evt_wfs_creation", "ops_pmc_wfs_")
                ):
                    continue
                for column in table.columns:
                    if any(
                        fk.target_fullname == "ops_domestic_packing_orders.id"
                        for fk in column.foreign_keys
                    ):
                        _delete_audit(session, delete(table).where(column.in_(ids)))
            session.execute(delete(PackingOrder).where(PackingOrder.id.in_(ids)))
        session.commit()
    counts["simulator_orders"] = local_simulator.forget()
    return counts

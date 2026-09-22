"""G3-B part 2: ODS → DWD publication end-to-end on an in-memory SQLite database."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.modules.data_pages.models import LingxingStoreDimension
from app.modules.integration_sync.models import (
    ApiRawRequestRef,
    DataLineage,
    IntegrationSyncRun,
    ParseJob,
)
from app.modules.pmc_purchase.gate3_models import (
    DwdPurchaseOrder,
    DwdPurchaseOrderLineItem,
    DwdPurchasePlan,
)
from app.modules.pmc_purchase.models import (
    LingxingPurchaseOrderItemOds,
    LingxingPurchaseOrderOds,
    LingxingPurchasePlanOds,
    LingxingReceiptOrderItemOds,
    LingxingReceiptOrderOds,
)
from app.modules.pmc_purchase.publisher import (
    PARSER_KEY,
    PmcPurchaseDwdPublisher,
    PmcPurchaseDwdPublishError,
)


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_: object, compiler: object, **kw: object) -> str:
    return "JSON"


ACCOUNT = "primary"
STORE = "110652398125259264"
T1 = datetime(2026, 9, 22, 3, 0, tzinfo=UTC)
T2 = datetime(2026, 9, 23, 3, 0, tzinfo=UTC)
TABLES = (
    "gov_integration_sync_runs",
    "ods_api_raw_request_refs",
    "gov_parse_jobs",
    "gov_data_lineage",
    "dim_lingxing_stores",
    "ods_lingxing_purchase_plans",
    "ods_lingxing_purchase_orders",
    "ods_lingxing_purchase_order_items",
    "ods_lingxing_receipt_orders",
    "ods_lingxing_receipt_order_items",
    "dwd_purchase_plan",
    "dwd_purchase_order",
    "dwd_purchase_order_line_item",
)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _sqlite_functions(dbapi_connection: object, _record: object) -> None:
        # PostgreSQL CHECK constraints use char_length(); SQLite has only length().
        dbapi_connection.create_function("char_length", 1, len)  # type: ignore[attr-defined]

    Base.metadata.create_all(engine, tables=[Base.metadata.tables[n] for n in TABLES])
    with Session(engine) as s:
        s.add(
            LingxingStoreDimension(
                id=uuid4(),
                source_account_ref=ACCOUNT,
                platform_code_raw="walmart",
                store_id=STORE,
                store_name="Store A",
                synced_at=T1,
            )
        )
        s.commit()
        yield s
    engine.dispose()


def _run(session: Session, key: str, status: str = "succeeded") -> tuple[UUID, UUID]:
    run_id, ref_id = uuid4(), uuid4()
    session.add(
        IntegrationSyncRun(
            id=run_id,
            interface_id=uuid4(),
            provider="lingxing",
            # The (provider, interface_key) unique index is partial on PostgreSQL
            # (status = 'running') but SQLite renders it unconditionally: keep keys unique.
            interface_key=f"{key}:{run_id.hex[:8]}",
            source_account_ref=ACCOUNT,
            trigger_type="manual",
            status=status,
            idempotency_key=f"{key}:{run_id}",
            queued_at=T1,
        )
    )
    session.add(
        ApiRawRequestRef(
            id=ref_id,
            run_id=run_id,
            work_item_id=uuid4(),
            raw_blob_id=uuid4(),
            request_kind="offset_page",
            attempt_no=1,
            request_safe_params={"offset": 0},
            is_success=True,
            requested_at=T1,
            received_at=T1,
        )
    )
    session.flush()
    return run_id, ref_id


def _plan(run: UUID, ref: UUID, **kw: object) -> LingxingPurchasePlanOds:
    base: dict[str, object] = dict(
        run_id=run,
        raw_request_ref_id=ref,
        source_account_ref=ACCOUNT,
        source_item_ordinal=0,
        payload_json={"update_time": "2026-08-05 14:33:13"},
        observed_at=T1,
        plan_sn="P1",
        status=2,
        create_time="2026-08-03 10:52:36",
        sid=STORE,
        sku="SKU-A",
        product_name="Widget",
        quantity_plan=100,
        remark="ITEMID:19051502014",
        is_aux=0,
        is_combo=0,
    )
    base.update(kw)
    return LingxingPurchasePlanOds(**base)


def _order(run: UUID, ref: UUID, **kw: object) -> LingxingPurchaseOrderOds:
    base: dict[str, object] = dict(
        run_id=run,
        raw_request_ref_id=ref,
        source_account_ref=ACCOUNT,
        source_item_ordinal=0,
        payload_json={"update_time": "2026-08-20 12:49:44"},
        observed_at=T1,
        order_sn="PO1",
        status=2,
        order_time="2026-08-05 12:00:00",
        create_time="2026-08-04 09:00:00",
        quantity_total=100,
        quantity_real=100,
        amount_total=Decimal("500.0000"),
        purchase_currency="CNY",
        item_count=1,
    )
    base.update(kw)
    return LingxingPurchaseOrderOds(**base)


def _item(run: UUID, ref: UUID, **kw: object) -> LingxingPurchaseOrderItemOds:
    base: dict[str, object] = dict(
        run_id=run,
        raw_request_ref_id=ref,
        source_account_ref=ACCOUNT,
        source_item_ordinal=0,
        payload_json={},
        observed_at=T1,
        order_sn="PO1",
        item_id="L1",
        line_ordinal=0,
        plan_sn="P1",
        sid=STORE,
        sku="SKU-A",
        quantity_plan=100,
        quantity_real=100,
        price=Decimal("5.0000"),
        amount=Decimal("500.0000"),
        is_delete=0,
    )
    base.update(kw)
    return LingxingPurchaseOrderItemOds(**base)


def _receipt(run: UUID, ref: UUID) -> tuple[LingxingReceiptOrderOds, LingxingReceiptOrderItemOds]:
    return (
        LingxingReceiptOrderOds(
            run_id=run,
            raw_request_ref_id=ref,
            source_account_ref=ACCOUNT,
            source_item_ordinal=0,
            payload_json={},
            observed_at=T1,
            order_sn="R1",
            business_order_sn="PO1",
            receive_time="2026-08-20 18:29:09",
            item_count=1,
        ),
        LingxingReceiptOrderItemOds(
            run_id=run,
            raw_request_ref_id=ref,
            source_account_ref=ACCOUNT,
            source_item_ordinal=0,
            payload_json={},
            observed_at=T1,
            receipt_order_sn="R1",
            line_ordinal=0,
            order_item_id="L1",
            product_receive_num=60,
        ),
    )


def _seed_first_window(session: Session) -> dict[str, tuple[UUID, UUID]]:
    runs = {k: _run(session, k) for k in ("purchasePlanList", "purchaseOrderList", "receipt")}
    session.add(_plan(*runs["purchasePlanList"]))
    session.add(_order(*runs["purchaseOrderList"]))
    session.add(_item(*runs["purchaseOrderList"]))
    session.add_all(_receipt(*runs["receipt"]))
    session.commit()
    return runs


def test_first_publish_inserts_dwd_rows_parse_jobs_and_lineage(session: Session) -> None:
    runs = _seed_first_window(session)
    result = PmcPurchaseDwdPublisher(session, now=T1).publish(source_account_ref=ACCOUNT)

    assert (result.plans_inserted, result.orders_inserted, result.lines_inserted) == (1, 1, 1)
    assert result.receipt_lines == 1 and result.stores_known == 1
    plan = session.scalar(select(DwdPurchasePlan))
    assert plan is not None
    assert plan.plan_sn == "P1" and plan.status == 2
    assert plan.create_date.isoformat() == "2026-08-03"
    assert plan.store_id == STORE and plan.store_attributed and plan.store_matched
    assert plan.remark_item_id == "19051502014"
    assert plan.first_seen_pending_date == T1.date()  # S2 start observed on first publish
    assert plan.source_run_id == runs["purchasePlanList"][0]
    assert plan.provider_update_time == "2026-08-05 14:33:13"

    line = session.scalar(select(DwdPurchaseOrderLineItem))
    assert line is not None
    assert (line.plan_key, line.plan_found, line.quantity_allocated) == ("P1", True, 100)
    assert line.remark_item_id == "19051502014" and line.store_matched

    jobs = list(session.scalars(select(ParseJob)))
    assert {j.raw_request_ref_id for j in jobs} == {
        runs["purchasePlanList"][1],
        runs["purchaseOrderList"][1],
    }
    assert all(j.parser_key == PARSER_KEY and j.target_layer == "DWD" for j in jobs)
    assert sum(j.records_written for j in jobs) == 3
    lineage_tables = {row.target_table for row in session.scalars(select(DataLineage))}
    assert lineage_tables == {
        "dwd_purchase_plan",
        "dwd_purchase_order",
        "dwd_purchase_order_line_item",
    }
    assert result.lineage_written == session.scalar(select(func.count(DataLineage.id)))


def test_republish_is_idempotent_and_newer_version_rewrites(session: Session) -> None:
    _seed_first_window(session)
    PmcPurchaseDwdPublisher(session, now=T1).publish(source_account_ref=ACCOUNT)
    lineage_before = session.scalar(select(func.count(DataLineage.id)))

    again = PmcPurchaseDwdPublisher(session, now=T2).publish(source_account_ref=ACCOUNT)
    assert (again.plans_unchanged, again.orders_unchanged, again.lines_unchanged) == (1, 1, 1)
    assert again.plans_inserted == again.plans_updated == 0
    assert again.parse_jobs_written == 0 and again.lineage_written == 0
    assert session.scalar(select(func.count(DataLineage.id))) == lineage_before

    # A later window re-delivers P1 (status → -2 completed) and PO1 with one more line.
    run2, ref2 = _run(session, "purchasePlanList")
    session.add(
        _plan(
            run2,
            ref2,
            status=-2,
            payload_json={"update_time": "2026-09-01 08:00:00"},
            observed_at=T2,
        )
    )
    run3, ref3 = _run(session, "purchaseOrderList")
    session.add(
        _order(
            run3,
            ref3,
            status=9,
            item_count=2,
            payload_json={"update_time": "2026-09-02 08:00:00"},
            observed_at=T2,
        )
    )
    session.add(_item(run3, ref3, observed_at=T2))
    session.add(
        _item(run3, ref3, item_id="L2", line_ordinal=1, plan_sn=None, sid="0", observed_at=T2)
    )
    session.commit()

    third = PmcPurchaseDwdPublisher(session, now=T2).publish(source_account_ref=ACCOUNT)
    assert (third.plans_updated, third.orders_updated) == (1, 1)
    assert (third.lines_updated, third.lines_inserted) == (1, 1)
    plan = session.scalar(select(DwdPurchasePlan))
    assert plan is not None and plan.status == -2 and plan.source_run_id == run2
    assert plan.first_seen_pending_date == T1.date()  # preserved, not re-stamped
    order = session.scalar(select(DwdPurchaseOrder))
    assert order is not None and order.status == 9 and order.line_count == 2
    assert session.scalar(select(func.count(DwdPurchaseOrderLineItem.id))) == 2
    l2 = session.scalar(
        select(DwdPurchaseOrderLineItem).where(DwdPurchaseOrderLineItem.order_item_id == "L2")
    )
    assert l2 is not None and l2.plan_key == "" and not l2.store_attributed


def test_failed_runs_are_ignored_and_bad_account_rejected(session: Session) -> None:
    run, ref = _run(session, "purchasePlanList", status="failed")
    session.add(_plan(run, ref))
    session.commit()
    result = PmcPurchaseDwdPublisher(session, now=T1).publish(source_account_ref=ACCOUNT)
    assert result.plans_inserted == 0 and result.report.plans_seen == 0
    with pytest.raises(PmcPurchaseDwdPublishError, match="SOURCE_ACCOUNT_REF_INVALID"):
        PmcPurchaseDwdPublisher(session).publish(source_account_ref=" primary")


def test_unknown_store_is_kept_but_flagged_unmatched(session: Session) -> None:
    run, ref = _run(session, "purchasePlanList")
    session.add(_plan(run, ref, sid="12345"))
    session.commit()
    PmcPurchaseDwdPublisher(session, now=T1).publish(source_account_ref=ACCOUNT)
    plan = session.scalar(select(DwdPurchasePlan))
    assert plan is not None
    assert plan.store_id == "12345" and plan.store_attributed and not plan.store_matched

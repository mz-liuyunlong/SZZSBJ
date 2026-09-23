"""G3-D: DWD → DWS refresh end-to-end on an in-memory SQLite database.

DWD rows are inserted directly (the publisher has its own tests); receipt events come
from ODS receipt rows of succeeded runs, exactly as in production.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.modules.data_pages.models import LingxingStoreDimension, WalmartListingDimension
from app.modules.integration_sync.models import ApiRawRequestRef, IntegrationSyncRun
from app.modules.pmc_purchase.gate3_models import (
    DwdPurchaseOrder,
    DwdPurchaseOrderLineItem,
    DwdPurchasePlan,
    DwsPurchaseBoard,
    DwsPurchasePending,
    DwsPurchaseSkuCycle,
    ManualPurchaseCycleOverride,
    RulePurchaseThresholds,
)
from app.modules.pmc_purchase.models import (
    LingxingReceiptOrderItemOds,
    LingxingReceiptOrderOds,
)
from app.modules.pmc_purchase.refresh import (
    DWS_CALC_VERSION,
    PackingSlipMatch,
    PmcPurchaseDwsRefresher,
    PmcPurchaseDwsRefreshError,
)
from app.modules.sku_detail.models import LingxingSkuProductInfoCurrent


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_: object, compiler: object, **kw: object) -> str:
    return "JSON"


ACCOUNT = "primary"
STORE = "110652398125259264"
NOW = datetime(2026, 9, 23, 3, 0, tzinfo=UTC)
TODAY = date(2026, 9, 23)
TABLES = (
    "gov_integration_sync_runs",
    "ods_api_raw_request_refs",
    "dim_lingxing_stores",
    "dim_walmart_listings",
    "dwd_lingxing_sku_product_info_current",
    "ods_lingxing_receipt_orders",
    "ods_lingxing_receipt_order_items",
    "dwd_purchase_plan",
    "dwd_purchase_order",
    "dwd_purchase_order_line_item",
    "dws_purchase_board",
    "dws_purchase_sku_cycle",
    "dws_purchase_pending",
    "manual_purchase_cycle_override",
    "rule_purchase_thresholds",
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
        dbapi_connection.create_function("char_length", 1, len)  # type: ignore[attr-defined]

    Base.metadata.create_all(engine, tables=[Base.metadata.tables[n] for n in TABLES])
    with Session(engine) as s:
        s.add(_rule())
        s.add(
            LingxingStoreDimension(
                id=uuid4(),
                source_account_ref=ACCOUNT,
                platform_code_raw="walmart",
                store_id=STORE,
                store_name="Store A",
                synced_at=NOW,
            )
        )
        s.add(
            WalmartListingDimension(
                id=uuid4(),
                source_account_ref=ACCOUNT,
                store_id=STORE,
                item_id="19051502014",
                msku="MSKU-A",
                gtin="00012345678905",
                fulfillment_type="0",
                synced_at=NOW,
            )
        )
        s.add(
            LingxingSkuProductInfoCurrent(
                id=uuid4(),
                provider="lingxing",
                source_account_ref=ACCOUNT,
                identity_id=uuid4(),
                lingxing_sku_id="900001",
                lingxing_sku_code="SKU-A",
                source_snapshot_id=uuid4(),
                source_run_id=uuid4(),
                source_observed_at=NOW,
                owner_uid="u-1",
                owner_name="Owner One",
                purchase_delivery_days=12,
            )
        )
        s.commit()
        yield s
    engine.dispose()


def _rule(**kw: object) -> RulePurchaseThresholds:
    base: dict[str, object] = dict(
        id=uuid4(),
        rule_key="pmc_purchase_thresholds",
        version=1,
        s1_approval_days=2,
        s2_pending_days=7,
        default_cycle_days=7,
        arrival_ratio=Decimal("0.5000"),
        auto_exclude_below_days=2,
        sample_window=5,
        min_samples_for_average=2,
        unstable_min_samples=5,
        unstable_range_days=3,
        baseline_evict_at_samples=5,
        effective_from=date(2026, 8, 1),
        is_active=True,
        approved_by="test",
        approved_at=NOW,
        change_reason="seed",
    )
    base.update(kw)
    return RulePurchaseThresholds(**base)


def _source(**kw: object) -> dict[str, object]:
    base: dict[str, object] = dict(
        source_account_ref=ACCOUNT,
        source_run_id=uuid4(),
        source_ods_id=uuid4(),
        source_observed_at=NOW,
        builder_version="test",
    )
    base.update(kw)
    return base


def _plan(session: Session, plan_sn: str, **kw: object) -> DwdPurchasePlan:
    base: dict[str, object] = dict(
        plan_sn=plan_sn,
        status=-2,
        create_date=date(2026, 8, 1),
        store_id=STORE,
        store_attributed=True,
        store_matched=True,
        sku="SKU-A",
        product_name="Widget",
        quantity_plan=100,
        remark="ITEMID:19051502014",
        remark_item_id="19051502014",
    )
    base.update(kw)
    row = DwdPurchasePlan(id=uuid4(), **_source(), **base)
    session.add(row)
    return row


def _order(session: Session, order_sn: str, **kw: object) -> DwdPurchaseOrder:
    base: dict[str, object] = dict(
        order_sn=order_sn,
        status=2,
        order_date=date(2026, 8, 5),
        create_date=date(2026, 8, 4),
        quantity_total=100,
        quantity_real=100,
        amount_total=Decimal("500.0000"),
        currency_code="CNY",
        line_count=1,
    )
    base.update(kw)
    row = DwdPurchaseOrder(id=uuid4(), **_source(), **base)
    session.add(row)
    return row


def _line(session: Session, order_sn: str, item_id: str, **kw: object) -> DwdPurchaseOrderLineItem:
    base: dict[str, object] = dict(
        order_sn=order_sn,
        order_item_id=item_id,
        line_ordinal=0,
        plan_sn="P1",
        plan_key="P1",
        plan_count=1,
        allocation_ratio=Decimal("1"),
        is_merged=False,
        plan_found=True,
        store_id=STORE,
        store_attributed=True,
        store_matched=True,
        sku="SKU-A",
        product_name="Widget",
        quantity_plan=100,
        quantity_real=100,
        quantity_allocated=100,
        amount_allocated=Decimal("500.0000"),
        unit_price=Decimal("5.0000"),
        remark_item_id=None,
    )
    base.update(kw)
    row = DwdPurchaseOrderLineItem(id=uuid4(), **_source(), **base)
    session.add(row)
    return row


def _receipt_run(session: Session, status: str = "succeeded") -> tuple[UUID, UUID]:
    run_id, ref_id = uuid4(), uuid4()
    session.add(
        IntegrationSyncRun(
            id=run_id,
            interface_id=uuid4(),
            provider="lingxing",
            interface_key=f"receipt:{run_id.hex[:8]}",
            source_account_ref=ACCOUNT,
            trigger_type="manual",
            status=status,
            idempotency_key=f"receipt:{run_id}",
            queued_at=NOW,
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
            requested_at=NOW,
            received_at=NOW,
        )
    )
    session.flush()
    return run_id, ref_id


_ORDINALS: dict[UUID, int] = {}


def _receipt(
    session: Session,
    run: tuple[UUID, UUID],
    receipt_sn: str,
    order_item_id: str,
    receive_time: str,
    quantity: int,
) -> None:
    run_id, ref_id = run
    ordinal = _ORDINALS.get(ref_id, 0)
    _ORDINALS[ref_id] = ordinal + 1
    session.add(
        LingxingReceiptOrderOds(
            run_id=run_id,
            raw_request_ref_id=ref_id,
            source_account_ref=ACCOUNT,
            payload_json={},
            observed_at=NOW,
            source_item_ordinal=ordinal,
            order_sn=receipt_sn,
            receive_time=receive_time,
            item_count=1,
        )
    )
    session.add(
        LingxingReceiptOrderItemOds(
            run_id=run_id,
            raw_request_ref_id=ref_id,
            source_account_ref=ACCOUNT,
            payload_json={},
            observed_at=NOW,
            source_item_ordinal=ordinal,
            receipt_order_sn=receipt_sn,
            line_ordinal=0,
            order_item_id=order_item_id,
            product_receive_num=quantity,
        )
    )


def _refresh(session: Session, **kw: object) -> DwsPurchaseBoard | None:
    PmcPurchaseDwsRefresher(session, now=NOW, **kw).refresh(  # type: ignore[arg-type]
        source_account_ref=ACCOUNT, today=TODAY
    )
    return session.scalar(select(DwsPurchaseBoard).order_by(DwsPurchaseBoard.order_sn))


def _board(session: Session) -> dict[tuple[str, str, str], DwsPurchaseBoard]:
    return {
        (r.order_sn, r.order_item_id, r.plan_key): r
        for r in session.scalars(select(DwsPurchaseBoard))
    }


def _pending(session: Session) -> dict[str, list[DwsPurchasePending]]:
    out: dict[str, list[DwsPurchasePending]] = {}
    for r in session.scalars(select(DwsPurchasePending)):
        out.setdefault(r.pending_type, []).append(r)
    return out


# --- tests -------------------------------------------------------------------------------------


def test_arrived_order_row_metrics_attribution_and_dimensions(session: Session) -> None:
    _plan(session, "P1")
    _order(session, "PO1")
    _line(session, "PO1", "L1")
    run = _receipt_run(session)
    _receipt(session, run, "R1", "L1", "2026-08-18 10:00:00", 30)  # 30 % — not yet arrived
    _receipt(session, run, "R2", "L1", "2026-08-20 10:00:00", 30)  # 60 % — arrival
    session.commit()

    result = PmcPurchaseDwsRefresher(session, now=NOW).refresh(
        source_account_ref=ACCOUNT, today=TODAY
    )
    assert (result.board_rows, result.sku_cycle_rows, result.rule_version) == (1, 1, 1)
    assert result.calc_version == DWS_CALC_VERSION and result.receipt_lines == 2

    row = _board(session)[("PO1", "L1", "P1")]
    assert row.stage_code == "S9" and row.overdue_days == 0
    assert row.quantity_received == 60 and row.remaining_quantity == 40
    assert row.progress_ratio == Decimal("0.6000")
    assert row.arrival_date == date(2026, 8, 20) and row.arrival_receipt_order_sn == "R2"
    assert row.purchase_cycle_days == 15 and row.approval_cycle_days == 3
    # ItemID from the plan remark; listing / owner joined through it
    assert (row.item_id, row.item_id_source) == ("19051502014", "from_plan_remark")
    assert row.item_id_source_ref == "P1" and row.item_id_match_status == "matched"
    assert row.item_id_matched_at is not None
    assert (row.msku, row.gtin, row.fulfillment_type) == ("MSKU-A", "00012345678905", "0")
    assert row.wfs_not_ready is True
    assert (row.store_name, row.owner_uid, row.owner_name) == ("Store A", "u-1", "Owner One")
    assert (row.amount_allocated, row.unit_price, row.currency_code) == (
        Decimal("500.0000"),
        Decimal("5.0000"),
        "CNY",
    )
    assert row.source_lineage_json["rule_version"] == 1
    assert row.source_lineage_json["receipt_order_sns"] == ["R1", "R2"]

    # one arrived sample < 2 valid → falls back to the Lingxing default (12 d)
    cycle = session.scalar(select(DwsPurchaseSkuCycle))
    assert cycle is not None
    assert (cycle.sku, cycle.source, cycle.sample_count) == ("SKU-A", "lingxing_default", 1)
    assert cycle.value_days == Decimal("12") and cycle.lingxing_default_days == 12
    assert cycle.samples_json[0]["purchase_order_sn"] == "PO1"
    assert row.sku_cycle_days == Decimal("12") and row.sku_cycle_source == "lingxing_default"

    pending = _pending(session)
    assert set(pending) == {"wfs_not_ready"}


def test_stages_purchase_overdue_vs_arrival_overdue_and_unattributed_store(
    session: Session,
) -> None:
    _plan(session, "P1")
    # A: 待下单 12 days ago → S2 purchase overdue (7 d) by 5 days
    _order(session, "PO-A", status=1, order_date=None, create_date=TODAY - timedelta(days=12))
    _line(session, "PO-A", "LA", plan_sn=None, plan_key="", plan_found=False)
    # B: ordered 20 days ago, nothing received → S3 arrival overdue; no arrived sample for
    # SKU-A, so the threshold is the Lingxing default delivery (12 d) → overdue 8
    _order(session, "PO-B", order_date=TODAY - timedelta(days=20))
    _line(session, "PO-B", "LB")
    # C: ordered 20 days ago, 30 % received → S4 arrival overdue
    _order(session, "PO-C", order_date=TODAY - timedelta(days=20))
    _line(session, "PO-C", "LC")
    # D: same as B but sid = 0 → no overdue at all
    _order(session, "PO-D", order_date=TODAY - timedelta(days=20))
    _line(session, "PO-D", "LD", store_id=None, store_attributed=False, store_matched=False)
    # E: void
    _order(session, "PO-E", status=-1)
    _line(session, "PO-E", "LE")
    run = _receipt_run(session)
    _receipt(session, run, "R-C", "LC", (TODAY - timedelta(days=3)).isoformat() + " 09:00:00", 30)
    session.commit()

    result = PmcPurchaseDwsRefresher(session, now=NOW).refresh(
        source_account_ref=ACCOUNT, today=TODAY
    )
    board = _board(session)
    a, b, c, d, e = (
        board[("PO-A", "LA", "")],
        board[("PO-B", "LB", "P1")],
        board[("PO-C", "LC", "P1")],
        board[("PO-D", "LD", "P1")],
        board[("PO-E", "LE", "P1")],
    )
    assert (a.stage_code, a.overdue_days, a.threshold_days) == ("S2", 5, 7)
    assert (b.stage_code, b.overdue_days, b.threshold_days) == ("S3", 8, 12)
    assert (c.stage_code, c.overdue_days, c.quantity_received) == ("S4", 8, 30)
    assert (d.stage_code, d.overdue_days, d.due_date, d.store_attributed) == ("S3", 0, None, False)
    assert (e.stage_code, e.overdue_days) == ("S0", 0)
    assert result.stage_counts == {"S0": 1, "S2": 1, "S3": 2, "S4": 1}

    overdue = {p.order_sn: p for p in _pending(session)["overdue"]}
    assert set(overdue) == {"PO-A", "PO-B", "PO-C"}
    assert overdue["PO-A"].detail_json["overdue_kind"] == "purchase"
    assert overdue["PO-B"].detail_json["overdue_kind"] == "arrival"
    assert overdue["PO-C"].detail_json["overdue_kind"] == "arrival"
    # line without any plan: ItemID waits for the packing slip (no manual source)
    assert (a.item_id, a.item_id_source, a.item_id_match_status) == (
        None,
        "pending_packing_slip",
        "pending",
    )
    itemid_pending = {p.order_sn for p in _pending(session)["itemid_pending"]}
    assert itemid_pending == {"PO-A"}  # void PO-E is not listed


def test_sku_cycle_samples_manual_overrides_and_threshold_feed_stage(session: Session) -> None:
    _plan(session, "P1")
    run = _receipt_run(session)
    # five arrived orders: cycles 10, 12, 1 (auto short), 14, 11
    specs = [("PO1", 1, 10), ("PO2", 3, 12), ("PO3", 5, 1), ("PO4", 7, 14), ("PO5", 9, 11)]
    for sn, day, cycle in specs:
        ordered = date(2026, 8, day)
        _order(session, sn, order_date=ordered, quantity_total=10)
        _line(session, sn, f"L-{sn}", quantity_allocated=10, quantity_plan=10, quantity_real=10)
        _receipt(
            session, run, f"R-{sn}", f"L-{sn}", f"{ordered + timedelta(days=cycle)} 08:00:00", 10
        )
    # PO6: manual exclude; PO7: arrival date corrected to 13 d after order
    for sn, day, cycle in (("PO6", 11, 30), ("PO7", 13, 40)):
        ordered = date(2026, 8, day)
        _order(session, sn, order_date=ordered, quantity_total=10)
        _line(session, sn, f"L-{sn}", quantity_allocated=10, quantity_plan=10, quantity_real=10)
        _receipt(
            session, run, f"R-{sn}", f"L-{sn}", f"{ordered + timedelta(days=cycle)} 08:00:00", 10
        )
    # PO8: ordered 12 days ago, open → S3 whose threshold must come from the SKU cycle
    _order(session, "PO8", order_date=TODAY - timedelta(days=12), quantity_total=10)
    _line(session, "PO8", "L-PO8", quantity_allocated=10, quantity_plan=10, quantity_real=10)
    session.add_all(
        [
            ManualPurchaseCycleOverride(
                id=uuid4(),
                source_account_ref=ACCOUNT,
                sku="SKU-A",
                kind="exclude",
                purchase_order_sn="PO6",
                before_json={},
                after_json={"excluded": True},
                reason="临时补单",
                operator_ref="rocky",
                effective_from=NOW - timedelta(days=1),
            ),
            ManualPurchaseCycleOverride(
                id=uuid4(),
                source_account_ref=ACCOUNT,
                sku="SKU-A",
                kind="arrival_date",
                purchase_order_sn="PO7",
                value_date=date(2026, 8, 13) + timedelta(days=13),
                before_json={"arrival_date": "2026-09-22"},
                after_json={"arrival_date": "2026-08-26"},
                reason="收货单日期录错",
                operator_ref="rocky",
                effective_from=NOW - timedelta(days=1),
            ),
        ]
    )
    session.commit()

    result = PmcPurchaseDwsRefresher(session, now=NOW).refresh(
        source_account_ref=ACCOUNT, today=TODAY
    )
    assert result.overrides_active == 2
    cycle = session.scalar(select(DwsPurchaseSkuCycle))
    assert cycle is not None
    # newest first: PO7 (13, corrected) PO6 (manual) PO5 11 PO4 14 PO3 (auto) PO2 12 PO1 10
    # window 5 → used: 13, 11, 14, 12, 10 → avg 12, range 4 → unstable
    assert cycle.source == "samples" and cycle.sample_count == 5
    assert cycle.value_days == Decimal("12.0000") and cycle.unstable and cycle.range_days == 4
    by_sn = {s["purchase_order_sn"]: s for s in cycle.samples_json}
    assert by_sn["PO6"]["exclusion"] == "manual" and by_sn["PO3"]["exclusion"] == "auto_short"
    assert by_sn["PO7"]["cycle_days"] == 13 and by_sn["PO7"]["used"] is True
    assert (
        cycle.source_lineage_json["override_ids"]
        and len(cycle.source_lineage_json["override_ids"]) == 2
    )

    po8 = _board(session)[("PO8", "L-PO8", "P1")]
    assert (po8.stage_code, po8.threshold_days, po8.overdue_days) == ("S3", 12, 0)
    assert po8.sku_cycle_unstable is True


def test_baseline_override_and_refresh_is_idempotent(session: Session) -> None:
    _plan(session, "P1")
    run = _receipt_run(session)
    for sn, day, cycle in (("PO1", 1, 10), ("PO2", 20, 20)):
        ordered = date(2026, 8, day)
        _order(session, sn, order_date=ordered, quantity_total=10)
        _line(session, sn, f"L-{sn}", quantity_allocated=10, quantity_plan=10, quantity_real=10)
        _receipt(
            session, run, f"R-{sn}", f"L-{sn}", f"{ordered + timedelta(days=cycle)} 08:00:00", 10
        )
    session.add(
        ManualPurchaseCycleOverride(
            id=uuid4(),
            source_account_ref=ACCOUNT,
            sku="SKU-A",
            kind="baseline",
            value_days=8,
            before_json={},
            after_json={"baseline_days": 8},
            reason="供应商换厂",
            operator_ref="rocky",
            effective_from=datetime(2026, 8, 10, tzinfo=UTC),  # PO1 (08-01) is before the baseline
        )
    )
    session.commit()

    refresher = PmcPurchaseDwsRefresher(session, now=NOW)
    refresher.refresh(source_account_ref=ACCOUNT, today=TODAY)
    cycle = session.scalar(select(DwsPurchaseSkuCycle))
    assert cycle is not None
    assert (cycle.source, cycle.baseline_days, cycle.baseline_set_on) == (
        "baseline_mix",
        8,
        date(2026, 8, 10),
    )
    assert cycle.value_days == Decimal("14.0000")  # (8 + 20) / 2
    by_sn = {s["purchase_order_sn"]: s for s in cycle.samples_json}
    assert by_sn["PO1"]["exclusion"] == "before_baseline"

    # second run: same counts, rows replaced not duplicated
    refresher.refresh(source_account_ref=ACCOUNT, today=TODAY)
    assert session.scalar(select(func.count()).select_from(DwsPurchaseBoard)) == 2
    assert session.scalar(select(func.count()).select_from(DwsPurchaseSkuCycle)) == 1
    # DWD / manual untouched
    assert session.scalar(select(func.count()).select_from(DwdPurchaseOrder)) == 2
    assert session.scalar(select(func.count()).select_from(ManualPurchaseCycleOverride)) == 1


def test_packing_slip_source_is_used_when_available(session: Session) -> None:
    _order(session, "PO1")
    _line(session, "PO1", "L1", plan_sn=None, plan_key="", plan_found=False)
    session.commit()

    class Slips:
        def lookup(
            self, *, order_sn: str, order_item_id: str, sku: str | None, store_id: str | None
        ) -> PackingSlipMatch | None:
            if (order_sn, order_item_id) == ("PO1", "L1"):
                return PackingSlipMatch("19051502014", "PK-1", NOW - timedelta(hours=1))
            return None

    PmcPurchaseDwsRefresher(session, now=NOW, packing_slips=Slips()).refresh(
        source_account_ref=ACCOUNT, today=TODAY
    )
    row = _board(session)[("PO1", "L1", "")]
    assert (row.item_id, row.item_id_source, row.item_id_source_ref) == (
        "19051502014",
        "from_packing_slip",
        "PK-1",
    )
    assert row.item_id_matched_at is not None
    assert row.item_id_matched_at.replace(tzinfo=UTC) == NOW - timedelta(hours=1)  # sqlite drops tz
    assert row.msku == "MSKU-A"  # listing joined through the back-filled ItemID
    assert "itemid_pending" not in _pending(session)


def test_failed_receipt_runs_ignored_and_rule_or_account_errors(session: Session) -> None:
    _plan(session, "P1")
    _order(session, "PO1")
    _line(session, "PO1", "L1")
    failed = _receipt_run(session, status="failed")
    _receipt(session, failed, "R1", "L1", "2026-08-20 10:00:00", 100)
    session.commit()

    PmcPurchaseDwsRefresher(session, now=NOW).refresh(source_account_ref=ACCOUNT, today=TODAY)
    row = _board(session)[("PO1", "L1", "P1")]
    assert row.quantity_received == 0 and row.arrival_date is None and row.stage_code == "S3"

    with pytest.raises(PmcPurchaseDwsRefreshError, match="SOURCE_ACCOUNT_REF_INVALID"):
        PmcPurchaseDwsRefresher(session, now=NOW).refresh(source_account_ref=" ")
    with pytest.raises(PmcPurchaseDwsRefreshError, match="RULE_VERSION_MISSING"):
        PmcPurchaseDwsRefresher(session, now=NOW).refresh(
            source_account_ref=ACCOUNT, today=date(2026, 7, 31)
        )
    # after a failed refresh the previous DWS rows are still there (rollback, no delete)
    assert session.scalar(select(func.count()).select_from(DwsPurchaseBoard)) == 1

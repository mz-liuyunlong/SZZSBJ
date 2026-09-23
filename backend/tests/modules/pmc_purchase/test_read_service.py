"""G3-E: read service / repository against real DWS rows produced by the G3-D refresh
on an in-memory SQLite database (filters, sorting, batch search, summary, detail,
SKU cycles, pending plans, account scope)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.modules.pmc_purchase.refresh import PmcPurchaseDwsRefresher
from app.modules.pmc_purchase.schemas import (
    BoardFilterQuery,
    BoardListQuery,
    PendingPlanQuery,
    SkuCycleQuery,
)
from app.modules.pmc_purchase.service import PmcPurchaseReadService
from tests.modules.pmc_purchase.test_refresh import (
    ACCOUNT,
    NOW,
    STORE,
    TODAY,
    _line,
    _order,
    _plan,
    _receipt,
    _receipt_run,
    session,  # noqa: F401  (fixture re-export)
)

SCOPE = frozenset({ACCOUNT})


@pytest.fixture
def seeded(session: Session) -> Session:  # noqa: F811
    run = _receipt_run(session)
    _plan(session, "P1")
    _plan(session, "P2", sku="SKU-B", remark=None, remark_item_id=None)
    # pending plans: P3 approved 10 days ago (overdue), P4 2 days ago, P5 sid=0
    _plan(session, "P3", status=2, create_date=TODAY - timedelta(days=10), sku="SKU-C")
    _plan(session, "P4", status=2, create_date=TODAY - timedelta(days=2), sku="SKU-D")
    _plan(
        session,
        "P5",
        status=2,
        create_date=TODAY - timedelta(days=30),
        store_id=None,
        store_attributed=False,
        store_matched=False,
    )
    # PO1: arrived this month, SKU-A with ItemID
    _order(session, "PO1", order_date=TODAY - timedelta(days=15))
    _line(session, "PO1", "L1")
    _receipt(session, run, "R1", "L1", f"{TODAY - timedelta(days=5)} 10:00:00", 100)
    # PO2: S3 arrival overdue, SKU-B, no ItemID
    _order(session, "PO2", order_date=TODAY - timedelta(days=30), amount_total=Decimal("900"))
    _line(
        session,
        "PO2",
        "L2",
        sku="SKU-B",
        plan_sn="P2",
        plan_key="P2",
        unit_price=Decimal("9"),
        amount_allocated=Decimal("900"),
    )
    # PO3: 待下单 S2 purchase overdue
    _order(session, "PO3", status=1, order_date=None, create_date=TODAY - timedelta(days=20))
    _line(session, "PO3", "L3", plan_sn=None, plan_key="", plan_found=False)
    # PO4: sid=0
    _order(session, "PO4", order_date=TODAY - timedelta(days=40))
    _line(session, "PO4", "L4", store_id=None, store_attributed=False, store_matched=False)
    session.commit()
    PmcPurchaseDwsRefresher(session, now=NOW).refresh(source_account_ref=ACCOUNT, today=TODAY)
    return session


def test_board_filters_sorting_and_scope(seeded: Session) -> None:
    svc = PmcPurchaseReadService(seeded, today=TODAY)
    data, total, freshness, rule = svc.list_board(BoardListQuery(), SCOPE)
    assert total == 4 and rule == 1 and freshness is not None
    # default sort: order_date desc with NULL (PO3) last
    assert [i.purchase_order_sn for i in data.items] == ["PO1", "PO2", "PO4", "PO3"]

    data, total, *_ = svc.list_board(BoardListQuery(status=["overdue"]), SCOPE)
    assert {i.purchase_order_sn for i in data.items} == {"PO2", "PO3"}
    kinds = {i.purchase_order_sn: i.stage.overdue_kind for i in data.items}
    assert kinds == {"PO2": "arrival", "PO3": "purchase"}

    data, total, *_ = svc.list_board(BoardListQuery(status=["unattributed"]), SCOPE)
    assert [i.purchase_order_sn for i in data.items] == ["PO4"]
    assert data.items[0].store.attributed is False and data.items[0].stage.overdue_days == 0

    data, total, *_ = svc.list_board(
        BoardListQuery(search_type="sku", search_values=["SKU-A SKU-B", "nope"]), SCOPE
    )
    assert {i.sku for i in data.items} == {"SKU-A", "SKU-B"}

    data, total, *_ = svc.list_board(BoardListQuery(item_id_source=["pending_packing_slip"]), SCOPE)
    # PO4 inherits P1's remark ItemID even though its store is unattributed
    assert {i.purchase_order_sn for i in data.items} == {"PO2", "PO3"}

    data, total, *_ = svc.list_board(
        BoardListQuery(owner_uid=["u-1"], price_min=Decimal("5"), price_max=Decimal("5")), SCOPE
    )
    assert {i.purchase_order_sn for i in data.items} == {"PO1", "PO3", "PO4"}  # SKU-A owner u-1

    data, total, *_ = svc.list_board(BoardListQuery(today_followup=True), SCOPE)
    assert {i.purchase_order_sn for i in data.items} == {"PO2", "PO3"}

    data, total, *_ = svc.list_board(BoardListQuery(sort="amount_desc", page_size=1), SCOPE)
    assert total == 4 and data.items[0].purchase_order_sn == "PO2"

    # other account scope → nothing
    data, total, *_ = svc.list_board(BoardListQuery(), frozenset({"other"}))
    assert total == 0 and data.items == []


def test_summary_cards(seeded: Session) -> None:
    data, _freshness, rule = PmcPurchaseReadService(seeded, today=TODAY).summary(
        BoardFilterQuery(), SCOPE
    )
    assert rule == 1
    assert data.awaiting_arrival_orders == 2  # PO2 (S3) + PO4 (S3, unattributed)
    assert data.arrival_overdue_orders == 1  # PO2 only (PO4 sid=0 never overdue)
    assert data.purchase_overdue_orders == 1  # PO3 待下单 20 d
    assert data.purchase_overdue_plans == 1  # P3 (P4 fresh, P5 sid=0 suppressed)
    assert data.average_purchase_cycle_days_90d == Decimal("10.0000")  # PO1: 15 - 5
    assert data.month_purchase_amount == [] or all(
        m.currency_code == "CNY" for m in data.month_purchase_amount
    )
    assert data.itemid_pending_lines == 2 and data.unattributed_store_lines == 1
    assert data.wfs_not_ready_lines == 1  # PO1 listing fulfillment_type=0; PO4 has no store
    assert data.unstable_sku_count == 0


def test_order_detail_and_missing(seeded: Session) -> None:
    svc = PmcPurchaseReadService(seeded, today=TODAY)
    detail, _f, _r = svc.order_detail("PO1", SCOPE)
    assert detail.stage.stage_code == "S9" and detail.arrival_date == TODAY - timedelta(days=5)
    assert [r.receipt_order_sn for r in detail.receipts] == ["R1"]
    assert detail.receipts[0].is_arrival_receipt is True
    assert [p.plan_sn for p in detail.plans] == ["P1"]
    assert detail.plans[0].remark_item_id == "19051502014"
    assert detail.sku_cycles[0].sku == "SKU-A"
    assert detail.lines[0].item_id.gtin == "00012345678905"
    with pytest.raises(ApiError) as excinfo:
        svc.order_detail("PO1", frozenset({"other"}))
    assert excinfo.value.status_code == 404


def test_sku_cycles_with_missing(seeded: Session) -> None:
    data, _f, rule = PmcPurchaseReadService(seeded, today=TODAY).sku_cycles(
        SkuCycleQuery(sku=["SKU-A", " SKU-Z ", "SKU-A"]), SCOPE
    )
    assert [i.sku for i in data.items] == ["SKU-A"] and data.missing == ["SKU-Z"]
    assert data.items[0].samples[0].purchase_order_sn == "PO1"
    assert rule == 1


def test_pending_plans_drill_down(seeded: Session) -> None:
    svc = PmcPurchaseReadService(seeded, today=TODAY)
    data, total, rule = svc.pending_plans(PendingPlanQuery(), SCOPE)
    assert total == 3 and rule == 1 and data.threshold_days == 7
    by_sn = {i.plan_sn: i for i in data.items}
    assert set(by_sn) == {"P3", "P4", "P5"}  # P1/P2 are on order lines → not pending
    assert (by_sn["P3"].pending_days, by_sn["P3"].overdue_days) == (10, 3)
    assert by_sn["P3"].pending_since_estimated is True  # first window: no observation date
    assert by_sn["P4"].overdue_days == 0
    assert by_sn["P5"].overdue_days == 0 and by_sn["P5"].store.attributed is False
    assert by_sn["P3"].store.name == "Store A"

    data, total, _ = svc.pending_plans(PendingPlanQuery(overdue_only=True), SCOPE)
    assert [i.plan_sn for i in data.items] == ["P3"]
    data, total, _ = svc.pending_plans(PendingPlanQuery(store_id=[STORE], page_size=1), SCOPE)
    assert total == 2 and len(data.items) == 1
    data, total, _ = svc.pending_plans(PendingPlanQuery(search_values=["SKU-D"]), SCOPE)
    assert [i.plan_sn for i in data.items] == ["P4"]

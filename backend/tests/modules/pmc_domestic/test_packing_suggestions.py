"""Synthetic read projections and approval guards; no configured database is connected."""

from datetime import UTC, date, datetime
from fractions import Fraction
from types import SimpleNamespace as Row
from uuid import uuid4

import pytest

from app.core.api import ApiError
from app.modules.pmc_domestic.packing_procurement_repository import PackingProcurementRepository
from app.modules.pmc_domestic.packing_repository import PackingRepository, matches
from app.modules.pmc_domestic.packing_schemas import Candidate, PackingQuery
from app.modules.pmc_domestic.packing_service import PackingService
from app.modules.pmc_domestic.packing_suggestions import (
    arrival_metrics,
    batch_metrics,
    suggest_quantities,
)
from app.modules.pmc_purchase.gate3_models import DwdPurchaseOrderLineItem as Line
from app.modules.pmc_purchase.models import LingxingPurchaseOrderItemOds as Item
from app.modules.pmc_purchase.models import LingxingPurchasePlanOds as Plan
from app.modules.sku_detail.models import LingxingSkuProductInfoCurrent as Product

A, B = "11111111111", "22222222222"


@pytest.mark.parametrize(
    "total,received,outstanding,status,pending",
    [
        (100, [30, 20], [20, 30], "partial", 50),
        (100, [0], [100], "none", 100),
        (100, [120], [0], "full", 0),
        (100, [None], [40], "unknown", 40),
        (None, [10], [40], "unknown", 40),
        (100, [], [], "unknown", None),
        (100, [True], [40], "unknown", 40),
        (100, [-1], [40], "unknown", 40),
        (100, [60], [None], "unknown", None),
        (100, [60], [True], "unknown", None),
        (100, [60], [-1], "unknown", None),
        (100, [60], [0], "unknown", 0),
    ],
)
def test_cumulative_arrival(total, received, outstanding, status, pending):
    value = arrival_metrics(total, received, outstanding)
    assert value["arrival_status"] == status
    assert value["arrival_pending"] == pending


def test_ratio_boxes_and_visible_tail():
    quantities, tail = suggest_quantities(103, 103, {A: Fraction(3), B: Fraction(2)}, {}, 10)
    assert quantities == {A: 60, B: 40}
    assert tail == 3
    # Once A has been approved, B keeps its share instead of receiving A's share again.
    assert suggest_quantities(103, 43, {A: Fraction(3), B: Fraction(2)}, {A: 60}, 10)[0] == {
        A: 0,
        B: 40,
    }


def test_no_box_uses_integer_remainders_and_stock_cap():
    values, tail = suggest_quantities(11, 11, {A: Fraction(1), B: Fraction(1)}, {}, None)
    assert values == {A: 6, B: 5} and tail == 0
    assert (
        sum(suggest_quantities(100, 13, {A: Fraction(1), B: Fraction(1)}, {}, 10)[0].values()) <= 13
    )
    assert suggest_quantities(10, 10, {}, {}, 10) == ({}, None)


def test_observed_batches_distinguish_partial_and_incomplete_history():
    batches = {"IB2": date(2026, 10, 2), "IB1": date(2026, 10, 1)}
    assert batch_metrics(batches, "IB2", "full", False) == {
        "split_arrival": True,
        "arrival_batch_count": 2,
        "arrival_batch_index": 2,
    }
    assert batch_metrics({"IB1": date.today()}, "IB1", "full", False)["split_arrival"] is None
    assert batch_metrics({"IB1": date.today()}, "IB1", "full", True)["split_arrival"] is False
    assert batch_metrics({"IB1": None}, "IB1", "partial", False)["arrival_batch_index"] is None


class Session:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def scalars(self, query):
        self.queries.append(query)
        return self.rows.get(query.column_descriptions[0]["entity"], [])


def line(plan, quantity, item="L1", order="PO1"):
    return Row(
        source_account_ref="primary",
        order_sn=order,
        order_item_id=item,
        sku="SKU",
        store_id="S1",
        plan_sn=plan,
        quantity_real=100,
        quantity_allocated=quantity,
    )


def plan(sn, item, quantity):
    return Row(
        source_account_ref="primary",
        plan_sn=sn,
        sku="SKU",
        sid="S1",
        remark=item,
        plan_remark=None,
        quantity_plan=quantity,
        is_aux=0,
        is_combo=0,
        payload_json={},
        observed_at=datetime.now(UTC),
        id=uuid4(),
    )


def test_original_purchase_line_not_duplicated_by_plan_splits():
    old = Row(
        source_account_ref="primary",
        order_sn="PO1",
        item_id="L1",
        sku="SKU",
        quantity_real=100,
        quantity_receive=70,
        is_delete=0,
        payload_json={"quantity_entry": 30},
        observed_at=datetime(2026, 10, 1, tzinfo=UTC),
        id=uuid4(),
    )
    new = Row(
        **{
            **vars(old),
            "quantity_receive": 40,
            "payload_json": {"quantity_entry": 60},
            "observed_at": datetime(2026, 10, 2, tzinfo=UTC),
            "id": uuid4(),
        }
    )
    session = Session({Item: [old, new], Plan: [plan("P1", A, 60), plan("P2", B, 40)]})
    repo = PackingProcurementRepository(
        session, {"primary"}, {"SKU"}, [line("P1", 60), line("P2", 40)]
    )
    data = repo.arrival("primary", "SKU", ["PO1", "PO1"])
    assert data["arrival_purchased"] == 100 and data["arrival_received"] == 60
    assert data["arrival_pending"] == 40
    assert data["arrival_status"] == "partial"
    new.payload_json = {}  # Missing entry must not be inferred from purchase minus pending.
    assert repo.arrival("primary", "SKU", ["PO1"])["arrival_received"] is None
    assert repo.arrival("primary", "SKU", ["PO1"])["arrival_pending"] == 40
    new.payload_json = {"quantity_entry": 60}
    assert repo.arrival("other", "SKU", ["PO1"])["arrival_received"] is None
    weights, refs = repo.weights("primary", "SKU", "S1", ["PO1"], {A, B}, {A, B})
    assert weights == {A: Fraction(60), B: Fraction(40)} and len(refs) == 2
    # Latest successful evidence query must remain scoped and exclude failed runs.
    sql = str(session.queries[0])
    assert "source_account_ref IN" in sql and "gov_integration_sync_runs.status" in sql
    new.quantity_real = 120  # DWD and latest ODS do not describe the same purchase quantity.
    assert repo.arrival("primary", "SKU", ["PO1"])["arrival_received"] is None


def test_plan_ambiguity_and_box_conflict_require_manual_input():
    p = plan("P1", f"{A} {B}", 100)
    session = Session(
        {
            Plan: [p],
            Product: [
                Row(source_account_ref="primary", lingxing_sku_code="SKU", box_pcs=10),
                Row(source_account_ref="primary", lingxing_sku_code="SKU", box_pcs=20),
            ],
        }
    )
    repo = PackingProcurementRepository(session, {"primary"}, {"SKU"}, [line("P1", 100)])
    assert repo.weights("primary", "SKU", "S1", ["PO1"], {A, B}, {A, B}) == ({}, [])
    assert repo.box("primary", "SKU") == (None, None)
    p.remark = A
    p.sid = "OTHER"
    assert repo.weights("primary", "SKU", "S1", ["PO1"], {A}, {A}) == ({}, [])


def test_one_plan_linked_to_two_orders_does_not_duplicate_its_weight():
    session = Session({Plan: [plan("P1", A, 100)]})
    repo = PackingProcurementRepository(
        session,
        {"primary"},
        {"SKU"},
        [
            line("P1", 60),
            line("P1", 40, item="L2", order="PO2"),
        ],
    )
    assert repo.weights("primary", "SKU", "S1", ["PO1"], {A}, {A})[0] == {A: Fraction(60)}


def test_wfs_guard_revalidates_even_when_listings_are_injected():
    service = PackingService(Session({}))
    service.listing_rows = lambda _: [Row(store_id="S1", item_id=A, fulfillment_type="0")]
    with pytest.raises(ApiError) as error:
        service.final_candidate(
            Row(store_id="S1", item_id=A), Row(target_store_id=None, target_item_id=None)
        )
    assert error.value.details["reason"] == "WFS_NOT_CONVERTED"


def test_candidate_keeps_unconverted_row_blocked(monkeypatch):
    from app.modules.data_pages.models import WalmartListingDimension as Listing
    from app.modules.pmc_domestic import packing_repository as module
    from app.modules.pmc_domestic.inbound_models import DomesticInboundBoard as Board
    from app.modules.pmc_domestic.inbound_schemas import ItemIdentity

    ident = uuid4()
    board = Row(
        id=ident,
        source_account_ref="primary",
        source_warehouse_id="16168",
        sku="SKU",
        store_id="S1",
        payload_json={"available_good_num": 100, "purchase_order_sns": []},
        inbound_order_sn="IB1",
        balance_num=100,
        arrival_business_date=date.today(),
    )
    pub = Row(id=uuid4(), source_observed_at=datetime.now(UTC))
    listing = Row(
        source_account_ref="primary",
        local_sku="SKU",
        store_id="S1",
        item_id=A,
        standard_status="PUBLISHED",
        fulfillment_type="0",
        gtin="00000000000000",
        msku="M1",
        business_hash="a" * 64,
    )

    class CandidateSession(Session):
        def execute(self, query):
            entities = [d["entity"] for d in query.column_descriptions]
            return (
                Row(all=lambda: [(board, pub)])
                if len(entities) == 2 and entities[0] is Board
                else []
            )

    def attach(_, rows, __):
        for row in rows:
            row.item_identities = [ItemIdentity(item_id=A, gtin=listing.gtin)]

    monkeypatch.setattr(module, "attach_board_item_ids", attach)
    monkeypatch.setattr(
        module.PackingStockRepository,
        "budgets",
        lambda *_: {
            ("primary", "16168", "SKU"): Row(available=100),
        },
    )
    monkeypatch.setattr(PackingRepository, "orders", lambda *_: [])
    repo = PackingRepository(CandidateSession({Listing: [listing], Line: [], Board: [board]}))
    candidate = repo.candidates({"primary"})[0]
    assert candidate.item_id == A and candidate.can_approve is False
    assert candidate.blocked_reasons == ["WFS_NOT_CONVERTED"]
    listing.fulfillment_type = "1"
    assert repo.candidates({"primary"})[0].can_approve is True
    candidate.split_arrival = True
    assert matches(candidate, PackingQuery(split_arrival="yes"))
    assert not matches(candidate, PackingQuery(split_arrival="no"))
    # New fields remain optional for old immutable approval snapshots.
    old = candidate.model_dump(exclude={"split_arrival", "quantity_suggestion"})
    assert Candidate.model_validate(old).quantity_suggestion is None

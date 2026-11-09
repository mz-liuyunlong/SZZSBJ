"""Synthetic scale and query-shape regression; no business database is contacted."""

from datetime import UTC, date, datetime
from types import SimpleNamespace as Row
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.modules.data_pages.models import WalmartListingDimension as Listing
from app.modules.pmc_domestic import packing_repository as module
from app.modules.pmc_domestic.inbound_models import DomesticInboundBoard as Board
from app.modules.pmc_domestic.inbound_schemas import ItemIdentity
from app.modules.pmc_domestic.packing_models import PackingAllocation, PackingOrder
from app.modules.pmc_domestic.packing_procurement_repository import PackingProcurementRepository
from app.modules.pmc_domestic.packing_stock_models import PackingExtraAllocation as Extra
from app.modules.pmc_domestic.packing_stock_repository import PackingStockRepository
from app.modules.pmc_purchase.gate3_models import DwdPurchaseOrderLineItem as Line
from app.modules.pmc_purchase.models import LingxingPurchasePlanOds as Plan


class Rows(list):
    def all(self):
        return self


def sql(query):
    return str(query.compile(dialect=postgresql.dialect()))


@pytest.mark.parametrize("count", [1, 500])
def test_candidate_queries_are_batched_and_preserve_full_plan_denominator(monkeypatch, count):
    boards, listings, lines, plans = [], [], [], []
    for i in range(count):
        account = f"account-{i % 2}"
        sku, order, plan = f"SKU-{i}", f"PO-{i}", f"PLAN-{i}"
        board = Row(
            id=uuid4(),
            source_account_ref=account,
            source_warehouse_id="16168",
            sku=sku,
            store_id="S1",
            balance_num=100,
            arrival_business_date=date.today(),
            inbound_order_sn=f"IB-{i}",
            payload_json={"available_good_num": 100, "purchase_order_sns": [order]},
        )
        boards.append((board, Row(id=uuid4(), source_observed_at=datetime.now(UTC))))
        listings.append(
            Row(
                source_account_ref=account,
                store_id="S1",
                local_sku=sku,
                item_id="11111111111",
                standard_status="PUBLISHED",
                fulfillment_type="1",
                item_url="https://www.walmart.com/ip/synthetic",
                gtin="00000000000000",
                msku=sku,
                business_hash="a" * 64,
            )
        )
        lines.append(
            Row(
                source_account_ref=account,
                sku=sku,
                store_id="S1",
                order_sn=order,
                order_item_id=f"item-{i}",
                plan_sn=plan,
                quantity_real=100,
                quantity_allocated=40,
            )
        )
        plans.append(
            Row(
                source_account_ref=account,
                sku=sku,
                sid="S1",
                plan_sn=plan,
                remark="11111111111",
                plan_remark=None,
                is_aux=0,
                is_combo=0,
                quantity_plan=100,
                payload_json={},
                id=uuid4(),
                observed_at=datetime.now(UTC),
            )
        )

    class Session:
        def __init__(self):
            self.queries = []

        def execute(self, query):
            self.queries.append(query)
            entities = [d["entity"] for d in query.column_descriptions]
            if len(entities) == 2 and entities[0] is Board:
                return Rows(boards)
            if entities[0] is Line:
                # Other orders sharing the same plan contribute the remaining 60.
                return Rows((p.source_account_ref, p.plan_sn, 100) for p in plans)
            return Rows()

        def scalars(self, query):
            self.queries.append(query)
            return {Listing: listings, Line: lines, Plan: plans, Board: [b for b, _ in boards]}.get(
                query.column_descriptions[0]["entity"], []
            )

    def attach(_, rows, __):
        for row in rows:
            row.item_identities = [ItemIdentity(item_id="11111111111")]

    monkeypatch.setattr(module, "attach_board_item_ids", attach)
    monkeypatch.setattr(
        module.PackingStockRepository,
        "budgets",
        lambda _, keys: {key: Row(available=100) for key in keys},
    )
    session = Session()
    result = module.PackingRepository(session).candidates({"account-0", "account-1"})
    assert len(result) == count
    assert all(r.quantity_suggestion.plan_weights == {"11111111111": 40.0} for r in result)
    # Fixed number of batch queries, independent of candidate/SKU count (the second
    # listing query, by attributed item id, was added by ItemID rule v2 on 2026-10-31).
    assert len(session.queries) == 15
    dwd = next(q for q in session.queries if q.column_descriptions[0]["expr"] is Line)
    assert (
        "(dwd_purchase_order_line_item.source_account_ref, "
        "dwd_purchase_order_line_item.order_sn, dwd_purchase_order_line_item.sku) IN"
    ) in sql(dwd)
    expected = {
        (b.source_account_ref, b.payload_json["purchase_order_sns"][0], b.sku) for b, _ in boards
    }
    assert any(
        set(value) == expected for value in dwd.compile().params.values() if isinstance(value, list)
    )
    decisions = next(
        q for q in session.queries if q.column_descriptions[0]["entity"] is PackingOrder
    )
    assert "snapshot_json" not in sql(decisions)
    assert "source_board_id IN" in sql(decisions)
    for query in session.queries:
        if query.column_descriptions[0]["entity"] in {PackingAllocation, Extra}:
            assert "source_board_id IN" in sql(query)


def test_weight_lookup_does_not_scan_unrelated_sku_buckets():
    class ForbiddenBucket:
        def __iter__(self):
            raise AssertionError("unrelated SKU scanned")

    repo = PackingProcurementRepository(Row(scalars=lambda _: []), set(), set(), [])
    repo.lines_by_key.update(
        {("account", f"SKU-{i}", "S1", "PO"): ForbiddenBucket() for i in range(10000)}
    )
    assert repo.weights("account", "target", "S1", ["PO"], {"1"}, {"1"}) == ({}, [])
    assert repo.weights("other-account", "SKU-1", "S1", ["PO"], {"1"}, {"1"}) == ({}, [])
    assert not repo.plan_totals


@pytest.mark.parametrize("count", [1, 1000])
def test_stock_batch_keeps_orphan_holds_without_per_sku_queries(count):
    boards = [
        Row(
            id=uuid4(),
            publication_id=uuid4(),
            source_account_ref="account",
            source_warehouse_id="16168",
            sku=f"SKU-{i}",
            payload_json={"available_good_num": 100},
        )
        for i in range(count)
    ]
    orphan = uuid4()

    class Session:
        def __init__(self):
            self.queries = []

        def scalars(self, query):
            self.queries.append(query)
            if query.column_descriptions[0]["entity"] is Board:
                return boards
            return [
                Row(
                    source_account_ref="account",
                    warehouse_id="16168",
                    sku=b.sku,
                    source_board_id=orphan,
                    qty=5,
                )
                for b in boards
            ]

        def execute(self, query):
            self.queries.append(query)
            return [
                (
                    Row(
                        source_account_ref="account",
                        warehouse_id="16168",
                        source_board_id=orphan,
                        qty=60,
                    ),
                    b.sku,
                )
                for b in boards
            ]

    session = Session()
    budgets = PackingStockRepository(session).budgets({("account", "16168", b.sku) for b in boards})
    assert len(session.queries) == 3
    assert all(b.available == 35 and b.held == 65 for b in budgets.values())
    assert all(b.sources[0][1] == 100 for b in budgets.values())
    # Keep stock headroom across all holds for requested SKU, including old boards.
    assert all("source_board_id IN" not in sql(q) for q in session.queries)
    assert all(" IN " in sql(q) for q in session.queries)

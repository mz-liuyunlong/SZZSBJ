from __future__ import annotations

import tracemalloc
from datetime import UTC, date, datetime
from decimal import Decimal
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.modules.product_management.repository import ProductManagementRepository
from app.modules.product_management.service import ProductManagementService
from app.modules.warehouse_wfs.anomaly_detection import (
    WfsSalesEvidence,
    WfsStandardFee,
    detect_wfs_anomalies,
)
from app.modules.warehouse_wfs.fee_detection import resolve_wfs_fees
from app.modules.warehouse_wfs.sales_reader import read_walmart_lifetime_sales_batch
from app.modules.warehouse_wfs.settlement_parser import parse_settlement_rows
from app.modules.warehouse_wfs.standard_fee_reader import read_product_management_wfs_fees


def _result(rows: list[object]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


def test_standard_fee_batch_query_count_is_constant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identities = frozenset(
        ("account-a", "store-a", f"item-{index}", f"MSKU-{index}") for index in range(100)
    )
    product_ids = {index: uuid4() for index in range(100)}
    sku_identity_ids = {index: uuid4() for index in range(100)}
    session = MagicMock()
    session.execute.side_effect = [
        _result(
            [
                ("account-a", "store-a", f"item-{index}", f"MSKU-{index}", f"SKU-{index}")
                for index in range(100)
            ]
        ),
        _result([(f"SKU-{index}", product_ids[index]) for index in range(100)]),
        _result(
            [("account-a", product_ids[index], sku_identity_ids[index]) for index in range(100)]
        ),
    ]
    session.scalars.side_effect = [
        _result([SimpleNamespace(identity_id=sku_identity_ids[index]) for index in range(100)]),
        _result([SimpleNamespace(identity_id=sku_identity_ids[index]) for index in range(100)]),
    ]
    active_rule = SimpleNamespace(version="confirmed-v1")
    monkeypatch.setattr(
        ProductManagementRepository,
        "list_effective_rules",
        lambda *_args, **_kwargs: {"account-a": active_rule},
    )
    monkeypatch.setattr(
        ProductManagementService,
        "_sku_pricing_rule",
        staticmethod(lambda _rule: SimpleNamespace()),
    )
    monkeypatch.setattr(
        ProductManagementService,
        "_sku_pricing_calculation",
        staticmethod(
            lambda *_args: SimpleNamespace(
                wfs_fulfillment_fee_usd=Decimal("6.55"),
                wfs_calc_status="ok",
            )
        ),
    )

    result = read_product_management_wfs_fees(session, identities=identities)

    assert len(result) == 100
    assert session.execute.call_count == 3
    assert session.scalars.call_count == 2


def test_sales_batch_query_count_is_constant_for_100_identities() -> None:
    identities = frozenset(
        ("account-a", "store-a", f"item-{index}", f"MSKU-{index}") for index in range(100)
    )
    listing_start = datetime(2026, 7, 3, 7, tzinfo=UTC)
    session = MagicMock()
    session.execute.side_effect = [
        _result([(*identity, listing_start) for identity in identities]),
        _result(
            [
                (*identity, Decimal("87"), date(2026, 7, 3), date(2026, 9, 22), 31)
                for identity in identities
            ]
        ),
        _result(
            [
                (
                    "account-a",
                    datetime(2026, 7, 3, tzinfo=UTC),
                    datetime(2026, 10, 17, tzinfo=UTC),
                    {"store_id": "store-a"},
                )
            ]
        ),
    ]

    result = read_walmart_lifetime_sales_batch(
        session,
        identities=identities,
        required_coverage_end=date(2026, 10, 17),
    )

    assert len(result) == 100
    assert all(item.coverage_status == "complete" for item in result.values())
    assert session.execute.call_count == 3


@pytest.mark.parametrize(
    ("store_count", "sku_count"),
    [(1, 100), (9, 1_000), (20, 10_000)],
)
def test_synthetic_collection_and_detection_scale(
    store_count: int,
    sku_count: int,
) -> None:
    rows_by_store: dict[str, list[dict[str, object]]] = {
        f"store-{index}": [] for index in range(store_count)
    }
    for index in range(sku_count):
        store_id = f"store-{index % store_count}"
        rows_by_store[store_id].append(
            {
                "storeId": store_id,
                "storeName": f"Store {index % store_count}",
                "msku": f"MSKU-{index}",
                "settlementDate": "2026-10-17",
                "uniqueId": f"source-{index}",
                "rowIndex": 0,
                "platformOrderNo": f"order-{index}",
                "salesNum": 1,
                "platformLogisticsAmount": "-6.95",
                "currencyCode": "USD",
                "platformCode": "10008",
                "transactionTypes": 0,
            }
        )

    tracemalloc.start()
    started = perf_counter()
    parsed_rows = []
    for store_id, store_rows in rows_by_store.items():
        parsed = parse_settlement_rows(
            store_rows,
            source_account_ref="account-a",
            expected_store_id=store_id,
            window_start=date(2026, 10, 17),
            window_end=date(2026, 10, 17),
            wfs_scope_verified=True,
        )
        assert parsed.rejected_rows == 0
        parsed_rows.extend(parsed.rows)
    collection_seconds = perf_counter() - started

    detection_started = perf_counter()
    actual = resolve_wfs_fees(parsed_rows, min_sample_units=1)
    standards = [
        WfsStandardFee(
            source_account_ref=item.source_account_ref,
            store_id=item.store_id,
            msku=item.msku,
            unit_fee=Decimal("6.55"),
            source="product_management_rule",
            rule_version="synthetic-v1",
        )
        for item in actual
    ]
    sales = {
        (item.source_account_ref, item.store_id, item.msku): WfsSalesEvidence(
            historical_units=Decimal("1"),
            sales_start_date=date(2026, 10, 17),
            sales_end_date=date(2026, 10, 17),
            coverage_status="complete",
            coverage_start_date=date(2026, 10, 17),
            coverage_end_date=date(2026, 10, 17),
            coverage_reason="synthetic_complete",
            source_watermark="synthetic",
        )
        for item in actual
    }
    detection = detect_wfs_anomalies(
        actual,
        standards,
        sales,
        as_of=date(2026, 10, 26),
    )
    detection_seconds = perf_counter() - detection_started
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert len(parsed_rows) == sku_count
    assert len(actual) == sku_count
    assert detection.anomalies == sku_count
    assert all(candidate.case_eligible for candidate in detection.candidates)
    print(
        "WFS_PERF "
        f"stores={store_count} skus={sku_count} sql_queries=0 "
        f"collection_ms={collection_seconds * 1000:.2f} "
        f"detection_ms={detection_seconds * 1000:.2f} "
        f"peak_mib={peak_bytes / 1024 / 1024:.2f}"
    )

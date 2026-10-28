from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.modules.warehouse_wfs.fee_detection import SettlementFeeRow
from app.modules.warehouse_wfs.settlement_repository import (
    WfsSettlementPersistenceError,
    WfsSettlementRepository,
)


def settlement_row() -> SettlementFeeRow:
    return SettlementFeeRow(
        source_account_ref="account-a",
        store_id="store-a",
        msku="SKU-A",
        platform_order_no="order-a",
        sales_num=Decimal("1"),
        platform_logistics_amount=Decimal("-6.95"),
        settlement_date="2026-10-10",
        source_line_ref="store-a:source-a:1",
    )


def test_upsert_is_idempotent_only_for_the_same_source_identity() -> None:
    session = MagicMock()
    listing_result = MagicMock()
    listing_result.all.return_value = [("account-a", "store-a", "SKU-A", "item-a")]
    upsert_result = MagicMock()
    upsert_result.scalars.return_value.all.return_value = [uuid4()]
    session.execute.side_effect = [listing_result, upsert_result]

    written = WfsSettlementRepository(session).upsert_rows(
        (settlement_row(),),
        raw_request_ref_id=uuid4(),
        collection_id=uuid4(),
        observed_at=datetime(2026, 10, 18, tzinfo=UTC),
    )

    assert written == 1
    statement = session.execute.call_args_list[1].args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (source_account_ref, source_line_ref) DO UPDATE" in sql
    assert "fact_walmart_wfs_fee_actual.store_id = excluded.store_id" in sql
    assert "fact_walmart_wfs_fee_actual.item_id = excluded.item_id" in sql
    assert "fact_walmart_wfs_fee_actual.msku = excluded.msku" in sql
    assert "RETURNING fact_walmart_wfs_fee_actual.id" in sql


def test_source_line_identity_conflict_fails_closed() -> None:
    session = MagicMock()
    listing_result = MagicMock()
    listing_result.all.return_value = [("account-a", "store-a", "SKU-A", "item-a")]
    upsert_result = MagicMock()
    upsert_result.scalars.return_value.all.return_value = []
    session.execute.side_effect = [listing_result, upsert_result]

    with pytest.raises(
        WfsSettlementPersistenceError,
        match="WFS_SETTLEMENT_SOURCE_IDENTITY_CONFLICT",
    ):
        WfsSettlementRepository(session).upsert_rows(
            (settlement_row(),),
            raw_request_ref_id=uuid4(),
            collection_id=uuid4(),
        )


def test_ambiguous_listing_identity_is_never_persisted() -> None:
    session = MagicMock()
    listing_result = MagicMock()
    listing_result.all.return_value = [
        ("account-a", "store-a", "SKU-A", "item-a"),
        ("account-a", "store-a", "SKU-A", "item-b"),
    ]
    session.execute.return_value = listing_result

    with pytest.raises(
        WfsSettlementPersistenceError,
        match="WFS_SETTLEMENT_IDENTITY_UNRESOLVED",
    ):
        WfsSettlementRepository(session).upsert_rows(
            (settlement_row(),),
            raw_request_ref_id=uuid4(),
            collection_id=uuid4(),
        )

    assert session.execute.call_count == 1


def test_duplicate_source_identity_in_one_batch_fails_before_database() -> None:
    session = MagicMock()

    with pytest.raises(
        WfsSettlementPersistenceError,
        match="WFS_SETTLEMENT_DUPLICATE_SOURCE_IDENTITY",
    ):
        WfsSettlementRepository(session).upsert_rows(
            (settlement_row(), settlement_row()),
            raw_request_ref_id=uuid4(),
            collection_id=uuid4(),
        )

    session.execute.assert_not_called()


def test_large_batch_uses_one_listing_read_and_one_upsert() -> None:
    session = MagicMock()
    rows = tuple(
        SettlementFeeRow(
            source_account_ref="account-a",
            store_id="store-a",
            msku=f"SKU-{index}",
            platform_order_no=f"order-{index}",
            sales_num=Decimal("1"),
            platform_logistics_amount=Decimal("-6.95"),
            settlement_date="2026-10-10",
            source_line_ref=f"store-a:source-{index}:1",
        )
        for index in range(1_000)
    )
    listing_result = MagicMock()
    listing_result.all.return_value = [
        ("account-a", "store-a", f"SKU-{index}", f"item-{index}") for index in range(1_000)
    ]
    upsert_result = MagicMock()
    upsert_result.scalars.return_value.all.return_value = [uuid4() for _ in rows]
    session.execute.side_effect = [listing_result, upsert_result]

    written = WfsSettlementRepository(session).upsert_rows(
        rows,
        raw_request_ref_id=uuid4(),
        collection_id=uuid4(),
    )

    assert written == 1_000
    assert session.execute.call_count == 2


def test_collection_records_explicit_verified_wfs_scope() -> None:
    session = MagicMock()
    collection = WfsSettlementRepository(session).create_collection(
        run_id=uuid4(),
        source_account_ref="account-a",
        store_id="store-a",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 10, 17),
        wfs_scope_status="verified_wfs",
    )

    assert collection.wfs_scope_status == "verified_wfs"
    assert collection.missing_store_count == 0


def test_collection_rejects_unknown_fee_scope() -> None:
    with pytest.raises(WfsSettlementPersistenceError, match="WFS_SETTLEMENT_SCOPE_INVALID"):
        WfsSettlementRepository(MagicMock()).create_collection(
            run_id=uuid4(),
            source_account_ref="account-a",
            store_id="store-a",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 10, 17),
            wfs_scope_status="guessed",
        )


def test_collection_with_unknown_store_row_cannot_be_verified() -> None:
    session = MagicMock()
    session.scalar.return_value = 1
    collection = WfsSettlementRepository(session).create_collection(
        run_id=uuid4(),
        source_account_ref="account-a",
        store_id="store-a",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 10, 17),
        wfs_scope_status="verified_wfs",
    )

    with pytest.raises(WfsSettlementPersistenceError, match="WFS_COLLECTION_INCOMPLETE"):
        WfsSettlementRepository(session).finalize_collection(
            collection,
            expected_total=2,
            captured_count=2,
            accepted_count=1,
            business_excluded_count=0,
            invalid_count=0,
            missing_store_count=1,
            duplicate_count=0,
            missing_identity_count=0,
            latest_settlement_date=date(2026, 10, 17),
        )

    assert collection.collection_status == "partial"
    assert collection.error_code == "SYNC_WFS_COLLECTION_INCOMPLETE"

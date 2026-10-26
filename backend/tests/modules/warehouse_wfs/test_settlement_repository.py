from datetime import UTC, datetime
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
    session.scalars.return_value.all.return_value = ["item-a"]
    session.execute.return_value.scalar_one_or_none.return_value = uuid4()

    written = WfsSettlementRepository(session).upsert_rows(
        (settlement_row(),),
        raw_request_ref_id=uuid4(),
        observed_at=datetime(2026, 10, 18, tzinfo=UTC),
    )

    assert written == 1
    statement = session.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (source_account_ref, source_line_ref) DO UPDATE" in sql
    assert "fact_walmart_wfs_fee_actual.store_id = excluded.store_id" in sql
    assert "fact_walmart_wfs_fee_actual.item_id = excluded.item_id" in sql
    assert "fact_walmart_wfs_fee_actual.msku = excluded.msku" in sql
    assert "RETURNING fact_walmart_wfs_fee_actual.id" in sql


def test_source_line_identity_conflict_fails_closed() -> None:
    session = MagicMock()
    session.scalars.return_value.all.return_value = ["item-a"]
    session.execute.return_value.scalar_one_or_none.return_value = None

    with pytest.raises(
        WfsSettlementPersistenceError,
        match="WFS_SETTLEMENT_SOURCE_IDENTITY_CONFLICT",
    ):
        WfsSettlementRepository(session).upsert_rows(
            (settlement_row(),),
            raw_request_ref_id=uuid4(),
        )


def test_ambiguous_listing_identity_is_never_persisted() -> None:
    session = MagicMock()
    session.scalars.return_value.all.return_value = ["item-a", "item-b"]

    with pytest.raises(
        WfsSettlementPersistenceError,
        match="WFS_SETTLEMENT_IDENTITY_UNRESOLVED",
    ):
        WfsSettlementRepository(session).upsert_rows(
            (settlement_row(),),
            raw_request_ref_id=uuid4(),
        )

    session.execute.assert_not_called()

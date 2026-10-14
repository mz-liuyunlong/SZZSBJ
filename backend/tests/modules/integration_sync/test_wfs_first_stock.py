"""WFS first-stock date safeguards."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.modules.integration_sync.wfs_first_stock import (
    chinese_observed_date,
    listing_identity,
    observe_first_wfs_stock,
    stock_is_available,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE dim_walmart_listings (
                    source_account_ref TEXT,
                    store_id TEXT,
                    item_id TEXT,
                    msku TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE mart_listing_management_current (
                    source_account_ref TEXT,
                    store_id TEXT,
                    item_id TEXT,
                    listing_start_at_utc TEXT,
                    msku TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE listing_wfs_first_stock (
                    id TEXT PRIMARY KEY,
                    source_account_ref TEXT NOT NULL,
                    store_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    msku TEXT NOT NULL,
                    monitoring_started_at_utc TEXT NOT NULL,
                    first_wfs_seen_at_utc TEXT,
                    launch_date_cn TEXT,
                    date_source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(source_account_ref, store_id, item_id, msku)
                )
                """
            )
        )

    with Session(engine) as active_session:
        yield active_session


def moment(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


def observe(
    session: Session,
    qty: str | None,
    when: datetime,
    *,
    msku: str = "MSKU1",
    item: str = "I1",
) -> None:
    observe_first_wfs_stock(
        session,
        source_account_ref="source-1",
        store_id="S1",
        item_id=item,
        msku=msku,
        wfs_quantity=None if qty is None else Decimal(qty),
        observed_at_utc=when,
    )
    session.flush()


def rows(session: Session):
    return session.execute(
        text(
            """
            SELECT msku, launch_date_cn, first_wfs_seen_at_utc, date_source
            FROM listing_wfs_first_stock
            ORDER BY msku
            """
        )
    ).all()


def insert_existing_mart_date(session: Session) -> None:
    session.execute(
        text(
            """
            INSERT INTO mart_listing_management_current (
                source_account_ref,
                store_id,
                item_id,
                listing_start_at_utc,
                msku
            )
            VALUES ('source-1', 'S1', 'I1', '2026-10-12 12:00:00', 'MSKU1')
            """
        )
    )


def insert_dim_listing(session: Session, msku: str) -> None:
    session.execute(
        text(
            """
            INSERT INTO dim_walmart_listings (
                source_account_ref,
                store_id,
                item_id,
                msku
            )
            VALUES ('source-1', 'S1', 'I1', :msku)
            """
        ),
        {"msku": msku},
    )


def test_identity_requires_store_item_and_msku() -> None:
    assert listing_identity(" S1 ", " I1 ", " MSKU1 ") == ("S1", "I1", "MSKU1")
    assert listing_identity("S1", "I1", "") is None
    assert listing_identity("S1", None, "MSKU1") is None


def test_stock_availability_requires_fresh_quantity_at_least_one() -> None:
    assert stock_is_available(Decimal("1"))
    assert stock_is_available(Decimal("2.5"))
    assert not stock_is_available(Decimal("0"))
    assert not stock_is_available(Decimal("-1"))
    assert not stock_is_available(None)


def test_china_calendar_date_uses_observed_instant() -> None:
    assert chinese_observed_date(moment(13, 15, 59)).isoformat() == "2026-10-13"
    assert chinese_observed_date(moment(13, 16, 1)).isoformat() == "2026-10-14"


def test_zero_stock_enrolls_pending_without_launch_date(session: Session) -> None:
    observe(session, "0", moment(13, 1))

    result = rows(session)

    assert len(result) == 1
    assert result[0][1] is None
    assert result[0][2] is None
    assert result[0][3] == "pending"


def test_first_stock_records_china_date_once(session: Session) -> None:
    observe(session, "0", moment(13, 1))
    observe(session, "1", moment(13, 16, 1))

    first = rows(session)[0]
    first_seen = first[2]

    assert str(first[1]) == "2026-10-14"
    assert first[3] == "wfs_first_stock"

    observe(session, "9", moment(15, 10))
    second = rows(session)[0]

    assert str(second[1]) == "2026-10-14"
    assert second[2] == first_seen


def test_existing_dimension_listing_is_not_backfilled(session: Session) -> None:
    insert_dim_listing(session, "MSKU1")

    observe(session, "2", moment(14, 8))

    assert rows(session) == []


def test_existing_mart_date_is_not_backfilled(session: Session) -> None:
    insert_existing_mart_date(session)

    observe(session, "2", moment(13, 10))

    assert rows(session) == []


def test_pending_is_not_finalized_after_mart_verified_date(session: Session) -> None:
    observe(session, "0", moment(13, 1))
    insert_existing_mart_date(session)

    observe(session, "2", moment(14, 4))

    assert rows(session)[0][1] is None
    assert rows(session)[0][3] == "pending"


def test_dimension_msku_reassignment_blocks_new_msku_capture(session: Session) -> None:
    observe(session, "2", moment(13, 8), msku="ORIGINAL")
    insert_dim_listing(session, "ORIGINAL")

    observe(session, "2", moment(14, 8), msku="CHANGED")

    assert len(rows(session)) == 1
    assert rows(session)[0][0] == "ORIGINAL"


def test_pending_old_msku_is_not_finalized_after_dimension_reassigned(
    session: Session,
) -> None:
    observe(session, "0", moment(13, 8), msku="ORIGINAL")
    insert_dim_listing(session, "CHANGED")

    observe(session, "2", moment(14, 8), msku="ORIGINAL")

    assert rows(session)[0][1] is None
    assert rows(session)[0][3] == "pending"

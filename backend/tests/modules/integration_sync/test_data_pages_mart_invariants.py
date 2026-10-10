from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app.modules.integration_sync.data_pages_business_rules_v2 import (
    DAILY_SALES_V2_VERSION,
    _low_price_delivery_surcharge,
)
from app.modules.integration_sync.data_pages_mart_invariants import (
    AutomaticMartDaySnapshot,
    AutomaticMartTableSnapshot,
    DataPagesMartInvariantError,
    profit_gap_summary,
    validate_automatic_mart_replay,
)

DAY = date(2026, 1, 15)


def _daily_row(
    *,
    item_id: str,
    msku: str,
    profit: Decimal | None,
    surcharge: Decimal = Decimal("0"),
) -> dict[str, object]:
    return {
        "business_date_la": DAY,
        "source_account_ref": "synthetic-account",
        "store_id": "synthetic-store",
        "item_id": item_id,
        "msku": msku,
        "local_sku": "synthetic-local-sku",
        "sales_amount": Decimal("12"),
        "sales_qty": Decimal("2"),
        "wfs_low_price_surcharge_amount": surcharge,
        "gross_profit_amount": profit,
        "calc_version": DAILY_SALES_V2_VERSION,
    }


def _order_row(*, profit: Decimal | None, surcharge: Decimal) -> dict[str, object]:
    return {
        "business_date_la": DAY,
        "source_account_ref": "synthetic-account",
        "local_sku": "synthetic-local-sku",
        "wfs_low_price_surcharge_amount": surcharge,
        "gross_profit_amount": profit,
        "calc_version": DAILY_SALES_V2_VERSION,
    }


def _table(
    rows: tuple[dict[str, object], ...],
    *,
    key_hash: str,
    content_hash: str,
) -> AutomaticMartTableSnapshot:
    return AutomaticMartTableSnapshot(
        row_count=len(rows),
        business_key_hash=key_hash,
        stable_content_hash=content_hash,
        calc_versions=((DAILY_SALES_V2_VERSION, len(rows)),) if rows else (),
        surcharge_sum=sum(
            (Decimal(str(row["wfs_low_price_surcharge_amount"])) for row in rows),
            Decimal("0"),
        ),
        profit_sum=sum(
            (
                Decimal(str(row["gross_profit_amount"]))
                for row in rows
                if row["gross_profit_amount"] is not None
            ),
            Decimal("0"),
        ),
        rows=rows,
    )


def _snapshot(
    daily_rows: tuple[dict[str, object], ...],
    order_rows: tuple[dict[str, object], ...],
    *,
    daily_content_hash: str = "daily-stable",
    order_content_hash: str = "order-stable",
) -> AutomaticMartDaySnapshot:
    return AutomaticMartDaySnapshot(
        DAY,
        _table(daily_rows, key_hash="daily-keys", content_hash=daily_content_hash),
        _table(order_rows, key_hash="order-keys", content_hash=order_content_hash),
    )


def test_canonical_mixed_null_gap_uses_actual_non_null_daily_delta() -> None:
    before = _snapshot(
        (
            _daily_row(item_id="synthetic-partial", msku="partial", profit=None),
            _daily_row(item_id="synthetic-complete", msku="complete", profit=Decimal("10")),
        ),
        (_order_row(profit=None, surcharge=Decimal("0")),),
    )
    after = _snapshot(
        (
            _daily_row(item_id="synthetic-partial", msku="partial", profit=None),
            _daily_row(
                item_id="synthetic-complete",
                msku="complete",
                profit=Decimal("8.75"),
            ),
        ),
        (_order_row(profit=None, surcharge=Decimal("0")),),
        daily_content_hash="daily-rebuilt",
    )

    summary = profit_gap_summary(
        before,
        after,
        require_lpds_explanation=False,
        validate=True,
    )

    assert summary.mixed_null_profit_groups == 1
    assert summary.mixed_null_explained_gap_change == Decimal("1.25")
    assert summary.unexplained_profit_gap_change == 0


def test_lpds_only_mixed_null_still_requires_surcharge_only_explanation() -> None:
    before = _snapshot(
        (
            _daily_row(item_id="synthetic-partial", msku="partial", profit=None),
            _daily_row(item_id="synthetic-complete", msku="complete", profit=Decimal("10")),
        ),
        (_order_row(profit=None, surcharge=Decimal("0")),),
    )
    after = _snapshot(
        (
            _daily_row(item_id="synthetic-partial", msku="partial", profit=None),
            _daily_row(
                item_id="synthetic-complete",
                msku="complete",
                profit=Decimal("8.75"),
            ),
        ),
        (_order_row(profit=None, surcharge=Decimal("0")),),
        daily_content_hash="daily-rebuilt",
    )

    with pytest.raises(
        DataPagesMartInvariantError,
        match="DATA_PAGES_MART_PROFIT_INVARIANT_FAILED",
    ):
        profit_gap_summary(
            before,
            after,
            require_lpds_explanation=True,
            validate=True,
        )


def test_automatic_replay_accepts_stable_new_version_rollup() -> None:
    daily = (
        _daily_row(
            item_id="synthetic-item",
            msku="synthetic-msku",
            profit=Decimal("3"),
            surcharge=Decimal("2"),
        ),
    )
    order = (_order_row(profit=Decimal("3"), surcharge=Decimal("2")),)
    snapshot = _snapshot(daily, order)

    summary = validate_automatic_mart_replay(
        snapshot,
        snapshot,
        expected_calc_version=DAILY_SALES_V2_VERSION,
        surcharge_for=_low_price_delivery_surcharge,
    )

    assert summary.comparable_profit_delta_daily == 0
    assert summary.comparable_profit_delta_order == 0
    assert summary.unexplained_profit_gap_change == 0


def test_automatic_replay_accepts_empty_business_day() -> None:
    snapshot = _snapshot((), ())

    summary = validate_automatic_mart_replay(
        snapshot,
        snapshot,
        expected_calc_version=DAILY_SALES_V2_VERSION,
        surcharge_for=_low_price_delivery_surcharge,
    )

    assert summary.comparable_profit_groups == 0
    assert summary.mixed_null_profit_groups == 0
    assert summary.unexplained_profit_gap_change == 0


def test_automatic_replay_rejects_unexplained_profit_change() -> None:
    first = _snapshot(
        (
            _daily_row(
                item_id="synthetic-item",
                msku="synthetic-msku",
                profit=Decimal("3"),
                surcharge=Decimal("2"),
            ),
        ),
        (_order_row(profit=Decimal("3"), surcharge=Decimal("2")),),
    )
    replay = _snapshot(
        (
            _daily_row(
                item_id="synthetic-item",
                msku="synthetic-msku",
                profit=Decimal("2"),
                surcharge=Decimal("2"),
            ),
        ),
        (_order_row(profit=Decimal("3"), surcharge=Decimal("2")),),
        daily_content_hash="daily-drifted",
    )

    with pytest.raises(
        DataPagesMartInvariantError,
        match="DATA_PAGES_MART_PROFIT_INVARIANT_FAILED",
    ):
        validate_automatic_mart_replay(
            first,
            replay,
            expected_calc_version=DAILY_SALES_V2_VERSION,
            surcharge_for=_low_price_delivery_surcharge,
        )


def test_automatic_replay_rejects_non_profit_content_drift() -> None:
    daily = (
        _daily_row(
            item_id="synthetic-item",
            msku="synthetic-msku",
            profit=Decimal("3"),
            surcharge=Decimal("2"),
        ),
    )
    order = (_order_row(profit=Decimal("3"), surcharge=Decimal("2")),)
    first = _snapshot(daily, order)
    replay = _snapshot(daily, order, daily_content_hash="daily-drifted")

    with pytest.raises(
        DataPagesMartInvariantError,
        match="DATA_PAGES_MART_IDEMPOTENCY_FAILED",
    ):
        validate_automatic_mart_replay(
            first,
            replay,
            expected_calc_version=DAILY_SALES_V2_VERSION,
            surcharge_for=_low_price_delivery_surcharge,
        )


def test_automatic_replay_rejects_old_calc_version() -> None:
    daily = (
        _daily_row(
            item_id="synthetic-item",
            msku="synthetic-msku",
            profit=Decimal("3"),
            surcharge=Decimal("2"),
        ),
    )
    order = (_order_row(profit=Decimal("3"), surcharge=Decimal("2")),)
    snapshot = _snapshot(daily, order)
    old_daily = replace(snapshot.daily, calc_versions=(("synthetic-old-version", 1),))
    replay = AutomaticMartDaySnapshot(DAY, old_daily, snapshot.order_profit)

    with pytest.raises(
        DataPagesMartInvariantError,
        match="DATA_PAGES_MART_CALC_VERSION_INVALID",
    ):
        validate_automatic_mart_replay(
            replay,
            replay,
            expected_calc_version=DAILY_SALES_V2_VERSION,
            surcharge_for=_low_price_delivery_surcharge,
        )

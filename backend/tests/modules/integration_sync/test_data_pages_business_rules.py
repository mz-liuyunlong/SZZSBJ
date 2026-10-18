from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy.orm import Session

from app.modules.integration_sync.data_pages_business_rules import (
    CHINA_TZ,
    DataPagesRealSyncRunner,
    _is_valid_sample,
    _refund_amounts,
    _sample_window_china,
)
from app.modules.integration_sync.data_pages_mart_invariants import DataPagesMartInvariantError


class _ScalarResult:
    def scalar_one(self) -> int:
        return 0


class _MappingResult:
    def __init__(self) -> None:
        self._row = None

    def mappings(self) -> "_MappingResult":
        return self

    def first(self) -> None:
        return self._row


class _CaptureSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def execute(self, statement: object, params: dict[str, Any] | None = None) -> _ScalarResult:
        self.calls.append((str(statement), params))
        return _ScalarResult()


class _MatchCaptureSession(_CaptureSession):
    def execute(self, statement: object, params: dict[str, Any] | None = None) -> _MappingResult:
        self.calls.append((str(statement), params))
        return _MappingResult()


def _runner(session: object | None = None) -> DataPagesRealSyncRunner:
    runner = DataPagesRealSyncRunner(
        session=cast(Session, session or object()),
        client=None,
        source_account_ref="primary",
        business_date=date(2026, 9, 1),
        page_size=100,
        campaign_type="SP",
        max_advertisers=10,
    )
    runner.store_ids = ("store-a",)
    return runner


def test_sample_order_window_converts_fixed_utc_minus_7_to_china_time() -> None:
    start_at, end_at = _sample_window_china(date(2026, 9, 1))

    assert start_at.strftime("%Y-%m-%d %H:%M:%S") == "2026-09-01 15:00:00"
    assert end_at.strftime("%Y-%m-%d %H:%M:%S") == "2026-09-02 14:59:59"
    assert start_at.utcoffset() == timedelta(hours=8)
    assert end_at.utcoffset() == timedelta(hours=8)


def test_sample_order_and_generic_order_share_la_business_day_window() -> None:
    runner = _runner()

    sample_body = runner._sample_order_body(offset=0, size=100)
    generic_body = runner._order_body(offset=0, size=100)

    assert (
        datetime.fromtimestamp(sample_body["start_time"], CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        == "2026-09-01 15:00:00"
    )
    assert (
        datetime.fromtimestamp(sample_body["end_time"], CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        == "2026-09-02 14:59:59"
    )
    assert (
        datetime.fromtimestamp(generic_body["start_time"], CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        == "2026-09-01 15:00:00"
    )
    assert (
        datetime.fromtimestamp(generic_body["end_time"], CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        == "2026-09-02 14:59:59"
    )


def test_sample_rule_uses_provider_status_and_normalized_cancel_time() -> None:
    assert _is_valid_sample(Decimal("0"), 0, 9) is True
    assert _is_valid_sample(Decimal("0"), "0", "9") is True
    assert _is_valid_sample(Decimal("0"), None, 9) is True
    assert _is_valid_sample(Decimal("0"), 0.0, "9") is True
    assert _is_valid_sample(Decimal("0"), "0.0", "9") is True
    assert _is_valid_sample(Decimal("0"), 0, 7) is False
    assert _is_valid_sample(Decimal("0"), "2026-09-01 10:00:00", None) is False
    assert _is_valid_sample(Decimal("0"), "2026-09-01 10:00:00", 9) is False
    assert _is_valid_sample(Decimal("1"), None, 9) is False


def test_sample_writer_keeps_required_business_fields() -> None:
    session = _CaptureSession()
    runner = _runner(session)

    written = runner._write_sample_orders(
        [
            {
                "global_order_no": "global-1",
                "global_purchase_time": str(
                    int(datetime(2026, 9, 1, 16, tzinfo=CHINA_TZ).timestamp())
                ),
                "store_id": "store-a",
                "store_name": "Store A",
                "amount_currency": "USD",
                "status": 9,
                "transaction_info": [{"order_total_amount": "0"}],
                "platform_info": [{"platform_code": "10008", "cancel_time": 0}],
                "item_info": [
                    {
                        "id": "line-1",
                        "platform_order_no": "platform-1",
                        "local_sku": "SKU-1",
                        "msku": "MSKU-1",
                        "quantity": "2",
                        "unit_price_amount": "9.99",
                    }
                ],
            }
        ]
    )

    assert written == 1
    params = session.calls[1][1]
    assert params is not None
    assert params["platform_order_no"] == "platform-1"
    assert params["source_order_line_id"] == "line-1"
    assert params["store_name"] == "Store A"
    assert params["local_sku"] == "SKU-1"
    assert params["msku"] == "MSKU-1"
    assert params["quantity"] == Decimal("2")
    assert params["unit_price_amount"] == Decimal("9.99")
    assert params["order_total_amount"] == Decimal("0")
    assert params["platform_code"] == "10008"
    assert params["cancel_time_raw"] == "0"
    assert params["is_cancelled"] is False
    assert params["is_valid_sample"] is False
    assert params["sample_rule_version"] == "candidate-unverified-v5"


def test_sample_item_resolution_requires_unique_listing_and_salestat_agreement() -> None:
    session = _CaptureSession()
    runner = _runner(session)

    unresolved = runner._resolve_sample_items()

    assert unresolved == 0
    assert len(session.calls) == 3

    enrich_sql = session.calls[0][0]
    assert "with listing_candidates as" in enrich_sql
    assert "join dim_walmart_listings l" in enrich_sql
    assert "count(distinct l.item_id) as item_count" in enrich_sql
    assert "join fact_walmart_sales_item_daily f" in enrich_sql
    assert "count(distinct f.item_id) as item_count" in enrich_sql
    assert "l.item_count=1 and f.item_count=1 and l.item_id=f.item_id" in enrich_sql
    assert "set item_id=r.item_id" in enrich_sql

    validate_sql = session.calls[1][0]
    assert "l.store_id=s.store_id and l.item_id=s.item_id" in validate_sql
    assert "f.store_id=s.store_id and f.item_id=s.item_id" in validate_sql
    assert "trim(f.msku)=trim(s.msku)" in validate_sql
    assert "f.allocation_status='direct'" in validate_sql


def test_sample_resolver_enriches_unverified_candidates_without_verifying() -> None:
    session = _CaptureSession()
    runner = _runner(session)
    assert runner._resolve_sample_items() == 0
    assert "and s.item_id is null" in session.calls[0][0]
    assert "and s.is_valid_sample=true and s.item_id is null" not in session.calls[0][0]
    assert "sample_rule_version=:verified_rule" in session.calls[2][0]


def test_confirmed_sample_replay_is_protected_and_changes_block_mart() -> None:
    class ChangedSession(_CaptureSession):
        def execute(
            self, statement: object, params: dict[str, Any] | None = None
        ) -> _ScalarResult:
            statement_text = str(statement)
            self.calls.append((statement_text, params))
            if "select count(*)" in statement_text and "sample_rule_version=:changed_rule" in statement_text:
                class OneResult:
                    def scalar_one(self) -> int:
                        return 1

                return OneResult()  # type: ignore[return-value]
            return _ScalarResult()

    row = {
        "global_order_no": "synthetic-order",
        "reference_no": "synthetic-ref",
        "global_purchase_time": str(
            int(datetime(2026, 9, 1, 16, tzinfo=CHINA_TZ).timestamp())
        ),
        "store_id": "store-a",
        "transaction_info": [{"order_total_amount": "0"}],
        "item_info": [{
            "order_item_no": "line-1",
            "quantity": "1",
            "unit_price_amount": "10.00",
        }],
    }
    session = ChangedSession()
    runner = _runner(session)
    with pytest.raises(DataPagesMartInvariantError, match="DATA_PAGES_VERIFIED_SAMPLE_CHANGED"):
        runner._write_sample_orders([row])
    assert "and not (is_valid_sample=true and sample_rule_version=:verified_rule)" in session.calls[0][0]
    assert "then :changed_rule else excluded.sample_rule_version end" in session.calls[1][0]
    assert "then coalesce(excluded.item_id,fact_walmart_sample_order_items.item_id)" in session.calls[1][0]


def test_sample_empty_items_counted_as_unresolved() -> None:
    session = _CaptureSession()
    runner = _runner(session)
    assert runner._write_sample_orders([{
        "global_purchase_time": str(
            int(datetime(2026, 9, 1, 16, tzinfo=CHINA_TZ).timestamp())
        ),
        "transaction_info": [{"order_total_amount": "0"}],
        "item_info": [],
    }]) == 0
    assert runner.summary.sample_unresolved_rows == 1


def test_refund_quantity_comes_from_return_api_quantity_display() -> None:
    session = _CaptureSession()
    runner = _runner(session)

    written = runner._write_refunds(
        [
            {
                "returnType": "REFUND",
                "returnOrderId": "return-1",
                "storeId": "store-a",
                "customerOrderId": "order-1",
                "items": [
                    {
                        "returnLineId": "return-line-1",
                        "purchaseOrderId": "purchase-1",
                        "itemId": "item-1",
                        "msku": "MSKU-1",
                        "localSku": "SKU-1",
                        "quantityDisplay": "3.5",
                        "lineTotalAmount": "59.50",
                        "lineTotalCurrency": "USD",
                        "currentRefundStatus": "REFUND_COMPLETED",
                    }
                ],
            }
        ]
    )

    assert written == 1
    params = session.calls[1][1]
    assert params is not None
    assert params["quantity"] == Decimal("3.5")

    gross, commission, net = _refund_amounts(
        Decimal("20"),
        params["quantity"],
        Decimal("0.15"),
    )
    assert gross == Decimal("70.0")
    assert commission == Decimal("10.500")
    assert net == Decimal("59.500")


def test_refund_order_match_types_nullable_text_parameters() -> None:
    session = _MatchCaptureSession()
    runner = _runner(session)

    matched = runner._match_refund_order_line(
        {
            "customer_order_id": "order-1",
            "purchase_order_id": None,
            "store_id": None,
            "item_id": None,
            "local_sku": "SKU-1",
            "msku": None,
        }
    )

    assert matched is None
    sql = session.calls[0][0]
    assert "cast(:customer_order_id as text) is not null" in sql
    assert "cast(:purchase_order_id as text) is not null" in sql
    assert "cast(:store_id as text) is null" in sql
    assert "cast(:item_id as text) is not null" in sql
    assert "trim(cast(:local_sku as text))" in sql
    assert "cast(:msku as text) is not null" in sql


def test_daily_sales_mart_is_based_on_salestat_and_joins_sku_cost_sources() -> None:
    session = _CaptureSession()
    runner = _runner(session)

    runner._refresh_daily_sales_mart()

    insert_sql = session.calls[1][0]
    assert "from fact_walmart_sales_item_daily" in insert_sql
    assert "fact_walmart_sample_order_items" in insert_sql
    assert "dws_walmart_refund_business_amounts" in insert_sql
    assert "dwd_lingxing_sku_product_info_current" in insert_sql
    assert "dws_product_management_pricing_current" in insert_sql
    assert "ref_store_commission_rule_versions" in insert_sql
    assert "'basis','fact_walmart_sales_item_daily'" in insert_sql


def test_refund_writer_keeps_event_day_current_on_conflict() -> None:
    session = _CaptureSession()
    runner = _runner(session)

    runner._write_refunds(
        [
            {
                "returnType": "REFUND",
                "returnOrderId": "return-1",
                "storeId": "store-a",
                "items": [
                    {
                        "purchaseOrderId": "purchase-1",
                        "msku": "MSKU-1",
                        "currentRefundStatus": "REFUND_COMPLETED",
                        "quantityDisplay": "1",
                        "lineTotalAmount": "20.00",
                    }
                ],
            }
        ]
    )

    insert_sql = session.calls[1][0]
    assert "business_date_la=excluded.business_date_la" in insert_sql


def test_refund_writer_ignores_non_completed_refunds() -> None:
    session = _CaptureSession()
    runner = _runner(session)

    written = runner._write_refunds(
        [
            {
                "returnType": "REFUND",
                "returnOrderId": "return-1",
                "storeId": "store-a",
                "items": [
                    {
                        "purchaseOrderId": "purchase-1",
                        "msku": "MSKU-1",
                        "currentRefundStatus": "NOT_REFUNDED",
                        "quantityDisplay": "1",
                        "lineTotalAmount": "20.00",
                    }
                ],
            }
        ]
    )

    assert written == 0
    assert len(session.calls) == 1


def test_sample_writer_preserves_full_item_discount_as_unverified_candidate() -> None:
    session = _CaptureSession()
    runner = _runner(session)
    written = runner._write_sample_orders(
        [
            {
                "global_order_no": "global-2",
                "reference_no": "reference-2",
                "global_purchase_time": str(
                    int(datetime(2026, 9, 1, 16, tzinfo=CHINA_TZ).timestamp())
                ),
                "store_id": "store-a",
                "status": 9,
                "transaction_info": [{"order_total_amount": "10.00"}],
                "item_info": [
                    {
                        "order_item_no": "line-2",
                        "msku": "MSKU-1",
                        "item_id": "item-1",
                        "quantity": "2",
                        "item_price_amount": "24.99",
                        "unit_price_amount": "12.495",
                        "discount_amount": "24.99",
                    }
                ],
            }
        ]
    )
    assert written == 1
    params = session.calls[1][1]
    assert params is not None
    assert params["platform_order_no"] == "reference-2"
    assert params["source_order_line_id"] == "line-2"
    assert params["unit_price_amount"] == Decimal("12.495")
    assert params["is_valid_sample"] is False


def test_sample_writer_quarantines_missing_order_line_identity() -> None:
    session = _CaptureSession()
    runner = _runner(session)
    row = {
        "global_order_no": "global-3",
        "reference_no": "reference-3",
        "global_purchase_time": str(int(datetime(2026, 9, 1, 16, tzinfo=CHINA_TZ).timestamp())),
        "store_id": "store-a",
        "status": 9,
        "transaction_info": [{"order_total_amount": "0"}],
        "item_info": [{"msku": "MSKU-1", "quantity": 1, "item_price_amount": "24.99"}],
    }
    assert runner._write_sample_orders([row]) == 0
    assert runner.summary.sample_unresolved_rows == 1


def test_sample_order_window_handles_dst_switch() -> None:
    winter_start, winter_end = _sample_window_china(date(2026, 12, 1))
    assert winter_start.strftime("%Y-%m-%d %H:%M:%S") == "2026-12-01 16:00:00"
    assert winter_end.strftime("%Y-%m-%d %H:%M:%S") == "2026-12-02 15:59:59"
    runner = _runner()
    runner.business_date = date(2026, 12, 1)
    assert runner._order_body(0, 20)["start_time"] == runner._sample_order_body(0, 20)["start_time"]


def test_sample_writer_quarantines_ambiguous_multiple_unit_prices() -> None:
    row = {
        "global_order_no": "global-multi",
        "reference_no": "reference-multi",
        "global_purchase_time": str(int(datetime(2026, 9, 1, 16, tzinfo=CHINA_TZ).timestamp())),
        "store_id": "store-a",
        "status": 9,
        "transaction_info": [{"order_total_amount": "0"}],
        "item_info": [
            {
                "order_item_no": "line-multi",
                "quantity": "2",
                "item_price_amount": "24.99",
                "discount_amount": "24.99",
            }
        ],
    }
    session = _CaptureSession()
    runner = _runner(session)
    assert runner._write_sample_orders([row]) == 1
    assert runner.summary.sample_unresolved_rows == 1
    assert session.calls[1][1]["unit_price_amount"] is None
    assert session.calls[1][1]["is_valid_sample"] is False

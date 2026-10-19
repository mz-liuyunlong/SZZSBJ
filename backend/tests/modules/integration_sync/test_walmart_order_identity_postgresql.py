from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import Settings, SettingsError, get_test_database_url
from app.modules.integration_sync.data_pages_business_rules import (
    HISTORICAL_VERIFIED_SAMPLE_RULE_VERSION,
)
from app.modules.integration_sync.data_pages_business_rules_v2 import DataPagesRealSyncRunner
from app.modules.integration_sync.data_pages_mart_invariants import DataPagesMartInvariantError

_DATABASE = "walmart_order_identity_test"
_USERNAME = "walmart_order_identity_test"
_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_ACCOUNT = "synthetic-order-identity"


def _validate_url(url: URL) -> URL:
    if (
        url.host not in _HOSTS
        or url.database != _DATABASE
        or url.username != _USERNAME
        or url.query
    ):
        raise SettingsError("Walmart order identity tests require the dedicated local database")
    return url


def _database_url() -> URL:
    if os.environ.get("WALMART_ORDER_IDENTITY_DB_TESTS") != "1":
        pytest.skip("real Walmart order identity PostgreSQL test requires explicit opt-in")
    try:
        return _validate_url(get_test_database_url(Settings()))
    except (SettingsError, ValidationError) as exc:
        pytest.fail(str(exc), pytrace=False)


@pytest.fixture  # type: ignore[untyped-decorator]
def engine() -> Iterator[Engine]:
    database_url = _database_url()
    engine = create_engine(database_url, poolclass=NullPool, hide_parameters=True)
    with engine.connect() as connection:
        identity = connection.execute(text("select current_database(),current_user")).one()
    assert identity == (_DATABASE, _USERNAME)
    with engine.begin() as connection:
        connection.execute(
            text("delete from mart_daily_sales_item_day where source_account_ref=:account"),
            {"account": _ACCOUNT},
        )
        connection.execute(
            text("delete from fact_walmart_sample_order_items where source_account_ref=:account"),
            {"account": _ACCOUNT},
        )
        connection.execute(
            text(
                "delete from audit_walmart_order_item_conflicts where source_account_ref=:account"
            ),
            {"account": _ACCOUNT},
        )
        connection.execute(
            text("delete from fact_walmart_order_items where source_account_ref=:account"),
            {"account": _ACCOUNT},
        )
        connection.execute(
            text("delete from fact_walmart_sales_item_daily where source_account_ref=:account"),
            {"account": _ACCOUNT},
        )
        connection.execute(
            text("delete from dim_walmart_listings where source_account_ref=:account"),
            {"account": _ACCOUNT},
        )
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("delete from mart_daily_sales_item_day where source_account_ref=:account"),
                {"account": _ACCOUNT},
            )
            connection.execute(
                text(
                    "delete from fact_walmart_sample_order_items where source_account_ref=:account"
                ),
                {"account": _ACCOUNT},
            )
            connection.execute(
                text(
                    "delete from audit_walmart_order_item_conflicts "
                    "where source_account_ref=:account"
                ),
                {"account": _ACCOUNT},
            )
            connection.execute(
                text("delete from fact_walmart_order_items where source_account_ref=:account"),
                {"account": _ACCOUNT},
            )
            connection.execute(
                text("delete from fact_walmart_sales_item_daily where source_account_ref=:account"),
                {"account": _ACCOUNT},
            )
            connection.execute(
                text("delete from dim_walmart_listings where source_account_ref=:account"),
                {"account": _ACCOUNT},
            )
        engine.dispose()


def _legacy_hash(line_id: str, version: int) -> str:
    return hashlib.sha256(f"{line_id}:{version}".encode()).hexdigest()


def _provider_row(*, store_id: str = "store-a", changed: bool = False) -> dict[str, object]:
    purchase_at = int(datetime(2026, 10, 16, 12, tzinfo=UTC).timestamp())
    return {
        "global_order_no": "order-a",
        "global_purchase_time": str(purchase_at),
        "store_id": store_id,
        "status": "cancelled" if changed else "created",
        "amount_currency": "USD",
        "transaction_info": [{"order_total_amount": "0"}],
        "item_info": [
            {
                "order_item_no": f"line-{index}",
                "item_id": f"item-{index}",
                "msku": f"msku-{index}",
                "local_sku": f"sku-{index}",
                "quantity": "2" if changed and index == 0 else "1",
                "sales_revenue_amount": "0",
                "discount_amount": "0",
            }
            for index in range(5)
        ],
    }


def test_order_identity_converges_12_legacy_versions_to_5_current_rows(engine: Engine) -> None:
    version_counts = (4, 3, 2, 2, 1)
    now = datetime.now(UTC)
    with Session(engine) as session:
        for line_index, versions in enumerate(version_counts):
            for version in range(versions):
                session.execute(
                    text(
                        "insert into fact_walmart_order_items "
                        "(id,source_account_ref,store_id,source_order_id,source_order_line_id,"
                        "source_line_hash,source_line_ordinal,item_id,msku,local_sku,quantity,"
                        "business_date_la,order_status_raw,sales_revenue_amount,"
                        "sales_revenue_currency_code,order_total_amount,order_total_currency_code,"
                        "discount_amount,discount_currency_code,is_sample_order,is_identity_current,"
                        "synced_at,created_at,updated_at) values "
                        "(:id,:account,'store-a','order-a',:line_id,:line_hash,:ordinal,:item_id,"
                        ":msku,:local_sku,:quantity,:day,'created',0,'USD',0,'USD',0,'USD',"
                        "false,false,:now,:now,:now)"
                    ),
                    {
                        "id": str(uuid4()),
                        "account": _ACCOUNT,
                        "line_id": f"line-{line_index}",
                        "line_hash": _legacy_hash(f"line-{line_index}", version),
                        "ordinal": line_index,
                        "item_id": f"item-{line_index}",
                        "msku": f"msku-{line_index}",
                        "local_sku": f"sku-{line_index}",
                        "quantity": version + 1 if line_index == 0 else 1,
                        "day": date(2026, 10, 16),
                        "now": now,
                    },
                )
        session.commit()

        runner = DataPagesRealSyncRunner(
            session=session,
            client=None,
            source_account_ref=_ACCOUNT,
            business_date=date(2026, 10, 16),
            page_size=20,
            campaign_type="SP",
            max_advertisers=1,
        )
        assert (
            runner._match_refund_order_line(
                {
                    "customer_order_id": "order-a",
                    "store_id": "store-a",
                    "item_id": "item-0",
                    "msku": "msku-0",
                }
            )
            is None
        )
        legacy_single = runner._match_refund_order_line(
            {
                "customer_order_id": "order-a",
                "store_id": "store-a",
                "item_id": "item-4",
                "msku": "msku-4",
            }
        )
        assert legacy_single is not None
        assert legacy_single["source_order_line_id"] == "line-4"

        assert runner._write_orders([_provider_row()]) == 5
        session.commit()

        adopted = runner._match_refund_order_line(
            {
                "customer_order_id": "order-a",
                "store_id": "store-a",
                "item_id": "item-0",
                "msku": "msku-0",
            }
        )
        assert adopted is not None
        assert adopted["source_order_line_id"] == "line-0"

        counts = session.execute(
            text(
                "select count(*),count(*) filter (where is_identity_current=true),"
                "count(distinct canonical_identity_hash) filter "
                "(where is_identity_current=true) from fact_walmart_order_items "
                "where source_account_ref=:account"
            ),
            {"account": _ACCOUNT},
        ).one()
        assert counts == (12, 5, 5)

        first_audit_count = session.scalar(
            text(
                "select count(*) from audit_walmart_order_item_conflicts "
                "where source_account_ref=:account"
            ),
            {"account": _ACCOUNT},
        )
        assert first_audit_count and first_audit_count > 0

        assert runner._write_orders([_provider_row(changed=True)]) == 5
        assert runner._write_orders([_provider_row(changed=True)]) == 5
        session.commit()

        assert (
            session.scalar(
                text(
                    "select count(*) from fact_walmart_order_items "
                    "where source_account_ref=:account"
                ),
                {"account": _ACCOUNT},
            )
            == 12
        )
        assert (
            session.scalar(
                text(
                    "select count(*) from fact_walmart_order_items "
                    "where source_account_ref=:account and is_identity_current=true"
                ),
                {"account": _ACCOUNT},
            )
            == 5
        )
        assert (
            session.scalar(
                text(
                    "select count(*) from audit_walmart_order_item_conflicts "
                    "where source_account_ref=:account and differing_fields_json ? 'quantity'"
                ),
                {"account": _ACCOUNT},
            )
            >= 1
        )

        same_order_line_other_store = _provider_row(store_id="store-b")
        items = cast(list[dict[str, object]], same_order_line_other_store["item_info"])
        same_order_line_other_store["item_info"] = [items[0]]
        assert runner._write_orders([same_order_line_other_store]) == 1
        session.commit()
        assert (
            session.scalar(
                text(
                    "select count(*) from fact_walmart_order_items "
                    "where source_account_ref=:account "
                    "and source_order_id='order-a' and source_order_line_id='line-0' "
                    "and is_identity_current=true"
                ),
                {"account": _ACCOUNT},
            )
            == 2
        )


def test_historical_v3_sample_survives_replay_and_conflict_rollback(engine: Engine) -> None:
    now = datetime.now(UTC)
    purchase_at = str(int(datetime(2026, 10, 16, 12, tzinfo=UTC).timestamp()))
    provider_row: dict[str, object] = {
        "global_order_no": "sample-order-a",
        "global_purchase_time": purchase_at,
        "store_id": "store-a",
        "status": "created",
        "amount_currency": "USD",
        "transaction_info": [{"order_total_amount": "0"}],
        "item_info": [
            {
                "order_item_no": "sample-line-a",
                "platform_order_no": "sample-platform-order-a",
                "item_id": "item-a",
                "msku": "msku-a",
                "local_sku": "sku-a",
                "quantity": "1",
                "unit_price_amount": "0",
            }
        ],
    }
    with Session(engine) as session:
        session.execute(
            text(
                "insert into dim_walmart_listings "
                "(id,source_account_ref,platform_code,store_id,item_id,msku,local_sku,"
                "synced_at,created_at,updated_at) values "
                "(:id,:account,'walmart','store-a','item-a','msku-a','sku-a',"
                ":now,:now,:now)"
            ),
            {"id": str(uuid4()), "account": _ACCOUNT, "now": now},
        )
        session.execute(
            text(
                "insert into fact_walmart_sales_item_daily "
                "(id,business_date_la,source_account_ref,platform_code,store_id,item_id,"
                "msku,local_sku,sales_qty,order_count,sales_amount,sales_currency_code,"
                "allocation_status,synced_at,created_at,updated_at) values "
                "(:id,:day,:account,'walmart','store-a','item-a','msku-a','sku-a',"
                "9,9,90,'USD','direct',:now,:now,:now)"
            ),
            {
                "id": str(uuid4()),
                "day": date(2026, 10, 16),
                "account": _ACCOUNT,
                "now": now,
            },
        )
        session.execute(
            text(
                "insert into fact_walmart_sample_order_items "
                "(id,business_date_utc_minus_7,business_timezone,source_account_ref,"
                "source_order_id,platform_order_no,store_id,platform_code,source_order_line_id,"
                "item_id,msku,local_sku,quantity,unit_price_amount,unit_price_currency_code,"
                "order_total_amount,"
                "order_total_currency_code,is_cancelled,is_valid_sample,sample_rule_version,"
                "synced_at,created_at,updated_at) values "
                "(:id,:day,'America/Los_Angeles',:account,'sample-order-a',"
                "'sample-platform-order-a','store-a','walmart','sample-line-a','item-a',"
                "'msku-a','sku-a',1,0,'USD',0,'USD',false,true,:rule,:now,:now,:now)"
            ),
            {
                "id": str(uuid4()),
                "day": date(2026, 10, 16),
                "account": _ACCOUNT,
                "rule": HISTORICAL_VERIFIED_SAMPLE_RULE_VERSION,
                "now": now,
            },
        )
        session.commit()
        runner = DataPagesRealSyncRunner(
            session=session,
            client=None,
            source_account_ref=_ACCOUNT,
            business_date=date(2026, 10, 16),
            page_size=20,
            campaign_type="SP",
            max_advertisers=1,
        )

        assert runner._write_sample_orders([provider_row]) == 1
        session.commit()
        preserved = session.execute(
            text(
                "select is_valid_sample,sample_rule_version "
                "from fact_walmart_sample_order_items where source_account_ref=:account"
            ),
            {"account": _ACCOUNT},
        ).one()
        assert preserved == (True, HISTORICAL_VERIFIED_SAMPLE_RULE_VERSION)

        assert runner._refresh_daily_sales_mart() == 1
        session.commit()
        mart_before = session.execute(
            text(
                "select gross_sales_qty,sample_order_count,sample_qty,sales_qty "
                "from mart_daily_sales_item_day where source_account_ref=:account "
                "and business_date_la=:day and store_id='store-a' and item_id='item-a'"
            ),
            {"account": _ACCOUNT, "day": date(2026, 10, 16)},
        ).one()
        assert mart_before == (9, 1, 1, 8)

        changed = dict(provider_row)
        changed["item_info"] = [
            {
                **cast(list[dict[str, object]], provider_row["item_info"])[0],
                "quantity": "2",
            }
        ]
        with pytest.raises(
            DataPagesMartInvariantError,
            match="DATA_PAGES_VERIFIED_SAMPLE_CHANGED",
        ):
            runner._write_sample_orders([changed])
        session.rollback()
        preserved_after_conflict = session.execute(
            text(
                "select is_valid_sample,sample_rule_version "
                "from fact_walmart_sample_order_items where source_account_ref=:account"
            ),
            {"account": _ACCOUNT},
        ).one()
        assert preserved_after_conflict == (True, HISTORICAL_VERIFIED_SAMPLE_RULE_VERSION)
        mart_after_conflict = session.execute(
            text(
                "select sample_order_count,sample_qty,sales_qty "
                "from mart_daily_sales_item_day where source_account_ref=:account "
                "and business_date_la=:day and store_id='store-a' and item_id='item-a'"
            ),
            {"account": _ACCOUNT, "day": date(2026, 10, 16)},
        ).one()
        assert mart_after_conflict == (1, 1, 8)


def test_isolated_database_guard_rejects_application_database() -> None:
    unsafe = make_url("postgresql+psycopg://application@127.0.0.1/szzsbj_app")
    with pytest.raises(SettingsError, match="dedicated local database"):
        _validate_url(unsafe)

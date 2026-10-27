"""Anomaly center scopes, identity and evidence tests (synthetic, no production I/O)."""

from datetime import date
from unittest.mock import MagicMock
from uuid import uuid4

from app.modules.integration_sync.repository import IntegrationSyncRepository


def test_anomaly_upsert_is_stable_for_same_date_and_scope() -> None:
    session = MagicMock()
    repo = IntegrationSyncRepository(session)
    run_id = uuid4()
    repo.record_business_anomaly(
        run_id=run_id,
        account="synthetic-account",
        interface_key="walmartAdItemSpList",
        business_date=date(2026, 10, 25),
        error_code="DATA_PAGES_SEM_SPEND_UNATTRIBUTED",
    )

    sql, values = session.execute.call_args.args
    statement = str(sql).lower()
    assert "on conflict on constraint uq_gov_sync_anomaly_identity" in statement
    assert "source_account_ref" in statement
    assert values["account"] == "synthetic-account"
    assert values["interface_key"] == "walmartAdItemSpList"
    assert values["subject_key"] == "date-scope"
    assert values["run_id"] == run_id
    assert values["store_id"] is None
    assert values["item_id"] is None
    assert values["platform_order_no"] is None


def test_anomaly_preserves_actual_source_identifiers_only() -> None:
    session = MagicMock()
    repo = IntegrationSyncRepository(session)
    repo.record_business_anomaly(
        run_id=uuid4(),
        account="synthetic-account",
        interface_key="saleStatPageList",
        business_date=date(2026, 8, 11),
        error_code="DATA_PAGES_CONFIRMED_SAMPLE_EXCEEDS_SALESTAT",
        subject_key="synthetic-identity",
        store_id="synthetic-store",
        item_id="synthetic-item",
        msku="synthetic-msku",
        platform_order_no="synthetic-order",
    )
    values = session.execute.call_args.args[1]
    assert values["subject_key"] == "synthetic-identity"
    assert values["store_id"] == "synthetic-store"
    assert values["item_id"] == "synthetic-item"
    assert values["msku"] == "synthetic-msku"
    assert values["platform_order_no"] == "synthetic-order"


def test_sample_evidence_capture_does_not_modify_financial_facts() -> None:
    session = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value = []
    repo = IntegrationSyncRepository(session)
    count = repo.record_sample_exceedance_details(
        run_id=uuid4(),
        account="synthetic-account",
        interface_key="saleStatPageList",
        business_date=date(2026, 8, 11),
    )
    assert count == 0
    sql = str(session.execute.call_args.args[0]).lower()
    assert sql.lstrip().startswith("with gross as")
    assert "source_account_ref=:account" in sql
    assert "business_date_utc_minus_7=:day" in sql
    assert "limit 200" in sql

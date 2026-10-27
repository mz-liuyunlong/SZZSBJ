from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.warehouse_wfs.automation_service import (
    WfsStoreDetectionPreview,
    detect_store_from_persisted_evidence,
    preview_persisted_wfs_detection,
)
from app.modules.warehouse_wfs.fee_detection import ResolvedWfsFee
from app.modules.warehouse_wfs.store_discovery import WfsSettlementStore


def test_batch_preview_scans_each_store_without_enabling_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, bool]] = []

    def stores(
        _session: Session,
        *,
        source_account_ref: str,
    ) -> tuple[WfsSettlementStore, ...]:
        return (
            WfsSettlementStore(source_account_ref, "store-a", "A", "sid-a"),
            WfsSettlementStore(source_account_ref, "store-b", "B", "sid-b"),
        )

    def detect(
        _session: Session,
        *,
        source_account_ref: str,
        store_id: str,
        execute_cases: bool,
        **_kwargs: object,
    ) -> WfsStoreDetectionPreview:
        calls.append((source_account_ref, store_id, execute_cases))
        return WfsStoreDetectionPreview(
            source_account_ref=source_account_ref,
            store_id=store_id,
            scanned_skus=3,
            valid_samples=2,
            overcharge_candidates=1,
            would_create=1,
            already_exists=0,
            review_required=0,
            skipped=2,
        )

    monkeypatch.setattr(
        "app.modules.warehouse_wfs.automation_service.discover_walmart_stores",
        stores,
    )
    monkeypatch.setattr(
        "app.modules.warehouse_wfs.automation_service.detect_store_from_persisted_evidence",
        detect,
    )

    session = MagicMock(spec=Session)
    result = preview_persisted_wfs_detection(
        session,
        settings=Settings.model_validate(
            {
                "APP_ENV": "test",
                "TEST_DATABASE_URL": "postgresql+psycopg://synthetic@db.invalid/synthetic",
            }
        ),
        source_account_refs=frozenset({"account-a", "account-b"}),
        start_date=date(2026, 8, 19),
        end_date=date(2026, 10, 17),
    )

    assert result.scanned_accounts == 2
    assert result.scanned_stores == 4
    assert result.scanned_skus == 12
    assert result.valid_samples == 8
    assert result.would_create == 4
    assert all(execute_cases is False for _, _, execute_cases in calls)


def test_manual_detection_rejects_unverified_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    repository = MagicMock()
    repository.get_verified_collection.return_value = None
    monkeypatch.setattr(
        "app.modules.warehouse_wfs.automation_service.WfsSettlementRepository",
        lambda _session: repository,
    )

    with pytest.raises(ValueError, match="WFS_COLLECTION_NOT_VERIFIED"):
        detect_store_from_persisted_evidence(
            session,
            settings=Settings.model_validate(
                {
                    "APP_ENV": "test",
                    "TEST_DATABASE_URL": ("postgresql+psycopg://synthetic@db.invalid/synthetic"),
                }
            ),
            source_account_ref="account-a",
            store_id="store-a",
            start_date=date(2026, 8, 19),
            end_date=date(2026, 10, 17),
        )

    repository.list_rows.assert_not_called()
    repository.get_verified_collection.assert_called_once_with(
        source_account_ref="account-a",
        store_id="store-a",
        start_date=date(2026, 8, 19),
        end_date=date(2026, 10, 17),
    )


def test_backtest_cannot_write_cases_or_evidence() -> None:
    with pytest.raises(ValueError, match="WFS_BACKTEST_WRITE_FORBIDDEN"):
        detect_store_from_persisted_evidence(
            MagicMock(spec=Session),
            settings=Settings.model_validate(
                {"APP_ENV": "test", "TEST_DATABASE_URL": "postgresql+psycopg://x@invalid/x"}
            ),
            source_account_ref="account-a",
            store_id="store-a",
            start_date=date(2026, 8, 19),
            end_date=date(2026, 10, 17),
            execute_cases=True,
            backtest=True,
            business_as_of_date=date(2026, 9, 1),
        )


def test_live_detection_uses_execution_date_and_requires_sales_through_window_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = MagicMock()
    repository.get_verified_collection.return_value = SimpleNamespace(id="collection-a")
    repository.list_rows.return_value = ()
    monkeypatch.setattr(
        "app.modules.warehouse_wfs.automation_service.WfsSettlementRepository",
        lambda _session: repository,
    )
    monkeypatch.setattr(
        "app.modules.warehouse_wfs.automation_service.resolve_wfs_fees",
        lambda *_args, **_kwargs: [
            ResolvedWfsFee(
                source_account_ref="account-a",
                store_id="store-a",
                msku="SKU-A",
                unit_fee=Decimal("6.95"),
                sample_units=Decimal("10"),
                fee_orders=2,
                mode_count=2,
                skipped_no_qty=0,
                latest_settlement_date=date(2026, 10, 16),
                fee_scope_status="verified_wfs",
            )
        ],
    )
    session = MagicMock(spec=Session)
    session.execute.return_value.all.return_value = [("SKU-A", "item-a")]
    monkeypatch.setattr(
        "app.modules.warehouse_wfs.automation_service.read_product_management_wfs_fees",
        lambda *_args, **_kwargs: {("account-a", "store-a", "item-a", "SKU-A"): SimpleNamespace()},
    )
    sales_reader = MagicMock(
        return_value={("account-a", "store-a", "item-a", "SKU-A"): SimpleNamespace()}
    )
    monkeypatch.setattr(
        "app.modules.warehouse_wfs.automation_service.read_walmart_lifetime_sales_batch",
        sales_reader,
    )
    detector = MagicMock(return_value=SimpleNamespace(candidates=()))
    monkeypatch.setattr(
        "app.modules.warehouse_wfs.automation_service.detect_wfs_anomalies",
        detector,
    )
    executed_at = datetime(2026, 10, 26, 12, tzinfo=UTC)

    detect_store_from_persisted_evidence(
        session,
        settings=Settings.model_validate(
            {"APP_ENV": "test", "TEST_DATABASE_URL": "postgresql+psycopg://x@invalid/x"}
        ),
        source_account_ref="account-a",
        store_id="store-a",
        start_date=date(2026, 8, 19),
        end_date=date(2026, 10, 17),
        detection_executed_at=executed_at,
    )

    assert detector.call_args.kwargs["as_of"] == date(2026, 10, 26)
    assert sales_reader.call_args.kwargs["required_coverage_end"] == date(2026, 10, 17)
    assert sales_reader.call_args.kwargs["identities"] == frozenset(
        {("account-a", "store-a", "item-a", "SKU-A")}
    )

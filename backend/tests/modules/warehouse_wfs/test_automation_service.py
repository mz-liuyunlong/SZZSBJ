from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.warehouse_wfs.automation_service import (
    WfsStoreDetectionPreview,
    detect_store_from_persisted_evidence,
    preview_persisted_wfs_detection,
)
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
    repository.has_completed_collection.return_value = False
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
    repository.has_completed_collection.assert_called_once_with(
        source_account_ref="account-a",
        store_id="store-a",
        start_date=date(2026, 8, 19),
        end_date=date(2026, 10, 17),
    )

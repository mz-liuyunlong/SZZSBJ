from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.data_pages.models import ListingArchiveState
from app.modules.data_pages.repository import ListingManagementRepository


def _listing() -> SimpleNamespace:
    return SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        source_account_ref="synthetic-account",
        store_id="synthetic-store",
        item_id="synthetic-item",
        msku="synthetic-msku",
    )


def test_repeated_archive_keeps_original_audit_fields() -> None:
    original_time = datetime(2026, 1, 15, tzinfo=UTC)
    state = ListingArchiveState(
        listing_id=_listing().id,
        source_account_ref="synthetic-account",
        store_id="synthetic-store",
        item_id="synthetic-item",
        msku="synthetic-msku",
        is_archived=True,
        archive_reason="synthetic reason",
        archived_at=original_time,
        archived_by="original-actor",
        updated_at=original_time,
    )
    session = MagicMock(spec=Session)
    session.scalar.return_value = state

    result = ListingManagementRepository(session).set_listing_archive_state(
        listing=_listing(),
        archived=True,
        actor_ref="retry-actor",
        archive_reason="synthetic reason",
    )

    assert result is state
    assert state.archived_at == original_time
    assert state.archived_by == "original-actor"
    assert state.updated_at == original_time
    session.commit.assert_not_called()


def test_repeated_restore_keeps_original_audit_fields() -> None:
    original_time = datetime(2026, 1, 15, tzinfo=UTC)
    state = ListingArchiveState(
        listing_id=_listing().id,
        source_account_ref="synthetic-account",
        store_id="synthetic-store",
        item_id="synthetic-item",
        msku="synthetic-msku",
        is_archived=False,
        archive_reason=None,
        restored_at=original_time,
        restored_by="original-actor",
        updated_at=original_time,
    )
    session = MagicMock(spec=Session)
    session.scalar.return_value = state

    result = ListingManagementRepository(session).set_listing_archive_state(
        listing=_listing(), archived=False, actor_ref="retry-actor"
    )

    assert result is state
    assert state.restored_at == original_time
    assert state.restored_by == "original-actor"
    assert state.updated_at == original_time
    session.commit.assert_not_called()


def test_archive_with_changed_reason_is_a_new_write() -> None:
    state = ListingArchiveState(
        listing_id=_listing().id,
        source_account_ref="synthetic-account",
        store_id="synthetic-store",
        item_id="synthetic-item",
        msku="synthetic-msku",
        is_archived=True,
        archive_reason="old synthetic reason",
    )
    session = MagicMock(spec=Session)
    session.scalar.return_value = state

    ListingManagementRepository(session).set_listing_archive_state(
        listing=_listing(),
        archived=True,
        actor_ref="new-actor",
        archive_reason="new synthetic reason",
    )

    assert state.archive_reason == "new synthetic reason"
    assert state.archived_by == "new-actor"
    session.commit.assert_called_once()

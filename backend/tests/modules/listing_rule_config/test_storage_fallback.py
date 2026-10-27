"""Missing rule table falls back to read-only defaults, not silent writes."""

from unittest.mock import Mock

import pytest
from sqlalchemy.exc import OperationalError

from app.core.api import ApiError
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig, ListingGradeRuleUpdate
from app.modules.listing_rule_config.service import ListingGradeRuleService


class PgUndefinedTable(Exception):
    sqlstate = "42P01"


class PgConnectionFailure(Exception):
    sqlstate = "08006"


def db_error(original: Exception) -> OperationalError:
    return OperationalError("SELECT rule versions", (), original)


def test_missing_table_returns_read_only_defaults() -> None:
    session = Mock()
    service = ListingGradeRuleService(session)
    service.repo.latest = Mock(side_effect=db_error(PgUndefinedTable()))
    result = service.get(can_edit=True)
    assert result.version == 0
    assert result.config == ListingGradeRuleConfig()
    assert result.storage_ready is False
    assert result.can_edit is False
    session.rollback.assert_called_once()


def test_missing_table_history_empty_and_not_ready() -> None:
    session = Mock()
    service = ListingGradeRuleService(session)
    service.repo.history = Mock(side_effect=db_error(PgUndefinedTable()))
    result = service.history(limit=20, offset=0)
    assert result.total == 0 and result.storage_ready is False
    session.rollback.assert_called_once()


def test_connection_failures_are_not_swallowed() -> None:
    session = Mock()
    service = ListingGradeRuleService(session)
    service.repo.latest = Mock(side_effect=db_error(PgConnectionFailure()))
    with pytest.raises(OperationalError):
        service.get(can_edit=True)


def test_missing_table_save_reports_503() -> None:
    session = Mock()
    service = ListingGradeRuleService(session)
    service.repo.lock_for_version_change = Mock()
    service.repo.latest = Mock(side_effect=db_error(PgUndefinedTable()))
    payload = ListingGradeRuleUpdate(
        expected_version=0,
        change_reason="test reason",
        config=ListingGradeRuleConfig(),
    )
    with pytest.raises(ApiError) as e:
        service.update(request=payload, actor="test")
    assert e.value.status_code == 503
    assert e.value.code == "LISTING_RULE_STORAGE_NOT_READY"
    session.rollback.assert_called_once()

"""Isolated service tests using a fake repository; never touch production."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.api import ApiError
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig, ListingGradeRuleUpdate
from app.modules.listing_rule_config.service import ListingGradeRuleService


class FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class FakeRepo:
    def __init__(self) -> None:
        self.rows: list[object] = []
        self.locked = False

    def lock_for_version_change(self) -> None:
        self.locked = True

    def latest(self):
        return self.rows[-1] if self.rows else None

    def append(self, row) -> None:
        self.rows.append(row)

    def history(self, *, limit: int, offset: int):
        return list(reversed(self.rows))[offset : offset + limit], len(self.rows)


def test_write_creates_version_and_rejects_stale_expected_version() -> None:
    session = FakeSession()
    service = ListingGradeRuleService(session)  # type: ignore[arg-type]
    repo = FakeRepo()
    service.repo = repo  # type: ignore[assignment]
    config = ListingGradeRuleConfig(short_days=6, short_min_valid_days=4)
    payload = ListingGradeRuleUpdate(
        expected_version=0, change_reason="缩短短期窗口", config=config
    )
    result = service.update(request=payload, actor="operator-1")
    assert repo.locked
    assert result.version == 1 and result.source == "database"
    assert session.committed
    assert result.effective_from is not None
    assert result.effective_from > datetime.now(UTC)
    assert result.effective_from <= datetime.now(UTC) + timedelta(days=1)
    with pytest.raises(ApiError) as error:
        service.update(request=payload, actor="operator-2")
    assert error.value.status_code == 409
    assert session.rolled_back


def test_no_change_does_not_create_duplicate_version() -> None:
    service = ListingGradeRuleService(FakeSession())  # type: ignore[arg-type]
    repo = FakeRepo()
    service.repo = repo  # type: ignore[assignment]
    payload = ListingGradeRuleUpdate(
        expected_version=0,
        change_reason="调整参数测试",
        config=ListingGradeRuleConfig(short_weight_percent=55, medium_weight_percent=45),
    )
    service.update(request=payload, actor="operator")
    with pytest.raises(ApiError) as error:
        service.update(
            request=ListingGradeRuleUpdate(
                expected_version=1,
                change_reason="重复保存测试",
                config=payload.config,
            ),
            actor="operator",
        )
    assert error.value.code == "LISTING_RULE_NO_CHANGES"
    assert len(repo.rows) == 1

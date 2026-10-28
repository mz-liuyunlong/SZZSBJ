"""Global Listing grade rule validation, scheduling and audit service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.modules.listing_rule_config.models import ListingGradeRuleVersion
from app.modules.listing_rule_config.repository import ListingGradeRuleRepository
from app.modules.listing_rule_config.schemas import (
    ListingGradeRuleConfig,
    ListingGradeRuleHistoryData,
    ListingGradeRuleHistoryItem,
    ListingGradeRuleRead,
    ListingGradeRuleUpdate,
)

CHINA_TZ = ZoneInfo("Asia/Shanghai")


def _rule_table_missing(error: DBAPIError) -> bool:
    """Only an undefined PostgreSQL relation can mean uninitialized storage.

    Never mistake network, permission or SQL errors for valid zero/default data.
    The caller only applies this to queries on the versioned Listing rule table.
    """
    orig = error.orig
    return getattr(orig, "sqlstate", getattr(orig, "pgcode", None)) == "42P01"


def next_rating_time_utc(now: datetime, execution_time: str = "22:30") -> datetime:
    """Next China-time boundary for the configured HH:mm (default 22:30).

    The function calculates a future configuration effective time; it does not
    enqueue or execute Listing evaluation tasks.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    hour, minute = map(int, execution_time.split(":"))
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("execution_time must be HH:mm in the 24-hour clock")
    local = now.astimezone(CHINA_TZ)
    scheduled = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if local >= scheduled:
        scheduled += timedelta(days=1)
    return scheduled.astimezone(UTC)


class ListingGradeRuleService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ListingGradeRuleRepository(session)

    @staticmethod
    def _read(row: ListingGradeRuleVersion | None, *, can_edit: bool) -> ListingGradeRuleRead:
        if row is None:
            return ListingGradeRuleRead(
                version=0,
                config=ListingGradeRuleConfig(),
                source="default",
                can_edit=can_edit,
            )
        return ListingGradeRuleRead(
            version=row.version,
            config=ListingGradeRuleConfig.model_validate(row.config_json),
            effective_from=row.effective_from,
            created_at=row.created_at,
            created_by=row.created_by,
            change_reason=row.change_reason,
            is_pending=row.effective_from > datetime.now(UTC),
            source="database",
            can_edit=can_edit,
        )

    def get(self, *, can_edit: bool) -> ListingGradeRuleRead:
        try:
            return self._read(self.repo.latest(), can_edit=can_edit)
        except DBAPIError as error:
            if not _rule_table_missing(error):
                raise
            # No schema migration is authorized against the local production tunnel.
            # Permit a truthful read-only preview of the approved defaults.
            self.session.rollback()
            return ListingGradeRuleRead(
                version=0,
                config=ListingGradeRuleConfig(),
                source="default",
                can_edit=False,
                storage_ready=False,
            )

    def update(self, *, request: ListingGradeRuleUpdate, actor: str) -> ListingGradeRuleRead:
        now = datetime.now(UTC)
        try:
            self.repo.lock_for_version_change()
            latest = self.repo.latest()
            current_version = latest.version if latest else 0
            if request.expected_version != current_version:
                raise ApiError(
                    code="LISTING_RULE_VERSION_CONFLICT",
                    status_code=409,
                    message="规则已被他人修改，请刷新后重试",
                    details={"current_version": current_version},
                )
            if (
                latest
                and ListingGradeRuleConfig.model_validate(latest.config_json) == request.config
            ):
                raise ApiError(
                    code="LISTING_RULE_NO_CHANGES",
                    status_code=409,
                    message="规则内容未变化，不生成重复版本",
                )
            row = ListingGradeRuleVersion(
                version=current_version + 1,
                config_json=request.config.model_dump(mode="json"),
                effective_from=next_rating_time_utc(now, request.config.execution_time),
                created_at=now,
                created_by=actor,
                change_reason=request.change_reason.strip(),
            )
            self.repo.append(row)
            self.session.commit()
            return self._read(row, can_edit=True)
        except DBAPIError as error:
            self.session.rollback()
            if _rule_table_missing(error):
                raise ApiError(
                    code="LISTING_RULE_STORAGE_NOT_READY",
                    status_code=503,
                    message="规则配置表尚未初始化；仅允许在隔离开发库迁移",
                ) from error
            raise
        except Exception:
            self.session.rollback()
            raise

    def history(self, *, limit: int, offset: int) -> ListingGradeRuleHistoryData:
        try:
            rows, total = self.repo.history(limit=limit, offset=offset)
        except DBAPIError as error:
            if not _rule_table_missing(error):
                raise
            self.session.rollback()
            return ListingGradeRuleHistoryData(items=[], total=0, storage_ready=False)
        return ListingGradeRuleHistoryData(
            total=total,
            items=[
                ListingGradeRuleHistoryItem(
                    version=row.version,
                    config=ListingGradeRuleConfig.model_validate(row.config_json),
                    effective_from=row.effective_from,
                    created_at=row.created_at,
                    created_by=row.created_by,
                    change_reason=row.change_reason,
                )
                for row in rows
            ],
        )

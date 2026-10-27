"""SQLAlchemy access to append-only Listing grade rule versions."""

from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.modules.listing_rule_config.models import ListingGradeRuleVersion


class ListingGradeRuleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def lock_for_version_change(self) -> None:
        """Serialize rule updates across workers without locking Listing data."""
        self.session.execute(text("SELECT pg_advisory_xact_lock(2406251025)"))

    def latest(self) -> ListingGradeRuleVersion | None:
        return self.session.scalars(
            select(ListingGradeRuleVersion)
            .order_by(ListingGradeRuleVersion.version.desc())
            .limit(1)
        ).first()

    def history(self, *, limit: int, offset: int) -> tuple[list[ListingGradeRuleVersion], int]:
        total = self.session.scalar(select(func.count()).select_from(ListingGradeRuleVersion)) or 0
        rows = self.session.scalars(
            select(ListingGradeRuleVersion)
            .order_by(ListingGradeRuleVersion.version.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return list(rows), total

    def append(self, version: ListingGradeRuleVersion) -> None:
        self.session.add(version)
        self.session.flush()

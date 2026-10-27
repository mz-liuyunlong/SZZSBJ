from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.walmart_monitor.models import RawWalmartMonitorEvent


@dataclass(frozen=True, slots=True)
class RawEventWriteResult:
    event: RawWalmartMonitorEvent
    created: bool


class WalmartMonitorEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def insert_or_get(self, values: dict[str, object]) -> RawEventWriteResult:
        statement = (
            insert(RawWalmartMonitorEvent)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[RawWalmartMonitorEvent.event_id])
            .returning(RawWalmartMonitorEvent.id)
        )
        inserted_id = self.session.scalar(statement)
        if isinstance(inserted_id, UUID):
            event = self.session.scalar(
                select(RawWalmartMonitorEvent).where(RawWalmartMonitorEvent.id == inserted_id)
            )
            if event is None:
                raise RuntimeError("inserted monitor event could not be read")
            return RawEventWriteResult(event=event, created=True)

        event_id = str(values["event_id"])
        existing = self.session.scalar(
            select(RawWalmartMonitorEvent).where(RawWalmartMonitorEvent.event_id == event_id)
        )
        if existing is None:
            raise RuntimeError("conflicting monitor event could not be read")
        return RawEventWriteResult(event=existing, created=False)

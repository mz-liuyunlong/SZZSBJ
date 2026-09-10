from sqlalchemy.orm import Session

from app.models.raw_lingxing_api import RawLingxingApi


class LingxingRawRepository:
    """Append-only RAW persistence; callers own transactions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, record: RawLingxingApi) -> RawLingxingApi:
        self.session.add(record)
        self.session.flush()
        return record

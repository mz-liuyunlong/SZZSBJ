from typing import Protocol
from uuid import UUID


class SyncHandler(Protocol):
    handler_key: str

    def execute(self, run_id: UUID) -> None: ...

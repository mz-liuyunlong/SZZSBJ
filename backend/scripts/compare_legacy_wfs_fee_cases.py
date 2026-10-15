from __future__ import annotations

import json

from sqlalchemy import text

from app.db.session import get_session_factory
from app.modules.warehouse_wfs.service import WfsFeeAlertService


def main() -> None:
    Session = get_session_factory()
    with Session() as session:
        session.execute(text("set transaction read only"))
        result = WfsFeeAlertService(session).compare_legacy_cases()
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

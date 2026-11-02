"""Read-only HTTP contract verification against the approved local database, no login writes."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from scripts.wfs_pending_local_schema import local_url  # noqa: E402


def main():
    engine = create_engine(local_url(), hide_parameters=True)
    from app.core.auth import Principal, get_optional_principal
    from app.db.session import get_db_session
    from app.main import create_app
    from app.modules.integration_sync.dependencies import require_source_account_scope
    from app.modules.pmc_domestic.packing_models import PackingOrder

    with Session(engine) as session:
        accounts = frozenset(session.scalars(select(PackingOrder.source_account_ref).distinct()))
        app = create_app()
        app.dependency_overrides[get_db_session] = lambda: session
        app.dependency_overrides[get_optional_principal] = lambda: Principal(
            user_id="local-readonly-verification", permissions=frozenset({"*"})
        )
        app.dependency_overrides[require_source_account_scope] = lambda: accounts
        with TestClient(app) as client:
            for path in ("orders", "summary", "filter-options"):
                response = client.get("/api/pmc/wfs/pending-packing/" + path)
                if response.status_code != 200:
                    raise RuntimeError(f"Local read contract failed: {path} {response.status_code}")
                payload = response.json()
                data = payload["data"]
                safe = {
                    "status": response.status_code,
                    "request_id_present": bool(payload["request_id"]),
                }
                if path == "orders":
                    safe["total"] = data["total"]
                elif path == "summary":
                    safe.update(data)
                else:
                    safe["store_option_count"] = len(data["stores"])
                print(json.dumps({path: safe}, ensure_ascii=False))
        session.rollback()
    engine.dispose()


if __name__ == "__main__":
    main()

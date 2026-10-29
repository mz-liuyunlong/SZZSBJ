"""Loopback-only E2E fixture app. Never import this module from application code."""

import os

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.api import success_response
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_domestic.warehouse_router import router as warehouse_router
from tests.modules.pmc_wfs.v2_support import (
    SyntheticGateway,
    app_for,
    engine_and_schema,
    seed_fixture,
)

assert os.environ.get("APP_ENV") == "test"
engine = engine_and_schema()
with Session(engine, expire_on_commit=False) as session:
    account, main, *_ = seed_fixture(session)
    _, edit, *_ = seed_fixture(session, boxes=3, per=5)
    main.pk = "PK-E2E-MAIN-" + main.id.hex[:8]
    edit.pk = "PK-E2E-EDIT-" + edit.id.hex[:8]
    edit.source_account_ref = account
    edit.snapshot_json = {**edit.snapshot_json, "source_account_ref": account}
    session.commit()

gateway = SyntheticGateway()
app = app_for(engine, account, gateway)
app.include_router(warehouse_router)


def db():
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_db_session] = db
app.dependency_overrides[require_source_account_scope] = lambda: frozenset({account})


@app.get("/health")
def health():
    return {"status": "synthetic-wfs-e2e-only"}


@app.get("/api/auth/me")
def me(request: Request):
    return success_response(
        request,
        data={
            "id": 16,
            "username": "wfs-fixture",
            "display_name": "WFS 隔离验收",
            "is_super_admin": True,
            "is_active": True,
            "permissions": ["*"],
            "role_keys": [],
            "role_names": [],
            "email": None,
            "phone": None,
        },
        meta={"synthetic": True},
    )

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from typing import cast
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import Column, Engine, MetaData, String, Table, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.sql.sqltypes import NullType

import app.modules.integration_sync.handlers.lingxing_product_list_sync as handler_module
from app.db.base import Base
from app.db.model_registry import register_productlist_sync_models
from app.modules.sku_detail.models import LingxingSkuIdentity
from scripts import run_productlist_once as command


def test_missing_product_model_reproduces_identity_flush_failure() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _UNREGISTERED_FLUSH_REPRO],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_registration_adds_required_tables_and_allows_identity_flush() -> None:
    register_productlist_sync_models()

    assert {
        "products",
        "dwd_lingxing_sku_identity_index",
        "gov_integration_sync_runs",
    } <= set(Base.metadata.tables)

    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        _create_identity_storage(engine)
        now = datetime(2026, 1, 1, tzinfo=UTC)
        run_id = uuid4()
        with Session(engine) as session:
            session.add(
                LingxingSkuIdentity(
                    id=uuid4(),
                    provider="lingxing",
                    source_account_ref="fixture-account",
                    lingxing_sku_id="fixture-id",
                    mapping_status="unmapped",
                    is_active=True,
                    first_seen_run_id=run_id,
                    last_seen_run_id=run_id,
                    first_seen_at=now,
                    last_seen_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.flush()
    finally:
        engine.dispose()


def test_handler_and_runner_register_models_without_io(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        handler_module,
        "register_productlist_sync_models",
        lambda: calls.append("handler"),
    )
    monkeypatch.setattr(
        command,
        "register_productlist_sync_models",
        lambda: calls.append("runner"),
    )

    session = MagicMock(spec=Session)
    handler_module.LingxingProductListSyncHandler(session, client=MagicMock())
    command.ProductListOneTimeRunner(session)

    assert calls == ["handler", "runner"]
    assert capsys.readouterr().out == ""


def _create_identity_storage(engine: Engine) -> None:
    source = cast(Table, LingxingSkuIdentity.__table__)
    storage = MetaData()
    Table(
        source.name,
        storage,
        *(
            Column(
                column.name,
                String() if isinstance(column.type, NullType) else column.type,
                primary_key=column.primary_key,
                nullable=column.nullable,
            )
            for column in source.columns
        ),
    )
    storage.create_all(engine)


_UNREGISTERED_FLUSH_REPRO = """
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Column, MetaData, String, Table, create_engine
from sqlalchemy.exc import NoReferencedTableError
from sqlalchemy.orm import Session
from sqlalchemy.sql.sqltypes import NullType

import app.modules.integration_sync.models
from app.modules.sku_detail.models import LingxingSkuIdentity

source = LingxingSkuIdentity.__table__
storage = MetaData()
Table(
    source.name,
    storage,
    *(Column(column.name, String() if isinstance(column.type, NullType) else column.type,
              primary_key=column.primary_key,
              nullable=column.nullable) for column in source.columns),
)
engine = create_engine("sqlite+pysqlite:///:memory:")
storage.create_all(engine)
now = datetime(2026, 1, 1, tzinfo=UTC)
run_id = uuid4()
try:
    with Session(engine) as session:
        session.add(LingxingSkuIdentity(
            id=uuid4(), provider="lingxing", source_account_ref="fixture-account",
            lingxing_sku_id="fixture-id", mapping_status="unmapped", is_active=True,
            first_seen_run_id=run_id, last_seen_run_id=run_id,
            first_seen_at=now, last_seen_at=now, created_at=now, updated_at=now,
        ))
        session.flush()
except NoReferencedTableError:
    raise SystemExit(0) from None
raise SystemExit(1)
"""

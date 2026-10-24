"""Receipt ODS → domestic batch DWD publication."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.modules.integration_sync.models import IntegrationSyncRun
from app.modules.pmc_domestic.models import DwdDomesticReceiptBatch, DwdDomesticReceiptBatchLink
from app.modules.pmc_domestic.publisher import PmcDomesticDwdPublisher
from app.modules.pmc_purchase.models import LingxingReceiptOrderItemOds, LingxingReceiptOrderOds

ACCOUNT = "primary"
T1 = datetime(2026, 10, 10, 3, 0, tzinfo=UTC)
TABLES = (
    "gov_integration_sync_runs",
    "ods_lingxing_receipt_orders",
    "ods_lingxing_receipt_order_items",
    "dwd_domestic_receipt_batch",
    "dwd_domestic_receipt_batch_link",
)


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_: object, compiler: object, **kw: object) -> str:
    return "JSON"


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _sqlite_functions(dbapi_connection: object, _record: object) -> None:
        dbapi_connection.create_function("char_length", 1, len)  # type: ignore[attr-defined]

    Base.metadata.create_all(engine, tables=[Base.metadata.tables[n] for n in TABLES])
    with Session(engine) as s:
        yield s
    engine.dispose()


def _run(session: Session) -> tuple[UUID, UUID]:
    run_id, ref_id = uuid4(), uuid4()
    session.add(
        IntegrationSyncRun(
            id=run_id,
            interface_id=uuid4(),
            provider="lingxing",
            interface_key=f"receipt:{run_id.hex[:8]}",
            source_account_ref=ACCOUNT,
            trigger_type="manual",
            status="succeeded",
            idempotency_key=f"receipt:{run_id}",
            queued_at=T1,
            started_at=T1,
            finished_at=T1,
        )
    )
    session.flush()
    return run_id, ref_id


def test_publish_inserts_batch_and_unresolved_link(session: Session) -> None:
    run_id, ref_id = _run(session)
    session.add(
        LingxingReceiptOrderOds(
            run_id=run_id,
            raw_request_ref_id=ref_id,
            source_account_ref=ACCOUNT,
            source_item_ordinal=0,
            payload_json={"update_time": "2026-10-09 12:00:00"},
            observed_at=T1,
            order_sn="R-100",
            business_order_sn="PO-9",
            receive_time="2026-10-09 23:30:00",
            wid="WH-1",
            item_count=1,
        )
    )
    session.add(
        LingxingReceiptOrderItemOds(
            run_id=run_id,
            raw_request_ref_id=ref_id,
            source_account_ref=ACCOUNT,
            source_item_ordinal=0,
            payload_json={},
            observed_at=T1,
            receipt_order_sn="R-100",
            line_ordinal=0,
            sku="SKU-A",
            product_receive_num=12,
        )
    )
    session.commit()

    result = PmcDomesticDwdPublisher(session, now=T1).publish(source_account_ref=ACCOUNT)
    assert result.batches_inserted == 1 and result.link_stubs_inserted == 1

    batch = session.scalar(select(DwdDomesticReceiptBatch))
    assert batch is not None
    assert batch.receipt_order_sn == "R-100"
    assert batch.received_business_date == date(2026, 10, 9)
    link = session.scalar(select(DwdDomesticReceiptBatchLink))
    assert link is not None and link.mapping_status == "unresolved"

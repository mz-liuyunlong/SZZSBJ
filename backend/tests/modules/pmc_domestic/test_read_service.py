"""Domestic batch board reads DWD only. Days use Asia/Taipei."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.api import ApiError, ErrorCode
from app.db.base import Base
from app.modules.data_pages.models import LingxingStoreDimension
from app.modules.integration_sync.models import IntegrationSyncRun  # noqa: F401
from app.modules.pmc_domestic.models import DwdDomesticReceiptBatch, DwdDomesticReceiptBatchLink
from app.modules.pmc_domestic.schemas import BatchFilterQuery, BatchListQuery
from app.modules.pmc_domestic.service import PmcDomesticBatchReadService
from app.modules.sku_detail.models import LingxingSkuIdentity, LingxingSkuProductInfoCurrent

ACCOUNT = "primary"
OTHER = "other"
STORE = "110652398125259264"
NOW = datetime(2026, 10, 19, 4, 0, tzinfo=UTC)
TODAY = date(2026, 10, 19)
SCOPE = frozenset({ACCOUNT})
TABLES = (
    "dim_lingxing_stores",
    "dwd_lingxing_sku_identity_index",
    "dwd_lingxing_sku_product_info_current",
    "gov_integration_sync_runs",
    "dwd_domestic_receipt_batch",
    "dwd_domestic_receipt_batch_link",
)

MATCHED_ID = UUID("11111111-1111-4111-8111-111111111111")
UNRESOLVED_ID = UUID("22222222-2222-4222-8222-222222222222")
MISSING_DATE_ID = UUID("33333333-3333-4333-8333-333333333333")
OTHER_ID = UUID("44444444-4444-4444-8444-444444444444")
MIXED_ID = UUID("55555555-5555-4555-8555-555555555555")


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


def _batch(
    session: Session,
    batch_id: UUID,
    *,
    account: str = ACCOUNT,
    receipt: str,
    line: int = 0,
    warehouse: str | None = "WH1",
    sku: str | None = "SKU-A",
    qty: int | None = 10,
    po: str | None = "PO1",
    received: date | None = date(2026, 10, 9),
    receive_time: str | None = "2026-10-09 08:00:00",
) -> DwdDomesticReceiptBatch:
    row = DwdDomesticReceiptBatch(
        id=batch_id,
        source_account_ref=account,
        source_run_id=uuid4(),
        source_ods_id=uuid4(),
        source_observed_at=NOW,
        builder_version="test",
        created_at=NOW,
        updated_at=NOW,
        receipt_order_sn=receipt,
        line_ordinal=line,
        purchase_order_sn=po,
        source_warehouse_id=warehouse,
        sku=sku,
        received_qty=qty,
        receive_time=receive_time,
        received_business_date=received,
    )
    session.add(row)
    return row


def _link(
    session: Session,
    batch_id: UUID,
    *,
    status: str,
    store_id: str | None = STORE,
    batch_no: str | None = "B-1",
    order_sn: str | None = "IB-1",
) -> None:
    session.add(
        DwdDomesticReceiptBatchLink(
            source_account_ref=ACCOUNT,
            receipt_batch_id=batch_id,
            batch_order_sn=order_sn,
            batch_no=batch_no,
            store_id=store_id,
            mapped_qty=4,
            mapping_status=status,
            mapping_method="manual" if status == "matched" else None,
            created_at=NOW,
            updated_at=NOW,
        )
    )


@pytest.fixture
def seeded(session: Session) -> Session:
    _batch(session, MATCHED_ID, receipt="IB-MATCH")
    _link(session, MATCHED_ID, status="matched")
    _batch(
        session,
        UNRESOLVED_ID,
        receipt="IB-OPEN",
        warehouse="WH2",
        sku="SKU-B",
        qty=5,
        po=None,
        received=date(2026, 10, 15),
    )
    _batch(
        session,
        MISSING_DATE_ID,
        receipt="IB-NODATE",
        sku="SKU-C",
        qty=3,
        po="PO2",
        received=None,
        receive_time=None,
    )
    _batch(session, MIXED_ID, receipt="IB-MIX", sku="SKU-D", qty=7, po="PO3")
    _link(session, MIXED_ID, status="unresolved", batch_no="B-open", store_id=None)
    _link(session, MIXED_ID, status="matched", batch_no="B-hit", store_id=STORE)
    _batch(session, OTHER_ID, account=OTHER, receipt="IB-OTHER")
    session.commit()
    return session


def _svc(session: Session) -> PmcDomesticBatchReadService:
    return PmcDomesticBatchReadService(session, now=NOW)


def test_list_is_account_scoped_and_computes_days(seeded: Session) -> None:
    data, total, freshness = _svc(seeded).list_batches(BatchListQuery(), SCOPE)
    assert total == 4
    assert freshness is not None
    aware = freshness if freshness.tzinfo else freshness.replace(tzinfo=UTC)
    assert aware == NOW
    by_receipt = {row.receipt_order_sn: row for row in data.items}
    assert set(by_receipt) == {"IB-MATCH", "IB-OPEN", "IB-NODATE", "IB-MIX"}
    matched = by_receipt["IB-MATCH"]
    assert matched.days_in_warehouse == 10
    assert matched.arrival_date_status == "known"
    assert matched.mapping_status == "matched"
    assert matched.links[0].store_id == STORE
    open_row = by_receipt["IB-OPEN"]
    assert open_row.days_in_warehouse == 4
    assert open_row.mapping_status == "unresolved"
    assert open_row.links == []
    missing = by_receipt["IB-NODATE"]
    assert missing.days_in_warehouse is None
    assert missing.arrival_date_status == "unknown"
    mixed = by_receipt["IB-MIX"]
    assert mixed.mapping_status == "matched"
    assert {link.mapping_status for link in mixed.links} == {"unresolved", "matched"}

    empty, empty_total, *_ = _svc(seeded).list_batches(BatchListQuery(), frozenset({OTHER}))
    assert empty_total == 1 and empty.items[0].id == OTHER_ID
    none, none_total, *_ = _svc(seeded).list_batches(BatchListQuery(), frozenset())
    assert none_total == 0 and none.items == []


def test_filters_mapping_store_warehouse_and_search(seeded: Session) -> None:
    svc = _svc(seeded)
    matched, total, *_ = svc.list_batches(BatchListQuery(mapping_status="matched"), SCOPE)
    assert total == 2
    assert {row.receipt_order_sn for row in matched.items} == {"IB-MATCH", "IB-MIX"}

    unresolved, total, *_ = svc.list_batches(BatchListQuery(mapping_status="unresolved"), SCOPE)
    assert total == 2
    assert {row.receipt_order_sn for row in unresolved.items} == {"IB-OPEN", "IB-NODATE"}

    store, total, *_ = svc.list_batches(BatchListQuery(store_id=[STORE]), SCOPE)
    assert {row.receipt_order_sn for row in store.items} == {"IB-MATCH", "IB-MIX"}
    assert total == 2

    warehouse, total, *_ = svc.list_batches(BatchListQuery(warehouse_id=["WH2"]), SCOPE)
    assert total == 1 and warehouse.items[0].receipt_order_sn == "IB-OPEN"

    by_sku, total, *_ = svc.list_batches(BatchListQuery(search="SKU-B"), SCOPE)
    assert total == 1 and by_sku.items[0].sku == "SKU-B"

    by_batch, total, *_ = svc.list_batches(BatchListQuery(search="B-hit"), SCOPE)
    assert total == 1 and by_batch.items[0].receipt_order_sn == "IB-MIX"

    ranged, total, *_ = svc.list_batches(
        BatchListQuery(received_from=date(2026, 10, 14), received_to=date(2026, 10, 15)),
        SCOPE,
    )
    assert total == 1 and ranged.items[0].receipt_order_sn == "IB-OPEN"

    by_po, total, *_ = svc.list_batches(BatchListQuery(purchase_order_sn=["PO2"]), SCOPE)
    assert total == 1 and by_po.items[0].receipt_order_sn == "IB-NODATE"

    by_receipt, total, *_ = svc.list_batches(BatchListQuery(receipt_order_sn=["IB-MATCH"]), SCOPE)
    assert total == 1 and by_receipt.items[0].sku == "SKU-A"


def test_summary_counts_receipt_lines_not_purchase_orders(seeded: Session) -> None:
    data, _freshness = _svc(seeded).summary(BatchFilterQuery(), SCOPE)
    assert data.as_of == TODAY
    assert data.receipt_batch_count == 4
    assert data.received_qty == 25
    assert data.warehouse_count == 2
    assert data.matched_batch_count == 2
    assert data.unresolved_batch_count == 2
    assert data.missing_arrival_date_count == 1

    warehouse_only, *_ = _svc(seeded).summary(BatchFilterQuery(warehouse_id=["WH2"]), SCOPE)
    assert warehouse_only.receipt_batch_count == 1
    assert warehouse_only.received_qty == 5
    assert warehouse_only.matched_batch_count == 0


def test_detail_and_trace_hide_other_accounts_and_mark_outbound_unknown(seeded: Session) -> None:
    svc = _svc(seeded)
    row, _ = svc.detail(MATCHED_ID, SCOPE)
    assert row.receipt_order_sn == "IB-MATCH"
    trace, _ = svc.trace(MATCHED_ID, SCOPE)
    assert trace.outbound.status == "unknown"
    assert trace.outbound.reason == "source_not_published"
    assert trace.outbound.events == []
    with pytest.raises(ApiError) as missing:
        svc.detail(MATCHED_ID, frozenset({OTHER}))
    assert missing.value.code == ErrorCode.NOT_FOUND
    with pytest.raises(ApiError) as unknown:
        svc.trace(uuid4(), SCOPE)
    assert unknown.value.status_code == 404


def _owner(
    session: Session,
    sku: str,
    uid: str | None,
    name: str | None = "同名负责人",
    account: str = ACCOUNT,
    active: bool = True,
) -> None:
    identity = LingxingSkuIdentity(
        id=uuid4(),
        provider="lingxing",
        source_account_ref=account,
        lingxing_sku_id=str(uuid4()),
        lingxing_sku_code=sku,
        is_active=active,
        first_seen_run_id=uuid4(),
        last_seen_run_id=uuid4(),
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    session.add(identity)
    session.flush()
    session.add(
        LingxingSkuProductInfoCurrent(
            provider="lingxing",
            source_account_ref=account,
            identity_id=identity.id,
            lingxing_sku_id=identity.lingxing_sku_id,
            source_snapshot_id=uuid4(),
            source_run_id=uuid4(),
            source_observed_at=NOW,
            owner_uid=uid,
            owner_name=name,
        )
    )


def test_current_owner_filters_share_scope_and_summary_without_duplicate_rows(seeded: Session):
    _owner(seeded, "SKU-A", "001")
    _owner(seeded, "SKU-B", "002")
    _owner(seeded, "SKU-C", None)
    _owner(seeded, "SKU-D", "003")
    _owner(seeded, "SKU-D", "004")  # Ambiguous identity, do not guess an owner.
    _owner(seeded, "SKU-A", "999", account=OTHER)
    _owner(seeded, "SKU-A", "old", active=False)
    seeded.flush()
    svc = _svc(seeded)
    listed, total, _ = svc.list_batches(BatchListQuery(owner_uid=["001", "002"]), SCOPE)
    assert total == 2 and {item.sku for item in listed.items} == {"SKU-A", "SKU-B"}
    summary, _ = svc.summary(BatchFilterQuery(owner_uid=["001", "002"]), SCOPE)
    assert summary.receipt_batch_count == total and summary.received_qty == 15
    _, total, _ = svc.list_batches(BatchListQuery(owner_uid=["002"], store_id=[STORE]), SCOPE)
    assert total == 0
    for uid in ("003", "004", "999", "old"):
        _, total, _ = svc.list_batches(BatchListQuery(owner_uid=[uid]), SCOPE)
        assert total == 0
    options = svc.filter_options(SCOPE)
    assert [item.value for item in options.owners] == ["001", "002"]
    assert [item.label for item in options.owners] == ["同名负责人", "同名负责人"]
    assert svc.filter_options(frozenset()).model_dump() == {"stores": [], "owners": []}


def test_store_options_use_real_ids_and_fail_safe_on_ambiguous_names(seeded: Session):
    seeded.add_all(
        [
            LingxingStoreDimension(
                source_account_ref=ACCOUNT,
                platform_code_raw="walmart",
                store_id=STORE,
                store_name="本店",
                synced_at=NOW,
            ),
            LingxingStoreDimension(
                source_account_ref=OTHER,
                platform_code_raw="walmart",
                store_id=STORE,
                store_name="其他账号店铺",
                synced_at=NOW,
            ),
        ]
    )
    seeded.flush()
    assert _svc(seeded).filter_options(SCOPE).stores[0].model_dump() == {
        "value": STORE,
        "label": "本店",
    }
    seeded.add(
        LingxingStoreDimension(
            source_account_ref=ACCOUNT,
            platform_code_raw="amazon",
            store_id=STORE,
            store_name="冲突名称",
            synced_at=NOW,
        )
    )
    _link(seeded, MATCHED_ID, status="matched", store_id="unknown-id", batch_no="B-other")
    seeded.flush()
    options = {item.value: item.label for item in _svc(seeded).filter_options(SCOPE).stores}
    assert options == {STORE: STORE, "unknown-id": "unknown-id"}

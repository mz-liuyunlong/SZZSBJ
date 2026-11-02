"""0062 and draft decisions on owned, disposable PostgreSQL databases only."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.db.domestic_schema_contract import require_domestic_table
from app.modules.pmc_domestic.inbound_models import DomesticInboundBoard
from app.modules.pmc_domestic.packing_models import (
    PackingAllocation,
    PackingEvent,
    PackingOrder,
    PackingPendingEdit,
)
from app.modules.pmc_domestic.packing_rules import listing_version
from app.modules.pmc_domestic.packing_schemas import (
    ApproveCommand,
    Candidate,
    EditDraftCommand,
    RejectCommand,
)
from app.modules.pmc_domestic.packing_service import PackingService, split_child_id
from tests.db.domestic_postgresql_support import admin_url, create_database, drop_database
from tests.db.test_domestic_chain_postgresql import (
    DOMESTIC_0049,
    DOMESTIC_TABLES,
    _alembic,
    _marker_unchanged,
    _seed_0049,
    _snapshot_0049,
    _version,
)

REVISION = "20261031_0069_walmart_gateway_ledger"
PREVIOUS = "20261027_0061_merge_purchase_main"


@pytest.mark.parametrize("start", [None, DOMESTIC_0049, PREVIOUS])
def test_0062_preserves_data_and_supports_atomic_draft_approval(start):
    url = admin_url()
    database = create_database(url, "pending_edit")
    engine = None
    try:
        before = marker = None
        if start:
            prepared = _alembic(url, database, start)
            assert prepared.returncode == 0, prepared.stderr
            marker = _seed_0049(url, database)
            before = _snapshot_0049(url, database)
        upgraded = _alembic(url, database, "head")
        assert upgraded.returncode == 0, upgraded.stderr
        assert _version(url, database) == [REVISION]
        if start:
            assert _snapshot_0049(url, database) == before
            assert _marker_unchanged(url, database, marker)
        else:
            _seed_0049(url, database)

        engine = sa.create_engine(url.set(database=database), hide_parameters=True)
        with engine.begin() as conn:
            tables = {name for name in sa.inspect(conn).get_table_names() if "_domestic_" in name}
            assert tables == set(DOMESTIC_TABLES) | {PackingPendingEdit.__tablename__}
            require_domestic_table(conn, PackingPendingEdit.__table__)
        _exercise_draft_decision(engine)
        _exercise_split_draft(engine)
        repeated = _alembic(url, database, "head")
        assert repeated.returncode == 0, repeated.stderr
        assert "Running upgrade" not in repeated.stdout + repeated.stderr
        with Session(engine) as session:
            # 1 approved + 1 rejected (single drafts) + 2 from one split draft.
            assert session.scalar(sa.select(sa.func.count()).select_from(PackingOrder)) == 4
            assert session.scalar(sa.select(sa.func.count()).select_from(PackingPendingEdit)) == 0
    finally:
        if engine is not None:
            engine.dispose()
        drop_database(url, database)


def _exercise_draft_decision(engine):
    with Session(engine) as session:
        board = session.scalar(sa.select(DomesticInboundBoard))
        candidate = Candidate(
            id=uuid4(),
            candidate_version="a" * 64,
            source_account_ref=board.source_account_ref,
            warehouse_id="16168",
            publication_id=board.publication_id,
            board_id=board.id,
            inbound_order_sn=board.inbound_order_sn,
            sku=board.sku,
            product_name=None,
            store_id="SYN-STORE",
            store_name=None,
            item_id="11111111111",
            gtin="00000000000000",
            msku="SYN-MSKU",
            purchase_order_sns=[],
            arrival_purchased=10,
            candidate_created_on=None,
            overdue=False,
            stock_balance=10,
            available_quantity=10,
            default_quantity=10,
            can_approve=True,
            blocked_reasons=[],
            source_observed_at=datetime.now(UTC),
        )
        listing = SimpleNamespace(
            id=uuid4(),
            source_account_ref=candidate.source_account_ref,
            store_id=candidate.store_id,
            local_sku=candidate.sku,
            item_id=candidate.item_id,
            gtin=candidate.gtin,
            msku=candidate.msku,
            standard_status="PUBLISHED",
            item_url="https://www.walmart.com/ip/synthetic",
            fulfillment_type="1",
            business_hash="b" * 64,
        )
        service = PackingService(session)
        # admin_url/create_database already enforce an owned disposable CI target.
        # Inject source proofs so this test exercises persistence and transactions,
        # without depending on provider sync or a pre-existing local business DB.
        service.guard_local = lambda: None
        service._base_candidates = lambda accounts: [candidate]
        service._store_names = lambda account: {}
        service._listings_by_identity = lambda account, store, item: [
            row for row in [listing] if row.store_id == store and row.item_id == item
        ]
        accounts = frozenset({candidate.source_account_ref})
        command = EditDraftCommand(
            source_account_ref=candidate.source_account_ref,
            candidate_version=candidate.candidate_version,
            target_store_id=listing.store_id,
            target_item_id=listing.item_id,
            listing_version=listing_version(listing),
            qty=4,
            customs="declare",
            edit_reason="合成测试修改",
        )
        with pytest.raises(ApiError) as denied:
            service.save_pending_edit(candidate.id, command, "synthetic-user", frozenset())
        assert denied.value.status_code == 403

        service.save_pending_edit(candidate.id, command, "synthetic-user", accounts)
        assert session.scalar(sa.select(sa.func.count()).select_from(PackingOrder)) == 0
        # Expiration forces the refreshed draft to be read from PostgreSQL.
        session.expire_all()
        refreshed = service.all_candidates(accounts)[0]
        assert refreshed.edit_draft_pending and refreshed.default_quantity == 4
        assert refreshed.manual_customs == "declare"
        assert session.get(PackingPendingEdit, candidate.id).requested_qty == 4
        candidate.candidate_version = "c" * 64
        stale = service.all_candidates(accounts)[0]
        assert stale.edit_draft_stale and not stale.can_approve
        assert "EDIT_DRAFT_STALE" in stale.blocked_reasons
        candidate.candidate_version = command.candidate_version

        approve = ApproveCommand(
            source_account_ref=candidate.source_account_ref,
            candidate_version=candidate.candidate_version,
            idempotency_key=uuid4(),
            qty=4,
            customs="declare",
        )

        def reject_commit(session):
            # Fail after flushing order/allocation/draft deletion, proving all of
            # them roll back together rather than testing an early validation error.
            session.flush()
            raise RuntimeError("synthetic-commit-failure")

        sa.event.listen(session, "before_commit", reject_commit)
        try:
            with pytest.raises(RuntimeError, match="synthetic-commit-failure"):
                service.decide(candidate.id, approve, "approve", "synthetic-user", accounts)
        finally:
            sa.event.remove(session, "before_commit", reject_commit)
        assert session.get(PackingPendingEdit, candidate.id) is not None
        for model in (PackingOrder, PackingAllocation, PackingEvent):
            assert session.scalar(sa.select(sa.func.count()).select_from(model)) == 0

        result = service.decide(candidate.id, approve, "approve", "synthetic-user", accounts)
        assert result.qty == 4 and result.customs_value is True
        assert result.pk.endswith("-001")  # Failed transaction did not consume a serial.
        assert session.get(PackingPendingEdit, candidate.id) is None
        replay = service.decide(candidate.id, approve, "approve", "synthetic-user", accounts)
        assert replay.id == result.id
        for model in (PackingOrder, PackingAllocation, PackingEvent):
            assert session.scalar(sa.select(sa.func.count()).select_from(model)) == 1
        candidate.id = uuid4()
        candidate.item_id = "22222222222"
        listing.item_id = candidate.item_id
        command = command.model_copy(
            update={
                "lines": None,
                "target_item_id": candidate.item_id,
                "listing_version": listing_version(listing),
            }
        )
        command = EditDraftCommand.model_validate(command.model_dump())
        service.save_pending_edit(candidate.id, command, "synthetic-user", accounts)
        assert session.get(PackingPendingEdit, candidate.id) is not None
        rejection = RejectCommand(
            source_account_ref=candidate.source_account_ref,
            candidate_version=candidate.candidate_version,
            idempotency_key=uuid4(),
            note="Synthetic rejected packing request",
        )
        sa.event.listen(session, "before_commit", reject_commit)
        try:
            with pytest.raises(RuntimeError, match="synthetic-commit-failure"):
                service.decide(candidate.id, rejection, "reject", "synthetic-user", accounts)
        finally:
            sa.event.remove(session, "before_commit", reject_commit)
        assert session.get(PackingPendingEdit, candidate.id) is not None
        assert session.scalar(sa.select(sa.func.count()).select_from(PackingOrder)) == 1
        assert session.scalar(sa.select(sa.func.count()).select_from(PackingEvent)) == 1
        rejected = service.decide(candidate.id, rejection, "reject", "synthetic-user", accounts)
        assert rejected.pk is None and rejected.qty is None and rejected.status == "rejected"
        assert rejected.snapshot.default_quantity == 4
        assert rejected.note == rejection.note
        assert session.get(PackingPendingEdit, candidate.id) is None
        replay = service.decide(candidate.id, rejection, "reject", "synthetic-user", accounts)
        assert replay.id == rejected.id
        assert session.scalar(sa.select(sa.func.count()).select_from(PackingOrder)) == 2
        assert session.scalar(sa.select(sa.func.count()).select_from(PackingEvent)) == 2
        assert session.scalar(sa.select(sa.func.sum(PackingAllocation.qty))) == 4
        assert session.scalar(sa.select(sa.func.count()).select_from(PackingAllocation)) == 1
        assert set(session.scalars(sa.select(PackingEvent.event_kind))) == {"approve", "reject"}


def _listing(candidate, store_id, item_id, *, local_sku=None, fulfillment_type="1"):
    return SimpleNamespace(
        id=uuid4(),
        source_account_ref=candidate.source_account_ref,
        store_id=store_id,
        local_sku=candidate.sku if local_sku is None else local_sku,
        item_id=item_id,
        gtin="00000000000000",
        msku=f"MSKU-{item_id}",
        standard_status="PUBLISHED",
        item_url="https://www.walmart.com/ip/synthetic",
        fulfillment_type=fulfillment_type,
        business_hash="b" * 64,
    )


def _exercise_split_draft(engine):
    """Rocky 2026-11-01: modify by ItemID, reason required, WFS + SKU guards, and a
    split draft that approves into one packing order (own PK + allocation) per line."""
    with Session(engine) as session:
        board = session.scalar(sa.select(DomesticInboundBoard))
        candidate = Candidate(
            id=uuid4(),
            candidate_version="d" * 64,
            source_account_ref=board.source_account_ref,
            warehouse_id="16168",
            publication_id=board.publication_id,
            board_id=board.id,
            inbound_order_sn=board.inbound_order_sn,
            sku=board.sku,
            product_name=None,
            store_id="SYN-STORE",
            store_name=None,
            item_id="33333333333",
            gtin="00000000000000",
            msku="SYN-MSKU",
            purchase_order_sns=[],
            arrival_purchased=10,
            candidate_created_on=None,
            overdue=False,
            stock_balance=10,
            available_quantity=10,
            default_quantity=10,
            can_approve=True,
            blocked_reasons=[],
            source_observed_at=datetime.now(UTC),
        )
        same_store = _listing(candidate, "SYN-STORE", "33333333333")
        other_store = _listing(candidate, "SYN-STORE-2", "44444444444", local_sku="")
        not_wfs = _listing(candidate, "SYN-STORE", "55555555555", fulfillment_type="0")
        other_sku = _listing(candidate, "SYN-STORE", "66666666666", local_sku="OTHER-SKU")
        listings = [same_store, other_store, not_wfs, other_sku]
        service = PackingService(session)
        service.guard_local = lambda: None
        service._base_candidates = lambda accounts: [candidate]
        service._store_names = lambda account: {"SYN-STORE": "店铺一", "SYN-STORE-2": "店铺二"}
        service._listings_by_identity = lambda account, store, item: [
            row for row in listings if row.store_id == store and row.item_id == item
        ]
        accounts = frozenset({candidate.source_account_ref})

        assert service._target_blocked(candidate, same_store) == []
        assert service._target_blocked(candidate, other_store) == []  # blank local SKU: by ItemID
        assert service._target_blocked(candidate, not_wfs) == ["WFS_NOT_CONVERTED"]
        assert service._target_blocked(candidate, other_sku) == ["SKU_MISMATCH"]

        def line(listing, qty):
            return {
                "target_store_id": listing.store_id,
                "target_item_id": listing.item_id,
                "listing_version": listing_version(listing),
                "qty": qty,
            }

        def draft(lines, reason="一票拆两个店铺"):
            return EditDraftCommand.model_validate(
                {
                    "source_account_ref": candidate.source_account_ref,
                    "candidate_version": candidate.candidate_version,
                    "lines": lines,
                    "customs": "skip",
                    "edit_reason": reason,
                }
            )

        def reason_of(lines, **kwargs):
            with pytest.raises(ApiError) as err:
                service.save_pending_edit(
                    candidate.id, draft(lines, **kwargs), "synthetic-user", accounts
                )
            return err.value.details["reason"]

        assert reason_of([line(same_store, 5)], reason=None) == "EDIT_REASON_REQUIRED"
        assert reason_of([line(not_wfs, 5)]) == "WFS_NOT_CONVERTED"
        assert reason_of([line(other_sku, 5)]) == "SKU_MISMATCH"
        assert reason_of([line(same_store, 5), line(same_store, 1)]) == "SPLIT_LINES_DUPLICATE"
        assert reason_of([line(same_store, 6), line(other_store, 5)]) == "INSUFFICIENT_STOCK"
        assert session.get(PackingPendingEdit, candidate.id) is None

        saved = service.save_pending_edit(
            candidate.id,
            draft([line(same_store, 6), line(other_store, 4)]),
            "synthetic-user",
            accounts,
        )
        assert [(x.store_id, x.item_id, x.qty) for x in saved.snapshot.split_lines] == [
            ("SYN-STORE", "33333333333", 6),
            ("SYN-STORE-2", "44444444444", 4),
        ]
        assert saved.snapshot.default_quantity == 10
        session.expire_all()
        listed = service.all_candidates(accounts)[0]
        assert listed.default_quantity == 10 and len(listed.split_lines) == 2

        def approve(qty, key):
            return ApproveCommand(
                source_account_ref=candidate.source_account_ref,
                candidate_version=candidate.candidate_version,
                idempotency_key=key,
                qty=qty,
                customs="skip",
            )

        key = uuid4()
        with pytest.raises(ApiError) as err:
            service.decide(candidate.id, approve(9, uuid4()), "approve", "u", accounts)
        assert err.value.details["reason"] == "SPLIT_QTY_MISMATCH"
        before = session.scalar(sa.select(sa.func.count()).select_from(PackingOrder))
        result = service.decide(candidate.id, approve(10, key), "approve", "u", accounts)
        assert len(result.split_pks) == 2 and len(set(result.split_pks)) == 2
        assert result.pk == result.split_pks[0] and result.qty == 6
        orders = list(
            session.scalars(
                sa.select(PackingOrder)
                .where(PackingOrder.pk.in_(result.split_pks))
                .order_by(PackingOrder.pk)
            )
        )
        assert [(o.store_id, o.item_id, o.qty) for o in orders] == [
            ("SYN-STORE", "33333333333", 6),
            ("SYN-STORE-2", "44444444444", 4),
        ]
        assert {o.candidate_id for o in orders} == {
            candidate.id,
            split_child_id(candidate.id, 2),
        }
        allocated = session.scalars(
            sa.select(PackingAllocation.qty).where(
                PackingAllocation.order_id.in_([o.id for o in orders])
            )
        )
        assert sorted(allocated) == [4, 6]
        assert session.scalar(sa.select(sa.func.count()).select_from(PackingOrder)) == before + 2
        assert session.get(PackingPendingEdit, candidate.id) is None
        replay = service.decide(candidate.id, approve(10, key), "approve", "u", accounts)
        assert replay.id == result.id and replay.split_pks == result.split_pks
        assert session.scalar(sa.select(sa.func.count()).select_from(PackingOrder)) == before + 2

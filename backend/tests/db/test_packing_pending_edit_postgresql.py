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
from app.modules.pmc_domestic.packing_service import PackingService
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

REVISION = "20261031_0070_feishu_org_snapshot"
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
        repeated = _alembic(url, database, "head")
        assert repeated.returncode == 0, repeated.stderr
        assert "Running upgrade" not in repeated.stdout + repeated.stderr
        with Session(engine) as session:
            assert session.scalar(sa.select(sa.func.count()).select_from(PackingOrder)) == 2
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
        service.listing_rows = lambda row: [listing]
        accounts = frozenset({candidate.source_account_ref})
        command = EditDraftCommand(
            source_account_ref=candidate.source_account_ref,
            candidate_version=candidate.candidate_version,
            target_store_id=listing.store_id,
            target_item_id=listing.item_id,
            listing_version=listing_version(listing),
            qty=4,
            customs="declare",
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
        command.target_item_id = candidate.item_id
        command.listing_version = listing_version(listing)
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

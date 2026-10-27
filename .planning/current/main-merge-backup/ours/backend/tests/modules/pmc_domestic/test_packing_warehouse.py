"""Only this warehouse slice, using guarded local rollback fixtures; no external calls."""

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
import test_packing_approval as approval
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.api import ApiError
from app.modules.pmc_domestic.packing_schemas import PackingQuery
from app.modules.pmc_domestic.packing_service import PackingService
from app.modules.pmc_domestic.warehouse_schemas import (
    BoxesCommand,
    BoxLineInput,
    CustomsCommand,
    DoneCommand,
    NoteCommand,
    PackageInput,
    ProductRequirement,
    WarehouseFilter,
    WarehouseQuery,
)
from app.modules.pmc_domestic.warehouse_service import WarehouseService, requirement

db = approval.db
seeded = approval.seeded


@pytest.fixture
def order(db, seeded):
    account, _board, pub = seeded
    base = PackingService(db)
    row = base.pending(PackingQuery(), frozenset({account})).items[0]
    cmd = approval.command(row)
    cmd.qty = 5
    result = base.decide(row.id, cmd, "approve", "fixture", frozenset({account}))
    return result, account, pub


def boxes(row, qty=5, **extra):
    return BoxesCommand(
        source_account_ref=row.source_account_ref,
        expected_version=row.version,
        idempotency_key=uuid4(),
        lines=[
            BoxLineInput(box_type="A", boxes=1, units_per_box=qty, gross_weight_kg=Decimal("3.5"))
        ],
        **extra,
    )


def done(row):
    return DoneCommand(
        source_account_ref=row.source_account_ref,
        expected_version=row.version,
        idempotency_key=uuid4(),
        expected_box_version=row.box_set.version,
        requirement_version=row.product_requirement.version,
    )


@pytest.mark.parametrize("value", [True, 0, -1, 1.2, "2"])
def test_box_quantity_is_strict(value):
    with pytest.raises(ValueError):
        BoxLineInput(box_type="A", boxes=value, units_per_box=2, gross_weight_kg="1")


def test_product_three_states_and_weights():
    assert requirement([]).state == "unknown"
    row = SimpleNamespace(
        id=uuid4(),
        source_snapshot_id=uuid4(),
        package_length_cm=Decimal(10),
        package_width_cm=Decimal(5),
        package_height_cm=Decimal(3),
        product_gross_weight_g=Decimal(100),
        product_net_weight_g=Decimal(80),
    )
    assert requirement([row]).state == "complete"
    assert requirement([row, row]).state == "unknown"
    row.package_width_cm = None
    assert requirement([row]).state == "missing"


def test_list_summary_scope_dates_and_current_projection(db, order):
    approved, account, _pub = order
    svc = WarehouseService(db)
    scope = frozenset({account})
    data = svc.list(WarehouseQuery(), scope)
    assert data.total == 1 and data.items[0].arrival_date == data.items[0].inbound_date
    assert data.items[0].inbound_date and data.items[0].warehouse_days is not None
    assert svc.list(WarehouseQuery(), frozenset()).total == 0
    assert svc.list(WarehouseQuery(keyword="NO-SUCH-PK"), scope).total == 0
    assert svc.summary(WarehouseFilter(status="packed"), scope).todo == 1
    assert svc.options(scope).stores[0].value == "fixture-store"
    assert svc.events(approved.id, scope, 1, 20).total == 1


def test_underpack_is_draft_and_no_second_inventory_allocation(db, order):
    approved, account, _ = order
    svc = WarehouseService(db)
    scope = frozenset({account})
    row = svc.detail(approved.id, scope)
    cmd = boxes(row, 3, reason="尾箱等货")
    result = svc.command(row.id, "boxes", cmd, "fixture", scope)
    assert result.box_set.total_qty == 3 and result.box_set.variance_qty == -2
    assert "QUANTITY_RULE_PENDING" not in result.completion_blocked_reasons
    assert svc.command(row.id, "boxes", cmd, "fixture", scope).version == result.version
    with pytest.raises(ApiError) as error:
        svc.command(row.id, "done", done(result), "fixture", scope)
    assert error.value.details["reason"] == "UNDERPACK_REASON_REQUIRED"
    assert (
        db.scalar(
            text(
                "SELECT sum(qty) FROM ops_domestic_packing_allocations WHERE source_account_ref=:a"
            ),
            {"a": account},
        )
        == 5
    )


def test_drafts_accept_actual_quantity_but_overcompletion_waits_for_stock_rule(db, order):
    approved, account, _ = order
    svc = WarehouseService(db)
    scope = frozenset({account})
    row = svc.detail(approved.id, scope)
    over = svc.command(row.id, "boxes", boxes(row, 6), "fixture", scope)
    assert over.box_set.total_qty == 6
    with pytest.raises(ApiError) as error:
        svc.command(row.id, "done", done(over), "fixture", scope)
    assert error.value.details["reason"] == "EXTRA_STOCK_CONFIRM_REQUIRED"
    saved = svc.command(row.id, "boxes", boxes(over, 3), "fixture", scope)
    assert saved.box_set.total_qty == 3


def test_undercompletion_freezes_once_and_retains_unpacked_hold(db, order):
    approved, account, _ = order
    svc = WarehouseService(db)
    scope = frozenset({account})
    row = svc.detail(approved.id, scope)
    saved = svc.command(row.id, "boxes", boxes(row, 3), "fixture", scope)
    command = done(saved)
    command.reason_category = "other"
    command.reason = "尾箱容纳不足"
    command.package = PackageInput(length_cm=12, width_cm=8, height_cm=4, gross_weight_g=123)
    result = svc.command(row.id, "done", command, "fixture", scope)
    assert result.status == "packed"
    assert result.variance_case.quantity == 2 and result.variance_case.state == "pending"
    assert result.variance_case.reason_category == "other"
    assert svc.command(row.id, "done", command, "fixture", scope).version == result.version
    with pytest.raises(ApiError) as error:
        svc.command(row.id, "done", done(result), "fixture", scope)
    assert error.value.details["reason"] == "ALREADY_COMPLETED"
    assert (
        db.scalar(
            text(
                "SELECT sum(qty) FROM ops_domestic_packing_allocations WHERE source_account_ref=:a"
            ),
            {"a": account},
        )
        == 5
    )


def test_completion_decision_branches():
    from app.modules.pmc_domestic.warehouse_completion_rules import decide_completion as decide

    assert decide(80, 80).outcome == "complete"
    assert decide(80, 70).blocker == "UNDERPACK_REASON_REQUIRED"
    assert decide(80, 70, reason_category="shortage").unpacked_qty == 10
    assert decide(80, 70, reason_category="other", reason=" ").blocker
    assert decide(80, 90).gap_qty is None
    assert decide(80, 90, extra_available=20).blocker == "EXTRA_STOCK_CONFIRM_REQUIRED"
    assert decide(80, 90, extra_available=20, confirm_extra=True).outcome == "complete"
    assert decide(80, 110, extra_available=20).blocker == "OVERPACK_REASON_REQUIRED"
    result = decide(80, 110, extra_available=20, reason="实物多于账面")
    assert result.outcome == "supplement_required" and result.gap_qty == 10


def test_unknown_package_blocks_complete_and_full_known_complete_is_idempotent(
    db, order, monkeypatch
):
    import app.modules.pmc_domestic.warehouse_service as module

    approved, account, _ = order
    svc = WarehouseService(db)
    scope = frozenset({account})
    row = svc.detail(approved.id, scope)
    saved = svc.command(row.id, "boxes", boxes(row), "fixture", scope)
    with pytest.raises(ApiError) as error:
        svc.command(row.id, "done", done(saved), "fixture", scope)
    assert error.value.details["reason"] == "PACKAGE_REQUIRED"
    # Explicit synthetic packaging proof; current real products are read-only in these tests.
    monkeypatch.setattr(
        module,
        "requirement",
        lambda _: ProductRequirement(
            state="complete",
            version="a" * 64,
            package=PackageInput(length_cm=10, width_cm=5, height_cm=3, gross_weight_g=100),
        ),
    )
    ready = svc.detail(row.id, scope)
    command = done(ready)
    result = svc.command(row.id, "done", command, "fixture", scope)
    assert result.status == "packed" and result.box_set.completed_at
    assert svc.command(row.id, "done", command, "fixture", scope).version == result.version
    for kind, body in (("done", done(result)), ("boxes", boxes(result))):
        with pytest.raises(ApiError) as error:
            svc.command(row.id, kind, body, "fixture", scope)
        assert error.value.details["reason"] == "ALREADY_COMPLETED"
    assert svc.summary(WarehouseFilter(status="todo"), scope).packed == 1
    assert svc.events(row.id, scope, 1, 20).total == 3


def test_customs_notes_versions_and_immutable_history(db, order):
    approved, account, _ = order
    svc = WarehouseService(db)
    scope = frozenset({account})
    row = svc.detail(approved.id, scope)
    changed = svc.command(
        row.id,
        "customs",
        CustomsCommand(
            source_account_ref=account,
            expected_version=row.version,
            idempotency_key=uuid4(),
            value=True,
        ),
        "fixture",
        scope,
    )
    assert changed.customs_value is True and changed.customs_src == "manual"
    cleared = svc.command(
        row.id,
        "customs",
        CustomsCommand(
            source_account_ref=account,
            expected_version=changed.version,
            idempotency_key=uuid4(),
            value=None,
        ),
        "fixture",
        scope,
    )
    assert cleared.customs_value is None and cleared.customs_src == "manual"
    noted = svc.command(
        row.id,
        "note",
        NoteCommand(
            source_account_ref=account,
            expected_version=cleared.version,
            idempotency_key=uuid4(),
            category="other",
            text="等待补标签",
        ),
        "fixture",
        scope,
    )
    assert noted.current_note.category == "other"
    resolved = svc.command(
        row.id,
        "note",
        NoteCommand(
            source_account_ref=account,
            expected_version=noted.version,
            idempotency_key=uuid4(),
            category="resolved",
        ),
        "fixture",
        scope,
    )
    assert resolved.current_note.resolved
    events = svc.events(row.id, scope, 1, 20)
    assert [r.kind for r in events.items] == ["note", "note", "customs", "customs", "approve"]
    assert events.items[2].reason is None
    assert events.items[3].reason is None
    assert events.items[0].before["current_note"]["text"] == "等待补标签"
    with pytest.raises(DBAPIError):
        db.execute(
            text(
                "UPDATE evt_domestic_packing_events SET request_json=request_json "
                "WHERE order_id=:id"
            ),
            {"id": row.id},
        )
    db.rollback()


def test_stale_version_actor_idempotency_and_publication_change(db, order):
    approved, account, pub = order
    svc = WarehouseService(db)
    scope = frozenset({account})
    row = svc.detail(approved.id, scope)
    cmd = boxes(row)
    result = svc.command(row.id, "boxes", cmd, "fixture", scope)
    with pytest.raises(ApiError) as error:
        svc.command(row.id, "boxes", cmd, "someone-else", scope)
    assert error.value.details["reason"] == "IDEMPOTENCY_KEY_REUSED"
    with pytest.raises(ApiError) as error:
        svc.command(row.id, "boxes", boxes(row), "fixture", scope)
    assert error.value.details["reason"] == "ORDER_VERSION_CHANGED"
    pub.is_current = False
    db.commit()
    refreshed = svc.detail(row.id, scope)
    assert refreshed.stock_balance is None
    assert (
        svc.command(row.id, "boxes", boxes(refreshed), "fixture", scope).version
        == result.version + 1
    )


def test_page_view_permission_cannot_write_and_scope_cannot_leak(db, order):
    from fastapi.testclient import TestClient

    from app.core.auth import Principal, get_optional_principal
    from app.db.session import get_db_session
    from app.main import create_app
    from app.modules.integration_sync.dependencies import require_source_account_scope

    approved, account, _ = order
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[require_source_account_scope] = lambda: frozenset({account})
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="fixture",
        permissions=frozenset({"page:pmc:domestic-warehouse-board:view"}),
    )
    with TestClient(app) as client:
        prefix = "/api/pmc/domestic/packing-warehouse"
        assert client.get(prefix + "/orders").status_code == 200
        assert (
            client.post(
                prefix + f"/orders/{approved.id}/boxes",
                json=boxes(
                    WarehouseService(db).detail(approved.id, frozenset({account}))
                ).model_dump(mode="json"),
            ).status_code
            == 403
        )
        app.dependency_overrides[require_source_account_scope] = lambda: frozenset({"unrelated"})
        assert client.get(prefix + f"/orders/{approved.id}").status_code == 404


def test_unknown_product_requires_warehouse_measurements_before_completion(db, order):
    approved, account, _ = order
    svc = WarehouseService(db)
    scope = frozenset({account})
    row = svc.detail(approved.id, scope)
    saved = svc.command(row.id, "boxes", boxes(row), "fixture", scope)
    command = done(saved)
    command.package = PackageInput(length_cm=12, width_cm=8, height_cm=4, gross_weight_g=123)
    result = svc.command(row.id, "done", command, "fixture", scope)
    assert result.status == "packed"
    assert result.box_set.package_snapshot["source"] == "warehouse_measurement"
    assert result.box_set.package_snapshot["values"]["gross_weight_g"] == "123"
    assert result.arrival_date == result.inbound_date
    assert result.received_dates == []


def test_event_failure_rolls_back_projection_and_version(db, order, monkeypatch):
    from app.modules.pmc_domestic.packing_models import PackingEvent

    approved, account, _ = order
    svc = WarehouseService(db)
    scope = frozenset({account})
    row = svc.detail(approved.id, scope)
    original = db.flush

    def fail_event(*args, **kwargs):
        if any(isinstance(obj, PackingEvent) for obj in db.new):
            raise RuntimeError("synthetic event failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(db, "flush", fail_event)
    with pytest.raises(RuntimeError, match="synthetic event failure"):
        svc.command(row.id, "boxes", boxes(row), "fixture", scope)
    monkeypatch.setattr(db, "flush", original)
    result = svc.detail(row.id, scope)
    assert result.version == row.version and result.box_set is None


def test_completion_recomputes_saved_line_total(db, order):
    approved, account, _ = order
    svc = WarehouseService(db)
    scope = frozenset({account})
    row = svc.detail(approved.id, scope)
    saved = svc.command(row.id, "boxes", boxes(row), "fixture", scope)
    db.execute(
        text("UPDATE ops_domestic_packing_box_lines SET units_per_box=4 WHERE box_set_id=:id"),
        {"id": saved.box_set.id},
    )
    db.commit()
    with pytest.raises(ApiError) as error:
        svc.command(row.id, "done", done(saved), "fixture", scope)
    assert error.value.details["reason"] == "BOX_TOTAL_CHANGED"


@pytest.mark.parametrize(
    "action,expected_hold,expected_available", [("resend", 3, 7), ("void", 5, 5)]
)
def test_unpacked_disposition_releases_only_when_explicitly_resending(
    db, order, action, expected_hold, expected_available
):
    from app.modules.pmc_domestic.warehouse_schemas import UnpackedDispositionCommand

    approved, account, _ = order
    scope = frozenset({account})
    svc = WarehouseService(db)
    row = svc.detail(approved.id, scope)
    saved = svc.command(row.id, "boxes", boxes(row, 3), "fixture", scope)
    command = done(saved)
    command.reason_category = "shortage"
    command.package = PackageInput(length_cm=12, width_cm=8, height_cm=4, gross_weight_g=123)
    completed = svc.command(row.id, "done", command, "fixture", scope)
    body = UnpackedDispositionCommand(
        source_account_ref=account,
        expected_version=completed.version,
        idempotency_key=uuid4(),
        action=action,
        reason="中台核实后处理",
    )
    result = svc.command(row.id, "unpacked", body, "mid-office", scope)
    assert result.approved_quantity == 5 and result.box_set.total_qty == 3
    assert result.variance_case.state == ("released" if action == "resend" else "voided")
    assert svc.command(row.id, "unpacked", body, "mid-office", scope).version == result.version
    assert (
        db.scalar(
            text("SELECT qty FROM ops_domestic_packing_allocations WHERE order_id=:id"),
            {"id": row.id},
        )
        == expected_hold
    )
    candidates = svc.base.repo.candidates(scope, include_decided=True)
    assert candidates[0].available_quantity == expected_available
    assert svc.events(row.id, scope, 1, 20).items[0].kind == "unpacked"
    body.expected_version = result.version
    body.idempotency_key = uuid4()
    with pytest.raises(ApiError) as error:
        svc.command(row.id, "unpacked", body, "mid-office", scope)
    assert error.value.details["reason"] == "NO_PENDING_UNPACKED"


def test_warehouse_permission_cannot_dispose_unpacked(db, order):
    from fastapi.testclient import TestClient

    from app.core.auth import Principal, get_optional_principal
    from app.db.session import get_db_session
    from app.main import create_app
    from app.modules.integration_sync.dependencies import require_source_account_scope

    approved, account, _ = order
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[require_source_account_scope] = lambda: frozenset({account})
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="warehouse",
        permissions=frozenset(
            {
                "page:pmc:domestic-warehouse-board:view",
                "action:pmc:domestic-warehouse-board:packing-boxes-save",
                "action:pmc:domestic-warehouse-board:packing-done",
            }
        ),
    )
    with TestClient(app) as client:
        response = client.post(
            f"/api/pmc/domestic/packing-warehouse/orders/{approved.id}/unpacked",
            json={
                "source_account_ref": account,
                "expected_version": 1,
                "idempotency_key": str(uuid4()),
                "action": "resend",
            },
        )
        assert response.status_code == 403


def test_rebox_is_separate_audited_revision_not_second_completion(db, order):
    from app.modules.pmc_domestic.warehouse_schemas import ReboxCommand

    approved, account, _ = order
    svc = WarehouseService(db)
    scope = frozenset({account})
    row = svc.detail(approved.id, scope)
    saved = svc.command(row.id, "boxes", boxes(row), "fixture", scope)
    finish = done(saved)
    finish.package = PackageInput(length_cm=12, width_cm=8, height_cm=4, gross_weight_g=123)
    completed = svc.command(row.id, "done", finish, "fixture", scope)
    request = ReboxCommand(
        **boxes(completed, 3, reason="尾箱重新装箱").model_dump(),
        expected_box_version=completed.box_set.version,
        reason_category="box_capacity",
    )
    result = svc.command(row.id, "rebox", request, "warehouse", scope)
    assert result.status == "packed" and result.box_set.total_qty == 3
    assert result.box_set.completed_at == completed.box_set.completed_at
    assert result.box_set.package_snapshot == completed.box_set.package_snapshot
    assert result.variance_case.quantity == 2 and result.variance_case.state == "pending"
    event = svc.events(row.id, scope, 1, 20).items[0]
    assert event.kind == "rebox" and event.before["box_set"]["total_qty"] == 5
    assert svc.command(row.id, "rebox", request, "warehouse", scope).version == result.version
    restore = ReboxCommand(
        **boxes(result, 5, reason="补齐尾箱装箱").model_dump(),
        expected_box_version=result.box_set.version,
    )
    restored = svc.command(row.id, "rebox", restore, "warehouse", scope)
    assert restored.variance_case.state == "resolved" and restored.box_set.total_qty == 5
    assert restored.box_set.completed_at == completed.box_set.completed_at

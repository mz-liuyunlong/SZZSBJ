"""G3-F: manual SKU cycle overrides — append-only writes, validation, idempotency and the
DWS rebuild they trigger (SQLite end-to-end), plus route auth/OpenAPI checks."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.core.auth import Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.integration_sync.dependencies import get_source_account_scope_provider
from app.modules.pmc_purchase.gate3_models import (
    DwdPurchaseOrder,
    DwsPurchaseBoard,
    ManualPurchaseCycleOverride,
)
from app.modules.pmc_purchase.overrides import PmcPurchaseOverrideService
from app.modules.pmc_purchase.refresh import PmcPurchaseDwsRefresher
from app.modules.pmc_purchase.schemas import CycleOverrideRequest
from tests.modules.pmc_purchase.test_refresh import (
    ACCOUNT,
    NOW,
    TODAY,
    _line,
    _order,
    _plan,
    _receipt,
    _receipt_run,
    session,  # noqa: F401  (fixture re-export)
)

SCOPE = frozenset({ACCOUNT})
PATH = "/api/pmc/purchase/sku-cycles/SKU-A/overrides"


@pytest.fixture
def seeded(session: Session) -> Session:  # noqa: F811
    """SKU-A: five arrived orders with cycles 10, 12, 30 (outlier), 14, 11 → avg 15.4."""

    _plan(session, "P1")
    run = _receipt_run(session)
    for sn, day, cycle in (
        ("PO1", 1, 10),
        ("PO2", 3, 12),
        ("PO3", 5, 30),
        ("PO4", 7, 14),
        ("PO5", 9, 11),
    ):
        ordered = date(2026, 8, day)
        _order(session, sn, order_date=ordered, quantity_total=10)
        _line(session, sn, f"L-{sn}", quantity_allocated=10, quantity_plan=10, quantity_real=10)
        arrived = ordered + timedelta(days=cycle)
        _receipt(session, run, f"R-{sn}", f"L-{sn}", f"{arrived} 08:00:00", 10)
    # open order whose S3 threshold follows the SKU cycle
    _order(session, "PO9", order_date=TODAY - timedelta(days=16), quantity_total=10)
    _line(session, "PO9", "L-PO9", quantity_allocated=10, quantity_plan=10, quantity_real=10)
    session.commit()
    PmcPurchaseDwsRefresher(session, now=NOW).refresh(source_account_ref=ACCOUNT, today=TODAY)
    return session


def _svc(db: Session) -> PmcPurchaseOverrideService:
    return PmcPurchaseOverrideService(db, now=NOW, today=TODAY)


def _req(**kw: Any) -> CycleOverrideRequest:
    base: dict[str, Any] = {"source_account_ref": ACCOUNT, "reason": "供应商临时补单"}
    base.update(kw)
    return CycleOverrideRequest(**base)


def _po9_threshold(db: Session) -> int | None:
    row = db.scalar(select(DwsPurchaseBoard).where(DwsPurchaseBoard.order_sn == "PO9"))
    assert row is not None
    return row.threshold_days


def test_exclude_then_restore_rewrites_dws_and_keeps_history(seeded: Session) -> None:
    assert _po9_threshold(seeded) == 15  # 15.4 rounded

    out = _svc(seeded).apply(
        sku="SKU-A",
        payload=_req(kind="exclude", purchase_order_sn="PO3"),
        accounts=SCOPE,
        actor_ref="rocky",
        request_id="req-1",
    )
    assert out.idempotent_replay is False and out.replaced_override_id is None
    assert out.override.kind == "exclude" and out.override.operator_ref == "rocky"
    assert out.override.before["value_days"] == "15.4000"
    assert out.override.before["sample"]["purchase_order_sn"] == "PO3"
    assert out.override.request_id == "req-1" and out.override.is_active
    assert out.sku_cycle is not None
    assert out.sku_cycle.value_days == Decimal("11.7500")  # (10+12+14+11)/4
    by_sn = {s.purchase_order_sn: s for s in out.sku_cycle.samples}
    assert by_sn["PO3"].exclusion == "manual" and by_sn["PO3"].used is False
    assert _po9_threshold(seeded) == 12  # stage threshold follows the new cycle
    assert out.refresh_board_rows == 6

    # restore = a newer record, the exclude row stays
    back = _svc(seeded).apply(
        sku="SKU-A",
        payload=_req(kind="restore", purchase_order_sn="PO3", reason="误剔除"),
        accounts=SCOPE,
        actor_ref="rocky",
        request_id="req-2",
    )
    assert back.sku_cycle is not None and back.sku_cycle.value_days == Decimal("15.4000")
    assert seeded.scalar(select(func.count()).select_from(ManualPurchaseCycleOverride)) == 2
    history = _svc(seeded).history(sku="SKU-A", accounts=SCOPE)
    assert [h.kind for h in history.items] == ["restore", "exclude"]
    # DWD untouched
    assert seeded.scalar(select(func.count()).select_from(DwdPurchaseOrder)) == 6


def test_arrival_date_and_baseline_with_replacement(seeded: Session) -> None:
    svc = _svc(seeded)
    out = svc.apply(
        sku="SKU-A",
        payload=_req(kind="arrival_date", purchase_order_sn="PO3", value_date=date(2026, 8, 18)),
        accounts=SCOPE,
        actor_ref="rocky",
        request_id="req-a",
    )
    assert out.sku_cycle is not None
    by_sn = {s.purchase_order_sn: s for s in out.sku_cycle.samples}
    assert by_sn["PO3"].cycle_days == 13 and by_sn["PO3"].used is True
    assert out.sku_cycle.value_days == Decimal("12.0000")

    first = svc.apply(
        sku="SKU-A",
        payload=_req(kind="baseline", value_days=8, reason="换厂"),
        accounts=SCOPE,
        actor_ref="rocky",
        request_id="req-b1",
    )
    assert first.replaced_override_id is None
    assert first.sku_cycle is not None and first.sku_cycle.source == "baseline_mix"
    assert first.sku_cycle.baseline_days == 8 and first.sku_cycle.baseline_set_on == TODAY
    # all five samples were ordered before the baseline date → only the baseline counts
    assert first.sku_cycle.value_days == Decimal("8.0000")

    second = svc.apply(
        sku="SKU-A",
        payload=_req(kind="baseline", value_days=9, reason="再次修正"),
        accounts=SCOPE,
        actor_ref="rocky",
        request_id="req-b2",
    )
    assert second.replaced_override_id == first.override.id
    closed = seeded.get(ManualPurchaseCycleOverride, first.override.id)
    assert closed is not None and closed.is_active is False and closed.effective_to is not None
    assert second.sku_cycle is not None and second.sku_cycle.baseline_days == 9
    active = [
        r
        for r in seeded.scalars(select(ManualPurchaseCycleOverride))
        if r.kind == "baseline" and r.is_active
    ]
    assert len(active) == 1 and active[0].value_days == 9


def test_idempotent_replay_and_validation_errors(seeded: Session) -> None:
    svc = _svc(seeded)
    first = svc.apply(
        sku="SKU-A",
        payload=_req(kind="exclude", purchase_order_sn="PO3", request_id="client-7"),
        accounts=SCOPE,
        actor_ref="rocky",
        request_id="header-ignored",
    )
    again = svc.apply(
        sku="SKU-A",
        payload=_req(kind="exclude", purchase_order_sn="PO3", request_id="client-7"),
        accounts=SCOPE,
        actor_ref="rocky",
        request_id="header-ignored-2",
    )
    assert again.idempotent_replay is True and again.override.id == first.override.id
    assert seeded.scalar(select(func.count()).select_from(ManualPurchaseCycleOverride)) == 1

    def expect(status: int, reason: str, **kw: Any) -> None:
        with pytest.raises(ApiError) as excinfo:
            svc.apply(
                sku=kw.pop("sku", "SKU-A"),
                payload=_req(**kw),
                accounts=kw.pop("accounts", SCOPE) if "accounts" in kw else SCOPE,
                actor_ref="rocky",
                request_id="req-x",
            )
        assert excinfo.value.status_code == status
        assert reason in (excinfo.value.details.get("reason"), excinfo.value.code)

    expect(422, "PURCHASE_ORDER_NOT_A_SAMPLE", kind="exclude", purchase_order_sn="PO9")
    expect(422, "PURCHASE_ORDER_NOT_EXCLUDED", kind="restore", purchase_order_sn="PO1")
    expect(
        422,
        "ARRIVAL_DATE_BEFORE_ORDER_DATE",
        kind="arrival_date",
        purchase_order_sn="PO1",
        value_date=date(2026, 7, 1),
    )
    expect(404, "SKU_CYCLE_NOT_FOUND", kind="baseline", value_days=5, sku="SKU-NOPE")
    with pytest.raises(ApiError) as denied:
        svc.apply(
            sku="SKU-A",
            payload=_req(kind="baseline", value_days=5, source_account_ref="other"),
            accounts=SCOPE,
            actor_ref="rocky",
            request_id="req-y",
        )
    assert denied.value.status_code == 403

    # schema-level shape rules
    for bad in (
        {"kind": "exclude"},
        {"kind": "baseline"},
        {"kind": "baseline", "value_days": 5, "purchase_order_sn": "PO1"},
        {"kind": "arrival_date", "purchase_order_sn": "PO1"},
        {"kind": "exclude", "purchase_order_sn": "PO1", "reason": "   "},
    ):
        with pytest.raises(ValueError):
            _req(**bad)


# --- routes -------------------------------------------------------------------------------------


def _app(*permissions: str) -> Any:
    application = create_app()
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user", permissions=frozenset(permissions)
    )
    application.dependency_overrides[get_source_account_scope_provider] = lambda: (
        lambda _principal: frozenset({"synthetic-account"})
    )
    application.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    return application


def test_override_routes_openapi_and_permissions(monkeypatch: Any) -> None:
    schema = create_app().openapi()
    path = schema["paths"]["/api/pmc/purchase/sku-cycles/{sku}/overrides"]
    assert path["post"]["operationId"] == "createPmcPurchaseSkuCycleOverride"
    assert path["get"]["operationId"] == "listPmcPurchaseSkuCycleOverrides"
    assert "201" in path["post"]["responses"]

    body = {
        "source_account_ref": "synthetic-account",
        "kind": "baseline",
        "value_days": 7,
        "reason": "x",
    }
    # read permission alone cannot write
    response = TestClient(_app("pmc:purchase:read")).post(PATH, json=body)
    assert response.status_code == 403 and response.json()["error"]["code"] == "FORBIDDEN"
    # the preview principal (auth.py) never carries the override permission
    from app.core.auth import _PREVIEW_PERMISSIONS

    assert "pmc:purchase:override" not in _PREVIEW_PERMISSIONS
    # write permission + service delegation → 201 envelope
    captured: dict[str, Any] = {}

    def fake_apply(self: Any, **kw: Any) -> Any:
        captured.update(kw)
        from app.modules.pmc_purchase.schemas import CycleOverrideMutationData, CycleOverrideRead

        return CycleOverrideMutationData(
            override=CycleOverrideRead(
                id="00000000-0000-0000-0000-000000000001",
                source_account_ref="synthetic-account",
                sku="SKU-A",
                kind="baseline",
                purchase_order_sn=None,
                value_days=7,
                value_date=None,
                before={},
                after={"kind": "baseline", "value_days": 7},
                reason="x",
                operator_ref=kw["actor_ref"],
                request_id=kw["request_id"],
                effective_from=NOW,
                effective_to=None,
                is_active=True,
                created_at=NOW,
            ),
            replaced_override_id=None,
            idempotent_replay=False,
            sku_cycle=None,
            refresh_board_rows=0,
        )

    monkeypatch.setattr(PmcPurchaseOverrideService, "apply", fake_apply)
    response = TestClient(_app("pmc:purchase:override")).post(
        PATH, json=body, headers={"X-Request-ID": "req-123"}
    )
    assert response.status_code == 201
    payload = response.json()
    assert (
        payload["success"] is True
        and payload["data"]["override"]["operator_ref"] == "synthetic-user"
    )
    assert captured["request_id"] == "req-123" and captured["sku"] == "SKU-A"
    assert payload["meta"]["source_objects"] == [
        "manual_purchase_cycle_override",
        "dws_purchase_sku_cycle",
    ]
    # invalid body shape → 422 envelope
    response = TestClient(_app("pmc:purchase:override")).post(
        PATH, json={"source_account_ref": "synthetic-account", "kind": "exclude", "reason": "x"}
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_ERROR"

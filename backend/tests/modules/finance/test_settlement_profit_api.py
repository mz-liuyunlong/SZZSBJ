"""Settlement profit API on PostgreSQL (opt-in, synthetic fixtures only).

Covers PRP §14 PR-4: permissions, data scope (store / owner), ``__unmapped__`` visibility,
idempotency, optimistic lock, error codes, field permissions, close / reopen.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.finance.settlement_profit import access as acc
from app.modules.finance.settlement_profit.access import ScopeGrants, load_scope_grants
from app.modules.finance.settlement_profit.inputs import Adjustment, FlowMovement, ReviewAction
from app.modules.finance.settlement_profit.keys import UNMAPPED_STORE_ID
from app.modules.finance.settlement_profit.router import get_recalculator
from app.modules.finance.settlement_profit.service import recalculate_month
from app.modules.finance.settlement_profit_models import (
    SETTLEMENT_PROFIT_TABLES,
    SettlementMonthClose,
    SettlementOrderAdjustment,
    SettlementOrderLine,
    SettlementOrderReview,
    SettlementReconcileStoreMonth,
    SettlementReviewAction,
    SettlementWriteLog,
)
from tests.db.domestic_postgresql_support import admin_url, create_database, drop_database
from tests.db.test_domestic_chain_postgresql import _alembic

from .settlement_fixtures import MONTH, RATE, base_input, movement

BASE = "/api/finance/settlement-profit"
M = "2030-01"
STORE_A, STORE_B = "store-a", "store-b"
NOW = datetime(2030, 2, 10, tzinfo=UTC)
ALL_FIELDS = {acc.FIELD_COST, acc.FIELD_NET_PROFIT, acc.FIELD_COMPANY_COST}


@dataclass(frozen=True)
class Persona:
    user_id: str
    permissions: frozenset[str]
    stores: frozenset[str] = frozenset({"*"})
    owners: frozenset[str] = frozenset()


LEAD = Persona(
    "101",
    frozenset({acc.VIEW, *acc.FINANCE_ACTIONS, *ALL_FIELDS}),
)
CLERK = Persona(
    "102", frozenset({acc.VIEW, acc.ADJUST, acc.REVIEW_FIRST, acc.FIELD_COST, acc.FIELD_NET_PROFIT})
)
LEAD_2 = Persona("103", LEAD.permissions)
MANAGEMENT = Persona("104", frozenset({acc.VIEW}))
STORE_CLERK = Persona(
    "105", frozenset({acc.VIEW, acc.ADJUST, acc.REVIEW_FIRST}), stores=frozenset({STORE_A})
)
OWNER_X = Persona("106", frozenset({acc.VIEW, acc.FIELD_NET_PROFIT}), owners=frozenset({"owner-x"}))
NO_SCOPE = Persona("107", frozenset({acc.VIEW}), stores=frozenset())
NO_VIEW = Persona("108", frozenset({acc.ADJUST}))


# ------------------------------------------------------------------ database + loader


@pytest.fixture(scope="module")
def engine() -> Iterator[sa.Engine]:
    url = admin_url()  # skips unless DOMESTIC_CHAIN_DB_TESTS=1
    database = create_database(url, "finsettleapi")
    try:
        up = _alembic(url, database, "head")
        assert up.returncode == 0, up.stderr
        eng = sa.create_engine(url.set(database=database), hide_parameters=True)
        yield eng
        eng.dispose()
    finally:
        drop_database(url, database)


@dataclass
class DbLoader:
    """Synthetic sources; manual adjustments and reviews are read back from the database."""

    session: Session
    rate: D | None = RATE
    unmapped: list[FlowMovement] = field(default_factory=list)
    owners: dict[str, str | None] = field(
        default_factory=lambda: {"I1": "owner-x", "I2": "owner-y"}
    )

    def store_ids(self, bill_month: date) -> list[str]:
        return [STORE_A, STORE_B]

    def fx_rate(self, bill_month: date) -> D | None:
        return self.rate

    def unmapped_movements(self, bill_month: date) -> list[FlowMovement]:
        return list(self.unmapped)

    def adjustments(self, store_id: str, bill_month: date) -> list[Adjustment]:
        rows = self.session.execute(
            sa.select(SettlementOrderAdjustment).where(
                SettlementOrderAdjustment.store_id == store_id,
                SettlementOrderAdjustment.bill_month == bill_month,
                SettlementOrderAdjustment.status == "active",
            )
        ).scalars()
        return [Adjustment(str(a.id), a.line_key, a.kind, a.payload, a.acted_at) for a in rows]

    def load_store_month(self, store_id: str, bill_month: date, assigned_movements):
        inp = base_input(store_id=store_id, fx_rate=self.rate, owner_by_item=dict(self.owners))
        inp.movements = list(assigned_movements)
        inp.adjustments = self.adjustments(store_id, bill_month)
        for a in self.session.execute(
            sa.select(SettlementOrderAdjustment).where(
                SettlementOrderAdjustment.store_id == store_id,
                SettlementOrderAdjustment.bill_month == bill_month,
            )
        ).scalars():
            changed = max(a.acted_at, a.revoked_at or a.acted_at)
            prev = inp.adjustment_changed_at.get(a.line_key)
            inp.adjustment_changed_at[a.line_key] = max(prev, changed) if prev else changed
        inp.review_actions = [
            ReviewAction(r.line_key, r.stage, r.decision, r.acted_at)
            for r in self.session.execute(
                sa.select(SettlementReviewAction).where(
                    SettlementReviewAction.store_id == store_id,
                    SettlementReviewAction.bill_month == bill_month,
                )
            ).scalars()
        ]
        return inp

    def company_cost_cny(self, bill_month: date) -> D | None:
        return None


@dataclass
class World:
    engine: sa.Engine
    loader_options: dict[str, Any] = field(default_factory=dict)
    persona: Persona = LEAD

    def loader(self, session: Session) -> DbLoader:
        return DbLoader(session, **self.loader_options)

    def recalc(self, session: Session, bill_month: date, store_ids: list[str]) -> str:
        recalculate_month(session, self.loader(session), bill_month, now=NOW)
        return "done"

    def db(self) -> Session:
        return Session(self.engine)


def _reset(engine: sa.Engine) -> None:
    tables = ", ".join((*SETTLEMENT_PROFIT_TABLES, "manual_settlement_write_log"))
    with engine.begin() as conn:
        conn.execute(sa.text(f"TRUNCATE {tables} CASCADE"))


def _seed(world: World) -> None:
    _reset(world.engine)
    with world.db() as s:
        recalculate_month(s, world.loader(s), MONTH, now=NOW)
        s.commit()


@pytest.fixture
def world(engine: sa.Engine) -> World:
    w = World(engine, {"unmapped": [movement("LIQ", store_id=None, row_hash="u-1")]})
    _seed(w)
    return w


@pytest.fixture
def client(world: World) -> Iterator[TestClient]:
    app = create_app()

    def db() -> Iterator[Session]:
        s = world.db()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id=world.persona.user_id, permissions=world.persona.permissions
    )
    app.dependency_overrides[load_scope_grants] = lambda: ScopeGrants(
        world.persona.stores, world.persona.owners
    )
    app.dependency_overrides[get_db_session] = db
    app.dependency_overrides[get_recalculator] = lambda: world.recalc
    with TestClient(app) as c:
        yield c


def as_(world: World, persona: Persona) -> None:
    world.persona = persona


def key() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4())}


def order_rows(client: TestClient, **params: Any) -> list[dict[str, Any]]:
    res = client.get(f"{BASE}/orders", params={"months": M, "page_size": 200, **params})
    assert res.status_code == 200, res.text
    return res.json()["data"]["rows"]


def first_order(client: TestClient, store: str = STORE_A) -> dict[str, Any]:
    return next(r for r in order_rows(client, store_ids=store) if r["row_kind"] == "order")


def unmapped_row(client: TestClient) -> dict[str, Any]:
    return next(r for r in order_rows(client) if r["store_id"] == UNMAPPED_STORE_ID)


def error(res) -> str:
    return res.json()["error"]["code"]


# ------------------------------------------------------------------ permissions + scope


def test_page_permission_and_store_scope_are_required(world: World, client: TestClient) -> None:
    as_(world, NO_VIEW)
    assert client.get(f"{BASE}/summary").status_code == 403
    as_(world, NO_SCOPE)
    res = client.get(f"{BASE}/summary")
    assert res.status_code == 403 and error(res) == "DATA_SCOPE_DENIED"
    as_(world, MANAGEMENT)
    line = first_order(client)
    res = client.post(
        f"{BASE}/orders/{line['line_id']}/adjustments",
        json={"kind": "note", "reason": "r", "expected_version": line["version"]},
        headers=key(),
    )
    assert res.status_code == 403 and error(res) == "FORBIDDEN"
    assert client.get(f"{BASE}/config/net-profit", params={"month": M}).status_code == 403
    as_(world, CLERK)
    res = client.post(
        f"{BASE}/months/{M}/close",
        json={"store_ids": "ALL", "confirm_token": f"CLOSE {M}"},
        headers=key(),
    )
    assert res.status_code == 403
    res = client.post(
        f"{BASE}/orders/review",
        json={
            "line_ids": [line["line_id"]],
            "stage": "final",
            "decision": "pass",
            "expected_versions": {line["line_id"]: line["version"]},
        },
        headers=key(),
    )
    assert res.status_code == 403


def test_unmapped_never_in_store_list_or_filters(world: World, client: TestClient) -> None:
    as_(world, LEAD)
    stores = client.get(f"{BASE}/stores", params={"months": M}).json()["data"]["rows"]
    assert [s["store_id"] for s in stores] == [STORE_A, STORE_B]
    for path in ("summary", "orders", "inventory", "reconcile"):
        res = client.get(f"{BASE}/{path}", params={"months": M, "store_ids": UNMAPPED_STORE_ID})
        assert res.status_code == 422, path
        assert error(res) == "VALIDATION_ERROR"
    summary = client.get(f"{BASE}/summary", params={"months": M, "view": "store"}).json()
    assert {r["key"]["store_id"] for r in summary["data"]["rows"]} == {STORE_A, STORE_B}
    reconcile = client.get(f"{BASE}/reconcile", params={"months": M}).json()["data"]["rows"]
    assert {r["store_id"] for r in reconcile} == {STORE_A, STORE_B}
    detail = client.get(f"{BASE}/items/{UNMAPPED_STORE_ID}/I1", params={"months": M})
    assert detail.status_code == 404
    # a store filter never brings 未对上店铺 rows along
    assert all(r["store_id"] == STORE_A for r in order_rows(client, store_ids=STORE_A))


@pytest.mark.parametrize(
    ("persona", "visible"),
    [
        (LEAD, True),
        (CLERK, True),
        (MANAGEMENT, False),  # all stores but not finance
        (STORE_CLERK, False),  # finance but not all stores
        (OWNER_X, False),
    ],
)
def test_unmapped_rows_only_for_all_store_finance(
    world: World, client: TestClient, persona: Persona, visible: bool
) -> None:
    as_(world, persona)
    rows = [r for r in order_rows(client) if r["store_id"] == UNMAPPED_STORE_ID]
    assert bool(rows) is visible
    if visible:
        assert rows[0]["store_label"] == "未对上店铺"
        assert rows[0]["reasons"] == ["unmapped_store"]
    adjustments = client.get(f"{BASE}/adjustments", params={"months": M}).json()["data"]["rows"]
    assert all(a["store_id"] != UNMAPPED_STORE_ID for a in adjustments) or visible


def test_unmapped_row_not_writable_outside_all_store_finance(
    world: World, client: TestClient
) -> None:
    as_(world, LEAD)
    todo = unmapped_row(client)
    as_(world, STORE_CLERK)
    res = client.post(
        f"{BASE}/orders/{todo['line_id']}/adjustments",
        json={
            "kind": "assign_store",
            "payload": {"store_id": STORE_A},
            "reason": "r",
            "expected_version": todo["version"],
        },
        headers=key(),
    )
    assert res.status_code == 404


def test_store_scope_and_owner_scope(world: World, client: TestClient) -> None:
    as_(world, STORE_CLERK)
    assert {r["store_id"] for r in order_rows(client)} == {STORE_A}
    res = client.get(f"{BASE}/orders", params={"store_ids": STORE_B})
    assert res.status_code == 403
    assert client.get(f"{BASE}/items/{STORE_B}/I1", params={"months": M}).status_code == 404
    stores = client.get(f"{BASE}/stores").json()["data"]["rows"]
    assert [s["store_id"] for s in stores] == [STORE_A]

    as_(world, OWNER_X)
    summary = client.get(f"{BASE}/summary", params={"months": M}).json()["data"]
    assert {r["key"]["item_id"] for r in summary["rows"]} == {"I1"}
    assert all(r["owner_ref"] == "owner-x" for r in order_rows(client))
    assert client.get(f"{BASE}/items/{STORE_A}/I2", params={"months": M}).status_code == 404
    assert client.get(f"{BASE}/items/{STORE_A}/I1", params={"months": M}).status_code == 200
    assert client.get(f"{BASE}/reconcile", params={"months": M}).status_code == 403


def test_field_permissions_hide_cost_and_net_profit(world: World, client: TestClient) -> None:
    as_(world, MANAGEMENT)
    row = client.get(f"{BASE}/summary", params={"months": M}).json()["data"]["rows"][0]
    assert "goods_cost" not in row and "net_profit" not in row
    order = first_order(client)
    assert "costs" not in order and "net_profit_share" not in order
    as_(world, LEAD)
    row = client.get(f"{BASE}/summary", params={"months": M}).json()["data"]["rows"][0]
    assert "goods_cost" in row and "net_profit" in row
    order = first_order(client)
    assert order["costs"]["purchase_cost_cny"]["currency_code"] == "CNY"


def test_read_envelope_meta_and_money_pairs(world: World, client: TestClient) -> None:
    as_(world, LEAD)
    body = client.get(f"{BASE}/summary", params={"months": M, "view": "item"}).json()
    assert body["success"] is True
    assert body["meta"]["source"] == "finance_settlement_profit_v2"
    assert body["meta"]["calc_version"] == 1
    sales = body["data"]["rows"][0]["sales"]
    assert set(sales) == {"amount", "currency_code"} and isinstance(sales["amount"], str)
    res = client.get(f"{BASE}/orders", params={"page_size": 201})
    assert res.status_code == 422
    res = client.get(f"{BASE}/orders", params={"sort_by": "drop table"})
    assert res.status_code == 422
    res = client.get(f"{BASE}/summary", params={"months": "2030/01"})
    assert res.status_code == 422


# ------------------------------------------------------------------ adjustments


def test_adjustment_idempotent_replay_conflict_and_stale_version(
    world: World, client: TestClient
) -> None:
    as_(world, CLERK)
    line = first_order(client)
    body = {
        "kind": "amount",
        "payload": {"column": "sales_amount_usd", "delta": "1.5", "currency": "USD"},
        "reason": "合成调整",
        "expected_version": line["version"],
    }
    headers = key()
    url = f"{BASE}/orders/{line['line_id']}/adjustments"
    first = client.post(url, json=body, headers=headers)
    assert first.status_code == 200, first.text
    data = first.json()["data"]
    # +1 for the adjustment, +1 again when the recalculation changes the line's amounts
    assert data["line"]["version"] == line["version"] + 2
    assert data["line"]["status"] == "adjusted"
    assert data["adjustment"]["payload"] == {"column": "sales_amount_usd", "delta_usd": "1.5"}
    assert data["recalc"]["status"] == "done"
    assert first.json()["meta"]["idempotent_replay"] is False

    again = client.post(url, json=body, headers=headers)
    assert again.status_code == 200
    assert again.json()["data"] == data
    assert again.json()["meta"]["idempotent_replay"] is True

    changed = client.post(url, json={**body, "reason": "另一个原因"}, headers=headers)
    assert changed.status_code == 409 and error(changed) == "IDEMPOTENCY_CONFLICT"

    stale = client.post(url, json=body, headers=key())
    assert stale.status_code == 409 and error(stale) == "STALE_VERSION"
    assert stale.json()["error"]["details"]["current_version"] == data["line"]["version"]

    with world.db() as s:
        adjustments = s.execute(sa.select(SettlementOrderAdjustment)).scalars().all()
        assert len(adjustments) == 1
        a = adjustments[0]
        assert (a.actor_id, a.actor_role) == ("102", "finance")
        assert a.request_id and a.before["line"]["version"] == line["version"]
        assert a.after["line"]["version"] == data["line"]["version"]
        logs = s.execute(sa.select(SettlementWriteLog)).scalars().all()
        assert len(logs) == 1 and logs[0].reason == "合成调整"
        # recalculated: the adjusted order line carries the delta in the new version
        recalced = s.execute(
            sa.select(SettlementOrderLine)
            .where(SettlementOrderLine.line_key == a.line_key)
            .order_by(SettlementOrderLine.calc_version.desc())
            .limit(1)
        ).scalar_one()
        assert recalced.calc_version == 2

    # 24 h later the same key is refused instead of replayed
    with world.db() as s:
        s.execute(
            sa.update(SettlementWriteLog).values(acted_at=datetime.now(UTC) - timedelta(hours=25))
        )
        s.commit()
    expired = client.post(url, json=body, headers=headers)
    assert expired.status_code == 409 and error(expired) == "IDEMPOTENCY_KEY_EXPIRED"


def test_idempotency_key_is_per_actor(world: World, client: TestClient) -> None:
    as_(world, CLERK)
    line = first_order(client)
    headers = key()
    body = {"kind": "note", "reason": "r", "expected_version": line["version"]}
    url = f"{BASE}/orders/{line['line_id']}/adjustments"
    assert client.post(url, json=body, headers=headers).status_code == 200
    as_(world, LEAD)  # same key from someone else is not their replay
    res = client.post(url, json={**body, "expected_version": line["version"] + 1}, headers=headers)
    assert res.status_code == 409 and error(res) == "IDEMPOTENCY_CONFLICT"


@pytest.mark.parametrize(
    ("target", "body"),
    [
        ("unmapped", {"kind": "cost", "payload": {"purchase_cny": "1"}}),
        ("order", {"kind": "amount", "payload": {"column": "storage_fee_usd", "delta": "1"}}),
        ("order", {"kind": "amount", "payload": {"column": "sales_amount_usd", "delta": "0"}}),
        (
            "order",
            {
                "kind": "amount",
                "payload": {"column": "sales_amount_usd", "delta": "1", "currency": "CNY"},
            },
        ),
        ("order", {"kind": "cost", "payload": {"purchase_cny": "-1"}}),
        ("order", {"kind": "cost", "payload": {"purchase_cny": "1", "x": 1}}),
        ("order", {"kind": "assign_store", "payload": {"store_id": STORE_A}}),
        ("order", {"kind": "assign_item", "payload": {"item_id": "I1"}}),
        ("unmapped", {"kind": "assign_store", "payload": {"store_id": UNMAPPED_STORE_ID}}),
        ("unmapped", {"kind": "assign_store", "payload": {"store_id": "no-such-store"}}),
        ("unmapped", {"kind": "assign_item", "payload": {"item_id": "I1"}}),
    ],
)
def test_adjustment_validation(
    world: World, client: TestClient, target: str, body: dict[str, Any]
) -> None:
    as_(world, LEAD)
    line = first_order(client) if target == "order" else unmapped_row(client)
    res = client.post(
        f"{BASE}/orders/{line['line_id']}/adjustments",
        json={**body, "reason": "r", "expected_version": line["version"]},
        headers=key(),
    )
    assert res.status_code == 422, res.text
    with world.db() as s:
        assert s.execute(sa.select(sa.func.count(SettlementWriteLog.id))).scalar_one() == 0


def test_write_requires_key_reason_and_cost_field(world: World, client: TestClient) -> None:
    as_(world, STORE_CLERK)  # no cost field permission
    line = first_order(client)
    url = f"{BASE}/orders/{line['line_id']}/adjustments"
    body = {"kind": "note", "reason": "r", "expected_version": line["version"]}
    assert client.post(url, json=body).status_code == 422  # no Idempotency-Key
    assert client.post(url, json={**body, "reason": ""}, headers=key()).status_code == 422
    res = client.post(
        url,
        json={**body, "kind": "cost", "payload": {"purchase_cny": "1"}},
        headers=key(),
    )
    assert res.status_code == 403
    missing = client.post(f"{BASE}/orders/{uuid4()}/adjustments", json=body, headers=key())
    assert missing.status_code == 404


# ------------------------------------------------------------------ review + revoke


def review(client: TestClient, lines, stage: str, decision: str = "pass", **extra: Any):
    return client.post(
        f"{BASE}/orders/review",
        json={
            "line_ids": [line["line_id"] for line in lines],
            "stage": stage,
            "decision": decision,
            "expected_versions": {line["line_id"]: line["version"] for line in lines},
            **extra,
        },
        headers=key(),
    )


def test_review_stages_reviewers_and_reject(world: World, client: TestClient) -> None:
    as_(world, LEAD)
    a, b = [r for r in order_rows(client, store_ids=STORE_A) if r["row_kind"] == "order"][:2]
    res = review(client, [a], "final")
    assert res.json()["data"]["results"][0]["code"] == "STAGE_ORDER"

    as_(world, CLERK)
    res = review(client, [a], "first")
    result = res.json()["data"]["results"][0]
    assert result["ok"] and result["status"] == "first_passed"
    assert result["version"] == a["version"] + 1

    as_(world, LEAD)
    first_again = review(client, [{**a, "version": result["version"]}], "first")
    assert first_again.json()["data"]["results"][0]["code"] == "STAGE_ORDER"
    stale = review(client, [a], "final")
    assert stale.json()["data"]["results"][0]["code"] == "STALE_VERSION"
    final = review(client, [{**a, "version": result["version"]}], "final")
    assert final.json()["data"]["results"][0]["status"] == "final_passed"

    # the same person cannot both first-review and final-review one line
    res = review(client, [b], "first")
    b_version = res.json()["data"]["results"][0]["version"]
    same = review(client, [{**b, "version": b_version}], "final")
    assert same.json()["data"]["results"][0]["code"] == "SAME_REVIEWER"

    # reject needs a reason and goes back a step
    as_(world, LEAD_2)
    assert review(client, [{**b, "version": b_version}], "final", "reject").status_code == 422
    rejected = review(client, [{**b, "version": b_version}], "final", "reject", comment="缺凭证")
    assert rejected.json()["data"]["results"][0]["status"] == "rejected"

    # 待指定 rows and unknown ids are reported per line, not as a failed batch
    todo = unmapped_row(client)
    mixed = review(client, [todo, {"line_id": str(uuid4()), "version": 1}], "first")
    codes = [r["code"] for r in mixed.json()["data"]["results"]]
    assert codes == ["NOT_REVIEWABLE", "NOT_FOUND"]
    with world.db() as s:
        actions = s.execute(sa.select(SettlementReviewAction)).scalars().all()
        assert {(x.stage, x.decision) for x in actions} == {
            ("first", "pass"),
            ("final", "pass"),
            ("final", "reject"),
        }
        assert all(x.actor_id and x.request_id and x.before for x in actions)


def test_batch_review_of_20_lines_needs_confirm_token(world: World, client: TestClient) -> None:
    as_(world, CLERK)
    lines = [{"line_id": str(uuid4()), "version": 1} for _ in range(20)]
    res = review(client, lines, "first")
    assert res.status_code == 422 and error(res) == "CONFIRM_TOKEN_MISMATCH"
    ok = review(client, lines, "first", confirm_token="REVIEW 20")
    assert ok.status_code == 200 and ok.json()["data"]["failed"] == 20
    too_many = review(client, [{"line_id": str(uuid4()), "version": 1}] * 501, "first")
    assert too_many.status_code == 422


def test_revoke_returns_line_to_first_review(world: World, client: TestClient) -> None:
    as_(world, CLERK)
    line = first_order(client)
    made = client.post(
        f"{BASE}/orders/{line['line_id']}/adjustments",
        json={"kind": "note", "reason": "r", "expected_version": line["version"]},
        headers=key(),
    ).json()["data"]
    adj = made["adjustment"]
    url = f"{BASE}/adjustments/{adj['id']}/revoke"
    stale = client.post(url, json={"reason": "x", "expected_version": 99}, headers=key())
    assert stale.status_code == 409 and error(stale) == "STALE_VERSION"
    res = client.post(url, json={"reason": "录错了", "expected_version": 1}, headers=key())
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["adjustment"]["status"] == "revoked"
    assert data["adjustment"]["revoke_reason"] == "录错了"
    assert data["line"]["status"] == "pending"
    again = client.post(url, json={"reason": "x", "expected_version": 2}, headers=key())
    assert again.status_code == 409 and error(again) == "ALREADY_REVOKED"
    ledger = client.get(f"{BASE}/adjustments", params={"status": "revoked"}).json()["data"]
    assert [r["id"] for r in ledger["rows"]] == [adj["id"]]


# ------------------------------------------------------------------ close / reopen


def close(client: TestClient, stores: Any = "ALL", token: str = f"CLOSE {M}"):
    return client.post(
        f"{BASE}/months/{M}/close",
        json={"store_ids": stores, "confirm_token": token},
        headers=key(),
    )


def test_close_blocked_by_unmapped_then_assign_close_and_reopen(
    world: World, client: TestClient
) -> None:
    as_(world, LEAD)
    res = close(client, token="CLOSE 2030-02")
    assert res.status_code == 422 and error(res) == "CONFIRM_TOKEN_MISMATCH"
    blocked = close(client)
    assert blocked.status_code == 409 and error(blocked) == "UNASSIGNED_PENDING"
    assert set(blocked.json()["error"]["details"]["blockers"]) == {STORE_A, STORE_B}
    assert close(client, [UNMAPPED_STORE_ID]).status_code == 422

    todo = unmapped_row(client)
    assigned = client.post(
        f"{BASE}/orders/{todo['line_id']}/adjustments",
        json={
            "kind": "assign_store",
            "payload": {"store_id": STORE_A},
            "reason": "按库存流水店铺代码确认",
            "expected_version": todo["version"],
        },
        headers=key(),
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["data"]["recalc"]["store_ids"] == [STORE_A]

    closed = close(client)
    assert closed.status_code == 200, closed.text
    rows = closed.json()["data"]["rows"]
    assert [(r["store_id"], r["status"]) for r in rows] == [
        (STORE_A, "closed"),
        (STORE_B, "closed"),
    ]
    assert rows[0]["snapshot_totals"]["sales"]["currency_code"] == "USD"
    with world.db() as s:
        assert (
            s.execute(
                sa.select(sa.func.count())
                .select_from(SettlementOrderLine)
                .where(SettlementOrderLine.frozen_at.is_(None))
                .where(
                    SettlementOrderLine.calc_version
                    == sa.select(sa.func.max(SettlementReconcileStoreMonth.calc_version))
                    .where(SettlementReconcileStoreMonth.store_id == SettlementOrderLine.store_id)
                    .scalar_subquery()
                )
            ).scalar_one()
            == 0
        )
        assert s.execute(sa.select(sa.func.count(SettlementMonthClose.id))).scalar_one() == 2

    # closed month: writes are refused
    line = first_order(client)
    res = client.post(
        f"{BASE}/orders/{line['line_id']}/adjustments",
        json={"kind": "note", "reason": "r", "expected_version": line["version"]},
        headers=key(),
    )
    assert res.status_code == 409 and error(res) == "MONTH_CLOSED"
    as_(world, CLERK)
    assert review(client, [line], "first").json()["data"]["results"][0]["code"] == "MONTH_CLOSED"
    as_(world, LEAD)
    config = client.put(
        f"{BASE}/config/net-profit",
        json={
            "effective_month": M,
            "fixed_cny": "15000",
            "excluded_owner_ids": [],
            "expected_version": 0,
            "confirm_token": f"CONFIG {M}",
        },
        headers=key(),
    )
    assert config.status_code == 409 and error(config) == "MONTH_CLOSED"
    again = close(client, [STORE_A])
    assert again.status_code == 409 and error(again) == "ALREADY_CLOSED"

    reopen_url = f"{BASE}/months/{M}/reopen"
    body = {"store_ids": [STORE_A], "reason": "补录调整", "confirm_token": f"REOPEN {M}"}
    assert client.post(reopen_url, json={**body, "reason": ""}, headers=key()).status_code == 422
    wrong = client.post(reopen_url, json={**body, "confirm_token": f"CLOSE {M}"}, headers=key())
    assert wrong.status_code == 422
    reopened = client.post(reopen_url, json=body, headers=key())
    assert reopened.status_code == 200, reopened.text
    out = reopened.json()["data"]
    assert out["rows"][0]["status"] == "reopened"
    assert out["rows"][0]["reopen_reason"] == "补录调整"
    assert out["recalc"]["status"] == "done"
    not_closed = client.post(reopen_url, json=body, headers=key())
    assert not_closed.status_code == 409 and error(not_closed) == "NOT_CLOSED"
    with world.db() as s:
        frozen_a = s.execute(
            sa.select(sa.func.count())
            .select_from(SettlementOrderLine)
            .where(
                SettlementOrderLine.store_id == STORE_A, SettlementOrderLine.frozen_at.isnot(None)
            )
        ).scalar_one()
        assert frozen_a == 0
        log = s.execute(
            sa.select(SettlementWriteLog).where(
                SettlementWriteLog.endpoint == "POST /months/{month}/reopen"
            )
        ).scalar_one()
        assert log.before[STORE_A]["status"] == "closed" and log.reason == "补录调整"


@pytest.mark.parametrize(
    ("options", "code"),
    [
        ({"rate": None}, "FX_MISSING"),
        ({"owners": {"I1": "owner-x", "I2": None}}, "OWNER_MISSING"),
    ],
)
def test_close_blockers(
    world: World, client: TestClient, options: dict[str, Any], code: str
) -> None:
    world.loader_options = options
    _seed(world)
    as_(world, LEAD)
    res = close(client)
    assert res.status_code == 409
    assert code in res.json()["error"]["details"]["blockers"][STORE_A]
    with world.db() as s:
        assert s.execute(sa.select(sa.func.count(SettlementMonthClose.id))).scalar_one() == 0


# ------------------------------------------------------------------ 纯利设置


def test_net_profit_config_versioned_update(world: World, client: TestClient) -> None:
    as_(world, LEAD)
    url = f"{BASE}/config/net-profit"
    default = client.get(url, params={"month": M}).json()["data"]
    assert default["is_default"] and default["version"] == 0
    assert default["fixed_cny"] == {"amount": "15000.0000", "currency_code": "CNY"}
    body = {
        "effective_month": M,
        "fixed_cny": "12000",
        "excluded_owner_ids": ["owner-y"],
        "expected_version": 0,
        "reason": "合成设置",
        "confirm_token": f"CONFIG {M}",
    }
    assert (
        client.put(url, json={**body, "confirm_token": "CONFIG"}, headers=key()).status_code == 422
    )
    res = client.put(url, json=body, headers=key())
    assert res.status_code == 200, res.text
    assert res.json()["data"]["config"]["version"] == 1
    stale = client.put(url, json=body, headers=key())
    assert stale.status_code == 409 and error(stale) == "STALE_VERSION"
    later = client.get(url, params={"month": "2030-03"}).json()["data"]
    assert later["effective_month"] == M and later["excluded_owner_ids"] == ["owner-y"]
    bad = client.put(url, json={**body, "fixed_cny": "-1", "expected_version": 1}, headers=key())
    assert bad.status_code == 422
    as_(world, CLERK)
    assert client.put(url, json={**body, "expected_version": 1}, headers=key()).status_code == 403
    with world.db() as s:
        log = s.execute(
            sa.select(SettlementWriteLog).where(
                SettlementWriteLog.endpoint == "PUT /config/net-profit"
            )
        ).scalar_one()
        assert log.before is None and log.after["version"] == 1
        assert log.actor_role == "finance_lead"
    with world.db() as s:  # review rows untouched by a config write
        assert s.execute(sa.select(sa.func.count(SettlementOrderReview.id))).scalar_one() > 0

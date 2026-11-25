"""结算利润 V3 建表（PR-1）在真实 PostgreSQL 上的约束检查（没配测试库就跳过）。全部合成数据。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import Settings, SettingsError, get_test_database_url
from app.modules.settlement_profit.models import (
    SettlementCostEntry,
    SettlementMonthClose,
    SettlementOrderLine,
    SettlementReviewAction,
    SettlementSetting,
    SettlementStoreMonthItem,
)

STORE = "100000000000000001"
MONTH = date(2026, 10, 1)
NOW = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)


@pytest.fixture
def session() -> Iterator[Session]:
    try:
        url = get_test_database_url(Settings())  # type: ignore[call-arg]
    except (SettingsError, ValidationError):
        pytest.skip("isolated PostgreSQL test database is not configured")
    engine = create_engine(url, poolclass=NullPool, hide_parameters=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
            yield db
        transaction.rollback()
    engine.dispose()


def _rejected(session: Session, row: Any) -> None:
    savepoint = session.begin_nested()
    session.add(row)
    with pytest.raises(IntegrityError):
        session.flush()
    savepoint.rollback()


def _entry(**overrides: Any) -> SettlementCostEntry:
    values: dict[str, Any] = {
        "id": uuid4(),
        "store_id": STORE,
        "msku": "MSKU-SYN-1",
        "shipping_list_code": "SP-SYN-0001",
        "scope_ref": "shipping:SP-SYN-0001",
        "purchase_cny": Decimal("10.0000"),
        "head_cny": Decimal("2.0000"),
        "entry_kind": "confirm",
        "actor_id": "user-syn-1",
        "actor_role": "finance_clerk",
    }
    values.update(overrides)
    return SettlementCostEntry(**values)


def _order_line(**overrides: Any) -> SettlementOrderLine:
    values: dict[str, Any] = {
        "id": uuid4(),
        "source_account_ref": "primary",
        "store_id": STORE,
        "period_key": "rk-synthetic-1020",
        "bill_month": MONTH,
        "line_key": f"{STORE}|rk-synthetic-1020|PO-SYN-1|1|00000000000001",
        "line_kind": "sale",
        "fulfillment_type": "wfs",
        "platform_order_no": "PO-SYN-1",
        "order_line_no": "1",
        "calc_version": 1,
        "content_hash": "0" * 64,
    }
    values.update(overrides)
    return SettlementOrderLine(**values)


def test_order_line_defaults_and_versions(session: Session) -> None:
    session.add(_order_line())
    session.add(_order_line(id=uuid4(), calc_version=2, content_hash="1" * 64))
    session.flush()
    rows = session.scalars(select(SettlementOrderLine).order_by(SettlementOrderLine.calc_version))
    first = next(iter(rows))
    session.refresh(first)
    assert first.fx_status == "missing" and first.fx_rate is None
    assert first.sales_usd == Decimal("0") and first.reasons == [] and first.is_current
    _rejected(session, _order_line(id=uuid4()))  # 同店同期同版本同 line_key


def test_month_columns_must_be_first_day(session: Session) -> None:
    _rejected(session, _order_line(bill_month=date(2026, 10, 2)))
    _rejected(
        session,
        SettlementSetting(
            id=uuid4(),
            setting_key="no_order_months",
            effective_month=date(2026, 10, 5),
            value={"months": 1},
            updated_by="user-syn-1",
        ),
    )


def test_vocabularies_are_enforced(session: Session) -> None:
    _rejected(session, _order_line(fx_status="guess"))
    _rejected(session, _order_line(line_kind="other"))
    _rejected(
        session,
        SettlementSetting(
            id=uuid4(),
            setting_key="not_a_setting",
            effective_month=MONTH,
            value={},
            updated_by="user-syn-1",
        ),
    )
    _rejected(
        session,
        SettlementStoreMonthItem(
            id=uuid4(),
            store_id=STORE,
            bill_month=MONTH,
            source_kind="inventory_movement",
            source_ref="ref-1",
            line_key="k",
            calc_version=1,
            content_hash="0" * 64,
        ),
    )


def test_cost_entry_scope_override_and_single_active(session: Session) -> None:
    _rejected(session, _entry(shipping_list_code=None))  # 两种范围都没有
    _rejected(session, _entry(outbound_order_no="OB-SYN-1"))  # 两种范围都有
    _rejected(session, _entry(entry_kind="override", reason=None))  # 修正必须写原因
    first = _entry()
    session.add(first)
    session.flush()
    _rejected(session, _entry())  # 同一范围已有未撤销的录入
    first.status = "revoked"
    session.flush()
    session.add(_entry())  # 撤销后可以重录
    session.flush()


def test_reject_needs_comment_and_unlock_needs_reason(session: Session) -> None:
    common = {"store_id": STORE, "bill_month": MONTH, "actor_id": "u", "actor_role": "r"}
    _rejected(
        session,
        SettlementReviewAction(
            id=uuid4(),
            target_kind="order_line",
            line_key="k",
            stage="first",
            decision="reject",
            **common,
        ),
    )
    _rejected(session, SettlementMonthClose(id=uuid4(), seq=2, action="unlock", **common))
    session.add(SettlementMonthClose(id=uuid4(), seq=1, action="close", **common))
    session.flush()
    _rejected(session, SettlementMonthClose(id=uuid4(), seq=1, action="close", **common))

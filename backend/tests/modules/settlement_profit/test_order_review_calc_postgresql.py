"""订单审核计算的数据库层：版本翻转、审核行状态、结账跳过。合成数据；没配隔离库就跳过。

成本计价流水表带两个外键（运行、原始页），这里不造那两层，把 flow_segments 换成内存实现；
流水表本身的读写由 #369 的测试覆盖。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import Settings, SettingsError, get_test_database_url
from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.fx_rates.models import LingxingFxRate
from app.modules.settlement_profit.models import (
    FinShippingDetailItem,
    FinShippingList,
    OwnerTagRule,
    SettlementCostEntry,
    SettlementMonthClose,
    SettlementOrderLine,
    SettlementOrderReview,
    SettlementSetting,
)
from app.modules.settlement_profit.order_review import calc as calc_module
from app.modules.settlement_profit.order_review.calc import (
    DbLookups,
    OrderReviewCalculator,
    load_settings,
    periods_for_recalc,
)
from app.modules.settlement_profit.order_review.rules import FlowSegment
from app.modules.walmart_bills.models import WalmartBillLine, WalmartBillPeriod

NOW = datetime(2026, 11, 20, 2, 0, tzinfo=UTC)
ACCOUNT = "primary"
STORE = "990000000000000001"
ORDER = "900000000000000001"
GTIN = "00000000000001"
ITEM = "30000000001"
MSKU = "SYN-001"
CODE = "SP2026T0001"
PERIOD = "2026-11-03"
REPORT = date(2026, 11, 3)


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


FLOWS: dict[str, list[FlowSegment]] = {}
# 打桩前留一份真实实现，给「只取出库方向」的 SQL 断言用
ORIGINAL_FLOW_SEGMENTS = DbLookups.flow_segments


@pytest.fixture(autouse=True)
def fake_flows(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    FLOWS.clear()

    def flow_segments(self: DbLookups, order_nos: Any, gtin: str | None) -> list[FlowSegment]:
        del gtin
        out: list[FlowSegment] = []
        for number in dict.fromkeys(order_nos):
            out.extend(FLOWS.get(number, []))
        return out

    monkeypatch.setattr(calc_module.DbLookups, "flow_segments", flow_segments)
    yield


def seed_period(session: Session, *, report_key: str = PERIOD, report_date: date = REPORT) -> None:
    session.add(
        WalmartBillPeriod(
            source_account_ref=ACCOUNT,
            store_id=STORE,
            report_key=report_key,
            report_date=report_date,
            line_count=1,
            excluded_line_count=0,
            amount_sum=Decimal(0),
            payable_amount=Decimal(0),
            status="normal",
            refreshed_at=NOW,
        )
    )


def seed_bill(
    session: Session,
    rows: list[tuple[str, str, str, str, int | None]],
    *,
    report_key: str = PERIOD,
    report_date: date = REPORT,
    fulfillment: str = "Walmart-fulfilled(WFS)",
    order: str = ORDER,
) -> None:
    for index, (ttype, desc, atype, amount, qty) in enumerate(rows):
        session.add(
            WalmartBillLine(
                source_account_ref=ACCOUNT,
                store_id=STORE,
                line_key=f"{report_key}-{order}-{index}",
                lx_line_id=f"{index}",
                report_key=report_key,
                report_date=report_date,
                posted_at=datetime(2026, 10, 20, 12, 0),
                posted_date=date(2026, 10, 20),
                transaction_type=ttype,
                transaction_description=desc,
                amount_type=atype,
                amount=Decimal(amount),
                currency_code="USD",
                ship_qty=qty,
                customer_order_no=order,
                customer_order_line_no="1",
                purchase_order_no=order,
                purchase_order_line_no="1",
                partner_gtin=GTIN,
                partner_item_id=ITEM,
                fulfillment_type=fulfillment,
                delete_flag=0,
                row_hash=f"h{report_key}{index}",
                first_seen_at=NOW,
                last_seen_at=NOW,
            )
        )


SALE = [
    ("Sale", "Purchase", "Product Price", "20.00", 1),
    ("Sale", "Purchase", "Commission on Product", "-3.00", 1),
    ("Adjustment", "WFS Fulfillment fee", "Fee/Reimbursement", "-4.00", None),
]


def seed_shipment(session: Session, *, purchase: str = "3.00", total: str = "6.50") -> None:
    session.add(
        FinShippingList(
            source_account_ref=ACCOUNT,
            store_id=STORE,
            shipping_list_code=CODE,
            shipping_list_status="2",
            logistics_provider_id="1234",
            logistics_provider_name="合成物流商",
            synced_at=NOW,
            row_hash="0" * 64,
            raw_row={},
        )
    )
    session.add(
        FinShippingDetailItem(
            source_account_ref=ACCOUNT,
            store_id=STORE,
            shipping_list_code=CODE,
            msku=MSKU,
            purchase_price=Decimal(purchase),
            head_stock_price=Decimal("1.50"),
            per_firstlet_cost=Decimal("2.00"),
            per_tax=Decimal("0"),
            wfs_stock_price=Decimal(total),
            currency_code="CNY",
            logistics_way="合成-卡派",
            synced_at=NOW,
            row_hash="1" * 64,
            raw_row={},
        )
    )


def seed_listing(
    session: Session, *, owner: str | None = "owner-a", tags: list[Any] | None = None
) -> None:
    session.add(
        ListingManagementCurrentMart(
            source_account_ref=ACCOUNT,
            store_id=STORE,
            item_id=ITEM,
            msku=MSKU,
            owner_ref=owner,
            tags_json=tags or [],
            calculated_at=NOW,
        )
    )


def seed_fx(session: Session) -> None:
    session.add(
        LingxingFxRate(
            rate_month="2026-11", currency_code="USD", my_rate=Decimal("7.2"), source="seed"
        )
    )


def seed_settings(session: Session) -> None:
    session.add(
        SettlementSetting(
            setting_key="wfs_carrier_provider_ids",
            effective_month=date(2026, 1, 1),
            value={"provider_ids": ["6899"]},
            updated_by="tester",
        )
    )


def flow(qty: int = 1) -> FlowSegment:
    return FlowSegment(
        cost_source=f"shipment:{CODE}",
        msku=MSKU,
        gtin=GTIN,
        quantity=Decimal(qty),
        business_number="7600000001",
        purchase_total=Decimal("-3"),
        logistics_total=Decimal("-3.5"),
        other_total=Decimal("0"),
        currency_code="CNY",
        row_hash="a" * 64,
    )


def seed_all(session: Session) -> None:
    seed_period(session)
    seed_bill(session, SALE)
    seed_shipment(session)
    seed_listing(session)
    seed_fx(session)
    seed_settings(session)
    FLOWS[ORDER] = [flow()]
    session.flush()


def current_lines(session: Session) -> list[SettlementOrderLine]:
    session.expire_all()
    return list(
        session.scalars(
            select(SettlementOrderLine)
            .where(SettlementOrderLine.is_current.is_(True))
            .order_by(SettlementOrderLine.line_key)
        ).all()
    )


def test_settings_default_to_unconfigured_carrier_list(session: Session) -> None:
    cfg = load_settings(session, bill_month=date(2026, 10, 1))
    assert cfg.wfs_carrier_provider_ids is None
    assert cfg.bill_month_cutoff_day == 5
    seed_settings(session)
    session.add(
        SettlementSetting(
            setting_key="bill_month_cutoff_day",
            effective_month=date(2026, 1, 1),
            value={"day": 7},
            updated_by="tester",
        )
    )
    session.flush()
    cfg = load_settings(session, bill_month=date(2026, 10, 1))
    assert cfg.wfs_carrier_provider_ids == frozenset({"6899"})
    assert cfg.bill_month_cutoff_day == 7


def test_recalc_writes_fact_and_review_and_skips_unchanged(session: Session) -> None:
    seed_all(session)
    calculator = OrderReviewCalculator(session, source_account_ref=ACCOUNT)
    result = calculator.recalc_period(STORE, PERIOD, run_ids=["run-1"])
    assert (result.status, result.lines_total, result.lines_new_version) == ("calculated", 1, 1)
    assert (result.auto_passed, result.pending, result.calc_version) == (1, 0, 1)

    lines = current_lines(session)
    assert len(lines) == 1
    line = lines[0]
    assert line.bill_month == date(2026, 10, 1)
    assert (line.sales_usd, line.commission_usd, line.wfs_fulfillment_fee_usd) == (
        Decimal("20"),
        Decimal("-3"),
        Decimal("-4"),
    )
    assert (line.purchase_cny, line.head_cny, line.cost_total_cny) == (
        Decimal("3"),
        Decimal("3.5"),
        Decimal("6.5"),
    )
    assert line.cost_total_usd == Decimal("0.9028")
    assert line.owner_id == "owner-a"
    assert line.auto_passed is True
    assert line.source_run_ids == ["run-1"]
    review = session.scalars(select(SettlementOrderReview)).one()
    assert (review.review_status, review.version, review.row_kind) == ("auto", 1, "order")
    assert review.line_key == line.line_key

    # 同一输入重算：不写新版本
    again = calculator.recalc_period(STORE, PERIOD)
    assert (again.lines_new_version, again.lines_unchanged, again.calc_version) == (0, 1, 1)
    assert session.scalar(select(func.count()).select_from(SettlementOrderLine)) == 1


def test_changed_input_flips_old_version_and_keeps_manual_review(session: Session) -> None:
    seed_all(session)
    calculator = OrderReviewCalculator(session, source_account_ref=ACCOUNT)
    calculator.recalc_period(STORE, PERIOD)
    review = session.scalars(select(SettlementOrderReview)).one()
    review.review_status = "first_passed"
    review.first_reviewed_by = "tester"
    session.flush()

    detail = session.scalars(select(FinShippingDetailItem)).one()
    detail.purchase_price = Decimal("3.10")
    detail.wfs_stock_price = Decimal("6.60")
    session.flush()
    result = calculator.recalc_period(STORE, PERIOD)
    assert (result.lines_new_version, result.calc_version) == (1, 2)
    rows = session.scalars(
        select(SettlementOrderLine).order_by(SettlementOrderLine.calc_version)
    ).all()
    assert [(r.calc_version, r.is_current) for r in rows] == [(1, False), (2, True)]
    assert rows[1].purchase_cny == Decimal("3.1")
    session.refresh(review)
    assert review.review_status == "first_passed"  # 已初审的行不自动改
    assert review.version == 2  # 计算值变了，版本 +1
    assert review.cost_total_cny == Decimal("6.6")
    assert "changed_after_review" in review.reasons  # 差异提示（§8.4）
    # 再算一次内容没变：提示保留，版本不动
    calculator.recalc_period(STORE, PERIOD)
    session.refresh(review)
    assert "changed_after_review" in review.reasons
    assert review.version == 2


def test_line_gone_from_bill_is_retired(session: Session) -> None:
    seed_all(session)
    calculator = OrderReviewCalculator(session, source_account_ref=ACCOUNT)
    calculator.recalc_period(STORE, PERIOD)
    for row in session.scalars(select(WalmartBillLine)).all():
        row.missing_since = NOW
    session.flush()
    result = calculator.recalc_period(STORE, PERIOD)
    assert (result.lines_total, result.lines_retired) == (0, 1)
    assert current_lines(session) == []
    assert session.scalar(select(func.count()).select_from(SettlementOrderReview)) == 0


def test_pending_reason_and_owner_from_tag_rule(session: Session) -> None:
    seed_period(session)
    seed_bill(session, SALE)
    seed_shipment(session)
    seed_listing(session, owner=None, tags=[{"name": "合成标签"}])
    seed_fx(session)
    session.add(OwnerTagRule(tag_name="合成标签", owner_id="owner-tag", updated_by="tester"))
    FLOWS[ORDER] = [flow()]
    session.flush()
    # 承运商清单没配置 → wfs_carrier_shipment 待审
    result = OrderReviewCalculator(session, source_account_ref=ACCOUNT).recalc_period(STORE, PERIOD)
    assert (result.auto_passed, result.pending) == (0, 1)
    line = current_lines(session)[0]
    assert line.reasons == ["wfs_carrier_shipment"]
    assert line.owner_id == "owner-tag"
    review = session.scalars(select(SettlementOrderReview)).one()
    assert review.review_status == "pending"


def test_cost_entry_is_picked_up_on_recalc(session: Session) -> None:
    seed_all(session)
    session.add(
        SettlementSetting(
            setting_key="wfs_carrier_provider_ids",
            effective_month=date(2026, 2, 1),
            value={"provider_ids": ["1234"]},
            updated_by="tester",
        )
    )
    session.flush()
    calculator = OrderReviewCalculator(session, source_account_ref=ACCOUNT)
    calculator.recalc_period(STORE, PERIOD)
    assert current_lines(session)[0].reasons == ["wfs_carrier_shipment"]
    session.add(
        SettlementCostEntry(
            store_id=STORE,
            msku=MSKU,
            shipping_list_code=CODE,
            scope_ref=f"shipping:{CODE}",
            purchase_cny=Decimal("3"),
            head_cny=Decimal("3.5"),
            entry_kind="confirm",
            actor_id="tester",
            actor_role="finance",
            idempotency_key="idem-1",
        )
    )
    session.flush()
    result = calculator.recalc_period(STORE, PERIOD)
    line = current_lines(session)[0]
    assert line.reasons == []
    assert len(line.cost_entry_ids) == 1
    # 人工录入的段不自动通过：留在待审，等初审 / 终审（#373 复审 P1）
    assert line.auto_passed is False
    assert (result.auto_passed, result.pending, result.calc_version) == (0, 1, 2)


def test_closed_month_is_skipped(session: Session) -> None:
    seed_all(session)
    session.add(
        SettlementMonthClose(
            store_id=STORE,
            bill_month=date(2026, 10, 1),
            seq=1,
            action="close",
            actor_id="tester",
            actor_role="finance",
        )
    )
    session.flush()
    result = OrderReviewCalculator(session, source_account_ref=ACCOUNT).recalc_period(STORE, PERIOD)
    assert result.status == "skipped_closed"
    assert current_lines(session) == []
    assert (
        OrderReviewCalculator(session, source_account_ref=ACCOUNT)
        .recalc_period(STORE, "missing")
        .status
        == "no_period"
    )


def test_refund_in_later_period_reverses_the_original_line(session: Session) -> None:
    seed_all(session)
    later = "2026-11-17"
    seed_period(session, report_key=later, report_date=date(2026, 11, 17))
    seed_bill(
        session,
        [
            ("Refund", "Return Refund", "Product Price", "-20.00", 1),
            ("Refund", "Return Refund", "Commission on Product", "3.00", 1),
        ],
        report_key=later,
        report_date=date(2026, 11, 17),
    )
    session.flush()
    calculator = OrderReviewCalculator(session, source_account_ref=ACCOUNT)
    calculator.recalc_period(STORE, PERIOD)
    calculator.recalc_period(STORE, later)
    refund = next(line for line in current_lines(session) if line.period_key == later)
    assert refund.line_kind == "refund"
    assert refund.quantity == Decimal("-1")
    assert refund.cost_total_cny == Decimal("-6.5")
    assert refund.auto_passed is True


def test_flow_lookup_only_takes_outbound_rows() -> None:
    """流水表全类型入库：退货入库行（quantity > 0）带同一个订单号，不能当成发货段。"""
    from sqlalchemy.dialects import postgresql

    captured: list[str] = []

    class Empty:
        def all(self) -> list[Any]:
            return []

    class Capture:
        def scalars(self, statement: Any) -> Empty:
            captured.append(str(statement.compile(dialect=postgresql.dialect())))
            return Empty()

    lookups = DbLookups.__new__(DbLookups)
    lookups.session = Capture()  # type: ignore[assignment]
    lookups.account = ACCOUNT
    lookups.store_id = STORE
    assert ORIGINAL_FLOW_SEGMENTS(lookups, [ORDER], GTIN) == []
    assert captured and "ods_lingxing_wfs_cost_valuation_flow.quantity < " in captured[0]
    assert "is_current IS true" in captured[0]


def test_periods_for_recalc_defaults_to_october_onwards(session: Session) -> None:
    seed_period(session, report_key="2026-09-22", report_date=date(2026, 9, 22))
    seed_period(session)
    session.flush()
    assert periods_for_recalc(session, source_account_ref=ACCOUNT) == [(STORE, PERIOD)]
    assert periods_for_recalc(session, source_account_ref=ACCOUNT, store_ids=["x"]) == []
    assert (
        len(
            periods_for_recalc(
                session, source_account_ref=ACCOUNT, report_date_from=date(2026, 9, 1)
            )
        )
        == 2
    )

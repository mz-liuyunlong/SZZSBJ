"""订单审核服务层：期列表、订单行查询、录成本 / 撤销、初审 / 终审 / 退回。合成数据。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
import test_order_review_calc_postgresql as base
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.settlement_profit.models import (
    SettlementCostEntry,
    SettlementMonthClose,
    SettlementOrderReview,
    SettlementReviewAction,
    SettlementSetting,
)
from app.modules.settlement_profit.order_review import service
from app.modules.settlement_profit.order_review.calc import OrderReviewCalculator
from app.modules.settlement_profit.order_review.schemas import (
    CostEntryCreate,
    CostEntryRevoke,
    CostEntryScope,
    RecalcRequest,
    ReviewRequest,
)

session = base.session  # fixture re-export
fake_flows = base.fake_flows
STORE, PERIOD, MSKU, CODE = base.STORE, base.PERIOD, base.MSKU, base.CODE


def prepare_pending(session: Session) -> SettlementOrderReview:
    """承运商清单把 1234 列为 WFS → 行待审（wfs_carrier_shipment）。"""
    base.seed_all(session)
    session.add(
        SettlementSetting(
            setting_key="wfs_carrier_provider_ids",
            effective_month=date(2026, 2, 1),
            value={"provider_ids": ["1234"]},
            updated_by="tester",
        )
    )
    session.flush()
    OrderReviewCalculator(session, source_account_ref=base.ACCOUNT).recalc_period(STORE, PERIOD)
    review = session.scalars(select(SettlementOrderReview)).one()
    assert review.review_status == "pending"
    return review


def entry_payload(**overrides: object) -> CostEntryCreate:
    values: dict[str, object] = {
        "store_id": STORE,
        "scope": CostEntryScope(msku=MSKU, shipping_list_code=CODE),
        "entry_kind": "confirm",
        "purchase_cny": Decimal("3"),
        "head_cny": Decimal("3.5"),
    }
    values.update(overrides)
    return CostEntryCreate.model_validate(values)


def test_periods_and_lines_listing(session: Session) -> None:
    prepare_pending(session)
    periods = service.list_periods(session)
    assert len(periods) == 1
    assert (periods[0].pending_count, periods[0].auto_count, periods[0].calc_version) == (1, 0, 1)
    assert periods[0].bill_month == date(2026, 10, 1)

    rows, total = service.list_lines(
        session, filters=service.LineFilters(period_keys=[PERIOD]), page=1, page_size=50
    )
    assert total == 1
    line = rows[0]
    assert line.review_status == "pending"
    assert line.reasons == ["wfs_carrier_shipment"]
    assert line.sales.amount == "20.0000"
    assert line.cost_total is not None and line.cost_total.amount == "6.5000"
    assert line.profit_usd is not None
    assert line.cost_sources[0].scope_ref == f"shipping:{CODE}"

    _, filtered = service.list_lines(
        session, filters=service.LineFilters(reasons=["cost_missing"]), page=1, page_size=10
    )
    assert filtered == 0
    _, by_type = service.list_lines(
        session,
        filters=service.LineFilters(transaction_types=["Sale|Purchase|Product Price"]),
        page=1,
        page_size=10,
    )
    assert by_type == 1
    _, by_keyword = service.list_lines(
        session, filters=service.LineFilters(keyword=base.ORDER[-6:]), page=1, page_size=10
    )
    assert by_keyword == 1
    with pytest.raises(service.OrderReviewError, match="排序"):
        service.list_lines(
            session, filters=service.LineFilters(), page=1, page_size=10, sort_by="x"
        )

    lookup = service.lookup(session, kind="msku", q="SYN", limit=10)
    assert lookup.items == [MSKU]
    types = service.transaction_types(session)
    assert {t.code for t in types} >= {"Sale|Purchase|Product Price"}
    assert all(t.translated for t in types)


def test_cost_entry_confirm_then_review_flow(session: Session) -> None:
    review = prepare_pending(session)
    result = service.create_cost_entry(
        session,
        entry_payload(),
        actor="u-cost",
        actor_role="cost",
        request_id="r1",
        idempotency_key="idem-1",
    )
    assert (result.affected_lines, result.recalculated_periods, result.replayed) == (1, 1, False)
    assert result.entry.status == "pending_first"
    replay = service.create_cost_entry(
        session,
        entry_payload(),
        actor="u-cost",
        actor_role="cost",
        request_id="r2",
        idempotency_key="idem-1",
    )
    assert replay.replayed is True and replay.entry.id == result.entry.id
    with pytest.raises(service.OrderReviewError, match="先撤销"):
        service.create_cost_entry(
            session,
            entry_payload(),
            actor="u",
            actor_role="c",
            request_id=None,
            idempotency_key=None,
        )

    session.refresh(review)
    line = base.current_lines(session)[0]
    assert line.reasons == [] and line.cost_entry_ids == [str(result.entry.id)]
    # 录入后不自动通过，进初审 / 终审（§8.4；#373 复审 P1）
    assert review.review_status == "pending"
    version_before = review.version  # 录入触发重算，内容变了版本已 +1
    first = service.review_lines(
        session,
        ReviewRequest(review_ids=[review.id], stage="first", decision="pass"),
        actor="u-first",
        actor_role="r1",
        request_id=None,
        idempotency_key="rev-1",
    )
    assert first.items[0].review_status == "first_passed"
    entry = session.get(SettlementCostEntry, result.entry.id)
    assert entry is not None and entry.status == "first_passed"  # 录入记录状态同步
    # 同一个 Idempotency-Key 重放：按当时的记录返回，不再改状态
    replayed = service.review_lines(
        session,
        ReviewRequest(review_ids=[review.id], stage="first", decision="pass"),
        actor="u-first",
        actor_role="r1",
        request_id=None,
        idempotency_key="rev-1",
    )
    assert replayed.items[0].review_status == "first_passed"
    session.refresh(review)
    # 首次初审 +1；同 key 重放不再 +1
    assert review.review_status == "first_passed" and review.version == version_before + 1

    # 撤销录入：已初审的行退回待审、录入记录撤销；同 key 重放返回首次结果
    revoked = service.revoke_cost_entry(
        session,
        result.entry.id,
        CostEntryRevoke(reason="重录", expected_version=1),
        actor="u-cost",
        actor_role="cost",
        request_id=None,
        idempotency_key="revoke-1",
    )
    assert revoked.replayed is False
    session.refresh(review)
    assert review.review_status == "pending"
    again = service.revoke_cost_entry(
        session,
        result.entry.id,
        CostEntryRevoke(reason="重录", expected_version=2),
        actor="u-cost",
        actor_role="cost",
        request_id=None,
        idempotency_key="revoke-1",
    )
    assert again.replayed is True


def test_changed_after_review_filter_and_replay_is_per_actor(session: Session) -> None:
    review = prepare_pending(session)
    service.review_lines(
        session,
        ReviewRequest(review_ids=[review.id], stage="first", decision="pass"),
        actor="u1",
        actor_role="r1",
        request_id=None,
        idempotency_key="same-key",
    )
    # 模拟重算写下的差异提示：它在审核行上，筛选要查审核行（#373 第 2 轮 P3-2）
    review.reasons = [service.CHANGED_AFTER_REVIEW]
    session.flush()
    _, flagged = service.list_lines(
        session,
        filters=service.LineFilters(reasons=[service.CHANGED_AFTER_REVIEW]),
        page=1,
        page_size=10,
    )
    assert flagged == 1
    _, other = service.list_lines(
        session, filters=service.LineFilters(reasons=["cost_missing"]), page=1, page_size=10
    )
    assert other == 0
    # 另一个人用了同一个 key：不当重放，照常终审（重放按 操作人 + key，P3-4）
    final = service.review_lines(
        session,
        ReviewRequest(review_ids=[review.id], stage="final", decision="pass"),
        actor="u2",
        actor_role="r2",
        request_id=None,
        idempotency_key="same-key",
    )
    assert final.items[0].review_status == "final_passed"
    session.refresh(review)
    assert service.CHANGED_AFTER_REVIEW not in review.reasons


def test_review_stage_order_same_reviewer_and_revert(session: Session) -> None:
    review = prepare_pending(session)
    # 待审且没录成本：货本不为空（预填了四项）→ 允许初审
    first = service.review_lines(
        session,
        ReviewRequest(review_ids=[review.id], stage="first", decision="pass"),
        actor="u1",
        actor_role="r1",
        request_id=None,
    )
    assert (first.succeeded, first.items[0].review_status) == (1, "first_passed")
    same = service.review_lines(
        session,
        ReviewRequest(review_ids=[review.id], stage="final", decision="pass"),
        actor="u1",
        actor_role="r2",
        request_id=None,
    )
    assert (same.failed, same.items[0].error_code) == (1, service.ERR_SAME_REVIEWER)
    final = service.review_lines(
        session,
        ReviewRequest(review_ids=[review.id], stage="final", decision="pass"),
        actor="u2",
        actor_role="r2",
        request_id=None,
    )
    assert final.items[0].review_status == "final_passed"
    again = service.review_lines(
        session,
        ReviewRequest(review_ids=[review.id], stage="first", decision="pass"),
        actor="u3",
        actor_role="r1",
        request_id=None,
    )
    assert again.items[0].error_code == service.ERR_STAGE_ORDER
    reverted = service.review_lines(
        session,
        ReviewRequest(review_ids=[review.id], stage="final", decision="revert", comment="x"),
        actor="u2",
        actor_role="r2",
        request_id=None,
    )
    assert reverted.items[0].review_status == "first_passed"
    rejected = service.review_lines(
        session,
        ReviewRequest(review_ids=[review.id], stage="first", decision="reject", comment="不对"),
        actor="u1",
        actor_role="r1",
        request_id=None,
    )
    assert rejected.items[0].review_status == "rejected"
    with pytest.raises(service.OrderReviewError, match="退回必须填原因"):
        service.review_lines(
            session,
            ReviewRequest(review_ids=[review.id], stage="first", decision="reject"),
            actor="u1",
            actor_role="r1",
            request_id=None,
        )
    missing = service.review_lines(
        session,
        ReviewRequest(review_ids=[uuid4()], stage="first", decision="pass"),
        actor="u1",
        actor_role="r1",
        request_id=None,
    )
    assert missing.items[0].error_code == service.ERR_NOT_FOUND
    # ≥ 20 行要 confirm_token（PRP §5）
    many = [uuid4() for _ in range(service.BATCH_CONFIRM_THRESHOLD)]
    with pytest.raises(service.OrderReviewError, match="二次确认"):
        service.review_lines(
            session,
            ReviewRequest(review_ids=many, stage="first", decision="pass"),
            actor="u1",
            actor_role="r1",
            request_id=None,
        )
    confirmed = service.review_lines(
        session,
        ReviewRequest(
            review_ids=many,
            stage="first",
            decision="pass",
            confirm_token=service.BATCH_CONFIRM_TOKEN,
        ),
        actor="u1",
        actor_role="r1",
        request_id=None,
    )
    assert confirmed.failed == len(many)
    actions = session.scalars(
        select(SettlementReviewAction).order_by(SettlementReviewAction.acted_at)
    ).all()
    assert [(a.stage, a.decision) for a in actions] == [
        ("first", "pass"),
        ("final", "pass"),
        ("final", "revert"),
        ("first", "reject"),
    ]
    session.refresh(review)
    assert review.version == 5


def test_closed_month_blocks_writes_and_auto_rows_need_no_review(session: Session) -> None:
    review = prepare_pending(session)
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
    with pytest.raises(service.OrderReviewError, match="已结账"):
        service.create_cost_entry(
            session,
            entry_payload(),
            actor="u",
            actor_role="c",
            request_id=None,
            idempotency_key=None,
        )
    blocked = service.review_lines(
        session,
        ReviewRequest(review_ids=[review.id], stage="first", decision="pass"),
        actor="u1",
        actor_role="r1",
        request_id=None,
    )
    assert blocked.items[0].error_code == service.ERR_MONTH_CLOSED
    assert (
        service.recalc(session, RecalcRequest(store_ids=[STORE])).items[0].status
        == "skipped_closed"
    )


def test_auto_passed_row_cannot_be_reviewed(session: Session) -> None:
    base.seed_all(session)
    OrderReviewCalculator(session, source_account_ref=base.ACCOUNT).recalc_period(STORE, PERIOD)
    review = session.scalars(select(SettlementOrderReview)).one()
    assert review.review_status == "auto"
    result = service.review_lines(
        session,
        ReviewRequest(review_ids=[review.id], stage="first", decision="pass"),
        actor="u1",
        actor_role="r1",
        request_id=None,
    )
    assert result.items[0].error_code == service.ERR_ALREADY_PASSED


def test_override_requires_reason_and_revoke_checks_version(session: Session) -> None:
    prepare_pending(session)
    with pytest.raises(service.OrderReviewError, match="原因"):
        service.create_cost_entry(
            session,
            entry_payload(entry_kind="override"),
            actor="u",
            actor_role="c",
            request_id=None,
            idempotency_key=None,
        )
    created = service.create_cost_entry(
        session,
        entry_payload(entry_kind="override", reason="领星值不对", purchase_cny=Decimal("4")),
        actor="u",
        actor_role="c",
        request_id=None,
        idempotency_key=None,
    )
    assert base.current_lines(session)[0].purchase_cny == Decimal("4")
    with pytest.raises(service.OrderReviewError, match="刷新"):
        service.revoke_cost_entry(
            session,
            created.entry.id,
            CostEntryRevoke(reason="x", expected_version=9),
            actor="u",
            actor_role="c",
            request_id=None,
        )
    entry = session.get(SettlementCostEntry, created.entry.id)
    assert entry is not None and entry.status == "pending_first"

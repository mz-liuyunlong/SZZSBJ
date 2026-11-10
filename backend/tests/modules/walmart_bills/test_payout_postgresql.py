"""回款对账落库：自动 / 合并 / 手动配对、日记账联动、撤销恢复、审核流、收款账户更换。

全部合成数据；没配隔离 PostgreSQL 测试库就跳过。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import Settings, SettingsError, get_test_database_url
from app.modules.finance_cashflow.models import (
    FinanceCashAccount,
    FinanceCashImport,
    FinanceCashLine,
    FinanceCashLineEvent,
    FinanceCashLineState,
    FinanceCashRawFile,
)
from app.modules.walmart_bills.models import WalmartBillPeriod
from app.modules.walmart_bills.payout_models import WalmartPayoutMatch
from app.modules.walmart_bills.payout_schemas import (
    PayoutAccountCreateRequest,
    PayoutAccountUpdateRequest,
    PayoutFollowRequest,
    PayoutManualMatchRequest,
    PayoutReviewRequest,
    PeriodKey,
)
from app.modules.walmart_bills.payout_service import PayoutReconError, PayoutReconService

STORE_A = "900000000000000001"
STORE_B = "900000000000000002"
ACC = "SYN_PP_USD"
ACC_OTHER = "SYN_PY_USD"
TODAY = date(2026, 11, 10)


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


@pytest.fixture
def svc(session: Session) -> PayoutReconService:
    for key, provider in ((ACC, "pingpong"), (ACC_OTHER, "payoneer")):
        session.add(
            FinanceCashAccount(
                account_key=key,
                display_name=f"合成 · {key}",
                entity="合成主体",
                currency_code="USD",
                kind="platform",
                provider=provider,
            )
        )
    session.flush()
    service = PayoutReconService(session)
    service.create_account(
        PayoutAccountCreateRequest(
            store_id=STORE_A, account_key=ACC, payee="", effective_from=date(2026, 10, 1)
        ),
        actor="tester",
    )
    return service


def add_line(
    session: Session, uid: str, day: str, amount: str, account: str = ACC, text: str = ""
) -> None:
    batch = FinanceCashImport(uploader="tester")
    session.add(batch)
    session.flush()
    raw = FinanceCashRawFile(
        import_id=batch.import_id,
        file_name="synthetic.xlsx",
        sha256=uuid4().hex * 2,
        size_bytes=1,
        storage_path="synthetic",
        parser_version="synthetic",
        status="parsed",
    )
    session.add(raw)
    session.flush()
    session.add(
        FinanceCashLine(
            line_uid=uid,
            account_key=account,
            business_date=date.fromisoformat(day),
            source_timezone="Asia/Shanghai",
            amount=Decimal(amount),
            currency_code="USD",
            counterparty_name="合成付款方 Z9",
            description=f"合成到账 Z9 {text}".strip(),
            dup_ordinal=0,
            statement_row_no=1,
            file_row_order=1,
            first_import_id=batch.import_id,
            first_raw_file_id=raw.file_id,
            last_import_id=batch.import_id,
            last_raw_file_id=raw.file_id,
            parser_version="synthetic",
        )
    )
    session.flush()


def add_period(
    session: Session, key: str, day: str, payable: str, store: str = STORE_A, status="normal"
) -> None:
    session.add(
        WalmartBillPeriod(
            source_account_ref="primary",
            store_id=store,
            report_key=key,
            store_name="CN9901-合成店",
            report_date=date.fromisoformat(day),
            currency_code="USD",
            line_count=1,
            excluded_line_count=0,
            amount_sum=Decimal(payable),
            payable_amount=Decimal(payable),
            status=status,
            refreshed_at=datetime.now(UTC),
        )
    )
    session.flush()


def rows_by_key(svc: PayoutReconService):
    return {row.report_key: row for row in svc.list_periods(today=TODAY).items}


def key(report_key: str, store: str = STORE_A) -> PeriodKey:
    return PeriodKey(store_id=store, report_key=report_key)


def test_auto_match_tags_the_journal_and_review_flow(session: Session, svc: PayoutReconService):
    add_period(session, "k1", "2026-10-06", "100.00")
    add_period(session, "k2", "2026-10-20", "60.00")
    add_period(session, "k3", "2026-10-20", "40.00")
    add_period(session, "k4", "2026-10-20", "0", status="not_payable")
    add_line(session, "SYNL000000000001", "2026-10-08", "100.01")
    add_line(session, "SYNL000000000002", "2026-10-22", "100.00")
    before = rows_by_key(svc)
    assert before["k1"].pay_state == "unpaid" and before["k4"].pay_state == "no_pay"
    assert svc.list_periods(today=TODAY).auto_ready == 3

    result = svc.auto_match(actor="tester", request_id="r1")
    assert (result.matched_lines, result.matched_periods) == (2, 3)
    after = rows_by_key(svc)
    assert after["k1"].pay_state == "paid" and after["k1"].diff == Decimal("0.01")
    assert after["k2"].match_size == 2 and after["k2"].match_id == after["k3"].match_id
    assert after["k2"].arrived_amount == Decimal("60.00")

    state = session.get(FinanceCashLineState, "SYNL000000000002")
    assert state.manual_memo == "平台回款 · CN9901 · 2026-10-20"
    assert state.manual_category == "T03"
    kinds = session.scalars(
        select(FinanceCashLineEvent.kind).where(FinanceCashLineEvent.line_uid == "SYNL000000000002")
    ).all()
    assert sorted(kinds) == ["set_category", "set_text"]

    first = svc.review(
        PayoutReviewRequest(kind="review1_pass", periods=[key("k1"), key("k4")]),
        actor="tester",
        request_id=None,
    )
    assert first.done == 1 and [s.report_key for s in first.skipped] == ["k4"]
    with pytest.raises(PayoutReconError):
        svc.review(
            PayoutReviewRequest(kind="review2_reject", periods=[key("k1")]),
            actor="boss",
            request_id=None,
        )
    svc.review(
        PayoutReviewRequest(kind="review2_reject", periods=[key("k1")], reason="合成驳回"),
        actor="boss",
        request_id=None,
    )
    rejected = rows_by_key(svc)["k1"]
    assert (rejected.stage, rejected.stage_reason) == ("rej2", "合成驳回")
    svc.review(
        PayoutReviewRequest(kind="review1_pass", periods=[key("k1")]), actor="t", request_id=None
    )
    svc.review(
        PayoutReviewRequest(kind="review2_pass", periods=[key("k1")]), actor="b", request_id=None
    )
    assert rows_by_key(svc)["k1"].stage == "ok2"
    with pytest.raises(PayoutReconError) as blocked:
        svc.unmatch(after["k1"].match_id, reason="合成", actor="t", request_id=None)
    assert blocked.value.code == "PAYOUT_RECON_STAGE_NOT_ALLOWED"


def test_unmatch_restores_journal_and_manual_match_allows_mismatch(
    session: Session, svc: PayoutReconService
):
    add_period(session, "k1", "2026-10-06", "100.00")
    add_line(session, "SYNL000000000003", "2026-10-07", "100.00")
    add_line(session, "SYNL000000000004", "2026-10-30", "95.00")
    svc.auto_match(actor="tester", request_id=None)
    match_id = rows_by_key(svc)["k1"].match_id
    with pytest.raises(PayoutReconError):
        svc.unmatch(match_id, reason=" ", actor="t", request_id=None)
    svc.unmatch(match_id, reason="合成撤销", actor="t", request_id=None)
    state = session.get(FinanceCashLineState, "SYNL000000000003")
    assert state.manual_memo is None and state.manual_category is None
    assert rows_by_key(svc)["k1"].pay_state == "unpaid"
    undone = session.scalars(select(WalmartPayoutMatch)).one()
    assert undone.undone_by == "t" and undone.undo_reason == "合成撤销"

    made = svc.manual_match(
        PayoutManualMatchRequest(line_uid="SYNL000000000004", periods=[key("k1")]),
        actor="t",
        request_id=None,
    )
    assert made.periods == 1
    row = rows_by_key(svc)["k1"]
    assert (row.pay_state, row.diff, row.anomaly) == ("mismatch", Decimal("-5.00"), True)
    with pytest.raises(PayoutReconError) as dup:
        svc.manual_match(
            PayoutManualMatchRequest(line_uid="SYNL000000000003", periods=[key("k1")]),
            actor="t",
            request_id=None,
        )
    assert dup.value.code == "PAYOUT_RECON_CONFLICT"


def test_user_edited_memo_is_not_overwritten_on_undo(session: Session, svc: PayoutReconService):
    add_period(session, "k1", "2026-10-06", "100.00")
    add_line(session, "SYNL000000000005", "2026-10-07", "100.00")
    svc.auto_match(actor="tester", request_id=None)
    state = session.get(FinanceCashLineState, "SYNL000000000005")
    state.manual_memo = "财务自己改的备注"
    session.flush()
    svc.unmatch(rows_by_key(svc)["k1"].match_id, reason="合成", actor="t", request_id=None)
    assert session.get(FinanceCashLineState, "SYNL000000000005").manual_memo == "财务自己改的备注"


def test_account_change_needs_reason_and_closes_the_old_one(
    session: Session, svc: PayoutReconService
):
    request = PayoutAccountCreateRequest(
        store_id=STORE_A, account_key=ACC_OTHER, payee="", effective_from=date(2026, 11, 1)
    )
    with pytest.raises(PayoutReconError):
        svc.create_account(request, actor="boss")
    svc.create_account(request.model_copy(update={"reason": "合成换户"}), actor="boss")
    items = {row.account_key: row for row in svc.list_accounts().items}
    assert items[ACC].effective_to == date(2026, 10, 31)
    assert items[ACC_OTHER].effective_from == date(2026, 11, 1)
    assert items[ACC_OTHER].org == "派安盈"


def test_follow_ups_are_appended(session: Session, svc: PayoutReconService):
    add_period(session, "k1", "2026-10-06", "100.00")
    for text in ("第一次合成跟进", "第二次合成跟进"):
        svc.follow(
            PayoutFollowRequest(store_id=STORE_A, report_key="k1", content=text, case_no="C-1"),
            actor="t",
            request_id=None,
        )
    row = rows_by_key(svc)["k1"]
    assert row.follow_count == 2 and row.latest_follow.content == "第二次合成跟进"
    detail = svc.period_detail(STORE_A, "k1", today=TODAY)
    assert [f.content for f in detail.follow_ups] == ["第一次合成跟进", "第二次合成跟进"]


def test_other_store_and_september_bills_are_ignored(session: Session, svc: PayoutReconService):
    add_period(session, "k9", "2026-09-22", "100.00")
    add_period(session, "kb", "2026-10-06", "100.00", store=STORE_B)
    add_line(session, "SYNL000000000006", "2026-10-07", "100.00")
    assert "k9" not in rows_by_key(svc)
    assert svc.auto_match(actor="t", request_id=None).matched_periods == 0


def test_voided_arrival_is_not_counted_and_can_be_undone(session: Session, svc: PayoutReconService):
    add_period(session, "k1", "2026-10-06", "100.00")
    add_line(session, "SYNL000000000011", "2026-10-07", "100.00")
    svc.auto_match(actor="t", request_id=None)
    svc.review(
        PayoutReviewRequest(kind="review1_pass", periods=[key("k1")]), actor="t", request_id=None
    )
    session.get(FinanceCashLine, "SYNL000000000011").voided_at = datetime.now(UTC)
    session.flush()
    row = rows_by_key(svc)["k1"]
    assert (row.pay_state, row.anomaly, row.arrival_voided) == ("unpaid", True, True)
    assert row.arrived_amount is None and row.match_id is not None
    final = svc.review(
        PayoutReviewRequest(kind="review2_pass", periods=[key("k1")]), actor="b", request_id=None
    )
    assert final.done == 0 and final.skipped[0].reason == "到账流水已作废，请撤销配对"
    svc.unmatch(row.match_id, reason="流水作废", actor="t", request_id=None)
    after = rows_by_key(svc)["k1"]
    assert (after.match_id, after.stage, after.arrival_voided) == (None, "todo", False)


def test_account_update_keeps_account_and_deactivate_needs_no_live_match(
    session: Session, svc: PayoutReconService
):
    current = svc.list_accounts().items[0]
    with pytest.raises(PayoutReconError) as changed:
        svc.update_account(
            current.id, PayoutAccountUpdateRequest(account_key=ACC_OTHER), actor="boss"
        )
    assert changed.value.status_code == 422
    edited = svc.update_account(
        current.id, PayoutAccountUpdateRequest(account_key=ACC, payee="合成公司"), actor="boss"
    )
    assert (edited.account_key, edited.payee) == (ACC, "合成公司")
    add_period(session, "k1", "2026-10-06", "100.00")
    add_line(session, "SYNL000000000012", "2026-10-07", "100.00", text="合成公司 付款")
    svc.auto_match(actor="t", request_id=None)
    with pytest.raises(PayoutReconError) as blocked:
        svc.deactivate_account(current.id, reason="合成停用", actor="boss")
    assert blocked.value.status_code == 409
    svc.unmatch(rows_by_key(svc)["k1"].match_id, reason="合成", actor="t", request_id=None)
    svc.deactivate_account(current.id, reason="合成停用", actor="boss")
    assert not [row for row in svc.list_accounts().items if row.is_active]


def test_auto_match_skips_lines_already_used_in_the_journal(
    session: Session, svc: PayoutReconService
):
    uses = {
        "SYNL000000000021": {"exclude_amount": Decimal("101"), "exclude_reason": "合成"},
        "SYNL000000000022": {"manual_pair": "SYNPAIR1"},
        "SYNL000000000023": {"parts": [{"amount": "103.0000", "category_code": None}]},
        "SYNL000000000024": {"manual_category": "G01"},
        "SYNL000000000025": {"manual_category": "T03"},
    }
    for index, (uid, fields) in enumerate(uses.items(), start=1):
        amount = f"{100 + index}.00"
        add_period(session, f"k{index}", "2026-10-06", amount)
        add_line(session, uid, "2026-10-07", amount)
        session.add(FinanceCashLineState(line_uid=uid, **fields))
    session.flush()
    result = svc.auto_match(actor="t", request_id=None)
    assert (result.matched_lines, result.matched_periods) == (1, 1)
    assert rows_by_key(svc)["k5"].line_uid == "SYNL000000000025"
    hints = {line.line_uid: line.journal_hint for line in svc.candidate_lines(STORE_A).items}
    assert hints["SYNL000000000021"] == "已剔除"
    assert hints["SYNL000000000022"] == "已内部配对"
    assert hints["SYNL000000000023"] == "已拆分"
    assert hints["SYNL000000000024"].startswith("已分类 ")
    assert hints["SYNL000000000025"] is None
    made = svc.manual_match(
        PayoutManualMatchRequest(line_uid="SYNL000000000024", periods=[key("k4")]),
        actor="t",
        request_id=None,
    )
    assert made.periods == 1


def test_manual_match_rejects_bills_before_recon_start(session: Session, svc: PayoutReconService):
    add_period(session, "k9", "2026-09-22", "100.00")
    add_line(session, "SYNL000000000031", "2026-10-07", "100.00")
    with pytest.raises(PayoutReconError) as early:
        svc.manual_match(
            PayoutManualMatchRequest(line_uid="SYNL000000000031", periods=[key("k9")]),
            actor="t",
            request_id=None,
        )
    assert (early.value.status_code, early.value.code) == (422, "PAYOUT_RECON_INVALID")


TAG = "平台回款 · CN9901 · 2026-10-06"


def matched_with_memo(session: Session, svc: PayoutReconService, uid: str, memo: str) -> str:
    """建一期 + 一笔带人工备注的到账并自动配上，返回 match_id。"""
    add_period(session, "k1", "2026-10-06", "100.00")
    add_line(session, uid, "2026-10-07", "100.00")
    session.add(FinanceCashLineState(line_uid=uid, manual_memo=memo))
    session.flush()
    svc.auto_match(actor="t", request_id=None)
    return str(rows_by_key(svc)["k1"].match_id)


def memo_of(session: Session, uid: str) -> str | None:
    session.expire_all()
    return session.get(FinanceCashLineState, uid).manual_memo


def text_events(session: Session, uid: str) -> int:
    return len(
        session.scalars(
            select(FinanceCashLineEvent).where(
                FinanceCashLineEvent.line_uid == uid, FinanceCashLineEvent.kind == "set_text"
            )
        ).all()
    )


def test_match_appends_to_manual_memo_and_undo_removes_only_the_tag(
    session: Session, svc: PayoutReconService
):
    uid = "SYNL000000000041"
    match_id = matched_with_memo(session, svc, uid, "合成人工备注")
    assert memo_of(session, uid) == f"合成人工备注；{TAG}"
    svc.unmatch(UUID(match_id), reason="合成", actor="t", request_id=None)
    assert memo_of(session, uid) == "合成人工备注"
    assert text_events(session, uid) == 2


def test_undo_after_user_edit_removes_only_the_appended_part(
    session: Session, svc: PayoutReconService
):
    uid = "SYNL000000000042"
    match_id = matched_with_memo(session, svc, uid, "合成人工备注")
    session.get(FinanceCashLineState, uid).manual_memo = f"合成人工备注；{TAG} 财务补充"
    session.flush()
    svc.unmatch(UUID(match_id), reason="合成", actor="t", request_id=None)
    assert memo_of(session, uid) == "合成人工备注 财务补充"


def test_undo_leaves_memo_alone_when_the_tag_is_gone(session: Session, svc: PayoutReconService):
    uid = "SYNL000000000043"
    match_id = matched_with_memo(session, svc, uid, "合成人工备注")
    session.get(FinanceCashLineState, uid).manual_memo = "财务整段重写"
    session.flush()
    svc.unmatch(UUID(match_id), reason="合成", actor="t", request_id=None)
    assert memo_of(session, uid) == "财务整段重写"
    assert text_events(session, uid) == 1


def test_too_long_or_already_tagged_memo_is_not_changed(session: Session, svc: PayoutReconService):
    long_memo = "合" * 490
    uid = "SYNL000000000044"
    match_id = matched_with_memo(session, svc, uid, long_memo)
    assert memo_of(session, uid) == long_memo and text_events(session, uid) == 0
    match = session.scalars(
        select(WalmartPayoutMatch).where(WalmartPayoutMatch.line_uid == uid)
    ).one()
    assert match.memo_set is None and "备注过长，未追加" in (match.note or "")
    svc.unmatch(UUID(match_id), reason="合成", actor="t", request_id=None)
    assert memo_of(session, uid) == long_memo and text_events(session, uid) == 0

    add_period(session, "k2", "2026-10-20", "50.00")
    add_line(session, "SYNL000000000045", "2026-10-21", "50.00")
    tagged = "财务先写了 平台回款 · CN9901 · 2026-10-20"
    session.add(FinanceCashLineState(line_uid="SYNL000000000045", manual_memo=tagged))
    session.flush()
    svc.auto_match(actor="t", request_id=None)
    assert memo_of(session, "SYNL000000000045") == tagged
    assert text_events(session, "SYNL000000000045") == 0

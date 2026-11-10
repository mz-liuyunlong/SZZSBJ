"""回款对账（PR-2）：读期次 + 到账 + 审核 + 跟进；
自动 / 手动配对、撤销、批量审核、跟进、收款账户映射。

规则见 payout_match.py。所有写操作先拿同一把事务级咨询锁，串行执行，避免两个人同时配同一期。
配上之后改日记账（Rocky 11-10）：备注写「平台回款 · 店铺 · 期次」；分类是空的才填「平台回款」；
撤销配对时恢复（备注被人改过就不动）。日记账的改动和日记账页面一样走事件留痕、版本号 +1。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Final, Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.modules.finance_cashflow import journal
from app.modules.finance_cashflow.models import (
    FinanceCashAccount,
    FinanceCashCategory,
    FinanceCashClassifyRule,
    FinanceCashLine,
    FinanceCashLineEvent,
    FinanceCashLineState,
)
from app.modules.walmart_bills import payout_match as rules
from app.modules.walmart_bills.models import WalmartBillPeriod
from app.modules.walmart_bills.payout_models import (
    WalmartPayoutAccount,
    WalmartPayoutFollowUp,
    WalmartPayoutMatch,
    WalmartPayoutReviewEvent,
)
from app.modules.walmart_bills.payout_schemas import (
    PayoutAccountCreateRequest,
    PayoutAccountListData,
    PayoutAccountOption,
    PayoutAccountRead,
    PayoutAccountUpdateRequest,
    PayoutAutoMatchData,
    PayoutFollowRead,
    PayoutFollowRequest,
    PayoutLineListData,
    PayoutLineRead,
    PayoutManualMatchRequest,
    PayoutMatchData,
    PayoutMatchHistoryRead,
    PayoutPeriodDetailData,
    PayoutPeriodListData,
    PayoutPeriodRead,
    PayoutReviewData,
    PayoutReviewEventRead,
    PayoutReviewRequest,
    PayoutReviewSkipped,
    PayoutStoreOption,
)

SHANGHAI: Final = ZoneInfo("Asia/Shanghai")
# 回款对账从 2026-10 起（Rocky 11-10：历史先补 10 月起，之前的以后再说）。
RECON_START: Final = date(2026, 10, 1)
SOURCE_REF: Final = "primary"
MAX_ROWS: Final = 2000
PLATFORM_CATEGORY: Final = "T03"  # 日记账类别「平台回款」
JOURNAL_SOURCE: Final = "payout_recon"
# 所有回款对账写操作共用的咨询锁编号（任意固定值，只在本模块用）。
LOCK_ID: Final = 7_202_611_100
ORG_BY_PROVIDER: Final = {"payoneer": "派安盈", "pingpong": "PingPong"}

ERR_NOT_FOUND: Final = "PAYOUT_RECON_NOT_FOUND"
ERR_CONFLICT: Final = "PAYOUT_RECON_CONFLICT"
ERR_INVALID: Final = "PAYOUT_RECON_INVALID"
ERR_STAGE: Final = "PAYOUT_RECON_STAGE_NOT_ALLOWED"


class PayoutReconError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


Key = tuple[str, str]  # (store_id, report_key)


def store_code(store_name: str | None, store_id: str) -> str:
    """店铺名形如「CN9901-xxx」，取横杠前的编号；没有店铺名就显示店铺 ID。"""
    name = (store_name or "").strip()
    return name.split("-", 1)[0].strip() or store_id if name else store_id


def today_shanghai() -> date:
    return datetime.now(SHANGHAI).date()


@dataclass
class _Group:
    match_id: UUID
    line_uid: str
    method: str
    keys: list[Key]


class PayoutReconService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------ 读

    def _periods(
        self,
        *,
        date_from: date | None,
        date_to: date | None,
        store_id: str | None,
        limit: int = MAX_ROWS,
    ) -> tuple[list[WalmartBillPeriod], bool]:
        query = select(WalmartBillPeriod).where(
            WalmartBillPeriod.source_account_ref == SOURCE_REF,
            WalmartBillPeriod.report_date >= max(date_from or RECON_START, RECON_START),
        )
        if date_to is not None:
            query = query.where(WalmartBillPeriod.report_date <= date_to)
        if store_id is not None:
            query = query.where(WalmartBillPeriod.store_id == store_id)
        query = query.order_by(
            WalmartBillPeriod.report_date.desc(), WalmartBillPeriod.store_id
        ).limit(limit + 1)
        rows = list(self.session.scalars(query))
        return rows[:limit], len(rows) > limit

    def _active_matches(self) -> list[WalmartPayoutMatch]:
        return list(
            self.session.scalars(
                select(WalmartPayoutMatch)
                .where(
                    WalmartPayoutMatch.undone_at.is_(None),
                    WalmartPayoutMatch.source_account_ref == SOURCE_REF,
                )
                .order_by(WalmartPayoutMatch.match_id, WalmartPayoutMatch.seq)
            )
        )

    def _accounts(self) -> dict[str, FinanceCashAccount]:
        return {row.account_key: row for row in self.session.scalars(select(FinanceCashAccount))}

    def _maps(self) -> list[WalmartPayoutAccount]:
        return list(
            self.session.scalars(
                select(WalmartPayoutAccount).where(
                    WalmartPayoutAccount.source_account_ref == SOURCE_REF,
                    WalmartPayoutAccount.is_active.is_(True),
                )
            )
        )

    @staticmethod
    def _account_ins(maps: Iterable[WalmartPayoutAccount]) -> list[rules.AccountIn]:
        return [
            rules.AccountIn(
                store_id=row.store_id,
                account_key=row.account_key,
                payee=row.payee,
                effective_from=row.effective_from,
                effective_to=row.effective_to,
            )
            for row in maps
        ]

    @staticmethod
    def _period_in(row: WalmartBillPeriod) -> rules.PeriodIn:
        return rules.PeriodIn(
            store_id=row.store_id,
            report_key=row.report_key,
            report_date=row.report_date,
            currency_code=row.currency_code,
            payable=row.payable_amount,
            status=row.status,
        )

    def _review_kinds(self, keys: Sequence[Key]) -> dict[Key, list[WalmartPayoutReviewEvent]]:
        out: dict[Key, list[WalmartPayoutReviewEvent]] = defaultdict(list)
        if not keys:
            return out
        events = self.session.scalars(
            select(WalmartPayoutReviewEvent)
            .where(
                WalmartPayoutReviewEvent.source_account_ref == SOURCE_REF,
                tuple_(WalmartPayoutReviewEvent.store_id, WalmartPayoutReviewEvent.report_key).in_(
                    list(keys)
                ),
            )
            .order_by(WalmartPayoutReviewEvent.seq_no)
        )
        for event in events:
            out[(event.store_id, event.report_key)].append(event)
        return out

    def _follow_ups(self, keys: Sequence[Key]) -> dict[Key, list[WalmartPayoutFollowUp]]:
        out: dict[Key, list[WalmartPayoutFollowUp]] = defaultdict(list)
        if not keys:
            return out
        rows = self.session.scalars(
            select(WalmartPayoutFollowUp)
            .where(
                WalmartPayoutFollowUp.source_account_ref == SOURCE_REF,
                tuple_(WalmartPayoutFollowUp.store_id, WalmartPayoutFollowUp.report_key).in_(
                    list(keys)
                ),
            )
            .order_by(WalmartPayoutFollowUp.created_at, WalmartPayoutFollowUp.id)
        )
        for row in rows:
            out[(row.store_id, row.report_key)].append(row)
        return out

    def _lines(self, uids: Iterable[str]) -> dict[str, FinanceCashLine]:
        wanted = list(set(uids))
        if not wanted:
            return {}
        return {
            row.line_uid: row
            for row in self.session.scalars(
                select(FinanceCashLine).where(FinanceCashLine.line_uid.in_(wanted))
            )
        }

    def _groups(self, matches: Sequence[WalmartPayoutMatch]) -> dict[UUID, _Group]:
        groups: dict[UUID, _Group] = {}
        for row in matches:
            group = groups.setdefault(
                row.match_id, _Group(row.match_id, row.line_uid, row.method, [])
            )
            group.keys.append((row.store_id, row.report_key))
        return groups

    def _arrivals(
        self,
        groups: dict[UUID, _Group],
        periods: dict[Key, WalmartBillPeriod],
        lines: dict[str, FinanceCashLine],
    ) -> dict[Key, tuple[Decimal, _Group]]:
        """每期到账金额：合并打款按应付分，差额落在账单日最晚的一期。"""
        out: dict[Key, tuple[Decimal, _Group]] = {}
        for group in groups.values():
            line = lines.get(group.line_uid)
            if line is None:
                continue
            known = [periods[key] for key in group.keys if key in periods]
            if len(known) != len(group.keys):
                # 有一期不在本次读取范围里：按应付记，差额无法判断时落在能看到的最后一期。
                known_keys = {(p.store_id, p.report_key) for p in known}
                missing = [
                    row
                    for row in self.session.scalars(
                        select(WalmartBillPeriod).where(
                            WalmartBillPeriod.source_account_ref == SOURCE_REF,
                            tuple_(WalmartBillPeriod.store_id, WalmartBillPeriod.report_key).in_(
                                [key for key in group.keys if key not in known_keys]
                            ),
                        )
                    )
                ]
                known = [*known, *missing]
            split = rules.split_arrival(
                line.amount,
                [((p.store_id, p.report_key), p.report_date, p.payable_amount) for p in known],
            )
            for key, amount in split.items():
                out[key] = (amount, group)
        return out

    def _open_lines(
        self, accounts: Iterable[str], taken: set[str], since: date
    ) -> list[FinanceCashLine]:
        wanted = sorted(set(accounts))
        if not wanted:
            return []
        rows = self.session.scalars(
            select(FinanceCashLine).where(
                FinanceCashLine.account_key.in_(wanted),
                FinanceCashLine.voided_at.is_(None),
                FinanceCashLine.amount > 0,
                FinanceCashLine.business_date >= since,
            )
        )
        free = [row for row in rows if row.line_uid not in taken]
        hints = self._journal_hints(row.line_uid for row in free)
        # 日记账里已剔除 / 已内部配对 / 已拆分 / 已分到别的类别的流水不自动配（可以手动配）。
        return [row for row in free if hints.get(row.line_uid) is None]

    def _journal_hints(self, uids: Iterable[str]) -> dict[str, str | None]:
        """这笔流水在日记账里是否已另有用途；None = 没有，可以自动配。"""
        wanted = list(set(uids))
        if not wanted:
            return {}
        names = dict(
            self.session.execute(select(FinanceCashCategory.code, FinanceCashCategory.name)).all()
        )
        states = {
            state.line_uid: state
            for state in self.session.scalars(
                select(FinanceCashLineState).where(FinanceCashLineState.line_uid.in_(wanted))
            )
        }
        classifier = self._classifier()
        out: dict[str, str | None] = {}
        for line in self.session.scalars(
            select(FinanceCashLine).where(FinanceCashLine.line_uid.in_(wanted))
        ):
            state = states.get(line.line_uid)
            hint: str | None = None
            if state is not None and state.exclude_amount is not None:
                hint = "已剔除"
            elif state is not None and state.manual_pair:
                hint = "已内部配对"
            elif state is not None and state.parts:
                hint = "已拆分"
            elif state is not None and state.refs:
                hint = "已挂审批单"
            elif state is not None and state.manual_category:
                code = state.manual_category
                hint = None if code == PLATFORM_CATEGORY else f"已分类 {names.get(code, code)}"
            else:
                # 没人工分类：日记账规则分出了「平台回款」以外的类别（如内部转账），也不自动配。
                code = classifier.classify(
                    f"{line.description} {line.memo}", line.counterparty_name
                )
                if code and code != PLATFORM_CATEGORY:
                    hint = f"已分类 {names.get(code, code)}（规则）"
            out[line.line_uid] = hint
        return out

    def _classifier(self) -> journal.Classifier:
        """日记账同一套分类规则（cfg_finance_cash_classify_rules）。"""
        return journal.Classifier(
            journal.Rule(rule.rule_type, rule.pattern, rule.category_code, rule.sort_order)
            for rule in self.session.scalars(select(FinanceCashClassifyRule))
        )

    @staticmethod
    def _line_in(row: FinanceCashLine) -> rules.LineIn:
        return rules.LineIn(
            line_uid=row.line_uid,
            account_key=row.account_key,
            business_date=row.business_date,
            amount=row.amount,
            currency_code=row.currency_code,
            text=" ".join((row.counterparty_name, row.description, row.memo)),
        )

    def _proposals(
        self, matches: Sequence[WalmartPayoutMatch] | None = None
    ) -> tuple[list[rules.AutoMatch], dict[Key, WalmartBillPeriod], dict[str, FinanceCashLine]]:
        matches = self._active_matches() if matches is None else matches
        taken_periods = {(row.store_id, row.report_key) for row in matches}
        taken_lines = {row.line_uid for row in matches}
        periods = [
            row
            for row in self.session.scalars(
                select(WalmartBillPeriod).where(
                    WalmartBillPeriod.source_account_ref == SOURCE_REF,
                    WalmartBillPeriod.report_date >= RECON_START,
                    WalmartBillPeriod.status == "normal",
                    WalmartBillPeriod.payable_amount > 0,
                )
            )
            if (row.store_id, row.report_key) not in taken_periods
        ]
        maps = self._maps()
        lines = self._open_lines((row.account_key for row in maps), taken_lines, RECON_START)
        proposals = rules.find_auto_matches(
            [self._period_in(row) for row in periods],
            [self._line_in(row) for row in lines],
            self._account_ins(maps),
        )
        return (
            proposals,
            {(row.store_id, row.report_key): row for row in periods},
            {row.line_uid: row for row in lines},
        )

    def list_periods(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        store_id: str | None = None,
        today: date | None = None,
    ) -> PayoutPeriodListData:
        today = today or today_shanghai()
        rows, truncated = self._periods(date_from=date_from, date_to=date_to, store_id=store_id)
        matches = self._active_matches()
        proposals, _, _ = self._proposals(matches)
        items = self._reads(rows, matches, today)
        return PayoutPeriodListData(
            items=items,
            today=today,
            recon_start=RECON_START,
            auto_ready=sum(len(p.periods) for p in proposals),
            limit=MAX_ROWS,
            truncated=truncated,
        )

    def _reads(
        self,
        rows: Sequence[WalmartBillPeriod],
        matches: Sequence[WalmartPayoutMatch],
        today: date,
    ) -> list[PayoutPeriodRead]:
        by_key = {(row.store_id, row.report_key): row for row in rows}
        groups = self._groups(matches)
        lines = self._lines(group.line_uid for group in groups.values())
        arrivals = self._arrivals(
            {gid: g for gid, g in groups.items() if any(k in by_key for k in g.keys)},
            by_key,
            lines,
        )
        keys = list(by_key)
        reviews = self._review_kinds(keys)
        follows = self._follow_ups(keys)
        accounts = self._accounts()
        maps = self._account_ins(self._maps())
        items: list[PayoutPeriodRead] = []
        for row in rows:
            key = (row.store_id, row.report_key)
            arrived = arrivals.get(key)
            line = lines.get(arrived[1].line_uid) if arrived else None
            # 到账流水已作废（日记账整批作废）：配对记录不动，这一期按没到账算，标打款异常。
            arrival_voided = line is not None and line.voided_at is not None
            counted = arrived[0] if arrived and not arrival_voided else None
            state, diff = rules.pay_state(self._period_in(row), counted, today)
            events = reviews.get(key, [])
            stage = rules.stage_of(event.kind for event in events)
            reject = next(
                (e.reason for e in reversed(events) if e.kind == rules.KIND_REVIEW2_REJECT), None
            )
            mapped = rules.account_for(maps, row.store_id, row.report_date)
            account_key = line.account_key if line else (mapped.account_key if mapped else None)
            account = accounts.get(account_key) if account_key else None
            follow_rows = follows.get(key, [])
            items.append(
                PayoutPeriodRead(
                    store_id=row.store_id,
                    store_code=store_code(row.store_name, row.store_id),
                    store_name=row.store_name,
                    report_key=row.report_key,
                    report_date=row.report_date,
                    period_start_date=row.period_start_date or row.first_posted_date,
                    period_end_date=row.period_end_date or row.last_posted_date,
                    currency_code=row.currency_code,
                    payable_amount=row.payable_amount,
                    period_status=row.status,
                    pay_state=state,
                    anomaly=arrival_voided or state in rules.ANOMALY_STATES,
                    arrival_voided=arrival_voided,
                    arrived_amount=counted,
                    diff=diff,
                    arrived_date=line.business_date if line else None,
                    line_uid=line.line_uid if line else None,
                    match_id=arrived[1].match_id if arrived else None,
                    match_method=arrived[1].method if arrived else None,
                    match_size=len(arrived[1].keys) if arrived else 0,
                    account_key=account_key,
                    account_name=account.display_name if account else None,
                    org=ORG_BY_PROVIDER.get(account.provider, account.provider)
                    if account
                    else None,
                    payee=mapped.payee if mapped else None,
                    stage=stage,
                    stage_reason=reject if stage == rules.STAGE_REJ2 else None,
                    follow_count=len(follow_rows),
                    latest_follow=_follow_read(follow_rows[-1]) if follow_rows else None,
                )
            )
        return items

    def period_detail(
        self, store_id: str, report_key: str, *, today: date | None = None
    ) -> PayoutPeriodDetailData:
        row = self.session.get(WalmartBillPeriod, (SOURCE_REF, store_id, report_key))
        if row is None:
            raise PayoutReconError(404, ERR_NOT_FOUND, "没有这一期账单")
        key = (store_id, report_key)
        read = self._reads([row], self._active_matches(), today or today_shanghai())[0]
        history = self.session.scalars(
            select(WalmartPayoutMatch)
            .where(
                WalmartPayoutMatch.source_account_ref == SOURCE_REF,
                WalmartPayoutMatch.store_id == store_id,
                WalmartPayoutMatch.report_key == report_key,
            )
            .order_by(WalmartPayoutMatch.created_at)
        )
        return PayoutPeriodDetailData(
            period=read,
            amounts_by_type={str(k): str(v) for k, v in (row.amounts_by_type or {}).items()},
            reviews=[
                PayoutReviewEventRead(
                    kind=e.kind, reason=e.reason, actor=e.actor, created_at=e.created_at
                )
                for e in self._review_kinds([key]).get(key, [])
            ],
            follow_ups=[_follow_read(f) for f in self._follow_ups([key]).get(key, [])],
            matches=[
                PayoutMatchHistoryRead(
                    match_id=m.match_id,
                    line_uid=m.line_uid,
                    method=m.method,
                    payable_amount=m.payable_amount,
                    created_by=m.created_by,
                    created_at=m.created_at,
                    undone_at=m.undone_at,
                    undone_by=m.undone_by,
                    undo_reason=m.undo_reason,
                )
                for m in history
            ],
        )

    def candidate_lines(self, store_id: str | None = None) -> PayoutLineListData:
        """手动配对可选的到账：映射过的收款账户里、10 月起、正数、没作废的流水（已配的标出来）。"""
        maps = self._maps()
        account_keys = {
            row.account_key for row in maps if store_id is None or row.store_id == store_id
        }
        taken = {row.line_uid for row in self._active_matches()}
        accounts = self._accounts()
        rows = self.session.scalars(
            select(FinanceCashLine)
            .where(
                FinanceCashLine.account_key.in_(sorted(account_keys) or [""]),
                FinanceCashLine.voided_at.is_(None),
                FinanceCashLine.amount > 0,
                FinanceCashLine.business_date >= RECON_START,
            )
            .order_by(FinanceCashLine.business_date.desc(), FinanceCashLine.line_uid)
            .limit(MAX_ROWS + 1)
        )
        found = list(rows)
        truncated = len(found) > MAX_ROWS
        found = found[:MAX_ROWS]
        hints = self._journal_hints(row.line_uid for row in found)
        return PayoutLineListData(
            limit=MAX_ROWS,
            truncated=truncated,
            items=[
                PayoutLineRead(
                    line_uid=row.line_uid,
                    account_key=row.account_key,
                    account_name=accounts[row.account_key].display_name
                    if row.account_key in accounts
                    else row.account_key,
                    business_date=row.business_date,
                    amount=row.amount,
                    currency_code=row.currency_code,
                    counterparty_name=row.counterparty_name,
                    description=row.description,
                    matched=row.line_uid in taken,
                    journal_hint=hints.get(row.line_uid),
                )
                for row in found
            ],
        )

    # ------------------------------------------------------------------ 写：配对

    def _lock(self) -> None:
        self.session.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": LOCK_ID})

    def auto_match(self, *, actor: str, request_id: str | None) -> PayoutAutoMatchData:
        self._lock()
        proposals, periods, lines = self._proposals()
        matched_periods = 0
        for proposal in proposals:
            self._create_group(
                lines[proposal.line_uid],
                [periods[key] for key in proposal.periods],
                method="auto",
                note=None,
                actor=actor,
                request_id=request_id,
            )
            matched_periods += len(proposal.periods)
        self.session.commit()
        return PayoutAutoMatchData(matched_periods=matched_periods, matched_lines=len(proposals))

    def manual_match(
        self, request: PayoutManualMatchRequest, *, actor: str, request_id: str | None
    ) -> PayoutMatchData:
        self._lock()
        line = self.session.get(FinanceCashLine, request.line_uid)
        if line is None or line.voided_at is not None:
            raise PayoutReconError(404, ERR_NOT_FOUND, "没有这笔到账")
        if line.amount <= 0:
            raise PayoutReconError(422, ERR_INVALID, "只能配收入（金额为正）的流水")
        keys = list(dict.fromkeys((p.store_id, p.report_key) for p in request.periods))
        periods = [self.session.get(WalmartBillPeriod, (SOURCE_REF, *key)) for key in keys]
        if any(row is None for row in periods):
            raise PayoutReconError(404, ERR_NOT_FOUND, "有一期账单不存在")
        found = [row for row in periods if row is not None]
        matches = self._active_matches()
        if any(row.line_uid == line.line_uid for row in matches):
            raise PayoutReconError(409, ERR_CONFLICT, "这笔到账已经配了别的期次，先撤销")
        taken = {(row.store_id, row.report_key) for row in matches}
        stages = self._stages(keys)
        for row in found:
            label = f"{store_code(row.store_name, row.store_id)} {row.report_date}"
            if row.report_date < RECON_START:
                raise PayoutReconError(
                    422, ERR_INVALID, f"{label} 早于 {RECON_START}，不在回款对账范围"
                )
            if row.status == "voided":
                raise PayoutReconError(409, ERR_CONFLICT, f"{label} 账单作废，不能配到账")
            if (row.store_id, row.report_key) in taken:
                raise PayoutReconError(409, ERR_CONFLICT, f"{label} 已经配了到账，先撤销")
            if row.currency_code and row.currency_code != line.currency_code:
                raise PayoutReconError(422, ERR_INVALID, f"{label} 币种和到账不一致")
            if stages[(row.store_id, row.report_key)] not in rules.FIRST_PENDING:
                raise PayoutReconError(409, ERR_STAGE, f"{label} 已审核，不能改配对")
        match_id = self._create_group(
            line, found, method="manual", note=request.note, actor=actor, request_id=request_id
        )
        self.session.commit()
        return PayoutMatchData(match_id=match_id, periods=len(found))

    def unmatch(
        self, match_id: UUID, *, reason: str, actor: str, request_id: str | None
    ) -> PayoutMatchData:
        self._lock()
        reason = reason.strip()
        if not reason:
            raise PayoutReconError(422, ERR_INVALID, "撤销配对必须写原因")
        rows = list(
            self.session.scalars(
                select(WalmartPayoutMatch)
                .where(
                    WalmartPayoutMatch.match_id == match_id,
                    WalmartPayoutMatch.undone_at.is_(None),
                )
                .order_by(WalmartPayoutMatch.seq)
            )
        )
        if not rows:
            raise PayoutReconError(404, ERR_NOT_FOUND, "没有这次配对（或已撤销）")
        keys = [(row.store_id, row.report_key) for row in rows]
        stages = self._stages(keys)
        line = self.session.get(FinanceCashLine, rows[0].line_uid)
        # 到账流水已作废：钱不在了，任何阶段都可以撤销（撤销后回到待初审）。
        arrival_voided = line is not None and line.voided_at is not None
        if not arrival_voided and any(
            stage not in rules.FIRST_PENDING for stage in stages.values()
        ):
            raise PayoutReconError(409, ERR_STAGE, "已初审 / 终审的期次不能撤销配对；先请终审驳回")
        now = datetime.now(UTC)
        for row in rows:
            row.undone_at, row.undone_by, row.undo_reason = now, actor, reason
        head = rows[0]
        self._journal_untag(head, actor=actor, request_id=request_id)
        for key, stage in stages.items():
            if stage != rules.STAGE_TODO:
                self._add_review(key, rules.KIND_RESET, reason, actor, request_id)
        self.session.commit()
        return PayoutMatchData(match_id=match_id, periods=len(rows))

    def _create_group(
        self,
        line: FinanceCashLine,
        periods: Sequence[WalmartBillPeriod],
        *,
        method: str,
        note: str | None,
        actor: str,
        request_id: str | None,
    ) -> UUID:
        ordered = sorted(periods, key=lambda p: (p.report_date, p.store_id, p.report_key))
        codes = sorted({store_code(p.store_name, p.store_id) for p in ordered})
        tag = rules.journal_tag("、".join(codes), [p.report_date for p in ordered])
        memo_before, memo_set, category_set, too_long = self._journal_tag(
            line, tag, actor=actor, request_id=request_id
        )
        match_id = uuid4()
        for seq, period in enumerate(ordered):
            self.session.add(
                WalmartPayoutMatch(
                    match_id=match_id,
                    seq=seq,
                    line_uid=line.line_uid,
                    source_account_ref=SOURCE_REF,
                    store_id=period.store_id,
                    report_key=period.report_key,
                    payable_amount=period.payable_amount,
                    method=method,
                    memo_before=memo_before,
                    memo_set=memo_set,
                    category_set=category_set,
                    note=_match_note(note, too_long),
                    created_by=actor,
                )
            )
        self.session.flush()
        return match_id

    # ------------------------------------------------------------------ 日记账联动

    def _journal_state(self, line_uid: str) -> FinanceCashLineState:
        self.session.execute(
            pg_insert(FinanceCashLineState)
            .values(line_uid=line_uid)
            .on_conflict_do_nothing(index_elements=["line_uid"])
        )
        state = self.session.get(
            FinanceCashLineState, line_uid, with_for_update=True, populate_existing=True
        )
        if state is None:  # pragma: no cover - 上一句刚写入
            raise PayoutReconError(404, ERR_NOT_FOUND, "没有这笔到账")
        return state

    def _journal_event(
        self,
        line: FinanceCashLine,
        state: FinanceCashLineState,
        kind: str,
        payload: dict[str, Any],
        *,
        actor: str,
        request_id: str | None,
    ) -> None:
        """和日记账页面同一套规则改这笔流水（journal.apply_event），留事件、版本号 +1。"""
        draft = journal.ReviewState(
            manual_category=state.manual_category,
            refs=list(state.refs or []),
            exclude_amount=state.exclude_amount,
            exclude_reason=state.exclude_reason,
            stage=state.stage,
            stage_reason=state.stage_reason,
            review_note=state.review_note,
            manual_description=state.manual_description,
            manual_memo=state.manual_memo,
            parts=[dict(part) for part in state.parts] if state.parts else None,
            manual_pair=state.manual_pair,
        )
        codes = frozenset(self.session.scalars(select(FinanceCashCategory.code)))
        auto_reset = journal.apply_event(
            draft,
            kind=kind,
            payload=payload,
            reason=None,
            line_amount=line.amount,
            valid_categories=codes,
        )
        state.manual_category = draft.manual_category
        state.manual_memo = draft.manual_memo
        state.stage, state.stage_reason = draft.stage, draft.stage_reason
        state.version += 1
        state.updated_at = datetime.now(UTC)
        self.session.add(
            FinanceCashLineEvent(
                line_uid=line.line_uid,
                kind=kind,
                payload={**payload, "source": JOURNAL_SOURCE},
                actor=actor,
                request_id=request_id,
            )
        )
        if auto_reset:
            self.session.add(
                FinanceCashLineEvent(
                    line_uid=line.line_uid,
                    kind=journal.KIND_AUTO_RESET,
                    payload={"triggered_by": kind, "source": JOURNAL_SOURCE},
                    actor="system",
                    request_id=request_id,
                )
            )

    def _category_empty(self, line: FinanceCashLine, state: FinanceCashLineState) -> bool:
        """日记账这笔没有任何分类：没人工选、没挂审批单、没拆分、没剔除、规则也分不出来。"""
        if state.manual_category or state.refs or state.parts or state.exclude_amount is not None:
            return False
        if state.stage not in journal.FIRST_PENDING:
            return False
        classifier = self._classifier()
        return (
            classifier.classify(f"{line.description} {line.memo}", line.counterparty_name) is None
        )

    def _journal_tag(
        self, line: FinanceCashLine, tag: str, *, actor: str, request_id: str | None
    ) -> tuple[str | None, str | None, bool, bool]:
        """返回（配对前人工备注，写入后的完整备注 / None = 没改，
        是否自动填了分类，备注是否过长没追加）。"""
        state = self._journal_state(line.line_uid)
        memo_before = state.manual_memo
        memo_set, too_long = memo_with_tag(memo_before, tag)
        if memo_set is not None:
            self._journal_event(
                line,
                state,
                journal.KIND_SET_TEXT,
                {"memo": memo_set},
                actor=actor,
                request_id=request_id,
            )
        category_set = False
        has_category = self.session.get(FinanceCashCategory, PLATFORM_CATEGORY) is not None
        if has_category and self._category_empty(line, state):
            self._journal_event(
                line,
                state,
                journal.KIND_SET_CATEGORY,
                {"category_code": PLATFORM_CATEGORY},
                actor=actor,
                request_id=request_id,
            )
            category_set = True
        return memo_before, memo_set, category_set, too_long

    def _journal_untag(
        self, match: WalmartPayoutMatch, *, actor: str, request_id: str | None
    ) -> None:
        line = self.session.get(FinanceCashLine, match.line_uid)
        if line is None:  # pragma: no cover - 外键保证
            return
        state = self._journal_state(line.line_uid)
        restored = memo_without_tag(state.manual_memo, match.memo_before, match.memo_set)
        if restored is not False:
            self._journal_event(
                line,
                state,
                journal.KIND_SET_TEXT,
                {"memo": restored},
                actor=actor,
                request_id=request_id,
            )
        if match.category_set and state.manual_category == PLATFORM_CATEGORY and not state.parts:
            self._journal_event(
                line,
                state,
                journal.KIND_SET_CATEGORY,
                {"category_code": None},
                actor=actor,
                request_id=request_id,
            )

    # ------------------------------------------------------------------ 写：审核、跟进

    def _stages(self, keys: Sequence[Key]) -> dict[Key, str]:
        events = self._review_kinds(keys)
        return {key: rules.stage_of(e.kind for e in events.get(key, [])) for key in keys}

    def _add_review(
        self, key: Key, kind: str, reason: str | None, actor: str, request_id: str | None
    ) -> None:
        self.session.add(
            WalmartPayoutReviewEvent(
                source_account_ref=SOURCE_REF,
                store_id=key[0],
                report_key=key[1],
                kind=kind,
                reason=(reason or "").strip() or None,
                actor=actor,
                request_id=request_id,
            )
        )

    def review(
        self, request: PayoutReviewRequest, *, actor: str, request_id: str | None
    ) -> PayoutReviewData:
        reason = (request.reason or "").strip()
        if request.kind == rules.KIND_REVIEW2_REJECT and not reason:
            raise PayoutReconError(422, ERR_INVALID, "终审驳回必须写原因")
        self._lock()
        keys = list(dict.fromkeys((p.store_id, p.report_key) for p in request.periods))
        existing = {
            (row.store_id, row.report_key)
            for row in self.session.scalars(
                select(WalmartBillPeriod).where(
                    WalmartBillPeriod.source_account_ref == SOURCE_REF,
                    tuple_(WalmartBillPeriod.store_id, WalmartBillPeriod.report_key).in_(keys),
                )
            )
        }
        active = self._active_matches()
        matched = {(row.store_id, row.report_key) for row in active}
        lines = self._lines(row.line_uid for row in active)
        voided = {
            (row.store_id, row.report_key)
            for row in active
            if row.line_uid in lines and lines[row.line_uid].voided_at is not None
        }
        stages = self._stages(keys)
        skipped: list[PayoutReviewSkipped] = []
        done = 0
        for key in keys:
            why = None
            if key not in existing:
                why = "没有这一期账单"
            elif key not in matched:
                why = "还没配上到账"
            elif key in voided:
                why = "到账流水已作废，请撤销配对"
            elif not rules.review_allowed(request.kind, stages[key], True):
                why = "不在这一步"
            if why:
                skipped.append(PayoutReviewSkipped(store_id=key[0], report_key=key[1], reason=why))
                continue
            self._add_review(key, request.kind, reason or None, actor, request_id)
            done += 1
        self.session.commit()
        return PayoutReviewData(done=done, skipped=skipped)

    def follow(
        self, request: PayoutFollowRequest, *, actor: str, request_id: str | None
    ) -> PayoutFollowRead:
        content = request.content.strip()
        if not content:
            raise PayoutReconError(422, ERR_INVALID, "跟进内容必填")
        if (
            self.session.get(WalmartBillPeriod, (SOURCE_REF, request.store_id, request.report_key))
            is None
        ):
            raise PayoutReconError(404, ERR_NOT_FOUND, "没有这一期账单")
        row = WalmartPayoutFollowUp(
            source_account_ref=SOURCE_REF,
            store_id=request.store_id,
            report_key=request.report_key,
            content=content,
            case_no=(request.case_no or "").strip() or None,
            next_follow_date=request.next_follow_date,
            actor=actor,
            request_id=request_id,
            # 同一事务里 now() 相同，用应用时间保证先后顺序。
            created_at=datetime.now(UTC),
        )
        self.session.add(row)
        self.session.commit()
        return _follow_read(row)

    # ------------------------------------------------------------------ 收款账户映射

    def _store_options(self) -> list[PayoutStoreOption]:
        rows = self.session.execute(
            select(WalmartBillPeriod.store_id, func.max(WalmartBillPeriod.store_name))
            .where(WalmartBillPeriod.source_account_ref == SOURCE_REF)
            .group_by(WalmartBillPeriod.store_id)
        ).all()
        stores = [
            PayoutStoreOption(store_id=sid, store_code=store_code(name, sid), store_name=name)
            for sid, name in rows
        ]
        return sorted(stores, key=lambda s: s.store_code)

    def list_accounts(self) -> PayoutAccountListData:
        accounts = self._accounts()
        stores = self._store_options()
        codes = {s.store_id: s.store_code for s in stores}
        rows = self.session.scalars(
            select(WalmartPayoutAccount)
            .where(WalmartPayoutAccount.source_account_ref == SOURCE_REF)
            .order_by(WalmartPayoutAccount.store_id, WalmartPayoutAccount.effective_from.desc())
        )
        return PayoutAccountListData(
            items=[self._account_read(row, accounts, codes) for row in rows],
            accounts=[
                PayoutAccountOption(
                    account_key=a.account_key,
                    account_name=a.display_name,
                    org=ORG_BY_PROVIDER.get(a.provider, a.provider),
                    currency_code=a.currency_code,
                )
                for a in sorted(accounts.values(), key=lambda a: (a.sort_order, a.account_key))
                if a.is_active
            ],
            stores=stores,
        )

    @staticmethod
    def _account_read(
        row: WalmartPayoutAccount,
        accounts: dict[str, FinanceCashAccount],
        codes: dict[str, str],
    ) -> PayoutAccountRead:
        account = accounts.get(row.account_key)
        return PayoutAccountRead(
            id=row.id,
            store_id=row.store_id,
            store_code=codes.get(row.store_id, row.store_id),
            account_key=row.account_key,
            account_name=account.display_name if account else row.account_key,
            org=ORG_BY_PROVIDER.get(account.provider, account.provider) if account else "",
            payee=row.payee,
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            is_active=row.is_active,
            change_reason=row.change_reason,
            updated_by=row.updated_by,
            updated_at=row.updated_at,
        )

    def _check_account(self, account_key: str) -> None:
        account = self.session.get(FinanceCashAccount, account_key)
        if account is None or not account.is_active:
            raise PayoutReconError(422, ERR_INVALID, "入账账户不存在或已停用")

    def create_account(
        self, request: PayoutAccountCreateRequest, *, actor: str
    ) -> PayoutAccountRead:
        self._lock()
        self._check_account(request.account_key)
        rows = [row for row in self._maps() if row.store_id == request.store_id]
        if any(row.effective_from == request.effective_from for row in rows):
            raise PayoutReconError(409, ERR_CONFLICT, "这家店这一天已经有一条收款账户，请改那一条")
        current = [row for row in rows if row.effective_to is None]
        reason = (request.reason or "").strip() or None
        for row in current:
            if row.effective_from > request.effective_from:
                raise PayoutReconError(409, ERR_CONFLICT, "生效日期早于现在这条，请先改现在这条")
            if reason is None:
                raise PayoutReconError(422, ERR_INVALID, "换收款账户要写原因")
            row.effective_to = request.effective_from - timedelta(days=1)
            row.updated_by, row.updated_at = actor, datetime.now(UTC)
        row = WalmartPayoutAccount(
            source_account_ref=SOURCE_REF,
            store_id=request.store_id,
            account_key=request.account_key,
            payee=request.payee.strip(),
            effective_from=request.effective_from,
            change_reason=reason,
            created_by=actor,
            updated_by=actor,
        )
        self.session.add(row)
        self.session.commit()
        codes = {s.store_id: s.store_code for s in self._store_options()}
        return self._account_read(row, self._accounts(), codes)

    def update_account(
        self, account_id: UUID, request: PayoutAccountUpdateRequest, *, actor: str
    ) -> PayoutAccountRead:
        self._lock()
        row = self.session.get(WalmartPayoutAccount, account_id)
        if row is None or not row.is_active:
            raise PayoutReconError(404, ERR_NOT_FOUND, "没有这条收款账户")
        if request.account_key != row.account_key:
            # 换入账账户会改变历史期次的归属，必须新增一条（生效日 + 原因），旧的留痕。
            raise PayoutReconError(422, ERR_INVALID, "换账户请新增一条，写生效日和原因")
        reason = (request.reason or "").strip()
        if not reason:
            raise PayoutReconError(422, ERR_INVALID, "改收款账户识别要写原因")
        row.payee = request.payee.strip()
        row.change_reason = reason
        row.updated_by, row.updated_at = actor, datetime.now(UTC)
        self.session.commit()
        codes = {s.store_id: s.store_code for s in self._store_options()}
        return self._account_read(row, self._accounts(), codes)

    def _covered_matches(self, row: WalmartPayoutAccount) -> int:
        """这条映射生效期间（按账单日）里，这家店还有几期生效中的配对。"""
        query = (
            select(func.count())
            .select_from(WalmartPayoutMatch)
            .join(
                WalmartBillPeriod,
                (WalmartBillPeriod.source_account_ref == WalmartPayoutMatch.source_account_ref)
                & (WalmartBillPeriod.store_id == WalmartPayoutMatch.store_id)
                & (WalmartBillPeriod.report_key == WalmartPayoutMatch.report_key),
            )
            .where(
                WalmartPayoutMatch.undone_at.is_(None),
                WalmartPayoutMatch.source_account_ref == row.source_account_ref,
                WalmartPayoutMatch.store_id == row.store_id,
                WalmartBillPeriod.report_date >= row.effective_from,
            )
        )
        if row.effective_to is not None:
            query = query.where(WalmartBillPeriod.report_date <= row.effective_to)
        return int(self.session.scalar(query) or 0)

    def deactivate_account(self, account_id: UUID, *, reason: str, actor: str) -> None:
        self._lock()
        row = self.session.get(WalmartPayoutAccount, account_id)
        if row is None or not row.is_active:
            raise PayoutReconError(404, ERR_NOT_FOUND, "没有这条收款账户")
        if not reason.strip():
            raise PayoutReconError(422, ERR_INVALID, "停用要写原因")
        if self._covered_matches(row):
            raise PayoutReconError(
                409, ERR_CONFLICT, "这条收款账户覆盖的期次里还有生效中的配对，先撤销配对再停用"
            )
        row.is_active = False
        row.change_reason = reason.strip()
        row.updated_by, row.updated_at = actor, datetime.now(UTC)
        self.session.commit()


MEMO_JOINER: Final = "；"
MEMO_TOO_LONG: Final = "备注过长，未追加"


def memo_with_tag(current: str | None, tag: str) -> tuple[str | None, bool]:
    """配对时日记账备注怎么改（Rocky 11-10）：没有人工备注写 tag；有就「原人工备注；tag」追加，
    已有一段和 tag 完全相同就不重复；拼完超过日记账备注上限不改。
    返回（新备注 / None = 不改，是否因过长没改）。
    """
    text = (current or "").strip()
    if not text:
        return tag, False
    # 按「；」切开逐段比：只有某一段和 tag 完全相同才算已有（合并打款的长 tag 不会挡掉短 tag）。
    if tag in (part.strip() for part in text.split(MEMO_JOINER)):
        return None, False
    # 原备注以「；」结尾时先去掉，免得拼出「；；」。
    head = text.rstrip(MEMO_JOINER).rstrip()
    joined = f"{head}{MEMO_JOINER}{tag}" if head else tag
    if len(joined) > journal.TEXT_MAX:
        return None, True
    return joined, False


def memo_without_tag(
    current: str | None, memo_before: str | None, memo_set: str | None
) -> str | None | Literal[False]:
    """撤销时备注怎么恢复（和 memo_with_tag 一样按「；」分段）。

    返回新备注（None = 清空），False = 不动。

    - 当前备注没被人改过（== memo_set）→ 恢复配对前的人工备注；
    - 被人改过：按「；」切段、去空格，和当初追加的 tag 完全相同的段恰好一处 → 只删这一段，
      其余各段用「；」拼回（拼完为空 = 清空）；0 处或多处 → 不动。
    """
    if memo_set is None:
        return False
    if current == memo_set:
        return memo_before
    tag = memo_set.split(MEMO_JOINER)[-1].strip()
    parts = [part.strip() for part in (current or "").split(MEMO_JOINER)]
    hits = [index for index, part in enumerate(parts) if part == tag]
    if not tag or len(hits) != 1:
        return False
    rest = [part for index, part in enumerate(parts) if index != hits[0] and part]
    return MEMO_JOINER.join(rest) or None


def _match_note(note: str | None, too_long: bool) -> str | None:
    parts = [(note or "").strip(), MEMO_TOO_LONG if too_long else ""]
    return MEMO_JOINER.join(part for part in parts if part) or None


def _follow_read(row: WalmartPayoutFollowUp) -> PayoutFollowRead:
    return PayoutFollowRead(
        content=row.content,
        case_no=row.case_no,
        next_follow_date=row.next_follow_date,
        actor=row.actor,
        created_at=row.created_at,
    )

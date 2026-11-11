"""审批单的读取和自动挂单。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.modules.finance_cashflow import approvals as A
from app.modules.finance_cashflow import journal
from app.modules.finance_cashflow.models import FinanceCashApproval, FinanceCashLineEvent
from app.modules.finance_cashflow.schemas import (
    CashflowApprovalCommentRead,
    CashflowApprovalFileRead,
    CashflowApprovalItemRead,
    CashflowApprovalPaidRead,
    CashflowApprovalRead,
    CashflowApprovalRecordRead,
)
from app.modules.finance_cashflow.service import CashflowService

LOCKED_STAGES = frozenset({journal.STAGE_OK1, journal.STAGE_OK2})
FEN = Decimal("0.01")


def allocate_payment(
    line_cny: Decimal | None,
    refs: Sequence[str],
    approvals: Mapping[str, FinanceCashApproval],
    usd_rate: Decimal | None,
) -> dict[str, Decimal | None]:
    """一笔付款的人民币分给它挂的各张审批单（rocky 2026-11-06）。

    按实际付出去的人民币，按各单金额比例分，精度到分。用最大余数法：每张先向下取整到分，
    剩下的几分钱按小数部分从大到小每张补 1 分，所以不会出现负数，加起来正好等于这笔付款。
    小数部分一样大时先给权重大的，再给单号小的，同样的输入每次结果都一样。
    流水人民币带分以下的小数时，先四舍五入到分再分。
    流水没有人民币的整笔待定（None）。只挂一张单时，这笔的人民币全算这张的。
    挂多张单时，缺汇率、单找不到、单没有金额、金额合计为 0 的也整笔待定。
    """
    serials = list(dict.fromkeys(refs))
    pending: dict[str, Decimal | None] = dict.fromkeys(serials)
    if line_cny is None or not serials:
        return pending
    total = abs(line_cny).quantize(FEN, rounding=ROUND_HALF_UP)
    if len(serials) == 1:
        return {serials[0]: total}
    rows = [approvals.get(serial) for serial in serials]
    if any(row is None or row.amount is None for row in rows):
        return pending
    same_currency = len({row.currency_code for row in rows if row is not None}) == 1
    weights: list[Decimal] = []
    for row in rows:
        assert row is not None and row.amount is not None
        amount = abs(row.amount)
        # 币种混合时先折人民币再比；同币种直接比原币。
        weight = amount if same_currency else journal.to_cny(amount, row.currency_code, usd_rate)
        if weight is None:
            return pending
        weights.append(weight)
    whole = sum(weights, Decimal("0"))
    if not whole:
        return pending
    return dict(zip(serials, _split_fen(total, serials, weights, whole), strict=True))


def _line_shares(
    item: journal.ComputedLine,
    approvals: Mapping[str, FinanceCashApproval],
    usd_rate: Decimal | None,
) -> dict[str, Decimal | None]:
    """一笔流水付给各审批单的人民币：拆分行挂的单按这一行的折人民币分（Rocky 11-10）；
    整笔挂的单按整笔里没挂单的那部分分（没拆分就是整笔）。"""
    parts = item.source.parts or []
    if not journal.part_refs(parts):
        return allocate_payment(item.amount_cny, item.source.refs, approvals, usd_rate)
    cnys = journal.part_cny(item.amount_cny, item.source.amount, parts)
    out: dict[str, Decimal | None] = {}
    rest: Decimal | None = abs(item.amount_cny) if item.amount_cny is not None else None
    for part, cny in zip(parts, cnys, strict=True):
        refs = part.get("refs") or []
        if not refs:
            continue
        if rest is not None and cny is not None:
            rest -= cny
        for serial, value in allocate_payment(cny, refs, approvals, usd_rate).items():
            known = out.get(serial, Decimal("0"))
            out[serial] = None if value is None or known is None else known + value
    if item.source.refs:
        for serial, value in allocate_payment(rest, item.source.refs, approvals, usd_rate).items():
            known = out.get(serial, Decimal("0"))
            out[serial] = None if value is None or known is None else known + value
    return out


def _split_fen(
    total: Decimal, serials: Sequence[str], weights: Sequence[Decimal], whole: Decimal
) -> list[Decimal]:
    """最大余数法。全程用分数算，不受 Decimal 除法精度影响。"""
    total_fen = int(total / FEN)
    exact = [Fraction(total_fen) * Fraction(weight) / Fraction(whole) for weight in weights]
    fen = [int(value) for value in exact]
    order = sorted(
        range(len(serials)),
        key=lambda index: (fen[index] - exact[index], -weights[index], serials[index]),
    )
    for index in order[: total_fen - sum(fen)]:
        fen[index] += 1
    return [Decimal(value) * FEN for value in fen]


def _local_text(value: datetime | None) -> str:
    return value.astimezone(A.SHANGHAI).strftime("%Y-%m-%d %H:%M") if value else ""


class ApprovalService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self._settings = settings

    @property
    def settings(self) -> Settings:
        return self._settings or get_settings()

    def auto_match(self, *, request_id: str | None = None) -> int:
        """按规则自动挂单，返回挂了几笔。幂等：已挂的、摘掉过的、已审核的都不动。"""
        cash = CashflowService(self.session, self.settings)
        result, by_uid, states = cash._compute()
        lines = [
            A.MatchLine(
                line_uid=item.source.line_uid,
                business_date=item.source.business_date,
                amount=item.source.amount,
                currency_code=item.source.currency_code,
                counterparty_name=item.source.counterparty_name,
                text=f"{item.source.description} {item.source.memo}",
                refs=(*item.source.refs, *journal.part_refs(item.source.parts)),
                amount_cny=item.amount_cny,
                cny_exact=item.fx_source in journal.FX_EXACT_SOURCES,
                stage=states[item.source.line_uid].stage
                if item.source.line_uid in states
                else journal.STAGE_TODO,
            )
            for item in result.lines
        ]
        refused = frozenset(
            (line_uid, str((payload or {}).get("ref") or ""))
            for line_uid, payload in self.session.execute(
                select(FinanceCashLineEvent.line_uid, FinanceCashLineEvent.payload).where(
                    FinanceCashLineEvent.kind == journal.KIND_DETACH_REF
                )
            )
        )
        matches = A.find_auto_matches(
            lines,
            cash.match_approvals(),
            locked_stages=LOCKED_STAGES,
            refused=refused,
        )
        done = 0
        for line_uid, serial, how in matches:
            if line_uid not in by_uid:
                continue
            state = cash._state_for_update(line_uid)
            if state.stage in LOCKED_STAGES or serial in (state.refs or []):
                continue
            state.refs = [*(state.refs or []), serial]
            state.version += 1
            state.updated_at = datetime.now(UTC)
            self.session.add(
                FinanceCashLineEvent(
                    line_uid=line_uid,
                    kind=journal.KIND_AUTO_ATTACH_REF,
                    payload={"ref": serial, "by": how},
                    actor="system",
                    request_id=request_id,
                )
            )
            done += 1
        self.session.commit()
        return done

    def list_approvals(self) -> list[CashflowApprovalRead]:
        cash = CashflowService(self.session, self.settings)
        result, _by_uid, _states = cash._compute()
        by_ref: dict[str, list[journal.ComputedLine]] = defaultdict(list)
        for item in result.lines:
            for ref in dict.fromkeys([*item.source.refs, *journal.part_refs(item.source.parts)]):
                by_ref[ref].append(item)
        rate_of = cash._usd_rate_lookup()
        rows = sorted(cash.approval_rows(), key=lambda row: row.serial_number, reverse=True)
        by_serial = {row.serial_number: row for row in rows}
        shares = {
            item.source.line_uid: _line_shares(item, by_serial, rate_of(item.source.business_date))
            for item in result.lines
            if item.source.refs or journal.part_refs(item.source.parts)
        }
        names = self.employee_names()
        return [
            self._read(row, by_ref.get(row.serial_number, []), shares, rate_of, names)
            for row in rows
        ]

    def employee_names(self) -> dict[str, str]:
        """飞书 user_id → 姓名，来自系统员工表 app_users；优先飞书姓名，其次显示名。

        匹配不到的，页面显示编号。不用 open_id：它每个飞书应用都不一样。
        """
        rows = self.session.execute(
            text(
                """
                select feishu_user_id,
                       coalesce(nullif(btrim(feishu_name), ''), nullif(btrim(display_name), ''))
                  from app_users
                 where feishu_user_id is not null
                """
            )
        ).all()
        return {str(row[0]): str(row[1]) for row in rows if row[1]}

    @staticmethod
    def _read(
        row: FinanceCashApproval,
        lines: list[journal.ComputedLine],
        shares: Mapping[str, Mapping[str, Decimal | None]],
        rate_of: Callable[[date], Decimal | None],
        names: Mapping[str, str],
    ) -> CashflowApprovalRead:
        wanted = abs(row.amount) if row.amount is not None else None
        if wanted is not None and row.currency_code != "CNY":
            day = row.started_at.astimezone(A.SHANGHAI).date() if row.started_at else None
            wanted = journal.to_cny(wanted, row.currency_code, rate_of(day) if day else None)
        paid: list[CashflowApprovalPaidRead] = []
        total = Decimal("0")
        paid_unknown = False
        for item in lines:
            value = shares[item.source.line_uid][row.serial_number]
            if value is None:
                paid_unknown = True
                paid.append(
                    CashflowApprovalPaidRead(line_uid=item.source.line_uid, amount_cny=None)
                )
                continue
            # 流出算已付，退款（流入）冲减。
            signed = value if item.source.amount < 0 else -value
            paid.append(CashflowApprovalPaidRead(line_uid=item.source.line_uid, amount_cny=signed))
            total += signed
        return CashflowApprovalRead(
            serial=row.serial_number,
            kind=row.kind,
            status=row.status,
            status_text=A.STATUS_TEXT.get(row.status, row.status),
            state=A.paid_state(
                status=row.status,
                wanted_cny=wanted,
                paid_cny=total,
                has_paid_lines=bool(paid),
                paid_unknown=paid_unknown,
            ),
            started_at=_local_text(row.started_at),
            completed_at=_local_text(row.completed_at),
            handled_at=_local_text(row.handled_at),
            applicant=names.get(row.applicant_user_id) or row.applicant_user_id,
            reason=row.reason,
            amount=row.amount,
            currency_code=row.currency_code,
            amount_cny=wanted,
            pay_method=row.pay_method,
            invoice=row.invoice,
            payee=row.payee,
            bank=row.payee_bank,
            last4=row.payee_account_last4,
            fee_category=row.fee_category,
            related_serial=row.related_serial,
            items=[CashflowApprovalItemRead(**item) for item in row.items or []],
            attachments=[CashflowApprovalFileRead(**item) for item in row.attachments or []],
            records=[
                CashflowApprovalRecordRead(
                    **{**item, "who": A.rename_people(str(item.get("who") or ""), names)}
                )
                for item in row.records or []
            ],
            comments=[
                CashflowApprovalCommentRead(
                    **{**item, "who": A.rename_people(str(item.get("who") or ""), names)}
                )
                for item in row.comments or []
            ],
            paid=paid,
            paid_sum=total,
            fetched_at=row.fetched_at,
        )

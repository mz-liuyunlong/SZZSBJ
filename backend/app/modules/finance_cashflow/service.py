from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.modules.finance_cashflow import approvals as approval_rules
from app.modules.finance_cashflow import journal
from app.modules.finance_cashflow.models import (
    FinanceCashAccount,
    FinanceCashAlertClosure,
    FinanceCashApproval,
    FinanceCashCategory,
    FinanceCashClassifyRule,
    FinanceCashExclusion,
    FinanceCashImport,
    FinanceCashImportQuality,
    FinanceCashLine,
    FinanceCashLineEvent,
    FinanceCashLineOccurrence,
    FinanceCashLineState,
    FinanceCashRawFile,
    FinancePayoneerStatementRow,
)
from app.modules.finance_cashflow.parsing import PARSER_VERSION, payoneer_statement, readers
from app.modules.finance_cashflow.parsing.model import Line, RejectFile
from app.modules.finance_cashflow.parsing.pipeline import ParsedFile, parse_file
from app.modules.finance_cashflow.parsing.seed import Seed, SeedAccount
from app.modules.finance_cashflow.schemas import (
    CashflowAccountRead,
    CashflowAlertCloseRequest,
    CashflowAlertClosureRead,
    CashflowAlertReopenRequest,
    CashflowAnomalyRead,
    CashflowCategoryRead,
    CashflowFileResult,
    CashflowImportListData,
    CashflowImportRead,
    CashflowLineEventData,
    CashflowLineEventRequest,
    CashflowLineListData,
    CashflowLinePartRead,
    CashflowLineRead,
    CashflowPairEventData,
    CashflowPairEventRequest,
    CashflowUploadData,
    CashflowVoidData,
)
from app.modules.fx_rates.reader import load_usd_cny_rates, usd_cny_rate_for

SHANGHAI = ZoneInfo("Asia/Shanghai")
STORAGE_SUBDIR = Path("finance") / "cashflow"
STATUS_PARSED = "parsed"
STATUS_REJECTED = "rejected"
STATUS_RECEIVED = "received"
STATUS_FAILED = "failed"
STATUS_VOIDED = "voided"
FILE_SUFFIX = {"xlsx": ".xlsx", "xls": ".xls", "text": ".csv", "pdf": ".pdf"}


class StorageNotConfiguredError(Exception):
    """MEDIA_STORAGE_ROOT 没配：不往别处写。"""


class ImportNotFoundError(Exception):
    pass


class ImportVoidedError(Exception):
    pass


class LineNotFoundError(Exception):
    pass


# 能关闭的异常类型（刘云龙 #339 终审）：后端算的 + 页面算的，和前端 data.ts 的 ALERT_GUIDE 一致。
KNOWN_ALERT_TYPES = frozenset(
    {
        journal.ALERT_UNPAIRED,  # 内部转账未配对
        journal.ALERT_PAIR_GAP,  # 转账到账差额
        "明细合计≠流水",
        journal.ALERT_BALANCE,  # 余额不连续
        journal.ALERT_EXCLUSION,  # 剔除未命中
        "审批单未付",
        "审批单部分已付",
        "审批单无付款流水",
        "审批单金额不符",
        journal.ALERT_PINGPONG_FEE,  # PingPong 付款手续费
        journal.ALERT_PAYONEER_FEE,  # 派安盈提现到账差额
        journal.ALERT_PAYONEER_MISSING,  # 缺派安盈实际汇率
        journal.ALERT_STATEMENT_UNMATCHED,  # 月结单有、流水没有
        journal.ALERT_STATEMENT_AMBIGUOUS,  # 月结单匹配到多笔
        journal.ALERT_STATEMENT_CONFLICT,  # 月结单前后不一致
    }
)
APPROVAL_SERIAL = re.compile(r"\d{12}")
LINE_TAIL = re.compile(r"[0-9a-f]{6}")


class AlertClosureError(Exception):
    """关闭 / 重新打开异常被拒：重复关闭、没有关闭记录、原因为空。"""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class ImportHasReviewedLinesError(Exception):
    """这一批作废后会有已审核的流水被一起作废；要先退回审核。"""

    def __init__(self, line_uids: list[str]) -> None:
        super().__init__("import has reviewed lines")
        self.line_uids = line_uids


def store_original(root: Path, sha256: str, kind: str, content: bytes) -> str:
    """原件按内容存放，同内容只留一份；返回相对 root 的路径。先写临时文件再改名，不留半截。"""
    relative = STORAGE_SUBDIR / sha256[:2] / f"{sha256}{FILE_SUFFIX.get(kind, '.bin')}"
    target = root / relative
    if target.exists():
        return relative.as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=target.parent, prefix=".upload-")
    try:
        with os.fdopen(handle, "wb") as temp_file:
            temp_file.write(content)
        os.chmod(temp_name, 0o640)
        os.replace(temp_name, target)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
    return relative.as_posix()


class CashflowService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    # ------------------------------------------------------------ 导入

    def _seed(self) -> Seed:
        rows = self.session.scalars(select(FinanceCashAccount)).all()
        return Seed(
            [
                SeedAccount(
                    account_key=row.account_key,
                    display_name=row.display_name,
                    entity=row.entity,
                    currency_code=row.currency_code,
                    kind=row.kind,
                    provider=row.provider,
                    account_no_last4=row.account_no_last4,
                    match=dict(row.identity_hint or {}),
                    is_active=row.is_active,
                )
                for row in rows
            ]
        )

    def _import_for_upload(
        self, import_id: UUID | None, actor: str, request_id: str | None
    ) -> FinanceCashImport:
        batch = self.session.get(FinanceCashImport, import_id) if import_id else None
        if batch is not None and batch.status == STATUS_VOIDED:
            raise ImportVoidedError
        if batch is None:
            batch = FinanceCashImport(
                import_id=import_id or uuid4(),
                uploader=actor,
                status=STATUS_RECEIVED,
                request_id=request_id,
            )
            self.session.add(batch)
            self.session.flush()
        return batch

    def _active_duplicate(self, sha256: str) -> FinanceCashRawFile | None:
        return self.session.scalars(
            select(FinanceCashRawFile)
            .join(
                FinanceCashImport,
                FinanceCashImport.import_id == FinanceCashRawFile.import_id,
            )
            .where(
                FinanceCashRawFile.sha256 == sha256,
                FinanceCashRawFile.status == STATUS_PARSED,
                FinanceCashImport.status != STATUS_VOIDED,
            )
            .order_by(FinanceCashRawFile.created_at.desc())
            .limit(1)
        ).first()

    def upload(
        self,
        *,
        import_id: UUID | None,
        file_name: str,
        content: bytes,
        actor: str,
        request_id: str | None,
    ) -> CashflowUploadData:
        root = self.settings.media_storage_root
        if root is None:
            raise StorageNotConfiguredError
        sha256 = hashlib.sha256(content).hexdigest()
        batch = self._import_for_upload(import_id, actor, request_id)
        duplicate = self._active_duplicate(sha256)
        if duplicate is not None:
            if duplicate.parser_version != PARSER_VERSION:
                # 同一个文件用新版解析再导一次：已有流水只刷新显示文字（如邮箱不再打码），不新增。
                try:
                    self._refresh_texts(parse_file(content, self._seed()).lines)
                except RejectFile:
                    pass
                else:
                    duplicate.parser_version = PARSER_VERSION
            result = self._file_result(duplicate)
            result.duplicate_of_file = True
            result.file_name = file_name
            result.rows_duplicate = result.rows_parsed
            result.rows_new = 0
            self._refresh_batch_status(batch, True)
            self.session.commit()
            return CashflowUploadData(import_id=batch.import_id, file=result)
        storage_path = store_original(Path(root), sha256, readers.kind_of(content), content)
        if payoneer_statement.is_statement(content):
            return self._upload_statement(batch, file_name, sha256, content, storage_path)
        try:
            parsed = parse_file(content, self._seed())
        except RejectFile as exc:
            result = self._save_rejected(batch, file_name, sha256, content, storage_path, str(exc))
            self._refresh_batch_status(batch, False)
            self.session.commit()
            return CashflowUploadData(import_id=batch.import_id, file=result)
        try:
            with self.session.begin_nested():
                result = self._save_parsed(batch, file_name, sha256, content, storage_path, parsed)
        except IntegrityError:
            result = self._save_rejected(
                batch, file_name, sha256, content, storage_path, "写入冲突，请重新上传"
            )
        self._refresh_batch_status(batch, result.status == STATUS_PARSED)
        self.session.commit()
        return CashflowUploadData(import_id=batch.import_id, file=result)

    def _upload_statement(
        self,
        batch: FinanceCashImport,
        file_name: str,
        sha256: str,
        content: bytes,
        storage_path: str,
    ) -> CashflowUploadData:
        """派安盈月结明细：只存明细行，读取时补到已有提现上，不新增流水。"""
        try:
            parsed = payoneer_statement.parse_statement(content, self._seed())
        except RejectFile as exc:
            result = self._save_rejected(batch, file_name, sha256, content, storage_path, str(exc))
            self._refresh_batch_status(batch, False)
            self.session.commit()
            return CashflowUploadData(import_id=batch.import_id, file=result)
        except payoneer_statement.UNEXPECTED_ERRORS:
            result = self._save_rejected(
                batch,
                file_name,
                sha256,
                content,
                storage_path,
                "文件内容解析失败，请确认是派安盈的原始导出",
            )
            self._refresh_batch_status(batch, False)
            self.session.commit()
            return CashflowUploadData(import_id=batch.import_id, file=result)
        seen = set(
            self.session.scalars(
                select(FinancePayoneerStatementRow.txn_id)
                .join(
                    FinanceCashImport,
                    FinanceCashImport.import_id == FinancePayoneerStatementRow.import_id,
                )
                .where(
                    FinancePayoneerStatementRow.account_key == parsed.account_key,
                    FinanceCashImport.status != STATUS_VOIDED,
                )
            )
        )
        raw = FinanceCashRawFile(
            import_id=batch.import_id,
            file_name=file_name,
            sha256=sha256,
            size_bytes=len(content),
            storage_path=storage_path,
            provider=payoneer_statement.PROVIDER,
            account_keys=[parsed.account_key],
            parser_version=PARSER_VERSION,
            status=STATUS_PARSED,
        )
        self.session.add(raw)
        self.session.flush()
        self.session.add_all(
            FinancePayoneerStatementRow(
                raw_file_id=raw.file_id,
                import_id=batch.import_id,
                account_key=parsed.account_key,
                row_no=row.row_no,
                txn_id=row.txn_id,
                txn_time=row.txn_time_utc,
                business_date=row.business_date,
                description=row.description,
                amount=row.amount,
                currency_code=row.currency_code,
                transfer_amount=row.transfer_amount,
                transfer_currency=row.transfer_currency,
            )
            for row in parsed.rows
        )
        rows_new = sum(1 for row in parsed.rows if not row.txn_id or row.txn_id not in seen)
        withdrawals = [
            row
            for row in parsed.rows
            if row.amount < 0 and journal.PAYONEER_WITHDRAWAL.match(row.description)
        ]
        in_cny = sum(1 for row in withdrawals if row.transfer_currency == "CNY")
        # 页面把 rows_new 显示成「新增 N 行」：月结补充不新增流水，所以填 0，读到多少写在说明里。
        warnings = [
            f"派安盈月结补充，不新增流水：读到 {len(parsed.rows)} 行"
            f"（其中 {rows_new} 行以前没导过），"
            f"提现 {len(withdrawals)} 笔，到账人民币 {in_cny} 笔"
        ]
        self.session.add(
            FinanceCashImportQuality(
                file_id=raw.file_id,
                rows_parsed=len(parsed.rows),
                rows_new=0,
                rows_duplicate=0,
                balance_chain_ok=None,
                warnings=warnings,
            )
        )
        self._refresh_batch_status(batch, True)
        self.session.commit()
        return CashflowUploadData(
            import_id=batch.import_id,
            file=CashflowFileResult(
                file_id=raw.file_id,
                file_name=file_name,
                sha256=sha256,
                size=len(content),
                status=STATUS_PARSED,
                account_keys=[parsed.account_key],
                detected_note=parsed.note,
                rows_parsed=len(parsed.rows),
                warnings=warnings,
            ),
        )

    def _refresh_batch_status(self, batch: FinanceCashImport, parsed: bool) -> None:
        if parsed:
            batch.status = STATUS_PARSED
        elif batch.status == STATUS_RECEIVED:
            batch.status = STATUS_FAILED

    def _save_rejected(
        self,
        batch: FinanceCashImport,
        file_name: str,
        sha256: str,
        content: bytes,
        storage_path: str,
        reason: str,
    ) -> CashflowFileResult:
        raw = FinanceCashRawFile(
            import_id=batch.import_id,
            file_name=file_name,
            sha256=sha256,
            size_bytes=len(content),
            storage_path=storage_path,
            parser_version=PARSER_VERSION,
            status=STATUS_REJECTED,
            reject_reason=reason,
        )
        self.session.add(raw)
        self.session.flush()
        return CashflowFileResult(
            file_id=raw.file_id,
            file_name=file_name,
            sha256=sha256,
            size=len(content),
            status=STATUS_REJECTED,
            reject_reason=reason,
        )

    def _save_parsed(
        self,
        batch: FinanceCashImport,
        file_name: str,
        sha256: str,
        content: bytes,
        storage_path: str,
        parsed: ParsedFile,
    ) -> CashflowFileResult:
        account_keys = sorted({line.account_key for line in parsed.lines})
        declared = parsed.declared_range
        raw = FinanceCashRawFile(
            import_id=batch.import_id,
            file_name=file_name,
            sha256=sha256,
            size_bytes=len(content),
            storage_path=storage_path,
            provider=parsed.provider,
            account_keys=account_keys,
            declared_range_from=date.fromisoformat(declared[0]) if declared else None,
            declared_range_to=date.fromisoformat(declared[1]) if declared else None,
            parser_version=PARSER_VERSION,
            status=STATUS_PARSED,
        )
        self.session.add(raw)
        self.session.flush()
        uids = [line.line_uid for line in parsed.lines]
        existing = set(
            self.session.scalars(
                select(FinanceCashLine.line_uid).where(FinanceCashLine.line_uid.in_(uids))
            )
        )
        new_rows = [line for line in parsed.lines if line.line_uid not in existing]
        self._refresh_texts([line for line in parsed.lines if line.line_uid in existing])
        self.session.add_all(
            self._line_row(line, batch.import_id, raw.file_id) for line in new_rows
        )
        self.session.flush()
        self.session.add_all(
            FinanceCashLineOccurrence(
                line_uid=line.line_uid,
                raw_file_id=raw.file_id,
                import_id=batch.import_id,
                statement_row_no=line.statement_row_no,
                file_row_order=line.file_row_order,
            )
            for line in parsed.lines
        )
        self.session.flush()
        for uid in existing:
            self._refresh_attribution(uid)
        rows_new, rows_duplicate = len(new_rows), len(existing)
        self.session.add(
            FinanceCashImportQuality(
                file_id=raw.file_id,
                rows_parsed=len(parsed.lines),
                rows_new=rows_new,
                rows_duplicate=rows_duplicate,
                balance_chain_ok=parsed.balance_chain_ok,
                warnings=parsed.warnings,
            )
        )
        self.session.flush()
        return CashflowFileResult(
            file_id=raw.file_id,
            file_name=file_name,
            sha256=sha256,
            size=len(content),
            status=STATUS_PARSED,
            account_keys=account_keys,
            detected_note=parsed.note,
            rows_parsed=len(parsed.lines),
            rows_new=rows_new,
            rows_duplicate=rows_duplicate,
            declared_range_from=raw.declared_range_from,
            declared_range_to=raw.declared_range_to,
            balance_chain_ok=parsed.balance_chain_ok,
            warnings=parsed.warnings,
        )

    def _refresh_texts(self, lines: Iterable[Line]) -> None:
        """已有流水按这次解析刷新对方 / 摘要 / 备注。
        line_uid 按原文算，不受影响；人工改的摘要 / 备注另存，不覆盖。"""
        by_uid = {line.line_uid: line for line in lines}
        if not by_uid:
            return
        for row in self.session.scalars(
            select(FinanceCashLine).where(FinanceCashLine.line_uid.in_(list(by_uid)))
        ):
            fresh = by_uid[row.line_uid]
            row.counterparty_name = fresh.counterparty_name
            row.description = fresh.description
            row.memo = fresh.memo

    @staticmethod
    def _line_row(line: Line, import_id: UUID, file_id: UUID) -> FinanceCashLine:
        return FinanceCashLine(
            line_uid=line.line_uid,
            account_key=line.account_key,
            business_date=line.business_date,
            source_time=line.source_time_utc,
            source_timezone=line.source_timezone,
            source_time_raw=line.source_time_raw[:64],
            amount=line.amount,
            currency_code=line.currency_code,
            balance_after=line.balance_after,
            counterparty_name=line.counterparty_name,
            counterparty_account_last4=line.counterparty_account_last4,
            description=line.description,
            memo=line.memo,
            source_ref=line.source_ref,
            dup_ordinal=line.dup_ordinal,
            statement_row_no=line.statement_row_no,
            file_row_order=line.file_row_order,
            first_import_id=import_id,
            first_raw_file_id=file_id,
            last_import_id=import_id,
            last_raw_file_id=file_id,
            parser_version=PARSER_VERSION,
        )

    def _refresh_attribution(self, line_uid: str) -> None:
        line = self.session.get(FinanceCashLine, line_uid)
        if line is None:
            return
        occurrences = self.session.scalars(
            select(FinanceCashLineOccurrence)
            .join(
                FinanceCashImport,
                FinanceCashImport.import_id == FinanceCashLineOccurrence.import_id,
            )
            .where(
                FinanceCashLineOccurrence.line_uid == line_uid,
                FinanceCashImport.status != STATUS_VOIDED,
            )
            .order_by(FinanceCashLineOccurrence.seen_seq)
        ).all()
        if not occurrences:
            line.voided_at = line.voided_at or datetime.now(UTC)
            return
        first, last = occurrences[0], occurrences[-1]
        line.first_import_id, line.first_raw_file_id = first.import_id, first.raw_file_id
        line.last_import_id, line.last_raw_file_id = last.import_id, last.raw_file_id
        line.file_row_order, line.statement_row_no = last.file_row_order, last.statement_row_no
        line.voided_at = None

    def void_import(self, import_id: UUID, *, reason: str, actor: str) -> CashflowVoidData:
        batch = self.session.get(FinanceCashImport, import_id, with_for_update=True)
        if batch is None:
            raise ImportNotFoundError
        if batch.status == STATUS_VOIDED:
            raise ImportVoidedError
        blocked = self._reviewed_lines_only_in(import_id)
        if blocked:
            self.session.rollback()
            raise ImportHasReviewedLinesError(blocked)
        batch.status = STATUS_VOIDED
        batch.voided_at = datetime.now(UTC)
        batch.voided_by = actor
        batch.void_reason = reason.strip()
        self.session.flush()
        uids = list(
            self.session.scalars(
                select(FinanceCashLineOccurrence.line_uid)
                .where(FinanceCashLineOccurrence.import_id == import_id)
                .distinct()
            )
        )
        for uid in uids:
            self._refresh_attribution(uid)
        self.session.commit()
        return CashflowVoidData(import_id=import_id, lines_affected=len(uids))

    def _reviewed_lines_only_in(self, import_id: UUID) -> list[str]:
        """只属于这一批、且已初审或终审的流水。也出现在别的未作废批次的，作废时只退归属，不拦。"""
        uids = set(
            self.session.scalars(
                select(FinanceCashLineOccurrence.line_uid).where(
                    FinanceCashLineOccurrence.import_id == import_id
                )
            )
        )
        if not uids:
            return []
        shared = set(
            self.session.scalars(
                select(FinanceCashLineOccurrence.line_uid)
                .join(
                    FinanceCashImport,
                    FinanceCashImport.import_id == FinanceCashLineOccurrence.import_id,
                )
                .where(
                    FinanceCashLineOccurrence.line_uid.in_(uids),
                    FinanceCashLineOccurrence.import_id != import_id,
                    FinanceCashImport.status != STATUS_VOIDED,
                )
            )
        )
        only_here = sorted(uids - shared)
        if not only_here:
            return []
        # 锁住流水行：审核动作也先锁这一行，检查和作废之间不会插进新的审核。
        self.session.execute(
            select(FinanceCashLine.line_uid)
            .where(FinanceCashLine.line_uid.in_(only_here))
            .order_by(FinanceCashLine.line_uid)
            .with_for_update()
        )
        return list(
            self.session.scalars(
                select(FinanceCashLineState.line_uid)
                .where(
                    FinanceCashLineState.line_uid.in_(only_here),
                    FinanceCashLineState.stage.in_([journal.STAGE_OK1, journal.STAGE_OK2]),
                )
                .order_by(FinanceCashLineState.line_uid)
            )
        )

    def _file_result(self, raw: FinanceCashRawFile) -> CashflowFileResult:
        quality = self.session.get(FinanceCashImportQuality, raw.file_id)
        return CashflowFileResult(
            file_id=raw.file_id,
            file_name=raw.file_name,
            sha256=raw.sha256,
            size=raw.size_bytes,
            status=raw.status,
            reject_reason=raw.reject_reason,
            account_keys=list(raw.account_keys or []),
            rows_parsed=quality.rows_parsed if quality else 0,
            rows_new=quality.rows_new if quality else 0,
            rows_duplicate=quality.rows_duplicate if quality else 0,
            declared_range_from=raw.declared_range_from,
            declared_range_to=raw.declared_range_to,
            balance_chain_ok=quality.balance_chain_ok if quality else None,
            warnings=list(quality.warnings or []) if quality else [],
        )

    def _import_read(self, batch: FinanceCashImport) -> CashflowImportRead:
        files = self.session.scalars(
            select(FinanceCashRawFile)
            .where(FinanceCashRawFile.import_id == batch.import_id)
            .order_by(FinanceCashRawFile.created_at, FinanceCashRawFile.file_name)
        ).all()
        return CashflowImportRead(
            import_id=batch.import_id,
            uploader=batch.uploader,
            status=batch.status,
            created_at=batch.created_at,
            voided_at=batch.voided_at,
            void_reason=batch.void_reason,
            files=[self._file_result(raw) for raw in files],
        )

    def get_import(self, import_id: UUID) -> CashflowImportRead:
        batch = self.session.get(FinanceCashImport, import_id)
        if batch is None:
            raise ImportNotFoundError
        return self._import_read(batch)

    def list_imports(
        self,
        *,
        status: str | None,
        from_date: date | None,
        to_date: date | None,
        page: int,
        page_size: int,
    ) -> CashflowImportListData:
        filters = []
        if status:
            filters.append(FinanceCashImport.status == status)
        if from_date:
            start = datetime(from_date.year, from_date.month, from_date.day, tzinfo=SHANGHAI)
            filters.append(FinanceCashImport.created_at >= start)
        if to_date:
            end = datetime(to_date.year, to_date.month, to_date.day, tzinfo=SHANGHAI)
            filters.append(FinanceCashImport.created_at < end + timedelta(days=1))
        total = self.session.scalar(
            select(func.count()).select_from(FinanceCashImport).where(*filters)
        )
        rows = self.session.scalars(
            select(FinanceCashImport)
            .where(*filters)
            .order_by(FinanceCashImport.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return CashflowImportListData(
            items=[self._import_read(row) for row in rows],
            total=total or 0,
            page=page,
            page_size=page_size,
        )

    # ------------------------------------------------------------ 日记账读取

    def _usd_rate_lookup(self) -> Callable[[date], Decimal | None]:
        rates = load_usd_cny_rates(self.session)
        return lambda day: usd_cny_rate_for(rates, day)

    def _compute(
        self,
    ) -> tuple[journal.JournalResult, dict[str, FinanceCashLine], dict[str, FinanceCashLineState]]:
        rows = self.session.execute(
            select(
                FinanceCashLine, FinanceCashAccount.provider, FinanceCashAccount.account_no_last4
            )
            .join(
                FinanceCashAccount,
                FinanceCashAccount.account_key == FinanceCashLine.account_key,
            )
            .where(FinanceCashLine.voided_at.is_(None))
        ).all()
        states = {
            state.line_uid: state for state in self.session.scalars(select(FinanceCashLineState))
        }
        rules = [
            journal.Rule(rule.rule_type, rule.pattern, rule.category_code, rule.sort_order)
            for rule in self.session.scalars(select(FinanceCashClassifyRule))
        ]
        classifier = journal.Classifier(rules)
        approval_cats = self._approval_categories(classifier)
        inputs: list[journal.LineInput] = []
        by_uid: dict[str, FinanceCashLine] = {}
        for line, provider, account_last4 in rows:
            state = states.get(line.line_uid)
            by_uid[line.line_uid] = line
            refs = list(state.refs or []) if state else []
            from_refs = [approval_cats[ref] for ref in refs if ref in approval_cats]
            inputs.append(
                journal.LineInput(
                    line_uid=line.line_uid,
                    account_key=line.account_key,
                    provider=provider,
                    currency_code=line.currency_code,
                    business_date=line.business_date,
                    amount=line.amount,
                    balance_after=line.balance_after,
                    description=line.description,
                    memo=line.memo,
                    counterparty_name=line.counterparty_name,
                    file_row_order=line.file_row_order,
                    manual_category=state.manual_category if state else None,
                    refs=refs,
                    exclude_amount=state.exclude_amount if state else None,
                    approval_category=approval_rules.single_value(c[0] for c in from_refs),
                    approval_rule_category=approval_rules.single_value(c[1] for c in from_refs),
                    parts=_parts_with_approval(state.parts, approval_cats)
                    if state and state.parts
                    else None,
                    manual_pair=state.manual_pair if state else None,
                    counterparty_last4=line.counterparty_account_last4 or "",
                    account_last4=account_last4 or "",
                    source_time=line.source_time,
                    manual_amount_cny=state.manual_amount_cny if state else None,
                )
            )
        internal = frozenset(
            self.session.scalars(
                select(FinanceCashCategory.code).where(FinanceCashCategory.is_internal.is_(True))
            )
        )
        exclusions = [
            journal.ExclusionEntry(
                entry_no=index,
                ref=row.ref,
                txn_date=row.txn_date,
                account_key=row.account_key,
                summary_contains=row.summary_contains,
                amount_cny=row.amount_cny,
                reason=row.reason,
                registered_on=row.registered_on,
            )
            for index, row in enumerate(
                self.session.scalars(
                    select(FinanceCashExclusion).order_by(FinanceCashExclusion.id)
                ),
                start=1,
            )
        ]
        result = journal.compute_journal(
            inputs,
            classifier,
            internal,
            self._usd_rate_lookup(),
            exclusions,
            self._statement_rows(),
            datetime.now(SHANGHAI).date(),
        )
        self._flag_auto_attached(result)
        return result, by_uid, states

    def _statement_rows(self) -> list[journal.StatementRow]:
        """未作废批次里的派安盈月结明细行。"""
        rows = self.session.scalars(
            select(FinancePayoneerStatementRow)
            .join(
                FinanceCashImport,
                FinanceCashImport.import_id == FinancePayoneerStatementRow.import_id,
            )
            .where(FinanceCashImport.status != STATUS_VOIDED)
            .order_by(FinancePayoneerStatementRow.id)
        ).all()
        return [
            journal.StatementRow(
                row_key=f"{row.raw_file_id}:{row.row_no}",
                account_key=row.account_key,
                txn_id=row.txn_id,
                txn_time=row.txn_time,
                business_date=row.business_date,
                description=row.description,
                amount=row.amount,
                currency_code=row.currency_code,
                transfer_amount=row.transfer_amount,
                transfer_currency=row.transfer_currency,
            )
            for row in rows
        ]

    def approval_rows(self) -> list[FinanceCashApproval]:
        """进日记账报销闭环的审批单：排除配置里不走这边账的部门。"""
        raw = self.settings.finance_approval_excluded_department_ids or ""
        excluded = {item.strip() for item in raw.split(",") if item.strip()}
        rows = self.session.scalars(select(FinanceCashApproval)).all()
        return [row for row in rows if row.department_id not in excluded]

    def match_approvals(self) -> list[approval_rules.MatchApproval]:
        out: list[approval_rules.MatchApproval] = []
        for row in self.approval_rows():
            anchor = row.completed_at or row.started_at
            out.append(
                approval_rules.MatchApproval(
                    serial=row.serial_number,
                    status=row.status,
                    amount=row.amount,
                    currency_code=row.currency_code,
                    payee=row.payee,
                    anchor_day=anchor.astimezone(SHANGHAI).date() if anchor else None,
                )
            )
        return out

    def _approval_categories(
        self, classifier: journal.Classifier
    ) -> dict[str, tuple[str | None, str | None]]:
        """单号 → (表单写明的类别, 按事由和明细跑规则的类别)。"""
        names_to_code = {
            row.name: row.code
            for row in self.session.scalars(select(FinanceCashCategory))
            if not row.is_exclude
        }
        out: dict[str, tuple[str | None, str | None]] = {}
        for row in self.session.scalars(select(FinanceCashApproval)):
            details = " ".join(str(item.get("content") or "") for item in row.items or [])
            out[row.serial_number] = (
                approval_rules.form_category_code(row.fee_category, names_to_code),
                classifier.classify(f"{row.reason} {details}", ""),
            )
        return out

    def _flag_auto_attached(self, result: journal.JournalResult) -> None:
        auto = {
            (line_uid, str((payload or {}).get("ref") or ""))
            for line_uid, payload in self.session.execute(
                select(FinanceCashLineEvent.line_uid, FinanceCashLineEvent.payload).where(
                    FinanceCashLineEvent.kind == journal.KIND_AUTO_ATTACH_REF
                )
            )
        }
        if not auto:
            return
        for item in result.lines:
            if any((item.source.line_uid, ref) in auto for ref in item.source.refs):
                item.flags.append("自动匹配")

    def _approval_candidates(self, result: journal.JournalResult) -> dict[str, list[str]]:
        approvals = self.match_approvals()
        if not approvals:
            return {}
        lines = [
            approval_rules.MatchLine(
                line_uid=item.source.line_uid,
                business_date=item.source.business_date,
                amount=item.source.amount,
                currency_code=item.source.currency_code,
                counterparty_name=item.source.counterparty_name,
                text="",
                refs=(*item.source.refs, *journal.part_refs(item.source.parts)),
                stage="",
                amount_cny=item.amount_cny,
                cny_exact=item.fx_source in journal.FX_EXACT_SOURCES,
            )
            for item in result.lines
        ]
        return approval_rules.candidates_by_line(lines, approvals)

    def list_lines(
        self,
        *,
        account_key: str | None,
        from_date: date | None,
        to_date: date | None,
        page: int,
        page_size: int,
    ) -> CashflowLineListData:
        result, by_uid, states = self._compute()
        selected = [
            item
            for item in result.lines
            if (not account_key or item.source.account_key == account_key)
            and (from_date is None or item.source.business_date >= from_date)
            and (to_date is None or item.source.business_date <= to_date)
        ]
        selected.sort(
            key=lambda item: (
                item.source.business_date,
                by_uid[item.source.line_uid].source_time or datetime.min.replace(tzinfo=UTC),
                item.source.file_row_order,
                item.source.line_uid,
            ),
            reverse=True,
        )
        window = selected[(page - 1) * page_size : page * page_size]
        candidates = self._approval_candidates(result)
        return CashflowLineListData(
            items=[
                self._line_read(
                    item,
                    by_uid[item.source.line_uid],
                    states.get(item.source.line_uid),
                    candidates.get(item.source.line_uid, []),
                )
                for item in window
            ],
            total=len(selected),
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def _line_read(
        item: journal.ComputedLine,
        line: FinanceCashLine,
        state: FinanceCashLineState | None,
        candidates: list[str] | None = None,
    ) -> CashflowLineRead:
        local_time = line.source_time.astimezone(SHANGHAI) if line.source_time else None
        return CashflowLineRead(
            line_uid=line.line_uid,
            account_key=line.account_key,
            business_date=line.business_date,
            month=line.business_date.isoformat()[:7],
            time=local_time.strftime("%H:%M:%S") if local_time else None,
            currency_code=line.currency_code,
            amount=line.amount,
            amount_cny=item.amount_cny,
            fx_rate=item.fx_rate,
            fx_source=item.fx_source,
            balance_after=line.balance_after,
            description=line.description,
            memo=line.memo,
            counterparty_name=line.counterparty_name,
            counterparty_account_last4=line.counterparty_account_last4,
            source_ref=line.source_ref,
            file_row_order=line.file_row_order,
            category_code=item.category_code,
            category_source=item.category_source,
            pair_id=item.pair_id,
            flags=item.flags,
            refs=list(state.refs or []) if state else [],
            exclude_amount=state.exclude_amount if state else None,
            exclude_reason=state.exclude_reason if state else None,
            list_excluded_cny=item.list_excluded_cny,
            stage=state.stage if state else journal.STAGE_TODO,
            stage_reason=state.stage_reason if state else None,
            review_note=state.review_note if state else None,
            manual_description=state.manual_description if state else None,
            manual_memo=state.manual_memo if state else None,
            parts=[CashflowLinePartRead(**part) for part in item.source.parts]
            if item.source.parts
            else None,
            manual_pair=state.manual_pair if state else None,
            manual_cny_reason=state.manual_cny_reason if state else None,
            auto_exclude_reason=item.auto_exclude_reason,
            version=state.version if state else 0,
            approval_candidates=candidates or [],
        )

    # ------------------------------------------------------------ 关闭异常（Rocky 11-10）

    def list_alert_closures(self) -> list[CashflowAlertClosureRead]:
        rows = self.session.scalars(
            select(FinanceCashAlertClosure)
            .where(FinanceCashAlertClosure.reopened_at.is_(None))
            .order_by(FinanceCashAlertClosure.closed_at.desc())
        )
        return [
            CashflowAlertClosureRead(
                alert_key=row.alert_key,
                alert_type=row.alert_type,
                reason=row.reason,
                closed_by=row.closed_by,
                closed_at=row.closed_at,
            )
            for row in rows
        ]

    def _open_closure(self, key: str) -> FinanceCashAlertClosure | None:
        return self.session.scalars(
            select(FinanceCashAlertClosure)
            .where(
                FinanceCashAlertClosure.alert_key == key,
                FinanceCashAlertClosure.reopened_at.is_(None),
            )
            .with_for_update()
        ).first()

    def close_alert(self, request: CashflowAlertCloseRequest, *, actor: str) -> None:
        reason = request.reason.strip()
        if not reason:
            raise AlertClosureError(422, "关闭异常要写原因")
        self._check_alert_target(request.alert_type, request.alert_key)
        if self._open_closure(request.alert_key) is not None:
            raise AlertClosureError(409, "这条异常已经关闭了")
        self.session.add(
            FinanceCashAlertClosure(
                alert_key=request.alert_key,
                alert_type=request.alert_type,
                reason=reason,
                closed_by=actor,
            )
        )
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise AlertClosureError(409, "这条异常已经关闭了") from exc

    def _check_alert_target(self, alert_type: str, alert_key: str) -> None:
        """关闭前确认这条异常指向的东西存在（刘云龙 #339 终审，轻量版）。

        编号就是页面上异常的编号「类型|编号」：编号是流水（账户:日期:流水号后 6 位）、
        审批单号（12 位）、剔除清单（剔除:日期:第几条），或者「账户:日期:金额」。
        只查对象存不存在，不在后端重算页面算出来的异常此刻是否成立。"""
        if alert_type not in KNOWN_ALERT_TYPES:
            raise AlertClosureError(422, "不认识的异常类型")
        prefix = f"{alert_type}|"
        if not alert_key.startswith(prefix) or len(alert_key) == len(prefix):
            raise AlertClosureError(422, "异常编号和异常类型对不上")
        ref = alert_key[len(prefix) :]
        if APPROVAL_SERIAL.fullmatch(ref):
            found = self.session.scalar(
                select(func.count())
                .select_from(FinanceCashApproval)
                .where(FinanceCashApproval.serial_number == ref)
            )
            if not found:
                raise AlertClosureError(404, "找不到这条异常对应的审批单")
            return
        if ref.startswith("剔除:"):
            number = ref.rsplit(":", 1)[-1]
            total = self.session.scalar(select(func.count()).select_from(FinanceCashExclusion))
            if not number.isdigit() or not 1 <= int(number) <= (total or 0):
                raise AlertClosureError(404, "找不到这条异常对应的剔除清单")
            return
        account, _sep, rest = ref.partition(":")
        day, _sep, tail = rest.partition(":")
        try:
            business_date: date | None = date.fromisoformat(day)
        except ValueError:
            business_date = None
        if business_date is not None and LINE_TAIL.fullmatch(tail):
            line = self.session.scalars(
                select(FinanceCashLine).where(
                    FinanceCashLine.account_key == account,
                    FinanceCashLine.business_date == business_date,
                    FinanceCashLine.line_uid.endswith(tail),
                )
            ).first()
            if line is not None:
                if line.voided_at is not None:
                    raise AlertClosureError(404, "找不到这条异常对应的流水（已作废）")
                return
            if not tail.isdigit():
                # 带字母的 6 位只能是流水号后 6 位（金额不会有字母）：找不到就是流水不存在。
                raise AlertClosureError(404, "找不到这条异常对应的流水")
        if self.session.get(FinanceCashAccount, account) is None:
            raise AlertClosureError(404, "找不到这条异常对应的流水 / 审批单 / 账户")

    def reopen_alert(self, request: CashflowAlertReopenRequest, *, actor: str) -> None:
        reason = request.reason.strip()
        if not reason:
            raise AlertClosureError(422, "重新打开要写原因")
        row = self._open_closure(request.alert_key)
        if row is None:
            raise AlertClosureError(404, "这条异常没有关闭记录")
        row.reopened_at, row.reopened_by, row.reopen_reason = datetime.now(UTC), actor, reason
        self.session.commit()

    def list_anomalies(self) -> list[CashflowAnomalyRead]:
        result, _, _ = self._compute()
        return [
            CashflowAnomalyRead(
                type=alert.type,
                account_key=alert.account_key,
                date=alert.date,
                message=alert.message,
                amount=alert.amount,
                currency_code=alert.currency_code,
                line_uid=alert.line_uid,
            )
            for alert in result.alerts
        ]

    def list_categories(self) -> list[CashflowCategoryRead]:
        rows = self.session.scalars(
            select(FinanceCashCategory).order_by(FinanceCashCategory.sort_order)
        ).all()
        return [
            CashflowCategoryRead(
                code=row.code,
                big=row.big,
                name=row.name,
                is_internal=row.is_internal,
                is_exclude=row.is_exclude,
            )
            for row in rows
        ]

    def list_accounts(self) -> list[CashflowAccountRead]:
        accounts = self.session.scalars(
            select(FinanceCashAccount).order_by(
                FinanceCashAccount.sort_order, FinanceCashAccount.account_key
            )
        ).all()
        stats = {
            row.account_key: row
            for row in self.session.execute(
                select(
                    FinanceCashLine.account_key,
                    func.count().label("line_count"),
                    func.min(FinanceCashLine.business_date).label("first_day"),
                    func.max(FinanceCashLine.business_date).label("last_day"),
                )
                .where(FinanceCashLine.voided_at.is_(None))
                .group_by(FinanceCashLine.account_key)
            )
        }
        files = self.session.scalars(
            select(FinanceCashRawFile)
            .join(
                FinanceCashImport,
                FinanceCashImport.import_id == FinanceCashRawFile.import_id,
            )
            .where(
                FinanceCashRawFile.status == STATUS_PARSED,
                FinanceCashImport.status != STATUS_VOIDED,
            )
            .order_by(FinanceCashRawFile.created_at)
        ).all()
        out: list[CashflowAccountRead] = []
        for account in accounts:
            stat = stats.get(account.account_key)
            own_files = [raw for raw in files if account.account_key in (raw.account_keys or [])]
            declared_to = [raw.declared_range_to for raw in own_files if raw.declared_range_to]
            cover_to = stat.last_day if stat else None
            source = "首末笔" if stat else None
            if stat and declared_to and max(declared_to) >= stat.last_day:
                cover_to, source = max(declared_to), "表头"
            out.append(
                CashflowAccountRead(
                    account_key=account.account_key,
                    display_name=account.display_name,
                    entity=account.entity,
                    currency_code=account.currency_code,
                    kind=account.kind,
                    provider=account.provider,
                    account_no_last4=account.account_no_last4,
                    is_active=account.is_active,
                    line_count=stat.line_count if stat else 0,
                    last_file_name=own_files[-1].file_name if own_files else None,
                    cover_from=stat.first_day if stat else None,
                    cover_to=cover_to,
                    cover_source=source,
                )
            )
        return out

    # ------------------------------------------------------------ 人工动作

    def _state_for_update(self, line_uid: str) -> FinanceCashLineState:
        self.session.execute(
            pg_insert(FinanceCashLineState)
            .values(line_uid=line_uid)
            .on_conflict_do_nothing(index_elements=["line_uid"])
        )
        state = self.session.get(
            FinanceCashLineState, line_uid, with_for_update=True, populate_existing=True
        )
        if state is None:  # pragma: no cover - 上一句刚写入
            raise LineNotFoundError
        return state

    def post_event(
        self,
        line_uid: str,
        request: CashflowLineEventRequest,
        *,
        actor: str,
        request_id: str | None,
    ) -> CashflowLineEventData:
        if request.kind == journal.KIND_AUTO_RESET:
            raise journal.EventRejectedError(422, "不支持的操作")
        if request.kind in {journal.KIND_PAIR, journal.KIND_UNPAIR}:
            # 只留批量接口一条路，否则一笔一笔发又可能只成功一半。
            raise journal.EventRejectedError(422, "配对和取消配对要走 /lines/pair-events")
        line = self.session.get(FinanceCashLine, line_uid, with_for_update=True)
        if line is None or line.voided_at is not None:
            raise LineNotFoundError
        state = self._state_for_update(line_uid)
        replayed = self._replay_if_seen(line_uid, request)
        if replayed is not None:
            return replayed
        if request.expected_version != state.version:
            raise journal.EventRejectedError(
                409, "这笔已被别人改过，请刷新后再操作", journal.ERR_VERSION_CONFLICT
            )
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
            manual_amount_cny=state.manual_amount_cny,
            manual_cny_reason=state.manual_cny_reason,
        )
        if request.kind == journal.KIND_SET_CNY and line.currency_code in {"CNY", "CNH"}:
            raise journal.EventRejectedError(422, "人民币流水不用改折人民币")
        auto_reset = journal.apply_event(
            draft,
            kind=request.kind,
            payload=request.payload,
            reason=request.reason,
            line_amount=line.amount,
            valid_categories=self._category_codes(),
        )
        state.manual_category = draft.manual_category
        state.refs = draft.refs
        state.exclude_amount = draft.exclude_amount
        state.exclude_reason = draft.exclude_reason
        state.stage = draft.stage
        state.stage_reason = draft.stage_reason
        state.review_note = draft.review_note
        state.manual_description = draft.manual_description
        state.manual_memo = draft.manual_memo
        state.parts = draft.parts
        state.manual_pair = draft.manual_pair
        state.manual_amount_cny = draft.manual_amount_cny
        state.manual_cny_reason = draft.manual_cny_reason
        state.version += 1
        state.updated_at = datetime.now(UTC)
        self._add_events(line_uid, request, auto_reset, actor, request_id)
        data = CashflowLineEventData(
            line_uid=line_uid,
            stage=state.stage,
            stage_reason=state.stage_reason,
            version=state.version,
            auto_reset=auto_reset,
        )
        try:
            self.session.commit()
        except IntegrityError:
            # 并发时两个请求可能都没查到同一个幂等键，后到的在这里撞唯一索引，按重放处理。
            self.session.rollback()
            replayed = self._replay_if_seen(line_uid, request)
            if replayed is None:
                raise
            return replayed
        return data

    def post_pair_event(
        self,
        request: CashflowPairEventRequest,
        *,
        actor: str,
        request_id: str | None,
    ) -> CashflowPairEventData:
        """配对 / 取消配对：几笔在同一个事务里，有一笔不行就全部回滚，什么都不改。"""
        try:
            return self._apply_pair_event(request, actor=actor, request_id=request_id)
        except (journal.EventRejectedError, LineNotFoundError):
            self.session.rollback()
            raise

    def _apply_pair_event(
        self,
        request: CashflowPairEventRequest,
        *,
        actor: str,
        request_id: str | None,
    ) -> CashflowPairEventData:
        expected = {item.line_uid: item.expected_version for item in request.lines}
        if len(expected) != len(request.lines):
            raise journal.EventRejectedError(422, "同一笔不能写两次")
        # 按流水号排序加锁，两个请求同时配到同一笔也不会互相等死。
        uids = sorted(expected)
        lines: list[FinanceCashLine] = []
        for uid in uids:
            line = self.session.get(FinanceCashLine, uid, with_for_update=True)
            if line is None or line.voided_at is not None:
                raise LineNotFoundError
            lines.append(line)
        states = {uid: self._state_for_update(uid) for uid in uids}
        replayed = self._replay_pair_if_seen(request, uids)
        if replayed is not None:
            return replayed
        if any(states[uid].version != expected[uid] for uid in uids):
            raise journal.EventRejectedError(
                409, "有一笔已被别人改过，请刷新后再操作", journal.ERR_VERSION_CONFLICT
            )
        if request.kind == journal.KIND_PAIR:
            pair_id = self._new_pair_id(lines, states)
        else:
            pair_id = self._whole_pair_id(uids, states)
        payload = {"pair_id": pair_id, "line_uids": uids}
        now = datetime.now(UTC)
        for line in lines:
            state = states[line.line_uid]
            draft = journal.ReviewState(stage=state.stage, manual_pair=state.manual_pair)
            journal.apply_event(
                draft,
                kind=request.kind,
                payload=payload,
                reason=request.reason,
                line_amount=line.amount,
                valid_categories=frozenset(),
            )
            state.manual_pair = draft.manual_pair
            state.version += 1
            state.updated_at = now
            self.session.add(
                FinanceCashLineEvent(
                    line_uid=line.line_uid,
                    kind=request.kind,
                    payload=payload,
                    reason=(request.reason or "").strip() or None,
                    actor=actor,
                    request_id=request_id,
                    idempotency_key=(
                        f"{request.idempotency_key}:{line.line_uid}"
                        if request.idempotency_key
                        else None
                    ),
                )
            )
        data = CashflowPairEventData(
            kind=request.kind,
            pair_id=pair_id,
            lines=[
                CashflowLineEventData(
                    line_uid=uid,
                    stage=states[uid].stage,
                    stage_reason=states[uid].stage_reason,
                    version=states[uid].version,
                )
                for uid in uids
            ],
        )
        try:
            self.session.commit()
        except IntegrityError:
            # 并发的同一个幂等键，后到的撞唯一索引，整个事务回滚后按重放处理。
            self.session.rollback()
            replayed = self._replay_pair_if_seen(request, uids)
            if replayed is None:
                raise
            return replayed
        return data

    @staticmethod
    def _new_pair_id(
        lines: Sequence[FinanceCashLine], states: Mapping[str, FinanceCashLineState]
    ) -> str:
        if len(lines) < 2:
            raise journal.EventRejectedError(422, "配对至少要两笔")
        if len({line.account_key for line in lines}) < 2:
            raise journal.EventRejectedError(422, "配对要选不同账户的流水")
        amounts = [line.amount for line in lines]
        if not (any(amount < 0 for amount in amounts) and any(amount > 0 for amount in amounts)):
            raise journal.EventRejectedError(422, "配对要一出一进")
        if any(state.manual_pair for state in states.values()):
            raise journal.EventRejectedError(
                409, "有一笔已经配对，先取消原来的配对", journal.ERR_PAIR_CONFLICT
            )
        return f"M{uuid4().hex[:20].upper()}"

    def _whole_pair_id(
        self, uids: Sequence[str], states: Mapping[str, FinanceCashLineState]
    ) -> str:
        """取消配对必须一次取消整组，不然剩下的那笔会变成落单的配对。"""
        pair_ids = {states[uid].manual_pair for uid in uids}
        if None in pair_ids:
            raise journal.EventRejectedError(409, "有一笔没有人工配对", journal.ERR_PAIR_CONFLICT)
        if len(pair_ids) != 1:
            raise journal.EventRejectedError(409, "这几笔不是同一组配对", journal.ERR_PAIR_CONFLICT)
        pair_id = str(pair_ids.pop())
        members = self.session.scalars(
            select(FinanceCashLineState.line_uid)
            .join(FinanceCashLine, FinanceCashLine.line_uid == FinanceCashLineState.line_uid)
            .where(
                FinanceCashLineState.manual_pair == pair_id,
                FinanceCashLine.voided_at.is_(None),
            )
        ).all()
        if set(members) != set(uids):
            raise journal.EventRejectedError(
                409, "这组配对的笔数变了，请刷新后再操作", journal.ERR_PAIR_CONFLICT
            )
        return pair_id

    def _replay_pair_if_seen(
        self, request: CashflowPairEventRequest, uids: Sequence[str]
    ) -> CashflowPairEventData | None:
        if not request.idempotency_key:
            return None
        seen = self.session.scalars(
            select(FinanceCashLineEvent).where(
                FinanceCashLineEvent.idempotency_key.startswith(
                    f"{request.idempotency_key}:", autoescape=True
                )
            )
        ).all()
        if not seen:
            return None
        if {item.kind for item in seen} != {request.kind} or {
            item.line_uid for item in seen
        } != set(uids):
            raise journal.EventRejectedError(
                409, "这个幂等键已经用在别的操作上", journal.ERR_IDEMPOTENCY_KEY_REUSED
            )
        pair_id = str(seen[0].payload.get("pair_id") or "")
        self.session.rollback()
        return CashflowPairEventData(
            kind=request.kind,
            pair_id=pair_id,
            lines=[self._event_data(uid, replayed=True) for uid in uids],
            replayed=True,
        )

    def _find_event_by_key(self, key: str) -> FinanceCashLineEvent | None:
        return self.session.scalars(
            select(FinanceCashLineEvent).where(FinanceCashLineEvent.idempotency_key == key)
        ).first()

    def _replay_if_seen(
        self, line_uid: str, request: CashflowLineEventRequest
    ) -> CashflowLineEventData | None:
        if not request.idempotency_key:
            return None
        seen = self._find_event_by_key(request.idempotency_key)
        if seen is None:
            return None
        if seen.line_uid != line_uid or seen.kind != request.kind:
            raise journal.EventRejectedError(
                409, "这个幂等键已经用在别的操作上", journal.ERR_IDEMPOTENCY_KEY_REUSED
            )
        self.session.rollback()
        return self._event_data(line_uid, replayed=True)

    def _category_codes(self) -> frozenset[str]:
        return frozenset(self.session.scalars(select(FinanceCashCategory.code)))

    def _add_events(
        self,
        line_uid: str,
        request: CashflowLineEventRequest,
        auto_reset: bool,
        actor: str,
        request_id: str | None,
    ) -> None:
        self.session.add(
            FinanceCashLineEvent(
                line_uid=line_uid,
                kind=request.kind,
                payload=request.payload,
                reason=(request.reason or "").strip() or None,
                actor=actor,
                request_id=request_id,
                idempotency_key=request.idempotency_key,
            )
        )
        if auto_reset:
            self.session.add(
                FinanceCashLineEvent(
                    line_uid=line_uid,
                    kind=journal.KIND_AUTO_RESET,
                    payload={"triggered_by": request.kind},
                    actor="system",
                    request_id=request_id,
                )
            )

    def _event_data(self, line_uid: str, *, replayed: bool) -> CashflowLineEventData:
        state = self.session.get(FinanceCashLineState, line_uid)
        if state is None:  # pragma: no cover - 重放时状态一定存在
            raise LineNotFoundError
        return CashflowLineEventData(
            line_uid=line_uid,
            stage=state.stage,
            stage_reason=state.stage_reason,
            version=state.version,
            replayed=replayed,
        )


def _parts_with_approval(
    parts: list[dict[str, Any]], approval_cats: dict[str, tuple[str | None, str | None]]
) -> list[dict[str, Any]]:
    """拆分行挂了审批单、自己没选类别的：类别跟着审批单走（表单写明的优先，其次按事由跑规则）。"""
    out = []
    for raw in parts:
        part = dict(raw)
        refs = part.get("refs") or []
        if refs and not part.get("category_code"):
            cats = [approval_cats[ref] for ref in refs if ref in approval_cats]
            form = approval_rules.single_value(c[0] for c in cats)
            ruled = approval_rules.single_value(c[1] for c in cats)
            if form:
                part["category_code"], part["category_source"] = form, journal.SOURCE_APPROVAL
            elif ruled:
                part["category_code"], part["category_source"] = (
                    ruled,
                    journal.SOURCE_APPROVAL_RULE,
                )
        out.append(part)
    return out

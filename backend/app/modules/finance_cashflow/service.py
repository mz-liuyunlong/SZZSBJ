from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.modules.finance_cashflow import journal
from app.modules.finance_cashflow.models import (
    FinanceCashAccount,
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
)
from app.modules.finance_cashflow.parsing import PARSER_VERSION, readers
from app.modules.finance_cashflow.parsing.model import Line, RejectFile
from app.modules.finance_cashflow.parsing.pipeline import ParsedFile, parse_file
from app.modules.finance_cashflow.parsing.seed import Seed, SeedAccount
from app.modules.finance_cashflow.schemas import (
    CashflowAccountRead,
    CashflowAnomalyRead,
    CashflowCategoryRead,
    CashflowFileResult,
    CashflowImportListData,
    CashflowImportRead,
    CashflowLineEventData,
    CashflowLineEventRequest,
    CashflowLineListData,
    CashflowLineRead,
    CashflowUploadData,
    CashflowVoidData,
)
from app.modules.product_management.models import ProductPricingRuleVersion

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


@dataclass(frozen=True)
class FxVersion:
    source_account_ref: str
    effective_from: datetime
    effective_to: datetime | None
    usd_cny_rate: Decimal


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _next_month(first_of_month: date) -> date:
    return (first_of_month + timedelta(days=32)).replace(day=1)


def month_usd_rate(versions: Iterable[FxVersion], day: date) -> Decimal | None:
    """当月生效的统一美元汇率；当月没有就是空，不兜底。

    表按店存多行，但汇率全公司统一（Rocky 2026-11-04），所以取当月内最新生效的那一行，不按店比对。
    """
    start = _month_start(day)
    begin = datetime(start.year, start.month, 1, tzinfo=SHANGHAI)
    following = _next_month(start)
    end = datetime(following.year, following.month, 1, tzinfo=SHANGHAI)
    in_month = [
        version
        for version in versions
        if version.effective_from < end
        and (version.effective_to is None or version.effective_to > begin)
    ]
    if not in_month:
        return None
    return max(in_month, key=lambda version: version.effective_from).usd_cny_rate


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
            result = self._file_result(duplicate)
            result.duplicate_of_file = True
            result.file_name = file_name
            result.rows_duplicate = result.rows_parsed
            result.rows_new = 0
            self._refresh_batch_status(batch, True)
            self.session.commit()
            return CashflowUploadData(import_id=batch.import_id, file=result)
        storage_path = store_original(Path(root), sha256, readers.kind_of(content), content)
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
        rows = self.session.scalars(
            select(ProductPricingRuleVersion).where(
                ProductPricingRuleVersion.is_active.is_(True),
                ProductPricingRuleVersion.usd_cny_rate.is_not(None),
            )
        ).all()
        versions = [
            FxVersion(
                source_account_ref=row.source_account_ref,
                effective_from=row.effective_from,
                effective_to=row.effective_to,
                usd_cny_rate=row.usd_cny_rate,
            )
            for row in rows
            if row.usd_cny_rate is not None
        ]
        cache: dict[date, Decimal | None] = {}

        def lookup(day: date) -> Decimal | None:
            key = _month_start(day)
            if key not in cache:
                cache[key] = month_usd_rate(versions, key)
            return cache[key]

        return lookup

    def _compute(
        self,
    ) -> tuple[journal.JournalResult, dict[str, FinanceCashLine], dict[str, FinanceCashLineState]]:
        rows = self.session.execute(
            select(FinanceCashLine, FinanceCashAccount.provider)
            .join(
                FinanceCashAccount,
                FinanceCashAccount.account_key == FinanceCashLine.account_key,
            )
            .where(FinanceCashLine.voided_at.is_(None))
        ).all()
        states = {
            state.line_uid: state for state in self.session.scalars(select(FinanceCashLineState))
        }
        inputs: list[journal.LineInput] = []
        by_uid: dict[str, FinanceCashLine] = {}
        for line, provider in rows:
            state = states.get(line.line_uid)
            by_uid[line.line_uid] = line
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
                    refs=list(state.refs or []) if state else [],
                    exclude_amount=state.exclude_amount if state else None,
                )
            )
        rules = [
            journal.Rule(rule.rule_type, rule.pattern, rule.category_code, rule.sort_order)
            for rule in self.session.scalars(select(FinanceCashClassifyRule))
        ]
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
            journal.Classifier(rules),
            internal,
            self._usd_rate_lookup(),
            exclusions,
        )
        return result, by_uid, states

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
        return CashflowLineListData(
            items=[
                self._line_read(
                    item, by_uid[item.source.line_uid], states.get(item.source.line_uid)
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
            version=state.version if state else 0,
        )

    def list_anomalies(self) -> list[CashflowAnomalyRead]:
        result, _, _ = self._compute()
        return [
            CashflowAnomalyRead(
                type=alert.type,
                account_key=alert.account_key,
                date=alert.date,
                message=alert.message,
                amount=alert.amount,
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
        line = self.session.get(FinanceCashLine, line_uid, with_for_update=True)
        if line is None or line.voided_at is not None:
            raise LineNotFoundError
        state = self._state_for_update(line_uid)
        if request.idempotency_key:
            replay = self.session.scalars(
                select(FinanceCashLineEvent).where(
                    FinanceCashLineEvent.idempotency_key == request.idempotency_key
                )
            ).first()
            if replay is not None:
                if replay.line_uid != line_uid or replay.kind != request.kind:
                    raise journal.EventRejectedError(409, "这个幂等键已经用在别的操作上")
                self.session.rollback()
                return self._event_data(line_uid, replayed=True)
        if request.expected_version is not None and request.expected_version != state.version:
            raise journal.EventRejectedError(409, "这笔已被别人改过，请刷新后再操作")
        draft = journal.ReviewState(
            manual_category=state.manual_category,
            refs=list(state.refs or []),
            exclude_amount=state.exclude_amount,
            exclude_reason=state.exclude_reason,
            stage=state.stage,
            stage_reason=state.stage_reason,
            review_note=state.review_note,
        )
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
        self.session.commit()
        return data

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

"""任务中心同步任务：把飞书四种资金审批单写进财务审批单表，然后自动挂单。

写法照 PMC 采购同步：运行记录 + 分步记录 + 状态流转；手动、定时、重试都走这里。
飞书审批列表一次最多查 30 天，所以时间窗口切成 30 天一段，每段一个分步记录。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import AppEnvironment, get_settings
from app.integrations.feishu_approval import (
    FeishuApprovalClient,
    FeishuApprovalError,
    HttpFeishuApprovalClient,
)
from app.modules.finance_cashflow import approvals as A
from app.modules.finance_cashflow.approval_service import ApprovalService
from app.modules.finance_cashflow.models import FinanceCashApproval
from app.modules.integration_sync.finance_approval_catalog import (
    FINANCE_APPROVAL_PROVIDER,
    FINANCE_APPROVAL_SYNC_SPEC,
    FinanceApprovalCodesError,
    parse_finance_approval_codes,
)
from app.modules.integration_sync.models import (
    IntegrationInterface,
    IntegrationSyncRun,
    IntegrationSyncRunWorkItem,
    utc_now,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository

logger = logging.getLogger("app.integration_sync.finance_approval")

SPEC = FINANCE_APPROVAL_SYNC_SPEC
SLICE_DAYS = 30
EXECUTABLE_TRIGGERS = frozenset({"manual", "schedule", "retry"})
# 已结束的单隔这么久就不再取详情：取消或撤销基本发生在结束后不久，省接口次数。
REFRESH_DONE_WITHIN = timedelta(days=14)


class FinanceApprovalSyncError(RuntimeError):
    """Safe error code without provider payloads."""


def _default_client() -> FeishuApprovalClient:
    settings = get_settings()
    if settings.app_env is not AppEnvironment.PRODUCTION:
        raise FinanceApprovalSyncError("SYNC_FEISHU_APPROVAL_SERVER_ENVIRONMENT_REQUIRED")
    return HttpFeishuApprovalClient(settings)


# 本地预览和测试可以换成回放客户端；正式环境只用上面这个。
client_factory: Callable[[], FeishuApprovalClient] = _default_client


def month_slices(start: datetime, end: datetime) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    step = SLICE_DAYS * 86_400_000
    cursor = start_ms
    while cursor < end_ms:
        stop = min(cursor + step - 1, end_ms)
        out.append((cursor, stop))
        cursor = stop + 1
    return out


@dataclass(slots=True)
class FinanceApprovalSyncResult:
    run_id: UUID
    status: str
    listed: int = 0
    written: int = 0
    auto_matched: int = 0


class FeishuFinanceApprovalSyncHandler:
    handler_key = SPEC.handler_key

    def __init__(self, session: Session, *, client: FeishuApprovalClient | None = None) -> None:
        self.session = session
        self.repository = IntegrationSyncRepository(session)
        self._client = client

    def execute(
        self, run: IntegrationSyncRun, interface: IntegrationInterface
    ) -> FinanceApprovalSyncResult:
        try:
            self._preflight(run, interface)
            codes = parse_finance_approval_codes(get_settings().finance_approval_codes)
            client = self._client or client_factory()
        except (FinanceApprovalSyncError, FinanceApprovalCodesError) as error:
            return self._fail(run, None, str(error))
        except FeishuApprovalError as error:
            return self._fail(run, None, error.code)
        try:
            run.status = "running"
            run.started_at = utc_now()
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            recovered = self.repository.get_run_for_update(run.id)
            if recovered is None:
                raise FinanceApprovalSyncError("SYNC_FEISHU_APPROVAL_RUN_MISSING") from None
            return self._fail(recovered, None, "SYNC_FEISHU_APPROVAL_ALREADY_RUNNING")
        try:
            return self._run(run, client, codes)
        finally:
            if self._client is None:
                client.close()

    def _preflight(self, run: IntegrationSyncRun, interface: IntegrationInterface) -> None:
        if (
            run.trigger_type not in EXECUTABLE_TRIGGERS
            or run.provider != FINANCE_APPROVAL_PROVIDER
            or run.interface_key != SPEC.interface_key
            or interface.handler_key != SPEC.handler_key
            or not interface.outbound_enabled
            or run.config_id is None
        ):
            raise FinanceApprovalSyncError("SYNC_FEISHU_APPROVAL_NOT_AUTHORIZED")
        config = self.repository.get_config(run.config_id, frozenset({run.source_account_ref}))
        if config is None or not config.is_enabled:
            raise FinanceApprovalSyncError("SYNC_FEISHU_APPROVAL_CONFIG_DISABLED")

    def _window(self, run: IntegrationSyncRun) -> tuple[datetime, datetime]:
        end = run.window_end or datetime.now(UTC)
        start = run.window_start or end - timedelta(days=SPEC.lookback_days)
        return start, end

    def _run(
        self, run: IntegrationSyncRun, client: FeishuApprovalClient, codes: dict[str, str]
    ) -> FinanceApprovalSyncResult:
        start, end = self._window(run)
        result = FinanceApprovalSyncResult(run_id=run.id, status="running")
        ordinal = 0
        for kind, code in codes.items():
            for slice_no, (start_ms, end_ms) in enumerate(month_slices(start, end)):
                ordinal += 1
                work = self._start_work(run, ordinal, kind, slice_no, start_ms, end_ms)
                try:
                    listed, written = self._sync_slice(run, client, kind, code, start_ms, end_ms)
                except FeishuApprovalError as error:
                    self.session.rollback()
                    return self._fail(run, work, error.code)
                except A.ApprovalParseError as error:
                    self.session.rollback()
                    return self._fail(run, work, f"SYNC_FEISHU_APPROVAL_PARSE_{error}".upper())
                except Exception:
                    self.session.rollback()
                    logger.exception("finance_approval_slice_failed run_id=%s", run.id)
                    return self._fail(run, work, "SYNC_FEISHU_APPROVAL_PUBLISH_FAILED")
                result.listed += listed
                result.written += written
                work.status = "succeeded"
                work.response_count = listed
                work.finished_at = utc_now()
                run.work_items_succeeded += 1
                run.records_seen += listed
                run.records_written += written
                self.session.commit()
        try:
            matched = ApprovalService(self.session).auto_match(request_id=str(run.id))
        except Exception:
            self.session.rollback()
            logger.exception("finance_approval_auto_match_failed run_id=%s", run.id)
            return self._fail(run, None, "SYNC_FEISHU_APPROVAL_AUTO_MATCH_FAILED")
        result.auto_matched = matched
        run.status = result.status = "succeeded"
        run.finished_at = utc_now()
        run.error_message = f"listed={result.listed} written={result.written} auto={matched}"
        self.session.commit()
        logger.info(
            "finance_approval_sync_succeeded run_id=%s listed=%s written=%s auto=%s",
            run.id,
            result.listed,
            result.written,
            matched,
        )
        return result

    def _start_work(
        self,
        run: IntegrationSyncRun,
        ordinal: int,
        kind: str,
        slice_no: int,
        start_ms: int,
        end_ms: int,
    ) -> IntegrationSyncRunWorkItem:
        work = IntegrationSyncRunWorkItem(
            id=uuid4(),
            run_id=run.id,
            ordinal=ordinal,
            request_kind=SPEC.request_kind,
            scope_key=kind,
            status="running",
            attempt_count=1,
            offset_value=slice_no,
            length_value=SPEC.default_page_size,
            request_safe_params={"kind": kind, "start_ms": start_ms, "end_ms": end_ms},
            started_at=utc_now(),
        )
        self.repository.add_work_items([work])
        run.work_items_total += 1
        self.session.commit()
        return work

    def _sync_slice(
        self,
        run: IntegrationSyncRun,
        client: FeishuApprovalClient,
        kind: str,
        code: str,
        start_ms: int,
        end_ms: int,
    ) -> tuple[int, int]:
        codes: list[str] = []
        token = ""
        for _ in range(SPEC.default_max_pages):
            page = client.list_instances(
                approval_code=code,
                start_ms=start_ms,
                end_ms=end_ms,
                page_size=SPEC.default_page_size,
                page_token=token,
            )
            codes.extend(page.instance_codes)
            token = page.page_token
            if not page.has_more or not token:
                break
        codes = list(dict.fromkeys(codes))
        settled = self._settled(codes)
        written = 0
        for instance_code in codes:
            if instance_code in settled:
                continue
            detail = client.get_instance(instance_code)
            # 姓名不在这里定：读取时按员工表现查，员工表以后补了人，老单子也能显示名字。
            parsed = A.parse_instance(
                detail, approval_code=code, kind=kind, instance_code=instance_code
            )
            self._upsert(parsed, run.id)
            written += 1
        return len(codes), written

    def _settled(self, codes: list[str]) -> set[str]:
        """已结束且结束超过 14 天的单，上次取过就不再取详情。"""
        if not codes:
            return set()
        cutoff = datetime.now(UTC) - REFRESH_DONE_WITHIN
        rows = self.session.execute(
            select(
                FinanceCashApproval.instance_code,
                FinanceCashApproval.status,
                FinanceCashApproval.completed_at,
            ).where(FinanceCashApproval.instance_code.in_(codes))
        ).all()
        return {
            row.instance_code
            for row in rows
            if row.status in A.TERMINAL_STATUSES
            and row.completed_at is not None
            and row.completed_at < cutoff
        }

    def _upsert(self, parsed: A.ParsedApproval, run_id: UUID) -> None:
        values = {
            "instance_code": parsed.instance_code,
            "serial_number": parsed.serial_number,
            "approval_code": parsed.approval_code,
            "kind": parsed.kind,
            "status": parsed.status,
            "started_at": parsed.started_at,
            "completed_at": parsed.completed_at,
            "handled_at": parsed.handled_at,
            "applicant_user_id": parsed.applicant_user_id,
            "department_id": parsed.department_id,
            "reason": parsed.reason,
            "amount": parsed.amount,
            "currency_code": parsed.currency_code,
            "pay_method": parsed.pay_method,
            "invoice": parsed.invoice,
            "payee": parsed.payee,
            "payee_bank": parsed.payee_bank,
            "payee_account_last4": parsed.payee_account_last4,
            "fee_category": parsed.fee_category,
            "related_serial": parsed.related_serial,
            "items": parsed.items,
            "attachments": parsed.attachments,
            "records": parsed.records,
            "comments": parsed.comments,
            "last_run_id": run_id,
            "fetched_at": utc_now(),
        }
        statement = pg_insert(FinanceCashApproval).values(**values)
        self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[FinanceCashApproval.instance_code],
                set_={key: statement.excluded[key] for key in values if key != "instance_code"},
            )
        )

    def _fail(
        self,
        run: IntegrationSyncRun,
        work: IntegrationSyncRunWorkItem | None,
        error_code: str,
    ) -> FinanceApprovalSyncResult:
        now = utc_now()
        code = error_code[:128]
        if work is not None and work.status == "running":
            work.status = "failed"
            work.error_code = code
            work.error_message = "Finance approval sync failed"
            work.finished_at = now
            run.work_items_failed += 1
        run.status = "failed"
        run.error_code = code
        run.error_message = "Finance approval sync failed"
        run.finished_at = now
        self.session.commit()
        logger.warning("finance_approval_sync_failed run_id=%s error_code=%s", run.id, code)
        return FinanceApprovalSyncResult(run_id=run.id, status="failed")

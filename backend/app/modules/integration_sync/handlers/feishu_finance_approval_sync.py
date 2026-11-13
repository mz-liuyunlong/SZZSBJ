"""任务中心同步任务：把飞书四种资金审批单写进财务审批单表，然后自动挂单。

写法照 PMC 采购同步：运行记录 + 分步记录 + 状态流转；手动、定时、重试都走这里。
飞书审批列表一次最多查 30 天，所以时间窗口切成 30 天一段，每段一个分步记录。
第二家公司（另一个飞书企业，env 前缀 YC_）配了审批定义编码就一起拉，单号前加 YC-，
申请人 / 处理人姓名从它的通讯录查（这些人不在系统员工表里）。见 finance_cashflow.approval_orgs。
"""

from __future__ import annotations

import logging
import re
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
from app.modules.finance_cashflow.approval_orgs import (
    ORG_MAIN,
    ORG_YC,
    org_serial,
    org_serials,
    yc_enabled,
)
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
# 通讯录查姓名：这些错误是整个应用没权限 / 凭证不对，后面的人也查不到，整次任务停查；
# 其他（某个人查不到、离职等）只跳过这个人（复审 P3-3）。
NAME_LOOKUP_FATAL = re.compile(r"_(TRANSPORT|TOKEN\w*)$|_HTTP_(401|403)_|_CODE_99991\d{3}$")


class FinanceApprovalSyncError(RuntimeError):
    """Safe error code without provider payloads."""


def _default_client() -> FeishuApprovalClient:
    settings = get_settings()
    if settings.app_env is not AppEnvironment.PRODUCTION:
        raise FinanceApprovalSyncError("SYNC_FEISHU_APPROVAL_SERVER_ENVIRONMENT_REQUIRED")
    return HttpFeishuApprovalClient(settings)


def _default_yc_client() -> FeishuApprovalClient:
    settings = get_settings()
    if settings.app_env is not AppEnvironment.PRODUCTION:
        raise FinanceApprovalSyncError("SYNC_FEISHU_APPROVAL_SERVER_ENVIRONMENT_REQUIRED")
    return HttpFeishuApprovalClient(settings, second_company=True)


# 本地预览和测试可以换成回放客户端；正式环境只用上面这两个。
client_factory: Callable[[], FeishuApprovalClient] = _default_client
yc_client_factory: Callable[[], FeishuApprovalClient] = _default_yc_client


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

    def __init__(
        self,
        session: Session,
        *,
        client: FeishuApprovalClient | None = None,
        yc_client: FeishuApprovalClient | None = None,
    ) -> None:
        self.session = session
        self.repository = IntegrationSyncRepository(session)
        self._client = client
        self._yc_client = yc_client
        self._names: dict[str, str] = {}
        self._names_off = False

    def execute(
        self, run: IntegrationSyncRun, interface: IntegrationInterface
    ) -> FinanceApprovalSyncResult:
        created: list[FeishuApprovalClient] = []
        try:
            self._preflight(run, interface)
            settings = get_settings()
            codes = parse_finance_approval_codes(settings.finance_approval_codes)
            yc_codes: dict[str, str] | None = None
            if yc_enabled(settings):
                try:
                    yc_codes = parse_finance_approval_codes(settings.yc_finance_approval_codes)
                except FinanceApprovalCodesError:
                    raise FinanceApprovalSyncError(
                        "SYNC_FEISHU_APPROVAL_YC_CODES_NOT_CONFIGURED"
                    ) from None
            client = self._client or self._made(created, client_factory)
            orgs: list[tuple[str, dict[str, str], FeishuApprovalClient]] = [
                (ORG_MAIN, codes, client)
            ]
            if yc_codes is not None:
                yc_client = self._yc_client or self._made(created, yc_client_factory)
                orgs.append((ORG_YC, yc_codes, yc_client))
        except (FinanceApprovalSyncError, FinanceApprovalCodesError) as error:
            self._close(created)
            return self._fail(run, None, str(error))
        except FeishuApprovalError as error:
            self._close(created)
            return self._fail(run, None, error.code)
        try:
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
            return self._run(run, orgs)
        finally:
            self._close(created)

    @staticmethod
    def _made(
        created: list[FeishuApprovalClient], factory: Callable[[], FeishuApprovalClient]
    ) -> FeishuApprovalClient:
        client = factory()
        created.append(client)
        return client

    @staticmethod
    def _close(created: list[FeishuApprovalClient]) -> None:
        for client in created:
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
        self,
        run: IntegrationSyncRun,
        orgs: list[tuple[str, dict[str, str], FeishuApprovalClient]],
    ) -> FinanceApprovalSyncResult:
        start, end = self._window(run)
        result = FinanceApprovalSyncResult(run_id=run.id, status="running")
        ordinal = 0
        for org, codes, client in orgs:
            for kind, code in codes.items():
                for slice_no, (start_ms, end_ms) in enumerate(month_slices(start, end)):
                    ordinal += 1
                    failed = self._run_slice(
                        run, result, client, org, kind, code, ordinal, slice_no, start_ms, end_ms
                    )
                    if failed is not None:
                        return failed
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

    def _run_slice(
        self,
        run: IntegrationSyncRun,
        result: FinanceApprovalSyncResult,
        client: FeishuApprovalClient,
        org: str,
        kind: str,
        code: str,
        ordinal: int,
        slice_no: int,
        start_ms: int,
        end_ms: int,
    ) -> FinanceApprovalSyncResult | None:
        """拉一段；失败返回失败结果（整个任务停），成功返回 None。"""
        work = self._start_work(run, ordinal, org, kind, slice_no, start_ms, end_ms)
        try:
            listed, written = self._sync_slice(run, client, org, kind, code, start_ms, end_ms)
        except FeishuApprovalError as error:
            self.session.rollback()
            return self._fail(run, work, error.code)
        except FinanceApprovalSyncError as error:
            self.session.rollback()
            return self._fail(run, work, str(error))
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
        return None

    def _start_work(
        self,
        run: IntegrationSyncRun,
        ordinal: int,
        org: str,
        kind: str,
        slice_no: int,
        start_ms: int,
        end_ms: int,
    ) -> IntegrationSyncRunWorkItem:
        params: dict[str, str | int] = {"kind": kind, "start_ms": start_ms, "end_ms": end_ms}
        if org != ORG_MAIN:
            params["org"] = org
        work = IntegrationSyncRunWorkItem(
            id=uuid4(),
            run_id=run.id,
            ordinal=ordinal,
            request_kind=SPEC.request_kind,
            # 主公司的分步照旧只写类型；第二家前面带公司，任务中心一眼能看出是哪家失败。
            scope_key=kind if org == ORG_MAIN else f"{org}:{kind}",
            status="running",
            attempt_count=1,
            offset_value=slice_no,
            length_value=SPEC.default_page_size,
            request_safe_params=params,
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
        org: str,
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
        else:
            # 上限用完飞书还有下一页：这一片不完整，不写入，任务记失败。
            raise FinanceApprovalSyncError("SYNC_FEISHU_APPROVAL_PAGE_LIMIT_REACHED")
        codes = list(dict.fromkeys(codes))
        settled = self._settled(codes)
        written = 0
        for instance_code in codes:
            if instance_code in settled:
                continue
            detail = client.get_instance(instance_code)
            # 主公司的姓名不在这里定：读取时按员工表现查，员工表以后补了人，老单子也能显示名字。
            # 第二家公司的人不在员工表里，这里从它的通讯录查一次，存在这张单上。
            parsed = A.parse_instance(
                detail, approval_code=code, kind=kind, instance_code=instance_code
            )
            names: dict[str, str] = {}
            if org != ORG_MAIN:
                parsed.serial_number = org_serial(org, parsed.serial_number)
                # 关联单号是逗号隔开的几张，逐个加前缀（复审 P3-1）
                parsed.related_serial = org_serials(org, parsed.related_serial)
                names = self._people_names(client, A.people_of(detail))
            self._upsert(parsed, run.id, org, names)
            written += 1
        return len(codes), written

    def _people_names(self, client: FeishuApprovalClient, people: set[str]) -> dict[str, str]:
        """按 user_id 查姓名（同一次任务里查过的不再查）。

        查不到 / 没有通讯录权限：留空，页面显示编号，不让整次同步失败；
        应用级的权限 / 凭证问题只记一次日志，这次任务后面的单子不再查；单个人查不到只跳过他。
        """
        lookup = getattr(client, "get_user_name", None)
        out: dict[str, str] = {}
        for user_id in sorted(people):
            if user_id not in self._names and lookup is not None and not self._names_off:
                try:
                    self._names[user_id] = lookup(user_id)
                except FeishuApprovalError as error:
                    if NAME_LOOKUP_FATAL.search(error.code):
                        self._names_off = True
                        logger.warning("finance_approval_user_name_unavailable code=%s", error.code)
                    else:
                        self._names[user_id] = ""  # 这个人查不到：这次任务里不再查他
            if self._names.get(user_id):
                out[user_id] = self._names[user_id]
        return out

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

    def _upsert(
        self, parsed: A.ParsedApproval, run_id: UUID, org: str, names: dict[str, str]
    ) -> None:
        values = {
            "instance_code": parsed.instance_code,
            "org": org,
            "people_names": names,
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
                # 姓名合并更新：老的加新的、新的优先；这次没查到的人保留上次查到的（复审 P3-2）。
                set_={
                    key: (
                        FinanceCashApproval.__table__.c.people_names.op("||")(
                            statement.excluded.people_names
                        )
                        if key == "people_names"
                        else statement.excluded[key]
                    )
                    for key in values
                    if key != "instance_code"
                },
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

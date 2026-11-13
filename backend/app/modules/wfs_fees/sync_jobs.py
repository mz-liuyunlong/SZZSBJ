"""WFS 费用报表同步（PR 2，Rocky 2026-11-13）：按店、按期向沃尔玛要报表，拉回来导入费用明细。

- 期：从 2026-08-22（周六）起每 14 天一期，周六到下一个周五；账单日 = 止日 + 4 天（周二），
  报表在止日 + 7 天（周五）上海 03:00 以后去要。历史只补 2026-10-01 以后结束的期，
  更早的以后由部署AI按票据回填。
- 报表：SETTLEMENT（结算，服务费各类 + 退货处理费）、WFS_STORAGE_FEE（仓储费）。
  一店 × 一类 × 一期 = 一条任务：排队 → 已下单（等沃尔玛生成）→ 已导入 / 空报告；
  失败 / 疑似个人信息拦下 是终态，定时不再重试，手动同步会重新排队失败的。
- 沃尔玛下单每店每类每小时 1 次：每次运行每店每类最多下单 1 次，下单前先查近 30 天
  同范围的请求能不能复用（执行器里做）；没生成好隔 1 小时再看，最多看 48 次。
  "1 小时内下过单"看 last_post_at：真下了单（成功或失败）才记，只复用已有请求的不记。
- 拉回来导入出错：这家店回滚、隔 1 小时再来，连续 48 次都出错算失败。
- 入库货件明细读完补分摊；补分摊出错只记 warning，不影响报表导入。
- 同步按钮：按一次锁 90 分钟；最近一次同步失败锁 60 分钟（Rocky 11-13）。
- 入库货件明细：沃尔玛远程采集每天落的 items.csv，读进 fact_walmart_wfs_inbound_items，
  入库运费按货件商品件数分摊（service._shipment_items）。
"""

from __future__ import annotations

import csv
import logging
import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.integrations.walmart.remote_dispatch import DispatchRejected
from app.integrations.walmart.wfs_report_engine import EXIT_TOKEN
from app.modules.wfs_fees.report_models import (
    ACTIVE_STATUSES,
    REPORT_TYPES,
    WalmartWfsInboundItem,
    WalmartWfsReportJob,
)
from app.modules.wfs_fees.service import SOURCE_REF, WfsFeeService

logger = logging.getLogger("app.wfs_fees.sync")

SHANGHAI: Final = ZoneInfo("Asia/Shanghai")
ANCHOR: Final = date(2026, 8, 22)
PERIOD_DAYS: Final = 14
BILL_LAG_DAYS: Final = 4
PULL_LAG_DAYS: Final = 7
PULL_HOUR: Final = 3
HISTORY_FROM: Final = date(2026, 10, 1)
RETRY_WAIT: Final = timedelta(hours=1)
MAX_POLLS: Final = 48
MAX_SUBMITS: Final = 3
MAX_REMOTE_FAILURES: Final = 48
MAX_IMPORT_FAILURES: Final = 48
MAX_POSTS_PER_RUN: Final = len(REPORT_TYPES)
MANUAL_LOCK: Final = timedelta(minutes=90)
FAILURE_LOCK: Final = timedelta(minutes=60)
ACTOR: Final = "system:wfs-report-sync"
ITEMS_FILE: Final = "items.csv"

# 下载 / 查状态出错：隔 1 小时再看，次数用完算失败
RETRY_FETCH_OUTCOMES: Final = frozenset(
    {"status_failed", "download_url_failed", "file_get_failed", "file_too_large", "bad_zip"}
)
SUBMITTED_OUTCOMES: Final = frozenset({"submitted", "reused"})
DEFERRED_OUTCOMES: Final = frozenset(
    {"deferred_rate_window", "deferred_one_post_per_type_per_run", "deferred_post_budget"}
)


@dataclass(frozen=True)
class StoreRef:
    store_id: str
    store_code: str


@dataclass(frozen=True)
class RemoteRun:
    """一家店远端跑完的结果：执行器 results、拉回本机的文件目录、用完要删的临时目录。"""

    results: list[dict[str, Any]]
    files_dir: Path | None
    cleanup_dir: Path | None = None
    exit_code: int = 0  # 执行器退出码；EXIT_TOKEN = 令牌被拒，中途停了


@dataclass
class StoreOutcome:
    store: StoreRef
    error: str | None = None
    imported: int = 0
    pending: int = 0
    failed_jobs: int = 0


@dataclass
class InboundLoad:
    rows: int = 0
    shipments: dict[str, set[str]] = field(default_factory=dict)  # 店铺 → 这次读到的货件号


@dataclass
class SyncOutcome:
    stores: list[StoreOutcome] = field(default_factory=list)
    inbound_items: int = 0
    inbound_reallocated: int = 0

    @property
    def errors(self) -> list[str]:
        return [f"{item.store.store_code}:{item.error}" for item in self.stores if item.error]


# ---------------------------------------------------------------- 期


def period_for(day: date) -> tuple[date, date]:
    """day 所在的那一期（周六到下一个周五）。"""
    offset = (day - ANCHOR).days // PERIOD_DAYS
    start = ANCHOR + timedelta(days=offset * PERIOD_DAYS)
    return start, start + timedelta(days=PERIOD_DAYS - 1)


def pull_at(period_end: date) -> datetime:
    """这一期的报表什么时候去要：止日 + 7 天，上海 03:00。"""
    day = period_end + timedelta(days=PULL_LAG_DAYS)
    return datetime.combine(day, time(PULL_HOUR), SHANGHAI)


def due_periods(now: datetime) -> list[tuple[date, date]]:
    """到了该要报表的期（从 2026-10-01 以后结束的期开始），旧到新。"""
    out: list[tuple[date, date]] = []
    start, end = period_for(HISTORY_FROM)
    while pull_at(end) <= now:
        out.append((start, end))
        start, end = start + timedelta(days=PERIOD_DAYS), end + timedelta(days=PERIOD_DAYS)
    return out


def walmart_range(start: date, end: date) -> tuple[str, str]:
    """沃尔玛只认这个格式（格式不对的下单也扣当小时额度）。"""
    return f"{start.isoformat()}T00:00:00.000Z", f"{end.isoformat()}T23:59:59.000Z"


def job_key(job: WalmartWfsReportJob) -> str:
    return f"{job.report_type}:{job.period_start:%Y%m%d}:{job.period_end:%Y%m%d}"


# ---------------------------------------------------------------- 入库货件明细


def _decimal(value: str | None) -> Decimal | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def load_inbound_items(
    session: Session, archive_root: Path, store_ids: Iterable[str]
) -> InboundLoad:
    """读远程采集每天落的入库货件明细（daily/<日期>/walmart/<店铺>/<run>/items.csv）。

    读过的 run 不再读（按 source_run_id 判断）；同一货件同一商品以最新一次为准。
    """
    daily = archive_root / "daily"
    loaded = InboundLoad()
    if not daily.is_dir():
        return loaded
    seen = set(
        session.scalars(
            select(WalmartWfsInboundItem.source_run_id)
            .where(WalmartWfsInboundItem.source_account_ref == SOURCE_REF)
            .distinct()
        )
    )
    for store_id in sorted(set(store_ids)):
        for path in sorted(daily.glob(f"*/walmart/{store_id}/*/{ITEMS_FILE}")):
            run_id = path.parent.name
            if run_id in seen or path.is_symlink():
                continue
            rows: dict[tuple[str, str, str], dict[str, Any]] = {}
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    shipment = (row.get("shipmentId") or "").strip()
                    if not shipment:
                        continue
                    gtin = (row.get("gtin") or "").strip()[:32]
                    sku = (row.get("sku") or "").strip()
                    rows[(shipment, gtin, sku)] = {
                        "source_account_ref": SOURCE_REF,
                        "store_id": store_id,
                        "shipment_id": shipment[:64],
                        "gtin": gtin,
                        "sku": sku,
                        "item_qty": _decimal(row.get("itemQty")),
                        "received_qty": _decimal(row.get("receivedQty")),
                        "source_run_id": run_id[:80],
                        "observed_at": datetime.now(UTC),
                    }
            for values in rows.values():
                statement = pg_insert(WalmartWfsInboundItem).values(**values)
                session.execute(
                    statement.on_conflict_do_update(
                        constraint="uq_wfs_inbound_item",
                        set_={
                            key: statement.excluded[key]
                            for key in ("item_qty", "received_qty", "source_run_id", "observed_at")
                        },
                    )
                )
                loaded.rows += 1
                loaded.shipments.setdefault(store_id, set()).add(values["shipment_id"])
            seen.add(run_id)
    session.commit()
    return loaded


# ---------------------------------------------------------------- 任务


class WfsReportSync:
    """排任务、给每家店拼执行计划、把执行器的结果落回任务并导入费用明细。

    远端执行由调用方传进来（runner），这里不碰 SSH、不拿令牌。
    """

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    # -------------------------------------------------------- 排队

    def plan_jobs(
        self, stores: Iterable[StoreRef], now: datetime, *, manual: bool, actor: str
    ) -> int:
        """给到期的每店 × 每类 × 每期建任务（已有就不建）。

        定时：失败 / 拦下的不重建；手动同步：失败的重新排队，正在等的提前到现在看。
        """
        created = 0
        periods = due_periods(now)
        for store in stores:
            existing: dict[tuple[str, date, date], list[WalmartWfsReportJob]] = {}
            for job in self.session.scalars(
                select(WalmartWfsReportJob).where(
                    WalmartWfsReportJob.source_account_ref == SOURCE_REF,
                    WalmartWfsReportJob.store_id == store.store_id,
                )
            ):
                existing.setdefault((job.report_type, job.period_start, job.period_end), []).append(
                    job
                )
            for report_type in REPORT_TYPES:
                for start, end in periods:
                    jobs = existing.get((report_type, start, end), [])
                    active = [job for job in jobs if job.status in ACTIVE_STATUSES]
                    if manual:
                        for job in active:
                            job.next_action_at = min(job.next_action_at, now)
                    done = any(job.status in ("imported", "empty") for job in jobs)
                    # 疑似个人信息拦下的：手动同步也不重排，要人看过再处理（复审 P2-2）
                    blocked = any(job.status == "pii_blocked" for job in jobs)
                    if active or done or blocked or (jobs and not manual):
                        continue
                    self.session.add(
                        WalmartWfsReportJob(
                            source_account_ref=SOURCE_REF,
                            store_id=store.store_id,
                            store_code=store.store_code,
                            report_type=report_type,
                            period_start=start,
                            period_end=end,
                            origin="manual" if manual else "schedule",
                            requested_by=actor[:255],
                            status="queued",
                            next_action_at=now,
                            updated_at=now,
                        )
                    )
                    created += 1
        self.session.commit()
        return created

    def due_jobs(self, store: StoreRef, now: datetime) -> list[WalmartWfsReportJob]:
        return list(
            self.session.scalars(
                select(WalmartWfsReportJob)
                .where(
                    WalmartWfsReportJob.source_account_ref == SOURCE_REF,
                    WalmartWfsReportJob.store_id == store.store_id,
                    WalmartWfsReportJob.status.in_(ACTIVE_STATUSES),
                    WalmartWfsReportJob.next_action_at <= now,
                )
                .order_by(WalmartWfsReportJob.period_start, WalmartWfsReportJob.report_type)
            )
        )

    def recent_posts(self, store: StoreRef, now: datetime) -> frozenset[str]:
        """这家店 1 小时内真下过单的报表类型（定时和手动挨得近时不再下，复审 P3-1）。

        按 last_post_at 看：下单成功、下单失败都占这一小时的额度；只复用已有请求的不占。
        """
        return frozenset(
            self.session.scalars(
                select(WalmartWfsReportJob.report_type)
                .where(
                    WalmartWfsReportJob.source_account_ref == SOURCE_REF,
                    WalmartWfsReportJob.store_id == store.store_id,
                    WalmartWfsReportJob.last_post_at > now - RETRY_WAIT,
                )
                .distinct()
            )
        )

    @staticmethod
    def build_plan(
        store: StoreRef,
        jobs: list[WalmartWfsReportJob],
        recent_posts: frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        """先看已下单的（不占下单额度），再下新单；执行器自己保证每类最多下单 1 次。

        1 小时内这类报表下过单的，这次只查已有请求能不能复用，不再下新单。
        """
        actions: list[dict[str, Any]] = []
        for job in jobs:
            if job.status == "submitted" and job.request_id:
                actions.append(
                    {
                        "op": "fetch",
                        "key": job_key(job),
                        "reportType": job.report_type,
                        "requestId": job.request_id,
                    }
                )
        for job in jobs:
            if job.status == "queued":
                start, end = walmart_range(job.period_start, job.period_end)
                actions.append(
                    {
                        "op": "submit",
                        "key": job_key(job),
                        "reportType": job.report_type,
                        "dataStartTime": start,
                        "dataEndTime": end,
                        "post_allowed": job.report_type not in recent_posts,
                    }
                )
        return {"store_code": store.store_code, "max_posts": MAX_POSTS_PER_RUN, "actions": actions}

    # -------------------------------------------------------- 落结果

    def apply(
        self,
        store: StoreRef,
        jobs: list[WalmartWfsReportJob],
        results: list[dict[str, Any]],
        files_dir: Path | None,
        *,
        run_id: UUID,
        now: datetime,
        exit_code: int = 0,
    ) -> StoreOutcome:
        outcome = StoreOutcome(store)
        by_key = {job_key(job): job for job in jobs}
        answered: set[str] = set()
        for result in results:
            job = by_key.get(str(result.get("key") or ""))
            if job is None:
                continue
            answered.add(job_key(job))
            job.remote_failures = 0
            job.import_failures = 0  # 走到这里没出错；整店出错会回滚，不会清零
            if result.get("op") == "submit":
                self._apply_submit(job, result, now)
            elif result.get("op") == "fetch":
                self._apply_fetch(job, result, files_dir, run_id=run_id, now=now)
            job.last_run_id = run_id
            job.updated_at = now
        stopped = [job for key, job in by_key.items() if key not in answered]
        if stopped:  # 执行器中途停了（比如令牌被拒）：下一轮再来，连续次数满了算失败
            self._remote_failed(
                stopped,
                "WFS_REPORTS_TOKEN_REJECTED" if exit_code == EXIT_TOKEN else "WFS_REPORTS_STOPPED",
                now,
            )
        for job in jobs:
            if job.status in ("imported", "empty"):
                outcome.imported += 1
            elif job.status in ACTIVE_STATUSES:
                outcome.pending += 1
            else:
                outcome.failed_jobs += 1
        self.session.commit()
        return outcome

    def _remote_failed(self, jobs: list[WalmartWfsReportJob], code: str, now: datetime) -> None:
        """远端没跑成：隔 1 小时再来；连续 48 次（约两天）都不成就标失败（复审 P2-1）。"""
        final = "WFS_REPORT_TOKEN_REJECTED" if "TOKEN" in code else "WFS_REPORT_REMOTE_UNAVAILABLE"
        for job in jobs:
            job.remote_failures += 1
            job.updated_at = now
            if job.remote_failures >= MAX_REMOTE_FAILURES:
                self._fail(job, final, now)
            else:
                job.error_code = code[:64]
                job.next_action_at = now + RETRY_WAIT

    @staticmethod
    def _fail(job: WalmartWfsReportJob, code: str, now: datetime) -> None:
        job.status = "failed"
        job.error_code = code[:64]
        job.finished_at = now

    def _apply_submit(
        self, job: WalmartWfsReportJob, result: dict[str, Any], now: datetime
    ) -> None:
        outcome = str(result.get("outcome") or "")
        if outcome in SUBMITTED_OUTCOMES and result.get("requestId"):
            job.status = "submitted"
            job.request_id = str(result["requestId"])[:80]
            job.submitted_at = job.submitted_at or now
            job.error_code = None
            ready = result.get("requestStatus") == "READY"
            job.next_action_at = now if ready else now + RETRY_WAIT
            if outcome == "submitted":
                job.submit_attempts += 1
                job.last_post_at = now
            return
        if outcome in DEFERRED_OUTCOMES:
            job.next_action_at = now + RETRY_WAIT
            return
        if outcome == "rate_limited":
            # 沃尔玛限流（这一小时这家店这类报表已经下过单，比如定时和手动挨得近）：
            # 不算失败次数，隔 1 小时再下。
            job.error_code = "WFS_REPORT_RATE_LIMITED"
            job.next_action_at = now + RETRY_WAIT
            return
        if outcome == "submit_failed":
            job.submit_attempts += 1
            job.last_post_at = now  # 下单失败也扣了这一小时的额度
            if job.submit_attempts >= MAX_SUBMITS:
                self._fail(job, "WFS_REPORT_" + outcome.upper(), now)
            else:
                job.error_code = ("WFS_REPORT_" + outcome.upper())[:64]
                job.next_action_at = now + RETRY_WAIT
            return
        self._fail(job, "WFS_REPORT_" + (outcome or "unknown").upper(), now)

    def _apply_fetch(
        self,
        job: WalmartWfsReportJob,
        result: dict[str, Any],
        files_dir: Path | None,
        *,
        run_id: UUID,
        now: datetime,
    ) -> None:
        outcome = str(result.get("outcome") or "")
        job.polls += 1
        if outcome == "downloaded":
            self._import(job, result, files_dir, run_id=run_id, now=now)
            return
        if outcome == "pii_blocked":
            job.status = "pii_blocked"
            job.error_code = "WFS_REPORT_PII_BLOCKED"
            job.finished_at = now
            return
        if outcome == "error_state":
            # 沃尔玛那边生成失败：重新下单（次数有上限）
            if job.submit_attempts >= MAX_SUBMITS:
                self._fail(job, "WFS_REPORT_ERROR_STATE", now)
                return
            job.status = "queued"
            job.request_id = None
            job.error_code = "WFS_REPORT_ERROR_STATE"
            job.next_action_at = now + RETRY_WAIT
            return
        if outcome == "not_ready" or outcome in RETRY_FETCH_OUTCOMES:
            if job.polls >= MAX_POLLS:
                code = "NOT_READY_TOO_LONG" if outcome == "not_ready" else outcome.upper()
                self._fail(job, "WFS_REPORT_" + code, now)
                return
            if outcome != "not_ready":
                job.error_code = ("WFS_REPORT_" + outcome.upper())[:64]
            job.next_action_at = now + RETRY_WAIT
            return
        self._fail(job, "WFS_REPORT_" + (outcome or "unknown").upper(), now)

    def _import(
        self,
        job: WalmartWfsReportJob,
        result: dict[str, Any],
        files_dir: Path | None,
        *,
        run_id: UUID,
        now: datetime,
    ) -> None:
        folder = files_dir / job_key(job) if files_dir is not None else None
        names = [str(item.get("name") or "") for item in result.get("files") or []]
        if folder is None or not names:
            self._fail(job, "WFS_REPORT_FILES_MISSING", now)
            return
        service = WfsFeeService(self.session, self.settings)
        file_ids: list[str] = []
        statuses: list[str] = []
        storage = job.report_type == "WFS_STORAGE_FEE"
        for name in names:
            path = folder / name
            if not path.is_file() or path.is_symlink() or "/" in name or name.startswith("."):
                self._fail(job, "WFS_REPORT_FILES_MISSING", now)
                return
            imported = service.upload(
                file_name=(
                    f"{job.store_code}_{job.report_type}_{job.period_start:%Y%m%d}_"
                    f"{job.period_end:%Y%m%d}_{name}"
                ),
                content=path.read_bytes(),
                actor=ACTOR,
                request_id=str(run_id),
                store_id=job.store_id,
                period_start=job.period_start if storage else None,
                period_end=job.period_end if storage else None,
                origin="sync",
                sync_run_id=run_id,
            )
            file_ids.append(str(imported.file_id))
            statuses.append(imported.status)
        job.file_ids = file_ids
        if "rejected" in statuses:
            self._fail(job, "WFS_REPORT_IMPORT_REJECTED", now)
            return
        job.status = "imported" if any(status != "empty" for status in statuses) else "empty"
        job.error_code = None
        job.finished_at = now

    # -------------------------------------------------------- 跑一次

    def run(
        self,
        stores: list[StoreRef],
        now: datetime,
        *,
        manual: bool,
        actor: str,
        run_id: UUID,
        execute: Callable[[StoreRef, dict[str, Any]], RemoteRun],
        archive_root: Path | None = None,
    ) -> SyncOutcome:
        """execute(店, 计划) → RemoteRun；出错抛异常，错误码在 str(异常) 里。"""
        result = SyncOutcome()
        if archive_root is not None:
            loaded: InboundLoad | None = None
            try:
                loaded = load_inbound_items(
                    self.session, archive_root, [store.store_id for store in stores]
                )
                result.inbound_items = loaded.rows
            except (OSError, csv.Error, ValueError):
                self.session.rollback()
                logger.exception("wfs_inbound_items_load_failed run_id=%s", run_id)
            if loaded is not None:
                # 货件明细后到：给这些货件里还没分摊的入库运费补分摊。
                # 补分摊出错只回滚补分摊（货件明细已经落库），记 warning，报表照常往下导。
                try:
                    result.inbound_reallocated = WfsFeeService(
                        self.session, self.settings
                    ).reallocate_inbound(loaded.shipments)
                except Exception:  # noqa: BLE001
                    self.session.rollback()
                    logger.warning("wfs_inbound_reallocate_failed run_id=%s", run_id, exc_info=True)
        self.plan_jobs(stores, now, manual=manual, actor=actor)
        for store in stores:
            jobs = self.due_jobs(store, now)
            if not jobs:
                result.stores.append(StoreOutcome(store))
                continue
            plan = self.build_plan(store, jobs, self.recent_posts(store, now))
            code: str | None = None
            try:
                remote = execute(store, plan)
            except DispatchRejected as exc:  # 固定错误码，可以直接记
                code = str(exc)[:64] or "WFS_REPORT_REMOTE_FAILED"
            except Exception:  # noqa: BLE001  一家店失败不影响别的店；细节只进日志
                logger.exception("wfs_report_remote_failed run_id=%s store=%s", run_id, store)
                code = "WFS_REPORT_REMOTE_FAILED"
            if code is not None:
                self.session.rollback()
                self._remote_failed(jobs, code, now)
                self.session.commit()
                result.stores.append(StoreOutcome(store, error=code, pending=len(jobs)))
                continue
            try:
                applied = self.apply(
                    store,
                    jobs,
                    remote.results,
                    remote.files_dir,
                    run_id=run_id,
                    now=now,
                    exit_code=remote.exit_code,
                )
            except Exception:  # noqa: BLE001
                # 导入出错：这家店回滚、推后 1 小时，接着下一家（复审 P2-4）
                logger.exception("wfs_report_import_failed run_id=%s store=%s", run_id, store)
                self.session.rollback()
                applied = self._import_failed(store, jobs, now)
            finally:
                # 拉回来的报表原件已经按 sha256 存进媒体目录，临时目录不留
                if remote.cleanup_dir is not None:
                    shutil.rmtree(remote.cleanup_dir, ignore_errors=True)
            result.stores.append(applied)
        return result

    def _import_failed(
        self, store: StoreRef, jobs: list[WalmartWfsReportJob], now: datetime
    ) -> StoreOutcome:
        """导入出错：隔 1 小时再来；连续 48 次都出错就标失败，不再一直重试。"""
        ids = [job.id for job in jobs]
        outcome = StoreOutcome(store, error="WFS_REPORT_IMPORT_FAILED")
        for job in self.session.scalars(
            select(WalmartWfsReportJob).where(
                WalmartWfsReportJob.id.in_(ids),
                WalmartWfsReportJob.status.in_(ACTIVE_STATUSES),  # 已经导入成功的不动
            )
        ):
            job.import_failures += 1
            job.updated_at = now
            if job.import_failures >= MAX_IMPORT_FAILURES:
                self._fail(job, "WFS_REPORT_IMPORT_FAILED", now)
                outcome.failed_jobs += 1
            else:
                job.error_code = "WFS_REPORT_IMPORT_FAILED"
                job.next_action_at = now + RETRY_WAIT
                outcome.pending += 1
        self.session.commit()
        return outcome


# ---------------------------------------------------------------- 页面状态


def latest_jobs(
    session: Session, store_ids: Iterable[str] | None = None
) -> list[WalmartWfsReportJob]:
    query = select(WalmartWfsReportJob).where(WalmartWfsReportJob.source_account_ref == SOURCE_REF)
    if store_ids is not None:
        query = query.where(WalmartWfsReportJob.store_id.in_(list(store_ids)))
    return list(
        session.scalars(
            query.order_by(WalmartWfsReportJob.period_end.desc(), WalmartWfsReportJob.store_code)
        )
    )

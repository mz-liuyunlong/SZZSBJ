"""「WFS 创建结果拉取」：数据中心 · 任务中心里的一个任务（Rocky 2026-11-04）。

PMC 的同步和定时任务统一走任务中心，频率、开关、日志、重试都在那里看，WFS 不另起定时器或
worker 入口。

* 任务中心按 cron（默认每 3 分钟）建一次运行；每次运行处理该账号下所有要处理的票：
  已批准待执行 → 提交 Walmart；提交中且到了查询时间 → 用我方单号查一次（单票最多 10 次，
  10 次仍查不到判失败并释放箱子，见 ``creation_worker``）；结果待核实 → 查一次；
  页面上点了「立即查询」/「补取箱唛」的票 → 处理一次。
* 批准、重试、立即查询、补取箱唛不等下一个 3 分钟：在任务中心里立即建一次手动运行
  （等同「立即同步」）。任务没注册或被关掉时只记一条事件，等下一次定时运行。
* 一次运行里每个操作一条明细（work item），失败原因写在明细上；任何一个操作出错，这次运行
  记失败，可在任务中心点重试。
* 是否真的调用 Walmart 仍由 ``WFS_CREATION_MODE`` 决定；关闭时有待处理的票，运行记失败并
  写明原因，没有待处理的票就是一次空的成功运行。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.modules.integration_sync.models import (
    IntegrationInterface,
    IntegrationSyncConfig,
    IntegrationSyncRun,
    IntegrationSyncRunWorkItem,
)
from app.modules.pmc_wfs.creation_models import WfsCreation, WfsCreationTicket

logger = logging.getLogger("app.pmc_wfs.creation_task")

PROVIDER = "walmart"
INTERFACE_KEY = "wfsCreationResultPoll"
DISPLAY_NAME = "WFS 创建结果拉取"
HANDLER_KEY = "walmart.pmc_wfs.creation_result_poll.v1"
ENDPOINT = "pmc-wfs://creation-result-poll"
CONTRACT_VERSION = "pmc-wfs-creation-result-poll-v1"
DEFAULT_CRON = "*/3 * * * *"
ACTOR = "wfs-creation-task"
REQUESTED = "requested"  # ticket.result key: reconcile / labels asked for on the page
STUCK_AFTER = timedelta(minutes=10)
OPEN_STATES = ("QUEUED", "RUNNING", "UNKNOWN")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def due_actions(tickets, now: datetime) -> list[str]:
    """What one task run does for one approved operation, in order."""
    from app.modules.pmc_wfs.creation_worker import fc_check_due, poll_due

    actions: list[str] = []
    states = {t.state for t in tickets}
    requested = {t.result.get(REQUESTED) for t in tickets} - {None}
    if "QUEUED" in states:
        actions.append("execute")  # also a retry: the worker reads back before resending
    stuck = any(
        t.state == "RUNNING"
        and not t.result.get("polling")
        and t.result.get("started_at")
        and now - datetime.fromisoformat(t.result["started_at"]) >= STUCK_AFTER
        for t in tickets
    )
    if "reconcile" in requested or "UNKNOWN" in states or stuck:
        actions.append("reconcile")
    if any(
        t.state == "RUNNING" and t.result.get("polling") and poll_due(t.result["polling"], now)
        for t in tickets
    ):
        actions.append("poll")
    fc_due = any(t.state == "SUCCEEDED" and fc_check_due(t.result, now) for t in tickets)
    if "labels" in requested or fc_due:
        actions.append("labels")  # labels mode also reads the missing FC back
    return actions


def pending_operations(session, account: str, now: datetime) -> list[tuple[UUID, list[str], int]]:
    """Approved operations of ``account`` with something due: (id, actions, ticket count)."""
    rows = session.execute(
        select(WfsCreation.id, WfsCreationTicket)
        .join(WfsCreationTicket, WfsCreationTicket.operation_id == WfsCreation.id)
        .where(
            WfsCreation.source_account_ref == account,
            WfsCreation.approval_ref.is_not(None),
            WfsCreation.approved_by.is_not(None),
            or_(
                WfsCreationTicket.state.in_(OPEN_STATES),
                WfsCreationTicket.result[REQUESTED].as_string().is_not(None),
                WfsCreationTicket.result["fc_check"].is_not(None),
            ),
        )
        .order_by(WfsCreation.created_at, WfsCreationTicket.number)
    ).all()
    grouped: dict[UUID, list] = defaultdict(list)
    for ident, ticket in rows:
        grouped[ident].append(ticket)
    result = []
    for ident, tickets in grouped.items():
        actions = due_actions(tickets, now)
        if actions:
            result.append((ident, actions, len(tickets)))
    return result


def _clear_requests(factory, ident: UUID) -> None:
    with factory() as session:
        tickets = session.scalars(
            select(WfsCreationTicket)
            .where(WfsCreationTicket.operation_id == ident)
            .with_for_update()
        )
        for ticket in tickets:
            if REQUESTED in ticket.result:
                ticket.result = {k: v for k, v in ticket.result.items() if k != REQUESTED}
        session.commit()


def _ticket_states(factory, ident: UUID) -> dict[UUID, str]:
    with factory() as session:
        return dict(
            session.execute(
                select(WfsCreationTicket.id, WfsCreationTicket.state).where(
                    WfsCreationTicket.operation_id == ident
                )
            ).all()
        )


class WfsCreationResultPollHandler:
    """Executes one task-center run of 「WFS 创建结果拉取」 for one account."""

    handler_key = HANDLER_KEY

    def __init__(self, session, *, gateway=None, factory=None, now=None) -> None:
        self.session = session
        self._gateway = gateway
        self._factory = factory
        self._now = now

    def _deps(self):
        if self._factory is None:
            from app.db.session import get_session_factory

            self._factory = get_session_factory()
        if self._gateway is None:
            from app.modules.pmc_wfs.gateway import get_creation_gateway

            self._gateway = get_creation_gateway()
        return self._factory, self._gateway

    def execute(self, run: IntegrationSyncRun, interface: IntegrationInterface) -> None:
        if (
            run.provider != PROVIDER
            or run.interface_key != INTERFACE_KEY
            or interface.handler_key != HANDLER_KEY
            or not interface.outbound_enabled
            or run.trigger_type not in ("manual", "schedule", "retry")
            or run.config_id is None
        ):
            return self._fail(run, "SYNC_WFS_CREATION_NOT_AUTHORIZED")
        config = self.session.get(IntegrationSyncConfig, run.config_id)
        if config is None or config.source_account_ref != run.source_account_ref:
            return self._fail(run, "SYNC_CONFIG_NOT_FOUND")
        if not config.is_enabled:
            return self._fail(run, "SYNC_CONFIG_DISABLED")
        try:
            run.status, run.started_at = "running", _utc_now()
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            return self._fail(run, "SYNC_WFS_CREATION_ALREADY_RUNNING")
        try:
            self._process(run)
        except Exception as error:  # the run must not stay "running"
            self.session.rollback()
            logger.exception("wfs_creation_poll_failed run_id=%s", run.id)
            self._fail(run, getattr(error, "code", None) or "SYNC_WFS_CREATION_FAILED")

    def _process(self, run: IntegrationSyncRun) -> None:
        from app.modules.pmc_wfs.creation_worker import run_operation

        factory, gateway = self._deps()
        now = self._now or _utc_now()
        with factory() as session:
            pending = pending_operations(session, run.source_account_ref, now)
        if pending and not gateway.enabled:
            return self._fail(
                run, "WFS_CREATION_DISABLED", getattr(gateway, "reason", None) or "WFS 创建未启用"
            )
        failed = 0
        for ordinal, (ident, actions, count) in enumerate(pending, start=1):
            work = IntegrationSyncRunWorkItem(
                id=uuid4(),
                run_id=run.id,
                ordinal=ordinal,
                request_kind="offset_page",
                scope_key=str(ident),
                status="running",
                attempt_count=1,
                offset_value=0,
                length_value=max(count, 1),
                request_safe_params={"operation_id": str(ident), "actions": actions},
                started_at=_utc_now(),
            )
            self.session.add(work)
            run.work_items_total += 1
            run.records_seen += count
            self.session.commit()
            before = _ticket_states(factory, ident)
            try:
                for action in actions:
                    run_operation(factory, gateway, ident, action)
                _clear_requests(factory, ident)
                after = _ticket_states(factory, ident)
                changed = sum(1 for k, v in after.items() if before.get(k) != v)
                work.status, work.response_count = "succeeded", changed
                run.work_items_succeeded += 1
                run.records_written += changed
            except Exception as error:
                failed += 1
                code = getattr(error, "code", None) or type(error).__name__
                details = getattr(error, "details", None) or {}
                work.status, work.error_code = "failed", str(code)[:128]
                work.error_message = str(details.get("reason") or code)[:500]
                run.work_items_failed += 1
                logger.warning("wfs_creation_poll_item_failed op=%s code=%s", ident, code)
            work.finished_at = _utc_now()
            self.session.commit()
        if failed:
            return self._fail(
                run, "SYNC_WFS_CREATION_PARTIAL", f"{failed} 个创建操作处理失败，见明细"
            )
        run.status, run.finished_at = "succeeded", _utc_now()
        self.session.commit()

    def _fail(self, run, code: str, message: str | None = None) -> None:
        run.status = "failed"
        run.error_code = code[:128]
        run.error_message = (message or "")[:500] or None
        run.finished_at = _utc_now()
        if run.started_at is None:
            run.started_at = run.finished_at
        self.session.commit()


# ----- 注册与立即运行 ----------------------------------------------------------------------


def interface_and_config(session, account: str):
    interface = session.scalar(
        select(IntegrationInterface).where(
            IntegrationInterface.provider == PROVIDER,
            IntegrationInterface.interface_key == INTERFACE_KEY,
        )
    )
    if interface is None:
        return None, None
    config = session.scalar(
        select(IntegrationSyncConfig).where(
            IntegrationSyncConfig.interface_id == interface.id,
            IntegrationSyncConfig.source_account_ref == account,
        )
    )
    return interface, config


def bootstrap(session, account: str) -> tuple[str, str]:
    """Register the task for ``account`` (idempotent). Auto sync stays off: an admin turns it
    on in 任务中心 at launch. Returns (interface status, config status)."""
    account = account.strip()
    if not account or len(account) > 128:
        raise ValueError("WFS_CREATION_TASK_ACCOUNT_INVALID")
    interface, config = interface_and_config(session, account)
    interface_status = config_status = "existing"
    if interface is None:
        interface = IntegrationInterface(
            id=uuid4(),
            provider=PROVIDER,
            interface_key=INTERFACE_KEY,
            display_name=DISPLAY_NAME,
            method="POST",
            endpoint_path=ENDPOINT,
            request_kind="offset_page",
            handler_key=HANDLER_KEY,
            contract_version=CONTRACT_VERSION,
            outbound_enabled=True,
        )
        session.add(interface)
        session.flush()
        interface_status = "created"
    if config is None:
        session.add(
            IntegrationSyncConfig(
                id=uuid4(),
                interface_id=interface.id,
                source_account_ref=account,
                is_enabled=True,
                schedule_enabled=False,
                schedule_cron=DEFAULT_CRON,
                schedule_timezone="UTC",
                max_attempts=1,
            )
        )
        config_status = "created"
    session.commit()
    return interface_status, config_status


def request_run(session, account: str, actor: str, reason: str) -> UUID | None:
    """Queue one immediate task-center run (like 「立即同步」); None when the task is not
    registered or switched off, or one is already running (the next run picks it up)."""
    from app.core.api import ApiError
    from app.modules.integration_sync.schemas import TriggerRequest
    from app.modules.integration_sync.service import IntegrationSyncService
    from app.modules.integration_sync.tasks import TaskDispatchError, dispatch_sync_run

    interface, config = interface_and_config(session, account)
    if config is None or not config.is_enabled or not interface.outbound_enabled:
        return None
    try:
        created = IntegrationSyncService(session).create_manual_run(
            config.id,
            TriggerRequest(reason=reason[:500]),
            actor_ref=actor,
            request_id=f"wfs-creation:{uuid4()}",
            account_refs=frozenset({account}),
        )
    except ApiError:
        session.rollback()
        return None
    from app.modules.pmc_wfs import local_simulator

    if local_simulator.simulator_active():
        _run_inline(created.run_id)  # no worker locally: run it here, still logged as a run
        return created.run_id
    try:
        dispatch_sync_run(created.run_id)
    except TaskDispatchError:
        logger.warning("wfs_creation_run_dispatch_deferred run_id=%s", created.run_id)
    return created.run_id


def _run_inline(run_id: UUID) -> None:
    """Local simulator only: execute the queued run in this process (``backend_ctl`` starts no
    worker). Never reached unless ``simulator_active()`` returned True."""
    from app.db.session import get_session_factory
    from app.modules.integration_sync.execution import SyncRunExecutionService

    with get_session_factory()() as session:
        SyncRunExecutionService(session).execute(run_id)


def simulator_pull(session, accounts, actor: str) -> list[UUID]:
    """「立即拉取结果（本机模拟）」: mark every open ticket in scope and run the task once per
    account. Raises ``SimulatorRefused`` outside local; the router turns "off" into 404."""
    from app.modules.pmc_wfs import local_simulator

    if not local_simulator.simulator_active():
        return []
    query = (
        select(WfsCreationTicket)
        .join(WfsCreation, WfsCreation.id == WfsCreationTicket.operation_id)
        .where(WfsCreationTicket.state.in_(OPEN_STATES))
        .with_for_update(of=WfsCreationTicket)
    )
    if accounts is not None and "*" not in accounts:
        query = query.where(WfsCreation.source_account_ref.in_(tuple(accounts)))
    wanted = set()
    for ticket in session.scalars(query):
        ticket.result = {**ticket.result, REQUESTED: "reconcile"}
        op = session.get(WfsCreation, ticket.operation_id)
        wanted.add(op.source_account_ref)
    session.commit()
    runs = []
    for account in sorted(wanted):
        run_id = request_run(session, account, actor, "WFS 创建 立即拉取（本机模拟）")
        if run_id is not None:
            runs.append(run_id)
    return runs


def dispatch_creation(operation_id, action="execute", factory=None):
    """CreationService dispatcher: mark what the page asked for, then run the task now."""
    from app.modules.pmc_wfs.creation_models import WfsCreationEvent

    if factory is None:
        from app.db.session import get_session_factory

        factory = get_session_factory()
    ident = UUID(str(operation_id))
    with factory() as session:
        op = session.get(WfsCreation, ident)
        if op is None:
            return None
        if action in ("reconcile", "labels"):
            tickets = session.scalars(
                select(WfsCreationTicket)
                .where(WfsCreationTicket.operation_id == ident)
                .with_for_update()
            )
            for ticket in tickets:
                wanted = (
                    ticket.state in OPEN_STATES
                    if action == "reconcile"
                    else ticket.state == "SUCCEEDED"
                )
                if wanted:
                    ticket.result = {**ticket.result, REQUESTED: action}
            session.commit()
        run_id = request_run(session, op.source_account_ref, ACTOR, f"WFS 创建 {action}")
        if run_id is None:
            session.add(
                WfsCreationEvent(
                    operation_id=ident,
                    actor_uid=ACTOR,
                    kind="waiting_task_center",
                    evidence={"action": action},
                )
            )
            session.commit()
        return run_id


def get_creation_dispatcher():
    return dispatch_creation

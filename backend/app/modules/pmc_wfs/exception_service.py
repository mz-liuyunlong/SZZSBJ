"""M1 exception center: durable cases and manual workflow; rule engine stubbed."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.api import ApiError
from app.modules.data_pages.models import LingxingStoreDimension as Store
from app.modules.pmc_wfs.exception_models import (
    WfsExceptionAction,
    WfsExceptionCase,
    WfsExceptionDetection,
)
from app.modules.pmc_wfs.exception_schemas import (
    AssignCommand,
    CaseEventCommand,
    ExceptionDetail,
    ExceptionFilter,
    ExceptionList,
    ExceptionOptions,
    ExceptionQuery,
    ExceptionRow,
    ExceptionSummary,
    StoreOption,
    TimelineItem,
)
from app.modules.pmc_wfs.repository import require_exception_schema

RULE_LABELS = {
    "create_long_unshipped": "创建长期未发货",
    "arrival_overdue": "超过预计到仓时间",
    "arrival_no_receiving": "到仓后长时间未收货",
    "receiving_incomplete": "收货长期未完成",
    "closed_shortage_damage": "关闭后仍存在短少或破损",
    "appeal_deadline": "申诉临期提醒",
}

STATUS_LABELS = {
    "OPEN": "待处理",
    "IN_PROGRESS": "处理中",
    "WAITING_EXTERNAL": "待外部反馈",
    "RESOLVED": "已解决",
    "CLOSED": "已关闭",
}

OPEN_STATUSES = frozenset({"OPEN", "IN_PROGRESS", "WAITING_EXTERNAL"})


def _now() -> datetime:
    return datetime.now(UTC)


class ExceptionCenterService:
    def __init__(self, session, accounts, stores):
        self.session = session
        self.accounts = accounts
        self.stores = stores

    def _scoped(self):
        require_exception_schema(self.session)
        stmt = select(WfsExceptionCase).where(
            WfsExceptionCase.source_account_ref.in_(self.accounts)
        )
        if self.stores is not None:
            stmt = stmt.where(WfsExceptionCase.store_id.in_(self.stores))
        return stmt

    def _store_names(self, store_ids: set[str]) -> dict[str, str]:
        if not store_ids:
            return {}
        rows = self.session.scalars(select(Store).where(Store.store_id.in_(store_ids)))
        return {row.store_id: row.store_name or row.store_id for row in rows}

    def _row(self, case: WfsExceptionCase, store_names: dict[str, str]) -> ExceptionRow:
        return ExceptionRow(
            id=case.id,
            shipment_id=case.shipment_id,
            shipment_row_id=case.shipment_row_id,
            rule_family=case.rule_family,  # type: ignore[arg-type]
            rule_label=RULE_LABELS.get(case.rule_family, case.rule_family),
            severity=case.severity,  # type: ignore[arg-type]
            status=case.status,  # type: ignore[arg-type]
            status_label=STATUS_LABELS.get(case.status, case.status),
            summary=case.summary,
            store_id=case.store_id,
            store_name=store_names.get(case.store_id),
            pk=case.pk,
            sku=case.sku,
            item_id=case.item_id,
            gtin=case.gtin,
            msku=case.msku,
            assignee_user_id=case.assignee_user_id,
            platform_case_ref=case.platform_case_ref,
            due_at=case.due_at,
            due_basis=case.due_basis,
            qty_variance=case.qty_variance,
            business_test=case.business_test,
            first_detected_at=case.first_detected_at,
            version=case.version,
            rule_version=case.rule_version,
        )

    def _apply_filters(self, stmt, query: ExceptionFilter):
        if query.store_id:
            stmt = stmt.where(WfsExceptionCase.store_id == query.store_id)
        if query.shipment_id:
            stmt = stmt.where(WfsExceptionCase.shipment_id == query.shipment_id)
        if query.rule_family:
            stmt = stmt.where(WfsExceptionCase.rule_family == query.rule_family)
        if query.status:
            stmt = stmt.where(WfsExceptionCase.status == query.status)
        if query.severity:
            stmt = stmt.where(WfsExceptionCase.severity == query.severity)
        if query.assignee_user_id:
            stmt = stmt.where(WfsExceptionCase.assignee_user_id == query.assignee_user_id)
        if query.only_test:
            stmt = stmt.where(WfsExceptionCase.business_test.is_(True))
        if query.due_soon:
            horizon = _now() + timedelta(days=7)
            stmt = stmt.where(
                WfsExceptionCase.due_at.is_not(None),
                WfsExceptionCase.due_at <= horizon,
                WfsExceptionCase.status.in_(tuple(OPEN_STATUSES)),
            )
        kw = query.keyword.strip()
        if kw:
            pattern = f"%{kw}%"
            field = query.keyword_field
            if field == "shipment":
                stmt = stmt.where(WfsExceptionCase.shipment_id.ilike(pattern))
            elif field == "pk":
                stmt = stmt.where(WfsExceptionCase.pk.ilike(pattern))
            elif field == "platform_case":
                stmt = stmt.where(WfsExceptionCase.platform_case_ref.ilike(pattern))
            else:
                stmt = stmt.where(WfsExceptionCase.summary.ilike(pattern))
        return stmt

    def list(self, query: ExceptionQuery) -> ExceptionList:
        stmt = self._apply_filters(self._scoped(), query)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        sort_col = {
            "first_detected_at": WfsExceptionCase.first_detected_at,
            "due_at": WfsExceptionCase.due_at,
        }[query.sort_by]
        order = sort_col.asc() if query.sort_dir == "asc" else sort_col.desc()
        stmt = stmt.order_by(order, WfsExceptionCase.id)
        offset = (query.page - 1) * query.page_size
        cases = list(self.session.scalars(stmt.offset(offset).limit(query.page_size)))
        names = self._store_names({c.store_id for c in cases})
        return ExceptionList(
            items=[self._row(c, names) for c in cases],
            total=int(total),
        )

    def summary(self, query: ExceptionFilter) -> ExceptionSummary:
        stmt = self._apply_filters(self._scoped(), query)
        sub = stmt.subquery()
        open_cases = (
            self.session.scalar(
                select(func.count()).select_from(sub).where(sub.c.status.in_(tuple(OPEN_STATUSES)))
            )
            or 0
        )
        open_shipments = (
            self.session.scalar(
                select(func.count(func.distinct(sub.c.shipment_id)))
                .select_from(sub)
                .where(sub.c.status.in_(tuple(OPEN_STATUSES)))
            )
            or 0
        )
        horizon = _now() + timedelta(days=7)
        due_soon = (
            self.session.scalar(
                select(func.count())
                .select_from(sub)
                .where(
                    sub.c.due_at.is_not(None),
                    sub.c.due_at <= horizon,
                    sub.c.status.in_(tuple(OPEN_STATUSES)),
                )
            )
            or 0
        )
        return ExceptionSummary(
            open_shipments=int(open_shipments),
            open_cases=int(open_cases),
            due_soon_cases=int(due_soon),
        )

    def options(self) -> ExceptionOptions:
        name = func.nullif(func.trim(Store.store_name), "")
        store_stmt = (
            select(Store.store_id, func.count(func.distinct(name)), func.max(name))
            .where(
                Store.source_account_ref.in_(self.accounts),
                func.trim(Store.store_id) != "",
            )
            .group_by(Store.store_id)
            .order_by(Store.store_id)
        )
        if self.stores is not None:
            store_stmt = store_stmt.where(Store.store_id.in_(self.stores))
        store_opts = [
            StoreOption(
                value=store_id,
                label=(label if count == 1 and label else store_id),
            )
            for store_id, count, label in self.session.execute(store_stmt).all()
        ]
        assignees = list(
            self.session.scalars(
                select(WfsExceptionCase.assignee_user_id)
                .where(
                    WfsExceptionCase.source_account_ref.in_(self.accounts),
                    WfsExceptionCase.assignee_user_id.is_not(None),
                )
                .distinct()
            )
        )
        if self.stores is not None:
            assignees = list(
                self.session.scalars(
                    select(WfsExceptionCase.assignee_user_id)
                    .where(
                        WfsExceptionCase.source_account_ref.in_(self.accounts),
                        WfsExceptionCase.store_id.in_(self.stores),
                        WfsExceptionCase.assignee_user_id.is_not(None),
                    )
                    .distinct()
                )
            )
        return ExceptionOptions(
            stores=store_opts,
            assignees=sorted({a for a in assignees if a}),
        )

    def _get_case(self, case_id) -> WfsExceptionCase:
        case = self.session.scalar(self._scoped().where(WfsExceptionCase.id == case_id))
        if case is None:
            raise ApiError(
                code="NOT_FOUND", status_code=404, message="异常案件不存在或不在当前权限范围"
            )
        return case

    def detail(self, case_id) -> ExceptionDetail:
        case = self._get_case(case_id)
        names = self._store_names({case.store_id})
        row = self._row(case, names)
        detections = list(
            self.session.scalars(
                select(WfsExceptionDetection)
                .where(WfsExceptionDetection.case_id == case.id)
                .order_by(WfsExceptionDetection.detected_at)
            )
        )
        actions = list(
            self.session.scalars(
                select(WfsExceptionAction)
                .where(WfsExceptionAction.case_id == case.id)
                .order_by(WfsExceptionAction.created_at)
            )
        )
        timeline: list[TimelineItem] = []
        for det in detections:
            timeline.append(
                TimelineItem(
                    id=det.id,
                    kind="detection",
                    message=f"规则检测：{det.outcome}",
                    payload={"outcome": det.outcome, "evidence": det.evidence},
                    created_at=det.detected_at,
                )
            )
        for act in actions:
            timeline.append(
                TimelineItem(
                    id=act.id,
                    kind="action",
                    action_type=act.action_type,
                    actor_uid=act.actor_uid,
                    message=str(act.payload.get("message") or act.action_type),
                    payload=act.payload,
                    created_at=act.created_at,
                )
            )
        timeline.sort(key=lambda item: item.created_at)
        return ExceptionDetail(
            **row.model_dump(),
            evidence=case.evidence or {},
            timeline=timeline,
            quantity_reconciliation_note="领星履约数量 M1 未接入，暂不提供对账结论。",
            lingxing_updated_at=None,
        )

    def _bump(self, case: WfsExceptionCase):
        case.version += 1
        case.updated_at = _now()

    def _record_action(
        self, case: WfsExceptionCase, actor_uid: str, action_type: str, payload: dict
    ):
        self.session.add(
            WfsExceptionAction(
                case_id=case.id,
                action_type=action_type,
                actor_uid=actor_uid,
                payload=payload,
            )
        )

    def _check_version(self, case: WfsExceptionCase, expected: int):
        if case.version != expected:
            raise ApiError(
                code="CASE_VERSION_CONFLICT",
                status_code=409,
                message="案件已被他人更新，请刷新后重试",
                details={"current_version": case.version},
            )

    def assign(self, case_id, actor_uid: str, cmd: AssignCommand) -> ExceptionDetail:
        case = self._get_case(case_id)
        self._check_version(case, cmd.expected_version)
        case.assignee_user_id = cmd.assignee_user_id
        if case.status == "OPEN":
            case.status = "IN_PROGRESS"
        self._record_action(
            case,
            actor_uid,
            "ASSIGN",
            {
                "message": f"分配给 {cmd.assignee_user_id}",
                "assignee_user_id": cmd.assignee_user_id,
            },
        )
        self._bump(case)
        self.session.flush()
        return self.detail(case_id)

    def post_event(self, case_id, actor_uid: str, cmd: CaseEventCommand) -> ExceptionDetail:
        case = self._get_case(case_id)
        self._check_version(case, cmd.expected_version)
        if cmd.action == "note":
            if not cmd.note.strip():
                raise ApiError(code="VALIDATION_ERROR", status_code=422, message="备注不能为空")
            if case.status == "OPEN":
                case.status = "IN_PROGRESS"
            self._record_action(
                case, actor_uid, "NOTE", {"message": cmd.note.strip(), "note": cmd.note.strip()}
            )
        elif cmd.action == "mark_waiting":
            if case.status not in {"IN_PROGRESS", "OPEN"}:
                raise ApiError(
                    code="INVALID_STATE_TRANSITION",
                    status_code=422,
                    message="当前状态不可标记待外部反馈",
                )
            case.status = "WAITING_EXTERNAL"
            note = cmd.note.strip() or "等待外部反馈"
            self._record_action(case, actor_uid, "MARK_WAITING", {"message": note})
        elif cmd.action == "resolve":
            if case.status in {"CLOSED", "RESOLVED"}:
                raise ApiError(
                    code="INVALID_STATE_TRANSITION",
                    status_code=422,
                    message="当前状态不可标记已解决",
                )
            case.status = "RESOLVED"
            note = cmd.note.strip() or "已解决"
            self._record_action(case, actor_uid, "RESOLVE", {"message": note})
        elif cmd.action == "close":
            if case.status == "CLOSED":
                raise ApiError(
                    code="INVALID_STATE_TRANSITION", status_code=422, message="案件已关闭"
                )
            if not cmd.reason.strip():
                raise ApiError(code="VALIDATION_ERROR", status_code=422, message="关闭必须填写原因")
            case.status = "CLOSED"
            self._record_action(
                case,
                actor_uid,
                "CLOSE",
                {"message": cmd.reason.strip(), "reason": cmd.reason.strip()},
            )
        elif cmd.action == "reopen":
            if case.status != "CLOSED":
                raise ApiError(
                    code="INVALID_STATE_TRANSITION", status_code=422, message="仅已关闭案件可重开"
                )
            if not cmd.reason.strip():
                raise ApiError(code="VALIDATION_ERROR", status_code=422, message="重开必须填写原因")
            case.status = "OPEN"
            self._record_action(
                case,
                actor_uid,
                "REOPEN",
                {"message": cmd.reason.strip(), "reason": cmd.reason.strip()},
            )
        else:
            raise ApiError(code="VALIDATION_ERROR", status_code=422, message="不支持的操作")
        if cmd.platform_case_ref is not None and cmd.platform_case_ref.strip():
            case.platform_case_ref = cmd.platform_case_ref.strip()
        self._bump(case)
        self.session.flush()
        return self.detail(case_id)

    @staticmethod
    def build_dedupe_key(
        source_account_ref: str,
        store_id: str,
        shipment_id: str,
        rule_family: str,
        item_key: str = "_",
    ) -> str:
        return f"{source_account_ref}:{store_id}:{shipment_id}:{rule_family}:{item_key}"

    def insert_case_for_tests(
        self,
        *,
        source_account_ref: str,
        store_id: str,
        shipment_id: str,
        rule_family: str,
        summary: str,
        severity: str = "MEDIUM",
        status: str = "OPEN",
        business_test: bool = True,
        shipment_row_id: str | None = None,
        pk: str | None = None,
        assignee_user_id: str | None = None,
        due_at: datetime | None = None,
    ) -> WfsExceptionCase:
        """Test and fixture helper; not exposed on production routes."""
        require_exception_schema(self.session)
        dedupe = self.build_dedupe_key(source_account_ref, store_id, shipment_id, rule_family)
        existing = self.session.scalar(
            select(WfsExceptionCase).where(WfsExceptionCase.dedupe_key == dedupe)
        )
        if existing:
            return existing
        now = _now()
        case = WfsExceptionCase(
            dedupe_key=dedupe,
            source_account_ref=source_account_ref,
            store_id=store_id,
            shipment_id=shipment_id,
            shipment_row_id=shipment_row_id,
            rule_family=rule_family,
            severity=severity,
            status=status,
            summary=summary,
            assignee_user_id=assignee_user_id,
            due_at=due_at,
            pk=pk,
            business_test=business_test,
            evidence={"source": "test_fixture", "rule_outcome": "HIT"},
            first_detected_at=now,
            created_at=now,
            updated_at=now,
        )
        self.session.add(case)
        self.session.flush()
        self.session.add(
            WfsExceptionDetection(
                case_id=case.id,
                outcome="HIT",
                rule_version="M1_STUB",
                evidence=case.evidence,
                detected_at=now,
            )
        )
        return case

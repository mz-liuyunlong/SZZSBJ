"""Exception center rule engine: the 8088 rules (``WFS-RULES-20261010``) over the current
published board, turned into durable cases.

* A rule hit opens a case (one per shipment × rule family) or refreshes the open one, and
  records a ``HIT`` detection.
* An open case of this rule version that no longer hits gets a ``MISS`` detection and is
  resolved by the system (``RESOLVE`` action, ``auto: true``), so the open list matches what
  the 8088 page shows. A case a person resolved or closed is never reopened by the system; a
  case the system resolved is reopened (``REOPEN``) if the rule hits again.
* Test shipments (``PMC-TEST-``) never produce cases. Cases from other sources (fixtures,
  manual entries) are not touched.

Reads only the published board; never calls Lingxing, Walmart or the carrier.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Final

from sqlalchemy import select

from app.modules.pmc_wfs.board_view import APPEAL_LAST_DAY, RULE_VERSION, WfsException
from app.modules.pmc_wfs.exception_models import (
    WfsExceptionAction,
    WfsExceptionCase,
    WfsExceptionDetection,
)
from app.modules.pmc_wfs.exception_service import OPEN_STATUSES, ExceptionCenterService
from app.modules.pmc_wfs.repository import require_exception_schema
from app.modules.pmc_wfs.shipment_board_service import ShipmentBoardService

SYSTEM_ACTOR: Final = "system:wfs-rules"
SEVERITY: Final = {"high": "HIGH", "mid": "MEDIUM", "low": "LOW"}


class ExceptionDetectionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DetectionResult:
    rule_version: str
    today: date
    hits: int
    created: int
    refreshed: int
    reopened: int
    auto_resolved: int


def _now() -> datetime:
    return datetime.now(UTC)


class WfsExceptionDetector:
    def __init__(self, session, account: str, *, today: date | None = None) -> None:
        if not account.strip():
            raise ExceptionDetectionError("WFS_EXCEPTION_SCOPE_INVALID")
        self.session = session
        self.account = account.strip()
        self.board = ShipmentBoardService(session, frozenset({self.account}), None)
        if today is not None:
            self.board.today = today

    def run(self) -> DetectionResult:
        require_exception_schema(self.session)
        if not self.board.freshness().publication_id:
            raise ExceptionDetectionError("WFS_EXCEPTION_NO_PUBLISHED_BOARD")
        self.board.list_rows()
        hits = [e for group in self.board.exceptions_by_code().values() for e in group]
        by_key = {self._key(e): e for e in hits}
        existing = {
            c.dedupe_key: c
            for c in self.session.scalars(
                select(WfsExceptionCase).where(
                    WfsExceptionCase.source_account_ref == self.account,
                    WfsExceptionCase.rule_version == RULE_VERSION,
                )
            )
        }
        now = _now()
        created = refreshed = reopened = resolved = 0
        for key, exc in by_key.items():
            case = existing.get(key)
            if case is None:
                case = self._create(key, exc, now)
                created += 1
            else:
                if case.status not in OPEN_STATUSES and self._auto_resolved(case):
                    case.status = "OPEN"
                    self._action(case, "REOPEN", "规则再次命中，系统重新打开")
                    case.version += 1
                    case.updated_at = now
                    reopened += 1
                self._refresh(case, exc, now)
                refreshed += 1
            self._detect(case, "HIT", exc, now)
        for key, case in existing.items():
            if key in by_key or case.status not in OPEN_STATUSES:
                continue
            self._detect(case, "MISS", None, now)
            case.status = "RESOLVED"
            self._action(case, "RESOLVE", "规则不再命中，系统自动解决")
            case.version += 1
            case.updated_at = now
            resolved += 1
        self.session.flush()
        return DetectionResult(
            rule_version=RULE_VERSION,
            today=self.board.today,
            hits=len(by_key),
            created=created,
            refreshed=refreshed,
            reopened=reopened,
            auto_resolved=resolved,
        )

    # ---- helpers -----------------------------------------------------------------------

    def _key(self, exc: WfsException) -> str:
        return ExceptionCenterService.build_dedupe_key(
            self.account, exc.store_id, exc.code, exc.rule_family
        )

    @staticmethod
    def _evidence(exc: WfsException) -> dict:
        return {
            "source": "wfs_rules",
            "rule_version": RULE_VERSION,
            "type": exc.type,
            "found": exc.found,
            "data_source": exc.source,
            "item_keys": list(exc.item_keys),
            "d0": exc.d0,
            "days_since_d0": exc.d_n,
            "rule_outcome": "HIT",
        }

    @staticmethod
    def _due(exc: WfsException) -> tuple[datetime | None, str | None]:
        if exc.rule_family != "appeal_deadline" or not exc.d0:
            return None, None
        deadline = date.fromisoformat(exc.d0) + timedelta(days=APPEAL_LAST_DAY)
        return (
            datetime.combine(deadline, time.min, tzinfo=UTC),
            f"沃尔玛签收日 {exc.d0} + {APPEAL_LAST_DAY} 天",
        )

    def _create(self, key: str, exc: WfsException, now: datetime) -> WfsExceptionCase:
        due_at, due_basis = self._due(exc)
        case = WfsExceptionCase(
            dedupe_key=key,
            source_account_ref=self.account,
            store_id=exc.store_id,
            shipment_id=exc.code,
            rule_family=exc.rule_family,
            severity=SEVERITY[exc.severity],
            status="OPEN",
            summary=exc.desc,
            due_at=due_at,
            due_basis=due_basis,
            qty_variance=exc.qty,
            business_test=False,
            evidence=self._evidence(exc),
            rule_version=RULE_VERSION,
            version=1,
            first_detected_at=now,
            created_at=now,
            updated_at=now,
        )
        self.session.add(case)
        self.session.flush()
        return case

    def _refresh(self, case: WfsExceptionCase, exc: WfsException, now: datetime) -> None:
        due_at, due_basis = self._due(exc)
        evidence = self._evidence(exc)
        changed = (
            case.summary != exc.desc
            or case.severity != SEVERITY[exc.severity]
            or case.qty_variance != exc.qty
            or case.evidence != evidence
            or case.due_at != due_at
        )
        if changed:
            case.summary = exc.desc
            case.severity = SEVERITY[exc.severity]
            case.qty_variance = exc.qty
            case.evidence = evidence
            case.due_at, case.due_basis = due_at, due_basis
            case.version += 1
            case.updated_at = now

    def _detect(
        self, case: WfsExceptionCase, outcome: str, exc: WfsException | None, now: datetime
    ) -> None:
        self.session.add(
            WfsExceptionDetection(
                case_id=case.id,
                outcome=outcome,
                rule_version=RULE_VERSION,
                evidence=self._evidence(exc) if exc else {"rule_outcome": outcome},
                detected_at=now,
            )
        )

    def _action(self, case: WfsExceptionCase, action_type: str, message: str) -> None:
        self.session.add(
            WfsExceptionAction(
                case_id=case.id,
                action_type=action_type,
                actor_uid=SYSTEM_ACTOR,
                payload={"message": message, "auto": True},
            )
        )

    def _auto_resolved(self, case: WfsExceptionCase) -> bool:
        last = self.session.scalar(
            select(WfsExceptionAction)
            .where(WfsExceptionAction.case_id == case.id)
            .order_by(WfsExceptionAction.created_at.desc())
            .limit(1)
        )
        return (
            case.status == "RESOLVED"
            and last is not None
            and last.actor_uid == SYSTEM_ACTOR
            and last.action_type == "RESOLVE"
        )

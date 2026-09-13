from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import get_session_factory  # noqa: E402
from app.modules.integration_sync.models import utc_now  # noqa: E402
from app.modules.integration_sync.repository import IntegrationSyncRepository  # noqa: E402

SAFE_ERROR_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,127}")


class ProductListRepairError(RuntimeError):
    """Safe repair error containing only a stable code."""


@dataclass(frozen=True, slots=True)
class ProductListRepairResult:
    repair_status: str
    run_id: UUID
    repaired_work_items_count: int
    run_error_code_present: bool


class ProductListFailedWorkItemRepair:
    """Repair stale work state only; never retries or reads integration payloads."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = IntegrationSyncRepository(session)

    def repair(self, run_id: UUID) -> ProductListRepairResult:
        run = self.repository.get_run_for_update(run_id)
        if (
            run is None
            or run.provider != "lingxing"
            or run.interface_key != "productList"
            or run.status != "failed"
            or run.error_code is None
            or SAFE_ERROR_CODE.fullmatch(run.error_code) is None
        ):
            raise ProductListRepairError("PRODUCTLIST_REPAIR_FAILED_WORK_ITEMS_RUN_NOT_ELIGIBLE")
        work_items = self.repository.list_running_work_items_for_update(run_id)
        if not work_items:
            return ProductListRepairResult(
                repair_status="NOOP",
                run_id=run_id,
                repaired_work_items_count=0,
                run_error_code_present=True,
            )

        finished_at = utc_now()
        for work in work_items:
            work.status = "failed"
            work.error_code = run.error_code
            work.error_message = "ProductList work item repaired after failed run"
            work.finished_at = finished_at
        run.work_items_failed += len(work_items)
        self.session.commit()
        return ProductListRepairResult(
            repair_status="PASS",
            run_id=run_id,
            repaired_work_items_count=len(work_items),
            run_error_code_present=True,
        )


def main() -> int:
    if os.getenv("PRODUCTLIST_REPAIR_FAILED_WORK_ITEMS_AUTHORIZED", "").casefold() != "true":
        print("PRODUCTLIST_REPAIR_FAILED_WORK_ITEMS_REQUIRES_AUTHORIZATION")
        return 2
    try:
        run_id = UUID(os.getenv("PRODUCTLIST_REPAIR_RUN_ID", ""))
    except (ValueError, AttributeError):
        print("PRODUCTLIST_REPAIR_FAILED_WORK_ITEMS_RUN_ID_INVALID")
        return 2

    try:
        with get_session_factory()() as session:
            result = ProductListFailedWorkItemRepair(session).repair(run_id)
    except ProductListRepairError as error:
        print(str(error))
        return 2
    except Exception:
        print("PRODUCTLIST_REPAIR_FAILED_WORK_ITEMS_FAILED")
        return 1

    print(f"repair_status={result.repair_status}")
    print(f"run_id={result.run_id}")
    print(f"repaired_work_items_count={result.repaired_work_items_count}")
    print(f"run_error_code_present={str(result.run_error_code_present).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

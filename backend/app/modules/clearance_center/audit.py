"""Read-only database readiness audit for clearance V1.

Usage in a separately approved environment:
    python -m app.modules.clearance_center.audit --source-account HK2613

No DML/DDL, no Walmart calls, no raw customer data, no credentials in output.
Requires database schema to have already been migrated to clearance V1.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.modules.clearance_center.repository import ClearanceReadRepository


def audit_account(session: Session, account: str) -> dict:
    if not account or account != account.strip():
        raise ValueError("Source account must be a canonical non-empty value")
    authorized = session.execute(
        text("""select 1 from gov_integration_sync_configs
                 where source_account_ref=:account limit 1"""),
        {"account": account},
    ).first()
    if authorized is None:
        raise ValueError("Source account is not registered for integration")
    report = ClearanceReadRepository(session).readiness_report(frozenset({account}))
    blockers = []
    if report["evaluation_status"] != "ready":
        blockers.append("DAILY_EVALUATION_MISSING")
    else:
        if report["not_evaluated_listings"]:
            blockers.append("LISTINGS_NOT_EVALUATED")
        if report["missing_sales_window"]:
            blockers.append("SALES_30D_COVERAGE_INCOMPLETE")
        if report["missing_wfs_stock"]:
            blockers.append("CURRENT_WFS_STOCK_MISSING_OR_STALE")
        if report["missing_profit_cost"]:
            blockers.append("PROFIT_COST_INCOMPLETE")
        if report["sales_mart_qty_mismatch"]:
            blockers.append("SOURCE_MART_SALES_MISMATCH")
    # This codebase does not have an authoritative per-day refund-sync
    # completion watermark. Refund event history must be verified separately.
    blockers.append("REFUND_SYNC_COMPLETENESS_UNVERIFIED")
    return {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "source_account_ref": account,
        "assessment": report,
        "blocking_data_quality_codes": blockers,
        "read_only": True,
        "business_approval_ready": len(blockers) == 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only clearance evidence audit")
    parser.add_argument("--source-account", required=True, help="Registered source account ref")
    args = parser.parse_args()
    # Explicit transaction read-only prevents even accidental DML in this audit.
    with get_engine().connect() as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            with Session(bind=connection, expire_on_commit=False) as session:
                report = audit_account(session, args.source_account)
                print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

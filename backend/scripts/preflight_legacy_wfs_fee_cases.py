"""Read-only historical WFS Case reconciliation; safe before migration 0036.

Prints aggregate counts only, without SKU, store, or account identifiers.
This is a gate: all unmatched, ambiguous, duplicate, and invalid counts
must be zero before executing any import.
"""

import json

from sqlalchemy import text

from app.db.session import get_session_factory
from app.modules.warehouse_wfs.legacy_identity import LEGACY_IDENTITY_PREFLIGHT_SQL


def main() -> None:
    Session = get_session_factory()
    with Session() as session:
        session.execute(text("set transaction read only"))
        row = session.execute(text(LEGACY_IDENTITY_PREFLIGHT_SQL)).mappings().one()
        values = dict(row)
        values["status_breakdown"] = dict(values["status_breakdown"])
        print(json.dumps(values, ensure_ascii=False, indent=2))
        unsafe = (
            values["unmatched_identities"]
            + values["ambiguous_identities"]
            + values["duplicate_identities"]
            + values["invalid_values"]
        )
        if unsafe or values["matched_identities"] != values["legacy_total"]:
            raise SystemExit("Preflight BLOCKED: historical identities require reconciliation")


if __name__ == "__main__":
    main()

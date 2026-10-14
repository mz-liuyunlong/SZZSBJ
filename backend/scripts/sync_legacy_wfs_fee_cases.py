from __future__ import annotations

import argparse
import json

from app.db.session import get_session_factory
from app.modules.warehouse_wfs.service import WfsFeeAlertService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview or execute legacy WFS fee case sync into formal case table."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write changes. Default is preview-only and does not mutate data.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    Session = get_session_factory()
    with Session() as session:
        result = WfsFeeAlertService(session).sync_legacy_cases(execute=args.execute)
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

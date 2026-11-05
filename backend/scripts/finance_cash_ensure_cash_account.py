"""补一个「现金」账户（手工平台、人民币），手工录入默认选它。不含账号，可重复执行。

默认演练（不写入）；加 --apply 才写入。已经有就不动。

    uv run python scripts/finance_cash_ensure_cash_account.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import get_session_factory  # noqa: E402
from app.modules.finance_cashflow.accounts import ensure_cash_account  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="真正写入；不加只看会不会新建")
    args = parser.parse_args()
    with get_session_factory()() as session:
        status = ensure_cash_account(session, apply=args.apply)
    print(f"{'APPLIED' if args.apply else 'DRY_RUN'} cash_account={status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

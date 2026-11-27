"""上线导入财务配置：账户、带名字的分类规则、剔除清单。文件不进仓库。

默认演练（校验并回滚）；加 --apply 才写入。只打印条数，不打印账号、名字、金额。

    uv run python scripts/finance_cash_deploy_load.py --file 文件路径
    uv run python scripts/finance_cash_deploy_load.py --file 文件路径 --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import get_session_factory  # noqa: E402
from app.modules.finance_cashflow.deploy_load import (  # noqa: E402
    DeployFileError,
    load_deploy_data,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="真正写入；不加只演练")
    args = parser.parse_args()
    data = json.loads(args.file.read_text(encoding="utf-8"))
    session = get_session_factory()()
    try:
        counts = load_deploy_data(session, data)
        if args.apply:
            session.commit()
        else:
            session.rollback()
    except DeployFileError as exc:
        session.rollback()
        print(f"FILE_INVALID: {exc}")
        return 2
    except Exception as exc:  # noqa: BLE001  数据库报错可能带账号，只打印类型
        session.rollback()
        print(f"WRITE_FAILED: {type(exc).__name__}")
        return 3
    finally:
        session.close()
    mode = "APPLIED" if args.apply else "DRY_RUN"
    print(
        f"{mode} accounts={counts.accounts} rules={counts.rules} "
        f"exclusions={counts.exclusions} fx_rates={counts.fx_rates}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

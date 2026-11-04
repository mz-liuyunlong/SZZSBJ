"""本机模拟数据：``seed`` 写入 DEMO-01 … 07，``clear`` 一键清除（只删带标记的）。

只在 APP_ENV=local + 本机库 127.0.0.1:55432/szzsbj_dev 运行，别处直接报错退出。
不调用 Walmart / 领星，不读凭证。用法::

    python scripts/seed_pmc_wfs_local_demo.py seed [来源账号]
    python scripts/seed_pmc_wfs_local_demo.py clear
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.model_registry import register_productlist_sync_models  # noqa: E402
from app.modules.pmc_wfs import local_demo  # noqa: E402
from app.modules.pmc_wfs.local_simulator import SimulatorRefused  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 1 or argv[0] not in {"seed", "clear"}:
        print("usage: seed_pmc_wfs_local_demo.py seed [source_account_ref] | clear")
        return 2
    try:
        local_demo.guard()
    except SimulatorRefused as error:
        print("PMC_WFS_LOCAL_DEMO_REFUSED", error)
        return 2
    from app.db.session import get_session_factory

    register_productlist_sync_models()
    factory = get_session_factory()
    try:
        if argv[0] == "seed":
            result = local_demo.seed(factory, argv[1] if len(argv) > 1 else None)
        else:
            result = local_demo.clear(factory)
    except SimulatorRefused as error:
        print("PMC_WFS_LOCAL_DEMO_REFUSED", error)
        return 2
    except Exception as error:
        print("PMC_WFS_LOCAL_DEMO_FAILED", type(error).__name__, getattr(error, "code", ""))
        return 1
    print(f"preflight = ok (APP_ENV=local, 127.0.0.1:55432/szzsbj_dev); {argv[0]} done")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

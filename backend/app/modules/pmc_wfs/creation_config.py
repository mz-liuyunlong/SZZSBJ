"""WFS creation rollout switch (Rocky 2026-11-04: probe first, then one shipment, then batch).

``WFS_CREATION_MODE`` is an owner-set server variable; request data never changes it.

* ``off``    (default) nothing reaches Walmart; boxes are never held.
* ``probe``  read-only probe and the optional inbound preview; creation stays refused.
* ``single`` creation enabled, one planned shipment per operation (the first real test).
* ``batch``  creation enabled without the one-shipment limit.

The poll schedule is fixed by Rocky: every 3 minutes, at most 10 times, then failed.
"""

import os
from typing import Final, Literal

Mode = Literal["off", "probe", "single", "batch"]
MODE_ENV: Final = "WFS_CREATION_MODE"
MODES: Final = ("off", "probe", "single", "batch")
CREATION_MODES: Final = frozenset({"single", "batch"})
PREVIEW_MODES: Final = frozenset({"probe", "single", "batch"})

POLL_INTERVAL_SECONDS: Final = 180
POLL_MAX_ATTEMPTS: Final = 10


def creation_mode() -> Mode:
    value = os.getenv(MODE_ENV, "off").strip().lower()
    return value if value in MODES else "off"  # type: ignore[return-value]


MODE_REASONS: Final[dict[str, str]] = {
    "off": "Walmart 创建尚未启用（WFS_CREATION_MODE=off），可先核对分箱方案",
    "probe": "当前为探测模式：只做连通性探测和分仓预览，不会创建货件",
    "single": "当前为单个测试模式：每次只能创建 1 个计划货件",
    "batch": "",
}

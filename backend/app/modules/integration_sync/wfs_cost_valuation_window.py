"""WFS 成本计价流水（#369）的滚动时间窗：定时和手动同步共用。

这个接口每次运行必须带窗口（处理器缺窗口直接失败），单次最多 92 天。
决策口径：每日滚动 60 天（docs/data-sources/decisions/warehouse-wfs-inventory-claim-decision.md）。
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Final
from zoneinfo import ZoneInfo

WFS_COST_VALUATION_INTERFACE_KEY: Final = "wfsCostValuationFlow"
WFS_COST_VALUATION_ROLLING_DAYS: Final = 60
_SHANGHAI: Final = ZoneInfo("Asia/Shanghai")


def wfs_cost_valuation_rolling_window(now: datetime) -> tuple[datetime, datetime]:
    """最近 60 天（上海日期，含当天）。

    起止都存成 UTC 零点：处理器按 window_start.date() / window_end.date() 取日期（两头都含），
    UTC 零点取日期不会跨天。
    """
    if now.utcoffset() is None:
        raise ValueError("rolling window requires an aware instant")
    last_day = now.astimezone(_SHANGHAI).date()
    first_day = last_day - timedelta(days=WFS_COST_VALUATION_ROLLING_DAYS - 1)
    return (
        datetime.combine(first_day, time.min, UTC),
        datetime.combine(last_day, time.min, UTC),
    )

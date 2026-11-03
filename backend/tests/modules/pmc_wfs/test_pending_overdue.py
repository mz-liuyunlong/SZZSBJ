"""打包完成满 3 天未建货件标红 (Rocky 2026-11-02): day count in Asia/Shanghai."""

from datetime import UTC, date, datetime

from app.modules.pmc_wfs.service import PENDING_OVERDUE_DAYS, packed_days


def test_packed_days_counts_business_days_in_shanghai():
    # 2026-10-30 17:00 UTC is already 2026-10-31 01:00 in Shanghai → 3 days on 11-03.
    assert packed_days(datetime(2026, 10, 30, 17, 0, tzinfo=UTC), date(2026, 11, 3)) == 3
    assert packed_days(datetime(2026, 11, 1, 15, 0, tzinfo=UTC), date(2026, 11, 3)) == 2
    assert packed_days(None, date(2026, 11, 3)) is None
    assert PENDING_OVERDUE_DAYS == 3

from zoneinfo import ZoneInfo

from app.modules.integration_sync import data_pages_real_sync


def test_la_timezone_constant_exists_for_listing_snapshot_dates() -> None:
    assert data_pages_real_sync.LA_TZ == ZoneInfo("America/Los_Angeles")

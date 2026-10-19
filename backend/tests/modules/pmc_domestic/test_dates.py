from datetime import date

from app.modules.pmc_domestic.dates import receive_time_to_taipei_business_date


def test_receive_time_maps_shanghai_clock_to_taipei_calendar_day() -> None:
    assert receive_time_to_taipei_business_date("2026-10-09 23:30:00") == date(2026, 10, 9)
    assert receive_time_to_taipei_business_date("0000-00-00 00:00:00") is None

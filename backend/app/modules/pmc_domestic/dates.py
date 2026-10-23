"""Lingxing time strings for the domestic warehouse board."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")
TAIPEI = ZoneInfo("Asia/Taipei")


def receive_time_to_taipei_business_date(value: object) -> date | None:
    """Map a Lingxing ``receive_time`` string to the Taipei calendar date.

    Provider timestamps are Asia/Shanghai without a zone suffix. The board uses
    Taipei for ``received_business_date`` and days-in-warehouse.
    """

    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text.startswith("0000-00-00"):
        return None
    if len(text) >= 19:
        try:
            naive = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
            aware = naive.replace(tzinfo=SHANGHAI)
            return aware.astimezone(TAIPEI).date()
        except ValueError:
            pass
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None

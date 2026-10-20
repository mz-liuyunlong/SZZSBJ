from datetime import date

import pytest

from app.modules.warehouse_wfs.settlement_collector import (
    WfsCollectionError,
    collect_wfs_settlements,
)


def collect(fetch):
    return collect_wfs_settlements(
        fetch_page=fetch,
        store_id="110704872940532224",
        start_date=date(2026, 8, 19),
        end_date=date(2026, 10, 17),
        page_size=2,
        max_pages=3,
    )


def test_complete_pagination():
    def fetch(_interface, params):
        offset = params["offset"]
        rows = [
            {"uniqueId": "u", "rowIndex": i}
            for i in range(offset, min(offset + 2, 3))
        ]
        return {"code": 0, "total": 3, "data": {"list": rows}}

    result = collect(fetch)
    assert result.total == 3
    assert result.pages == 2
    assert len(result.rows) == 3


def test_empty_result():
    result = collect(
        lambda *_: {"code": 0, "total": 0, "data": {"list": []}}
    )
    assert result.rows == ()


def test_duplicate_line_rejected():
    def fetch(_interface, params):
        rows = [
            {"uniqueId": "u", "rowIndex": 1},
            {"uniqueId": "u", "rowIndex": 2},
        ] if params["offset"] == 0 else [
            {"uniqueId": "u", "rowIndex": 2}
        ]
        return {"code": 0, "total": 3, "data": {"list": rows}}

    with pytest.raises(WfsCollectionError, match="WFS_DUPLICATE_LINE"):
        collect(fetch)


def test_incomplete_page_rejected():
    with pytest.raises(WfsCollectionError, match="WFS_INCOMPLETE_PAGE"):
        collect(
            lambda *_: {
                "code": 0,
                "total": 3,
                "data": {"list": [{"uniqueId": "u", "rowIndex": 1}]},
            }
        )


def test_provider_error_rejected():
    with pytest.raises(WfsCollectionError, match="WFS_PROVIDER_ERROR"):
        collect(lambda *_: {"code": 1001})

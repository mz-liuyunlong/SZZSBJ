"""The two tracking reads use saved data and page only after global filtering."""

from datetime import date

from app.modules.new_products import tracking_read as reader


def _row(item, outcome="未判定", arrival="2026-09-01", owner="运营A", grade="A"):
    return {
        "id": "acc::store::" + item,
        "identity": ("acc", "store", item),
        "item": item,
        "sku": item,
        "name": "商品" + item,
        "owner": owner,
        "category": "类目1",
        "secondary": None,
        "grade": grade,
        "has_initial_grade": True,
        "arrival": arrival,
        "launch": arrival,
        "entry": arrival,
        "tracking": outcome,
    }


def test_board_counts_and_overdue_use_entire_saved_pool(monkeypatch):
    rows = [
        _row("one", "打品成功"),
        _row("two", "打品失败"),
        _row("three", "继续观察"),
        _row("four", "未判定", "2026-10-31"),
    ]
    monkeypatch.setattr(reader, "_projection", lambda *args: rows)
    data = reader.board_summary(None, None, frozenset({"acc"}),
                                date(2026, 9, 1), date(2026, 11, 1))
    assert data["counts"]["pool"] == 4
    assert data["counts"]["success"] == 1
    assert data["counts"]["failed"] == 1
    assert data["counts"]["due"] == 1
    assert data["success_rate"] == 25.0
    assert data["owners"][0]["rate"] == 50.0


def test_tracking_list_total_is_before_page_and_outcome_filtered(monkeypatch):
    rows = [_row(str(i), "打品成功" if i % 2 == 0 else "打品失败")
            for i in range(80)]
    monkeypatch.setattr(reader, "_projection", lambda *args: rows)
    result = reader.detail_list(None, None, frozenset({"acc"}),
                                page=10, page_size=20, keyword="", owners="", grades="",
                                outcome="success", drill_kind="", drill_value="",
                                parent_category="", start_date=None, end_date=None)
    assert result["total"] == 40
    assert result["items"] == []
    assert result["counts"]["all"] == 80
    assert result["counts"]["failure"] == 40


def test_tracking_list_date_range_is_scoped_before_counts(monkeypatch):
    rows = [_row("one", "打品成功", "2026-09-01"),
            _row("two", "打品失败", "2026-10-01")]
    monkeypatch.setattr(reader, "_projection", lambda *args: rows)
    result = reader.detail_list(None, None, frozenset({"acc"}),
                                page=2, page_size=20, keyword="", owners="", grades="",
                                outcome="all", drill_kind="all", drill_value="",
                                parent_category="", start_date=date(2026, 9, 1),
                                end_date=date(2026, 9, 30))
    assert result["total"] == 1
    assert result["counts"]["success"] == 1
    assert result["counts"]["failure"] == 0


def test_tracking_list_fetches_only_page_identities(monkeypatch):
    from app.modules.new_products import evaluation_workflow

    rows = [_row(str(i), "打品成功") for i in range(82)]
    monkeypatch.setattr(reader, "_projection", lambda *args: rows)
    seen = []

    class FakeService:
        def __init__(self, *args, **kwargs):
            pass

        def _list_saved(self, accounts, query, *, item_keys):
            seen.extend(item_keys)
            return {"items": [{"listing": {
                "source_account_ref": a, "store_id": s, "item_id": i,
            }} for a, s, i in item_keys]}

    monkeypatch.setattr(reader, "NewProductService", FakeService)
    monkeypatch.setattr(evaluation_workflow, "decorate_page", lambda _db, result: result)
    result = reader.detail_list(None, None, frozenset({"acc"}),
                                page=2, page_size=20, keyword="", owners="", grades="",
                                outcome="all", drill_kind="", drill_value="",
                                parent_category="", start_date=None, end_date=None)
    assert result["total"] == 82
    assert len(result["items"]) == 20
    assert len(seen) == 20
    assert all(row["tracking_page_decision"] == "打品成功" for row in result["items"])

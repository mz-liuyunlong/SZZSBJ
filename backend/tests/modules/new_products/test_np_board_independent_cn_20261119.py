"""New-product board independent aggregate: scoped, WFS-only, Chinese category."""

from datetime import date

from app.modules.new_products import performance_list_scope as scope


def test_board_scope_wfs_window_current_state_and_chinese_category(monkeypatch):
    rows = [
        dict(
            identity=("acc", "st", "one"),
            status="测评通过",
            grade="A",
            total="8.2",
            first_wfs=date(2026, 11, 3),
            category="厨房用品",
            developer="开发甲",
            sku="S1",
            name="商品甲",
            dimensions={},
            market_score="8",
        ),
        dict(
            identity=("acc", "st", "two"),
            status="测评未通过",
            grade="D",
            total="2",
            first_wfs=date(2026, 11, 5),
            category="Kitchen & Dining",
            developer="开发甲",
            sku="S2",
            name="商品乙",
            dimensions={"profit": "2"},
            market_score="5",
        ),
        dict(
            identity=("acc", "st", "three"),
            status="测评中",
            grade="pending",
            total=None,
            first_wfs=None,
            category="厨房用品",
            developer="开发甲",
            sku="S3",
            name="未到货",
            dimensions={},
            market_score=None,
        ),
        dict(
            identity=("acc", "st", "four"),
            status="待市场评分",
            grade="pending",
            total=None,
            first_wfs=date(2026, 9, 1),
            category="收纳",
            developer="开发乙",
            sku="S4",
            name="超出范围",
            dimensions={},
            market_score=None,
        ),
    ]
    monkeypatch.setattr(scope, "scoped_projection", lambda *_: rows)
    got = scope.board_summary(
        None,
        None,
        frozenset({"acc"}),
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 10),
    )
    assert got["counts"]["total"] == 2
    assert got["counts"]["passed"] == 1 and got["counts"]["failed"] == 1
    assert got["pass_rate"] == "50.0%"
    assert sorted(r["name"] for r in got["categories"]) == ["厨房用品"]
    assert got["untranslated_categories"] == 0
    assert got["failure_dimensions"]["profit"] == 1
    assert got["date_basis"] == "first_wfs_available_date_la"


def test_board_no_account_scope_does_not_access_source():
    class Never:
        def execute(self, *args, **kwargs):
            raise AssertionError("query out of scope")

        def scalar(self, *args, **kwargs):
            raise AssertionError("query out of scope")

    value = scope.board_summary(
        Never(),
        Never(),
        frozenset(),
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 30),
    )
    assert value["counts"]["total"] == 0


def test_board_date_range_rejects_reversed_dates():
    try:
        scope.board_summary(
            None,
            None,
            frozenset(),
            start_date=date(2026, 11, 30),
            end_date=date(2026, 11, 1),
        )
    except ValueError as e:
        assert str(e) == "NP_BOARD_DATE_RANGE_INVALID"
    else:
        raise AssertionError("reversed range accepted")


def test_known_english_category_translates_with_identity_retained():
    from app.modules.new_products.category_zh import translate_category

    assert translate_category("Kitchen & Dining") == "厨房与餐饮"
    assert translate_category("Home > Kitchen & Dining") == "家居 / 厨房与餐饮"
    assert translate_category("厨房用品") == "厨房用品"
    assert translate_category("") == "未分类"
    assert translate_category("unreviewed-new-category") == "待补充中文分类"

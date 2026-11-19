# Exact Chinese mapping coverage of the 2026-11-19 real board snapshot.

from app.modules.new_products.category_zh import _EXACT_CATEGORY_PATH_ZH, translate_category


def test_current_150_english_category_paths_have_chinese_translation():
    assert len(_EXACT_CATEGORY_PATH_ZH) == 151
    for raw, chinese in _EXACT_CATEGORY_PATH_ZH.items():
        assert translate_category(raw) == chinese, raw
        assert "待补充中文分类" not in chinese


def test_board_category_translations_keep_granularity_and_unknowns():
    assert (
        translate_category(
            "Home > Kitchen & Dining > Tools & Gadgets > "
            "Kitchen Tools & Gadgets > Chopping & Slicing"
        )
        == "厨房工具 / 切碎与切片工具"
    )
    assert (
        translate_category(
            "Auto & Tires > Interior Parts & Accessories > "
            "Car Organizers > Back Seat Organizers"
        )
        == "汽车收纳 / 后座收纳袋"
    )
    assert (
        translate_category(
            "Home > Kitchen & Dining > Dining & Entertaining > Drinkware"
        )
        == "餐桌用品 / 饮具"
    )
    assert translate_category(None) == "未分类"
    assert translate_category("") == "未分类"
    assert translate_category("unreviewed-new-category") == "待补充中文分类"

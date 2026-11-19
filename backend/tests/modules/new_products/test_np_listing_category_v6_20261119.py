"""Regression tests: all 479 valid Listing category paths use full Chinese paths."""
from app.modules.new_products.category_zh import (
    _EXACT_CATEGORY_PATH_ZH,
    _V6_EXACT_CATEGORY_PATH_ZH,
    business_category,
    category_path_detail,
    translate_category,
)


def test_v6_listing_category_count():
    assert len(_EXACT_CATEGORY_PATH_ZH) == 151
    assert len(_V6_EXACT_CATEGORY_PATH_ZH) == 328
    assert not set(_EXACT_CATEGORY_PATH_ZH).intersection(_V6_EXACT_CATEGORY_PATH_ZH)


def test_v6_listing_category_full_chinese():
    for raw in (*_EXACT_CATEGORY_PATH_ZH, *_V6_EXACT_CATEGORY_PATH_ZH):
        detail = category_path_detail(raw)
        assert detail["raw"] == raw
        assert detail["zh"] != "待补充中文分类"
        assert detail["zh"].split(" > ")[-1] == detail["label"]
        assert len(detail["zh"].split(" > ")) == len(raw.split(" > "))
        assert translate_category(raw) != "待补充中文分类"
        assert business_category(raw) not in {"未分类", "待补充中文分类"}


def test_v6_listing_category_examples():
    kitchen = (
        "Home > Kitchen & Dining > Tools & Gadgets > "
        "Kitchen Tools & Gadgets > Chopping & Slicing"
    )
    assert category_path_detail(kitchen)["zh"] == (
        "家居 > 厨房与餐饮 > 工具与小配件 > "
        "厨房工具与小配件 > 切碎与切片工具"
    )
    assert business_category(kitchen) == "厨房用品"
    toilet = "Household Essentials > Bathroom Cleaning Supplies > Toilet Brushes"
    assert category_path_detail(toilet)["zh"].endswith("浴室清洁用品 > 马桶刷")
    assert business_category(toilet) == "清洁用品"

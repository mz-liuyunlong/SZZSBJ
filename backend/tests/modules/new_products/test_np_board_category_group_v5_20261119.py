"""Business category aggregation and 2-line taxonomy sources; no DB writes."""

import re
from datetime import date

from app.modules.new_products import performance_list_scope as scope
from app.modules.new_products.category_zh import (
    _EXACT_CATEGORY_PATH_ZH,
    business_category,
    category_path_detail,
)


def test_full_english_to_chinese_path_levels():
    raw = "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadgets > Chopping & Slicing"
    expected = "家居 > 厨房与餐饮 > 工具与小配件 > 厨房工具与小配件 > 切碎与切片工具"
    pair = category_path_detail(raw)
    assert pair == {"raw": raw, "zh": expected, "label": "切碎与切片工具"}
    assert len(pair["zh"].split(" > ")) == len(raw.split(" > ")) == 5
    assert business_category(raw) == "厨房用品"


def test_all_151_verified_raw_paths_have_full_chinese_level_translation():
    assert len(_EXACT_CATEGORY_PATH_ZH) == 151
    for raw in _EXACT_CATEGORY_PATH_ZH:
        pair = category_path_detail(raw)
        assert len(pair["zh"].split(" > ")) == len(raw.split(" > ")), raw
        assert not re.search(r"[a-zA-Z]", pair["zh"]), raw
        assert business_category(raw) not in {"待补充中文分类", "未分类"}, raw


def test_board_groups_keep_item_count_and_each_original_path(monkeypatch):
    kitchen = (
        "Home > Kitchen & Dining > Tools & Gadgets > Kitchen Tools & Gadgets > Chopping & Slicing"
    )
    cups = "Home > Kitchen & Dining > Bakeware > Measuring Cups"
    storage = "Home > Storage & Organization > Storage Containers > Shop Storage Containers"

    def row(item_id, raw, status="测评中", first=date(2026, 11, 1)):
        return {
            "identity": ("account", "store", item_id),
            "status": status,
            "grade": "pending",
            "total": None,
            "first_wfs": first,
            "category": raw,
            "developer": "开发甲",
            "sku": "SKU" + item_id,
            "name": "商品" + item_id,
            "dimensions": {},
            "market_score": None,
        }

    sample = [row("1", kitchen), row("2", cups), row("3", storage), row("4", "")]
    sample += [row("5", kitchen, first=None)]
    monkeypatch.setattr(scope, "scoped_projection", lambda *_args: sample)
    response = scope.board_summary(
        None,
        None,
        frozenset({"account"}),
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 30),
    )
    assert response["counts"]["total"] == 4
    groups = {group["name"]: group for group in response["categories"]}
    assert sum(group["count"] for group in groups.values()) == 4
    assert groups["厨房用品"]["count"] == 2
    assert groups["家居收纳"]["count"] == 1
    assert groups["未分类"]["count"] == 1
    traces = groups["厨房用品"]["subcategories"]
    assert {detail["raw"] for detail in traces} == {kitchen, cups}
    assert all(detail["zh"] != "待补充中文分类" for detail in traces)
    assert groups["未分类"]["subcategories"] == []
    assert response["date_basis"] == "first_wfs_available_date_la"

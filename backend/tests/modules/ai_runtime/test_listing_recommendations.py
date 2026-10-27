"""05 Listing actions are always a read-only projection of 01 decisions."""

from app.modules.ai_runtime.listing_recommendations import (
    HEADERS_05,
    create_listing_actions,
)

HEADERS = (
    "关键词", "关键词中文意思", "关键词类型", "页面承接情况", "投放等级",
    "未上传原因",
)


def test_listing_actions_have_14_columns_and_block_hard_risk() -> None:
    rows = [
        ("coffee organizer", "咖啡收纳架", "核心本体词", "页面没埋但可优化", "P0", ""),
        ("competitor brand organizer", "", "品牌/竞品词", "页面没埋但可优化", "品牌等级", "竞品品牌"),
        ("mystery use", "", "人工确认词", "页面看不出来", "候选复查", "事实待确认"),
    ]
    headers, result = create_listing_actions(HEADERS, rows)
    assert headers == HEADERS_05
    assert all(len(row) == 14 for row in result)
    assert result[0][12] == "P0 必须补"
    assert result[1][4] == "否"
    assert result[1][13] == "加入禁用埋词"
    assert result[2][4] == "用户确认后再补"


def test_single_listing_draft_is_not_replicated_or_published() -> None:
    draft = {
        "title": "Confirmed organizer",
        "features": ["fact"] * 5,
        "description": "Confirmed use",
    }
    _, rows = create_listing_actions(HEADERS, [], draft=draft)
    assert len(rows) == 7
    assert rows[0][6] == "Confirmed organizer"
    assert all(row[4] == "用户确认后再补" for row in rows)

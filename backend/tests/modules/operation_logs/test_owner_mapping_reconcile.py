from app.modules.operation_logs.owner_mapping_reconcile import (
    matching_user_ids,
    normalize_owner_name,
)


def test_owner_name_normalization_is_exact_after_whitespace_normalization():
    assert normalize_owner_name("  刘云龙　") == normalize_owner_name("刘云龙")


def test_matching_owner_name_returns_one_unique_active_candidate():
    users = [
        {"id": 10, "display_name": "刘云龙", "feishu_name": None},
        {"id": 11, "display_name": "陈佳聪", "feishu_name": None},
    ]
    assert matching_user_ids(["刘云龙"], users) == {10}


def test_duplicate_names_are_ambiguous_not_auto_assigned():
    users = [
        {"id": 10, "display_name": "刘云龙", "feishu_name": None},
        {"id": 12, "display_name": "刘云龙", "feishu_name": None},
    ]
    assert matching_user_ids(["刘云龙"], users) == {10, 12}


def test_unmatched_owner_name_returns_no_candidate():
    users = [{"id": 10, "display_name": "刘云龙", "feishu_name": None}]
    assert matching_user_ids(["不存在的负责人"], users) == set()

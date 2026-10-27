"""One deterministic, 14-column Listing action sheet from persisted keyword decisions.

This is an internal review. Do not publish generated copy or re-score ads.
"""

from __future__ import annotations

from collections.abc import Sequence

HEADERS_05 = (
    "优化位置",
    "建议埋词",
    "中文意思",
    "当前页面状态",
    "是否建议补到页面",
    "具体怎么优化",
    "建议写法示例",
    "禁止写法",
    "为什么要这样做",
    "不建议埋词原因",
    "优化后预期影响",
    "执行顺序",
    "优先级",
    "执行动作",
)

BLOCKED_TYPES = frozenset(
    {
        "品牌/竞品词",
        "配件/替换词",
        "错货架词",
        "结构冲突词",
        "材质不符词",
        "规格/尺寸不符词",
        "Pack/数量不符词",
        "颜色/款式不符词",
        "合规/认证风险词",
        "机器设备词",
        "食材本身词",
    }
)
COVERAGE_TO_STATE = {
    "标题已埋词": "标题已埋",
    "标题意思已覆盖": "标题已埋",
    "详情/属性已埋词": "五点/详情已埋",
    "场景/用途能接住": "五点/详情已埋",
    "用户确认能接住": "页面埋得弱",
    "页面没埋但可优化": "标题没埋",
    "页面埋得弱，先验证": "页面埋得弱",
    "页面看不出来": "页面看不出来",
    "页面不建议埋": "页面不建议埋",
}


def _row(
    keyword: str,
    translation: str,
    primary: str,
    coverage: str,
    grade: str,
    reason: str,
    *,
    order: int,
) -> tuple[str, ...]:
    state = COVERAGE_TO_STATE.get(coverage, "页面看不出来")
    prohibited = (
        primary in BLOCKED_TYPES or grade in ("不投放", "品牌等级") or coverage == "页面不建议埋"
    )
    if prohibited:
        return (
            "暂不建议埋",
            keyword,
            translation,
            state,
            "否",
            "禁止把该词写入标题、五点、详情、图片或属性",
            "",
            "不得写竞品品牌或与实际材质、规格、结构、配件不符的声明",
            "仅使用已确认的真实商品事实",
            reason or primary,
            "避免误导买家及错配流量",
            str(order),
            "不建议补",
            "加入禁用埋词",
        )
    if grade not in ("P0", "P1", "P2") or coverage in ("页面看不出来", "页面埋得弱，先验证"):
        return (
            "暂不建议埋",
            keyword,
            translation,
            state,
            "用户确认后再补",
            "先核实商品事实、真实 Walmart 页面和该关键词的对应关系",
            "",
            "不得凭竞品标题推断本品的功能或规格",
            "目前证据不足，不能直接写入 Listing",
            reason or "承接待复核",
            "确认事实后再决定是否优化",
            str(order),
            "确认后再补",
            "先问用户确认",
        )
    if coverage in ("标题已埋词", "标题意思已覆盖"):
        return (
            "标题",
            keyword,
            translation,
            state,
            "否",
            "检查标题已有表达是否准确，不要重复堆砌相同关键词",
            "",
            "禁止重复关键词及不实功能描述",
            "现有标题已经承接，不需要为了广告重复埋词",
            "",
            "保持页面自然可读",
            str(order),
            "不建议补",
            "只做广告测试，不补页面",
        )
    if coverage in ("详情/属性已埋词", "场景/用途能接住"):
        return (
            "五点",
            keyword,
            translation,
            state,
            "否",
            "检查五点或详情中的现有表达是否对应商品事实",
            "",
            "禁止增加未经确认的功能、材质或适用场景",
            "页面已有文本承接，暂不重复扩写",
            "",
            "保留既有准确承接",
            str(order),
            "不建议补",
            "只做广告测试，不补页面",
        )
    pos, action, priority = (
        ("标题", "补到标题前半段", "P0 必须补")
        if grade == "P0"
        else ("五点", "补到五点", "P1 建议补")
        if grade == "P1"
        else ("详情描述", "补到详情描述", "P2 可选补")
    )
    return (
        pos,
        keyword,
        translation,
        state,
        "是",
        f"仅在确认本品能承接后，把“{keyword}”自然加入{pos}；先核对页面与包装事实",
        f"可使用已核实的“{keyword}”表达，补齐真实商品信息后由运营审稿",
        "禁止把竞品属性、未认证功能或不存在的配件写入页面",
        "当前页面尚未明确表达此已通过规则的关键词",
        "",
        "改善页面与已确认搜索意图的文本对应",
        str(order),
        priority,
        action,
    )


def create_listing_actions(
    headers_01: Sequence[str],
    rows_01: Sequence[Sequence[object]],
    *,
    draft: dict | None = None,
) -> tuple[tuple[str, ...], list[tuple[str, ...]]]:
    """Only project the 01 sheet; no independently generated grades or eligibility."""
    columns = {
        key: headers_01.index(key)
        for key in (
            "关键词",
            "关键词中文意思",
            "关键词类型",
            "页面承接情况",
            "投放等级",
            "未上传原因",
        )
    }
    actions: list[tuple[str, ...]] = []
    for order, row in enumerate(rows_01, 1):

        def field(name: str) -> str:
            value = row[columns[name]]
            return str(value) if value is not None else ""

        keyword = field("关键词")
        if not keyword:
            continue
        actions.append(
            _row(
                keyword,
                field("关键词中文意思"),
                field("关键词类型"),
                field("页面承接情况"),
                field("投放等级"),
                field("未上传原因"),
                order=order,
            )
        )
    if draft is not None:
        title = draft.get("title")
        features = draft.get("features")
        description = draft.get("description")
        if (
            isinstance(title, str)
            and title.strip()
            and isinstance(description, str)
            and description.strip()
            and isinstance(features, list)
            and len(features) == 5
            and all(isinstance(item, str) and item.strip() for item in features)
        ):
            # Exactly ONE saved listing draft. Mark every line as human-review only.
            copy_rows = (
                [("标题", title)]
                + [(f"五点", item) for item in features]
                + [("详情描述", description)]
            )
            for pos, content in copy_rows:
                actions.append(
                    (
                        pos,
                        "",
                        "",
                        "页面看不出来",
                        "用户确认后再补",
                        "根据已确认的商品事实逐句审稿，再决定是否发布",
                        content,
                        "不得发布未经核实的 AI 商品描述",
                        "这是同一份 AI Listing 草稿，并非已发布页面事实",
                        "",
                        "经人工核实后改善表达",
                        "0",
                        "确认后再补",
                        "先问用户确认",
                    )
                )
    return HEADERS_05, actions

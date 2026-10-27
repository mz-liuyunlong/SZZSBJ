"""V1.0 02/03 tables derived ONLY from persisted 01 and frozen keyword metadata."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping, Sequence
from statistics import mean

ROOT_HEADERS = (
    "核心词根",
    "词根中文意思",
    "词根等级",
    "词根处理类型",
    "词根判断类型",
    "关联关键词数量",
    "代表关键词",
    "平均潜力分",
    "最高潜力分",
    "页面承接情况",
    "是否已进入Exact",
    "是否进入Broad广告组",
    "Broad投放角色",
    "Broad扩词风险",
    "Broad准入判断",
    "Broad风险说明",
    "不进Broad原因",
    "后续处理建议",
)
RISK_HEADERS = (
    "关键词",
    "关键词中文意思",
    "核心词根",
    "冷启动投放潜力分",
    "风险类型",
    "不投放原因",
    "是否结构冲突",
    "是否规格冲突",
    "是否品牌词",
    "是否进入上传表",
    "后续处理建议",
)
RISK_LABELS = {
    "合规/认证风险词": "合规/认证风险",
    "错货架词": "错货架风险",
    "配件/替换词": "配件/替换风险",
    "结构冲突词": "结构冲突风险",
    "材质不符词": "材质不符风险",
    "规格/尺寸不符词": "规格/尺寸不符风险",
    "Pack/数量不符词": "Pack/数量不符风险",
    "颜色/款式不符词": "颜色/款式不符风险",
    "品牌/竞品词": "品牌/竞品风险",
    "泛流量词": "泛流量风险",
    "机器设备词": "机器设备风险",
    "食材本身词": "食材本身风险",
    "低价值重复词": "低价值重复",
    "人工确认词": "人工确认风险",
}
ROOT_GRADES = {
    "R0": "R0核心主词根",
    "R1": "R1高相关词根",
    "R2": "R2精准长尾词根",
}


def project_v1_review_sheets(
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    metadata: Mapping[str, Mapping[str, object]],
) -> tuple[list[tuple], list[tuple]]:
    col = {
        key: headers.index(key)
        for key in (
            "关键词",
            "关键词中文意思",
            "关键词类型",
            "核心词根",
            "页面承接情况",
            "冷启动投放潜力分",
            "投放等级",
            "未上传原因",
            "是否进入手动Exact",
            "是否进入手动Broad",
        )
    }
    groups: OrderedDict[str, list[Sequence[object]]] = OrderedDict()
    risks: list[tuple] = []
    for row in rows:
        keyword = str(row[col["关键词"]])
        root = str(row[col["核心词根"]] or "")
        if root:
            groups.setdefault(root.casefold(), []).append(row)
        kind = str(row[col["关键词类型"]])
        grade = str(row[col["投放等级"]])
        confirmed_brand = (
            kind == "品牌/竞品词" and grade == "品牌等级" and not row[col["未上传原因"]]
        )
        risky_type = kind in RISK_LABELS and not confirmed_brand
        if risky_type or grade in ("不投放", "候选复查") or row[col["未上传原因"]]:
            label = RISK_LABELS.get(kind, "页面无法证明" if grade == "候选复查" else "人工确认风险")
            risks.append(
                (
                    keyword,
                    row[col["关键词中文意思"]],
                    root,
                    row[col["冷启动投放潜力分"]],
                    label,
                    row[col["未上传原因"]] or grade,
                    "是" if kind == "结构冲突词" else "否",
                    "是" if kind in ("规格/尺寸不符词", "Pack/数量不符词") else "否",
                    "是" if kind == "品牌/竞品词" or grade == "品牌等级" else "否",
                    "是"
                    if row[col["是否进入手动Exact"]] == "是"
                    or row[col["是否进入手动Broad"]] == "是"
                    else "否",
                    "人工确认再决定，不自动作为否定关键词上传",
                )
            )
    roots = []
    for records in groups.values():
        representative = records[0]
        root_name = str(representative[col["核心词根"]])
        scores = [
            float(row[col["冷启动投放潜力分"]])
            for row in records
            if isinstance(row[col["冷启动投放潜力分"]], (int, float))
        ]
        covered = any(row[col["是否进入手动Exact"]] == "是" for row in records)
        selected = any(row[col["是否进入手动Broad"]] == "是" for row in records)
        roles = {
            str(metadata.get(str(row[col["关键词"]]).casefold(), {}).get("broad_role") or "")
            for row in records
            if row[col["是否进入手动Broad"]] == "是"
        }
        grade = str(
            metadata.get(str(representative[col["关键词"]]).casefold(), {}).get("root_grade") or ""
        )
        broad_role = (
            "词根" if "root" in roles else "安全精准长尾" if "long_tail" in roles else "未入选"
        )
        row_meta = metadata.get(str(representative[col["关键词"]]).casefold(), {})
        reason = str(row_meta.get("broad_reason") or "")
        roots.append(
            (
                root_name,
                root_name,
                ROOT_GRADES.get(grade, "-"),
                "可投放词根" if selected else "边界风险待确认",
                "来自已确认的01表与冻结词根证据",
                len(records),
                representative[col["关键词"]],
                round(mean(scores), 2) if scores else "",
                max(scores) if scores else "",
                representative[col["页面承接情况"]],
                "是" if covered else "否",
                "是" if selected else "否",
                broad_role,
                "需复核" if selected else "未知",
                "满足冻结证据" if selected else "暂未通过",
                reason,
                "" if selected else reason or "未通过Broad准入审核",
                "入选后监测搜索词扩展" if selected else "先核实商品页面、词根及扩词风险",
            )
        )
    return roots, risks

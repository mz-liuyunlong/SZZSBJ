"""PR337 confirmed scoring parameter validation; accepts complete unchanged RuleDraft JSON."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

DEFAULT_WEIGHTS = {"market": 15, "speed": 30, "ad": 20, "profit": 25, "trust": 10}
DEFAULT_PARAMETERS = {
    "speed": {
        "firstFullDays": 3,
        "firstZeroDays": 14,
        "observationDays": 14,
        "targetOrders": 20,
        "firstWeight": 40,
        "ordersWeight": 60,
    },
    "ad": {
        "acosFull": 20,
        "acosZero": 70,
        "cpcFull": 0.8,
        "cpcZero": 2,
        "cvrZero": 2,
        "cvrFull": 8,
        "minClicks": 20,
        "acosWeight": 40,
        "cpcWeight": 20,
        "cvrWeight": 40,
    },
    "profit": {
        "roiZero": 0.5,
        "roiFull": 1.5,
        "marginZero": 10,
        "marginFull": 25,
        "roiWeight": 60,
        "marginWeight": 40,
    },
    "trust": {
        "targetUnits": 20,
        "singleRatioZero": 40,
        "singleRatioFull": 90,
        "unitsWeight": 60,
        "singleRatioWeight": 40,
    },
}


def dec(x: Any) -> Decimal:
    if isinstance(x, bool) or x is None:
        raise ValueError("missing or invalid numeric parameter")
    try:
        v = Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError) as e:
        raise ValueError("invalid numeric parameter") from e
    if not v.is_finite():
        raise ValueError("non-finite numeric parameter")
    return v


def _validate_thresholds(cfg: dict):
    w = cfg.get("weights")
    if (
        not isinstance(w, dict)
        or set(w) != set(DEFAULT_WEIGHTS)
        or sum((dec(x) for x in w.values()), Decimal(0)) != 100
    ):
        raise ValueError("五维权重合计必须为100%")
    p = cfg.get("confirmedScoring")
    if not isinstance(p, dict):
        raise ValueError("缺少已确认的评分配置 confirmedScoring")
    for kind, fields in DEFAULT_PARAMETERS.items():
        section = p.get(kind)
        if not isinstance(section, dict) or set(section) != set(fields):
            raise ValueError(f"{kind}评分参数不完整")
        for _name, v in section.items():
            if dec(v) < 0:
                raise ValueError("评分参数不可为负数")
    s, a, pr, t = (p[k] for k in ("speed", "ad", "profit", "trust"))
    for section, keys in (
        (s, ["firstFullDays", "firstZeroDays", "observationDays", "targetOrders"]),
        (a, ["minClicks"]),
        (t, ["targetUnits"]),
    ):
        for key in keys:
            v = dec(section[key])
            if v < 1 or v != v.to_integral_value():
                raise ValueError(key + "必须为正整数")
    if dec(s["observationDays"]) > 180:
        raise ValueError("观察周期超出上限")
    for ok in [
        dec(s["firstZeroDays"]) > dec(s["firstFullDays"]),
        dec(a["acosZero"]) > dec(a["acosFull"]),
        dec(a["cpcZero"]) > dec(a["cpcFull"]),
        dec(a["cvrFull"]) > dec(a["cvrZero"]),
        dec(pr["roiFull"]) > dec(pr["roiZero"]),
        dec(pr["marginFull"]) > dec(pr["marginZero"]),
        dec(t["singleRatioFull"]) > dec(t["singleRatioZero"]),
    ]:
        if not ok:
            raise ValueError("评分零分与满分阈值顺序错误")
    for part, keys in [
        (s, ["firstWeight", "ordersWeight"]),
        (a, ["acosWeight", "cpcWeight", "cvrWeight"]),
        (pr, ["roiWeight", "marginWeight"]),
        (t, ["unitsWeight", "singleRatioWeight"]),
    ]:
        if sum((dec(part[k]) for k in keys), Decimal(0)) != 100:
            raise ValueError("维度内权重之和必须100%")
    for part, keys in [
        (a, ["acosFull", "acosZero", "cvrZero", "cvrFull"]),
        (pr, ["marginZero", "marginFull"]),
        (t, ["singleRatioZero", "singleRatioFull"]),
    ]:
        if any(dec(part[k]) > 100 for k in keys):
            raise ValueError("百分比范围错误")
    bands = cfg.get("gradeBands")
    if not isinstance(bands, dict) or set(bands) != {"S", "A", "B", "C", "D"}:
        raise ValueError("评级区间缺失")
    for tier, pair in bands.items():
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or not (0 <= dec(pair[0]) <= dec(pair[1]) <= 10)
        ):
            raise ValueError("评级区间错误 " + tier)
    # Grade thresholds must be contiguous to 0.01 precision for authoritative
    # backend scoring. Frontend validation alone cannot enforce persisted rules.
    ordered = ["D", "C", "B", "A", "S"]
    if dec(bands["D"][0]) != 0 or dec(bands["S"][1]) != 10:
        raise ValueError("评级区间必须覆盖0至10分")
    for lower, upper in zip(ordered, ordered[1:], strict=False):
        if dec(bands[upper][0]) - dec(bands[lower][1]) != Decimal("0.01"):
            raise ValueError("评级区间必须连续且互不重叠")
    quantities = cfg.get("quantities")
    if not isinstance(quantities, dict) or not {"S", "A", "B", "C", "D", "Pass"}.issubset(
        quantities
    ):
        raise ValueError("缺少采购数量配置")
    for name, pair in quantities.items():
        if (
            len(pair) != 2
            or not (0 <= dec(pair[0]) <= dec(pair[1]))
            or any(dec(v) != dec(v).to_integral_value() for v in pair)
        ):
            raise ValueError("采购范围错误 " + name)
    if any(dec(v) != 0 for k in ("D", "Pass") for v in quantities[k]):
        raise ValueError("D/Pass不建议采购")
    if not isinstance(cfg.get("scoreCriteria"), dict):
        raise ValueError("人工评分标准缺失")
    if not isinstance(cfg.get("penalties"), list) or not isinstance(cfg.get("vetoes"), list):
        raise ValueError("风险规则缺失")
    return cfg


TRACKING_NUMERIC = {
    "successStartDay",
    "focusStartDay",
    "focusEndDay",
    "availableCoveragePct",
    "healthyMarginPct",
    "recentLossDays",
    "sustainedLossDays",
    "marginDropPoints",
    "profitDropPct",
    "lowVolumeDailyOrders",
    "stockAttentionDays",
    "stockSevereDays",
    "stockSafetyDays",
    "replenishmentAttentionDays",
    "replenishmentSevereDays",
}
TRACKING_BOOLEAN = {
    "lowVolumeProtection",
    "profitDeteriorationAlert",
    "inventoryRiskAlert",
    "notifyRecommendationChange",
    "notifyMajorRisk",
    "notifyMilestones",
}


def validate(kind: str, config: dict) -> dict:
    if not isinstance(config, dict):
        raise ValueError("规则必须为 JSON object")
    if kind == "performance":
        return _validate_thresholds(config)
    if kind != "tracking":
        raise ValueError("未知规则类型")
    if set(config) != (TRACKING_NUMERIC | TRACKING_BOOLEAN):
        raise ValueError("打品辅助规则字段不完整")
    for k in TRACKING_NUMERIC:
        if dec(config[k]) < 0:
            raise ValueError("负数阈值 " + k)
    for k in TRACKING_BOOLEAN:
        if not isinstance(config[k], bool):
            raise ValueError("开关值错误 " + k)
    if dec(config["focusEndDay"]) < dec(config["focusStartDay"]) or dec(
        config["successStartDay"]
    ) > dec(config["focusEndDay"]):
        raise ValueError("观察天数不合法")
    if dec(config["sustainedLossDays"]) <= dec(config["recentLossDays"]):
        raise ValueError("亏损窗口顺序错误")
    return config

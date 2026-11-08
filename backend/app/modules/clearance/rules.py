"""Global versioned WFS Clearance rule contract (LA business-day semantics)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Period = Literal[7, 14, 30]


class ClearanceRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Stock and qualifying risks. Do not use age-lot quantities: not reliable.
    coverageLookback: Period = 30
    highCoverage: int = Field(default=180, ge=1, le=3650)
    mediumCoverage: int = Field(default=90, ge=1, le=3650)
    assistCoverage: int = Field(default=60, ge=1, le=3650)
    zeroLookback: Period = 30
    minListingDays: int = Field(default=30, ge=1, le=3650)
    newProductProtectionDays: int = Field(default=60, ge=0, le=3650)
    minBusinessSignals: int = Field(default=1, ge=1, le=10)
    enableCoverage: bool = True
    enableZero: bool = True
    enableAssisted: bool = True

    # Business signals; independently switchable, grouped for counting.
    enableProfit: bool = True
    enableMargin30: bool = False
    margin30Threshold: float = Field(default=8, ge=0, le=100)
    enableDecline: bool = True
    salesDropPercent: float = Field(default=40, ge=0, le=100)
    minBaselineSales7: int = Field(default=10, ge=1, le=1000000)
    minSalesDropUnits7: int = Field(default=5, ge=1, le=1000000)
    enableAd: bool = True
    adRateIncrease: float = Field(default=5, ge=0, le=100)
    enableReturns: bool = True
    returnRate: float = Field(default=8, ge=0, le=100)
    minReturns30: int = Field(default=5, ge=1, le=1000000)
    minReturnSales30: int = Field(default=30, ge=1, le=1000000)
    enableRating: bool = True
    ratingThreshold: float = Field(default=3.8, ge=1, le=5)
    minReviewCount: int = Field(default=10, ge=1, le=1000000)
    enableLastSale: bool = False
    lastSaleDaysLimit: int = Field(default=14, ge=1, le=3650)
    enableActiveDays: bool = False
    maxActiveSalesDays30: int = Field(default=5, ge=0, le=30)
    enableAdConversion: bool = False
    minAdClicks30: int = Field(default=80, ge=1, le=10000000)
    maxAdConversionPercent: float = Field(default=1, ge=0, le=100)
    enableNetSales: bool = False
    maxNetUnits30: int = Field(default=5, ge=0, le=1000000)

    # Protection cannot hide independently proven high risks.
    enableNewProductProtection: bool = True
    enableRecoveryProtection: bool = False
    salesRecoveryPercent: float = Field(default=50, ge=0, le=1000)
    minSalesForRecovery: int = Field(default=5, ge=1, le=1000000)
    enableBuyBoxProtection: bool = False
    enableInboundConflict: bool = True
    inboundConflictMin: int = Field(default=1, ge=1, le=1000000)
    enablePurchaseConflict: bool = False
    purchaseConflictMin: int = Field(default=1, ge=1, le=1000000)

    # Sorting and non-executing recommendations.
    enableCapitalPriority: bool = True
    minStockCapital: float = Field(default=3000, ge=0, le=1000000000)
    enableRiskDuration: bool = False
    riskDaysThreshold: int = Field(default=7, ge=1, le=3650)
    enableHoldingCost: bool = False
    holdingCost30Threshold: float = Field(default=60, ge=0, le=1000000000)
    enableQtySuggestion: bool = True
    targetHoldingDays: int = Field(default=60, ge=0, le=3650)
    safetyStockUnits: int = Field(default=50, ge=0, le=1000000)
    enableFloorPrice: bool = False
    allowedClearanceLoss: float = Field(default=0, ge=0, le=1000000)
    enableClearanceReview: bool = False
    # Existing re-backlog reminder is not a batch-age rule or admission signal.
    # Retain the current flag in versioned config without changing risk evaluation.
    enableRepeatBacklog: bool = False

    @model_validator(mode="after")
    def ensure_ascending_stock_thresholds(self) -> ClearanceRules:
        if not self.assistCoverage < self.mediumCoverage < self.highCoverage:
            raise ValueError("售罄阈值必须满足：经营辅助 < 中风险 < 高风险")
        return self


CLEARANCE_RULE_CATALOG = (
    ("库存风险", "coverageLookback", "预计售罄统计周期", "lookback"),
    ("库存风险", "highCoverage", "高风险售罄天数", "number"),
    ("库存风险", "mediumCoverage", "中风险售罄天数", "number"),
    ("库存风险", "assistCoverage", "经营辅助准入天数", "number"),
    ("库存风险", "enableCoverage", "启用售罄天数识别", "switch"),
    ("库存风险", "enableAssisted", "启用经营辅助识别", "switch"),
    ("滞销与经营", "zeroLookback", "零销量观察窗口", "lookback"),
    ("滞销与经营", "minListingDays", "零销量最低上架天数", "number"),
    ("滞销与经营", "enableZero", "启用零销量高风险", "switch"),
    ("滞销与经营", "minBusinessSignals", "经营辅助最少异常类数", "number"),
    ("滞销与经营", "enableProfit", "启用7/14天持续亏损", "switch"),
    ("滞销与经营", "enableMargin30", "启用30天低利润率", "switch"),
    ("滞销与经营", "margin30Threshold", "30天利润率低于", "number"),
    ("滞销与经营", "enableDecline", "启用销量下滑", "switch"),
    ("滞销与经营", "salesDropPercent", "7天销量下降比例", "number"),
    ("滞销与经营", "minBaselineSales7", "上一个7天最低销量", "number"),
    ("滞销与经营", "minSalesDropUnits7", "7天最少下降件数", "number"),
    ("滞销与经营", "enableAd", "启用广告占比上升且亏损", "switch"),
    ("滞销与经营", "adRateIncrease", "广告占比上升百分点", "number"),
    ("滞销与经营", "enableReturns", "启用退货率异常", "switch"),
    ("滞销与经营", "returnRate", "30天退货率阈值", "number"),
    ("滞销与经营", "minReturns30", "退货率最低退货件数", "number"),
    ("滞销与经营", "minReturnSales30", "退货率最低销量件数", "number"),
    ("滞销与经营", "enableRating", "启用低评分异常", "switch"),
    ("滞销与经营", "ratingThreshold", "最低评分阈值", "number"),
    ("滞销与经营", "minReviewCount", "评分最低评论数", "number"),
    ("滞销与经营", "enableLastSale", "启用最后出单间隔", "switch"),
    ("滞销与经营", "lastSaleDaysLimit", "最后出单间隔天数", "number"),
    ("滞销与经营", "enableActiveDays", "启用有效出单天数", "switch"),
    ("滞销与经营", "maxActiveSalesDays30", "30天有效出单天数上限", "number"),
    ("滞销与经营", "enableAdConversion", "启用广告低转化", "switch"),
    ("滞销与经营", "minAdClicks30", "最低30天广告点击", "number"),
    ("滞销与经营", "maxAdConversionPercent", "最低广告转化率", "number"),
    ("滞销与经营", "enableNetSales", "启用净销量偏低", "switch"),
    ("滞销与经营", "maxNetUnits30", "30天净销量上限", "number"),
    ("保护与冲突", "enableNewProductProtection", "启用新品保护", "switch"),
    ("保护与冲突", "newProductProtectionDays", "新品保护天数", "number"),
    ("保护与冲突", "enableRecoveryProtection", "启用销量恢复保护", "switch"),
    ("保护与冲突", "salesRecoveryPercent", "销量恢复百分比", "number"),
    ("保护与冲突", "minSalesForRecovery", "销量恢复最低样本", "number"),
    ("保护与冲突", "enableBuyBoxProtection", "启用购物车保护", "switch"),
    ("保护与冲突", "enableInboundConflict", "启用在途补货冲突提醒", "switch"),
    ("保护与冲突", "inboundConflictMin", "在途补货提醒件数", "number"),
    ("保护与冲突", "enablePurchaseConflict", "启用未完成采购冲突提醒", "switch"),
    ("保护与冲突", "purchaseConflictMin", "未完成采购提醒件数", "number"),
    ("优先级", "enableCapitalPriority", "启用库存资金占用提醒", "switch"),
    ("优先级", "minStockCapital", "库存资金占用阈值", "number"),
    ("优先级", "enableRiskDuration", "启用风险持续天数提醒", "switch"),
    ("优先级", "riskDaysThreshold", "风险持续最低天数", "number"),
    ("优先级", "enableHoldingCost", "启用预计持有成本提醒", "switch"),
    ("优先级", "holdingCost30Threshold", "30天持有成本阈值", "number"),
    ("清货建议", "enableQtySuggestion", "启用建议清货数量", "switch"),
    ("清货建议", "targetHoldingDays", "建议保留销售天数", "number"),
    ("清货建议", "safetyStockUnits", "额外安全库存", "number"),
    ("清货建议", "enableFloorPrice", "启用建议最低清货价", "switch"),
    ("清货建议", "allowedClearanceLoss", "每件容忍清货亏损", "number"),
    ("清货建议", "enableClearanceReview", "启用任务效果复盘", "switch"),
)

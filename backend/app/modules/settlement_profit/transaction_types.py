"""沃尔玛账单交易类型：中文名翻译表 + 订单行归类（PRP §0.3、§7A）。

账单一行 = (transactionType, transactionDescription, amountType)。订单审核只把带订单号、且属于
订单级的金额归到订单行；店铺级（广告、仓储、调拨、返还、SEM、杂项发票、WFS 退货处理 / 弃置等）
不进订单行，由结算利润那边处理。

清单来自 2026-10-26 本地归档的 7 家店账单（97 种组合）；新类型出现时同步任务告警，翻译补上前
不上线（§7A）。测试断言清单里每一种组合都有中文名、都有归类。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

# 订单行金额列（fact_settlement_order_lines 的列名去掉 _usd）
LineColumn = Literal[
    "sales",
    "refund",
    "promotion",
    "commission",
    "return_fee",
    "tax_withheld",
    "wfs_fulfillment_fee",
    "mcf_fee",
]
# store = 店铺级，不进订单行；excluded = WFS 服务费类，只用 WFS 费用表（§0.3 通用规则）
Category = LineColumn | Literal["store", "excluded"]


@dataclass(frozen=True, slots=True)
class TransactionTypeInfo:
    code: str
    transaction_type: str
    transaction_description: str
    amount_type: str
    name_zh: str
    category: Category


TRANSACTION_TYPE_ZH: Final[dict[str, str]] = {
    "Sale": "销售",
    "Refund": "退款",
    "Adjustment": "调整",
    "Service Fee": "服务费",
    "Campaigns": "广告活动",
    "Other": "其他",
    "Dispute Settlement": "争议裁定",
}

DESCRIPTION_ZH: Final[dict[str, str]] = {
    "Purchase": "购买",
    "Return Refund": "退货退款",
    "Keep-it refund": "免退货退款",
    "Seller Initiated Returns": "卖家发起退货",
    "Seller Triggered Refund": "卖家发起退款",
    "Walmart Customer Care Refund": "沃尔玛客服退款",
    "Customer Chargeback": "买家拒付",
    "WFS Fulfillment fee": "WFS 配送费",
    "WFS Return Processing Fee": "WFS 退货处理费",
    "WFS Returned Item Disposal Fee": "WFS 退货商品弃置费",
    "WFS StorageFee": "WFS 仓储费",
    "WFS InboundTransportationFee": "WFS 入库运输费",
    "WFS InventoryTransferFee": "WFS 调拨费",
    "WFS FoundInventory": "WFS 找回库存",
    "WFS LostInventory": "WFS 丢失库存",
    "WFS DamageInWarehouse": "WFS 仓内损坏",
    "WFS Refund": "WFS 退费",
    "WFS Charge": "WFS 收费",
    "WFS PrepServiceFee": "WFS 预处理服务费",
    "WFS InventoryDisposalOrder": "WFS 库存弃置单",
    "WFS InventoryRemovalOrder": "WFS 库存移除单",
    "WFS RC_InventoryDisposalFee": "WFS 退货中心库存弃置费",
    "WFS DiscountAdjustment": "WFS 费用返还",
    "WFS MultiChannelFulfillmentFee": "WFS 多渠道配送费",
    "SEM Marketing": "SEM 营销",
    "Walmart Product Advertising": "沃尔玛商品广告",
    "Walmart Product Advertising Credits": "沃尔玛商品广告赠送额度",
    "Review Accelerator": "评价加速器",
    "Misc Invoices": "杂项发票",
    "Walmart Return Shipping Charge": "沃尔玛退货运费",
    "Walmart Failed Return Delivery Processing Charge": "沃尔玛退货配送失败处理费",
    "CUSTOMER RETURN REFUND REVERSAL-LOST LATER DELIVERED": "买家退货退款冲回（丢失后送达）",
    "Customer Return Reversal": "买家退货冲回",
}

AMOUNT_TYPE_ZH: Final[dict[str, str]] = {
    "Product Price": "商品价格",
    "Commission on Product": "商品佣金",
    "Product tax": "商品税",
    "Product tax withheld": "商品税代扣",
    "Other tax (Fees)": "其他税（费用）",
    "Promo Code": "促销码折扣",
    "Total Walmart Funded Savings": "沃尔玛承担的优惠",
    "Extra Savings": "额外优惠",
    "ExcessRefundAdjustment": "超额退款调整",
    "Fee/Reimbursement": "费用 / 补偿",
    "WFS Inventory Fee/Reimbursement": "WFS 库存费用 / 补偿",
    "WFS Inbound Fee": "WFS 入库费用",
    "WFS Fee/Reimbursement": "WFS 费用 / 补偿",
    "SEM Marketing Fee": "SEM 营销费",
    "Review Accelerator Fee": "评价加速器费",
    "Retroactive Discount": "追溯折扣",
    "Item Fees": "商品费用",
    "": "（无）",
}

# 订单级金额按 amountType 归列（§0.2、§0.3）。
_ORDER_AMOUNT_COLUMNS: Final[dict[str, LineColumn]] = {
    "Commission on Product": "commission",
    "Product tax": "tax_withheld",
    "Product tax withheld": "tax_withheld",
    "Other tax (Fees)": "tax_withheld",
    "Promo Code": "promotion",
    "Total Walmart Funded Savings": "promotion",
    "Extra Savings": "promotion",
    "ExcessRefundAdjustment": "refund",
}

# 带订单号但不进订单行的描述：WFS 退货处理费 / 弃置费只用 WFS 费用表（§0.3）。
_EXCLUDED_DESCRIPTIONS: Final[frozenset[str]] = frozenset(
    {"WFS Return Processing Fee", "WFS Returned Item Disposal Fee"}
)
# 非 WFS 的退货处理类（§0.3 第一行）
_RETURN_FEE_DESCRIPTIONS: Final[frozenset[str]] = frozenset(
    {
        "Walmart Return Shipping Charge",
        "Walmart Failed Return Delivery Processing Charge",
    }
)
# 退款冲回（钱回到卖家）：归退款列，正数抵减退款，不是费用（#373 复审 P3-1）
_REFUND_REVERSAL_DESCRIPTIONS: Final[frozenset[str]] = frozenset(
    {
        "CUSTOMER RETURN REFUND REVERSAL-LOST LATER DELIVERED",
        "Customer Return Reversal",
    }
)


def categorize(
    transaction_type: str | None,
    transaction_description: str | None,
    amount_type: str | None,
) -> Category:
    """一行账单归到订单行的哪一列；店铺级返回 store，WFS 服务费类返回 excluded。"""
    ttype = (transaction_type or "").strip()
    desc = (transaction_description or "").strip()
    atype = (amount_type or "").strip()
    if desc in _EXCLUDED_DESCRIPTIONS:
        return "excluded"
    if desc == "WFS Fulfillment fee":
        return "wfs_fulfillment_fee"
    if desc == "WFS MultiChannelFulfillmentFee":
        return "mcf_fee"
    if desc in _RETURN_FEE_DESCRIPTIONS:
        return "return_fee"
    if desc in _REFUND_REVERSAL_DESCRIPTIONS:
        return "refund"
    if ttype in {"Sale", "Refund"}:
        if atype == "Product Price":
            return "sales" if ttype == "Sale" else "refund"
        column = _ORDER_AMOUNT_COLUMNS.get(atype)
        if column is not None:
            return column
    return "store"


def type_code(
    transaction_type: str | None,
    transaction_description: str | None,
    amount_type: str | None,
) -> str:
    return "|".join(
        (
            (transaction_type or "").strip(),
            (transaction_description or "").strip(),
            (amount_type or "").strip(),
        )
    )


def describe(
    transaction_type: str | None,
    transaction_description: str | None,
    amount_type: str | None,
) -> TransactionTypeInfo | None:
    """三段都能翻译才返回；缺任何一段的翻译返回 None（新类型，要先补翻译表）。"""
    ttype = (transaction_type or "").strip()
    desc = (transaction_description or "").strip()
    atype = (amount_type or "").strip()
    if (
        ttype not in TRANSACTION_TYPE_ZH
        or desc not in DESCRIPTION_ZH
        or atype not in AMOUNT_TYPE_ZH
    ):
        return None
    parts = [TRANSACTION_TYPE_ZH[ttype], DESCRIPTION_ZH[desc]]
    if atype:
        parts.append(AMOUNT_TYPE_ZH[atype])
    return TransactionTypeInfo(
        code=type_code(ttype, desc, atype),
        transaction_type=ttype,
        transaction_description=desc,
        amount_type=atype,
        name_zh=" / ".join(parts),
        category=categorize(ttype, desc, atype),
    )


def english_name(
    transaction_type: str | None,
    transaction_description: str | None,
    amount_type: str | None,
) -> str:
    parts = [
        p for p in ((transaction_type or "").strip(), (transaction_description or "").strip()) if p
    ]
    atype = (amount_type or "").strip()
    if atype:
        parts.append(atype)
    return " / ".join(parts)

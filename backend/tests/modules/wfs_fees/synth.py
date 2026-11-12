"""WFS 费用测试用合成报表（没有真实店铺、商品、金额）。"""

from __future__ import annotations

import csv
import io

STORE_A = "900000000000000001"
STORE_B = "900000000000000002"
PARTNER_A = "10009900001"
GTIN_1 = "00400000000013"
GTIN_2 = "00400000000020"
GTIN_3 = "00400000000037"
CARGO = "9900001WFA"

API_SETTLEMENT_HEAD = [
    "Order ID",
    "Order Line Number",
    "PO Number",
    "PO Line Number",
    "Transaction Type",
    "Reason Code",
    "Detail",
    "WFS Reference ID",
    "Transaction Date and Time",
    "Quantity",
    "Billing Method",
    "Partner ID",
    "GTIN",
    "Item Name",
    "Category",
    "Subcategory",
    "Net Payable",
    "Customer Order ID",
    "Order Channel ID",
    "Original Amount",
    "Discount Savings",
]
SC_SETTLEMENT_HEAD = [
    "Walmart.com Order #",
    "Walmart.com Order Line #",
    "Walmart.com PO #",
    "Walmart.com PO Line #",
    "Transaction Type",
    "Reason Code",
    "Detail",
    "WFSReferenceID",
    "Transaction Date/Time",
    "Qty",
    "Partner ID",
    "Partner GTIN",
    "Partner Item Name",
    "Category",
    "Sub Category",
    "Net Payable",
    "CustomerOrderId",
    "OrderChannelId",
]


def _csv(rows: list[list[str]]) -> bytes:
    out = io.StringIO()
    csv.writer(out).writerows(rows)
    return out.getvalue().encode("utf-8")


def settlement(rows: list[dict[str, str]], *, seller_center: bool = False) -> bytes:
    """rows 的键用接口列名；seller_center=True 时转成卖家后台的列名和 ="…" 保护符。"""
    head = SC_SETTLEMENT_HEAD if seller_center else API_SETTLEMENT_HEAD
    # 接口列名 → 卖家后台列名（两张表头顺序、列数都不同，不能按位置 zip）
    rename = {
        "Order ID": "Walmart.com Order #",
        "Order Line Number": "Walmart.com Order Line #",
        "PO Number": "Walmart.com PO #",
        "PO Line Number": "Walmart.com PO Line #",
        "Transaction Type": "Transaction Type",
        "Reason Code": "Reason Code",
        "Detail": "Detail",
        "WFS Reference ID": "WFSReferenceID",
        "Transaction Date and Time": "Transaction Date/Time",
        "Quantity": "Qty",
        "Partner ID": "Partner ID",
        "GTIN": "Partner GTIN",
        "Item Name": "Partner Item Name",
        "Category": "Category",
        "Subcategory": "Sub Category",
        "Net Payable": "Net Payable",
        "Customer Order ID": "CustomerOrderId",
        "Order Channel ID": "OrderChannelId",
    }
    out = [head]
    for row in rows:
        full = {k: row.get(k, "") for k in API_SETTLEMENT_HEAD}
        if seller_center:
            full = {rename[k]: v for k, v in full.items() if k in rename}
            for key in ("Partner ID", "Partner GTIN"):
                if full.get(key):
                    full[key] = f'="{full[key]}"'
        out.append([full.get(k, "") for k in head])
    return _csv(out)


def fee(
    fee_type: str,
    day: str,
    net: str,
    *,
    gtin: str = "",
    ref: str = "",
    reason: str = "",
    detail: str = "",
    po: str = "",
    qty: str = "1",
    orig: str = "",
    disc: str = "",
    partner: str = PARTNER_A,
) -> dict[str, str]:
    return {
        "Transaction Type": fee_type,
        "Reason Code": reason,
        "Detail": detail,
        "WFS Reference ID": ref,
        "Transaction Date and Time": day,
        "Quantity": qty,
        "Partner ID": partner,
        "GTIN": gtin,
        "PO Number": po,
        "Net Payable": net,
        "Original Amount": orig,
        "Discount Savings": disc,
    }


STORAGE_HEAD = [
    "GTIN",
    "SKU",
    "Item ID",
    "Item Name",
    "Length (in)",
    "Width (in)",
    "Height (in)",
    "Weight (lb)",
    "Standard: daily storage fee per unit",
    "Peak: daily storage fee per unit",
    "Long-term (366-450 days): daily storage fee per unit",
    "Long-term (450+ days): daily storage fee per unit",
    "Standard: average daily units available",
    "Peak: average daily units available",
    "Long-term (366-450 days): average daily units available",
    "Long-term (450+ days): average daily units available",
    "Days in report period",
    "Final storage fee",
    "Original Amount",
    "Discount Savings",
]


def storage(
    rows: list[tuple[str, str, str, str, str]],
    *,
    period: tuple[str, str] | None = None,
    total: str | None = None,
) -> bytes:
    """rows = (gtin, sku, final, original, discount)；period 给了就带卖家后台的汇总块。"""
    out: list[list[str]] = []
    if period:
        out += [
            ["STORE"],
            ["Report start date", "Report end date", "Total storage fees"],
            [period[0], period[1], total or ""],
        ]
    out.append(STORAGE_HEAD)
    for gtin, sku, final, orig, disc in rows:
        out.append(
            [
                gtin,
                sku,
                "",
                "合成商品",
                "1",
                "1",
                "1",
                "1",
                "0.001",
                "0.001",
                "0.003",
                "0.01",
                "10",
                "0",
                "0",
                "0",
                "14",
                final,
                orig,
                disc,
            ]
        )
    return _csv(out)


INBOUND_HEAD = [
    "Shipment ID",
    "Delivery Date",
    "Service Type",
    "Reason Code",
    "Actual Charge",
    "Quote Amount",
    "Quote Weight",
    "Quote Case or Pallet Count",
    "Quote Freight Class",
    "Actual Weight",
    "Actual Billable Weight",
    "Actual Case or Pallet Count",
    "Actual Freight Class",
    "Ship From City",
    "Ship From State",
    "Ship To City",
    "Ship To State",
    "Comments",
]


def inbound(rows: list[tuple[str, str, str, str, str]], period: tuple[str, str]) -> bytes:
    """rows = (cargo, delivery_date, service, reason, charge)。"""
    out: list[list[str]] = [
        ["synthetic-store"],
        ["ReportingPeriod_StartDate", "ReportingPeriod_EndDate"],
        list(period),
        INBOUND_HEAD,
    ]
    for cargo, day, service, reason, charge in rows:
        out.append([f'="{cargo}"', day, service, reason, charge] + [""] * 13)
    return _csv(out)
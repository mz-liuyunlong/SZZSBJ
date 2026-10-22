"""Purchase order terms -> published MART evidence; no RAW/ODS access in business GETs."""

from __future__ import annotations

from sqlalchemy import select

from app.modules.pmc_domestic.packing_customs_rules import customs_proof
from app.modules.pmc_purchase.gate3_models import DwdPurchaseOrder
from app.modules.pmc_purchase.models import LingxingPurchaseOrderOds


def enrich_customs(session, account, rows):
    order_sns = {
        sn
        for row in rows
        for sn in row.get("purchase_order_sns") or []
        if isinstance(sn, str) and sn.strip()
    }
    headers: dict[str, dict] = {}
    if order_sns:
        for order_row, ods in session.execute(
            select(DwdPurchaseOrder, LingxingPurchaseOrderOds)
            .join(
                LingxingPurchaseOrderOds,
                LingxingPurchaseOrderOds.id == DwdPurchaseOrder.source_ods_id,
            )
            .where(
                DwdPurchaseOrder.source_account_ref == account,
                DwdPurchaseOrder.order_sn.in_(order_sns),
                LingxingPurchaseOrderOds.source_account_ref == account,
                LingxingPurchaseOrderOds.run_id == DwdPurchaseOrder.source_run_id,
            )
        ):
            payload = ods.payload_json if isinstance(ods.payload_json, dict) else {}
            headers[order_row.order_sn] = {
                "order_sn": order_row.order_sn,
                "payment_method": payload.get("payment_method"),
                "payment": payload.get("payment"),
                "is_tax": payload.get("is_tax"),
                "ref": str(ods.id),
                "observed_at": order_row.source_observed_at.isoformat(),
            }
    for row in rows:
        sns = row.get("purchase_order_sns") or []
        orders = [headers[sn] for sn in sns if sn in headers]
        row["customs_proof"] = customs_proof(orders=orders)

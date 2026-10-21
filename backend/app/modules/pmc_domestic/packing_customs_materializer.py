"""Offline remarks -> published MART evidence; no RAW/ODS access in business GETs."""

from collections import defaultdict

from app.modules.integration_sync.models import ApiRawBlob, ApiRawRequestRef
from app.modules.pmc_domestic.packing_customs_rules import customs_proof
from app.modules.pmc_purchase.gate3_models import (
    DwdPurchaseOrderLineItem,
    DwdPurchasePlan,
)
from app.modules.pmc_purchase.models import (
    LingxingPurchaseOrderItemOds,
    LingxingPurchasePlanOds,
)
from app.modules.sku_detail.models import (
    LingxingSkuProductInfoCurrent,
    LingxingSkuProductInfoSnapshot,
)
from sqlalchemy import select


def enrich_customs(session, account, rows):
    skus = {r["sku"] for r in rows}
    if not skus:
        return
    products = {}
    records = session.execute(
        select(
            LingxingSkuProductInfoCurrent,
            LingxingSkuProductInfoSnapshot,
            ApiRawRequestRef,
            ApiRawBlob,
        )
        .join(
            LingxingSkuProductInfoSnapshot,
            LingxingSkuProductInfoSnapshot.id
            == LingxingSkuProductInfoCurrent.source_snapshot_id,
        )
        .join(
            ApiRawRequestRef,
            ApiRawRequestRef.id
            == LingxingSkuProductInfoSnapshot.source_raw_request_ref_id,
        )
        .join(ApiRawBlob, ApiRawBlob.id == ApiRawRequestRef.raw_blob_id)
        .where(
            LingxingSkuProductInfoCurrent.source_account_ref == account,
            LingxingSkuProductInfoCurrent.lingxing_sku_code.in_(skus),
            LingxingSkuProductInfoSnapshot.source_account_ref == account,
            ApiRawRequestRef.is_success.is_(True),
            ApiRawBlob.storage_mode == "database",
        )
    )
    for current, snapshot, ref, blob in records:
        envelope = blob.payload_json
        data = envelope.get("data") if isinstance(envelope, dict) else None
        items = (
            data if isinstance(data, list) else [data] if isinstance(data, dict) else []
        )
        matches = [
            v
            for v in items
            if isinstance(v, dict) and str(v.get("id")) == current.lingxing_sku_id
        ]
        if len(matches) != 1 or "purchase_remark" not in matches[0]:
            continue
        item = matches[0]
        products.setdefault(current.lingxing_sku_code, []).append(
            {
                "remark": item.get("purchase_remark")
                if isinstance(item.get("purchase_remark"), str)
                else "",
                "ref": str(ref.id),
                "field": "product.purchase_remark",
                "observed_at": current.source_observed_at.isoformat(),
            }
        )
    # Ambiguous SKU identities are not guessed; purchases remain the fallback.
    products = {sku: values[0] for sku, values in products.items() if len(values) == 1}
    purchases = defaultdict(list)
    for dwd, ods, kind in (
        (DwdPurchasePlan, LingxingPurchasePlanOds, "purchase_plan"),
        (DwdPurchaseOrderLineItem, LingxingPurchaseOrderItemOds, "purchase_order_item"),
    ):
        seen = set()
        for row, source in session.execute(
            select(dwd, ods)
            .join(ods, ods.id == dwd.source_ods_id)
            .where(
                dwd.source_account_ref == account,
                dwd.sku.in_(skus),
                ods.source_account_ref == account,
                ods.run_id == dwd.source_run_id,
            )
        ):
            if source.id in seen:
                continue
            seen.add(source.id)
            payload = source.payload_json
            parts = [
                payload.get(k)
                for k in ("item_purchase_remark", "remark", "plan_remark")
            ]
            remark = " ".join(v for v in parts if isinstance(v, str) and v.strip())
            if remark:
                purchases[row.sku].append(
                    {
                        "remark": remark,
                        "ref": str(source.id),
                        "field": kind + ".item_purchase_remark/remark/plan_remark",
                        "time": row.provider_update_time
                        or row.source_observed_at.isoformat(),
                        "observed_at": row.source_observed_at.isoformat(),
                    }
                )
    for row in rows:
        row["customs_proof"] = customs_proof(
            products.get(row["sku"]), purchases[row["sku"]]
        )

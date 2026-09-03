import json, re, sys

path = sys.argv[1]
with open(path, encoding='utf-8', errors='ignore') as f:
    content = f.read()

# 按 "--- 第N条 ---" 切分，每块后面紧跟一个JSON对象
blocks = re.split(r'--- 第\d+条 ---\n', content)
records = []
for b in blocks[1:]:
    # 从这块文本里提取第一个完整的顶层JSON对象（从第一个{到匹配的最后一个}）
    start = b.find('{')
    if start == -1:
        continue
    depth = 0
    end = None
    for i in range(start, len(b)):
        if b[i] == '{':
            depth += 1
        elif b[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        continue
    try:
        obj = json.loads(b[start:end])
        records.append(obj)
    except json.JSONDecodeError as e:
        print(f"解析失败: {e}", file=sys.stderr)

print(f"成功解析 {len(records)} 条记录\n")

target_fields = [
    "salesAmount", "productCommission", "shippingCommission",
    "wfsWarehousFee", "wfsShipmentFee", "wfsReturnFee",
    "wfsLostInventoryFee", "wfsFoundInventoryFee", "wfsDamageInWarehouseFee",
    "wfsInventoryTransferFee", "wfsInventoryRTVFee", "wfsChargeFee",
    "wfsAdjustmentCostAmount", "wfsReceivingErrorChargeBackFee",
    "platformAdvertisingFee", "semMarketingFee", "advertisementAmount",
    "walmartPromoCode", "walmartSavingsBenefit", "walmartExtraDiscount",
    "walmartProductAdvertisingCreditsFee", "walmartReturnServiceFee",
    "commentAcceleratorFee", "purchaseAmount", "transportationAmount",
    "otherAmount", "tailAmount", "refundAmount", "taxAmount", "marketTaxAmount",
    "promotionAmount", "platformLogisticsAmount", "platformStorageAmount",
    "promotionDiscountAmount", "platformWfsStorageAmount", "platformWfsRemoveAmount",
    "wfsPrepServiceFee", "grossProfit",
]

sums = {k: 0.0 for k in target_fields}
counts = {k: 0 for k in target_fields}
for r in records:
    for k in target_fields:
        v = r.get(k)
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        sums[k] += fv
        if fv != 0:
            counts[k] += 1

print(f"{'字段名':40s} {'求和(CNY)':>15s} {'非零笔数':>8s}")
for k in target_fields:
    print(f"{k:40s} {sums[k]:15.2f} {counts[k]:8d}")

salesNum_total = sum(float(r.get('salesNum', 0) or 0) for r in records)
print(f"\nsalesNum总计: {salesNum_total}")

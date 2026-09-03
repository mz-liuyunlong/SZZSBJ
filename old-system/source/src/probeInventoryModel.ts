import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

type AnyRecord = Record<string, unknown>;

type ApiWrap = {
  status?: number;
  data?: {
    code?: number | string;
    message?: string;
    msg?: string;
    data?: unknown;
  };
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function unwrapList(resp: ApiWrap): unknown[] {
  const payload = resp?.data?.data ?? resp?.data;
  if (Array.isArray(payload)) return payload;
  if (payload && typeof payload === "object") {
    const p = payload as Record<string, unknown>;
    const list = p.list ?? p.data;
    if (Array.isArray(list)) return list;
  }
  return [];
}

function asRecord(value: unknown): AnyRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as AnyRecord) : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function pickQuantityFields(rec: AnyRecord): AnyRecord {
  const out: AnyRecord = {};
  for (const key of Object.keys(rec)) {
    if (key.startsWith("quantity_")) out[key] = rec[key];
  }
  return out;
}

function print(title: string, data?: unknown): void {
  console.log(`\n=== ${title} ===`);
  if (data !== undefined) {
    console.log(typeof data === "string" ? data : JSON.stringify(data, null, 2));
  }
}

async function main(): Promise<void> {
  const client = new LingxingClient(loadConfig());

  print("probeInventoryModel start", { at: new Date().toISOString() });
  console.log("NO_SQL=true");
  console.log("NO_DB_CONNECTION=true");

  const purchasePath = "/erp/sc/routing/data/local_inventory/purchaseOrderList";
  const purchasePages: AnyRecord[][] = [];
  const purchaseAll: AnyRecord[] = [];
  const statusStats = new Map<string, { count: number; text: string }>();

  for (const offset of [0, 100, 200]) {
    const params = { offset, length: 100 };
    print(`purchaseOrderList request offset=${offset}`, params);
    const resp = (await client.post(purchasePath, params)) as ApiWrap;
    print(`purchaseOrderList response meta offset=${offset}`, {
      status: resp?.status,
      code: resp?.data?.code,
      message: resp?.data?.message ?? resp?.data?.msg ?? "",
    });
    const list = unwrapList(resp).map(asRecord);
    print(`purchaseOrderList list count offset=${offset}`, { count: list.length });
    purchasePages.push(list);
    purchaseAll.push(...list);
    for (const rec of list) {
      const status = String(rec.status ?? "");
      const statusText = String(rec.status_text ?? rec.statusName ?? rec.status_name ?? "");
      const hit = statusStats.get(status) ?? { count: 0, text: statusText };
      hit.count += 1;
      if (!hit.text && statusText) hit.text = statusText;
      statusStats.set(status, hit);
    }
    await sleep(200);
  }

  const firstPurchase = purchaseAll[0] ?? {};
  const firstPurchaseItem = asRecord(asArray(firstPurchase.item_list)[0]);
  print("purchaseOrderList first record keys", Object.keys(firstPurchase));
  print("purchaseOrderList first record item_list first keys", Object.keys(firstPurchaseItem));

  const statusDist: AnyRecord = {};
  for (const [status, v] of statusStats.entries()) {
    statusDist[status] = { count: v.count, status_text: v.text };
  }
  print("purchaseOrderList status distribution", statusDist);

  const sampledOrders = purchaseAll.filter((rec) => ["1", "2", "9"].includes(String(rec.status ?? ""))).slice(0, 8);
  const sampledPayload = sampledOrders.map((rec) => ({
    order_sn: rec.order_sn,
    status: rec.status,
    status_text: rec.status_text,
    ware_house_name: rec.ware_house_name,
    order_time: rec.order_time,
    item_list: asArray(rec.item_list).map((row) => {
      const r = asRecord(row);
      return {
        sku: r.sku,
        msku: r.msku,
        ...pickQuantityFields(r),
      };
    }),
  }));
  print("purchaseOrderList sampled status in {1,2,9}", sampledPayload);

  const inventoryPath = "/erp/sc/routing/data/local_inventory/inventoryDetails";
  const inventoryParams = { offset: 0, length: 200 };
  print("inventoryDetails request", inventoryParams);
  const invResp = (await client.post(inventoryPath, inventoryParams)) as ApiWrap;
  print("inventoryDetails response meta", {
    status: invResp?.status,
    code: invResp?.data?.code,
    message: invResp?.data?.message ?? invResp?.data?.msg ?? "",
  });
  const inventoryList = unwrapList(invResp).map(asRecord);
  print("inventoryDetails first record keys", Object.keys(inventoryList[0] ?? {}));

  const widStats: Record<string, number> = {};
  for (const rec of inventoryList) {
    const wid = String(rec.wid ?? "");
    widStats[wid] = (widStats[wid] ?? 0) + 1;
  }
  print("inventoryDetails sample count + wid stats", {
    total: inventoryList.length,
    by_wid: widStats,
  });

  const first15 = inventoryList.slice(0, 15).map((rec) => ({
    wid: rec.wid,
    sku: rec.sku,
    msku: rec.msku,
    seller_id: rec.seller_id,
    fnsku: rec.fnsku,
    product_total: rec.product_total,
    product_valid_num: rec.product_valid_num,
    expect_valid_num: rec.expect_valid_num,
    quantity_receive: rec.quantity_receive,
    expect_pending_num: rec.expect_pending_num,
    product_onway: rec.product_onway,
    product_lock_num: rec.product_lock_num,
  }));
  print("inventoryDetails first 15 rows", first15);

  const invSummary = {
    product_valid_num_gt_0: inventoryList.filter((rec) => Number(rec.product_valid_num ?? 0) > 0).length,
    quantity_receive_gt_0: inventoryList.filter((rec) => Number(rec.quantity_receive ?? 0) > 0).length,
    product_onway_gt_0: inventoryList.filter((rec) => Number(rec.product_onway ?? 0) > 0).length,
  };
  print("inventoryDetails positive-count summary", invSummary);

  const receiveHit = inventoryList.find((rec) => Number(rec.quantity_receive ?? 0) > 0);
  if (!receiveHit) {
    print("cross check", "inventoryDetails sample has no quantity_receive>0 row");
    return;
  }

  const hitSku = String(receiveHit.sku ?? "");
  const hitMsku = String(receiveHit.msku ?? "");
  const matchedOrders: AnyRecord[] = [];
  for (const order of purchaseAll) {
    for (const item of asArray(order.item_list)) {
      const row = asRecord(item);
      if ((hitSku && String(row.sku ?? "") === hitSku) || (hitMsku && String(row.msku ?? "") === hitMsku)) {
        matchedOrders.push({
          order_sn: order.order_sn,
          status: order.status,
          status_text: order.status_text,
          ware_house_name: order.ware_house_name,
          order_time: order.order_time,
          sku: row.sku,
          msku: row.msku,
          quantity_fields: pickQuantityFields(row),
        });
      }
    }
  }

  print("cross check inventory row", {
    sku: receiveHit.sku,
    msku: receiveHit.msku,
    wid: receiveHit.wid,
    seller_id: receiveHit.seller_id,
    product_total: receiveHit.product_total,
    product_valid_num: receiveHit.product_valid_num,
    expect_valid_num: receiveHit.expect_valid_num,
    quantity_receive: receiveHit.quantity_receive,
    expect_pending_num: receiveHit.expect_pending_num,
    product_onway: receiveHit.product_onway,
    product_lock_num: receiveHit.product_lock_num,
  });
  print("cross check matched purchase items", matchedOrders.slice(0, 20));
}

main().catch((err) => {
  console.error("probeInventoryModel failed");
  console.error(err instanceof Error ? err.stack ?? err.message : String(err));
  process.exit(1);
});

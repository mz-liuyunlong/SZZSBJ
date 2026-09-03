import "dotenv/config";
import * as mysql from "mysql2/promise";

function dbConfig() {
  return {
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
    dateStrings: true,
  };
}

type Row = mysql.RowDataPacket & Record<string, unknown>;

function print(title: string, data?: unknown) {
  console.log(`\n=== ${title} ===`);
  if (data !== undefined) {
    console.log(typeof data === "string" ? data : JSON.stringify(data, null, 2));
  }
}

function n(v: unknown): number {
  const x = Number(v ?? 0);
  return Number.isFinite(x) ? x : 0;
}

function round4(v: number): number {
  return Math.round(v * 10000) / 10000;
}

async function main() {
  console.log("=== probeInventoryOverview start ===");
  console.log(JSON.stringify({ at: new Date().toISOString(), read_only: true, sql_only: "SELECT" }, null, 2));

  const db = await mysql.createConnection(dbConfig());
  try {
    const [[localSnap]] = await db.query<Row[]>(
      `SELECT MAX(snapshot_date) AS latest_snap FROM fact_local_inventory_daily`,
    );
    const localDate = String(localSnap.latest_snap ?? "");

    const [[localAgg]] = await db.query<Row[]>(
      `SELECT snapshot_date,
              COUNT(*) AS total_rows,
              SUM(CASE WHEN qty > 0 THEN 1 ELSE 0 END) AS qty_pos_rows,
              SUM(qty) AS qty_sum
         FROM fact_local_inventory_daily
        WHERE snapshot_date = ?
        GROUP BY snapshot_date`,
      [localDate],
    );
    const [localSample] = await db.query<Row[]>(
      `SELECT sku, qty
         FROM fact_local_inventory_daily
        WHERE snapshot_date = ?
        ORDER BY qty DESC, sku ASC
        LIMIT 8`,
      [localDate],
    );
    print("1) fact_local_inventory_daily latest snapshot", {
      latest_snap: localDate,
      total_rows: n(localAgg?.total_rows),
      qty_pos_rows: n(localAgg?.qty_pos_rows),
      qty_sum: n(localAgg?.qty_sum),
      sample_8: localSample,
    });

    const [[invSnap]] = await db.query<Row[]>(
      `SELECT MAX(snapshot_date) AS latest_snap FROM fact_inventory_daily WHERE platform='walmart'`,
    );
    const invDate = String(invSnap.latest_snap ?? "");

    const [[invAgg]] = await db.query<Row[]>(
      `SELECT snapshot_date,
              COUNT(*) AS total_rows,
              SUM(CASE WHEN COALESCE(wfs_available_stock,0) > 0 THEN 1 ELSE 0 END) AS wfs_pos_rows,
              SUM(CASE WHEN COALESCE(non_wfs_available_stock,0) > 0 THEN 1 ELSE 0 END) AS nonwfs_pos_rows
         FROM fact_inventory_daily
        WHERE platform='walmart' AND snapshot_date = ?
        GROUP BY snapshot_date`,
      [invDate],
    );
    const [invSample] = await db.query<Row[]>(
      `SELECT store_name, item_id, msku, sku, wfs_available_stock, non_wfs_available_stock
         FROM fact_inventory_daily
        WHERE platform='walmart' AND snapshot_date = ?
        ORDER BY COALESCE(wfs_available_stock,0) DESC, COALESCE(non_wfs_available_stock,0) DESC, item_id ASC
        LIMIT 8`,
      [invDate],
    );
    print("2) fact_inventory_daily latest snapshot", {
      latest_snap: invDate,
      total_rows: n(invAgg?.total_rows),
      wfs_pos_rows: n(invAgg?.wfs_pos_rows),
      nonwfs_pos_rows: n(invAgg?.nonwfs_pos_rows),
      sample_8: invSample,
    });

    const [[costAgg]] = await db.query<Row[]>(
      `SELECT COUNT(*) AS total_rows,
              SUM(CASE WHEN purchase_cost IS NOT NULL THEN 1 ELSE 0 END) AS purchase_not_null,
              SUM(CASE WHEN first_mile_shipping_cost IS NOT NULL THEN 1 ELSE 0 END) AS first_mile_not_null,
              SUM(CASE WHEN purchase_cost IS NOT NULL AND first_mile_shipping_cost IS NOT NULL THEN 1 ELSE 0 END) AS both_not_null
         FROM (
           SELECT c.*
             FROM dim_product_cost_config c
             JOIN (
               SELECT platform, store_id, item_id, msku, MAX(effective_date) AS mx
                 FROM dim_product_cost_config
                WHERE platform='walmart'
                GROUP BY platform, store_id, item_id, msku
             ) t
               ON t.platform = c.platform
              AND t.store_id = c.store_id
              AND t.item_id = c.item_id
              AND t.msku = c.msku
              AND t.mx = c.effective_date
            WHERE c.platform='walmart'
         ) z`,
    );
    const [costSample] = await db.query<Row[]>(
      `SELECT c.item_id, c.msku, c.store_name, c.purchase_cost, c.first_mile_shipping_cost, c.effective_date
         FROM dim_product_cost_config c
         JOIN (
           SELECT platform, store_id, item_id, msku, MAX(effective_date) AS mx
             FROM dim_product_cost_config
            WHERE platform='walmart'
            GROUP BY platform, store_id, item_id, msku
         ) t
           ON t.platform = c.platform
          AND t.store_id = c.store_id
          AND t.item_id = c.item_id
          AND t.msku = c.msku
          AND t.mx = c.effective_date
        WHERE c.platform='walmart'
        ORDER BY effective_date DESC, item_id ASC
        LIMIT 8`,
    );
    const costTotal = n(costAgg?.total_rows);
    print("3) dim_product_cost_config latest effective rows", {
      total_rows: costTotal,
      purchase_cost_not_null: n(costAgg?.purchase_not_null),
      purchase_cost_ratio: costTotal ? round4(n(costAgg?.purchase_not_null) / costTotal) : 0,
      first_mile_not_null: n(costAgg?.first_mile_not_null),
      first_mile_ratio: costTotal ? round4(n(costAgg?.first_mile_not_null) / costTotal) : 0,
      both_not_null: n(costAgg?.both_not_null),
      sample_8: costSample,
    });

    const [bridgeSummary] = await db.query<Row[]>(
      `WITH local_pos AS (
         SELECT sku, SUM(qty) AS qty
           FROM fact_local_inventory_daily
          WHERE snapshot_date = ? AND qty > 0
          GROUP BY sku
       ), bridge AS (
         SELECT l.sku, l.qty, COUNT(DISTINCT d.item_id) AS item_cnt
           FROM local_pos l
           LEFT JOIN dim_product d
             ON d.platform='walmart' AND d.sku = l.sku
          GROUP BY l.sku, l.qty
       )
       SELECT COUNT(*) AS total_sku,
              SUM(CASE WHEN item_cnt > 0 THEN 1 ELSE 0 END) AS matched_sku,
              SUM(CASE WHEN item_cnt = 0 THEN 1 ELSE 0 END) AS unmatched_sku,
              MAX(item_cnt) AS max_item_cnt
         FROM bridge`,
      [localDate],
    );
    const [bridgeDist] = await db.query<Row[]>(
      `WITH local_pos AS (
         SELECT sku, SUM(qty) AS qty
           FROM fact_local_inventory_daily
          WHERE snapshot_date = ? AND qty > 0
          GROUP BY sku
       ), bridge AS (
         SELECT l.sku, COUNT(DISTINCT d.item_id) AS item_cnt
           FROM local_pos l
           LEFT JOIN dim_product d
             ON d.platform='walmart' AND d.sku = l.sku
          GROUP BY l.sku
       )
       SELECT item_cnt, COUNT(*) AS sku_cnt
         FROM bridge
        GROUP BY item_cnt
        ORDER BY item_cnt`,
      [localDate],
    );
    const [bridgeMiss] = await db.query<Row[]>(
      `WITH local_pos AS (
         SELECT sku, SUM(qty) AS qty
           FROM fact_local_inventory_daily
          WHERE snapshot_date = ? AND qty > 0
          GROUP BY sku
       ), bridge AS (
         SELECT l.sku, l.qty, COUNT(DISTINCT d.item_id) AS item_cnt
           FROM local_pos l
           LEFT JOIN dim_product d
             ON d.platform='walmart' AND d.sku = l.sku
          GROUP BY l.sku, l.qty
       )
       SELECT sku, qty
         FROM bridge
        WHERE item_cnt = 0
        ORDER BY qty DESC, sku ASC
        LIMIT 10`,
      [localDate],
    );
    const totalSku = n(bridgeSummary[0]?.total_sku);
    const matchedSku = n(bridgeSummary[0]?.matched_sku);
    const unmatchedSku = n(bridgeSummary[0]?.unmatched_sku);
    print("4) SKU↔ITEMID bridge hit-rate", {
      latest_local_snapshot: localDate,
      total_sku: totalSku,
      matched_sku: matchedSku,
      unmatched_sku: unmatchedSku,
      matched_ratio: totalSku ? round4(matchedSku / totalSku) : 0,
      unmatched_ratio: totalSku ? round4(unmatchedSku / totalSku) : 0,
      item_count_distribution: bridgeDist,
      max_item_cnt: n(bridgeSummary[0]?.max_item_cnt),
      unmatched_top10: bridgeMiss,
    });

    const [pickedItems] = await db.query<Row[]>(
      `WITH local_pos AS (
         SELECT sku, SUM(qty) AS local_qty
           FROM fact_local_inventory_daily
          WHERE snapshot_date = ? AND qty > 0
          GROUP BY sku
       ), wfs_pos AS (
         SELECT platform, store_id, store_name, item_id, msku, sku, wfs_available_stock, non_wfs_available_stock
           FROM fact_inventory_daily
          WHERE platform='walmart' AND snapshot_date = ? AND COALESCE(wfs_available_stock,0) > 0
       ), candidate AS (
         SELECT w.item_id, dp.sku, MAX(lp.local_qty) AS local_qty, SUM(w.wfs_available_stock) AS wfs_sum
           FROM wfs_pos w
           JOIN dim_product dp
             ON dp.platform='walmart' AND dp.store_id=w.store_id AND dp.item_id=w.item_id AND dp.msku=w.msku
           JOIN local_pos lp
             ON lp.sku = dp.sku
          GROUP BY w.item_id, dp.sku
       )
       SELECT item_id, sku, local_qty, wfs_sum
         FROM candidate
        ORDER BY wfs_sum DESC, local_qty DESC, item_id ASC
        LIMIT 5`,
      [localDate, invDate],
    );

    print("5) end-to-end picked item count", { picked: pickedItems.length });

    for (const picked of pickedItems) {
      const itemId = String(picked.item_id ?? "");
      const localSku = String(picked.sku ?? "");
      const localQty = n(picked.local_qty);

      const [groupCostRows] = await db.query<Row[]>(
        `SELECT c.purchase_cost, c.first_mile_shipping_cost, c.effective_date, c.store_name, c.msku
           FROM dim_product_cost_config c
           JOIN (
             SELECT platform, store_id, item_id, msku, MAX(effective_date) AS mx
               FROM dim_product_cost_config
              WHERE platform='walmart' AND item_id = ?
              GROUP BY platform, store_id, item_id, msku
           ) t
             ON t.platform = c.platform
            AND t.store_id = c.store_id
            AND t.item_id = c.item_id
            AND t.msku = c.msku
            AND t.mx = c.effective_date
          WHERE c.platform='walmart' AND c.item_id = ?
          ORDER BY c.effective_date DESC, c.store_name ASC, c.msku ASC`,
        [itemId, itemId],
      );

      const groupPurchaseCost = groupCostRows.length ? n(groupCostRows[0].purchase_cost) : 0;
      const groupFirstMile = groupCostRows.length ? n(groupCostRows[0].first_mile_shipping_cost) : 0;
      const localWarehouseValue = localQty * groupPurchaseCost;

      const [subRows] = await db.query<Row[]>(
        `SELECT inv.store_id, inv.store_name, inv.item_id, inv.msku, dp.sku,
                inv.wfs_available_stock, inv.non_wfs_available_stock,
                cost.purchase_cost, cost.first_mile_shipping_cost, cost.effective_date
           FROM fact_inventory_daily inv
           LEFT JOIN dim_product dp
             ON dp.platform='walmart' AND dp.store_id=inv.store_id AND dp.item_id=inv.item_id AND dp.msku=inv.msku
           LEFT JOIN (
             SELECT c.platform, c.store_id, c.item_id, c.msku, c.purchase_cost, c.first_mile_shipping_cost, c.effective_date
               FROM dim_product_cost_config c
               JOIN (
                 SELECT platform, store_id, item_id, msku, MAX(effective_date) AS mx
                   FROM dim_product_cost_config
                  WHERE platform='walmart'
                  GROUP BY platform, store_id, item_id, msku
               ) t
                 ON t.platform = c.platform
                AND t.store_id = c.store_id
                AND t.item_id = c.item_id
                AND t.msku = c.msku
                AND t.mx = c.effective_date
              WHERE c.platform='walmart'
           ) cost
             ON cost.platform='walmart' AND cost.store_id=inv.store_id AND cost.item_id=inv.item_id AND cost.msku=inv.msku
          WHERE inv.platform='walmart' AND inv.snapshot_date=? AND inv.item_id=?
          ORDER BY inv.store_name ASC, inv.msku ASC`,
        [invDate, itemId],
      );

      let sumWfs = 0;
      let sumNonwfs = 0;
      let wfsValue = 0;
      let zeroValueNullCostRows = 0;
      const subPayload = subRows.map((r) => {
        const pc = r.purchase_cost == null ? null : n(r.purchase_cost);
        const fm = r.first_mile_shipping_cost == null ? null : n(r.first_mile_shipping_cost);
        const wfs = n(r.wfs_available_stock);
        const nonwfs = n(r.non_wfs_available_stock);
        sumWfs += wfs;
        sumNonwfs += nonwfs;
        const value = wfs * ((pc ?? 0) + (fm ?? 0));
        if (wfs > 0 && (pc == null || fm == null)) zeroValueNullCostRows += 1;
        wfsValue += value;
        return {
          store_name: r.store_name,
          store_id: r.store_id,
          item_id: r.item_id,
          msku: r.msku,
          sku: r.sku,
          wfs_available_stock: wfs,
          non_wfs_available_stock: nonwfs,
          purchase_cost: pc,
          first_mile_shipping_cost: fm,
          effective_date: r.effective_date,
          wfs_value_by_rule: round4(value),
        };
      });

      const inventoryQty = localQty + sumWfs;
      const totalValue = localWarehouseValue + wfsValue;
      const weightedUnitCost = inventoryQty > 0 ? totalValue / inventoryQty : 0;

      print(`5) item ${itemId}`, {
        header: {
          item_id: itemId,
          local_sku: localSku,
          local_qty: localQty,
          purchase_cost: groupPurchaseCost,
          first_mile_shipping_cost: groupFirstMile,
          purchased_qty_current_probe: 0,
          inbound_qty_current_probe: 0,
          local_warehouse_value: round4(localWarehouseValue),
        },
        sub_rows: subPayload,
        calc: {
          local_qty: localQty,
          sum_wfs: sumWfs,
          sum_nonwfs: sumNonwfs,
          local_warehouse_value: round4(localWarehouseValue),
          wfs_inventory_value: round4(wfsValue),
          inventory_qty_rule_now: inventoryQty,
          inventory_total_value: round4(totalValue),
          weighted_unit_cost: round4(weightedUnitCost),
          note_nonwfs_not_in_value: true,
          null_cost_rows_zeroed_in_wfs_value: zeroValueNullCostRows,
        },
      });
    }

    const [factCols] = await db.query<Row[]>(
      `SELECT table_name, column_name
         FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name LIKE 'fact\_%'
          AND column_name IN ('quantity_receive', 'product_onway', 'inbound_stock')
        ORDER BY table_name, column_name`,
    );

    const [nullCostImpact] = await db.query<Row[]>(
      `WITH picked AS (
         SELECT item_id
           FROM (
             WITH local_pos AS (
               SELECT sku, SUM(qty) AS local_qty
                 FROM fact_local_inventory_daily
                WHERE snapshot_date = ? AND qty > 0
                GROUP BY sku
             ), wfs_pos AS (
               SELECT platform, store_id, store_name, item_id, msku, sku, wfs_available_stock
                 FROM fact_inventory_daily
                WHERE platform='walmart' AND snapshot_date = ? AND COALESCE(wfs_available_stock,0) > 0
             ), candidate AS (
               SELECT w.item_id, dp.sku, MAX(lp.local_qty) AS local_qty, SUM(w.wfs_available_stock) AS wfs_sum
                 FROM wfs_pos w
                 JOIN dim_product dp
                   ON dp.platform='walmart' AND dp.store_id=w.store_id AND dp.item_id=w.item_id AND dp.msku=w.msku
                 JOIN local_pos lp
                   ON lp.sku = dp.sku
                GROUP BY w.item_id, dp.sku
             )
             SELECT item_id
               FROM candidate
              ORDER BY wfs_sum DESC, local_qty DESC, item_id ASC
              LIMIT 5
           ) x
       )
       SELECT COUNT(*) AS wfs_rows_in_5_items,
              SUM(CASE WHEN COALESCE(inv.wfs_available_stock,0) > 0 AND (cost.purchase_cost IS NULL OR cost.first_mile_shipping_cost IS NULL) THEN 1 ELSE 0 END) AS null_cost_wfs_rows
         FROM fact_inventory_daily inv
         LEFT JOIN (
           SELECT c.platform, c.store_id, c.item_id, c.msku, c.purchase_cost, c.first_mile_shipping_cost
             FROM dim_product_cost_config c
             JOIN (
               SELECT platform, store_id, item_id, msku, MAX(effective_date) AS mx
                 FROM dim_product_cost_config
                WHERE platform='walmart'
                GROUP BY platform, store_id, item_id, msku
             ) t
               ON t.platform = c.platform
              AND t.store_id = c.store_id
              AND t.item_id = c.item_id
              AND t.msku = c.msku
              AND t.mx = c.effective_date
            WHERE c.platform='walmart'
         ) cost
           ON cost.platform='walmart' AND cost.store_id=inv.store_id AND cost.item_id=inv.item_id AND cost.msku=inv.msku
        WHERE inv.platform='walmart' AND inv.snapshot_date=? AND inv.item_id IN (SELECT item_id FROM picked)`,
      [localDate, invDate, invDate],
    );

    print("6) gap notes", {
      purchased_quantity_receive_in_fact_tables: factCols.filter((r) => String(r.column_name) === "quantity_receive"),
      inbound_related_columns_in_fact_tables: factCols.filter((r) => String(r.column_name) !== "quantity_receive"),
      note_purchased_qty_in_inventory_overview_probe: "当前探测未发现承接采购单 quantity_receive 的独立 FACT 汇总列；本次组头按 0 打印已采购/在途。",
      note_null_cost_rule: "本探测按 NULL -> 0 计货值，不报错。",
      null_cost_zeroed_rows_in_5_items: n(nullCostImpact[0]?.null_cost_wfs_rows),
      wfs_rows_in_5_items: n(nullCostImpact[0]?.wfs_rows_in_5_items),
    });
  } finally {
    await db.end();
  }
}

main().catch((err) => {
  console.error("probeInventoryOverview failed");
  console.error(err instanceof Error ? err.stack ?? err.message : String(err));
  process.exit(1);
});

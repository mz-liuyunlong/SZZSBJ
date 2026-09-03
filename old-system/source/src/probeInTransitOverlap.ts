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

async function main() {
  console.log("=== probeInTransitOverlap start ===");
  console.log(JSON.stringify({ at: new Date().toISOString(), read_only: true, sql_only: "SELECT" }, null, 2));

  const db = await mysql.createConnection(dbConfig());
  try {
    const [[shipAgg]] = await db.query<Row[]>(
      `SELECT COUNT(*) AS total_rows,
              COUNT(DISTINCT shipment_id) AS distinct_shipment_id,
              DATE_FORMAT(MAX(system_update_date), '%Y-%m-%d %H:%i:%s') AS max_system_update_date,
              DATE_FORMAT(MIN(cargo_create_date), '%Y-%m-%d %H:%i:%s') AS min_cargo_create_date,
              DATE_FORMAT(MAX(cargo_create_date), '%Y-%m-%d %H:%i:%s') AS max_cargo_create_date,
              SUM(CASE WHEN to_closed_time IS NULL AND to_cancelled_time IS NULL THEN 1 ELSE 0 END) AS unfinished_rows,
              SUM(CASE WHEN to_closed_time IS NOT NULL THEN 1 ELSE 0 END) AS closed_rows,
              SUM(CASE WHEN to_cancelled_time IS NOT NULL THEN 1 ELSE 0 END) AS cancelled_rows
         FROM fact_wfs_shipment
        WHERE platform='walmart'`,
    );
    const [shipStatus] = await db.query<Row[]>(
      `SELECT status, status_name, COUNT(*) AS cnt
         FROM fact_wfs_shipment
        WHERE platform='walmart'
        GROUP BY status, status_name
        ORDER BY cnt DESC, status ASC`,
    );
    print("1) fact_wfs_shipment overview", {
      total_rows: n(shipAgg?.total_rows),
      distinct_shipment_id: n(shipAgg?.distinct_shipment_id),
      max_system_update_date: shipAgg?.max_system_update_date,
      cargo_create_date_min: shipAgg?.min_cargo_create_date,
      cargo_create_date_max: shipAgg?.max_cargo_create_date,
      unfinished_rows: n(shipAgg?.unfinished_rows),
      closed_rows: n(shipAgg?.closed_rows),
      cancelled_rows: n(shipAgg?.cancelled_rows),
      status_distribution: shipStatus,
    });

    const [[itemAgg]] = await db.query<Row[]>(
      `SELECT COUNT(*) AS total_rows
         FROM fact_wfs_shipment_item
        WHERE platform='walmart'`,
    );
    const [itemSample] = await db.query<Row[]>(
      `SELECT store_id, shipment_id, msku, sku, declare_num, shipments_num, received_num, damaged_qty
         FROM fact_wfs_shipment_item
        WHERE platform='walmart'
        ORDER BY id DESC
        LIMIT 8`,
    );
    print("2) fact_wfs_shipment_item overview", {
      total_rows: n(itemAgg?.total_rows),
      sample_8: itemSample,
    });

    const [transitBridge] = await db.query<Row[]>(
      `WITH unfinished AS (
         SELECT i.store_id, i.msku,
                SUM(i.declare_num) AS declared,
                SUM(i.received_num) AS received,
                SUM(GREATEST(i.declare_num - i.received_num, 0)) AS in_transit
           FROM fact_wfs_shipment_item i
           JOIN fact_wfs_shipment s
             ON s.platform=i.platform AND s.store_id=i.store_id AND s.shipment_id=i.shipment_id
          WHERE i.platform='walmart'
            AND s.platform='walmart'
            AND s.to_closed_time IS NULL
            AND s.to_cancelled_time IS NULL
          GROUP BY i.store_id, i.msku
         HAVING SUM(GREATEST(i.declare_num - i.received_num, 0)) > 0
       )
       SELECT COUNT(*) AS transit_rows,
              SUM(in_transit) AS transit_units,
              SUM(CASE WHEN dp.item_id IS NOT NULL THEN 1 ELSE 0 END) AS mapped_rows,
              SUM(CASE WHEN dp.item_id IS NULL THEN 1 ELSE 0 END) AS unmapped_rows
         FROM unfinished u
         LEFT JOIN (
           SELECT platform, store_id, msku, MIN(item_id) AS item_id
             FROM dim_product
            WHERE platform='walmart'
            GROUP BY platform, store_id, msku
         ) dp
           ON dp.platform='walmart' AND dp.store_id=u.store_id AND dp.msku=u.msku`,
    );
    const [transitTop10] = await db.query<Row[]>(
      `WITH unfinished AS (
         SELECT i.store_id, i.msku,
                SUM(i.declare_num) AS declared,
                SUM(i.received_num) AS received,
                SUM(GREATEST(i.declare_num - i.received_num, 0)) AS in_transit
           FROM fact_wfs_shipment_item i
           JOIN fact_wfs_shipment s
             ON s.platform=i.platform AND s.store_id=i.store_id AND s.shipment_id=i.shipment_id
          WHERE i.platform='walmart'
            AND s.platform='walmart'
            AND s.to_closed_time IS NULL
            AND s.to_cancelled_time IS NULL
          GROUP BY i.store_id, i.msku
         HAVING SUM(GREATEST(i.declare_num - i.received_num, 0)) > 0
       )
       SELECT sh.store_name, dp.item_id, u.msku, u.declared, u.received, u.in_transit
         FROM unfinished u
         LEFT JOIN (
           SELECT platform, store_id, msku, MIN(item_id) AS item_id
             FROM dim_product
            WHERE platform='walmart'
            GROUP BY platform, store_id, msku
         ) dp
           ON dp.platform='walmart' AND dp.store_id=u.store_id AND dp.msku=u.msku
         LEFT JOIN (
           SELECT platform, store_id, MIN(store_name) AS store_name
             FROM fact_wfs_shipment
            WHERE platform='walmart'
            GROUP BY platform, store_id
         ) sh
           ON sh.platform='walmart' AND sh.store_id=u.store_id
        ORDER BY u.in_transit DESC, u.store_id ASC, u.msku ASC
        LIMIT 10`,
    );
    const transitRows = n(transitBridge[0]?.transit_rows);
    const mappedRows = n(transitBridge[0]?.mapped_rows);
    const unmappedRows = n(transitBridge[0]?.unmapped_rows);
    print("3) in-transit aggregate + bridge", {
      unfinished_store_msku_rows_gt_0: transitRows,
      total_in_transit_units: n(transitBridge[0]?.transit_units),
      mapped_rows: mappedRows,
      unmapped_rows: unmappedRows,
      mapped_ratio: transitRows ? mappedRows / transitRows : 0,
      unmapped_ratio: transitRows ? unmappedRows / transitRows : 0,
      top10: transitTop10,
    });

    const [classAgg] = await db.query<Row[]>(
      `SELECT SUM(CASE WHEN i.received_num = 0 THEN 1 ELSE 0 END) AS not_received_rows,
              SUM(CASE WHEN i.received_num > 0 AND i.received_num < i.declare_num THEN 1 ELSE 0 END) AS partially_received_rows,
              SUM(CASE WHEN i.received_num >= i.declare_num AND s.to_closed_time IS NULL THEN 1 ELSE 0 END) AS fully_received_but_unclosed_rows
         FROM fact_wfs_shipment_item i
         JOIN fact_wfs_shipment s
           ON s.platform=i.platform AND s.store_id=i.store_id AND s.shipment_id=i.shipment_id
        WHERE i.platform='walmart'
          AND s.platform='walmart'
          AND s.to_closed_time IS NULL
          AND s.to_cancelled_time IS NULL`,
    );
    const [redFlagRows] = await db.query<Row[]>(
      `SELECT s.store_name, i.store_id, i.shipment_id, i.msku, i.sku, i.declare_num, i.received_num,
              s.status_name, DATE_FORMAT(s.to_receive_time, '%Y-%m-%d %H:%i:%s') AS to_receive_time
         FROM fact_wfs_shipment_item i
         JOIN fact_wfs_shipment s
           ON s.platform=i.platform AND s.store_id=i.store_id AND s.shipment_id=i.shipment_id
        WHERE i.platform='walmart'
          AND s.platform='walmart'
          AND s.to_closed_time IS NULL
          AND s.to_cancelled_time IS NULL
          AND s.to_receive_time IS NOT NULL
          AND i.received_num = 0
        ORDER BY s.to_receive_time DESC, i.shipment_id ASC
        LIMIT 10`,
    );
    const [[redFlagCnt]] = await db.query<Row[]>(
      `SELECT COUNT(*) AS red_flag_rows
         FROM fact_wfs_shipment_item i
         JOIN fact_wfs_shipment s
           ON s.platform=i.platform AND s.store_id=i.store_id AND s.shipment_id=i.shipment_id
        WHERE i.platform='walmart'
          AND s.platform='walmart'
          AND s.to_closed_time IS NULL
          AND s.to_cancelled_time IS NULL
          AND s.to_receive_time IS NOT NULL
          AND i.received_num = 0`,
    );

    const [[latestInv]] = await db.query<Row[]>(
      `SELECT MAX(snapshot_date) AS latest_snap FROM fact_inventory_daily WHERE platform='walmart'`,
    );
    const latestInvDate = String(latestInv.latest_snap ?? "");

    const [[overlapCnt]] = await db.query<Row[]>(
      `WITH transit AS (
         SELECT i.store_id, i.msku,
                SUM(i.declare_num) AS declared,
                SUM(i.received_num) AS received,
                SUM(GREATEST(i.declare_num - i.received_num, 0)) AS in_transit,
                MIN(s.status_name) AS status_name,
                MAX(s.to_receive_time) AS to_receive_time
           FROM fact_wfs_shipment_item i
           JOIN fact_wfs_shipment s
             ON s.platform=i.platform AND s.store_id=i.store_id AND s.shipment_id=i.shipment_id
          WHERE i.platform='walmart'
            AND s.platform='walmart'
            AND s.to_closed_time IS NULL
            AND s.to_cancelled_time IS NULL
          GROUP BY i.store_id, i.msku
         HAVING SUM(GREATEST(i.declare_num - i.received_num, 0)) > 0
       ), inv AS (
         SELECT store_id, msku, SUM(COALESCE(wfs_available_stock,0)) AS wfs_available_stock
           FROM fact_inventory_daily
          WHERE platform='walmart' AND snapshot_date = ?
          GROUP BY store_id, msku
       )
       SELECT COUNT(*) AS overlap_rows
         FROM transit t
         LEFT JOIN inv v ON v.store_id=t.store_id AND v.msku=t.msku
        WHERE COALESCE(v.wfs_available_stock,0) > 0`,
      [latestInvDate],
    );
    const [overlapRows] = await db.query<Row[]>(
      `WITH transit AS (
         SELECT i.store_id, i.msku,
                SUM(i.declare_num) AS declared,
                SUM(i.received_num) AS received,
                SUM(GREATEST(i.declare_num - i.received_num, 0)) AS in_transit,
                MIN(s.status_name) AS status_name,
                MAX(s.to_receive_time) AS to_receive_time
           FROM fact_wfs_shipment_item i
           JOIN fact_wfs_shipment s
             ON s.platform=i.platform AND s.store_id=i.store_id AND s.shipment_id=i.shipment_id
          WHERE i.platform='walmart'
            AND s.platform='walmart'
            AND s.to_closed_time IS NULL
            AND s.to_cancelled_time IS NULL
          GROUP BY i.store_id, i.msku
         HAVING SUM(GREATEST(i.declare_num - i.received_num, 0)) > 0
       ), inv AS (
         SELECT store_id, msku, SUM(COALESCE(wfs_available_stock,0)) AS wfs_available_stock
           FROM fact_inventory_daily
          WHERE platform='walmart' AND snapshot_date = ?
          GROUP BY store_id, msku
       ), dp AS (
         SELECT platform, store_id, msku, MIN(item_id) AS item_id
           FROM dim_product
          WHERE platform='walmart'
          GROUP BY platform, store_id, msku
       ), sh AS (
         SELECT platform, store_id, MIN(store_name) AS store_name
           FROM fact_wfs_shipment
          WHERE platform='walmart'
          GROUP BY platform, store_id
       )
       SELECT sh.store_name, dp.item_id, t.msku, t.declared, t.received, t.in_transit,
              COALESCE(v.wfs_available_stock,0) AS wfs_available_stock,
              t.status_name,
              DATE_FORMAT(t.to_receive_time, '%Y-%m-%d %H:%i:%s') AS to_receive_time
         FROM transit t
         LEFT JOIN inv v ON v.store_id=t.store_id AND v.msku=t.msku
         LEFT JOIN dp ON dp.platform='walmart' AND dp.store_id=t.store_id AND dp.msku=t.msku
         LEFT JOIN sh ON sh.platform='walmart' AND sh.store_id=t.store_id
        WHERE COALESCE(v.wfs_available_stock,0) > 0
        ORDER BY t.in_transit DESC, wfs_available_stock DESC, t.store_id ASC, t.msku ASC
        LIMIT 15`,
      [latestInvDate],
    );

    const [[gapCnt]] = await db.query<Row[]>(
      `WITH recv AS (
         SELECT i.store_id, i.msku,
                SUM(i.declare_num) AS declared,
                SUM(i.received_num) AS received,
                SUM(GREATEST(i.declare_num - i.received_num, 0)) AS in_transit,
                MIN(s.status_name) AS status_name,
                MAX(s.to_receive_time) AS to_receive_time
           FROM fact_wfs_shipment_item i
           JOIN fact_wfs_shipment s
             ON s.platform=i.platform AND s.store_id=i.store_id AND s.shipment_id=i.shipment_id
          WHERE i.platform='walmart'
            AND s.platform='walmart'
            AND s.to_closed_time IS NULL
            AND s.to_cancelled_time IS NULL
            AND i.received_num > 0
          GROUP BY i.store_id, i.msku
       ), inv AS (
         SELECT store_id, msku, SUM(COALESCE(wfs_available_stock,0)) AS wfs_available_stock
           FROM fact_inventory_daily
          WHERE platform='walmart' AND snapshot_date = ?
          GROUP BY store_id, msku
       )
       SELECT COUNT(*) AS gap_rows
         FROM recv r
         LEFT JOIN inv v ON v.store_id=r.store_id AND v.msku=r.msku
        WHERE COALESCE(v.wfs_available_stock,0) = 0`,
      [latestInvDate],
    );
    const [gapRows] = await db.query<Row[]>(
      `WITH recv AS (
         SELECT i.store_id, i.msku,
                SUM(i.declare_num) AS declared,
                SUM(i.received_num) AS received,
                SUM(GREATEST(i.declare_num - i.received_num, 0)) AS in_transit,
                MIN(s.status_name) AS status_name,
                MAX(s.to_receive_time) AS to_receive_time
           FROM fact_wfs_shipment_item i
           JOIN fact_wfs_shipment s
             ON s.platform=i.platform AND s.store_id=i.store_id AND s.shipment_id=i.shipment_id
          WHERE i.platform='walmart'
            AND s.platform='walmart'
            AND s.to_closed_time IS NULL
            AND s.to_cancelled_time IS NULL
            AND i.received_num > 0
          GROUP BY i.store_id, i.msku
       ), inv AS (
         SELECT store_id, msku, SUM(COALESCE(wfs_available_stock,0)) AS wfs_available_stock
           FROM fact_inventory_daily
          WHERE platform='walmart' AND snapshot_date = ?
          GROUP BY store_id, msku
       ), dp AS (
         SELECT platform, store_id, msku, MIN(item_id) AS item_id
           FROM dim_product
          WHERE platform='walmart'
          GROUP BY platform, store_id, msku
       ), sh AS (
         SELECT platform, store_id, MIN(store_name) AS store_name
           FROM fact_wfs_shipment
          WHERE platform='walmart'
          GROUP BY platform, store_id
       )
       SELECT sh.store_name, dp.item_id, r.msku, r.declared, r.received, r.in_transit,
              COALESCE(v.wfs_available_stock,0) AS wfs_available_stock,
              r.status_name,
              DATE_FORMAT(r.to_receive_time, '%Y-%m-%d %H:%i:%s') AS to_receive_time
         FROM recv r
         LEFT JOIN inv v ON v.store_id=r.store_id AND v.msku=r.msku
         LEFT JOIN dp ON dp.platform='walmart' AND dp.store_id=r.store_id AND dp.msku=r.msku
         LEFT JOIN sh ON sh.platform='walmart' AND sh.store_id=r.store_id
        WHERE COALESCE(v.wfs_available_stock,0) = 0
        ORDER BY r.received DESC, r.store_id ASC, r.msku ASC
        LIMIT 10`,
      [latestInvDate],
    );

    print("4) overlap / lag diagnostics", {
      latest_inventory_snapshot: latestInvDate,
      class_counts: {
        not_received_rows: n(classAgg[0]?.not_received_rows),
        partially_received_rows: n(classAgg[0]?.partially_received_rows),
        fully_received_but_unclosed_rows: n(classAgg[0]?.fully_received_but_unclosed_rows),
      },
      red_flag_count: n(redFlagCnt?.red_flag_rows),
      red_flag_top10: redFlagRows,
      overlap_count_transit_gt0_and_wfs_gt0: n(overlapCnt?.overlap_rows),
      overlap_top15: overlapRows,
      gap_count_received_gt0_but_wfs0: n(gapCnt?.gap_rows),
      gap_top10: gapRows,
    });

    print("5) summary counters", {
      red_flag_count: n(redFlagCnt?.red_flag_rows),
      overlap_count_transit_gt0_and_wfs_gt0: n(overlapCnt?.overlap_rows),
      gap_count_received_gt0_but_wfs0: n(gapCnt?.gap_rows),
    });
  } finally {
    await db.end();
  }
}

main().catch((err) => {
  console.error("probeInTransitOverlap failed");
  console.error(err instanceof Error ? err.stack ?? err.message : String(err));
  process.exit(1);
});

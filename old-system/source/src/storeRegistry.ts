/**
 * storeRegistry.ts
 *
 * 统一的店铺来源：从 dim_store_config 读取 is_active=1 的沃尔玛店铺。
 * 供各同步脚本调用，替代写死的 STORES 数组。
 * 读表失败 / 结果为空时，安全回退到 syncDailyBaseData 里写死的 STORES，保证同步不因表异常而全挂。
 */
import "dotenv/config";
import * as mysql from "mysql2/promise";
import { STORES, StoreConfig } from "./syncDailyBaseData";

export type { StoreConfig };

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
}

/**
 * 读取 dim_store_config 中 is_active=1 的沃尔玛店铺 → StoreConfig[]。
 * 任何异常或空结果 → 回退写死 STORES（打印告警）。
 */
export async function loadStores(): Promise<StoreConfig[]> {
  let db: mysql.Connection | null = null;
  try {
    db = await getDb();
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, store_name, advertiser_id
       FROM dim_store_config
       WHERE platform = 'walmart' AND is_active = 1
       ORDER BY store_name`,
    );
    const list: StoreConfig[] = (rows as mysql.RowDataPacket[]).map((r) => ({
      storeId: String(r.store_id),
      storeName: String(r.store_name ?? ""),
      advertiserId: r.advertiser_id ? String(r.advertiser_id) : undefined,
    }));
    if (list.length === 0) {
      console.warn("[loadStores] dim_store_config 无 active 店铺，回退写死 STORES");
      return STORES;
    }
    console.log(`[loadStores] 从 dim_store_config 读到 ${list.length} 个 active 店铺`);
    return list;
  } catch (e) {
    console.warn(`[loadStores] 读 dim_store_config 失败，回退写死 STORES：${e instanceof Error ? e.message : String(e)}`);
    return STORES;
  } finally {
    if (db) { try { await db.end(); } catch { /* ignore */ } }
  }
}

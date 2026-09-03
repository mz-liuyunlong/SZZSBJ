# 产品管理 Tab V1 实施计划

> 说明：本次仅做代码核查与方案设计，**未修改任何代码/数据库**。本环境是项目本地代码镜像，没有生产服务器 SSH / MySQL 连接权限，无法直接执行 `npx ts-node scripts/inspect_mysql_schema.ts` 或抽样 SQL。下文所有表结构结论均来自仓库内 `sql/*.sql`、`docs/*.md`、`src/*.ts` 源码通读核实，标注"待人工执行确认"的地方，请在有数据库权限的环境跑一遍附带的 SQL 再拍板。

---

## 一、当前真实表结构核对结果

通读 `sql/001_create_data_warehouse_tables.sql`、`sql/002_add_indexes.sql`、`sql/003_product_identity_owner_cost_tables.sql`、`sql/004_add_cost_columns.sql`、`B线第1期/sql_01_建表与加列.sql`，确认如下（均为仓库已提交、已在用的建表脚本，非猜测）：

| 表 | 定义位置 | 关键字段 |
|---|---|---|
| `dim_product` | 001 第122-145行 + B线第1期加列 | platform, store_id, store_name, item_id, msku, sku, item_name, product_name, owner, launch_date（B线第1期新增）, status, fulfillment_type |
| `dim_owner` | 001 第148-161行 | owner_id, owner_name, department, status |
| `dim_product_owner` | 003 第39-59行 | platform, store_id, store_name, item_id, msku, owner_name, owner_id, effective_date, status, source_raw_id |
| `dim_product_cost_config` | 003 第65-87行 + 004加列 | platform, store_id, store_name, item_id, msku, sku, delivery_fee, shipping_fee, purchase_cost, logistics_cost, first_mile_shipping_cost（004）, last_mile_delivery_fee（004）, effective_date, status |
| `dim_product_identity` | 003 第13-33行 | platform, store_id, store_name, item_id, msku, sku, source_raw_id |
| `dim_product_business_state` | B线第1期 sql_01 第7-53行 | stat_date, platform, store_id, item_id, msku, product_type, lifecycle_stage, system_lifecycle_stage, launch_date（快照冗余字段） |

`dim_product.launch_date` 确认存在（B线第1期加列，非 001 原表），任务说明里"以当前真实表结构为准"的判断是对的，第0期报告的"没有上架字段"是旧状态。

---

## 二、dim_product 唯一键

```
UNIQUE KEY uq_dim_product (platform, store_id, item_id, msku(64))
```

✅ 正确使用 `store_id`，未用 `store_name`，符合规范。`dim_product` 是本页面主要的展示/负责人写入目标表。

---

## 三、dim_product_owner 唯一键 / active 负责人规则

```
UNIQUE KEY uq_dim_product_owner (platform, store_name(64), item_id, msku(64), owner_name(64))
```

⚠️ **风险点（必须提前告知）**：该表唯一键用的是 `store_name`，不是 `store_id`。这是 003 SQL 建表时的历史设计（`docs/feishu_item_owner_sync.md` 第85-87行也这样写），不是本次任务引入的问题，但与"store_id 是店铺唯一值"的原则冲突。

现有 active 规则（`syncFeishuItemOwnerToMysql.ts` 第439-456行）：按 `platform + item_id + msku` 分组，用窗口函数把非最新一条全部置为 `inactive`，注意**这个去重分组也没有带 store_id**，也是按 item_id+msku 全局去重（同一 item_id+msku 若真实分属两个不同 store_id，也会被这段逻辑合并成一个"当前负责人"）。

结论：V1 产品管理页的"改负责人"接口**不能复用**这段 upsert/去重逻辑原样照搬，必须按下面第八节的写入方案，用精确 UPDATE + store_id 条件定位，不触发这个唯一键结构的副作用。

---

## 四、dim_product_cost_config 唯一键 / 成本字段结构

```
UNIQUE KEY uq_dim_product_cost (platform, store_name(64), item_id, msku(64), effective_date)
```

同样以 `store_name` 而非 `store_id` 作为唯一键的一部分，风险同上。

**成本字段口径（004 SQL 注释原文，第25-33行）**：

```
total_base_cost = purchase_cost + first_mile_shipping_cost + last_mile_delivery_fee
purchase_cost            ← 领星 cg_price
first_mile_shipping_cost ← 领星 US_cg_transport_costs
last_mile_delivery_fee   ← 飞书 ItemID负责人.配送费   （注释声明的"正确"目标字段）
delivery_fee             ← 兼容保留，原飞书写入字段，勿删勿覆盖
logistics_cost           ← 兼容保留，原字段
```

🔴 **发现一个真实的架构漂移（非本次任务引入，但直接影响"WFS配送费"该读写哪个字段）**：

- `004_add_cost_columns.sql` 的注释明确说"飞书配送费 → last_mile_delivery_fee"，`src/syncLingxingProductCost.ts` 的注释（第9、13行）也复述了同样的说法。
- 但实际检查 `syncFeishuItemOwnerToMysql.ts` 第468-483行（当前仍在跑的同步脚本），飞书"WFS配送费（$）"列写入的字段仍然是 **`delivery_fee`**，不是 `last_mile_delivery_fee`。
- 全仓库搜索 `last_mile_delivery_fee`：只出现在注释里，**没有任何一处实际 INSERT/UPDATE 语句写过这个字段**。

也就是说：`last_mile_delivery_fee` 是 2 年前"预留设计"的字段，代码从未跟进迁移，真实历史数据全部在 `delivery_fee` 里。

**要求人工核实（我无数据库权限，无法代跑）**：
```sql
SELECT COUNT(*) AS cnt_delivery_fee     FROM dim_product_cost_config WHERE delivery_fee IS NOT NULL;
SELECT COUNT(*) AS cnt_last_mile        FROM dim_product_cost_config WHERE last_mile_delivery_fee IS NOT NULL;
```
预期结果：`cnt_delivery_fee` 远大于 0，`cnt_last_mile` = 0 或接近 0。若结果符合预期，V1 产品管理页按下方方案读写 `delivery_fee`（当前真实字段），不动 `last_mile_delivery_fee`；是否在 V1.1 迁移到 `last_mile_delivery_fee` 留作后续决策，本次不做迁移。

---

## 五、dim_product_business_state 字段情况

按天生成的快照表（`stat_date` 为唯一键一部分），要拿"当前"生命周期需要 `JOIN` 最新一天。现有代码 `src/feishuRawSalesRoutes.ts` 第694-703行（"订单利润 Beta"接口）已有先例：

```sql
LEFT JOIN dim_product_business_state bs
  ON bs.platform='walmart'
 AND bs.stat_date=(SELECT MAX(stat_date) FROM dim_product_business_state WHERE platform='walmart')
 AND bs.item_id=agg.item_id
 AND COALESCE(bs.msku,'')=COALESCE(agg.msku,'')
 AND (店铺按 store_id 优先、store_name 兜底的 OR 条件)
```

产品管理页复用同样的 JOIN 写法读 `lifecycle_stage`，为空显示"-"。**不修改这张表，不新增字段，不做重算**（符合任务"V1不做dim_product_business_state重算任务"）。

---

## 六、准备修改的文件

| 文件 | 修改内容 |
|---|---|
| `src/syncFeishuItemOwnerToMysql.ts` | 修复 BUG：删除对 `dim_product` 表 INSERT/UPDATE 语句中的 `source_raw_id` 字段引用（第401-413行）。**不改动**对 `dim_product_identity`/`dim_product_owner`/`dim_product_cost_config` 的 `source_raw_id` 写入（这三张表确实有该列） |
| `src/feishuRawSalesRoutes.ts` | 新增 3 个路由（见第七节），挂在文件末尾 `export default router` 之前 |
| `admin-frontend/src/FeishuRawSalesData.tsx` | `SHEET_TABS` 数组新增一项 `{ sheetId: "<REDACTED_FEISHU_SHEET_ID>", label: "产品管理" }`；新增该 tab 专属的列表渲染 + 可编辑单元格（负责人下拉、WFS配送费输入框、保存按钮） |

## 七、准备新增的文件

- 无需新增独立路由文件或独立表。按任务要求"不新建独立页面/不新建重复表"，新增接口直接写在 `feishuRawSalesRoutes.ts` 内。
- 如果 `FeishuRawSalesData.tsx` 改到 1000+ 行不易维护，可选：把产品管理 tab 的渲染逻辑拆到 `admin-frontend/src/ProductManagementTab.tsx`，由 `FeishuRawSalesData.tsx` import 使用（不算新页面/新路由，只是组件拆分，便于代码审查，非必须）。

## 八、负责人写入方案

**接口**：`POST /api/feishu-raw-sales/product-management/update-owner`
**参数**：`platform, store_id, item_id, msku, sku, owner`

**写入逻辑（不使用 INSERT...ON DUPLICATE KEY，规避第三节提到的 store_name 唯一键风险）**：

```sql
-- 1) 把该产品维度下的旧 active 负责人置为 inactive（带 store_id，不影响其他店铺）
UPDATE dim_product_owner
SET status='inactive', updated_at=NOW()
WHERE platform=? AND store_id=? AND item_id=? AND msku=? AND status='active';

-- 2) 查是否已存在该 (platform, store_id, item_id, msku, owner_name) 的历史行
SELECT id FROM dim_product_owner
WHERE platform=? AND store_id=? AND item_id=? AND msku=? AND owner_name=?;

-- 3a) 存在则重新激活该行
UPDATE dim_product_owner
SET status='active', store_name=?, effective_date=CURDATE(), source_system='product_management', updated_at=NOW()
WHERE id=?;

-- 3b) 不存在则插入新行（走精确 INSERT，不走 ON DUPLICATE KEY，避免命中旧唯一键误判）
INSERT INTO dim_product_owner
  (platform, store_id, store_name, item_id, msku, owner_name, effective_date, status, source_system)
VALUES (?, ?, ?, ?, ?, ?, CURDATE(), 'active', 'product_management');

-- 4) 同步更新 dim_product 快照
UPDATE dim_product
SET owner=?, updated_at=NOW()
WHERE platform=? AND store_id=? AND item_id=? AND msku=?;
```

步骤 1、3、4 建议放在同一个 MySQL 事务里（`beginTransaction/commit/rollback`），任一步失败整体回滚，避免"负责人已改但快照没同步"的中间状态。

`updated_by` / `operator` 字段：核查 003 SQL，`dim_product_owner` 表没有这两个字段。V1 暂不加字段（任务要求"是否需要新增字段"要在计划里说明，见第十节），`source_system` 写 `'product_management'` 作为操作来源标记，代替记录具体操作人；后续如需记录具体操作人，需要新增 `updated_by` 字段，放到 V1.1。

## 九、WFS配送费写入方案

**接口**：`POST /api/feishu-raw-sales/product-management/update-wfs-fee`
**参数**：`platform, store_id, item_id, msku, sku, wfs_delivery_fee`

**后端强制规则（CS测品兜底，不只靠前端）**：
```ts
const isCsTest = msku.toUpperCase().startsWith("CS");
if (isCsTest && Number(wfs_delivery_fee) !== 4) {
  return res.status(400).json({ error: "CS测品WFS配送费固定为4，不允许修改" });
}
```

**写入 SQL（只碰 delivery_fee 一个字段，不碰 purchase_cost / first_mile_shipping_cost / logistics_cost / last_mile_delivery_fee）**：

```sql
-- 1) 查该维度当天是否已有 effective_date=CURDATE() 的行
SELECT id FROM dim_product_cost_config
WHERE platform=? AND store_id=? AND item_id=? AND msku=? AND effective_date=CURDATE();

-- 2a) 有则只 UPDATE delivery_fee 这一列
UPDATE dim_product_cost_config
SET delivery_fee=?, source_system='product_management', updated_at=NOW()
WHERE id=?;

-- 2b) 没有则 INSERT 新行，其余成本字段留空（不臆造采购成本/头程成本的值）
INSERT INTO dim_product_cost_config
  (platform, store_id, store_name, item_id, msku, sku, delivery_fee, effective_date, status, source_system)
VALUES (?, ?, ?, ?, ?, ?, ?, CURDATE(), 'active', 'product_management');
```

**读取 SQL（列表接口展示用，避免"用整行 MAX(effective_date) 决定配送费"的错误做法）**：

```sql
SELECT delivery_fee
FROM dim_product_cost_config
WHERE platform=? AND store_id=? AND item_id=? AND msku=? AND delivery_fee IS NOT NULL
ORDER BY effective_date DESC, updated_at DESC
LIMIT 1;
```

对每个产品单独按"该字段自己的最新非空值"取值，而不是先按整行 `MAX(effective_date)` 定位一行再读该行的 `delivery_fee`（那样如果当天写入的行只碰了 `delivery_fee` 而其它成本字段为空，会导致展示口径互相干扰）。这正是任务要求的"不要用 MAX(effective_date) 同时决定采购、头程、配送费"在读取侧的落地方式。

## 十、是否需要新增字段

不需要。V1 复用现有字段：`dim_product.owner`、`dim_product.launch_date`、`dim_product_owner.*`、`dim_product_cost_config.delivery_fee`、`dim_product_business_state.lifecycle_stage`。

（唯一可讨论的是 `dim_product_owner` 缺 `updated_by`，V1 不加，留 V1.1。）

## 十一、是否需要新增表

不需要。全部复用现有 5 张表（`dim_product` / `dim_owner` / `dim_product_owner` / `dim_product_cost_config` / `dim_product_business_state`），不新建重复表。

## 十二、回滚方案

1. **代码回滚**：本次改动集中在 `syncFeishuItemOwnerToMysql.ts`（删几行字段引用）、`feishuRawSalesRoutes.ts`（新增 3 个路由，不改现有路由）、`FeishuRawSalesData.tsx`（新增 1 个 tab 分支，不改现有 tab 逻辑）。改动均为增量新增或删除明确错误的字段引用，`git revert` 单个 commit 即可完全回滚，不影响其他 6 个已有 tab。
2. **数据回滚**：
   - 负责人写入：`dim_product_owner` 每次操作是"旧行 inactive + 新行/复用行 active"，历史行不删除，可按 `updated_at` 时间窗口手工把误操作的行状态改回来（先查 `SELECT * FROM dim_product_owner WHERE item_id=? AND updated_at > '误操作时间点'` 确认影响范围，再决定是否人工回滚，不做自动回滚脚本）。
   - WFS配送费写入：只改了当天 `effective_date=CURDATE()` 那一行的 `delivery_fee` 列，其余历史 `effective_date` 行不受影响，误操作可直接 `UPDATE ... SET delivery_fee=旧值 WHERE id=?` 手工恢复。
3. **不涉及**：不改 RAW 层，不改 FACT 层，无需数据备份即可回滚（改动范围本身就很小、可逆）。

## 十三、风险点

1. 🔴 **P0 - dim_product_owner / dim_product_cost_config 唯一键用 store_name 不用 store_id**（历史遗留，非本次引入）：第八、九节的写入方案已规避（用精确 UPDATE + store_id 条件，不走 ON DUPLICATE KEY），但如果后续有人在这两张表上加新的批量同步逻辑，仍可能踩到这个坑，建议记入项目长期待办，不在 V1 改表结构。
2. 🟡 **P1 - delivery_fee vs last_mile_delivery_fee 字段漂移**：需要第四节的 SQL 核实后再定方向，V1 默认按 `delivery_fee`（当前真实数据所在字段）。
3. 🟡 **P1 - 本次无生产数据库访问权限**：本计划的表结构结论全部来自源码静态核查，未做过 `SELECT`/`DESCRIBE` 实测。正式改代码前，建议在有权限环境执行 `npm run db:inspect` 或至少跑一遍第十四节的验收 SQL 确认现状与本计划一致。
4. 🟢 **P2 - 前端目前是"整张表统一渲染"架构**，没有可编辑单元格的先例（`FeishuRawSalesData.tsx` 841行全是只读表格 + 筛选器），产品管理 tab 需要新增下拉框/输入框/保存按钮这类新 UI 组件，属于新增能力，不是复用现有渲染逻辑，工作量比"加一个 tab"看起来大。
5. 🟢 **P2 - CS测品判断口径**：`msku LIKE 'CS%'`，与 `cs_test_product_config` 表里维护的规则一致（007 SQL），未发现冲突。

## 十四、优先修复的已知 BUG：source_raw_id

**报错**：`Unknown column 'source_raw_id' in 'field list'`

**根因定位（已用源码核实，非猜测）**：

`src/syncFeishuItemOwnerToMysql.ts` 第401-413行，对 `dim_product` 表执行：

```sql
INSERT INTO dim_product
  (platform, store_id, store_name, item_id, msku, sku,
   item_name, owner, launch_date, source_system, source_raw_id, extra_json)
VALUES (...)
ON DUPLICATE KEY UPDATE
  ..., source_raw_id=VALUES(source_raw_id), ...
```

但 `dim_product` 表定义（`sql/001_create_data_warehouse_tables.sql` 第122-145行）**从未包含 `source_raw_id` 列**。该列只存在于 003 SQL 新建的 `dim_product_identity` / `dim_product_owner` / `dim_product_cost_config` 三张表。`docs/feishu_item_owner_sync.md` 第76-79行也明确写着 `dim_product`"已存在"，未要求补这个字段。

结论：这是纯粹的字段引用错误（脚本对 `dim_product` 误写了本不属于它的字段），不是"字段被删除导致的历史回归"，`dim_product` 从建表起就没有这一列。按任务要求"如果字段已经不存在，就不要继续写 source_raw_id"，修复方式是**删除**，不是补字段。

**修复补丁（未应用，待确认后执行）**：

```diff
  const { inserted, updated } = await upsertCount(db,
    `INSERT INTO dim_product
       (platform, store_id, store_name, item_id, msku, sku,
-       item_name, owner, launch_date, source_system, source_raw_id, extra_json)
-     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
+       item_name, owner, launch_date, source_system, extra_json)
+     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON DUPLICATE KEY UPDATE
       item_name=VALUES(item_name), owner=VALUES(owner), sku=VALUES(sku),
       launch_date=COALESCE(VALUES(launch_date), launch_date),
-      store_name=VALUES(store_name), source_raw_id=VALUES(source_raw_id), extra_json=VALUES(extra_json),
+      store_name=VALUES(store_name), extra_json=VALUES(extra_json),
       updated_at=NOW()`,
    [platform, storeId, resolvedStoreName, item_id, msku, sku,
-    item_name, owner, launch_date, SOURCE_SYSTEM, sourceRawId, extraBase],
+    item_name, owner, launch_date, SOURCE_SYSTEM, extraBase],
  );
```

`dim_product_identity`（第366-380行）、`dim_product_owner`（第425-435行）、`dim_product_cost_config`（第470-483行）三处的 `source_raw_id` 写入**保留不动**，这三张表确实有该列。

**验证方式（不重新拉取飞书 <REDACTED_FEISHU_SHEET_ID> 做大规模覆盖，只读或小范围验证）**：

1. 只读验证：`npx ts-node src/syncFeishuItemOwnerToMysql.ts`（默认 dry-run，不加 `--confirm-write`），确认能正常读表头、打印预览，不报错。
2. 小范围验证：应用补丁后执行 `npx ts-node src/syncFeishuItemOwnerToMysql.ts --confirm-write`，观察控制台第536-558行的 `printSummary` 输出，确认 `dim_product: 新增/更新` 计数正常增长、无报错退出。
3. 抽样核对（人工在有 DB 权限环境执行）：
   ```sql
   SELECT item_id, msku, owner, launch_date, updated_at
   FROM dim_product
   WHERE updated_at > NOW() - INTERVAL 10 MINUTE
   ORDER BY updated_at DESC LIMIT 20;
   ```
   确认这批更新的 owner/launch_date 符合预期，且没有影响未变化的产品行。

修复本身不涉及飞书重新拉取或覆盖，只是删掉两处错误字段引用，风险极低。

---

## 十五、建议接口清单（汇总）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/feishu-raw-sales/product-management` | 列表，支持 page/page_size/keyword/store_id/owner/product_type/msku/sku/item_id |
| POST | `/api/feishu-raw-sales/product-management/update-owner` | 改负责人 |
| POST | `/api/feishu-raw-sales/product-management/update-wfs-fee` | 改WFS配送费 |

路径挂在现有 `feishuRawSalesRoutes` 下，代码注释会明确写：`product-management 数据源为 MySQL DIM/状态表，不读取飞书 <REDACTED_FEISHU_SHEET_ID>`。

列表 SQL 主体（示意）：

```sql
SELECT
  p.platform, p.store_id, p.store_name, p.owner,
  p.item_id, p.msku, p.sku,
  COALESCE(NULLIF(p.item_name,''), NULLIF(p.product_name,''), '-') AS product_name,
  CASE WHEN p.msku LIKE 'CS%' THEN 'CS测品' ELSE '常规产品' END AS product_type,
  DATE_FORMAT(p.launch_date, '%Y-%m-%d') AS launch_date,
  COALESCE(bs.lifecycle_stage, '-') AS lifecycle_stage,
  cc.delivery_fee AS wfs_delivery_fee
FROM dim_product p
LEFT JOIN dim_product_business_state bs
  ON bs.platform=p.platform AND bs.store_id=p.store_id
 AND bs.item_id=p.item_id AND COALESCE(bs.msku,'')=COALESCE(p.msku,'')
 AND bs.stat_date=(SELECT MAX(stat_date) FROM dim_product_business_state WHERE platform='walmart')
LEFT JOIN (
  SELECT platform, store_id, item_id, msku, delivery_fee
  FROM dim_product_cost_config c1
  WHERE delivery_fee IS NOT NULL
    AND effective_date = (
      SELECT MAX(effective_date) FROM dim_product_cost_config c2
      WHERE c2.platform=c1.platform AND c2.store_id=c1.store_id
        AND c2.item_id=c1.item_id AND COALESCE(c2.msku,'')=COALESCE(c1.msku,'')
        AND c2.delivery_fee IS NOT NULL
    )
) cc ON cc.platform=p.platform AND cc.store_id=p.store_id
    AND cc.item_id=p.item_id AND COALESCE(cc.msku,'')=COALESCE(p.msku,'')
WHERE p.platform='walmart'
  -- + keyword/store_id/owner/product_type 筛选条件
ORDER BY p.updated_at DESC
LIMIT ? OFFSET ?;
```

CS测品行的 `wfs_delivery_fee` 展示层再兜底一次 `msku LIKE 'CS%' ? 4 : cc.delivery_fee`，即使某条 CS 测品历史上误写过非 4 的值，页面展示也强制显示 4（写入侧已在第九节做了后端拒绝）。

## 十六、前端字段说明

`FeishuRawSalesData.tsx` 新增 tab：`{ sheetId: "<REDACTED_FEISHU_SHEET_ID>", label: "产品管理" }`，专属渲染分支（不复用现有只读表格组件，因为需要可编辑单元格）：

- 展示列（严格按任务要求 11 列）：店铺ID、店铺名称、负责人、ItemID、MSKU、SKU、产品名称、产品类型、上架时间、生命周期、WFS配送费（$）
- 负责人列：下拉框（选项来自 `/filter-options` 复用 owner 查询逻辑），选中后调用 update-owner 接口
- WFS配送费列：常规产品为输入框；`msku` 以 `CS` 开头的行输入框 `disabled`，固定显示 `4`
- 保存：单行内联保存按钮（不做批量修改），成功/失败 toast 提示
- 筛选：分页、关键词、店铺ID、负责人、产品类型，均走 GET 接口的 query 参数

## 十七、测试命令

```bash
# 1. 类型检查（改动后必跑）
npm run typecheck

# 2. 负责人同步脚本 dry-run（验证 BUG 修复不报错）
npx ts-node src/syncFeishuItemOwnerToMysql.ts

# 3. 负责人同步脚本小范围写入验证
npx ts-node src/syncFeishuItemOwnerToMysql.ts --confirm-write

# 4. 本地起后台服务，人工在浏览器验收产品管理 Tab
npm run admin:build && npm run admin:server
```

## 十八、页面验收结果（本次未执行，因无生产环境访问权限，清单供实施后逐项打勾）

- [ ] 产品管理 Tab 正常显示，字段仅含要求的 11 列
- [ ] 不显示利润等级/库存状态/广告状态/问题标签
- [ ] 分页、搜索、店铺ID筛选、负责人筛选、产品类型筛选均正常

## 十九、负责人写入验收 SQL

```sql
-- 改前查看当前 active 负责人
SELECT * FROM dim_product_owner
WHERE platform='walmart' AND store_id=? AND item_id=? AND msku=? AND status='active';

-- 页面操作后复查：应只有 1 条 active，旧的应变为 inactive
SELECT owner_name, status, updated_at FROM dim_product_owner
WHERE platform='walmart' AND store_id=? AND item_id=? AND msku=?
ORDER BY updated_at DESC;

-- dim_product 快照应同步
SELECT owner, updated_at FROM dim_product
WHERE platform='walmart' AND store_id=? AND item_id=? AND msku=?;

-- 防串数据：同 item_id 下其他 store_id 不应变化
SELECT store_id, owner, updated_at FROM dim_product
WHERE platform='walmart' AND item_id=? ORDER BY store_id;
```

## 二十、WFS配送费写入验收 SQL

```sql
-- 改前后对比配送费，且 purchase_cost / first_mile_shipping_cost 不应变化
SELECT delivery_fee, purchase_cost, first_mile_shipping_cost, updated_at
FROM dim_product_cost_config
WHERE platform='walmart' AND store_id=? AND item_id=? AND msku=?
ORDER BY effective_date DESC;

-- CS测品应恒为4（无论页面是否尝试提交其他值）
SELECT msku, delivery_fee FROM dim_product_cost_config
WHERE platform='walmart' AND msku LIKE 'CS%' AND delivery_fee <> 4;
-- 期望：0 行
```

## 二十一、唯一键防串数据验证结果（待实施后人工跑一遍确认）

```sql
-- 同一 item_id 多个 store_id 场景：改其中一个 store_id 后，其余不变
SELECT store_id, owner, updated_at FROM dim_product WHERE item_id=? ORDER BY store_id;

-- 同一 item_id 多个 msku/sku 场景：改其中一个 msku 后，其余不变
SELECT msku, sku, owner, updated_at FROM dim_product WHERE item_id=? AND store_id=? ORDER BY msku;
```

## 二十二、数据源验收

- 不读取飞书 <REDACTED_FEISHU_SHEET_ID>：产品管理页 GET 接口全程无 `raw_feishu_table` / `FeishuSheetWriter` 调用，只查 `dim_product` / `dim_product_business_state` / `dim_product_cost_config`。
- 不写飞书 <REDACTED_FEISHU_SHEET_ID>：update-owner / update-wfs-fee 接口不引入 `FeishuSheetWriter`。
- 产品名称来自 `dim_product.item_name` / `product_name`；上架时间来自 `dim_product.launch_date`；生命周期来自 `dim_product_business_state.lifecycle_stage`；WFS配送费来自 `dim_product_cost_config.delivery_fee`；负责人来自 `dim_product.owner` + `dim_product_owner` active 映射。均已在第十五节 SQL 中体现。

## 二十三、V1.1 后续建议

1. 02:15 定时任务：待 V1 稳定运行 1-2 周、无数据错乱反馈后再排期。
2. 领星产品名称自动同步：需先确认领星商品接口的字段与调用频率限制。
3. `launch_date` 自动补齐（CS测品按首次广告日期反推 / 常规产品按首次WFS库存反推）：涉及 `fact_ads_product_daily` / `fact_inventory_daily` 大表扫描，建议单独立项评估性能。
4. CS测品 `delivery_fee=4` 批量补齐：建议先跑一次只读统计有多少条 CS 测品的 `delivery_fee <> 4`，再决定是批量脚本还是留给运营手工在新页面上改。
5. `dim_product_business_state` 重算任务：不属于产品管理页范畴，仍归 B线负责。
6. 是否把 `last_mile_delivery_fee` 正式启用替代 `delivery_fee`：取决于第四节的核实结果，若决定迁移，需要一次性数据搬迁 + 双写过渡期，不建议在 V1.1 直接切换。

## 二十四、是否建议后续加入 02:15 crontab

**本次不建议现在加。** 理由：V1 只做人工触发的读写接口，没有需要定时跑的批处理逻辑；只有 V1.1 的"产品名称同步""launch_date 自动补齐""CS测品配送费批量补齐"这几项功能明确落地后，才需要评估是否要挂定时任务，且需要与现有 02:15 附近的其他定时任务（如有）核对资源占用和执行顺序，避免冲突。当前阶段维持"V1 不加 crontab、不做自动任务"的既定原则。

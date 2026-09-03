# 飞书 ItemID负责人 → MySQL 同步说明

## ⚠️ V1.2 状态更新（当前生效）

从产品管理 V1.2 起，本文档描述的"飞书 → 结构化表"同步链路已**硬锁定为 RAW-only**：

1. 飞书 `<REDACTED_FEISHU_SHEET_ID>`（ItemID负责人表）**不再是日常维护入口**。运营不应再在这张飞书表里维护负责人、
   WFS配送费（$）、上架时间等字段。
2. 负责人、WFS配送费（$）、产品状态统一通过后台「产品管理」Tab 维护
   （`http://42.193.254.170/admin/#/feishu-raw-sales-data` → 产品管理），直接写
   `dim_product` / `dim_product_owner` / `dim_product_cost_config`。
3. `src/syncFeishuItemOwnerToMysql.ts` **只保留读取飞书 <REDACTED_FEISHU_SHEET_ID> → 写入 `raw_feishu_table`**
   这一段能力，用于历史镜像、初始化备份、排查对账。脚本**不再写** `dim_product` /
   `dim_product_owner` / `dim_product_cost_config` / `dim_product_identity` / `dim_owner`。
4. 不要再用这个脚本去覆盖产品管理页面维护的数据——它现在物理上写不到那几张表了（写入代码已停用，
   不是靠约定，是代码层面就不再执行那几段 SQL）。
5. 如需排查历史飞书数据，直接查 `raw_feishu_table`（`sheet_id='<REDACTED_FEISHU_SHEET_ID>'`），或使用后台仍保留的
   "ItemID负责人"历史只读接口（`GET /api/feishu-raw-sales/data?sheet_id=<REDACTED_FEISHU_SHEET_ID>`，前端 Tab 入口已隐藏，
   接口本身未删除，可用于排查）。
6. 飞书 `<REDACTED_FEISHU_SHEET_ID>` 表本身建议由管理员设置为只读 / 归档 / 历史备份，避免运营继续手工编辑（本次开发环境
   无飞书后台管理权限，未能直接操作，需要人工在飞书后台设置，见验收报告的操作说明）。

以下"概述"至"可追溯性"章节描述的是 **V1.1 及之前版本**的历史行为，保留作为背景参考，
**当前实际执行的写入范围以上面这一节为准**。

## 概述

将飞书表格「ItemID负责人」持续同步到 MySQL 数据中台 `walmart_ai_data`。

飞书表格地址：`<REDACTED_FEISHU_RESOURCE_URL>  
Sheet ID：`<REDACTED_FEISHU_SHEET_ID>`  
spreadsheetToken：`<REDACTED_FEISHU_SPREADSHEET_TOKEN>`（来自 `config/currentReportFieldMapping.json`）

---

## 数据流（V1.1 及之前的历史行为，V1.2 起下半段已停用）

```
飞书 ItemID负责人（Sheet: <REDACTED_FEISHU_SHEET_ID>）
        ↓  lark-cli + FeishuSheetWriter.readValues()
raw_feishu_table          ← 原始每行 JSON，raw_hash 去重（V1.2 仍然执行，唯一保留的写入）
        ↓  字段清洗 + 校验                                    ▲
dim_product_identity      ← 商品身份映射（V1.2 起停用）         │
        ↓                                                    │ V1.2 起，
┌─────────────────────┐                                      │ 下面这四张表
│ dim_product         │  ← 商品基础信息（V1.2 起停用）          │ 不再被本脚本
│ dim_owner           │  ← 负责人维度（V1.2 起停用）            │ 写入
│ dim_product_owner   │  ← 商品-负责人关系（V1.2 起停用）        │
│ dim_product_cost_config │ ← 配送费等成本配置（V1.2 起停用）    │
└─────────────────────┘ ─────────────────────────────────────┘
```

---

## 执行方式（V1.2 起，--confirm-write 只会写 raw_feishu_table）

```bash
# dry-run（默认，只预览不写入）
npx ts-node src/syncFeishuItemOwnerToMysql.ts

# 正式写入（V1.2 起：只写 raw_feishu_table，不再写任何结构化表）
npx ts-node src/syncFeishuItemOwnerToMysql.ts --confirm-write

# npm script
npm run sync:feishu-item-owner               # dry-run
npm run sync:feishu-item-owner -- --confirm-write  # 写入（仅 RAW）
```

---

## 字段映射

脚本自动识别表头，不依赖列号。支持以下别名：

| 字段 | 飞书表头别名 |
|------|------------|
| sku | SKU, sku |
| msku | MSKU, msku |
| item_id | 商品ID, ItemID, item_id |
| item_name | 中文名称, 商品名称, 产品名称, item_name |
| owner | 负责人, owner |
| delivery_fee | WFS配送费（$）, WFS配送费, 配送费, delivery_fee |
| store_name | 店铺, 店铺名称, store_name |
| platform | 平台, platform |
| status | 状态, status |
| remark | 备注, remark |

---

## 表结构说明（V1.2：除 raw_feishu_table 外，以下均为历史行为，本脚本已不再写入）

### raw_feishu_table（已存在，V1.2 仍在写）
原始 RAW 层，每行飞书数据保存一条。`raw_hash = md5(row_json)` 去重，相同内容不重复插入。

### dim_product_identity（新建 - 003 SQL，⚠️ V1.2 起本脚本停止写入）
商品身份映射表。唯一键：`platform + store_name + item_id + msku`。
- `item_id` 或 `msku` 为空时跳过，不写入，记录异常。

### dim_product（已存在，⚠️ V1.2 起本脚本停止写入）
唯一键：`platform + store_id + item_id + msku`。
- 需要 `store_id`，脚本从 `dim_store` 按 `store_name` 查找。
- 若 `store_name` 为空或查不到对应 `store_id`，跳过此表写入，记录警告。
- V1.2 起，`owner` / `launch_date` 只能通过产品管理页面维护。

### dim_owner（已存在，⚠️ V1.2 起本脚本停止写入）
唯一键：`owner_name`（`department` 为空时降级为仅 `owner_name` 唯一）。
- 已存在的负责人不重复插入。

### dim_product_owner（新建 - 003 SQL，⚠️ V1.2 起本脚本停止写入）
商品-负责人关系表。唯一键：`platform + store_name + item_id + msku + owner_name`。
- 重复同步时更新 `status` 和 `source_raw_id`，不新增重复行。
- V1.2 起，当前 active 负责人只能通过产品管理页面的"修改负责人"维护。

### dim_product_cost_config（新建 - 003 SQL，⚠️ V1.2 起本脚本停止写入）
成本配置表。唯一键：`platform + store_name + item_id + msku + effective_date`。
- `effective_date` 默认为同步当天日期。
- 仅当 `delivery_fee` 有值时写入。
- V1.2 起，`delivery_fee` 只能通过产品管理页面的"修改WFS配送费"维护。

---

## 校验规则

| 校验项 | 规则 | 失败处理 |
|--------|------|----------|
| item_id 为空 | 必填 | 写 raw，跳过 dim，记录异常 |
| msku 为空 | 必填 | 写 raw，跳过 dim，记录异常 |
| owner 为空 | 必填 | 写 raw，跳过 dim，记录异常 |
| delivery_fee 非数字 | 数值校验 | 写 raw，跳过 cost_config，记录异常 |
| 全空行 | 跳过 | 静默跳过，不记录异常 |

---

## 新增建表

部署前在服务器执行：

```bash
mysql walmart_ai_data < sql/003_product_identity_owner_cost_tables.sql
```

---

## 可追溯性（历史数据仍可查，V1.2 起不再产生新的关联写入）

V1.1 及之前写入的历史数据里，DIM 层仍保留 `source_raw_id` 字段，值为 `raw_feishu_table.raw_hash`，
可以从 DIM 层反查原始飞书行数据（这是历史数据，V1.2 起不会再新增）：

```sql
SELECT r.*
FROM dim_product_owner po
JOIN raw_feishu_table r ON r.raw_hash = po.source_raw_id
WHERE po.item_id = 'YOUR_ITEM_ID';
```

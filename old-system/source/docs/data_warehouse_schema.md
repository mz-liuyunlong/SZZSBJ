# 数据中台架构说明文档 v1.0

> 数据库：`walmart_ai_data`（MySQL）
> 版本：v1.0 · 2026-06-24

---

## 一、整体架构

采用 **5 层数据架构**，所有数据最终统一进入 MySQL。

```
领星 API / 飞书表格 / 前端上传（CSV）
              ↓
        RAW 原始层（保留完整原始数据）
              ↓
     DIM 维度层 + FACT 事实业务层
              ↓
         EVENT 业务事件层
              ↓
           AI 分析层
              ↓
      前端展示 / 飞书通知
```

---

## 二、分层说明

| 层级 | 前缀 | 表数量 | 核心职责 |
|------|------|--------|---------|
| RAW  | `raw_` | 4 | 保留所有原始响应，不过度拆字段 |
| DIM  | `dim_` | 4 | 稳定的基础维度（店铺/商品/人员/关键词） |
| FACT | `fact_` | 6 | 核心业务指标，每日聚合粒度 |
| EVENT | `biz_` | 1 | 业务异常事件、提醒、任务流 |
| AI   | `ai_`  | 1 | AI 分析结果，只读 FACT/DIM，只写 ai_analysis_result |
| 系统 | `sync_` / `data_` / `schema_` | 3 | 任务日志、对账、字段变更记录 |

---

## 三、数据来源与入口

| 数据来源 | 入口方式 | 落点 |
|---------|---------|------|
| 领星 API | 定时脚本拉取 | `raw_lingxing_api` → DIM/FACT |
| 飞书表格 | 定时脚本 + 人工补充 | `raw_feishu_table` → FACT/EVENT |
| 前端上传 CSV | 用户上传（必须提供 `store_id`） | `raw_frontend_upload` + `raw_walmart_ads_csv` → `fact_ads_keyword_daily` |
| 前端人工配置 | 前端页面操作 | 直接写 DIM/FACT |

---

## 四、核心表说明

### RAW 层

| 表名 | 用途 |
|------|------|
| `raw_lingxing_api` | 领星 API 原始响应，保留 response_json |
| `raw_feishu_table` | 飞书所有 sheet 原始行数据 |
| `raw_frontend_upload` | 前端上传文件记录 |
| `raw_walmart_ads_csv` | Walmart 广告 CSV 原始行（前端上传直入 MySQL） |

### DIM 层

| 表名 | 唯一键 | 说明 |
|------|--------|------|
| `dim_store` | `platform + store_id` | 店铺，**不以 store_name 做唯一键** |
| `dim_product` | `platform + store_id + item_id + msku` | 商品 |
| `dim_owner` | `owner_name + department` | 负责人 |
| `dim_keyword` | `platform + normalized_keyword + keyword_type` | 关键词/搜索词 |

### FACT 层

| 表名 | 粒度 | 说明 |
|------|------|------|
| `fact_sales_daily` | 日 + 店铺 + 商品 | 每日销售 |
| `fact_inventory_daily` | 日 + 店铺 + 商品 | 每日库存快照 |
| `fact_ads_product_daily` | 日 + 广告活动 + 商品 | 商品广告 |
| `fact_ads_keyword_daily` | 日 + 店铺 + 商品 + 关键词 + 来源 | **统一关键词广告（领星/CSV/前端/飞书）** |
| `fact_profit_daily` | 日 + 店铺 + 商品 | 每日利润 |
| `fact_purchase_daily` | 采购单号 + SKU | 采购记录（预留） |

### EVENT 层

| 表名 | 说明 |
|------|------|
| `biz_event` | 统一业务事件：断销/库存预警/ACoS超标/亏损/负责人缺失等 |

### AI 层

| 表名 | 说明 |
|------|------|
| `ai_analysis_result` | AI 分析结果，AI 只写此表，不允许直接修改 FACT/DIM |

---

## 五、关键设计原则

1. **store_id 是唯一标识**：所有表关联必须使用 `store_id`，不以 `store_name` 做关联键
2. **RAW 层优先 JSON 字段**：`response_json` / `row_json` 保留原始数据，不过度拆字段
3. **所有表预留 `extra_json`**：不确定的字段先放 `extra_json`，后续再通过 `ALTER TABLE` 提升为正式字段
4. **不允许直接删除字段**：废弃字段先标记 `deprecated`，再写入 `schema_change_log`
5. **AI 只写 ai_analysis_result**：不允许 AI 直接修改 FACT/DIM 数据

---

## 六、字段迭代规则

```
发现新字段有价值
     ↓
先存入 extra_json
     ↓
评估稳定性（观察 2-4 周）
     ↓
通过 ALTER TABLE ADD COLUMN 提升为正式字段
     ↓
写入 schema_change_log（change_type = add_column）
     ↓
更新本文档
```

**禁止直接删除字段**，废弃流程：
1. 在文档标记 `[deprecated]`
2. 写入 `schema_change_log`（change_type = deprecate_column）
3. 确认无业务引用后，提 `drop_column_request`
4. 人工确认后执行 DROP

---

## 七、Walmart 店铺清单

已初始化到 `dim_store`：

| store_id | store_name |
|----------|------------|
| 110687423514268160 | CN2601-瑞盈龙盛(刘云龙） |
| 110687427724845056 | CN2501-掌上便捷(陈佳聪） |
| 110687428693128704 | CN2502-悦斯电子(陈文胜） |
| 110689966555011584 | CN2602-添详商贸(邓添祥) |
| 110704863834580480 | CN2603-四颗洋葱(林翔） |
| 110704872940532224 | HK2612-张李华(賽藝境） |

---

## 八、系统日志表

| 表名 | 用途 |
|------|------|
| `sync_task_log` | 每次同步任务的运行记录（成功/失败/行数） |
| `data_reconcile_log` | MySQL vs 飞书 vs API 数据对账 |
| `schema_change_log` | 所有表结构变更记录（强制执行） |

---

## 九、执行顺序

```bash
# Step 1: 检查现有库结构
npx ts-node scripts/inspect_mysql_schema.ts

# Step 2: 创建所有新表（IF NOT EXISTS，安全）
mysql -u<user> -p walmart_ai_data < sql/001_create_data_warehouse_tables.sql

# Step 3: 创建索引
mysql -u<user> -p walmart_ai_data < sql/002_add_indexes.sql

# Step 4: 人工确认评估报告中的 ❓ 和 ❌ 表后，再决定是否清理
```

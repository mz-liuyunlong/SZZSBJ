# 批13 · 单品现金利润改按「店铺 + ITEMID」出数 —— 核查与改造方案 v1

> 2026-08-14 ｜ 依据：需求方拍板「先做 175 个可直归的」「采购归属不设日期切点」「第一批范围 YC00200+ 全部 252 个 item」
> 本文所有现状描述均来自**实读代码 + 线上只读探针**，未作任何推测。

---

## 一、现网实现核查（`src/aiFinanceRoutes.ts` L855-1293，`AiFinanceItemCashProfit.tsx` 388 行）

### 1.1 现在的聚合键是「店铺 + 本地SKU」

```ts
const rowOf = (store: string, sku: string): IcpRow => { const k = `${store}||${sku}`; ... }
```

所有成本源先经 **msku → sku** 映射再落行，映射表来自：

```sql
SELECT msku, MAX(sku) FROM fact_inventory_daily
 WHERE COALESCE(sku,'')<>'' AND msku<>'' GROUP BY msku HAVING COUNT(DISTINCT sku)=1
```

即 **只有唯一命中才用**，多命中直接丢弃 → 这是现网「未映射」行的来源之一。

### 1.2 七条成本源各自的 item_id 可用性（决定改造难度）

| 源 | 表 | 现在怎么落行 | 有无 item_id | 改造后 |
| --- | --- | --- | --- | --- |
| 回款/退款/赔付/WFS配送/其他按品 | `fact_reconciliation_item` | msku→sku | **有**（sale 无 item_id 占比：05月 0%、06月 0.15%/$55.22、07月 0.57%/$264.72） | 直接用 item_id，**去掉一层映射，更准** |
| 广告 | `fact_ads_product_daily` | msku→sku，msku 空时走 store+item_id 反查 msku 再转 sku | **有** | 直接用 item_id，**反查链路整段删除** |
| 仓储费 | `fact_wfs_storage_fee` | `sku` 列实为 MSKU，映射不中时按原名 | **有，100% 填充** | 直接用 item_id |
| 入库运输 | `fact_inbound_freight_alloc` | msku→sku，不中则进店铺级 | **有，100% 填充** | 直接用 item_id |
| 头程现金 | `fact_shipping_first_let` | 按 sku 落行 | **有**（store_id 为空的 8 行 ambiguous 已被 `l.store_id<>''` 排除） | 直接用 item_id |
| **采购现金** | `fact_purchase_cash_item` | sid 有效→归店；sid=0→按发货单 sku 份额拆店 | **无（SKU级）** | **唯一需要分摊的路径** |
| **期初池消耗** | `biz_finance_opening_cost` | SKU 级 FIFO，按店铺销量份额拆 | **无（SKU级）** | 需分摊；但见 §3.2 |

**结论：七条里五条本来就带 item_id，改造是「去掉映射层」而不是「新增映射层」——比预想的简单，且更准。真正要分摊的只有采购与期初池两条。**

### 1.3 换 key 会牵动但**不需要改**的部分

- 店铺级容器 `sRowOf`（SEM / 测评 / 赔付 / 其他 / 未映射广告 / 未归属采购）：本就与品无关，原样保留。
- 五个哨兵（回款完整性、广告/仓储/入库 管道vs账单、期初恒等）：比的都是**总量**，与聚合键无关，原样保留。
  - 现网状态（需求方截图）：回款完整性 差 -68,783.91、广告 差 67,420.76、仓储 差 7,593.33、入库运输 差 8,726.83 均为红，期初恒等为绿。**这些是既有问题，与本次改造无关，不得混为一谈。**
- 汇率折算 `rateOf`（归属月取上一月 my_rate 退 rate_org）、虚拟SKU豁免、`normStore` 领星精度损坏修复：全部原样保留。
- 早期评估区（2026-01~04）：仍按 SKU，不动。

---

## 二、关键风险与既定口径（写代码前必须钉死）

### 2.1 ITEMID 不是全局唯一，(店铺, ITEMID) 才是

线上实测：`19307124352` 挂 4 个店铺（JJ8006）、`19051502014` 挂 3 个店铺（且对应 YC00019 与 YC00019-2 两个本地SKU），另有 25+ 个 ITEMID 挂 2 店。

已查明成因：**同一 Walmart listing 多店共用** —— 两店各有自己的 MSKU（如 CN2601 `YC00377-1D`／HK2614 `YC00377-1U`），共用同一个 ITEMID。**不是脏数据。**

> **硬性口径：一律用 (store_id, item_id) 复合键；禁止任何「由 item_id 反查店铺」的写法；页面必须带店铺列。**

### 2.2 一个 (店, ITEMID) 可能对应多个本地SKU

`19051502014` → YC00019 与 YC00019-2。改造后 SKU 列改为**多值展示**（与现网 MSKU 列同风格，逗号拼接、上限 12 个）。

### 2.3 采购的 sid=8345 对不上 dim_store

实测 9 个 sid 中 8 个命中，唯 `8345`（5 行 / ¥16,166.24）在 dim_store 查无。**未查明前该 5 行走「未归属采购」单列，禁止猜测归属。**

### 2.4 ambiguous 头程 3 行（¥1,951.52）暂挂起

YC00206 / YC00364 / YC00305 三行因跨多店无法自动定店，**全部落在需分摊的 36 个 SKU 内，不在本次 175 个范围内**，不阻塞。详见 TASK_CHANGE_LOG「ambiguous 归属可行性定案」。

---

## 三、改造方案

### 3.1 隔离新建，不动现网接口（铁律：新功能隔离开发，最小改动旧页面）

| | 现网 | 新增 |
| --- | --- | --- |
| 接口 | `GET /api/finance/item-cash-profit`（按 店铺+SKU） | `GET /api/finance/item-cash-profit-v2`（按 店铺+ITEMID） |
| 前端 | `AiFinanceItemCashProfit.tsx` | `AiFinanceItemCashProfitV2.tsx`，独立 hash 路由（UI_STANDARDS §9） |
| 风险 | 零 —— 旧接口旧页面**一行不改** | 新页面验完再决定是否替换 |

新接口支持 `scope` 参数：

- `scope=clean`（第一版默认）：只出 **1店1item 的可直归 item**，零分摊争议 —— YC00200+ 范围内 175 个，全量范围内 243 个。
- `scope=all`：全部 item，需分摊的按 §3.3 规则拆。

### 3.2 期初池：第一版恒为 0，但保留逻辑

线上实测：**YC00200+ 的 211 个 SKU 100% 不在期初池**（`biz_finance_opening_cost` 无记录）。故第一版这 175 个 item 的「期初消耗」列恒为 0、「耗池量」恒为 0。

FIFO 池推进逻辑**必须原样保留**（老品第二批要用），只是在 clean scope 下不产生行。

### 3.3 采购分摊规则（唯一需要分摊的路径）

按需求方 2026-08-14 拍板「不设日期切点，逐行判断」：

```
A. sid ≠ 0 且能对上 dim_store  → 直接归该店
     店内该 sku 若只对应 1 个 item → 全额直落（175 个全部走这条）
     店内该 sku 对应多个 item     → 按 fact_shipping_first_let 发货量份额拆
B. sid = 0                      → 按发货单 sku→(店,item) 发货量份额拆
C. A/B 均不可得                  → 计入店铺级「未归属采购」，不摊到品，不判为缺陷
   （含 sid=8345 的 5 行；含新品采购尚未发货的 39 行 / ¥175,676.66）
```

**对本次 175 个 item：全部是 1店1item，份额恒为 100%，等价于直落，零分摊争议。**

### 3.4 前端改动

沿用现网全部 UI 规范（§1 工具条 / §5 列宽拖动 / §7 表头ⓘ / §8 表头吸顶+总计吸底+翻页 / §9 独立 hash 路由）。列定义变化：

- 新增 **ITEM_ID** 为主键列（紧跟店铺之后），**SKU 与 MSKU 降为展示列、支持多值**。
- 其余 17 列口径与现网完全一致，不改算法、不改表头文案。
- 顶部增加 scope 切换（可直归 / 全部），默认「可直归」。

---

## 四、验收标准

| # | 验收项 | 期望 |
| --- | --- | --- |
| 1 | 后端 `npx tsc --noEmit -p tsconfig.json` | 错误数 = 基线 8（缺包噪声：exceljs/bcryptjs/jsonwebtoken），不得新增 |
| 2 | 前端 `npx tsc --noEmit` + `npm run build` | 0 错误；记录 bundle 名 |
| 3 | 现网旧接口回归 | `/item-cash-profit` 返回体与改造前**逐字节一致**（同参数比对 md5） |
| 4 | 新接口 `scope=clean` 行数 | YC00200+ 口径 = **175 行**；全量口径 = **243 行** |
| 5 | 收入交叉核对 | 新接口 175 行销售额合计 vs 直接 SQL 按 (store,item) 聚合 recon sale，差额 = 0 |
| 6 | 采购交叉核对 | 175 行采购合计 vs §3.3 规则的 SQL 试算，差额 = 0 |
| 7 | 期初消耗 | 175 行全部为 0（实证：YC200+ 100% 不在期初池） |
| 8 | 哨兵 | 五个哨兵数值与现网**完全一致**（换 key 不改变总量） |
| 9 | 人工抽验 | TOP 5 item 逐个核到沃尔玛账单与领星采购单 |
| 10 | 服务 | 重启后 `sleep 10` 再冒烟；`curl /api/finance/item-cash-profit-v2` 未鉴权返回 401 属正常 |

---

## 五、分期

- **本期（第一批）**：新接口 + 新页面，`scope=clean`，175 个可直归 item 跑通并逐个核账。
- **第二批**：接 77 行分摊逻辑（36 个 SKU），同期处理 ambiguous 3 行与 sid=8345。
- **第三批**：老品（有期初库存的 164 SKU / 455 item），按发货单拆期初，解决一刀切争议。

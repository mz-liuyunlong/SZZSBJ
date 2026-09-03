# Phase 7 — 发货单（仓库发货）跟进 设计说明

记录日期：2026-06-21
背景：测试发现 purchaseOrderList 只到"采购到货"(status_shipped: 1未到货 / 3已到货)，**不含"是否已发货/发货到哪一步"**。
发货环节是领星独立的「发货单」体系，需新接数据源。

---

## 一、修正后的全链路状态机

```
【采购单接口 purchaseOrderList 管的】（Phase 1-6 已实现）
  ① 审批未下单    auditor_time有 + order_time空
  ② 已下单未到货  order_time有 + status_shipped=1
  ③ 已到货        status_shipped=3
        ↓ 人工创建发货单 → 领星扣减"该采购入库批次库存"
──────────────── 采购单接口看不到下面 ────────────────
【发货单接口管的】（Phase 7 待建）
  ④ 已创建发货单（批次库存被扣减）→ 仓库发货流程：
       打包 → 装箱 → 头程物流 → 确认发出 → 海外到货
       海外仓：亚马逊FBA / 沃尔玛WFS / 第三方海外仓
       每个状态卡住超时 → 提醒（新增一组规则）
```

判定"已创建发货单" = 该采购入库批次库存被扣减（发货单接口/库存接口可查）。

---

## 二、领星接口（用户已提供，均只读）

### 亚马逊 FBA
| 用途 | 路径 | 方法 |
|------|------|------|
| 查询FBA发货计划 | `/erp/sc/data/fba_report/shipmentPlanLists` | POST |
| 查询发货单详情 | `/erp/sc/routing/storage/shipment/getInboundShipmentListMwsDetail` | POST |
| （创建发货计划，写，不用） | `/erp/sc/routing/storage/shipment/createShipmentPlan` | — |

### 沃尔玛 WFS
| 用途 | 路径 | 方法 |
|------|------|------|
| 查询WFS货件列表 | `/cepf/warehouse/api/openApi/queryWFSCargoPage` | POST |
| 查询WFS库存列表 | `/cepf/warehouse/api/openApi/queryWFSInventionPage` | POST |

注：WFS 是 `/cepf/...` 前缀，与采购单 `/erp/...` 不同，但同一 LingxingClient 可调（只读校验通过）。

---

## 三、Phase 7 待办（探测真实字段后细化）

1. **probeShipments.ts**（先做）：调用上述读接口，打印字段结构 + 状态分布 + 关联键，搞清：
   - 发货单如何关联回 SKU / 采购批次 / order_sn；
   - 哪个字段表示发货状态（打包/装箱/头程/确认发出/海外到货）；
   - 分页参数名（offset/length 还是 page/pageSize）。
2. **fetchShipments.ts**：标准化拉取 FBA + WFS 发货单。
3. **发货阶段枚举**：在 stages.ts 增加 SHIP_PACKING / SHIP_BOXING / SHIP_FIRST_LEG / SHIP_CONFIRMED / SHIP_ARRIVED_OVERSEAS 等。
4. **checkStatus 扩展**：到货后用发货单状态接管"到仓发货"环节，替换当前不可靠的 status_shipped===2 终态判定。
5. **规则配置**：各发货阶段超时天数/提醒间隔（新增 R005~R009 之类）。

---

## 三bis、探测到的真实接口结构（2026-06-21）

### FBA 发货计划 shipmentPlanLists（POST, 参数 offset/length 可用）
外层：`{ ispg_id, create_time, seq(RP260414001), remark, create_user, list[] }`
list[] 每条：`sku`(JJ9002)、`msku`、`status`(数字, 样本=5, **含义待确认**)、`order_sn`(R260414001=发货单号)、`fnsku`、`wname`(美东NY仓)、`sid`、`shipment_plan_quantity`、`shipment_time`、`create_time`、`box_num`、`is_relate_mws`。
→ 有 sku、status、发货单号、目标仓、计划时间。

### WFS 货件 queryWFSCargoPage（POST, 参数 offset/length 可用）
每条：`cargo_code`、`in_bound_order_id`、`store_name`、`country_name`、`logistics_code`、`cargo_create_date`、`cargo_status`(PENDING_SHIPMENT_DETAILS / CANCELLED…)、`status`(0/4)、`cargo_sync_status`(已申报/已取消)、各阶段时间戳 `to_pending_time/to_await_time/to_receive_time/to_closed_time/to_cancelled_time`、`cargo_good_list[]`(sku/msku/declare_num/received_num/shipments_num)。
→ 有 sku、状态机、各阶段时间戳（适合算阶段超时）。

### WFS 库存 queryWFSInventionPage
"参数检验不通过"——缺必填参数（多半 store_id/sid），暂不用。

### 关联决策（已确认）
**按 SKU + 时间关联**：某 SKU 采购已到货(status_shipped=3)，但近 N 天该 SKU 无新发货计划/货件 → 提醒发货。不做精确批次匹配。

### 仍缺（设计发货流程阶段提醒前必须确认）
- FBA `list[].status` 状态码表（0/1/2…各含义，对应 打包/装箱/头程/确认发出/海外到货）。
- WFS `cargo_status` 全部取值及对应阶段。

---

## 五、Phase 7 拆两步走

- **7a ✅ 已完成（2026-06-21 实测 410→26 条）**：到仓未发货提醒由三条判据共同决定，任一命中即不提醒：
  ① fetchShipments：近60天该SKU有 FBA发货计划/WFS货件；
  ② 采购单 update_time 超 60 天（PMC_STALE_SHIP_DAYS，历史遗留）；
  ③ fetchLocalInventory：本地仓该SKU当前库存≤0（已发走/被扣减）。
  三个数据源任一拉取失败均降级（不应用该过滤），不误杀。涉及文件：fetchShipments.ts / fetchLocalInventory.ts / checkStatus.ts / pipeline.ts。
- **7b（需状态码表）**：发货流程各阶段卡住提醒（打包/装箱/头程/确认发出/海外到货超时），用 WFS 各阶段时间戳 + FBA status 算停留天数。

---

## 四、当前 Phase 1-6 的临时处置（上线一半，安全）

在 Phase 7 接好前：
- **关闭** runDaily 的"到仓发货"提醒（ARRIVED_PENDING_SHIP / OVERDUE_SHIP），避免历史已到货老单被当成待发货轰炸（实测 410 条）。
- **保留** 审批未下单(R001)、已下单未到货(R002) 两段正式提醒——这两段采购单接口能可靠判断。
- 终态 status_shipped===2 永不成立，相关分支先视为无效。

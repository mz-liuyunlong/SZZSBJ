# AI PMC 模块 — 待修复问题清单

状态：记录在案，**待 Phase 5/6 全链路测试完成后统一修复**
记录日期：2026-06-21
适用范围：src/ai_pmc/ Phase 1–4

> 说明：以下问题不阻塞继续开发 Phase 5/6，但 ⚠️ 标记项在「开启 cron 自动写台账」之前必须修掉，否则会漏提醒或写错数据。

---

## 零、测试中发现的致命问题（最高优先级，--send 前必修）

### ISSUE-12 🔴 历史已发货老单被全部判成「到仓待发货」
- 现象：runDaily dry-run 输出 410 条"到仓待发货"，含 PO250821001 等 2025-08 的老单（早已发完货）。
- 根因：终态判据 `status_shipped === 2` 未生效——这些老单的 status_shipped 不等于 2，或领星不用该值表示"已发货完成"。导致所有"已入库≥应入库"的历史单永远卡在待发货、进不了 DONE。
- 风险：真发会给仓库负责人刘晶晶轰炸数百条无效提醒。
- 待办：用诊断脚本确认领星"已发货完成"的真实字段/取值，改对 `resolveStage` 与 checkStatus 的终态判定。可能还需对到仓时间做"过老即视为已完成/不再提醒"的兜底（如 D0 距今 > N 天直接跳过）。

### ISSUE-13 🔴 D0（warehouse_time）取值为空，逾期判断永不触发
- 现象：提醒文案是"货已到仓，请安排发货"而非"货已到仓 N 天"，说明 arrival_time 为空 → daysFromD0=0 → 永远走 R003、进不了 R004 逾期/升级。
- 根因：`fetchLingxing.mapOrder` 里 `arrival_time = raw.warehouse_time`，但该字段名可能不对或采购单主表无此值。
- 待办：用诊断脚本确认领星到仓/入库时间真实字段名；若主表确无，则落实 P0-2 兜底（用通知日志首次 ARRIVED_PENDING_SHIP 时间作 D0）。

---

## 一、必修（影响正确性 — 自动写台账前修复）

### ISSUE-1 ⚠️ fetchLingxing 单页失败会整次中断拉取
- 文件：`fetchLingxing.ts` 第 191-194 行
- 现象：分页 catch 里是 `break`，某一页彻底失败就停止拉取，**后面所有采购单被静默丢弃** → 漏提醒。
- 期望（P2-2）：记日志后跳过本批、继续下一页。
- 改法：`catch { ... }` 内把 `break` 改为 `offset += PAGE_SIZE; continue;`（注意避免死循环，可加最大空页计数）。

### ISSUE-2 ⚠️ readOwners 缺 SKU→ItemID 桥接，运营负责人全部兜底
- 文件：`readOwners.ts`（列写死 A=ItemID、B=负责人）；`generateTasks.ts` 第 145 行、`checkStatus.ts` 第 225 行把 SKU 当 ItemID。
- 现象：服务器日志满屏 `YC00xxx 无运营负责人配置 兜底江梓博`；台账 H 列（运营负责人）全部写成江梓博。
- 影响：当前提醒收件人用固定角色（采购/仓库/PMC），**收件人不受影响**；但台账负责人列写错，且未来「补货执行→运营负责人」提醒会失效。
- 改法：`readOwners` 改为按表头名读出 sku / 商品ID(ItemID) / 负责人 三列，建立 `sku → { itemId, ownerName, openId }` 映射；`generateTasks` / `checkStatus` 用该映射拿真正的 ItemID 与负责人。

### ISSUE-3 checkStatus 多 SKU 采购单数量算错
- 文件：`checkStatus.ts` `getQty()` 第 71-78 行
- 现象：`getQty(order)` 把整张单所有明细数量求和，再套用到单内每个 SKU。多 SKU 单会：① 别的 SKU 到货导致本 SKU 误判到仓/部分到货；② 同单多 SKU 生成多条雷同提醒。
- 期望（P1-5）：按 (ItemID, 采购单号) 聚合各自明细。`generateTasks` 已按 SKU 分组聚合（正确），两边需对齐。
- 改法：checkStatus 也按 sku 分组，`getQty` 只统计该 sku 对应的明细。

---

## 二、建议（健壮性）

### ISSUE-4 读表写死 A1:L3000 / A1:I3000 上限
- 文件：`generateTasks.ts`、`updateTasks.ts`、`checkStatus.ts`
- 风险：台账/日志超过 3000 行会被截断（尾部产品多、单量会涨）。
- 改法：用 `writer.getRowCount()` 动态确定行数，或分页读取。

### ISSUE-5 新行追加用 existingRows.length+1 估算起始行
- 文件：`generateTasks.ts` 第 242 行
- 风险：读取行数与飞书真实行数不一致时，追加可能覆盖或留空行。
- 改法：改用 `writer.getRowCount()` 真实行数定位起始行。

### ISSUE-6 防重复用字符串字典序比较 notify_time
- 文件：`checkStatus.ts` 第 114 行 `notifyTime > existing`
- 风险：依赖时间字符串格式严格统一，脆。
- 改法：用 `parseBJDateMs()` 转毫秒数值后比较。

---

## 三、锦上添花（一致性 / 性能 / 整洁）

### ISSUE-7 dateUtil 未被全员复用
- `generateTasks.ts` / `readOwners.ts` 自写 `nowBJ()` / `isEmpty()`，违背 P1-3「集中解析」。
- 改法：统一改调 `dateUtil` 的 `nowBJString()` / `isEmptyTime()`。

### ISSUE-8 token/sheetId 多处硬编码
- `generateTasks.ts` / `readOwners.ts` / `checkStatus.ts` 各自硬编码表 token、sheetId。
- 改法：统一从 `config.ts` 的 `PMC_SPREADSHEET_TOKEN` / `SHEET` 常量引用。

### ISSUE-9 逐行两次 writeCells，写请求过多
- `generateTasks.ts` / `updateTasks.ts` 每行发 2 次飞书写请求（F/G + K/L），34 条 = 68+ 次，量大时慢且易触发限流。
- 改法：合并为批量写。

### ISSUE-10 一次运行台账被读多遍
- generate / check / update 各读一次台账。
- 改法：编排层读一次，传入各函数复用。

### ISSUE-11 checkStatus 中 lookupOwner() 计算未使用（dead code）
- 文件：`checkStatus.ts` 第 228 行
- 改法：删除，或在按 ISSUE-2 改造后用于补货阶段。

---

## 修复优先级建议

| 优先级 | 问题 | 触发条件 | 上线前必修 |
|--------|------|----------|-----------|
| P0 | ISSUE-1 分页中断 | 任一页超时 | ✅ |
| P0 | ISSUE-2 负责人兜底 | 一直存在 | ✅ |
| P1 | ISSUE-3 多SKU数量 | 多SKU采购单 | 建议 |
| P2 | ISSUE-4/5 行上限/定位 | 台账>3000行 | 视单量 |
| P3 | ISSUE-6~11 | — | 排期优化 |

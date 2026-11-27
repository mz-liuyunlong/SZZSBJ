# 国内仓组（批次看板 / 打包单审批 / 打包单（仓库））对齐 8088 · 接口数据源决策

- 调查日期：2026-11-02
- 调查人：PMC B 国内仓组 代码 AI（只读调查，未写代码、未调接口、未连服务器）
- 目标 method/path：`/api/pmc/domestic/*`、`/api/pmc/domestic/inbound-batches/*`、`/api/pmc/domestic/packing-approval/*`、`/api/pmc/domestic/packing-warehouse/*`（既有接口的字段扩展；本决策只列"新增或改变来源"的字段组）
- 业务用途：按 8088 DEMO（需求来源）补齐正式系统三个页签的业务字段与动作
- 接口总体状态：**BLOCKED_BY_OWNER_DECISION**（仅剩 §3 D1 中两处与正式仓库既有约束冲突、需刘云龙确认；Rocky 2026-11-02 已定 D2–D5）
- 是否包含 NEED_OWNER_DECISION：是
- 负责人批准状态：业务口径 Rocky 已定（2026-11-02）；技术确认待刘云龙
- 关联证据：见 §1
- 决策文件路径：`docs/data-sources/decisions/pmc-domestic-group-8088-alignment-decision.md`
- 后续接口 PRP：`PRPs/pmc-domestic-group-8088-alignment.md`
- 复用的既有决策（仍有效）：`pmc-domestic-inbound-board-decision.md`、`pmc-domestic-board-identity-decision.md`、`pmc-domestic-filter-options-decision.md`、`pmc-domestic-packing-approval-decision.md`、`pmc-domestic-packing-approval-m2-decision.md`、`pmc-packing-approval-allocation-arrival-decision.md`、`pmc-packing-warehouse-decision.md`、`pmc-packing-gtin-label-decision.md`；六状态候选方案 `PRPs/pmc-domestic-business-status.md`（BLOCKED）

## 1. 前置调查（§3.1）

| 前置调查项 | 证据位置与调查结论 |
|---|---|
| 旧页面 | 8088 `/domestic/`：`本地 DEMO 工作区 features/pmc-domestic-warehouse/drafts/demo-v7.html`（页面模板，`refresh_demo.py` 只替换数据块生成 demo-latest.html）；页签 = 批次看板 / 打包单（仓库）/ 打包单审批 / 双轨对账 / 通知设置。8088 新版 `/v2/#/pmc/domestic/batches`（`features/pmc-v2-app/src/pages/domestic/*`）只做了批次看板，口径照 demo-v7 |
| 旧 API | 8088 审批服务 `features/pmc-replenishment/review_server/server.py`：GET `/pmc-api/domestic/state`；POST `/pmc-api/domestic/event`，kind = approve / reject / link / void / diff_ok / test / boxes / done / customs / note / rebox 等，只追加事件 |
| 旧接口文件位置 | 同上；页面数据 `drafts/demo-data-daily.json` 由 `drafts/build_from_daily.py` 从每周拉数 `features/pmc-wfs-shipment/data/daily/<日>/` 生成 |
| 读取表 | 8088 不读库：读 daily CSV（批次明细、90 天库存流水、海外仓备货单 OWS、平台仓发货单 SP、WFS 货件、Listing、产品资料、采购单）+ 服务器 jsonl 事件 |
| 表写入方 | 8088：审批服务追加 jsonl；正式系统：`pmc_domestic` packing/warehouse service 写 ops/evt 表（迁移 0051–0053） |
| cron / 脚本 / 外部 API | 8088：每周拉数脚本（daily_pull）；箱规写领星由部署 AI 跑 `tools/boxspec_exec`（票据制）。正式系统：入库 W1/W3 同步 + 入库发布器 |
| 人工写库入口 | 两边都只有页面动作（口令 + 姓名 / 正式系统为登录 + 动作权限 + 口令） |
| 外部平台重新获取可能性 | 入库、批次、流水、OWS 可经领星只读接口重取；SP 发货单接口在 `API_CONTRACT_SOURCE_MAP.md` 标 DO_NOT_USE（见 D1） |
| 少量配置数据可行性 | 打包天数阈值 3 天、在仓超时 7 天 / 90%、延迟备注分类 8 项、箱型 A/B/C：均可作为代码常量或配置，不需建表 |
| 短期策略 | 已有数据源能支撑的字段先做（§2 可进入 PRP 的行）；依赖 SP / FIFO / 可发量的状态与发货字段等负责人决定 |
| 长期策略 | 按 `PRPs/pmc-domestic-business-status.md` 建 OWS / SP / 出库事件同步与分配事实后补齐六状态 |

## 2. 数据集分类

| 数据集或字段组 | 业务用途（8088 对应） | 当前权威来源 | 分类 | 短期策略 | 长期策略 | 退出条件或切换点 | 需负责人确认 |
|---|---|---|---|---|---|---|---|
| 入库批次 / 余额 / 到仓日期 / 在仓天数 | 批次看板主表 | 已发布 `mart_domestic_inbound_batch_board` | REBUILD_SYNC（复用） | 复用 | 复用 | — | 否 |
| 店铺 / ItemID / GTIN / 负责人 | 批次看板、审批 | 采购计划备注 + Listing + 产品资料（identity 决策） | REBUILD_SYNC（复用） | 复用 | 复用 | — | 否 |
| 系统打包单 PK、审批、分配、装箱、打包完成、报关、延迟备注 | 打包单 / 打包天数 / 延迟备注列 | 正式系统 ops / evt 表 | NEW_SYSTEM_OWNED（复用） | 批次看板只读投影（按 IB×SKU×店铺 关联 PK 分配） | 同 | — | 否 |
| 打包天数（审批日起算，已完成按完成日，超过阈值标红） | 批次看板 + 仓库页 | 系统审批时间 + 打包完成事件 | NEW_SYSTEM_OWNED | 后端计算；阈值读"设置"（D 组设置 AI 提供的读设置接口），读不到时用默认 3 天 | 同 | — | 否（Rocky 已定：3 天，可在设置里改） |
| 领星 OWS 号与系统 PK 两向关联、双轨对账、测试单、补录 | 审批页「系统打包单」段 / 双轨对账页签 | 8088 服务器事件；正式系统 M2 已删除 | ARCHIVE_ONLY（不做） | 不恢复 | 不恢复 | — | 否（Rocky 2026-11-02：不恢复） |
| 发出事件（6501 净出库、4107 旧流程）、发货单号、发出日期 | 批次看板状态 / 发货列 | 领星库存流水（W3 已同步） | REBUILD_SYNC | 按 8088 规则（§3.1）从流水计算 | 同；SP 列表接口若获准则补实际发货时间 | — | 是（D1-a：SP 列表接口） |
| 出库归属到入库批次（先进先出）、发货完成率、出仓周期、超时未发、六种状态 | 批次看板 | 由上面事件计算 | REBUILD_SYNC（派生 FACT） | 按 8088 规则（§3.1） | 同 | — | 是（D1-b：跨店铺先进先出） |
| 非发货出库（4201 其他出库 / 4106 调拨出库）+ 原因 | 批次看板状态 | 领星库存流水 | REBUILD_SYNC | 按 8088 规则（§3.1） | 同 | — | 否 |
| 已发出货物的店铺 / ItemID（按 WFS 货件实际去向） | 批次看板 ItemID 列"按货件" | 发货单 → WFS 货件 → 店铺 + GTIN → ItemID | REBUILD_SYNC | 复用 PMC-07 的领星 WFS 货件同步（合入 main 后） | 同 | WFS 分支合入 | 否 |
| 产品标签 PDF（50×30mm Code128 / 14 位 GTIN） | 仓库页「标签 PDF」 | 系统生成 | NEW_SYSTEM_OWNED | 按已提交的 `pmc-packing-gtin-label.md`（待确认） | 同 | 该 PRP 获批 | 是（已有 PRP） |
| 打包完成后写领星「更多箱规」 | 仓库页状态列 | 领星产品资料（写入） | NEW_SYSTEM_OWNED（写入记录）+ 领星受控写 | A 期只显示状态；写入列 B 期 | 正式系统内实现写入，按 AGENTS 红线逐单 / 逐批票据批准 | 受控写票据获批 | 否（Rocky 已定：要写回） |
| 通知设置（6 条规则开关 / 频率 / 对象） | 8088「通知设置」 | 8088 只是界面（不保存） | NEW_SYSTEM_OWNED（规则配置） | 不做（8088 本期推送全部关闭） | 系统级通知框架 | 负责人排期 | 否（移出本期） |

## 3. 决定记录与剩余确认

### 3.1 8088 的发货 / 出库归属规则（`build_from_daily.py`，原样摘录，作为本期口径）

1. **发出事件**：库存流水 `sub_type=6501`（发货单 WFS 出库），按（SKU, 发货单号）取净额（出库为正、"出库单撤销"回冲为负）；净额 ≤ 0 或发货单状态"已作废"的不算发出。2026-05 前旧流程 `4107`（备货单出库）同样计入。测试货件（PMC-TEST-）及其发货单排除。
2. **发出日期**：优先发货单 `delivery_time`，没有则用流水 `opt_time`。
3. **非发货出库**：`4201` 其他出库、`4106` 调拨出库，带流水备注作原因；`3401/1601` 换标一出一进净 0 不算；`2702` 手动移除入库与采购批次无关，不算。不计入发货完成率。
4. **归属到入库批次**：同一 SKU 的所有入库行按到仓日期从早到晚排；发出事件和非发货出库按日期合并排队，**先进先出**冲减各行余额；早于该入库行到仓日期的事件跳过（属于窗口外的老库存）。
5. **分母**：可发 = 质检良品数（流水 `2801 product_good_num`），没有则用到货数；不良 = 到货 − 良品。
6. **发货完成率** = 已发出 ÷ 可发；**发出日期**取累计发出达到可发 90% 的那张发货单；**出仓周期** = 该日期 − 到仓日期。
7. **状态**：有 90% 发出日期 → 已发出；余额 ≤ 0 且只有非发货出库 → 非发货出库；余额 ≤ 0 → 已发出；（打包相关以本系统 PK 为准）；其余 → 在库。批次快照余额低于流水推算时按快照，记"非发货出库（盘亏 / 未识别出库）"；批次快照里没有、流水也无出库的按流水余额算在库（标"流水余额"）。
8. **超时未发** = 非已发出 / 非发货出库，且在仓 > 7 自然日，且完成率 < 90%。
9. **已发出货物的店铺 / ItemID** 以 WFS 货件实际去向为准（发货单 → 货件 → 店铺 + GTIN → ItemID），采购单 / 入库单上的店铺只做参考（Rocky 2026-09-29）。
10. 数据窗口：流水只有 90 天；更早但仍有余额的批次按批次明细补行。

### 3.2 决定（Rocky 2026-11-02）

- **D1 发货 / 出库归属**：按 §3.1 的 8088 规则。剩两处与正式仓库已有约束冲突，需刘云龙确认：
  - **D1-a**：发货单列表接口（LX-C99E2D00C76D）在 `API_CONTRACT_SOURCE_MAP.md` 标 DO_NOT_USE。8088 只用它取"已作废"状态和实际发货时间。建议：作废靠流水净额已能识别（撤销回冲），发出日期先用流水 `opt_time`，SP 接口不接；若云龙同意解禁再补实际发货时间。
  - **D1-b**：入库 M1 定过"禁止跨店先进先出"，8088 是按 SKU 跨店铺先进先出。建议：按 8088 做，结果标"估算（先进先出）"，已发出行的店铺仍以 WFS 货件去向为准。
- **D2 PK ↔ OWS 关联、双轨对账**：不恢复。
- **D3 操作人**：不限定吴贤玲；8443 上线后由权限设置管理（谁有动作权限谁能操作）。
- **D4 箱规写回领星**：要写。列入 B 期，写入按领星受控写红线逐单 / 逐批票据批准。
- **D5 打包天数阈值**：3 天，可在"设置"里改。本模块读 D 组设置接口，读不到用默认 3。

## 4. 数据血缘（新增字段）

| 接口字段 | 数据集 | 源 | 转换 | 时区 | 新鲜度 | 写入方 |
|---|---|---|---|---|---|---|
| `packing_days` | 系统审批/完成事件 | ops 订单 approved_at、evt pack_complete | 完成？完成日−审批日：业务日−审批日；已发出为 null | 北京业务日（与入库业务日一致） | 实时 | 打包服务 |
| `packing_days_over` | 同上 | 同上 | packing_days > 3 | — | 实时 | — |
| `delay_note`（最新一条 + 条数） | 仓库延迟备注事件 | `POST /packing-warehouse/orders/{id}/notes` 事件 | 按 PK 取最新；"已处理"= 解除 | UTC 存、北京显示 | 实时 | 仓库页 |
| `pk_refs[]` | 分配表 | PK × IB × SKU × 店铺 | 批次行关联有效 PK（排除 voided） | — | 实时 | 审批服务 |

## 5. 风险检查

- [x] 每个字段组一种分类，无 MIXED。
- [ ] 不存在未解决 NEED_OWNER_DECISION —— **仅剩 D1-a / D1-b 待刘云龙确认**。
- [x] 不在 API route 实时拉外部平台；不读旧库；不读 8088 JSON 作为生产事实。
- [x] 不默认双写；8088 jsonl 与正式系统数据不互导（如需迁移另出 MIGRATE_ONCE 决策）。

# WFS 到货提醒系统设计（v1.1，决策已确认）

日期：2026-07-14　状态：需求方已确认 4 项决策，可进入实施　作者：AI 工程师
v1.1 变更：R3 改为"每天检测、持续提醒直到有广告"；R2b 并入 R2a 简化口径；同步每日 1 次；接收人=负责人私信+群汇总。

## 一、需求

| # | 提醒 | 触发 |
|---|---|---|
| R1 | 货件到仓提醒 | WFS 货件状态进入 RECEIVING_IN_PROGRESS（开始接收）；CLOSED 时补发接收完成（含签收/损坏数量） |
| R2 | WFS 库存 0→非0 / 上架可售提醒（已合并，简化口径） | 同商品 WFS 可售库存从 0 变为 >0，即视为上架可售；listing 在线状态核验留二期 |
| R3 | ~~无广告每日私信提醒~~（**2026-07-15 需求方决定停用**：通知量过大） | 代码保留但默认关闭（`WFS_NO_ADS_DAILY_ENABLED=1` 可恢复）；"未创建广告"由 R4 升级覆盖，"创建了未投放"由 R5/R6 广告组静默覆盖 |

## 二、数据源（已核对 API 文档）

`POST /cepf/warehouse/api/openApi/queryWFSCargoPage`（令牌桶 10，分页上限 200）

- 增量参数：`cargo_update_time_ge/le`（平台更新时间）、`update_time_ge/le`；全量参数：`start_time/end_time`（创建时间）、`cargo_status_list`
- 关键字段：`records.id`（货件id）、`cargo_code`、`in_bound_order_id`、`store_id/store_name`、`status(0-4)/status_name/cargo_status`、`cargo_sync_status`、五个状态时间戳 `to_pending_time / to_await_time / to_receive_time / to_closed_time / to_cancelled_time`、`update_date`
- 商品明细 `cargo_good_list[]`：`msku / sku / gtin / product_name / declare_num（申报量）/ shipments_num（已发）/ received_num（签收）/ dameged_qty（损坏，注意 API 拼写）`
- ✅ 2026-07-14 probe 实测（100 货件 / 301 明细，total=413）定稿格式：
  - `to_*_time` 全部为 **epoch 毫秒字符串**，未到达该状态时为字符串 `"0"`（解析函数必须把 "0"/空 视为 NULL）
  - 数量字段（declare/shipments/received/dameged）全部为**字符串数字**；`total` 也是字符串
  - `status` 为 number（0-4 全部实测出现）；`cargo_sync_status` 中文（已申报/已发货/入库中/已完成/已取消）
  - 实测新增字段 `system_update_date`（datetime 字符串）——比 `update_date` 更适合做增量锚点，入库保存
  - `shipping_list_codes` 可为 null

R2/R3 复用现有 FACT：`fact_inventory_daily.wfs_available_stock`（T-2）、`fact_ads_product_daily.ad_spend`（T-2）、`dim_product.owner`。

## 三、架构（严格走分层：数据源→RAW→FACT→EVENT→通知）

```
领星 queryWFSCargoPage
   → raw_lingxing_api（每批响应先留痕，RAW 失败不得写下游）
   → fact_wfs_shipment / fact_wfs_shipment_item（upsert 快照）
   → 事件检测 → EVENT 层（biz_event 或新表，见 §五）
   → arrivalNotify.ts → feishuNotify 统一发送（批B规范）
```

前端如后续要看货件列表，只读 FACT，不直查 RAW。

## 四、新表设计（SQL 草案：sql/010_wfs_shipment_tables.sql）

### fact_wfs_shipment（货件头快照）

| 字段 | 类型 | 说明 |
|---|---|---|
| platform | VARCHAR(20) 默认 'walmart' | |
| store_id / store_name | VARCHAR | |
| shipment_id | VARCHAR(64) | = records.id |
| cargo_code / inbound_order_id | VARCHAR(128) | |
| status | TINYINT | 0-4 |
| status_name / cargo_status / cargo_sync_status | VARCHAR | |
| cargo_create_date / to_pending_time / to_await_time / to_receive_time / to_closed_time / to_cancelled_time / update_date | DATETIME NULL | 解析失败置 NULL 并计数告警，禁止写非法值（遵守 2026-07-11 dateStrings 规约） |
| source_raw_id | BIGINT | raw_lingxing_api 留痕 id |
| created_at / updated_at | | |

唯一键：`uq_wfs_shipment(platform, store_id, shipment_id)`

### fact_wfs_shipment_item（货件商品行）

shipment 同键 + `msku/sku/gtin/product_name/declare_num/shipments_num/received_num/damaged_qty`（数量经安全转数，禁止 NaN/负值直写）
唯一键：`uq_wfs_shipment_item(platform, store_id, shipment_id, msku(64))`

无人工字段，纯 upsert，不删历史（CANCELLED 也保留）。

## 五、EVENT 层与幂等

事件类型（biz_key 保证幂等，重复检测不重复通报）：

| event_type | biz_key | 触发判定 |
|---|---|---|
| wfs_shipment_receiving | shipment_id | DB 旧 status<2 → 新 status=2（或首见即 2） |
| wfs_shipment_closed | shipment_id | → status=3，payload 带 declared/received/damaged 汇总 |
| wfs_stock_first_available | store_id+item_id+msku+日期 | fact_inventory_daily 昨日 wfs=0（或无记录）→ 今日 wfs>0（R2 合并口径，即"上架可售"） |
| wfs_received_no_ads | shipment_id+msku+**检测日** | 持续型：接收完成（to_closed_time=D）后每天生成当日事件，条件=接收日起至最新可用广告数据日，该商品 ad_spend 与 impressions 累计均为 0；出现广告后停止生成（resolved）。biz_key 含检测日 → 每天恰好提醒一次、幂等重跑不重复 |

R3 持续型补充规则：
- 数据可用性护栏：广告 FACT 为 T-2，检测日 X 只能看到 ≤X-2 的数据；只有当 X-2 ≥ D（至少覆盖接收当日）才开始判定，实际首次提醒 ≈ D+2~D+3，此为数据链路物理下限，文案中注明"数据截至 YYYY-MM-DD"。
- 停止条件：①接收日后任一日 ad_spend>0 或 impressions>0；②商品被人工归档（product_management_status=archived / 人工生命周期清货期可配置豁免）；③货件 CANCELLED。
- 文案带压力递进：`已接收 N 天仍无广告（第 M 次提醒）`，便于负责人感知拖延时长。

落表方案（2026-07-14 定案）：**采用专表 `event_arrival_notify`**。已核对生产 `biz_event` 真实结构：其唯一键为 `uq_biz_event(event_date, event_type, source_key(200))` **含 event_date**，跨日一次性事件（如"货件开始接收只报一次"）无法靠它幂等，且无通报回执列；不改 biz_event 结构，专表与 `event_product_owner_clear` 先例一致。通报状态列（pending/notified/failed + notified_at）由通知脚本回写——只写事件自身状态，不碰 RAW/FACT。

### R4 升级通报（2026-07-14 需求方追加，绩效口径）

- 触发：商品 WFS 库存 0→非0（上架可售日 D，取库存快照日期）后，**第 3 天仍无广告投放**（可售日起广告花费与曝光累计均为 0）。
- 口径定稿（2026-07-15 二次修订，需求方确认）：**升级扣绩效仅针对"未创建广告"**。判定依据：生产核验确认领星广告报表每天为已存在广告组输出全量行（含0值行），因此可售日起该商品在 `fact_ads_product_daily` **无任何行=未创建广告**（升级），**有行即使全0=已创建**（不升级不扣绩效，由 R3 日常提醒 + R5/R6 广告组静默覆盖"创建了但未投放"）。无需新接广告活动列表API。
- 动作：①发到通报群（绩效考核口径文案，@负责人纯文本）②同步指定升级接收人（默认黄少如，经花名册解析，环境变量 `FEISHU_ARRIVAL_ESCALATION_USERS` 配置姓名，禁止硬编码 open_id）③负责人私信抄送。
- 幂等：`wfs_no_ads_escalation`，biz_key=store:item:msku:可售日，**一次性**（升级只报一次；日常持续提醒仍由 R3 每天进行直到有广告）。
- 口径统一：R3/R4 的无广告判定统一锚定"上架可售日 D"（v1.1 的货件 CLOSED 锚点废弃——可售才具备开广告条件，且库存事件自带 item_id 免去 msku 映射歧义）。R1 货件到仓/完成通报保持货件锚点不变。
- T-2 说明：广告与库存 FACT 均 T-2，"第 3 天"按数据覆盖天数计算（可售日起 ≥3 个数据日无广告即升级），实际升级发出约在可售后第 5 个自然日，文案标注"数据截至"日期。
- 防轰炸上限：持续提醒最长 `WFS_NO_ADS_MAX_DAYS`（默认 30 数据日），超限后停止日常提醒（升级通报不受影响），死品走人工归档停止。
- 库存剔除信号（2026-07-15 需求方追加，R3/R4/R5/R6 通用）：商品/广告组关联商品**当前总可售库存（WFS+非WFS）为 0** 时不提醒——缺货状态下无广告属正常。R3/R4 按最新库存快照逐锚点核查；R5/R6 广告组级按关联商品合计核查（任一商品有库存则仍提醒）。无库存数据时保守放行不剔除。

### R5/R6 广告组静默提醒（2026-07-15 需求方追加，归入广告通报）

- R5：广告组连续 **5** 个数据日 花费=0 且 曝光=0 → 提醒（疑似停投/预算耗尽/拒审）
- R6：广告组连续 **7** 个数据日 花费=0（曝光可>0）→ 提醒（出价/预算问题）
- 数据源：`fact_ads_product_daily`（含 campaign_id/ad_group_id/item_id），广告组某日无行按 0 处理；
  广告组"存在"锚点 = 近 30 个数据日内出现过行（报表型数据无"活动创建"字段，与 R4 同为投放代理口径）。
- 幂等：biz_key = store:campaign:ad_group:连续段起始日 + 阈值类型，同一连续段各提醒一次。
- 规则纯函数已实现：`src/notifyRules/adGroupSilenceRule.ts`；收敛参数（2026-07-15 二轮 dry-run 230→74 校准）：新鲜度上限 `AD_SILENCE_FRESH_GRACE=5`、活跃紧邻窗口 `AD_SILENCE_ACTIVITY_WINDOW=7`。
- **发送通道分离（2026-07-15 需求方决定）**：广告组静默与到货通报是两件事，禁止共用 14:00 发送。`arrivalNotify.ts` 已收窄为 `wfs_*` 事件白名单（到货专线）；`ad_group_*` 事件由 20:45 任务持续生成留痕但**暂停发送**，待专属发送方案（独立脚本+独立时间）确定后开闸，开闸前必须先将历史积压 pending 标记 skipped。

## 六、脚本与调度（cron 均需你明确授权后才加）

| 脚本 | 职责 | 调度（已确认每日 1 次同步） |
|---|---|---|
| src/probeWfsCargo.ts | 一次性只读探测真实响应格式 | 手动 |
| src/syncWfsShipments.ts | API→RAW→FACT upsert→状态迁移事件（R1） | 每日 08:20 |
| src/buildArrivalEvents.ts | R2/R3 检测（依赖 T-2 FACT，需在 16:45 主链之后取最新快照） | 每日 20:40（状态表 20:30 之后） |
| src/arrivalNotify.ts | 读未通报事件→feishuNotify→回写 notified | 每日 08:40（发送当日 R1 + 前晚 R2/R3；避开 09:00/10:00 现有通知高峰） |

全部脚本：默认 dry-run，`--confirm-write` 写库，`--send` 真发，`--test-send` 只进测试群且输出 `NOTIFY_TEST_SENT=1`（批B规范）；接入 `feishuNotify.ts` 节流与重试；接收人 = dim_product.owner 经花名册（`dim_feishu_member` active）解析，匹配不到进"未匹配"汇总，禁止猜测发送；日志不落 token/webhook/chat_id。

负责人匹配注意：货件明细只有 msku 无 item_id，按 `store_id + msku` 查 `dim_product` 唯一命中才取 owner，多命中标 ambiguous 进汇总，不按 item 级猜测。

## 七、已确认决策（需求方 2026-07-14 拍板）

1. **接收人**：负责人私信 + 群汇总双通道；未匹配负责人的事件进群兜底。群 chat_id 走环境变量（建议 `FEISHU_ARRIVAL_CHAT_ID`），禁止硬编码。
2. **R1 同步频率**：每日 1 次（08:20），当日下午到仓的次日早提醒，需求方接受。
3. **R3 口径**：持续型——接收次日起每天检测、每天提醒，直到出现广告（ad_spend>0 或 impressions>0）为止；受 T-2 限制实际首提醒 ≈ 接收后 2~3 天。CS 测品不豁免。
4. **R2 口径**：简化版，WFS 0→非0 即"上架可售"，与库存提醒合并为一条；listing 在线核验留二期。
5. cron 新增 3 条（08:20 / 20:40 / 08:40）待部署前再走一次正式授权。

## 八、实施顺序与验收

1. probe 真实响应（只读）→ 修订本设计的字段/格式假设
2. 建表 SQL 评审（核对主键/唯一键）→ 执行
3. syncWfsShipments + 单测（纯函数：状态迁移检测、时间戳解析、数量安全转换）→ dry-run 验收 → --confirm-write 首次全量回填（start_time 取近 90 天）
4. buildArrivalEvents + 单测（0→非0 判定、无广告窗口判定、幂等键）
5. arrivalNotify --test-send 进测试群验收（exit 0 + NOTIFY_TEST_SENT=1）
6. cron 申请与上线，观察 3 天事件量与误报，更新 context 四件套

回滚：新表/新脚本均为增量隔离，回滚 = 停 cron + 保留数据，不影响现有任何链路。

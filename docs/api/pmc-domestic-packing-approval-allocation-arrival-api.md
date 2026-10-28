# 打包单审批接口：WFS 准入、比例预填与到货信息

日期：2026-10-28。状态：代码已修改，验收暂停；未部署，未完成真实本地数据库联调。

本文件覆盖早期 M1/M2 文档中“履约类型允许 0/1”“多 ItemID 只能手填”“到货状态固定 unknown”的说明。未调整的端点、权限、幂等与事务约束继续沿用原接口。数据源决策见 [数据源决策](../data-sources/decisions/pmc-packing-approval-allocation-arrival-decision.md)，范围见 [PRP](../../PRPs/pmc-packing-approval-allocation-arrival.md)。

## 1. 页面与接口对应

页面：`/#/pmc/domestic/packing-approval`。接口前缀：`/api/pmc/domestic/packing-approval`。

| 方法及路径（相对前缀） | 页面用途 | 本轮变化 |
|---|---|---|
| GET /pending | 待审批表格 | 增加比例建议、到货数量、分批信息和 WFS 阻断原因 |
| GET /pending/summary | 待审、受阻、超时、已审统计 | 使用与列表相同的到货和分批筛选 |
| GET /filter-options | 店铺筛选选项 | 保留既有选项来源，不增加角色或店铺授权 |
| GET /pending/{candidate_id}/edit-options | 修改弹窗目标店铺／ItemID | 同账号、同 SKU、全店铺范围内仅返回 PUBLISHED 且履约类型 1 的 Listing |
| POST /pending/{candidate_id}/approve | 提交最终人工确认数量 | 严格检查目标履约类型 1，继续检查版本与共享库存 |
| POST /pending/{candidate_id}/reject | 驳回 | 保留现有行为，受阻不会自动变为驳回 |
| GET /manual/sources | 手工申请选择入库来源 | 使用相同候选投影和查询模型 |
| GET /manual/{board_id}/options | 手工申请选择目标商品 | 目标同样要求履约类型 1 |
| POST /manual | 提交手工待审申请 | 复用最终目标校验；不因申请而发 PK 或分配库存 |
| GET /orders、/orders/{order_id} | 审批记录、详情 | 快照兼容新增字段；旧记录不补写、不重算 |
| GET /orders/{order_id}/events | 审计事件 | 原权限和返回结构不变 |

所有接口返回统一 `{ success, data, error, meta, request_id }`。本轮没有增加接口路径，也没有引入外部平台请求或 Celery 任务。

## 2. 列表、统计与历史查询参数

| 参数 | 类型／默认值 | 页面含义 |
|---|---|---|
| store_id | 可重复 string，最多 50 项 | 店铺筛选 |
| overdue | all / overdue / not_overdue；默认 all | 审批超时筛选 |
| arrival | all / full / partial / none / unknown；默认 all | 到货情况 |
| split_arrival | all / yes / no / unknown；默认 all | **独立的分批到货筛选**；yes 已观测多批，no 单批且已到齐并有完整历史覆盖，unknown 无法确认 |
| keyword | string，最长 200 | 入库单、SKU、采购单、ItemID、MSKU 搜索 |
| created_from、created_to | date，可空 | 来源入库到仓日期范围；开始不得晚于结束 |
| page | int，默认 1，最小 1 | 页码；仅分页列表 |
| page_size | int，默认 50，范围 1–200 | 每页条数；仅分页列表 |
| sort | created_desc / created_asc，默认 created_desc | 列表排序；统计不传 |

前端字段 `splitArrival` 映射后端 `split_arrival`。列表响应 `data={items: Candidate[], total: int}`；统计响应 `data={pending, overdue, blocked, approved, rejected}`。历史按保存的快照筛选，不会用最新采购备注改写历史结果。

## 3. 与页面对应的响应字段

以下为本轮改变或新增的 Candidate 字段；Candidate 的身份、来源、库存、报关、日期等既有字段继续返回。

| 字段 | 类型 | 对应页面及口径 |
|---|---|---|
| arrival_purchased | int / null | 到货情况第一项“采购量”；账号＋采购单＋SKU 下，按原 order_item_id 去重后汇总采购 DWD quantity_real，不能将计划拆行重复累加 |
| arrival_received | int / null | 第二项“已到量”；同账号、采购单、原明细 ID 对应的成功同步最新 ODS payload_json.quantity_entry（到货入库量）之和，**不是 quantity_receive、库存余额或不同采集版本累加**；缺任一原明细已到量则 null |
| arrival_pending | int / null | 第三项“未到量”；相同原明细 quantity_receive（待到货量）之和，直接使用源计数，不按采购量减已到量推算；缺任一未到量则 null |
| arrival_status | full / partial / none / unknown | 采购／已到／未到均有效时：待到为0且已到≥采购为 full；待到＞0且0＜已到＜采购为 partial；待到＞0且已到=0＜采购为 none；缺失或矛盾组合为 unknown |
| arrival_source_refs | string[] | 本次计数引用的采购明细 ODS UUID，供快照／追溯；不包含密钥或原始完整响应 |
| split_arrival | bool / null | 分批到货标签：true 已观测分批；false 有完整覆盖的单批已到齐；null 未知 |
| arrival_batch_count | int / null | 当前发布范围内，同账号、惠州仓、采购单＋SKU 关联的不同入库单数量；跨店铺展示行去重，包含已无余额的已发布入库单 |
| arrival_batch_index | int / null | 当前入库单按到仓日期、入库单号排序的位置，从 1 开始；缺日期／不在观测集时 null |
| default_quantity | int / null | 表格“建议备货”及修改弹窗初值；单身份沿用可用量，多身份按计划比例建议；无可靠比例为 null；整箱不足时可能为 0，须人工确认后才能提交正数量 |
| available_quantity | int / null | 表格“可用库存”；所有同源候选共享上限，不能逐行相加 |
| quantity_suggestion | object / null | 建议计算说明，结构见下表；旧审批快照缺字段时默认 null |
| can_approve | bool | 商品、库存等校验均满足时为 true；建议数量可编辑，不代表自动审批 |
| blocked_reasons | string[] | 待补资料具体原因；新增 WFS_NOT_CONVERTED，显示“尚未完成 WFS 转换” |

### quantity_suggestion 对象

| 字段 | 类型 | 含义 |
|---|---|---|
| rule | single / plan_ratio / manual | 单身份默认／采购计划比例／人工填写 |
| plan_weights | object<string, number> | ItemID 对应计划权重；允许按关联份额产生小数，仅供建议，不是金额或最终审批数量 |
| box_pcs | int / null | 同账号＋SKU 唯一有效产品标准资料的每箱件数；缺失、不唯一、非正整数均不使用 |
| tail_quantity | int / null | 源可分配量不足一整箱的余数；无建议依据时 null。尾差不是已自动追加到某行的数量 |
| notes | string[] | 比例依据不足、未按箱规取整、尾差待人工确认等提示 |
| source_refs | string[] | 计划 ODS UUID、产品资料 source_snapshot_id；随既有审批 JSON 快照保存 |

数量例：可分配 103 件、A:B 计划比例 60:40、箱规 10 件，建议 A=60、B=40，尾差 3 件提示人工确认。人工可以把建议改为其他正整数，所有审批仍受实际剩余库存约束。先审批 A 后，不把 A 已占用的计划份额重新分给 B。

## 4. 取数与未知值规则

1. 入库来源为 `gov_domestic_board_publications` 当前 `published` 版本及 `mart_domestic_inbound_batch_board`，仓库固定 16168。默认待审仍要求正余额。
2. ItemID 沿用批次采购备注＋Listing 解析。GET 会读取新系统本地采购 ODS，不是只读已发布 MART；不读取旧库、不实时调用领星。
3. 采购比例通过 DWD 采购行关联 plan_sn，再读取成功同步的采购计划 quantity_plan 与备注。同店同 SKU 的 Listing 验证后，计划恰能确定一个 ItemID 才形成权重；候选缺权重、计划缺失或歧义时不等分猜测。
4. 一个计划关联多采购行时按 DWD 已分配份额计算权重，避免重复计整份计划。整箱使用最大余数分配，不足一箱的尾差留给人工；箱规不可用时按整数件数建议并提示。
5. 到货计数要求 DWD 和最新成功 ODS 的采购明细数量一致；缺明细、明细已删除、SKU 不一致或数量版本不一致时保留未知。已到与待到字段分别汇总；字段缺失、布尔、负数或非整数时仅对应数量为 null，状态为 unknown，不用差值补值。超收事实保留，不把已到量截断为采购量。`quantity_entry` 复用原同步已保存的采购明细 JSON，没有新物理列。
6. 分批判断独立于采购是否到齐，只说明当前发布范围的观测结果，不承诺完整领星历史。一张入库单、历史覆盖不足时，不能断言“不是分批”。
7. ItemID、GTIN、MSKU 继续按目标 Listing 校验。履约类型 0 可以展示为受阻候选；**只有 1 才能审批**。跨店修改仍只限同账号同 SKU，不改变原入库库存来源。

## 5. 审批写请求与返回

本轮不新增命令字段。approve body：

| 字段 | 类型／要求 |
|---|---|
| source_account_ref | string，必填；必须在可信数据范围内 |
| warehouse_id | 固定 string `16168`，默认该值 |
| candidate_version | 必填 64 位摘要；过期候选拒绝 |
| idempotency_key | UUID，必填；重试保持同一键和请求 |
| qty | 严格整数 1–1000000，必填；人工最终确认数量，不超过当前可用量 |
| customs | default / declare / skip，默认 default |
| rwh | 可选 string，最多 128；沿用既有仓库备注规则 |
| target_store_id、target_item_id | 可选 string；修改身份时使用，同账号同 SKU |
| listing_version | 修改目标时必填 64 位摘要；已提供时也验证版本 |
| edit_reason | 修改身份时去空白后至少 2 字，最多 500 |
| operator_name、passcode | 保留现有操作身份／口令流程；不得记录或回显 passcode |

客户端不能提交 GTIN、MSKU、PK、actor、订单状态或 is_test 等服务端结果字段。审批返回沿用 OrderRead：id、candidate_id、pk、status、qty、version、is_test、customs_value/src、rwh、actor_uid、note、created_at、snapshot、source_snapshot、voided_at、void_note。qty 是人工最终数量；snapshot/source_snapshot 保存 Candidate 建议与来源信息。

权限、幂等、库存锁、订单＋分配＋快照＋事件单事务不变。本轮未改变既有 APP_ENV 数据库写入策略；仅授权本地开发，不代表允许生产执行。

## 6. 错误和兼容性

- 401 未认证，403 权限／账号范围／目标环境不允许，404 候选或订单不存在，422 参数非法，409 来源、Listing、状态或库存冲突。
- 待审 `WFS_NOT_CONVERTED` 是 blocked 原因，不是“已驳回”。审批目标不在有效可选范围时可能返回 `LISTING_MISSING_OR_AMBIGUOUS`；最终校验也防御履约类型变化。
- 新字段有默认值，旧审批 JSON 快照不回填。真实数据库没有新增物理字段、表或迁移。已保存旧快照的到货情况继续保持原值。
- 当前未完成真实数据联调；测试于负责人要求后暂停，不能将已编写的测试文件当成全部验收通过。

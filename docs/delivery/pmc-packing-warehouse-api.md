# 仓库打包本地接口

前缀 `/api/pmc/domestic/packing-warehouse`；统一 envelope，登录用户为操作人，所有读写均校验来源账号范围。尚未接入领星写入或货件。

| 方法 / 路径 | 用途 / 权限动作 |
|---|---|
| GET /orders | 已审批PK分页；店铺、状态、关键字、审批日期、排序 |
| GET /orders/summary | 同条件待打包/已打包数量 |
| GET /filter-options | 已审批单真实店铺选项 |
| GET /orders/{id} | 最新单据及版本 |
| GET /orders/{id}/events | 修改前后及登录操作人审计分页 |
| POST /orders/{id}/boxes | 暂存；packing-boxes-save |
| POST /orders/{id}/done | 单次完成；packing-done |
| POST /orders/{id}/rebox | 已完成单改装箱；packing-rebox |
| POST /orders/{id}/supplemental-inbound | 中台登记IB；packing-supplement-ib |
| POST /orders/{id}/supplemental-sync | 中台同步核验；packing-supplement-sync |
| POST /orders/{id}/unpacked | 中台未装处置；packing-unpacked-dispose |
| POST /orders/{id}/customs | 独立授权改报关；packing-customs |
| POST /orders/{id}/notes | 中台延迟备注；packing-note |

动作权限前缀 `action:pmc:domestic-warehouse-board:`。仓库仅授予页面查看、boxes-save、done、rebox；中台处置/备注单独授予，不使用共享口令或用户输入姓名。

写入必带 `source_account_ref`、`expected_version`、UUID `idempotency_key`；相同请求重试返回原结果，不同操作人或payload复用键409。done需 `expected_box_version`、`requirement_version`；少装须 `reason_category`（shortage/damage/box_capacity/other），other须 `reason`。包装不足须 `package`：长宽高cm、毛重g、可选净重g。rebox需reason、expected_box_version、lines；如少装另须reason_category。unpacked传action=resend/void，void必填reason。

| 返回字段 | 页面中文含义 |
|---|---|
| approved_quantity | 原审批数量Q |
| box_set.total_qty | 实际装箱T |
| box_set.variance_qty | T-Q，负数未装、正数超出 |
| variance_case.quantity | 未装/超出件数 |
| variance_case.state | pending待中台、released已回池、voided作废未装、resolved已解决 |
| arrival_date / inbound_date | 到仓日期，采用入库业务日 |
| received_dates | 可靠关联的实际收货日，无证据为空 |
| stock_balance | 来源入库单最近快照余额，不是跨入库单可多装余量 |
| balance_observed_at | 最近库存观察时间 |
| product_requirement | 资料完整/缺失/未知及版本令牌 |
| completed_at / completed_by | 首次完成时间/登录操作人，改装箱保留 |

多装余量足须confirm_extra=true；不足须reason并返回成功接受但command_outcome=blocked，未完成。登记补单传inbound_order_sn；同步无额外请求字段。真实同步未配置时明确返回variance_case.last_sync_code=LINGXING_SYNC_NOT_CONFIGURED。unpacked回池仅修改本单有效分配qty，不改原审批Q；审计前后记录与异常证据保留。void保留排除占用，不写领星库存。


## 多装扩展契约

GET /orders支持exception=overpack筛选blocked异常；summary新增overpack_blocked/unpacked_pending，原分页、筛选与信封不变。每个POST仍要求expected_version、来源账号与幂等UUID。补IB格式为IB开头、长度<=64；动作与登录账号范围独立校验。同步不接受客户端提交库存证据或发布版本。

| 字段 | 中文含义 |
|---|---|
| extra_available | 同SKU跨入库单可额外占用数量，已扣本单原审批；操作弹窗重读并在命令内再校验 |
| extra_publication_id | 预算使用的当前发布版本 |
| extra_allocations[] | 额外占用来源：入库单、数量、源发布及源MART行；同时进入不可变事件快照 |
| command_outcome | saved已保存 / completed已完成 / blocked阻塞已记录 / ready已解除需人工确认 |
| variance_case.gap_qty | 当前缺口数量 |
| variance_case.last_sync_code | MATCHED校验通过、IB_QUANTITY_INSUFFICIENT入库不足、STOCK_STILL_INSUFFICIENT余量仍不足、IB_SKU_WAREHOUSE_MISMATCH不匹配、SYNC_EVIDENCE_STALE旧证据、LINGXING_SYNC_NOT_CONFIGURED未配置等 |
| variance_case.last_sync_gap | 最近核验仍差件数 |
| variance_case.notification_state | 本地待配置/已取消的通知状态，无发送器 |
| variance_case.proposed_lines | 已完成PK因改装箱缺口保存的提议；原实装冻结，获准后再提交rebox |

同步provider默认None；真实网络适配未接入。mock只在回滚验收app中依赖覆盖，不存在HTTP开关或证据上传绕过。当前接口不触发Celery或外部消息，未配置/失败也审计；未来真实网络采集须在命令事务外通过治理同步发布。

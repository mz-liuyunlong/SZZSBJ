# 国内仓打包单审批 API（本地 M1）

2026-10-20；状态testing、本地已实现，不代表已部署或允许生产审批。来源决策/PRP：pmc-domestic-packing-approval-decision.md、pmc-domestic-packing-approval-backend.md。复用统一SuccessEnvelope，OpenAPI已注册，数据中心API目录同步。

## 范围和权限
前缀`/api/pmc/domestic/packing-approval`。所有接口需登录及可信source-account scope。GET需`page:pmc:domestic-warehouse-board:view`；通过需`action:pmc:domestic-warehouse-board:packing-approve`；驳回需`action:pmc:domestic-warehouse-board:packing-reject`。页面权限不能替代动作权限，已有角色未自动授予动作。来源仓库固定惠州16168。任何POST还校验APP_ENV及真实Engine连接目标，只允许本地szzsbj_dev（测试环境仅szzsbj_test）；均为is_test=true，不创建OWS、不触发Celery、不调用领星或Walmart。

## 端点
| 方法 | 路径 | 返回 |
|---|---|---|
| GET | /pending | items/total；当前尚未决定的候选，含阻断原因 |
| GET | /pending/summary | pending、overdue、blocked、approved、rejected |
| GET | /filter-options | stores(value,label)、local_verification_only=true、manual_enabled=false |
| GET | /orders | 已通过/驳回记录items/total，按审批时间倒序 |
| GET | /orders/{order_id} | 决策详情及不可变来源快照 |
| GET | /orders/{order_id}/events | items，事件ID/动作/actor_uid/order_version/occurred_at/note |
| POST | /pending/{candidate_id}/approve | 本地订单详情，成功200 |
| POST | /pending/{candidate_id}/reject | 驳回详情，成功200，无PK/分配 |

## 查询参数
pending/orders：page>=1，page_size=50且<=200，sort=created_desc/created_asc。pending按来源到仓日期排序，orders按审批时间倒序。pending/summary/orders共享：store_id重复参数最多50项，overdue=all/overdue/not_overdue，arrival=all/full/partial/none/unknown，keyword<=200，created_from/to为到仓业务日边界，开始不得大于结束。arrival未知不落入none，当前收货标准化不完整因此full/partial/none筛选为空。keyword匹配入库单/SKU/ItemID/MSKU/采购单；不承诺按PK搜索。summary中approved/rejected与候选采用同一来源筛选，不以PK创建时间代替到仓日。待审包括blocked，blocked为待审子集；超时为到仓日距当前北京日>=1，不是批次7日未发规则。

## 候选字段字典
| 字段 | 类型/空值 | 来源与含义 |
|---|---|---|
| id | UUID | 账号/仓库/稳定board_id/ItemID的确定性候选身份；SKU和店铺已含在board_id中 |
| candidate_version | 64位摘要 | 当前来源发布、库存分配及Listing指纹，时间规范UTC；非OPS订单version |
| source_account_ref、warehouse_id | string | 可信账号与惠州仓标识；不得由用户扩展来源范围 |
| publication_id、board_id | UUID | 当前MART复合来源主键；审批保留历史引用 |
| inbound_order_sn、sku | string | 入库单与SKU，不使用空收货DWD替代 |
| product_name、store_id/name | string/null | 发布资料及DIM，未知归属保留null |
| item_id、gtin、msku | string/null | 同账号+店铺+SKU的PUBLISHED且履约类型0/1的DIM记录；不转数字丢前导零 |
| purchase_order_sns | string[] | 入库来源采购关联，不猜测 |
| arrival_purchased | int/null | DWD原采购行order_item_id去重后汇总quantity_real；关联不完整为null |
| arrival_received/pending | int/null | 当前收货DWD未齐全，两者为null，不拿库存余额代替到货量 |
| arrival_status | unknown | 当前没有足够标准收货事实 |
| candidate_created_on | date/null | 到仓业务日；不是审批时间或PK日期 |
| overdue | bool/null | 北京业务日差>=1；无日期时未知 |
| stock_balance | int/null | 当前已发布批次余额，不等同可打包量 |
| available_quantity | int/null | 发布时良品量-领星良品锁定量-本地有效分配；源量缺失或异常为null |
| default_quantity | int/null | 单ItemID默认可用量；多ItemID需用户填数量 |
| can_approve、blocked_reasons | bool/string[] | 明确可操作状态，不静默删除问题行 |
| source_observed_at | timestamptz | 原始采集时间，不以本地重新发布时间冒充新鲜采集 |

阻断码：STORE_UNKNOWN、ELIGIBLE_LISTING_MISSING、GTIN_INVALID、MSKU_MISSING、STOCK_PROOF_UNKNOWN、STOCK_FULLY_ALLOCATED。

## 写请求与响应
共同body：source_account_ref(string<=128)、warehouse_id='16168'、candidate_version、idempotency_key(UUID)。approve增加qty（严格整数1..1000000且不超过来源可用量）、customs(default/declare/skip，默认未知)、rwh(可选备注<=128)、is_test=true。reject增加note（trim后非空，<=500）。客户端不传actor、PK或订单状态。

响应data：id、candidate_id、pk(null仅驳回)、status(approved/rejected)、qty、version=1、is_test、customs_value(bool/null)、customs_src(manual/unknown)、rwh、actor_uid、note、created_at、snapshot(完整Candidate)。默认报关未知，不能伪造采购备注auto结果。

## 事务、幂等与错误
来源账号+幂等键先加事务锁；相同动作/候选/actor/body重试返回原响应，不重复发号；不同请求409。随后与发布器共用账号+仓库事务锁，重查来源版本、已决定状态和库存；发号/订单/分配/事件单事务。PK为PKYYMMDD-001..999，北京业务日全库统一序列。幂等成功响应写入不可变事件，事件trigger禁止UPDATE/DELETE；订单保存version，为后续变更留扩展。

401未认证；403缺动作/来源范围/本地目标不匹配；404不可见或不存在；422参数不合法；409 reason为IDEMPOTENCY_KEY_REUSED、ALREADY_DECIDED、SOURCE_CHANGED、CANDIDATE_BLOCKED、INSUFFICIENT_STOCK、PK_DAILY_LIMIT；500内部失败不回显源记录或凭据。出现来源/库存变化刷新候选再核对，禁止客户端绕过数量上限。GET没有写入/外部采集副作用。

## 技术依据
事务嵌套测试按[SQLAlchemy Session文档](https://docs.sqlalchemy.org/en/20/orm/session_api.html#sqlalchemy.orm.Session.params.join_transaction_mode)；发布/审批互斥使用[PostgreSQL事务咨询锁](https://www.postgresql.org/docs/14/functions-admin.html#FUNCTIONS-ADVISORY-LOCKS)。实际验证结果见交付记录，不把文档设计当成测试结果。

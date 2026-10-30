# 待发货打包单 API

日期：2026-10-23。仅本阶段本地开发；没有审批或外部执行。前缀 `/api/pmc/wfs/pending-packing`。

## 权限与来源

页面权限 `page:pmc:wfs:view`；生成草稿 `action:pmc:wfs-pending-packing:draft-submit`；换身份 `action:pmc:wfs-pending-packing:identity-switch`。来源账号与店铺范围同时验证；超级权限通配符沿用现有IAM，不硬编码角色/姓名。新权限已登记，不自动授予用户或角色。

装箱来自本系统 `ops_domestic_packing_box_sets/lines`；PK、身份和报关来自本系统打包单。草稿、商品快照、装箱占用、审计分别为 `ops_pmc_wfs_drafts`、`ops_pmc_wfs_draft_items`、`ops_pmc_wfs_box_allocations`、`evt_pmc_wfs_draft_events`。旧代码仅参考，不在运行时读取。GET不写库、不调外部API。

## 接口

| 方法 / 后缀 | 请求 | 响应 data |
|---|---|---|
| GET /orders | store_id、keyword、only_test、arrangement（all/ready/partial/done）、creation_result（all/none/in_progress/succeeded/failed/partial/unknown）、completed_from/completed_to（Asia/Taipei 日历日）；page>=1，page_size默认20最大200 | items:PendingRow[]、total |
| GET /summary | 同上筛选（含 arrangement 与 creation_result），不含分页 | completed、ready、test、waiting、no_box、filled_not_done、available_boxes、available_units |
| GET /filter-options | 无 | stores:[{value,label}]；来源为当前账号/店铺数据范围内的 `dim_lingxing_stores`，并补充已完成待发货 PK 上出现过的店铺名称 |
| GET /orders/{UUID} | 无 | 最新PendingRow；未完成/不可见404 |
| GET /orders/{UUID}/identity-options | 无 | 同账号同SKU、当前可见有效Listing，含listing_version |
| POST /orders/{UUID}/identity | source_account_ref、idempotency_key、expected_version、expected_box_version、target_store_id、target_item_id、listing_version、reason | 新PK对应PendingRow |
| POST /drafts | 见下例 | drafts:DraftRead[]；均为pending |
| GET /drafts/{UUID} | 无 | DraftRead，按当前权限重新验证 |

统一信封 `{success,data,error,meta,request_id}`；meta.source=new_system_postgresql、execution_enabled=false。详见OpenAPI response_model；403/404不泄露隐藏单据内容。

```json
{
  "source_account_ref": "<已授权来源账号>",
  "idempotency_key": "<客户端UUID，同请求重试保持>",
  "selections": [{
    "order_id": "<PK内部UUID>",
    "expected_version": 1,
    "expected_box_version": 1,
    "box_line_ids": ["<本系统装箱行UUID>"]
  }],
  "return_address": {
    "address_line1": "<退货街道>", "city": "<城市>",
    "state_code": "TX", "postal_code": "77449", "country_code": "US"
  },
  "its": false
}
```

退货地址为用户输入快照，未宣称平台验证。selections最多100个PK，每PK最多20行；同账号/店铺/业务测试标记；整行分配，不支持半行箱数。请求不接收actor、status或客户端库存证据。每箱件数不同按组生成多张草稿，批量事务原子提交。件数由后端计算。

## PendingRow 字段

order复用仓库WarehouseOrderRead（含原Q、实装T、UUID行、尺寸cm/重量kg、版本和UTC完成时间）；business_test为业务测试，不替代order.is_test环境保护；occupied_line_ids为已占用行；available_line_ids为可选剩余行；blocked_reasons解释资料缺失；can_edit在任意行占用后为false。总数按PK计，装箱按行计；统计包含筛选范围中全部页。

缺GTIN/身份不完整阻断草稿，缺值不伪造为零。合法少装/多装沿用国内仓既有完成规则，不要求Q=T；仅当前真实已完成装箱可用。时间UTC返回，前端Asia/Taipei展示。

## 改箱与报关

复用 `/api/pmc/domestic/packing-warehouse/orders/{id}/rebox`、`/customs`，见 `docs/delivery/pmc-packing-warehouse-api.md`。前端同时要求国内仓查看及对应动作权限。两入口在共享账号/仓库/PK锁内执行WFS占用守卫，直接调用旧接口也不能绕过。改箱不足仍按原规则仅保存阻塞提议，不覆盖实装。

换身份作废旧PK、创建新PK，克隆完成装箱和快照；原/额外库存分配转移，不新增扣库存。差异继承，阻塞差异先处理。国内仓void/approve事件与WFS identity事件保留新旧链及原因；后端重新核对Listing版本及目标店铺范围。

## 错误、幂等与边界

401未登录；403权限/账号/店铺或非本阶段允许的本地环境；404不可见/不存在；409版本、占用、身份、状态或幂等冲突；422输入校验。409的error.details.reason含ORDER_VERSION_CHANGED、BOX_VERSION_CHANGED、WFS_BOXES_OCCUPIED、WFS_BOXES_OCCUPIED_OR_INVALID、LISTING_CHANGED、STORE_OR_TEST_MIXED等。

命令绑定登录人、完整请求哈希及账号UUID幂等键。事务采用共享账号/仓库锁，按PK排序行锁和装箱唯一约束；同请求重试返回原草稿，改变请求或操作人409。草稿回执重试仍检查当前范围。审计事件数据库trigger禁止UPDATE/DELETE。

本阶段有效占用持续保留，不提供批准、撤回、释放、外部计划取消/改数量/箱唛接口。下一阶段需单独状态机及结构升级，不能以删除草稿/审计释放。

本地结构由负责人批准的专用加法脚本创建；不改变现有Alembic版本。正式部署需另外整理Alembic迁移，不可只部署代码。


## V2 按箱数创建接口（2026-10-29）

本节是当前页面契约；上文 drafts 接口仅保留历史兼容，页面不再提交待人工审批草稿。
基路径 `/api/pmc/wfs/pending-packing`。统一 JSON envelope；文件下载例外。

| 方法 | 路径 | 功能 / 动作权限后缀 |
|---|---|---|
| GET | /capabilities | 创建/探测能力及禁用原因 |
| POST | /allocation-preview | 整箱分票核对 / create |
| POST | /creation-operations | 幂等提交、自动审批、异步创建 / create |
| GET | /creation-operations?order_id=UUID&page=1&page_size=10 | PK 创建记录，含合并来源 PK；分页最大100 |
| GET | /creation-operations/{ident} | 逐票状态、实际货件与箱唛状态 |
| POST | /creation-operations/{ident}/reconcile | 核实结果 / reconcile |
| POST | /creation-operations/{ident}/labels/retry | 仅补取箱唛 / label-retry |
| GET | /creation-operations/{ident}/labels/{shipment_id} | PDF附件，application/octet-stream，no-store |
| POST | /optional-previews | 可选探测、不占用 / preview |

动作权限前缀 `action:pmc:wfs-pending-packing:`；所有接口验证 `page:pmc:wfs:view` 和来源账号/店铺范围。旧 draft-submit 权限不自动授予 create。

分箱请求：`order_id`、`expected_version`、`expected_box_version`；其他 PK 放 `additional_selections`，每项同样三个字段；`shipping_boxes`、`shipment_count`、`shipment_boxes` 为严格正整数，票数匹配数组长度，箱数和必须一致，上限9999。所有 PK 账号、店铺、测试标记一致；相同 SKU 身份一致。响应返回 `tickets`、每票 `ranges` 的 PK/SKU/行/箱序/实际件数，以及 `preview_hash`、可用和剩余箱数。
创建在上述字段基础增加 `source_account_ref`、`preview_hash`、UUID `idempotency_key`、`its`（默认 true），可选 `return_address`（不传 = Walmart 回填店铺默认退货地址）、可选带时区 `expected_delivery_at`（不传 = 北京时间今天 +30 天）。地址详细结构沿用原 ReturnAddress schema。不传 OWS。表单重试复用同键；改变请求不得复用。（2026-10-31 负责人决定；前端创建弹窗已去掉地址与日期输入。）

创建响应包含 `id`、`order_id`、`state`、`created_at`、`approval_mode=automatic`、`automatically_approved_at`、`tickets`。票包含 allocation、state、error_code、shipments；shipment 包含 shipment_id 和 label_state。标签二进制和凭据不出现在 JSON。自动审批和创建结果分别表达。

状态：QUEUED/RUNNING/SUCCEEDED/FAILED/UNKNOWN/PARTIAL；票不使用PARTIAL。标签 PENDING/READY/FAILED。超时视 UNKNOWN，禁止盲目重发。按已知货件补标签不会重建。未启用平台适配器返回503 WFS_EXECUTION_DISABLED且不占用；403权限/环境，404不可见，409版本/占用/幂等冲突，422字段校验。

新增四表：ops_wfs_creation_operations、ops_wfs_creation_tickets、ops_wfs_box_holds、evt_wfs_creation_events。事件禁止更新/删除；占用具有箱行+版本+箱序唯一约束；失败不自动释放。只在隔离测试库执行新增迁移；尚未迁移的业务环境不能宣称本页可用。
Worker 复用既有 Celery，显式加载 app.modules.pmc_wfs.tasks、消费 integration 队列；任务名 integration_sync.wfs_creation。本次未改变公共调度，真实 Gateway 默认禁用。

缺少V2表时返回503 `WFS_SCHEMA_NOT_READY`；页面显示数据库结构尚未更新，不再以通用服务错误或空列表掩盖。


## Walmart 适配器（2026-10-31）

`get_creation_gateway()` 按环境变量选择，复用服务器已有的 `/etc/szzsbj/walmart-scf.env`（celery 服务已加载）：`SZZSBJ_WFS_CREATION_GATEWAY=scf` 时启用 `WalmartScfCreationGateway`，并要求 `SZZSBJ_WALMART_SCF_STORE_ID_MAP`（审核过的 store_id→店铺码）、`SZZSBJ_WALMART_SCF_CVM_ROLE`、`SZZSBJ_WALMART_SCF_TARGET_ROLE_ARN`、`SZZSBJ_WALMART_SCF_APPROVED_READ_KEYS` 含 `inbound_shipments,inbound_shipment_items`、新增 `SZZSBJ_WALMART_SCF_APPROVED_WRITE_KEYS`；任一缺失 → 仍为 Disabled（503 `WFS_EXECUTION_DISABLED`）。适配器只能在 company-ai 进程里真正发起调用（CVM 身份）。

店铺前置：`ops_wfs_store_settings`（迁移 0072，维护入口见 pmc-wfs-settings-api.md）必须有该店铺行，`creation_enabled=true`，用 ITS 时 `its_enabled=true`，且与服务器审核映射一致。否则 409：`WFS_STORE_NOT_CONFIGURED` / `WFS_STORE_CREATION_DISABLED` / `WFS_ITS_NOT_AVAILABLE` / `WFS_STORE_MAPPING_CONFLICT`；SKU 缺 14 位 GTIN → 409 `WFS_ITEM_IDENTITY_MISSING`。这些在「确认创建」前校验，不占用箱子。

执行：计划号 `PMC-[TEST-]<店铺码>-<票号前12位hex>`，建前按计划号回读查重（幂等）→ POST 建单 → 回读得 shipmentId → 每张货件取箱唛 PDF。Walmart 4xx 且回读无货件 → 票 FAILED（`WFS_PLATFORM_REJECTED`，Walmart 错误体记在 `walmart_call` 事件里）；5xx 或建成后回读为空 → 票 UNKNOWN，箱子保留，等「重新核对」（先到领星看是否已出现，再到 Seller Center 核对，不自动取消）。每次 Walmart 调用写一条 `evt_wfs_creation_events(kind=walmart_call)`：操作键、状态码、引用、去敏错误体；不含令牌和响应正文。

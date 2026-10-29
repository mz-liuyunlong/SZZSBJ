# 待发货打包单 API

日期：2026-10-23。仅本阶段本地开发；没有审批或外部执行。前缀 `/api/pmc/wfs/pending-packing`。

## 权限与来源

页面权限 `page:pmc:wfs:view`；生成草稿 `action:pmc:wfs-pending-packing:draft-submit`；换身份 `action:pmc:wfs-pending-packing:identity-switch`。来源账号与店铺范围同时验证；超级权限通配符沿用现有IAM，不硬编码角色/姓名。新权限已登记，不自动授予用户或角色。

装箱来自本系统 `ops_domestic_packing_box_sets/lines`；PK、身份和报关来自本系统打包单。草稿、商品快照、装箱占用、审计分别为 `ops_pmc_wfs_drafts`、`ops_pmc_wfs_draft_items`、`ops_pmc_wfs_box_allocations`、`evt_pmc_wfs_draft_events`。旧代码仅参考，不在运行时读取。GET不写库、不调外部API。

## 接口

| 方法 / 后缀 | 请求 | 响应 data |
|---|---|---|
| GET /orders | store_id、keyword、only_test；page>=1，page_size默认20最大200 | items:PendingRow[]、total |
| GET /summary | 同上筛选，不含分页 | completed、ready、test、waiting、no_box、filled_not_done、available_boxes、available_units |
| GET /filter-options | 无 | stores:[{value,label}]，完整已完成单范围 |
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

# RBAC v2 0041 后全链路审计

Status: `ready_for_review`（未合并、未部署、未执行生产迁移）

Audit date: 2026-10-17

Base: `7a8eab793c4edf9e419b3ae846e2b47dddf51587`

## 1. 审计方法与结论

本次以 `navigation.ts`、`routes.tsx`、15 个 FastAPI router、统一
`permission_for_request()`、各 route dependency、Service 对象级检查及前后端测试为证据。
静态路由盘点共 125 个 `/api/**` route；以下矩阵按 API family 覆盖全部 route，不把
ComingSoon、mock-only 或纯前端页面伪报为后端已完成。

已修复的错误拒绝或潜在越权：

1. Approval Workspace 已从退休 key 切换到 canonical page/action 权限；申请、补充材料、审核互相隔离。
2. WFS follow、archive-request、archive-review、mark-recovered、sync-legacy 分别授权。
3. 所有本次发现的直接权限集合判断改用支持 `*` 的公共 helper；真实超管来源仍是后端身份。
4. method-specific policy 先于宽泛 prefix，避免 PMC override、运营计划 clearance、定价规则等写请求被 page view 吞掉。
5. 用户资料编辑、启停、角色和数据范围是独立动作；请求字段不能借另一个动作权限越权。
6. 真实用户的数据源账号宇宙来自 `gov_integration_sync_configs`，不再依赖 preview-only 环境变量。
7. 用户级数据范围可在用户管理页面查看、修改、审计；未登记的 source account 会被后端拒绝。
8. 飞书异常不再携带 provider body、provider message、原始 exception text 或异常 cause。
9. 运营计划按 UUID 的读取、事件、目标修改、清货和失败明细导出已在 Repository 内执行
   `source_account` 对象校验；写入使用同一条 `UPDATE ... WHERE ... RETURNING` 防止 TOCTOU。
10. 角色分配同时校验功能权限、高风险权限和角色携带的数据范围；组合角色、`*`、用户级 override
    均不能让普通管理员间接扩权。
11. Order Profit 与 Daily Sales 的列表、汇总、趋势和 CSV 均在后端输出边界执行利润金额/利润率字段过滤。
12. 非数字且非 preview 的 principal 不再继承已配置账号全集；运行时 fail closed。

## 2. 页面 → API → 权限矩阵

| 页面 / 状态 | API family | 页面权限 | 动作 / 字段权限 | 数据范围 | 角色策略 | 主要测试 | 结论 |
|---|---|---|---|---|---|---|---|
| 产品管理 / API connected | `/api/product-management/**`, `/api/products/skus/**`, `/api/user-table-views/product-management` | `page:products:product-management:view` | export、recalculate-pricing、update-pricing-rules、save-table-view、view-sync-history、view-raw-lineage、view-operation-logs；purchase-cost 字段 | `source_account` | 动态角色授权 | permission policy、router、source scope | 已修复；详情子动作与价格写入独立 |
| Product Core（无页面主数据入口） | `/api/v1/products/**` | legacy contract + `*` | create/update/listing create/update | 尚无可信 ownership | 仅真实 superadmin | products router | 正确拒绝；在独立 ownership PRP 前 fail closed |
| Listing 管理 / API connected | `/api/listings/**` | `page:products:listing-management:view` | export、manage-tags、archive、restore、edit-analysis-link | `source_account` | 动态角色授权 | policy/router | 正确授权；写请求不使用 page view |
| 每日销售 / API connected | `/api/sales/daily-sales**`, `/api/data-pages/filter-options` | `page:sales:daily-sales:view` | export；受限成本字段按后端字段规则 | `source_account` | 动态角色授权 | data pages router | 正确授权 |
| 订单利润 / API connected | `/api/sales/order-profit**` | `page:sales:order-profit:view` | export；利润敏感字段按后端字段规则 | `source_account` | 动态角色授权 | data pages router | 与每日销售分离 |
| 退款管理 / API connected | `/api/after-sales/refunds/**` | `page:aftersales:refund-management:view` | 当前只读 | `source_account` | 动态角色授权 | after-sales router | 正确授权 |
| 运营计划 / API connected | `/api/operations/plans/**` | `page:operations:plan:view` | create、edit、import | `source_account` + item-level object check；多账号 item 整体拒绝 | 动态角色授权 | permission policy/router + PostgreSQL object-scope tests | clearance/target update 使用原子 scoped UPDATE；events 受父计划约束；failed-export 受批次创建者和保存的账号集合约束 |
| WFS 费用异常 / API connected | `/api/warehouse/wfs-fee-alerts/**`, `/api/warehouse/wfs-fee-cases/**` | `page:warehouse:wfs-fee-alert:view` | follow、archive-request、archive-review、mark-recovered；legacy sync 仅真实超级管理员 | `source_account` | 动态角色授权；跨账号 legacy sync 不等同普通 action | unified approvals、WFS router/frontend | 高危动作未自动扩权；生产执行环境开关仍保留 |
| PMC 采购看板 / API connected | `/api/pmc/purchase/**` | `page:pmc:purchase-board:view` | override | `source_account` | 动态角色授权 | permission policy/PMC tests | override POST 不再被 page prefix 吞掉 |
| 审批工作台 / API connected | `/api/approvals/**` | `page:data-center:approval-workspace:view` | WFS archive-request / archive-review | `source_account` + applicant/reviewer + state/version | 动态角色授权 | unified approval tests | 已修复；view 不能补材料或审核 |
| 任务中心 / API connected | `/api/integrations/**` | `page:data-center:task-center:view` | configure、execute | `source_account` | 动态角色授权 | integration tests | 读取、配置、执行分离 |
| 用户管理 / API connected | `/api/settings/users**`, `/api/settings/user-role-options`, `/api/settings/rbac/users/**` | `page:settings:user-management:view` | create、edit、assign-role、reset-password、enable-disable、configure-data-scope；phone/email 字段 | 用户级 scope 管理为高危动作 | 动态角色授权；超管账号保护 | IAM/RBAC/action separation | 已补用户级入口；`*` 二次确认且后端限制 |
| 角色管理 / API connected | `/api/settings/rbac/catalog`, `/roles**`, `/audit-events` | `page:settings:role-management:view` | create、configure-permissions、configure-data-scope、view-audit | grant boundary | 动态角色授权；普通 admin 不等于超管 | RBAC tests | 乐观锁、越级授予和审计保持 |
| 费用规则 / API connected | `/api/business-rules/**` | `page:settings:fee-rules:view` | edit、recalculate | 规则自身 scope | 动态角色授权 | policy/business-rule tests | deactivate 属于 edit |
| 登录与密码恢复 | `/api/auth/**` | 登录/恢复端点按既有公开边界；`/me` 受认证 | session revoke、统一恢复响应 | 不适用 | 后端身份 | IAM tests | 未扩大 public allowlist |
| 媒体图片读取 | `/api/media/image-assets/**` | 由签名媒体 contract 控制 | 无本次新增动作 | 资产签名边界 | 后端校验 | media tests | 未改动 |
| Ads Campaign、运营日志、数据导入、API 文档 | 无对应业务 API 或使用静态/前端能力 | 各自 page key | 无后端动作可宣称 | 未实现 | 动态页面权限 | route tests | 前端已实现/占位边界，不伪报 API coverage |
| 其余 navigation 页面 | `ComingSoonPage` | 已登记 page key | 无 | 无 | 动态页面权限 | route tests | planned，不是 implemented |

页面角色列不写死业务角色名。角色只是一组可配置权限；超级管理员能力来自可信的
`app_users.is_super_admin`，不是 `role_key=admin` 或客户端声明。

## 3. 125 个 API route 的 family 盘点

| Family | Method / path（包含该 family 的全部 route 形态） | 实际裁决 |
|---|---|---|
| Auth | `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`, `POST /api/auth/password-reset/request`, `POST /api/auth/password-reset/confirm` | public 边界仅限既有 auth contract；其余 protected-by-default |
| Product BFF | `GET /api/product-management/options`, `GET/POST /skus`, `GET /skus/summary`, `GET /skus/{sku_id}`, `GET /skus/{sku_id}/pricing-breakdown`, `GET/POST /skus/export`, `POST /skus/recalculate-pricing`, `GET/PUT /pricing-rules`, `GET/PUT /api/user-table-views/product-management` | page/action/field + source account |
| SKU detail | `GET /api/products/skus`, `GET /{sku_id}/detail`, `/platform-listings`, `/sync-history`, `/raw-lineage`, `/cost-history`, `/operation-logs` | page；history/lineage/log/cost 用独立 action/field |
| Product Core | `GET/POST /api/v1/products`, `GET /options`, `GET/PATCH /{product_id}`, `GET/POST /{product_id}/listings`, `PATCH /{product_id}/listings/{listing_id}` | legacy API permission + real-superadmin-only temporary scope gate |
| Listing | `GET /api/listings/walmart`, `/summary`, `/filter-options`, `/export`; `POST /{listing_id}/archive|restore`; `GET/PUT /{listing_id}/gpt-analysis`; tag GET/POST/PATCH/DELETE 与 batch-set | page/action + source account |
| Sales | Daily Sales GET/list/export；Order Profit GET/list/filter-options/trend/export；shared filter-options | distinct page/export + source account |
| After-sales | refund items/overview/product-analysis GET | page + source account |
| Operation Plan | summary/options/products/events/template/failed-export GET；import/clearance POST；targets PATCH | page/create/edit/import + source account |
| WFS | alerts/cases/list/detail/legacy-compare GET；compat PUT；follow/archive-request/archive-review/mark-recovered/sync preview/execute POST | page + five distinct actions + source account |
| Approval | list/summary/detail GET；submit/supplement/review POST | page + request/review + source account + object/state |
| PMC | board/summary/order/plans/cycles/overrides GET；override POST | page/override + source account |
| Integration | interfaces/configs/runs/raw refs/work items GET；config PATCH；run/backfill/retry POST | page/configure/execute + source account |
| Business rules | commissions/logs GET；upsert/deactivate/recalculate POST | page/edit/recalculate |
| IAM/RBAC | users/roles/permission catalog/audit/user-role-options/user data scopes/role data scopes 的 GET/POST/PATCH/PUT/DELETE | page + exact action + field + grant boundary + audit |
| Media | signed image asset GET | signed asset boundary |

### 3.1 Route → Service → Repository 数据边界复核

| Route family | Service / Repository 执行点 | 对象 / 数据范围结论 | 导出 / 字段结论 |
|---|---|---|---|
| Product Management / SKU Detail | `ProductManagementService/Repository`、`SkuDetailService/Repository` | `source_account`；SKU 主路径为内部 UUID | purchase/logistics cost 使用 canonical field key；列表、详情、cost history 与 CSV 分开校验 |
| Listing | `ListingManagementService/Repository`、`ListingTagRepository` | 列表/对象按账号；batch-set 必须全部 ID 都在范围内，否则整体 403 | export 复用账号范围；tag 维护必须 `manage-tags`，不是 page view |
| Daily Sales / Order Profit | `DailySalesService`、`OrderProfitService` 及 repository | 查询和 export 使用同一账号范围 | list/summary/trend/CSV 都在 response/export 边界过滤 gross-profit 与 profit-margin 派生值 |
| After-sales | `AfterSalesService/Repository` | `source_account` | 当前只读，无独立导出写路径 |
| Operation Plan | `OperationPlanService/Repository` | item 的全部当前 Listing 账号必须属于调用者；events 继承父计划；batch export 校验创建者、保存范围和当前范围 | failed-export 不按 UUID 裸读；无权与不存在统一隐藏为 404 |
| WFS / Approval | `WfsFeeAlertService/Repository`、`ApprovalService/Repository` | source account + parent object + state/version；legacy sync 仅真实超管 | request/review 分离；无 page-only 写入 |
| PMC | `PmcPurchaseReadService/Repository`、override service | `source_account` | override 为独立高风险 action |
| Integration | sync services/repositories | governance account universe 与用户有效范围取交集 | config/execute 与 page view 分离；RAW 内容不由本次接口扩权 |
| IAM/RBAC | `RbacService/RbacRepository` | 目标用户保护；角色权限、high-risk、role scopes 与 actor effective scopes 一次判定 | phone/email 仍为独立字段权限；审计不记录 secret |
| Business rules | business-rule service/repository | 规则自身 scope 与 exact action | deactivate/edit/recalculate 分离 |
| Product Core | product service/repository | 尚无可信 ownership；当前真实超级管理员 gate，普通主体 fail closed | 不宣称 source-account/store/product 隔离已完成 |
| Auth / Media | IAM service；signed media boundary | 既有身份和签名边界 | 不扩大 public allowlist |

上述矩阵覆盖 OpenAPI 的 109 个 path / 125 个 method 操作。`store/owner/sku/product` 的登记能力不等于
Repository 已执行隔离；未建立可信归属的写路径继续 fail closed。

## 4. 数据范围真实执行状态

| 维度 | 当前执行状态 | 结论 |
|---|---|---|
| `source_account` | API dependency 从 governance config 取得合法全集，再与用户级（同类型覆盖）或角色级范围取交集；空集拒绝 | 已执行 |
| `store` | 可登记、可显示来源，但业务 repository 尚未统一消费 | registry-only，不得宣称隔离完成 |
| `owner` | 同上 | registry-only |
| `sku` | 同上 | registry-only |
| `product` | 同上；Product Core 缺 ownership，临时仅真实超管 | registry-only / fail closed |

用户级同类型范围优先于角色范围；多个角色同类型按并集；无范围拒绝；`*` 只能来自明确授权。
`source_account` 的具体值必须存在于 `gov_integration_sync_configs`。普通管理员不能授予超出自身有效范围的值，
超级管理员也不能保存未登记值。其余四类范围在服务端过滤完成前只可视为登记信息。

## 5. 兼容逻辑分类

- 必要的滚动兼容：0042 暂留 `approvals:workbench:read`，并仅将已有 grant 复制到 canonical page key。
- 受控兼容：部分旧 route 声明仍由 `permission_for_request()` 映射到 canonical page/action/field；静态测试固定允许清单。
- runtime 不再接受 declared legacy permission 作为 canonical policy 的通用 fallback；仅有旧 page/read/write key
  不能调用新 action。模块级成本兼容仅限既有 Product Management 读路径，结束条件是生产角色完成 canonical
  字段授权并经过真实账号 smoke，届时另开任务移除。
- 不可作为长期后门：WFS 旧 action 不再用于 runtime；审批旧 review 不映射到 WFS 高危审核。
- 待独立治理：`/api/v1/products` 的 legacy CRUD keys。在 ownership/data-scope PRP 完成前维持 superadmin-only。

## 6. 生产案例分类

历史材料中的用户 ID 41 尚未通过本地证据证明就是刘云龙；发布前必须由获授权的生产只读诊断确认身份。
该 403 需要分开处理：

- 代码缺陷：Approval/WFS key 断链、preview-only account universe、method prefix 吞动作；本 PR 已修复。
- 配置缺失：用户及其角色没有 `source_account`；系统应继续返回 `DATA_SCOPE_DENIED`。
- 正确拒绝：没有产品、Listing、每日销售等页面权限时，不应因修复 403 自动获得页面。
- 授权漏洞：本次未发现需要通过放宽权限解决的路径；任何真实账号分配仍需 Owner 确认。

## 7. 未关闭风险

1. `mypy app tests` 的仓库基线仍先因 duplicate module 退出；使用
   `--explicit-package-bases` 后仍有既有跨模块类型债务，本 PR 不伪报通过。
2. 本 PR 已将未执行的 0042 revision 缩短为 `20261017_0042_rbac_backfill`，并让新建 PostgreSQL
   version table 使用 `varchar(128)`；fresh chain 与模拟生产 `varchar(32)` 的 0041→0042 均已通过。
3. 管理 UI 目前手工输入范围；`source_account` 有后端权威值校验，但尚无脱敏候选列表 API。
4. `store/owner/sku/product` 尚未成为通用 repository filter；不得依赖 UI 登记声称隔离已完成。
5. 合并不等于生产事故关闭；仍需单独批准 migration、部署、重启和真实角色只读 smoke。

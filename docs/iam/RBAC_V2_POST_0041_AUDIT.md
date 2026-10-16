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

## 2. 页面 → API → 权限矩阵

| 页面 / 状态 | API family | 页面权限 | 动作 / 字段权限 | 数据范围 | 角色策略 | 主要测试 | 结论 |
|---|---|---|---|---|---|---|---|
| 产品管理 / API connected | `/api/product-management/**`, `/api/products/skus/**`, `/api/user-table-views/product-management` | `page:products:product-management:view` | export、recalculate-pricing、update-pricing-rules、save-table-view、view-sync-history、view-raw-lineage、view-operation-logs；purchase-cost 字段 | `source_account` | 动态角色授权 | permission policy、router、source scope | 已修复；详情子动作与价格写入独立 |
| Product Core（无页面主数据入口） | `/api/v1/products/**` | legacy contract + `*` | create/update/listing create/update | 尚无可信 ownership | 仅真实 superadmin | products router | 正确拒绝；在独立 ownership PRP 前 fail closed |
| Listing 管理 / API connected | `/api/listings/**` | `page:products:listing-management:view` | export、manage-tags、archive、restore、edit-analysis-link | `source_account` | 动态角色授权 | policy/router | 正确授权；写请求不使用 page view |
| 每日销售 / API connected | `/api/sales/daily-sales**`, `/api/data-pages/filter-options` | `page:sales:daily-sales:view` | export；受限成本字段按后端字段规则 | `source_account` | 动态角色授权 | data pages router | 正确授权 |
| 订单利润 / API connected | `/api/sales/order-profit**` | `page:sales:order-profit:view` | export；利润敏感字段按后端字段规则 | `source_account` | 动态角色授权 | data pages router | 与每日销售分离 |
| 退款管理 / API connected | `/api/after-sales/refunds/**` | `page:aftersales:refund-management:view` | 当前只读 | `source_account` | 动态角色授权 | after-sales router | 正确授权 |
| 运营计划 / API connected | `/api/operations/plans/**` | `page:operations:plan:view` | create、edit、import | `source_account` | 动态角色授权 | permission policy/router | clearance 与 target update 均按 edit，不由 view 放行 |
| WFS 费用异常 / API connected | `/api/warehouse/wfs-fee-alerts/**`, `/api/warehouse/wfs-fee-cases/**` | `page:warehouse:wfs-fee-alert:view` | follow、archive-request、archive-review、mark-recovered、sync-legacy | `source_account` | 动态角色授权 | unified approvals、WFS router/frontend | 已修复；高危动作未自动扩权 |
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
- 不可作为长期后门：WFS 旧 action 不再用于 runtime；审批旧 review 不映射到 WFS 高危审核。
- 待独立治理：`/api/v1/products` 的 legacy CRUD keys。在 ownership/data-scope PRP 完成前维持 superadmin-only。

## 6. 生产案例分类

已知用户 ID 41 的 403 需要分开处理：

- 代码缺陷：Approval/WFS key 断链、preview-only account universe、method prefix 吞动作；本 PR 已修复。
- 配置缺失：用户及其角色没有 `source_account`；系统应继续返回 `DATA_SCOPE_DENIED`。
- 正确拒绝：没有产品、Listing、每日销售等页面权限时，不应因修复 403 自动获得页面。
- 授权漏洞：本次未发现需要通过放宽权限解决的路径；任何真实账号分配仍需 Owner 确认。

## 7. 未关闭风险

1. `mypy app tests` 的仓库基线存在 namespace 冲突；最终诊断模式
   `mypy --explicit-package-bases app tests` 报告 `399 errors in 59 files`，属于既有大规模类型基线，本 PR 不伪报通过。
2. 从空库重放历史 migration 会因旧 revision 长于 Alembic 默认 `varchar(32)` 失败；0042 的 0041→0042 演练已在加宽版本表的隔离库完成，但空库重建问题应单独治理。
3. 管理 UI 目前手工输入范围；`source_account` 有后端权威值校验，但尚无脱敏候选列表 API。
4. `store/owner/sku/product` 尚未成为通用 repository filter；不得依赖 UI 登记声称隔离已完成。
5. 合并不等于生产事故关闭；仍需单独批准 migration、部署、重启和真实角色只读 smoke。

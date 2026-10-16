# RBAC v2 生产角色授权修复方案

Status: `ready_for_review`（不包含生产授权写入）

## 1. 问题分类

已知生产案例用户 ID 41 不能用一个“403”概括：

| 类型 | 示例 | 本次处理 |
|---|---|---|
| 代码缺陷 / 错误拒绝 | Approval/WFS 使用退休 key；`*` 直接集合判断；真实用户错误依赖 preview account universe；宽 prefix 吞掉 action | 已在代码和测试中修复 |
| 配置缺失 | 用户和角色都没有 `source_account`，但访问要求该范围的业务 API | 保持 fail closed，由 Owner 确认后经 UI 配置 |
| 正确拒绝 | 没有产品、Listing、每日销售等 page permission | 不自动补权 |
| 授权漏洞 | 只有 page view 却能审核、启停、改角色或改 scope | 已拆分 action 并补充后端校验 |

修复代码不会自动把 user 41、operations、warehouse 或普通 admin 升级为超级管理员，也不会授予 `*`。

## 2. 当前数据范围事实

- `source_account` 是当前业务 API 真正执行的通用数据范围。
- 有效账号全集来自 `gov_integration_sync_configs`，再与用户/角色授权取交集。
- 用户级同类型 scope 存在时覆盖角色级同类型 scope；多个角色的同类型 scope 按并集合并。
- 空范围、未知账号或已撤销账号 fail closed。
- `store`、`owner`、`sku`、`product` 当前只能登记和显示来源，尚未被所有 repository 统一消费；不得宣称已完成隔离。
- Product Core 缺少可信 ownership 模型，当前 CRUD 临时只允许真实 `is_super_admin`，不是依据角色名称。

## 3. 发布前 Owner 必须确认的清单

Owner 应以业务归属为依据逐一确认，不得让工程师猜测：

| 主体 | 需确认内容 | 禁止默认 |
|---|---|---|
| user 41 | 是否应访问哪些具体 source account；需要哪些已实现页面 | `*`、全页面、超管 |
| operations 角色 | 允许的页面和动作；是否用角色级账号范围 | 所有产品/销售/仓库范围 |
| warehouse 角色 | WFS view/follow/archive-request/review 的独立组合；账号范围 | 因能申请就能审核 |
| 普通 admin | 管理页面、动作与 grant boundary | 角色名等同 `is_super_admin` |
| finance / owner / 其他角色 | 与工作职责匹配的最小权限和账号范围 | 从相似角色复制全部权限 |

## 4. 安全修复流程

1. Owner 提供“主体 → 页面 → 动作 → 具体 source account”的批准清单。
2. 超级管理员在角色管理 UI 配置共享的最小 page/action 权限。
3. 在角色数据权限中配置可共享的具体账号；只有确有全量职责时才考虑 `*`，并完成二次确认。
4. 对个别用户例外，在用户管理的“数据权限”入口配置用户级具体账号；该层会覆盖同类型角色范围。
5. 刷新后重新读取配置，确认普通用户的有效来源显示为 role 或 user；真实超管不使用该编辑入口。
6. 使用目标用户重新获取身份/权限，再执行对应页面和 API 的只读 smoke。
7. 核对 IAM audit event，确认操作者、目标、旧值/新值和 request ID 已记录且无敏感载荷。

不得通过生产 SQL、修改 Token、preview 环境变量或硬编码 user ID 修复授权。

## 5. user 41 的最小恢复路径

若 Owner 确认 user 41 属于 operations 且只需某个已登记 source account：

1. 保持其现有角色，不改变 `is_super_admin`；
2. 只补 Owner 批准的 page/action；
3. 优先在 operations 角色配置共同账号，或在确属个人例外时配置用户级账号；
4. 不授予 `source_account='*'`；
5. 对未批准的产品、Listing、每日销售等页面继续拒绝；
6. 分别验证授权账号允许、其他账号拒绝、详情/导出/写操作不越界。

如果 Owner 尚未确认账号归属，`DATA_SCOPE_DENIED` 是正确的安全结果，不得绕过。

## 6. 角色 smoke 矩阵

| 角色类型 | 必测结果 |
|---|---|
| 真实超管 | `permissions=['*']`；受 governance 已配置账号宇宙约束；可执行获批高危管理动作 |
| 普通 admin | 只按实际 grant；不能提升自己、修改超管或授予自身没有的权限/范围 |
| operations | 已授权页面在具体账号范围内可读；未授权页面、账号和写动作拒绝 |
| warehouse request-only | 可提交符合状态/对象范围的归档申请；不能审核 |
| warehouse reviewer | 可审核授权范围、有效状态和版本的申请；不能越过账号范围 |
| page-only user | 可打开页面/初始化；无 action 时写操作拒绝 |
| no-scope user | 业务接口 `DATA_SCOPE_DENIED`，不返回其他账号数据 |

## 7. 停止条件

- UI 提供的账号不在 governance config；
- 保存后范围来源或有效值与批准清单不一致；
- 普通角色获得 `*`、superadmin 或未批准的高风险 action；
- 用户能通过 URL、ID、分页、筛选、详情或导出读取范围外数据；
- 权限收回后新请求仍可访问；
- 审计事件缺失或包含敏感业务值。

发生上述情况应停止授权和后续发布，不得通过扩大 grant 消除错误。

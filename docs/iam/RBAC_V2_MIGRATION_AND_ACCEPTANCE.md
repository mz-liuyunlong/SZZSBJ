# IAM / RBAC v2 迁移、回滚与验收说明

## 1. 目标

RBAC v2 将权限拆成四个相互独立的边界：

1. 页面权限：决定菜单是否显示、URL 是否允许进入。
2. 功能权限：决定具体页面中的新增、编辑、导出、设置角色等动作。
3. 字段权限：决定敏感字段是否允许返回、展示和导出。
4. 数据权限：决定允许访问哪些数据源账号、店铺、负责人、SKU 或产品。

功能权限必须归属具体页面，不存在“通用操作”。超级管理员仅通过
`app_users.is_super_admin = 1` 获得 `*`；普通 `admin` 角色不会自动绕过权限。

## 2. 迁移边界

本 PR 只提交 migration 和应用代码，不执行生产迁移、生产写入、部署或服务重启。
合并前必须先在独立测试数据库完整演练。生产执行必须获得单独授权。

当前 `main` 的既有基线为：

```text
20261014_0035_add_auth_rbac
  -> 20261015_0036_wfs_cases
```

RBAC v2 迁移严格接在已合入的 `20261015_0036_wfs_cases` 后，不改写、重命名或复用
其他分支已经提交的 revision ID：

1. `20261015_0037_rbac_v2`
   - 扩展权限元数据；
   - 增加角色版本；
   - 增加角色/用户数据范围；
   - 增加 IAM 审计事件；
   - 写入页面、功能、字段权限目录；
   - 将旧权限映射到新权限。
2. `20261015_0038_retire_legacy_rbac_permissions`
   - 删除角色上的旧权限关联；
   - 将旧权限标记为停用。
3. `20261015_0039_restrict_default_data_scopes`
   - 删除非管理员角色的默认全量数据范围；
   - 未显式配置数据范围的普通角色按拒绝访问处理。
4. `20261015_0040_wfs_rbac_actions`
   - 将已合入的 WFS Case 功能权限映射为页面专属 action 权限；
   - 保留 WFS 正式 Case 流程的权限边界；
   - 停用对应旧 WFS action 权限关联。

合并前必须再次同步最新 `main` 并执行 `alembic heads`。若并行分支新增迁移造成多 head，
只新增 Alembic merge revision，不修改任何已合入或他人分支的历史 migration。

## 3. 测试库演练

### 3.1 迁移前检查

仅确认变量是否已设置，不输出连接串：

```bash
[ -n "$APP_ENV" ] && echo "APP_ENV=set" || echo "APP_ENV=missing"
[ -n "$DATABASE_URL" ] && echo "DATABASE_URL=set" || echo "DATABASE_URL=missing"
```

确认数据库是独立测试库后执行：

```bash
cd backend
uv run alembic current
uv run alembic heads
uv run alembic upgrade head
uv run alembic current
```

不得把生产数据库连接串粘贴到日志、PR、聊天或终端截图中。

### 3.2 迁移后只读核对

核对以下对象存在：

- `app_permissions` 新元数据列；
- `app_roles.version`；
- `app_role_data_scopes`；
- `app_user_data_scopes`；
- `iam_audit_events`。

核对权限目录：

- 每个页面只有一个唯一 `page:*:view`；
- 每个 `action:*` 都带所属页面；
- 每个 `field:*` 都带所属页面；
- 旧权限已停用且不再关联角色；
- 非管理员角色没有隐式 `source_account:*`；
- WFS Case 页面专属 action 权限存在且旧 WFS action 权限已停用。

## 4. 回滚演练

RBAC v2 的回滚边界是已合入的 WFS 基线 `20261015_0036_wfs_cases`，不得回退或覆盖
该迁移：

```bash
cd backend
uv run alembic downgrade 20261015_0036_wfs_cases
```

回滚后核对：

- 新增的数据范围和审计表已删除；
- 旧权限恢复为启用；
- 旧角色权限关联已恢复；
- `app_roles.version` 和权限元数据列已移除；
- `20261015_0036_wfs_cases` 及其正式 WFS Case 表结构仍然保留。

回滚会移除 v2 期间新增的审计与数据范围记录，生产环境执行前必须有可恢复备份。

## 5. 权限验收矩阵

### 5.1 超级管理员 `admin`

- `/api/auth/me` 返回 `is_super_admin=true` 和 `permissions=["*"]`；
- 所有页面和功能可访问；
- 可以修改系统管理员角色、数据范围和高危权限；
- 可以永久删除非自身、非超级管理员用户；
- 不能删除或停用自身。

### 5.2 普通管理员 `user`

- `is_super_admin=false`；
- 只按角色实际权限显示页面；
- 不因 `role_key=admin` 获得前端全权限；
- 不能修改超级管理员；
- 不能分配管理员角色；
- 不能授予自身没有的权限或高危权限。

### 5.3 普通业务角色

配置为只拥有：

```text
page:settings:user-management:view
```

验收结果必须是：

- 只显示用户管理页面；
- 角色管理、费用规则等页面不可见；
- 直接输入无权限 URL 会被拦截；
- 用户列表可读取；
- 未配置用户管理动作权限时，新增、编辑、设置角色、重置密码、停用和删除入口不可用；
- 未配置数据范围时，真实业务数据接口返回 `DATA_SCOPE_DENIED`。

## 6. 页面与功能权限验收

重点验证以下页面不再共用权限：

- 产品管理 / Listing 管理；
- 每日销售 / 订单利润；
- 用户管理 / 角色管理 / 费用规则；
- 数据导入 / 任务中心 / API 文档。

角色管理中的功能权限必须按“模块 / 页面”分组，例如：

```text
设置 / 用户管理
  新增用户
  编辑用户
  设置角色
  重置密码

产品 / Listing管理
  导出Listing
  管理标签
  归档Listing
```

不得出现“通用操作”。

## 7. 数据权限验收

角色数据范围支持：

- `source_account`
- `store`
- `owner`
- `sku`
- `product`

同类型多值按并集处理。`*` 代表该类型全范围。没有任何范围时按拒绝访问处理。
超级管理员仍受已配置数据宇宙约束，但不受角色范围约束。

## 8. 审计验收

以下操作必须产生审计事件：

- 新增角色；
- 修改角色权限；
- 修改角色数据范围；
- 新增或编辑用户；
- 修改用户角色；
- 停用用户；
- 重置密码；
- 永久删除用户。

审计记录包含操作者、目标、事件、时间、request ID、来源 IP 和 User-Agent。
不得记录密码、访问令牌、密钥或完整敏感载荷。

## 9. 自动化验证

本 PR 合并前必须全部通过：

```bash
cd backend
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run python -c "import app.main"

cd ../frontend
npm run lint
npm test -- --run
npm run build
```

GitHub CI 的 rule-pack、backend、frontend、WFS PostgreSQL migration smoke 以及 Vercel Preview
均须成功。

## 10. 上线后核对

上线后仅做只读检查：

- 三个账号身份和角色正确；
- 超级管理员通配符正常；
- 角色只显示已授权页面；
- 数据范围按角色生效；
- 权限修改无需重新登录即可在下一次请求生效；
- 多标签页切换账号后，显示身份与实际 token 保持一致；
- 角色权限保存、数据范围保存及用户角色变更均产生审计记录。

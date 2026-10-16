# RBAC v2 0041 后修复发布与验收

Status: `ready_for_review`（未合并、未部署、未执行生产迁移）

## 1. 交付标识

| 项目 | 当前值 |
|---|---|
| Branch | `fix/rbac-post-0041-end-to-end-hardening` |
| Base commit | `7a8eab793c4edf9e419b3ae846e2b47dddf51587` |
| Fix commit | `990b79c89250e4d18045a1dd06b0bd9d002f12bc` |
| Pull request | `#226` |
| CI | PASS；PR #226 共 6 项检查通过 |
| New migration | `20261017_0042_approval_rbac_backfill` |
| Production migration/deploy/restart | Not performed; separate Owner authorization required |

以上 commit、PR 和 CI 均为 GitHub 实际结果，不以本地验证冒充 CI。

## 2. 交付内容

- Approval/WFS canonical page/action 权限及对象/状态边界；
- 支持超级管理员 `*` 的统一 permission helper；
- method-specific permission policy，阻止 page view 吞掉写 action；
- 0042 forward-only 权限目录与既有 grant 回填；
- 真实用户 source-account universe 与用户级数据范围管理；
- 用户资料、启停、角色和数据范围动作分离；
- Product Core 在 ownership PRP 前的 real-superadmin-only fail-closed gate；
- 飞书和密码恢复日志脱敏；
- 前端 Approval、WFS、用户/角色管理的按钮与后端权限一致；
- 权限矩阵、迁移方案、角色授权修复方案和回归测试。

完整文件清单以 PR diff 为准。本 PR 不包含生产配置、生产数据、secret、RAW artifact 或旧系统修改。

## 3. 验证证据

| 检查 | 结果 |
|---|---|
| Backend Ruff format/check | PASS；390 files formatted，lint clean |
| Backend pytest | PASS；`1091 passed, 3 skipped` |
| Backend mypy | BLOCKED BY BASELINE；标准命令因 duplicate module 退出；诊断模式 `399 errors in 59 files`，未伪报通过 |
| Frontend ESLint | PASS |
| Frontend tests | PASS；`35 files / 147 tests` |
| Frontend build | PASS；保留既有大 chunk warning |
| Alembic heads | PASS；单一 `20261017_0042_approval_rbac_backfill` |
| Isolated PostgreSQL 0041→0042 | PASS；权限差异、幂等和 forward-only 阻断已验证 |
| Secret/RAW/scope scan | PASS |
| Rule pack | PASS |
| GitHub CI | PASS；Vercel、Vercel Preview Comments、WFS PostgreSQL migration smoke、backend、frontend、rule-pack-check 共 6 项 |

## 4. 生产执行前授权

必须分别获得 Owner 对以下动作的明确授权：

1. 使用已合并 main 构建和部署；
2. 对生产 PostgreSQL 执行 0042 migration；
3. backend/frontend 滚动部署或服务重启；
4. 为真实角色或用户配置页面、动作或具体 source account；
5. 执行真实账号的发布后 smoke。

本 PR 不授权生产数据库写入、部署、重启、外部 API、Token 请求或同步任务执行。

## 5. 受控发布顺序

1. 备份/snapshot，并核对生产 revision 为 0041；
2. 核对单一 Alembic head 和发布 commit；
3. 执行 0042，按迁移方案验证授权差异；
4. 滚动部署 backend，再部署 frontend；
5. 先以真实超管做只读管理 smoke；
6. 再以普通 admin、operations、warehouse request-only/reviewer 做矩阵 smoke；
7. Owner 仅按批准清单配置具体 `source_account`；
8. 观察授权错误、审计事件与应用错误率后决定是否关闭变更窗口。

旧审批 read 暂留，支持新旧进程滚动；预计无需因 0042 主动停机，但任何重启仍走既有生产审批。

## 6. 发布后验收

- 导航、直接 URL、页面初始化 API 和操作按钮结果一致；
- page view 不赋予 POST/PATCH/DELETE 或审核能力；
- WFS request/review 分离，对象、状态、版本和 source account 同时校验；
- 用户管理 page、profile edit、enable-disable、assign-role、scope 配置分离；
- 普通 admin 不能获得或下放超出自身的权限/范围；
- 用户级范围来源可见、刷新后保持且留下 audit event；
- 授权账号 A 可访问，账号 B 拒绝；空 scope fail closed；
- 飞书失败和密码恢复响应不泄漏 provider body、Token、链接或身份存在性；
- 同步任务和 Celery 行为不受本 PR 影响。

## 7. 停止与恢复条件

立即停止后续步骤：

- migration 非 0041→0042、出现多 head 或权限差异超出计划；
- 普通角色获得 `*`、WFS review 或未知账号范围；
- 受保护路由返回匿名 200，或 page-only 用户能执行写操作；
- 范围外详情/导出可见；
- 日志/响应出现 secret、Authorization、飞书 body 或业务 RAW；
- 生产错误率、401/403 或同步任务异常显著上升。

0042 不支持 destructive downgrade。若 migration 已提交，按 snapshot 恢复方案处理；不得手工改 grant 或
`alembic_version`。如果仅应用部署失败，利用旧 key 兼容性回退应用版本，并保留 0042 等待修复版本。

## 8. 尚未关闭的风险

- 仓库 mypy 基线和 test namespace 冲突未在本 PR 扩大修复；
- 历史空库重放的 Alembic version 列宽问题需单独任务；
- `store/owner/sku/product` 仍是 registry-only；
- Product Core ownership/data scope 需独立 PRP；
- 数据范围 UI 仍为手工输入，缺少脱敏候选选择器。

代码合并不等于生产事故关闭。只有 Owner 授权并完成 migration、部署、真实角色 smoke 和必要配置后，
才能将事故标记为 resolved。

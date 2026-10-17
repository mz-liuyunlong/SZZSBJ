# RBAC v2 0042 生产迁移方案

Status: `ready_for_review`（未合并、未部署、未执行生产迁移）

## 1. 目标和边界

`20261017_0042_rbac_backfill` 修复 0041 之后的权限目录、已有角色授权兼容性和运营计划批次对象范围证据：

- 把已持有 `approvals:workbench:read` 的角色幂等回填到
  `page:data-center:approval-workspace:view`；
- 保留旧审批读取权限，支持新旧应用进程滚动切换；
- 登记本次新增的 canonical page/action/field 权限；
- 不将旧审批审核权限转换为 WFS `archive-review`；
- 不创建角色、用户或超级管理员，不修改角色成员关系；
- 不授予 `source_account='*'`，不写角色级或用户级数据范围；
- 为 `ops_operation_plan_import_batches` 增加非空 JSONB `source_account_refs_json`；新批次保存导入时的账号集合，
  旧批次默认空集合并因此对失败明细导出 fail closed；
- 不修改 0037—0041 历史 migration，不改审批业务数据。

原候选 revision `20261017_0042_approval_rbac_backfill` 长于常见 `varchar(32)`，且从未进入共享环境。
本 PR 将其 revision id 缩短为 27 字符的 `20261017_0042_rbac_backfill`；迁移文件名保留不影响 Alembic。
新建数据库由项目 PostgreSQL Alembic implementation 创建 `varchar(128)` version table，现有生产
`varchar(32)` 不需要且不得手工加宽，短 revision 可直接记录。

合并代码不代表授权执行生产迁移、部署或服务重启。以上动作均需 Owner 单独批准。

## 2. 前置条件

执行人必须在不输出连接串的前提下确认：

1. 已获得本次生产 migration 的明确授权；
2. 部署来源是本 PR 合并后的受审 `main` commit；
3. 当前生产 revision 精确为 `20261016_0041_wfs_rbac_actions`；
4. `alembic heads` 只有 `20261017_0042_rbac_backfill` 一个 head；
5. 只读确认生产 `alembic_version.version_num` 的类型/长度以及当前 0041 值；若不是预期 PostgreSQL
   schema，停止并重新评审，不手工修改版本表；
6. 已完成可恢复的 PostgreSQL snapshot/backup，并记录恢复负责人；
7. 没有其他 migration、运营计划导入或权限管理写任务并发执行；
8. 生产日志、终端输出和变更单不会记录连接串、Token 或业务数据。

任一条件不满足即停止，不得通过手工 SQL 绕过。

## 3. 已完成的隔离 PostgreSQL 演练

本 PR 使用本机一次性 PostgreSQL 集群，仅监听 `127.0.0.1`，未连接生产或共享数据库。

| 检查 | 结果 |
|---|---|
| 空库完整链 | PASS；无需人工预建/加宽版本表；最终 version table 为 `varchar(128)` |
| 生产兼容 0041 基线 | PASS；在隔离库将 version table 明确模拟为 `varchar(32)`，0041 revision 正常存储 |
| 0041 → 0042 | PASS；短 revision 正常写入 `varchar(32)`，没有 DDL 成功但 revision 写入失败 |
| 旧审批 read 已授权角色 | migration 前 3 条；admin、operations、warehouse 的 canonical page grant 从各 0 变为各 1 |
| 旧审批 read 保留 | PASS |
| WFS 高风险审核 | 未扩权；operations、warehouse 仍为 0，既有 admin 保持 1 |
| finance / purchase | 未新增审批授权 |
| 角色/用户数据范围 | 未新增或修改 |
| grant 总量 | 49 → 52；仅新增上述 3 条审批 canonical grant |
| 其他 legacy 映射 | 真实 0041 演练中 `products:read` 已由 0039 清理为 0；其余候选旧 key 无目录/授权来源，匹配均为 0，不产生 grant |
| 新 Order Profit field 权限 | 目录存在；角色 grant 为 0，不推测授权 |
| 幂等重放回填 | PASS；第二次 `upgrade head` 后 canonical approval 仍 3、总 grant 仍 52 |
| downgrade | 按设计阻断，revision 保持 0042 |

0042 未尝试从 0039 已删除的授权“猜回”业务角色。0038 已完成既有 catalog 内 legacy→canonical
复制；0042 只有仍保留来源的 Approval legacy grant 能产生实际回填。其他新增 action/field 必须由 Owner
按职责配置，不能由 migration 根据角色名推断。

## 4. 受控执行顺序

1. 进入维护变更窗口，停止权限配置写操作；业务读流量无需因本 migration 主动停机。
2. 只读记录当前 revision、单一 head、目标权限 grant 数量和快照标识。
3. 执行一次 `alembic upgrade 20261017_0042_rbac_backfill`。
4. 只读核对当前 revision、canonical 权限目录、回填角色和未扩权角色。
5. 部署与 migration 兼容的 backend，再部署 frontend；旧 read key 暂留，允许滚动部署。
6. 按超级管理员、普通管理员、operations、warehouse 的顺序执行只读 smoke。
7. 观察 401/403、权限审计事件和错误率；不得把配置缺失当作代码错误而临时扩权。

0042 增加少量权限目录/grant，并为运营计划导入批次增加一个带常量默认值的 JSONB 列。隔离 PostgreSQL
演练已通过，但生产锁等待仍需在变更窗口观察；不得据此保证零锁等待或自动执行。进程重启/滚动部署仍属于
生产操作，必须使用既有发布流程并获得授权。

## 5. 预期差异

升级后只允许出现以下授权变化：

- 每个原本拥有 `approvals:workbench:read` 的角色新增一个
  `page:data-center:approval-workspace:view` grant；
- canonical action/field 目录项存在，但没有推测性角色 grant；
- 旧 `approvals:workbench:read` grant 继续存在。
- `ops_operation_plan_import_batches.source_account_refs_json` 存在；旧行为空数组，新导入批次由应用写入
  实际账号集合。旧批次失败明细不能导出是预期 fail-closed 行为。

出现以下任一情况必须停止发布：

- 普通角色新增 `*` 或未批准的 WFS review/action；
- 角色/用户 `source_account` 范围发生变化；
- grant 数超过旧 read 授权角色数量；
- Alembic 出现多个 head、revision 不是预期值或 migration 报错；
- 发现业务表、用户角色、审批记录或同步任务被修改。

## 6. 回滚和恢复策略

0042 是 forward-only migration，`downgrade()` 会明确失败，避免删除正在使用的 canonical 授权或制造滚动部署断链。
不能把 `alembic downgrade` 当作生产恢复手段。

失败恢复顺序：

1. 若 transaction 未提交，确认数据库已经自动回滚并停止；
2. 若已提交但应用尚未部署，可继续运行旧应用，因为旧 key 仍保留；
3. 若需撤销已提交变更，先停止权限写入，再由 DBA/Owner 评估从 snapshot 恢复；
4. 不允许临时删除 grant、改 `alembic_version` 或手工补写权限；
5. 恢复后重新核对 revision、角色 grant、用户/角色 scope 和审批业务数据。

## 7. 发布后只读验收

- 真实超级管理员 `*` 可通过统一 `has_permission()`；普通 `admin` 不自动获得超管能力；
- operations/warehouse 若此前有旧审批 read，可打开审批工作台；
- 只有页面 view 不能审核 WFS 归档；
- `archive-request` 与 `archive-review` 相互独立；
- 未配置 `source_account` 的业务请求仍返回 `DATA_SCOPE_DENIED`；
- 只有 Owner 确认的账号范围可通过用户/角色管理 UI 配置；
- 飞书失败日志不含 provider body、消息、Token、重置链接或异常原文。

生产事故只有在 migration、部署、角色只读 smoke 和必要的 Owner 授权配置全部完成后才能关闭。

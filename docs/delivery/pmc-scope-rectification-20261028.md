# PMC 范围整改与本地验收

日期：2026-10-28。工作分支 develop；整改基于 dde422f。只读更新远端引用后，main 为 bf0ccfd；新增的 Walmart 集成文件没有在本轮修改或覆盖。此记录取代同日集成审查中“保留采购父子调度”的建议。

## 公共模块撤回证据

以下命令在本地工作树执行，输出为空：

```powershell
git diff origin/main --name-only -- backend/app/modules/integration_sync frontend/src/pages/data-center frontend/src/config/navigation.ts backend/app/core/config.py backend/.env.example
git diff HEAD --name-only -- backend/alembic
```

统一任务执行、调度、管理和重试恢复、采购/国内仓同步 handler、任务中心列表/配置/日志/API、全局导航、公共 Settings 及示例配置恢复 main。采购父子任务实现、bootstrap、专用页面测试及专用帮助文档撤回；登记表改为已撤回。没有修改现有任务配置、启停任务或运行真实同步。旧采购任务不会再经过本分支新增的父任务接管判断。

恢复 main 表示公共行为交回统一任务中心负责人；不声称修复 main 自身可能存在的任务中心错误处理问题。

## 保留的 PMC 修复

- 审批列表恢复修改、审批通过、驳回入口；只读权限下不可执行写入。
- 审批和驳回均强制检查非空口令。缺失口令在业务服务创建前拒绝；后端既有动作权限和账号 scope 保留，审计主体来自登录用户，不使用提交的显示姓名授权。
- 取消硬编码审批人名单，前端显示当前登录用户。
- PMC 私有口令模块读取既有口令摘要配置；失败预算使用既有 Redis broker，通过 Lua 原子预留/释放，在多个 API worker 间共享。每个用户每个固定十分钟窗口最多保留十次失败计数，key 设置二十分钟过期；这不是滑动窗口。计数服务不可用返回 503，不退回进程内计数或跳过验证。
- 恢复入库看板“超发待补入库”提示卡。没有查到负责人要求删除的明确依据。
- 恢复完整审批/驳回/生成 PK/审计浏览器用例，补充保存与刷新草稿的合成浏览器回归；真实 PostgreSQL 用例补充驳回后不增加库存占用的断言。

没有更改服务器或真实环境配置。审批上线前需要负责人核实口令摘要配置与 Redis 可用性；缺少任一项将拒绝审批。

## 迁移清单（本轮没有修改）

| 完整 revision | 上游 | 数据库影响 |
|---|---|---|
| `20261026_0055_purchase_board_draft_no` | `20261022_0054_merge_walmart_identity_and_domestic_packing` | `dwd_purchase_order_line_item`、`dws_purchase_board` 各增加可空 `draft_no varchar(64)`；无新索引、约束或数据回填 |
| `20261027_0061_merge_purchase_main` | 上述采购 0055 与 `20261026_0060_merge_listing_business_heads` | 合并依赖；没有业务表 DDL |
| `20261028_0062_packing_pending_edit` | 上述 0061 | 创建 `ops_domestic_packing_pending_edits`：candidate_id UUID 主键，source_account_ref varchar(128)，base_candidate_version varchar(64)，requested_qty integer，customs varchar(16)，edit_reason varchar(500) 可空，draft_snapshot_json JSONB，actor_uid varchar(128)，updated_at timestamptz；其余列非空。CHECK：数量 1–1000000、报关枚举 default/declare/skip；账号单列索引；无外键 |
| `20261028_0067_merge_pmc_main` | 国内仓 0062 与 `20261028_0066_walmart_monitor_listing_projection` | 合并依赖；没有业务表 DDL |

完整 revision ID 保留，数字前缀重复不等于完整 ID 冲突；最终依赖仍需数据库负责人审核。没有连接生产库，因此各版本的实际生产执行状态、同名表/字段及版本列长度均未确认。若已经存在同名表/字段，现有 DDL 会报错，不得用 stamp 绕过，也不得猜测为结构一致。

负责人可在已授权只读会话中检查：

```sql
BEGIN READ ONLY;
SELECT version_num FROM public.alembic_version ORDER BY version_num;
SELECT table_name, column_name, data_type, character_maximum_length
FROM information_schema.columns
WHERE table_schema = 'public'
  AND ((table_name = 'alembic_version' AND column_name = 'version_num')
    OR (table_name IN ('dwd_purchase_order_line_item','dws_purchase_board')
        AND column_name = 'draft_no')
    OR table_name = 'ops_domestic_packing_pending_edits');
ROLLBACK;
```

## 本地测试与未完成验收

- pytest：口令校验、旧采购同步、服务调度、调度工作流、Alembic 静态链合计 **55 passed**。
- 审批表格 Vitest：**3 passed**，包含审批和驳回入口。此前审批目录其他文件已通过；表格定位问题修正后单独重跑通过。
- Playwright Edge：**5 passed**，覆盖草稿保存刷新、只读与请求错误、审批通过、驳回、生成 PK、审批历史及审计详情。这些是合成接口响应测试，不代表真实数据库业务验收。
- PMC 前端 ESLint 通过；TypeScript 构建检查通过；后端 Ruff 检查通过，755 个文件格式检查通过。
- 新增 Redis 多客户端并发计数测试，纳入国内仓 PostgreSQL CI job；CI 使用 Redis 7 service。它只用于隔离测试，不修改运行时调度逻辑。
- 新 PostgreSQL 业务断言和 Redis 并发测试尚未实际执行。本地临时 PostgreSQL initdb 被权限阻止，Docker 引擎未启动；没有连接现有业务库替代测试，也没有启动 Docker 服务。
- 不以之前提交的绿色 CI 作为当前未提交整改的验证。远端全量 CI 尚未执行，必须先获得本轮提交/push 的明确确认。

## 验收状态

本地整改待负责人审核；PR 保持 Draft。本轮没有提交、push、更新 PR、合并或部署。没有执行生产查询、迁移、stamp、业务写入或修改真实环境文件。代码合并和生产迁移均未授权。最终全量 CI、真实 PostgreSQL/Redis 验证及数据库负责人依赖审查完成前，不建议标记最终验收通过。

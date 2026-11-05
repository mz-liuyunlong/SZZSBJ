# 财务 · 飞书审批单同步 数据源决策

- 调查日期：2026-11-05
- 调查人：Rocky 侧代码 AI（财务板块）
- 目标 method/path：`GET /api/finance/cashflow/approvals`、`GET /api/finance/cashflow/approvals/sync`、`POST /api/finance/cashflow/approvals/sync`
- 业务用途：财务在日记账上把付款流水和飞书资金类审批单（费用报销、付款申请、备用金申请、备用金核销）对起来，看金额差额，找出审批过却没有付款流水的单。
- 接口总体状态：**READY_FOR_PRP**
- 结论：**飞书只读同步，`SOURCE_SYNC`**
- 是否包含 NEED_OWNER_DECISION：否
- 负责人批准状态：已批准（rocky 2026-11-05）
- 关联 PRP：`PRPs/finance-journal-approvals-v1.md`
- 关联证据：
  - 业务原型（Rocky 侧工作区，不在仓库）：财务 Demo 的审批单对账，由部署 AI 人工跑脚本拉取。
  - 生产只读探测（2026-11-05，rocky 授权）：生产飞书应用的审批实例列表用 GET、毫秒时间戳、不超过 30 天的窗口，四类审批全部返回成功；实例详情可读。此前的 400 是请求方法用错（POST）。
  - 员工表匹配探测（2026-11-05，生产只读，rocky 授权）：最近 29 天的申请人全部能在 `app_users.feishu_user_id` 匹配到姓名。
  - 规则：`docs/delivery/backend-data-source-decision-gate.md`、`docs/data-sources/database-layering-standard.md`、`docs/data-sources/field-standardization-standard.md`。

## 1. 旧系统与来源调查（强制前置）

| 前置调查项 | 证据位置与调查结论 |
|---|---|
| 旧页面 | 旧系统没有审批单对账页面；Demo 是唯一业务原型。不适用迁移。 |
| 旧 API | 无。不适用。 |
| 旧接口文件位置 | 无。不适用。 |
| 读取表 | 新系统原来没有审批单表。本决策新建 `std_finance_feishu_approvals`。 |
| 表写入方 | 唯一写入方是任务中心的财务审批单同步任务。 |
| cron / 脚本 / 外部 API | 飞书开放平台只读接口：取应用 token、审批实例列表、审批实例详情。本期不建定时任务。Demo 的人工拉数脚本只是原型过渡，正式系统不依赖。 |
| 人工写库入口 | 无。审批单不能在系统里改；财务只能挂单、摘单，这些写在人工状态表。 |
| 外部平台重新获取可能性 | 可以：飞书保留实例，同步可重复执行，按实例编码覆盖。 |
| 少量配置数据可行性 | 审批定义编码和排除部门走环境变量，不进仓库。 |
| 短期策略 | 手动同步（本决策）。 |
| 长期策略 | 任务中心打开定时后自动同步，处理逻辑不变。 |

## 2. 数据集分类

| 数据集 | 层 | 对象 | 分类 | 权威来源 | 必要约束 |
|---|---|---|---|---|---|
| A 审批单 | L3 Standardized | `std_finance_feishu_approvals` | `SOURCE_SYNC` | 飞书审批实例 | 主键是实例编码，单号唯一；收款账号只存尾号；不存附件链接；不存姓名 |
| B 同步运行记录 | L12 Audit | `gov_integration_sync_runs`、`gov_integration_sync_run_work_items` | `NEW_SYSTEM_OWNED` | 任务中心 | 错误只记接口名、HTTP 状态和飞书错误码 |
| C 挂单结果 | Manual layer | `manual_finance_cash_line_state`、`evt_finance_cash_line_reviews` | `NEW_SYSTEM_OWNED` | 自动挂单和财务操作 | 自动挂单留 `auto_attach_ref` 事件；财务摘过的组合不再自动挂 |
| D 员工姓名 | 既有 | `app_users` | 既有 IAM 数据，只读 | 系统员工表 | 按 `feishu_user_id` 匹配，读取时现查，匹配不到显示编号 |

不保留飞书原始响应，因为其中有完整银行账号和临时下载链接。没有 `READ_LEGACY_TEMPORARILY`，没有 `MIGRATE_ONCE`。

## 3. 字段口径

| 字段 | 规则 |
|---|---|
| 单号 | 飞书 `serial_number` |
| 飞书状态 | 飞书原值；已同意但被撤销的单记为已撤销，按已取消处理 |
| 发起、完成时间 | 飞书毫秒时间戳，存带时区时间，页面按 Asia/Shanghai 显示 |
| 办理时间 | 审批记录里办理节点通过的最晚时间 |
| 金额 | 按类型取对应金额控件，转 Decimal 后存 `numeric(18,4)`，不经浮点运算 |
| 币种 | 金额控件的币种，缺失时看明细，再缺失按 CNY |
| 收款人 | 收款人控件，缺失时用收款账户控件的户名 |
| 账号尾号 | 收款账户控件账号的数字部分末 4 位；完整账号解析后丢弃 |
| 附件 | 只留来源、控件名、标题、是否图片、明细序号 |

## 4. 权限与敏感性

- 全部接口只有超级管理员，不新增权限点。
- 收款人、事由、审批记录属于敏感内容，不进日志和错误信息。
- 飞书凭证只从现有配置读取，不打印。审批定义编码和排除部门只放环境变量。
- 测试和文档只用合成数据，不写真实部门、人名、ID。

## 5. 质量与控制

- 每次同步在运行记录里留取到条数、写入条数和错误码。
- 没配置审批定义编码时明确报错，不静默跳过。
- 单张详情结构解析不了时，这次同步失败并记错误码，已写入的单保留。

## 6. 退出条件 / 风险

- 不依赖旧库，无退出条件。
- 飞书表单改字段名时，对应字段会变空，靠核对同步结果发现。
- 首次生产同步在上线后进行，每步需 rocky 书面授权。

## 负责人决定

已批准（rocky 2026-11-05）。

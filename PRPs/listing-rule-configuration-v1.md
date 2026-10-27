# PRP: Listing 管理「规则配置」V1.0（待负责人审批）

- 日期：2026-10-25
- 状态：**待项目负责人确认；禁止开始功能代码实现**
- 数据源决策：`docs/data-sources/decisions/listing-rule-configuration-decision.md`
- 主执行切片：**Listing 等级评级配置**。生命周期、库存修复、运营跟进分组仅作为后续设计，不在本 PR 实现。

## 1. Goal / Why

在现有「产品 → Listing 管理」工具栏中新增「规则配置」入口，打开宽抽屉，让有权限的管理者查看并修改 Listing 等级评级参数；保留不可变规则版本、修改原因和操作审计。**本任务只做配置能力，不启用新的评级算法，不运行迁移或任何生产写入**。

## 2. Scope

### In scope（实现获批后）
- 现有 Listing 页面右上工具栏按钮、抽屉；保留原有搜索、列配置、导出操作及顺序。
- 四个分组的导航设计：等级评级可编辑；生命周期、库存与修复、运营跟进在 V1.0 显示**只读规则摘要及「后续版本」说明**，不提供假保存。
- 第一切片可编辑项：短/中窗口默认 7/14 天；权重 60%/40%；最低有效日 4/8；等级阈值 5/10/15%；纳入生命周期默认打品、启动、上升、稳定、下滑、修复。测品、断货可选；清货、归档永久排除。
- 全局统一配置，版本化、权限、审计记录、输入校验、变更原因、保存成功/失败反馈及历史列表。
- UI：加载、空态、错误、只读、禁用、冲突刷新、未保存更改确认；使用 Ant Design/ProComponents，保留 PageShell 帮助入口。
- 单元/API/E2E 测试、API 文档、SOP、交接。

### Out of scope
- 直接计算/写入 Listing 等级、每天 22:30 定时计算、C/D 运营日志生成。
- 历史财务数据回填、RAW JSON 扫描、真实领星/Walmart API、任何生产数据库变更。
- 生命周期数值阈值的在线修改；WFS 库存快照机制；清货/归档审批变更。
- 修改 `old-system/**`、页面导航结构、已有费用规则模型。

## 3. Navigation / Page
- 一级导航：产品
- 二级导航：Listing 管理
- 现有页面：`frontend/src/pages/products/ListingManagementPage.tsx`
- 现有工具栏：`frontend/src/pages/products/components/ListingManagementToolbar.tsx`
- 新组件（建议）：`frontend/src/pages/products/components/ListingRuleConfigDrawer.tsx`
- 页面状态：planned（待审批）；没有独立导航页面。

## 4. Permissions
- 页面查看：现有 `page:products:listing-management:view`（由 IAM 目录定义）。
- 配置写入：新增 `action:products:listing-management:configure-rules`，必须由后端强制检查。
- 变更历史：建议与配置查看权限分开评审，审批时确定最终权限 Key。
- 数据作用域：全局统一规则，不按单店铺分别配置；仅授权人员写入。
- 高风险：版本生效前二次确认、修改原因、审计、禁止追溯覆盖历史。

## 5. Data Source
- 决策文件：`docs/data-sources/decisions/listing-rule-configuration-decision.md`
- 状态：READY_FOR_PRP（仅数据源所有权就绪）；**owner approval status: pending**
- 分类：NEW_SYSTEM_OWNED；新 PostgreSQL 版本化配置与变更记录。
- 旧库、旧系统：不依赖、不写入。
- 财务、广告与评级结果：本任务不接入，交给未来评级引擎的单独 PRP 和数据源决策。

## 6. API Contract（提议，待审批）
- `GET /api/listing-rule-config`：当前生效规则及版本、固定保护项、配置来源；需要 Listing 查看权限。
- `PUT /api/listing-rule-config`：参数、expected_version、change_reason；后台鉴权、验证后新增版本；需要 configure-rules 权限。
- `GET /api/listing-rule-config/history`：分页规则版本及审计信息；限定查看权限。
- 所有 API 使用项目统一 `{success,data,error,meta,request_id}`，FastAPI response_model 和结构化错误码。
- 主要错误：`LISTING_RULE_INVALID_WEIGHT`、`LISTING_RULE_INVALID_WINDOW`、`LISTING_RULE_INVALID_THRESHOLD`、`LISTING_RULE_IMMUTABLE_FIELD`、`LISTING_RULE_VERSION_CONFLICT`、403。
- API 参数和响应需要 Pydantic 明确 schema，不允许 `Any` 任意接收与覆盖系统字段。

## 7. Hard invariants
- 定时评级时区 `Asia/Shanghai`，22:30；业务日 `America/Los_Angeles`，统计截止日 T-2；四项暂不开放修改。
- 先汇总有效日销售及利润，再按 7/14 窗口 60/40 计算；只用 ERP「每日销售」统一利润口径。
- 广告和必要成本未知不得视作零；这是一条固定财务边界，不是用户可关闭开关。
- D <5%，C [5%,10%)，B [10%,15%]，A >15%；零销售且真实亏损的特殊 D 规则不可因配置编辑丢失。
- 配置保存不自动启动评级重算、同步或历史回填；历史规则只增版本，不原位覆盖。

## 8. Implementation slices（负责人批准后执行）
1. 后端切片：schema、service、repository、版本化 model、Alembic 迁移（**仅提交迁移文件，不执行生产迁移**）、权限与审计、API 单测及 Markdown API 文档。
2. 前端切片：独立抽屉组件、API client、UI 测试及 PageShell SOP。
3. 集成与验收：仅本地隔离环境跑 pytest、ruff、npm lint/typecheck/test/build/E2E，检查权限、版本冲突、受保护字段、重复保存及回滚说明。

每个切片可独立 PR；不得以一个 PR 同时把生命周期引擎、评级定时任务和运营日志都重写。

## 9. Acceptance checklist
- [ ] 负责人批准 PRP 和拟议 API/权限方案
- [ ] Listing 原工具栏功能不回归；新增规则配置按钮不修改左侧导航
- [ ] 查看与编辑权限由 IAM 动态配置，后端拒绝越权
- [ ] 参数联动校验：权重合计100、有效天数≤窗口、阈值递增
- [ ] 清货/已归档无法纳入评级
- [ ] 22:30/T-2/业务时区不可通过表单更改
- [ ] 修改记录生成不可变版本，含原因、操作者、生效时间
- [ ] 不影响原利润与同步，不自动重算历史
- [ ] API 契约、单元测试、E2E、SOP 和帮助入口完备
- [ ] lint/typecheck/test/build/pytest/ruff 通过（**本规划 PR 不声称通过**）
- [ ] `CODEX_HANDOFF.md` 及完成报告更新（功能完成时）
- [ ] 不修改 `old-system/**`、`.env` 或生产服务

## 10. Rollback
- 配置版本以新增版本进行回滚，保留历史及审计；不删除旧版。
- 代码可独立回退该功能切片；禁止手工删除生产库表或直接写生产数据。
- 第一切片未获批准、未实施前无需回滚业务数据。

## 11. Owner approval requested
请项目负责人确认：本 PRP 的第一开发切片范围、`configure-rules` 权限设计、全局统一配置及下一次评级周期生效。**确认后才开始代码实现。**

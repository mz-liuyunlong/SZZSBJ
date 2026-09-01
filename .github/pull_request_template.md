# Pull Request

## 本次修改目的

请说明这个 PR 解决什么问题。

---

## 单功能开发确认

- [ ] 本 PR 只处理一个功能。
- [ ] 本 PR 最多只新增或修改一个页面。
- [ ] 本 PR 没有顺手开发其他模块。
- [ ] 本 PR 没有大范围重构。
- [ ] 本 PR 没有修改无关公共组件。
- [ ] 如修改了共享代码，已说明原因和影响范围。

---

## old-system 只读确认

- [ ] 本 PR 没有修改 `old-system/`。
- [ ] 本 PR 没有从 `old-system/` 直接复制代码。
- [ ] 如参考了 `old-system/`，已说明读取了哪些文件。
- [ ] 如参考了 `old-system/`，已将业务规则重新设计到新系统。

---

## 修改范围

- [ ] 前端
- [ ] 后端
- [ ] 数据库
- [ ] Celery 后台任务
- [ ] 外部 API
- [ ] LLM 调用层
- [ ] 权限 / 操作日志
- [ ] 数据来源 / 字段血缘
- [ ] 财务计算
- [ ] 性能优化
- [ ] 文档
- [ ] 测试

---

## 组件与模块封装

- [ ] 页面没有写成大文件。
- [ ] API 请求已封装。
- [ ] 类型已独立定义。
- [ ] 后端按 Route / Schema / Service / Repository 分层。
- [ ] 如新增 Shared 组件，已更新 `docs/UI_COMPONENT_CATALOG.md`。
- [ ] 如新增后端通用模块，已更新 `docs/BACKEND_MODULE_CATALOG.md`。

---

## 数据、财务、性能确认

- [ ] 字段来源已说明。
- [ ] 财务公式已确认。
- [ ] 金额币种明确。
- [ ] 时间时区明确。
- [ ] 大表查询已分页或说明性能处理。
- [ ] 外部 API 批量调用已考虑限流 / Celery。

---

## Skill 使用确认

- [ ] 本 PR 开发前已进行 Skill 自发现判断。
- [ ] 本 PR 已说明本次使用了哪些 Skill 以及选择原因。
- [ ] 本 PR 只读取了本次任务相关的 Skill，没有无意义全文读取全部 Skill。
- [ ] 本 PR 已读取相关项目规则。
- [ ] 如涉及页面开发，已读取 `skills/feature-slice-planner/SKILL.md`。
- [ ] 如涉及组件拆分，已读取 `skills/react-component-architect/SKILL.md`。
- [ ] 如涉及 old-system，已读取 `skills/old-system-readonly-analyzer/SKILL.md`。
- [ ] 如涉及后端模块，已读取 `skills/backend-module-designer/SKILL.md`。
- [ ] 如涉及后台任务，已读取 `skills/background-task-designer/SKILL.md`。
- [ ] 如涉及数据血缘，已读取 `skills/data-lineage-analyzer/SKILL.md`。
- [ ] 如涉及财务计算，已读取 `skills/financial-calculation-reviewer/SKILL.md`。
- [ ] 如涉及性能，已读取 `skills/performance-reviewer/SKILL.md`。

---

## API 契约

- [ ] 无 API 变更。
- [ ] 有 API 变更，契约如下：

---

## 数据库变更

- [ ] 无数据库变更。
- [ ] 有数据库变更，migration 文件为：

兼容性说明：

---

## 配置 / 依赖变更

- [ ] 无配置变更。
- [ ] 无新增依赖。
- [ ] 有配置或依赖变更，说明如下：

---

## 测试结果

执行命令：

```bash

```

结果：

```text

```

如未执行测试，请说明原因：

---

## AI 参与说明

- [ ] 本 PR 未使用 AI。
- [ ] 本 PR 使用了 AI 辅助。

AI 工具名称：

AI 参与范围：

- [ ] 需求拆解
- [ ] 代码生成
- [ ] 代码修改
- [ ] 测试建议
- [ ] 文档编写
- [ ] Code Review

---

## 风险点

1.
2.
3.

---

## 回滚方式

```bash
git revert <commit-id>
```

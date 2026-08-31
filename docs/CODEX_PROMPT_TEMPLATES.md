# Codex 提示词模板

## 单页面开发模板

```md
本次只开发一个页面：{页面名称}。

请先读取：
1. AGENTS.md
2. docs/FEATURE_SLICE_DEVELOPMENT_RULES.md
3. docs/COMPONENT_AND_MODULE_RULES.md
4. docs/CODE_COMMENT_RULES.md
5. docs/API_CONTRACT_RULES.md
6. skills/feature-slice-planner/SKILL.md
7. skills/react-component-architect/SKILL.md

要求：
1. 只处理这个页面，不开发其他页面。
2. 页面不能写成大文件。
3. 先输出组件拆分方案和后端模块拆分方案。
4. API 契约先给我确认。
5. 如需参考 old-system，只读分析后先输出方案。
6. 用户确认前不要改代码。
```

## old-system 分析模板

```md
请只读分析 old-system 中与 {功能} 相关的代码。

必须遵守：
1. 不修改 old-system。
2. 不复制旧代码。
3. 不运行写数据库脚本。
4. 输出读取文件清单、旧逻辑、数据来源、风险、新系统重建建议。
5. 分析结果写入 docs/old-system-analysis/，不要写回 old-system。
```

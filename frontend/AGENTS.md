# Frontend AGENTS.md

本文件适用于 `frontend/` 下所有前端开发。

## 技术栈

- React
- TypeScript
- Vite
- Ant Design
- ProComponents
- React Router
- Zustand
- ECharts

## 规则

1. 页面负责组合，不堆复杂逻辑。
2. API 调用必须封装。
3. 类型必须明确，避免 `any`。
4. 优先复用 `docs/UI_COMPONENT_CATALOG.md` 中的组件。
5. 多页面重复 UI 必须考虑抽成 Shared 组件。
6. 页面专属组件放入 feature 目录。
7. Shared 组件不得包含具体业务模块逻辑。
8. 所有数据页必须处理 Loading / Empty / Error / Pagination。
9. 不允许前端直接调用敏感外部 API。
10. 不允许从 `old-system/` import 代码。

开发页面前，先读取 `skills/react-component-architect/SKILL.md`。

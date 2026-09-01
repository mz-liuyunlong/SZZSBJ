# Vercel Agent Skills Standard — Project Rule Pack V1.0

## 1. Positioning

Vercel Agent Skills 是可选 AI 审查辅助工具，用于 React、UI、组件组合、文档和 Vercel 部署后优化分析。

它不是 本项目 生产依赖。

## 2. Recommended skills

| Skill | Use |
|---|---|
| react-best-practices | React / Next.js 性能和组件审查 |
| web-design-guidelines | UI、可访问性、表单、交互审查 |
| composition-patterns | 组件组合与抽象审查 |
| writing-guidelines | SOP、API 文档、帮助文档审查 |
| vercel-optimize | 部署到 Vercel 后的成本、性能、缓存分析 |

## 3. Forbidden by default

`vercel-deploy-claimable` 默认禁止使用。未经项目负责人明确批准，不允许 AI 自动部署、生成外部访问地址或 claim URL。

## 4. Rules

```text
不加入 frontend/backend 生产依赖
不写入 Dockerfile
不作为 CI 必装
不覆盖 Project Rule Pack
不跳过 Playwright / pytest / lint
不以审查建议替代项目负责人确认
```

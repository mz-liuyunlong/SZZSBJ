# Frontend Page Scaffold Rules

## Required Flow

1. 确认 PRP、Page Spec、navigation/route 和 Page Registry 状态。
2. 输出 Component Reuse Plan。
3. 复用 `PageShell`、既有 layout、设计 token 和适用 Shared 组件。
4. 只实现批准的 loading/empty/error/permission/no-api/data states。
5. 添加最小测试、视觉验收和 registry/catalog 更新。

## Boundaries

- 不复制 navigation metadata、breadcrumb、permission 或第二套路由。
- No-API 壳不创建假业务列表、不假装保存/同步成功、不持久化未批准数据。
- Page scaffold 不自动授权后端 API、业务字段、权限、E2E 依赖或 Shared 组件扩建。
- 页面局部组件保持局部；真实跨页复用出现后再提升。

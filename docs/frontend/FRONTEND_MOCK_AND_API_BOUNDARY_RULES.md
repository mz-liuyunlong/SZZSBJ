# Frontend Mock and API Boundary Rules

## Required Rules

- `mock_only`、`no_api` 和真实 `api_connected` 三种状态必须在代码、测试、UI 文案和 Page Registry 中一致。
- Mock 数据集中在明确 mocks/fixtures，仅用于测试或批准的演示；不得散落页面、冒充生产数据或成为 API contract 真源。
- No-API 页面可展示结构、空状态和待接入提示，但不得假装查询、保存、同步、导入或删除成功。
- 接入真实 API 前必须有批准的 backend contract、Source Decision（如适用）、permission/data scope、error/freshness 行为和 registry 更新。
- 前端不得直接调用外部平台或在浏览器保存 secret。
- 移除 mock 必须与真实 API 接入同任务明确处理，禁止静默 fallback。

现有登录 mock 等批准例外按其 PRP 边界维护，不得推广为真实认证模式。

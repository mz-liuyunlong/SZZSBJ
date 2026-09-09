# Frontend Page Registry Rules

## Required Rules

- `docs/frontend/PAGE_REGISTRY.md` 是页面依赖和状态登记入口；navigation 配置仍是菜单 metadata 真源。
- 每个页面记录 Page Key/Name、一级/二级导航、Route、Status、Components、Backend API、Read Model、Permission、PRP、PR 和 Notes。
- 新页面或上述字段变化必须同 PR 更新 registry。
- `no_api/mock_only/display_only` 必须显著标记；接 API 后才能使用 `api_connected`。
- Registry 不复制完整 navigation metadata，不替代 API contract 或 Data Interface Registry。

## Stop Conditions

导航变更未获批准、API/read model 不存在、permission 不明确或状态缺证据时停止并保持 planned/candidate。

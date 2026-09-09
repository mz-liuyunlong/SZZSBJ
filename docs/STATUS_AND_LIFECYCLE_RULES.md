# Status and Lifecycle Rules

## Canonical Statuses

| Status | Meaning |
|---|---|
| `draft` | 草案，等待 Review/确认 |
| `planned` | 已规划，尚未批准实现 |
| `candidate` | 候选，证据或决定不足 |
| `approved` | 精确范围已批准，不等于实现 |
| `implemented` | 已合并且有验证证据 |
| `blocked` | 存在明确阻塞项 |
| `deprecated` | 仍存在但不应新增使用 |
| `superseded` | 已被另一决定或能力取代 |
| `historical_reference_only` | 仅保留历史上下文 |
| `legacy_reference` | 旧系统只读证据，不是新系统权威 |
| `no_api` | 页面/能力无真实 API |
| `mock_only` | 仅本地模拟，不是真实业务流程 |
| `display_only` | 只展示，不产生权威结果 |
| `api_connected` | 已连接获批的新系统 API；不自动代表业务 ready |

## Hard Rules

- Planned is not implemented.
- Future scope is not current scope.
- Mentioned is not approved.
- Approved is not automatically authorized for execution.
- Mock/no-API/display-only 状态必须在 UI、文档和测试中明确。
- 状态变化必须引用负责人决定或 PR/测试证据，不得靠聊天推断。
- `superseded` 和 `historical_reference_only` 内容不得被重新当作实现授权。

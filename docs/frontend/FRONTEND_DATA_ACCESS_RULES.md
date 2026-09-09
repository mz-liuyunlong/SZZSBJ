# Frontend Data Access Rules

## Required Rules

- 前端只调用新系统 FastAPI；不得直接访问数据库、RAW、对象存储或领星/Walmart/飞书等外部平台。
- API 字段来自已批准后端 contract/types；前端不得自行定义权威业务字段、公式或 fallback。
- Mock 字段必须集中、明确 `mock_only`，不能冒充真实 contract/data。
- 权限、data scope、字段脱敏和权威计算由后端执行；前端隐藏只改善体验。
- 请求必须处理 loading、empty、error、permission、stale/partial 和 cancellation/race。
- 页面接入或改变真实数据时，同 PR 更新 Data Interface Registry、Page Registry 和相关 contract。

## Stop Conditions

后端 API、字段语义、权限、新鲜度或错误 contract 未批准时，保留 no-api 壳并停止真实接入。

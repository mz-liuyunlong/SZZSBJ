# Data Interface Registry

Registry Status: `draft; approved only after owner review and merge`

## Registry Rules Summary

- GitHub 中本文件是真源；外部表格仅是只读镜像。
- 空表不表示能力不存在；条目只有在 PR 合并且验证通过后才可为 `implemented`。
- 未知值写 `TBD` 并保持 `candidate/blocked`；Secret 只写 `secret_ref`。

## External Interface Registry

| Interface ID | Provider | Interface Name | Direction | Method | Endpoint / Source Path | Auth Type | Secret Ref | Business Purpose | Platform / Store Scope | Sync Type | Sync Cadence | RAW Required | RAW Storage Location | Standardized Layer | Core Table | Read Model | Backend API | Frontend Page | Permission Key | Owner | Status | PRP | PR | Last Updated | Risk / Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

## Internal Backend API Registry

| API ID | Method | Route | Purpose | Source Layer | Read Model / Table | Permission Key | Data Scope | Frontend Page | Status | PRP | PR | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |  |  |  |  |

## Storage / Table / Read Model Registry

| Storage ID | Layer | Object Name | Purpose | Authority Level | Source Interface | Write Owner | Read Owner | Retention | Permission / Sensitivity | Status | PRP | PR | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |

## Frontend Usage Registry

| Page Key | Page Name | Data Dependency | Backend API | Read Model | Display-only Calculation | Mock Status | Permission Key | Status | PRP | PR | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |  |  |  |

## Sync / Import / Export Registry

| Flow ID | Type | Source Interface / File | RAW Location | Target Layer / Object | Run / Batch ID | Idempotency Key | Cadence / Trigger | Permission Key | Owner | Status | PRP | PR | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |

## Notification / Webhook Registry

| Notification ID | Provider | Purpose | Source Event | Secret Ref | Recipient Scope | Dedup / Cooldown | Permission Key | Owner | Status | PRP | PR | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |  |  |  |  |

## Status Definitions

| Status | Meaning |
|---|---|
| `planned` | 已规划，未批准实现 |
| `candidate` | 候选，证据不足 |
| `approved` | 精确范围获批，未必实现 |
| `implemented` | 已合并并有验证证据 |
| `blocked` | 存在明确阻塞 |
| `deprecated` | 不再新增使用 |
| `superseded` | 已被另一条目取代 |

## Update Checklist

- [ ] 状态有 PRP/PR 或负责人决定证据。
- [ ] 来源、RAW、目标层、读写方和前端依赖可追溯。
- [ ] 权限、data scope、敏感性和 freshness 已说明。
- [ ] 只记录 `secret_ref`，没有秘密值。
- [ ] 同一 PR 同步更新受影响的 Page/Task/Module catalog。

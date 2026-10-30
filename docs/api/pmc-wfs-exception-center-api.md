# PMC WFS 异常中心 API（M1）

日期：2026-10-29。前缀 `/api/pmc/wfs/exception-center`。案件持久化 + 人工处理；规则引擎与领星事实 M1 为 STUB。

## 权限

| 能力 | permissionKey |
|---|---|
| 列表/详情/统计/选项 | `page:pmc:wfs:view` + 来源账号与店铺数据范围 |
| 分配负责人 | `action:pmc:wfs-exceptions:assign` |
| 备注/状态变更/关闭/重开 | `action:pmc:wfs-exceptions:handle` |

## 端点

- `GET /cases` — 分页列表（`rule_family`、`status`、`severity`、`assignee_user_id`、`due_soon`、`shipment_id` 等）
- `GET /cases/{case_id}` — 详情 + 检测/处理时间线
- `GET /summary` — `open_shipments`、`open_cases`、`due_soon_cases`
- `GET /filter-options` — 店铺（dim_lingxing_stores）、历史负责人
- `POST /cases/{case_id}/assign` — `{ assignee_user_id, expected_version }`
- `POST /cases/{case_id}/events` — `{ action: note|resolve|close|reopen|mark_waiting, expected_version, note?, reason?, platform_case_ref? }`

## 错误码

- `404` 案件不存在或越权
- `409` `CASE_VERSION_CONFLICT`
- `422` `INVALID_STATE_TRANSITION` / 校验失败
- `503` `WFS_EXCEPTION_SCHEMA_NOT_READY`

决策：`docs/data-sources/decisions/pmc-wfs-exception-center-decision.md`

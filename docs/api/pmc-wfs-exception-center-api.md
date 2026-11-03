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

## 第一期：规则引擎（2026-11-03）

规则引擎由 STUB 换成 8088 规则（`WFS-RULES-20261010`），由 `WfsExceptionDetector` 从当前发布的看板计算（只读看板，不调外部接口），本期只在本地回放脚本中调用，不开定时：

- 规则命中：同一 货件 × 规则族 建一个案件（去重键同 `build_dedupe_key`），已有未关闭案件则刷新描述、级别、差异件数和证据；每次记录 `HIT` 检测。
- 不再命中：本规则版本的未关闭案件记录 `MISS`，由系统解决（动作 `RESOLVE`，操作人 `system:wfs-rules`，`payload.auto=true`）。
- 系统解决过的案件再次命中会重开（`REOPEN`）；人工解决 / 关闭的案件系统不重开。
- 测试货件（`PMC-TEST-`）不建案；其他来源（人工、夹具）的案件不动。
- 申诉类规则族 `appeal_deadline` 的 `due_at` = 沃尔玛签收日 + 50 天。

新增规则族 `carrier_delivered_unreceived`（货代已签收 · WFS 未收货）。

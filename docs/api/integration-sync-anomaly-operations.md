# Integration Sync 异常处理台 API（开发分支）

更新时间：2026-11-20。Status: `under-development`，未合并、未部署、未通过全部测试。

## 来源和访问控制

| 路径 | 权限 | 用途 |
|---|---|---|
| `GET /api/integrations/sync-anomalies` | `integrations:read` | 读取现有异常及其数量、状态与业务日期 |
| `GET /api/integrations/sync-anomalies/{id}/history` | `integrations:read` | 追加式操作历史 |
| `GET /api/integrations/sync-anomalies/{id}/diagnosis` | `integrations:read` | 从当前 FACT/MART 只读核对明细 |
| `POST /api/integrations/sync-anomalies/{id}/recheck` | `integrations:update` | 复核且仅数据真实一致时自动关闭 |
| `PATCH /api/integrations/sync-anomalies/{id}` | `integrations:update` | 保存人工核对、备注、误报说明；拒绝直接标为 resolved |
| `POST /api/integrations/sync-anomalies/{id}/replay` | `integrations:execute` | 符合条件时经既有队列派发 **单日** SaleStat 同步及 MART 重算 |

所有接口复用鉴权与 `source_account_ref` 范围；不读取旧库、RAW payload，不存密钥。

## 诊断响应

标准后端 envelope `{success,data,error,meta,request_id}`，data:
`status` = `manual_review` / `needs_identity` / `blocked_by_salestat` / `source_missing` / `ready_for_replay` / `verified`;
`explanation` 与 `next_action` 为中文用户说明。
可选字段 `recognized_zero_paid_orders`、`recognized_zero_paid_qty`、`approved_sample_qty`、`approved_sample_amount`、`salestat_qty`、`salestat_amount`、`mart_sample_qty`、`mart_gross_qty` 均为只读 FACT/MART 聚合，金额为十进制字符串。

已解决的自动判断：零元来源订单全部核实、SaleStat 和 MART 的商品日结果一致、无相关争议告警。日期级汇总、其他广告错误及来源缺失不得直接自动关闭。

## 重新核对和证据记录

`POST /recheck` 无业务参数；每次重新读取事实，仅 `verified` 自动更新 `gov_integration_sync_anomalies.status=resolved` 并追加 `gov_integration_sync_anomaly_audit`。没有修改来源订单、费用或利润。

`PATCH` body `{status,note}`。当前禁止 `resolved` 人工提交；误报 `dismissed` 必须不少于30字、写明订单/店铺/来源报表等证据。补充说明保留在既有业务备注与审计，不是事实更正接口。

## 单日受控回放

`POST /replay` body: `{"reason": "<至少12字证据说明>"}`。
只接受：
- 对应异常处于 `ready_for_replay`、未关闭；
- 一条唯一、已启用的源账号 `saleStatPageList` 配置；
- 业务日距当前洛杉矶日期 0—30 天，阻止历史锁账日期自动改写；
- 原有任务执行权限和账号隔离均通过。

服务器创建有幂等键的 `gov_integration_sync_runs`，将状态写为 `review_pending` 并记审计，返回任务 `run_id`；**202仅代表已经接受入队，不能承诺成功**。后台工作任务完成后，复核相关送样异常，只有真实核对通过才关闭。失败或财务差额保留异常并展示诊断原因。

错误码含 `SYNC_ANOMALY_REPLAY_NOT_SAFE`、`SYNC_ANOMALY_ALREADY_CLOSED`、`SYNC_ANOMALY_REPLAY_CONFIG_UNAVAILABLE`、`SYNC_ANOMALY_HISTORICAL_REPLAY_REQUIRES_APPROVAL`、`SYNC_ANOMALY_RECHECK_REQUIRED`、`SYNC_ANOMALY_DISMISS_EVIDENCE_REQUIRED`；403表示缺少操作权限。

## 未实现 / 禁止假装完成

直接把人工 Item ID、单价、广告费用写入 FACT、真实历史锁账日重算、上传凭据、财务费用分摊自动修复及跨品种复验尚未实现。前端人工提交的备注不能被解释为“已经修复财务”。

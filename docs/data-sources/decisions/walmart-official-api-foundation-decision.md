# Walmart 官方 API 基础客户端数据源决策（待负责人确认）

- 日期：2026-10-26
- 状态：**BLOCKED_BY_OWNER_DECISION**
- 本 PR 范围：纯离线接口计划；不新增业务路由，不读取或写入业务数据
- 来源证据：同事交接的 `features/tools/walmart_remote_pull/run_worker.py` 和 `routing.example.json`（不在当前 main）
- 现有新系统：`backend/app/modules/integration_sync/`、`backend/app/integrations/lingxing/`
- 旧系统：仅做历史只读参考；本 PR 不读取其代码、库或业务数据

## 强制前置调查

| 项目 | 结果 |
|---|---|
| 旧页面 / API / 文件 | 此 PR 不迁移旧业务页面或 API；不适用 |
| 旧数据表及写入方 | 不涉及；不适用 |
| cron / 外部 API | 同事单独运行的 Walmart worker，不属于新系统 main |
| 人工写入 | 不涉及 |
| Walmart 重新获取 | 候选，可用性与账号授权待正式核对 |
| 短期策略 | 离线校验与 Mock，默认禁止外部请求 |
| 长期策略 | 按单个业务接口签核后 REBUILD_SYNC |
| 权威来源 | Walmart 对应业务 API；字段级授权与映射待确认 |

## 数据集与风险

| 数据集 | 分类 | 当前状态 |
|---|---|---|
| 店铺固定出口与 SSM 名称 | NEW_SYSTEM_OWNED 候选 | 来自 2026-10-15 交接映射，未核验全部真实出口 |
| Client Secret / Token 访问 | NEED_OWNER_DECISION | 真实 SSM/SCF 权限、Invoker、SSH 隔离待审批 |
| Walmart 业务响应字段 | NEED_OWNER_DECISION | 官方接口契约、数据血缘、RAW/ODS/MART、DQ 待逐项批准 |
| 广告接口 | NEED_OWNER_DECISION | Walmart Connect 独立授权待确认 |

本 PR 没有新增对外业务返回字段、数据标准化或数据存储，故无业务字段血缘表可批准；未来必须遵守字段字典、时区、货币、身份映射和来源血缘规则。

## 禁止事项

- 不调用腾讯云 SSM、SCF、Walmart API，不运行 SSH，不触碰生产服务。
- CN2502 永久保持本阶段采集禁用；其他 8 店一店一服务器，无自动 failover。
- 不向主服务器或开发人员输出任何长期凭据。
- 不授权任意 URL、HTTP method、写接口或生产数据同步。
- 本次远程分支和 PR **不代表**批准真实业务接口的实施。

## 负责人决定（待记录）

需要单独确认：真实 API 的权威来源和字段、运行身份与 Token 可见性、固定出口信任、每种操作的权限及 RAW 发布边界。确认后才能将此决策改为 READY_FOR_PRP，再进入正式接口 PRP 和实现。

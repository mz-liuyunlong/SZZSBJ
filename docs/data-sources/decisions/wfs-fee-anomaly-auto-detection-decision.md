# WFS 费用异常自动检测数据源决策

- Status: Approved for implementation
- Decision date: 2026-10-26
- Owner authorization: 当前任务《WFS 费用异常自动检测完整开发任务》

## Purpose

为 WFS 费用异常自动检测确定唯一的数据来源、身份边界和写入边界。本文批准本地代码实现和隔离测试，不批准生产采集、迁移、调度启用或案件写入。

## Authoritative sources

| Data | Authoritative source | Required identity / lineage |
| --- | --- | --- |
| 结算原始证据 | Lingxing `POST /basicOpen/multiplatform/profit/report/order` 经 Integration Sync RAW/ODS 管线 | `source_account_ref`, `store_id`, request ref, RAW blob hash |
| 订单级实际 WFS | `fact_walmart_wfs_fee_actual` 的规范化、可追溯结算行 | account + store + MSKU + provider order + source line |
| 历史累计销量 | 新系统 `mart_daily_sales_item_day` | account + Walmart + store + MSKU；Item ID 仅使用已确认 Listing 映射 |
| 当前标准 WFS | Product Management 已有定价计算与有效规则 | listing → product → confirmed Lingxing identity → pricing calculation |
| 异常案件 | 现有 `ops_wfs_fee_anomaly_cases` | 复用既有唯一约束和人工生命周期 |
| 运行治理 | 现有 Integration Sync run/work item/config/lock | 每店铺、窗口、批次独立，默认关闭 |

## Required rules

1. 结算按订单次数选择众数，不按销售件数加权；金额使用 `Decimal` 和 `ROUND_HALF_UP`。
2. 缺少订单号、MSKU、店铺身份、USD 货币、合法日期或完整分页的数据不得进入有效样本。
3. API 每页响应先写现有 RAW blob/request ref，再进入规范化事实；认证参数和密钥不得写 RAW、日志或错误。
4. 历史累计销量与有费用证据销量必须分开；销量覆盖缺失时返回 unknown，不得当作 0。
5. 当前标准费回看历史只表示理论估算；没有历史有效规则时不得表述为确认可索赔金额。
6. 自动检测和自动建案使用独立默认关闭开关。案件写入只允许 INSERT-on-conflict-do-nothing，不覆盖人工状态或金额。
7. 店铺动态发现且相互隔离；单店失败不得污染其他店铺，部分采集不得发布为成功检测。

## Approved implementation scope

- 扩展现有 WFS 结算事实以承载订单级证据和 RAW 回指。
- 接通 Lingxing client、Integration Sync RAW/ODS、销量读取、动态标准费用、检测、dry-run、案件写入、Celery 调度和现有 WFS 页面。
- 新增必要 Alembic migration、API/Markdown/SOP、测试和 registry/catalog 更新。

## Explicitly not approved

- 真实 Lingxing/Token 请求、生产数据库连接或迁移、生产案件写入。
- 启用生产 Celery schedule、部署或重启。
- 旧系统修改、旧 MySQL 读取、临时 JSONL 作为正式运行依赖。
- 自动确认索赔金额、覆盖人工案件、跨店铺 MSKU 模糊匹配。

## Stop conditions

- 接口合同、分页总数、货币、订单身份或店铺身份无法确认。
- 标准费用或销量来源不完整，却将 unknown 写成 0。
- 需要扩大到生产写入、真实接口、旧系统或未批准的数据源。

# 关键词 V1.1 API（本地开发契约）

状态：**未部署、未批准正式投放**。路径前缀：`/api/v1/keyword-planning`。JSON 接口使用 `{success,data,error,meta,request_id}`；内部工作簿是下载响应，不是平台上传文件。OpenAPI 由 FastAPI 路由和 `response_model` 生成。不得把本文件当作生产接口已开放的证据。

## 身份、权限与范围

所有接口先校验登录身份和 `source_account_ref` 数据范围；商品还必须属于该范围内的当前 Listing。只读接口使用 `products:read`；商品确认、ASIN 导入、Excel 导入、分析创建、人工词入库使用 `products:write`；规则创建/草稿使用超级管理员校验；D01–D08 提交、复核、发布分别要求 `action:ai-center:keyword-rules:submit`、`:review`、`:publish`。审批人由服务端会话确定，Body 不能自报身份。写接口还受本地显式写入开关控制。

账号、商品和快照 ID 必须一起校验，不能仅凭 UUID 查询他人资料。`404` 表示不在当前范围；`409` 的 `details.reason_code` 提供安全的阻断原因；`422` 表示请求 Schema 无效；`403` 表示权限或数据范围拒绝。错误响应不回显密钥、原始外部 payload 或敏感商品明细。

## 来源与分析

| 接口 | 权限 | 请求要点 | 返回 | 数据来源 / 副作用 |
|---|---|---|---|---|
| `GET /products/{product_id}/source-state` | `products:read` | Query `source_account_ref` | 最近已确认事实、上传 ID、ASIN 数量 | `ai_kw_product_fact_snapshot`、`raw_kw_upload_file`、`biz_sku_asin_reference`；只读 |
| `POST /sources/walmart/confirm` | `products:write` | 账号、商品、Item ID、已验证 Decodo 快照 UUID、逐字段人工确认及可选复核短语 | 新事实和页面快照 ID | 读取已保存来源，追加不可变快照；不调用 Decodo |
| `POST /sources/amazon/asin` | `products:write` | 账号、商品、合法 ASIN、已保存来源快照 UUID | ASIN 快照 ID、图片数 | 读取已保存来源并保存历史/图片顺序；不调用 Amazon |
| `POST /imports/xlsx` | `products:write` | Query 账号、商品、已确认事实 ID、文件名；Body 为 `.xlsx` 二进制 | 上传 ID、状态、原始行数 | 原件放入受限私有存储；`raw_kw_upload_file/row`、标准词、来源事件、市场观测追加；解析错误保留而不伪造成功 |
| `GET /preflight` | `products:read` | Query 账号、商品、Item ID、事实/规则/上传 ID | 可创建复核批次、缺失证据代码、候选数，以及已确认事实自动归类/人工证据归类/仍待人工确认三类计数 | 只读；不会把 D01–D08 pending 当批准；计数不是正式投放通过率 |
| `POST /analyses` | `products:write` | 冻结来源 ID 和 `request_key` | run ID、状态、词数 | 同账号幂等；创建不可变分析批次，不调用外部 API、不创建广告 |
| `GET /products/{product_id}/runs` | `products:read` | Query 账号、分页 | 历史批次 | `ai_kw_analysis_run`；只读 |
| `GET /runs/{run_id}` | `products:read` | Query 账号 | 批次详情 | 冻结分析；只读 |
| `GET /runs/{run_id}/keywords` | `products:read` | Query 账号、分页 | 类型、六维、承接、等级、拒绝原因 | `ai_kw_run_keyword`；只读 |
| `GET /runs/{run_id}/internal-workbook` | `products:read` | Query 账号 | 内部五表 `.xlsx` | 同一冻结 run 派生；拒绝作为 Walmart 官方上传文件 |

## 词库与规则

| 接口 | 权限 | 请求要点 | 返回 | 数据来源 / 副作用 |
|---|---|---|---|---|
| `GET /products/{product_id}/library` | `products:read` | Query 账号、关键词、状态、`limit/offset` | 标准词、来源种类/数量、观测数、最新分析 | `biz_sku_keyword`、`dim_kw_term`、`biz_kw_source_event`、`biz_kw_market_observation`；只读 |
| `POST /products/{product_id}/library/manual` | `products:write` | 账号、Item ID、稳定 `request_key`、最多 100 个词 | 接受数、新增来源事件数 | 先进入 review；重复请求不重造事件，不能冒充自动广告搜索词 |
| `GET /rulesets`、`GET /rulesets/{id}/versions` | `products:read` | Query 账号 | 规则集及版本 | 只读，版本列表不推定审批通过 |
| `POST /rulesets`、`POST /rulesets/{id}/drafts` | 超级管理员 | 账号、规则键/名称或版本配额/品牌证据 | 草稿/规则 ID 与 SHA | 仅生成禁用草稿；不直接发布 |
| `GET /rules/{id}/decisions` | `products:read` | Query 账号 | 八项状态与审计事件 | 只读，未提交项显式缺失 |
| `POST /rules/{id}/decisions/{D01-D08}/submit` | `...:submit` | 账号、具体方案、证据编号 | pending_review | 仅创建者可提交，D04 需策略选择 |
| `POST /rules/{id}/decisions/{D01-D08}/review` | `...:review` | 账号、通过/驳回、证据编号 | approved/rejected | 独立审批人；审计事件追加 |
| `POST /rules/{id}/publish` | `...:publish` | 账号 | 发布收据 | 八项批准、配置哈希与人员隔离全部通过才冻结发布；不创建广告 |
| `POST /rules/{id}/retire` | 超级管理员 | 账号 | 退役收据 | 保留旧版本和旧批次 |

## 数据口径和审计

- RAW：保留原文件/全部工作表行、已验证页面和 ASIN 历史快照；不删除重复来源。
- 词库：按规范化词去重；来源事件按账号、来源类型、事件键、商品、词幂等；市场观测仍逐行保留，D08 未批准前不取最大值。
- 分析：六维为 `match 0–30`、`intent 0–20`、`page 0–20`、`root 0–15`、`data 0–15`、`risk -40–0`。未知证据为 null/review，不能由前端补分。批次和规则版本不可回写。
- 回滚：草稿可退役或新建版本；已发布规则、RAW、历史分析不覆盖。数据迁移只允许 Alembic；生产迁移与恢复需另行授权。
- 外部状态：当前仅有已保存可信来源的导入适配；缺少自动广告搜索词、已授权报表契约或官方模板时返回阻断/不可用，不得伪称实采或可上传。

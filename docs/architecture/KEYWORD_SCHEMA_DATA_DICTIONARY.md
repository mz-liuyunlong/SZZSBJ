# 关键词系统数据库设计 · 数据字典与部署边界

> **当前交付：21 张第一阶段新增表的 SQLAlchemy 模型、静态 Alembic 迁移和 PostgreSQL DDL；数据库尚未执行迁移。**
> 复用主表：`products`、`product_platform_listings`（已通过 GitHub `main` 模型核对）。
> 未来广告阶段：12 张逻辑表，仅设计，不包含本次迁移。

## 1. 现有数据与关联键

- `products.id`: UUID PK；`products.sku` 系统现有唯一 SKU。不要并行创建 `kw_products`、`kw_sku_master`。
- `product_platform_listings.id`: UUID PK，引用 `products.id`，含 platform/store_name/msku/external_listing_id。Walmart Item ID 关联需要结合真实查询和平台 Listing 的实际字段核验，不强行把 `external_listing_id` 当 Item ID。
- `source_account_ref`：现有接口层沿用的账户数据范围；关键词业务库按产品共享，原始 API/广告来源按账户和店铺分开。在 API 层必须由登录主体解析并检查权限，**不可直接信任前端提交的账户范围**。
- `store_id`：平台店铺维度；不能用单个 SKU 代替广告账户/店铺分区。没有确认来源的店铺信息要为空或待匹配。

## 2. 第一阶段物理表（21 张新增）

| 类别 | 表 | 主要用途 | 关键设计 |
|---|---|---|---|
| 原始来源 | `raw_kw_upload_file` | 每一次 Excel 原文件存储凭据 | `original_filename,object_key,sha256,uploaded_by,parser_version,status,product_id,source_account_ref`；**不按 SHA 去重上传事件** |
| 原始来源 | `raw_kw_upload_row` | Excel 每 Sheet 每行原始解析数据 | `upload_id,sheet_name,row_number,source_cells` 唯一定位；保留重复行和错误行 |
| 原始来源 | `raw_kw_walmart_page_snapshot` | Walmart 实际页面内容和 Item ID 采集证据 | `item_id,listing_id,verification_status,page_title,features_json,attributes_json,raw_object_key`；与商品事实分开 |
| 原始来源 | `raw_kw_asin_snapshot` | Amazon API ASIN 不可变快照 | `asin,title,features_json,description_text,fetch_status,raw_object_key`；每抓取一次创建一份 |
| 原始来源 | `raw_kw_asin_image` | 一个 ASIN 快照的**所有**图片 URL | `asin_snapshot_id,image_index,image_url,width,height,image_type`；URL 用 TEXT，允许同 URL 不同 index |
| 输入事实 | `ai_kw_product_fact_snapshot` | 已确认本品事实及逐字段来源 | `facts_with_sources_json` 格式 `field:{value,source,evidence_ref}`，`item_verified`, `confirmed_by`,`confirmed_at`；确认后冻结 |
| 词条 | `dim_kw_term` | 全局标准化关键词字典 | `normalized_keyword` 唯一；不将复数/语序/同义词无依据合并 |
| 词库 | `biz_sku_keyword` | SKU 级正式长期词库 | `product_id + term_id` 唯一；当前运营状态、人工翻译与备注，不被重跑覆盖 |
| 词库 | `biz_kw_market_observation` | Excel/外部来源市场观测历史 | `source_kind,upload_row_id,monthly_searches,monthly_purchases,ppc_usd,bid_min/max,source_metrics_json`；旧值不覆盖 |
| 词库 | `biz_kw_source_event` | Excel、手动、自动搜索词、系统创建等来源事件 | `source_kind,source_event_key,product_id,term_id,evidence_json,discovered_at`，入库与否由独立规则评估/词库状态表达 |
| 词库 | `biz_sku_asin_reference` | SKU 持续关联竞品 ASIN | `product_id,asin,reference_role,latest_snapshot_id,is_active` |
| 规则 | `ai_kw_rule_set` | 一组同类型规则管理 | `scoring/search_term_admission/ad_creation/ad_optimization/export`；scope_key |
| 规则 | `ai_kw_rule_version` | 草稿与不可变已发布规则 | `rule_set_id,version_number,config_json,config_sha256,engine_version,published_at` |
| 分析 | `ai_kw_analysis_run` | 每次分析任务和不可变运行快照 | `product_id,item_id,store_id,fact/page/rule_version_id,input_sha256,engine_version,status,确认信息` |
| 分析 | `ai_kw_run_file` | 一个 run 关联多份上传文件 | `(run_id,upload_id)` 唯一；跨账号复合 FK |
| 分析 | `ai_kw_run_asin` | 一个 run 关联多个 ASIN 快照 | `(run_id,asin_snapshot_id)` 唯一；跨账号复合 FK |
| 分析 | `ai_kw_run_keyword` | **每词唯一评分/投放决定事实源** | `(run_id,term_id)` 唯一；类型、页面、六分量、原始等级/名额等级、Exact/Broad、原因、证据 JSON |
| 输出 | `ai_kw_listing_version` | Listing 草稿/确认的历史版本 | `run_id,version_number,title,features_json,description_text` |
| 输出 | `ai_kw_export_file` | 分析 Excel/Listing CSV/上传版文件档案 | `run_id,template_version,object_key,file_sha256,approved_by/time`；真实文件仍保存对象存储 |
| 审计 | `biz_kw_decision_history` | 运营、规则对 SKU 词库的动作历史 | 状态前后快照、动作类型、原因、执行者、关联规则版本 |
| 审计 | `ai_kw_rule_evaluation` | 自动规则**通过和拒绝**的判断证据 | `candidate_keyword,rule_version,input_metrics_json,decision,reason_codes,idempotency_key`；没进词库的候选也留证 |

**计数：现有 2 张 + 新增 21 张 = 当前覆盖 23 张相关业务表**。历史讨论中的 18/20 新增表数字已随实际新增 Walmart 页面快照、决策历史、规则判定记录而更新。

## 3. 数据关系与唯一性

```text
products (SKU) ─┬─ product_platform_listings (店铺商品)
                ├─ raw_kw_upload_file ── raw_kw_upload_row ── biz_kw_market_observation
                ├─ raw_kw_walmart_page_snapshot
                ├─ ai_kw_product_fact_snapshot
                ├─ biz_sku_keyword ── dim_kw_term
                │                └── biz_kw_decision_history
                ├─ biz_kw_source_event ── ai_kw_rule_evaluation
                ├─ biz_sku_asin_reference ── raw_kw_asin_snapshot ── raw_kw_asin_image
                └─ ai_kw_analysis_run
                     ├─ ai_kw_run_file ─────── raw_kw_upload_file
                     ├─ ai_kw_run_asin ─────── raw_kw_asin_snapshot
                     ├─ ai_kw_run_keyword ──── dim_kw_term
                     ├─ ai_kw_listing_version
                     └─ ai_kw_export_file
ai_kw_rule_set ── ai_kw_rule_version ── ai_kw_analysis_run / ai_kw_rule_evaluation
```

关键唯一性：

1. `dim_kw_term(normalized_keyword)` 唯一。
2. `biz_sku_keyword(product_id,term_id)` 唯一。请先 INSERT 全局词再通过 `ON CONFLICT DO NOTHING` + SELECT 关联到 SKU；不要以先查再插替代数据库约束。
3. `raw_kw_upload_file` **没有 sha256 唯一约束**。用户两次上传相同文件 = 两次操作，原始字节保存策略可物理复用，但不能丢两条上传元数据。
4. `raw_kw_upload_row(upload_id,sheet_name,row_number)` 唯一，**相同关键词内容不唯一**。
5. `raw_kw_asin_image(asin_snapshot_id,image_index)` 唯一，不对 URL 做唯一性限制。
6. `ai_kw_run_keyword(run_id,term_id)` 唯一；已经完成的 run 和结果不可更新。
7. `biz_kw_source_event(source_account_ref,source_kind,source_event_key,product_id,term_id)` 为事件幂等键；同一个词来自不同时间、渠道仍保留多条来源。
8. `ai_kw_rule_evaluation(source_account_ref,idempotency_key)` 唯一，避免规则任务重试重复写评价记录。

## 4. 不可变与状态

本次迁移附带 PostgreSQL trigger guard：

- 保护原始行、ASIN、Walmart 页面快照、图片 URL、来源事件、市场观测、分析结果行、输出文件记录、规则评估、决策历史等，禁止 UPDATE/DELETE。
- `raw_kw_upload_file` 允许上传解析状态变化，但禁止修改文件名、对象 key、SHA256、大小、归属。
- 已经确认的商品事实、已发布/已退役规则、已完成的分析 run 禁止 UPDATE/DELETE；变更必须创建新版本。
- `biz_sku_keyword` 本身允许更新当前运营状态，但应**在同一事务写入** `biz_kw_decision_history`；此事务性要求由 service/repository 保证，单靠表定义无法保证。
- 当前 DB 不负责真正存储二进制原文件，也没有导入/下载 API；必须接对象存储、哈希校验、权限及备份服务。DB 表存在不等于文件已留存。

## 5. 下一阶段拟建的 12 张表（**未在本次迁移中创建**）

| 类别 | 拟建表 | 用途/索引主维度 |
|---|---|---|
| 账户 | `ads_advertiser_account` | `source_account_ref/store_id/advertiser_id`、授权能力状态；不存明文密钥 |
| 广告对象 | `ads_campaign` | advertiser + provider campaign id、Campaign 类型/预算/状态 |
| 广告对象 | `ads_ad_group` | campaign + provider ad group id |
| 广告对象 | `ads_ad_item` | ad group + Walmart Item ID + SKU 归属证据 |
| 广告目标 | `biz_kw_ad_target` | 广告账户/店铺/Campaign/Ad Group/Keyword/Match Type/provider target ID |
| 原始报表 | `raw_ads_report_batch` | provider report ID、统计窗口、模板版本、对象存储 key、同步 run |
| 搜索词表现 | `fact_kw_search_term_daily` | account/store/campaign/adgroup/search term/date/归因/报告来源 |
| 目标表现 | `fact_kw_ad_daily` | target/date/花费/点击/订单/销售额/归因/新鲜度 |
| 否定词 | `ads_negative_target` | advertiser + scope + negative term + match type/status |
| 执行 | `ads_action_job` | 创建/调整广告意图、幂等、审批、状态、风险保护 |
| 执行尝试 | `ads_action_attempt` | API 请求尝试、响应状态、去敏错误、重试历史 |
| 对账异常 | `ads_reconcile_issue` | 来源不明、手动后台变更、无 SKU 归属、接口状态不一致 |

**阶段二须根据真实 Walmart Advertising API/账户权限确定字段后，再制作独立 Alembic 迁移。** 不把“搜索词发现”偷换成“已经投放的关键词 Target”。

## 6. SQL/Alembic 衔接的现实障碍

已只读核对 GitHub `main`：截至检查时 Alembic 合并头是 `20261022_0054_merge_walmart_identity_and_domestic_packing`，`products.id` / `product_platform_listings.id` 均为 UUID。交付的迁移基于这个头。

但你上传的本地 `git status` 表明另有**未跟踪**的 `backend/alembic/versions/20261022_0048_decodo_config_usage.py`。由于那份文件源码尚未提供，我们不知道它的真正 `revision`/`down_revision`，更不能认定它属于同一个版本线。**必须先在用户本地检查 `alembic heads` 和该文件实际 revision，再决定迁移依赖或建立 merge revision。不要直接改别人的历史 revision，也不能在双 head 不明时 `alembic upgrade head`。**

此外 `backend/alembic/env.py` 必须 import `app.modules.keyword_planning.models` 才能把新 metadata 登记进 Alembic 自动比较；本次提供了单独的导入补丁。正式迁移执行只在**已明确授权的隔离测试数据库**中进行，本交付未执行任何 DB 命令。

## 7. 上线前必须补的服务能力（不能被 DDL 冒充）

- 安全上传：文件类型/大小限制、实际二进制哈希、私有对象存储、业务权限、原始行全保留。
- API 查询与商品核验：Item ID 真正身份验证 + page evidence、接口失败区别 `failed/partial/mismatch`、用户修正事实的来源追踪。
- ASIN 捕获：全量文本与几十张图片 URL 原样存储，保留原始响应和图片顺序。
- 后端规则 service：依发布规则+不可变输入运行，输出完整 25 类、九页面证据、六分量、等级及两个广告准入；**本次仅提供保守规则底座**。
- 输出 5 表及最新 Walmart 官方模板合约测试；不能使用不经验证的 Mock 五表直接上传平台。
- RBAC 与按账户数据隔离；对象存储签名 URL、密钥不得泄漏到错误账户。
- 验收完毕后再考虑启用自动搜索词入库规则、广告同步、创建和调价任务。

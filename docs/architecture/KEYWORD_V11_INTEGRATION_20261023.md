# Walmart Keyword V1.1 — 本批交付、边界与验收

## 执行基线
- 本地 worktree: `acceptance/keyword-planning`；用户此前已验证 **84 passed / 1 skipped**。
- 已存在: `analysis_execution.py`, 规则安全引擎、3 条只读 API、0055/0056 迁移。
- 本批只修改 `keyword_planning/router.py` 以注册子路由；其他已存在文件不覆盖。
- **本批不是“所有业务规则已批准、平台正式投放上线”。** D01–D08 尚无最终授权裁决，语义分类器、正式出价和 Walmart 官方模板仍缺少可验证契约。

## 本批接口（额外 3 条）
| Method | Path | 权限 | 结果 |
|---|---|---|---|
| POST | `/api/v1/keyword-planning/imports/xlsx?source_account_ref=...&product_id=...&product_fact_snapshot_id=...&filename=...` | `products:write`, 账户范围, 写入开关 | 私有原件不可覆盖存储、工作表全部原始行、词条 upsert、来源事件 |
| POST | `/api/v1/keyword-planning/analyses` | `products:write`, 账户范围, 写入开关 | 可信快照+已发布规则+已解析原始行 -> 批次、不可变逐词结果；证据不足为 `blocked` |
| GET | `/api/v1/keyword-planning/runs/{run_id}/internal-workbook?source_account_ref=...` | `products:read`, 账户范围 | 五 Sheet **内部分析报告**；01 固定 14 列；04 强制标“禁止上传” |

以上全部继承 FastAPI 全局认证和数据范围约束，并显式拒绝 `frontend-preview` 主体；新增 POST 默认为禁用（返回 403），须**仅在隔离开发环境**使用 `KEYWORD_V11_WRITE_ENABLED=1` 显式开启。真实生产上线不属于本批授权。

### 私有 XLSX 存储

本批实现 `PrivateLocalKeywordStore` 作为本机隔离开发存储。私有存储根目录环境变量的准确名称以 `backend/app/modules/keyword_planning/analysis_routes.py` 中的定义为准；其值必须指向**已存在的绝对路径、权限 0700、非符号链接的目录**，且不在 web 静态文件目录内。每次上传使用不可覆盖的 0600 文件，保存 SHA-256 和唯一对象键。真正生产部署应替换为组织批准的私有对象存储 + KMS，而非使用本地目录作为长期对象存储。

上传前校验 `product_fact_snapshot_id` 确属本账户、本商品、`confirmed` 且 `item_verified=true`，否则拒绝；仅有可访问店铺账户的权限并不等于能写入任意商品。

请求应以 `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` 发送 **原始 XLSX bytes**，不是 JSON、multipart 或前端剥离后的数据。上传会保存所有 sheet 与原始行（包括 Notes / ASIN 辅助页），且只对具有 `关键词/keyword/search term` 表头的 sheet 提取候选。含公式/错误的数据行标记，上传状态 `failed`，不会用于分析；不会执行 Excel 公式/宏。

### 创建分析请求

```json
{
  "source_account_ref":"your-authorized-account",
  "product_id":"00000000-0000-0000-0000-000000000001",
  "item_id":"verified-item-id",
  "product_fact_snapshot_id":"00000000-0000-0000-0000-000000000002",
  "rule_version_id":"00000000-0000-0000-0000-000000000003",
  "upload_file_id":"00000000-0000-0000-0000-000000000004",
  "request_key":"explicit-unique-request"
}
```

前端**不**能提交假定分数/关键词类型/品牌/认证来源。服务从已冻结数据库快照重建事实和规则，从 `raw_kw_upload_row` + `dim_kw_term` 构造候选，排序和去重不删原始行。没有已确认的语义/市场打分证据时，记录可复核的 `blocked` 批次，而不是捏造 `succeeded` 或广告建议价。

### 导出

`internal_export.py` 使用 Python 标准库生成 XLSX，不新增后端依赖。01 使用《广告投放正式版V1.0》§12.2 的 **14 列原始字段顺序**；02-05 只投影同一 run 的已有信息。04 在没有批准的官方 Walmart Bulk 模板、真实默认价/预算、最终审批时**明确写“禁止上传”**。所有危险 Excel 字符串避免公式执行。未生成正式的 Walmart 上传 XLSX；不会执行真实广告操作。

### 前端

仅新增 `frontend/src/api/keywordPlanningV11Api.ts` 的类型安全 API Client。未擅自修改用户 Mac 中尚未提交的三个前端页面；调用方需要将三个页面按当前本地状态接入，不能把增量 API Client 误认成页面已联调。

## 运行测试（Mac worktree）

```bash
cd "$(git rev-parse --show-toplevel)/backend"
.venv/bin/python -m pytest -q tests/modules/keyword_planning tests/modules/decodo
git diff --check
git diff --cached --check
```

隔离 PostgreSQL DDL 原已由用户实测 `1 passed`，新 HTTP DB 写入未在用户真实隔离 PostgreSQL 中复测。本地启用写入前需检查迁移链和已有数据库状态；本批未执行生产迁移、push、部署或 PR。

## 尚未具备的“全量 V1.1 正式验收”条件
1. D01–D08 业务裁决、可复现 25 类型黄金样例和六维可计算的语义证据策略；当前仍以 `人工确认词` + `blocked` 保护真实性。
2. 可核验的 Walmart 商品身份/ASIN API 及操作凭据；当前 API 仅引用事先保存的可信快照，不对外抓取。
3. 已验证的 Walmart 官方 Bulk 模板、执行出价/预算、最终审批机制；现仅内部工作簿。
4. 三个前端页面当前的完整本地未提交代码，以便不覆盖 UI 进行真实联调。
5. 真实隔离 PostgreSQL 中验证本批新增导入、任务入库、权限和回滚；单元测试不是完整数据库端到端验收。

**不得对外宣称正式规则、Walmart 官方上传、前端完整联调或全流程生产可用。**

## 新增 HTTP 最小验收补充

本包还包含 `test_v11_http_extensions.py`，使用真实 `app.main.create_app()` + `TestClient`，验证三条新路由、匿名访问拒绝、跨账户拒绝、预览主体拒绝、默认禁止写入和内部 XLSX 返回。需在 **Mac 原工作树**跑通，不能以隔离 stub 路由注册替代真实认证链验证。

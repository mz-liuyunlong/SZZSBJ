# PR #278 新品表现 / 打品跟踪草稿接口说明

状态：Draft；非正式采购执行接口。应用统一返回 `{ success, data, error, meta, request_id }`，所有入口受登录和对应 IAM 权限保护。

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/new-products/source-accounts` | 仅列当前用户有权的来源账户 |
| GET | `/api/new-products/workflows` | 按 `source_account_ref`、page、page_size 查草稿，越权 403 |
| GET | `/api/new-products/workflows/{sku_id}` | 返回受账户范围保护的单 SKU 状态 |
| GET | `/api/new-products/workflows/{sku_id}/metrics` | 30/60/90 天读模型；财务值按订单利润字段权限脱敏 |
| POST | `/api/new-products/workflows/{sku_id}/market` | 人工市场分与理由 |
| POST | `/api/new-products/workflows/{sku_id}/purchase-request` | 独立新品草稿申请，不写 PMC |
| POST | `/api/new-products/workflows/{sku_id}/purchase-decision` | 审核草稿，`approved_draft` 不产生正式采购订单 |
| POST | `/api/new-products/workflows/{sku_id}/verified-dates` | 经权限校验确认实际到货/可售日期与证据 |
| POST | `/api/new-products/workflows/{sku_id}/review` | 仅观察与优化复盘 |
| GET/PUT | `/api/new-products/rules` | 读取或版本化修改现有草稿规则，非正式五维审批 |

变更请求含 `expected_version`，版本过期 409；SKU 与账户不一致 404。字段定义及准确性限制见 `docs/data-sources/decisions/new-product-performance-source-decision.md`。

数据空值不是 0。周期 `data_issues` 给出缺失日、成本不完整、币种未知或广告归因缺失的机器可读状态；`complete=false` 不能正式评分。未经负责人签署的评分规则只返回 `provisional`（预估），不能当正式等级。

服务端按既有 `field:sales:order-profit:gross-profit` 和 `field:sales:order-profit:profit-margin` 控制 `profit`、`margin` 及可推导的评分/打品结论；前端隐藏不是权限校验。

**显式未实现：** 正式独立采购计划及幂等创建、完整评分修正审核、四页正式数据统一、广告上游币种补录与真实多店数据对账。Mock 仅作样式验收。

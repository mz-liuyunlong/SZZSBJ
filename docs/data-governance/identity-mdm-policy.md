# 身份与 MDM 治理策略

> Status: 规则在负责人合并后为 `approved`；identity store、匹配任务和 review queue 均为 `planned`。
> Scope: 产品、Listing、SKU、MSKU、ItemID、店铺、平台等跨来源身份关系。
> Non-goals: 不选择生产主键、不创建映射表、不执行自动匹配或旧数据迁移。

## 核心身份规则

1. `sku` 不能作为全局唯一键；它可以为空、重复或在不同上下文复用。
2. `msku` 不能作为全局唯一键。
3. `item_id` 不能脱离 `platform` 与 `store_id` 上下文使用。
4. Listing identity 必须至少评估 `platform + store_id + item_id/listing_id`；最终键由接口级 Source Decision 和 PRP 确认。
5. `store_id` 必须携带 `source_system`/`platform` 上下文，不能假设跨平台唯一。
6. 同一内部产品可对应多个平台、店铺、listing、SKU/MSKU 和外部 ID；关系必须显式建模，不能塞进逗号分隔字段。
7. 自动匹配不能覆盖人工确认；人工确认的 mapping 优先级高于自动推断，但仍须可撤销、版本化和审计。
8. 低置信度、冲突或上下文不足的 mapping 不得发布到 Canonical、DIM/MASTER 或 MART，必须进入 quarantine/review queue。

## 常见实体与字段

| entity_or_field | 语义 | 唯一性边界 | 必需上下文/元数据 | status |
| --- | --- | --- | --- | --- |
| `internal_product_id` | 新系统内部产品稳定身份 | 仅由获批 MDM 规则保证 | entity version、created source | planned |
| `platform` | Walmart/Amazon/TEMU 等平台代码 | 由 Reference Data 管理 | reference version | planned |
| `store_id` | 来源店铺标识 | 仅在 source/platform 上下文内 | `source_system`, `platform` | candidate |
| `item_id` | 平台 item 标识 | 不脱离 platform/store | platform、store、source endpoint | candidate |
| `listing_id` | 平台 listing 标识 | 按平台契约判断 | platform、store、contract version | candidate |
| `sku` | 商品/内部/来源 SKU 字符串 | 不保证全局唯一 | source、store/listing context | candidate |
| `msku` | Merchant SKU | 不保证全局唯一 | platform、store、source | candidate |
| `seller_sku` | Seller 侧 SKU | 按平台与店铺限定 | platform、store | candidate |
| `external_product_id` | 外部产品标识 | 按 source contract 限定 | source system、ID type | candidate |
| `supplier_sku` | 供应商 SKU | 按 supplier 上下文限定 | supplier identity | candidate |
| `mapping_confidence` | 自动/人工 mapping 置信度 | 不是身份键 | method、threshold、evidence | planned |
| `mapping_status` | candidate/confirmed/rejected/quarantined 等状态 | 由 workflow 管理 | actor、time、version | planned |

## Mapping 证据契约

每条 identity mapping 至少记录：

| 字段 | 要求 |
| --- | --- |
| source/target identity | 类型、值的受控引用及完整上下文；敏感值按字段规则保护 |
| `mapping_method` | deterministic rule、source assertion、manual confirmation 等 |
| `mapping_confidence` | 可解释等级/数值与阈值版本，不得伪造精度 |
| `mapping_status` | candidate、confirmed、rejected、quarantined、superseded |
| `source` | 来源系统、endpoint/file/table reference |
| `evidence` | raw record、文件行、合同或人工审批引用 |
| `confirmed_by` / `confirmed_at` | 仅 confirmed 时必填；不得填通用系统用户掩盖责任 |
| `rule_version` | 自动匹配规则版本 |
| effective/history | 生效、失效、合并、拆分、撤销历史 |

## 冲突处理示例

| 情况 | 处理 | 禁止 |
| --- | --- | --- |
| 同一 SKU 对多个 item | 保留多关系并结合平台/店铺证据；必要时 quarantine | 任取第一条 |
| 同一 item 对多个 SKU | 记录来源事实与时间，不自动合并内部产品 | 删除“重复”记录 |
| 自动结果与人工确认冲突 | 保留两者，人工确认继续生效并产生 review issue | sync job 静默覆盖人工值 |
| 来源间标识冲突 | 隔离 mapping，记录来源优先级待决策 | 用字符串相似度直接发布 |
| 低置信度匹配 | 进入 review queue，不进入 canonical/mart | 降低阈值绕过 Review |

## 权限、血缘与留存

- identity mapping 的查看、确认、合并、拆分必须使用不同 action permission，并由后端校验 data scope。
- 映射必须能追溯到来源、规则版本、run/batch 或人工操作；merge/split 不得删除历史。
- 外部标识是否敏感由字段字典确定；日志与错误中不得批量输出真实标识。
- MDM 输出是被治理的身份解析结果，不代表所有描述属性也成为权威。

## Forbidden patterns

- `sku`, `msku`, `item_id` 单字段全局 `UNIQUE`，未说明业务上下文。
- 用 `platform + item_id` 代替已要求的店铺上下文而无契约证据。
- 自动 fuzzy match 直接写 canonical。
- 人工确认没有 actor、reason、evidence、time 或 before/after。
- identity mapping 表兼做产品详情、库存事实或 MART。
- AI 建议自动确认身份。

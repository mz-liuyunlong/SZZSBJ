# Product Basic Information OD-9 Readonly DB Inventory

## 1. Execution Boundary Confirmation

```text
Inventory Date: 2026-09-07
Execution Role: Backend Engineer Codex / OD-9 Readonly DB Inventory Executor
Database: walmart_ai_data
Allowed Tables: dim_product, dim_store, dim_store_config
Access Mode: Read-only
Sanitized Result Source: /tmp/od9_inventory_allowed_output_v2.txt
Database Write Used: No
DDL Used: No
Temporary Table Used: No
External API Used: No
```

负责人已在本机终端亲自完成 SSH key passphrase 和只读数据库账号密码输入；凭据未写入命令、文件、对话或本报告。第一次只读聚合因 `ONLY_FULL_GROUP_BY` 报错，未发生写库、建表或样本导出；负责人随后以等价聚合表达式取得本报告使用的脱敏结果。

本报告只使用脱敏结果中的元数据和非识别聚合。未重新连接数据库、启动 SSH tunnel 或执行 SQL。

## 2. Actual Inventory Scope

实际盘点严格限于以下三张表：

- `dim_product`
- `dim_store`
- `dim_store_config`

收集范围为表存在性、相关字段结构、主键与索引、精确行数、ItemID/SKU/MSKU 完整性与重复聚合、身份交叉映射聚合、`store_id` 覆盖、`store_name` 缺失与表内冲突，以及更新时间候选字段的结构信息。

成本、价格、利润、库存、广告、结算、退款、负责人、生命周期及人工运营状态字段值均未查询或评估。字段结构输出中出现的排除域字段没有被用于任何值统计。

## 3. Table Existence and Row Counts

| Table | Exists | Type / engine | Metadata estimate | Exact aggregate count | Evidence assessment |
|---|---:|---|---:|---:|---|
| `dim_product` | Yes | BASE TABLE / InnoDB | 2,444 | 2,446 | 元数据估算与精确计数相差 2；本报告的数据质量比例使用精确计数。 |
| `dim_store` | Yes | BASE TABLE / InnoDB | 9 | 9 | 估算与精确计数一致。 |
| `dim_store_config` | Yes | BASE TABLE / InnoDB | 10 | 10 | 估算与精确计数一致。 |

三表均存在。行数证明本次已执行聚合的数据规模有限，但不能替代后续接口分页、超时、并发与旧库退出边界的负责人决定。

## 4. Relevant Column Structure Summary

### 4.1 `dim_product`

| Column | Type | Nullable | Default | Key / extra | Structural meaning and risk |
|---|---|---:|---|---|---|
| `product_key` | `bigint` | No | `NULL` | Primary key; auto increment | 旧表内部主键，不等同 ItemID、SKU 或 MSKU。 |
| `platform` | `varchar(64)` | No | `walmart` | Indexed; first column of unique key | 默认值不能自动成为新系统 canonical platform。 |
| `store_id` | `varchar(64)` | No | `NULL` | Indexed; second column of unique key | 结构为必填字符串。 |
| `store_name` | `varchar(255)` | Yes | `NULL` | None | 可空；脱敏结果未提供本表名称缺失率。 |
| `item_id` | `varchar(64)` | No | `NULL` | Indexed; third column of unique key | 外部标识字符串，不能与内部主键混用。 |
| `msku` | `varchar(128)` | No | `NULL` | Fourth column of unique key | 无独立索引；不能从 SKU 或 ItemID 推导。 |
| `sku` | `varchar(128)` | Yes | `NULL` | None | 结构允许空值且无独立索引。 |
| `product_name` | `text` | Yes | `NULL` | None | 第一阶段已决定不作为默认名称 fallback。 |
| `item_name` | `text` | Yes | `NULL` | None | 第一阶段名称候选；本轮未统计值完整性。 |
| `source_system` | `varchar(64)` | No | `lingxing` | None | 默认值只反映旧表结构，不构成新系统来源批准。 |
| `source_raw_id` | `varchar(128)` | Yes | `NULL` | None | 可用于旧链路追溯的结构候选；本轮未查询值。 |
| `created_at` | `datetime` | No | `CURRENT_TIMESTAMP` | Generated default | 旧行创建时间，不等同来源更新时间。 |
| `updated_at` | `datetime` | No | `CURRENT_TIMESTAMP` | Auto-updated | 行变更时间候选，不足以证明来源新鲜度。 |

### 4.2 `dim_store`

| Column | Type | Nullable | Default | Key / extra | Structural meaning and risk |
|---|---|---:|---|---|---|
| `id` | `bigint` | No | `NULL` | Primary key; auto increment | 旧表内部主键。 |
| `platform` | `varchar(64)` | No | `walmart` | Indexed; first column of unique key | 与 `store_id` 共同约束唯一性。 |
| `store_id` | `varchar(64)` | No | `NULL` | Second column of unique key | 结构为必填字符串。 |
| `store_name` | `varchar(255)` | Yes | `NULL` | None | 结构可空，但本次聚合未发现空值。 |
| `source_system` | `varchar(64)` | No | `lingxing` | None | 旧结构来源标签，不是权威来源决定。 |
| `created_at` | `datetime` | No | `CURRENT_TIMESTAMP` | Generated default | 旧行创建时间。 |
| `updated_at` | `datetime` | No | `CURRENT_TIMESTAMP` | Auto-updated | 行变更时间候选。 |

### 4.3 `dim_store_config`

| Column | Type | Nullable | Default | Key / extra | Structural meaning and risk |
|---|---|---:|---|---|---|
| `id` | `bigint` | No | `NULL` | Primary key; auto increment | 旧表内部主键。 |
| `platform` | `varchar(64)` | No | `walmart` | Indexed; first column of unique key | 与 `store_id` 共同约束唯一性。 |
| `store_id` | `varchar(64)` | No | `NULL` | Second column of unique key | 结构为必填字符串。 |
| `store_name` | `varchar(255)` | Yes | `NULL` | None | 结构可空，但本次聚合未发现空值。 |
| `is_active` | `tinyint` | No | `1` | Indexed | 配置状态字段；本轮未查询分布。 |
| `source` | `varchar(64)` | No | `lingxing` | None | 旧结构来源标签，不是权威来源决定。 |
| `first_seen_at` | `datetime` | Yes | `NULL` | None | 首次发现时间候选，仅作结构记录。 |
| `last_seen_at` | `datetime` | Yes | `NULL` | None | 最近发现时间候选，仅作结构记录。 |
| `created_at` | `datetime` | No | `CURRENT_TIMESTAMP` | Generated default | 旧行创建时间。 |
| `updated_at` | `datetime` | No | `CURRENT_TIMESTAMP` | Auto-updated | 行变更时间候选。 |

## 5. Primary Key and Index Summary

| Table | Primary key | Unique key | Other relevant indexes | Risk assessment |
|---|---|---|---|---|
| `dim_product` | `product_key` | `uq_dim_product(platform, store_id, item_id, msku)` | `item_id`, `platform`, `store_id` | 组合键支持 listing 粒度候选；SKU/MSKU 无独立索引，且列级重复不能被误判为组合键冲突。 |
| `dim_store` | `id` | `uq_dim_store(platform, store_id)` | `platform` | 使用 `platform + store_id` 的连接具备组合索引结构；`store_name` 不唯一。 |
| `dim_store_config` | `id` | `uq_dim_store_config(platform, store_id)` | `platform`, `is_active` | 使用 `platform + store_id` 的连接具备组合索引结构；`store_name` 不唯一。 |

## 6. Allowed Aggregate Statistics

所有比例均以精确行数为分母；只报告数量和比例，不含真实标识值。

### 6.1 `dim_product` completeness and duplicate groups

| Field | Null or blank | Null or blank rate | Duplicate groups |
|---|---:|---:|---:|
| `item_id` | 0 | 0.00% | 227 |
| `sku` | 662 | 27.06% | 271 |
| `msku` | 0 | 0.00% | 273 |

重复组是在单列、全表粒度下统计；重复组是身份粒度证据，不自动代表数据缺陷。

### 6.2 Cross-identity aggregates

| Metric | Aggregate result | Interpretation boundary |
|---|---:|---|
| ItemID associated with multiple nonblank SKUs | 3 groups | 不得据此推导 SKU。 |
| SKU associated with multiple nonblank ItemIDs | 192 groups | 不得据此推导 ItemID。 |

相关额外指标不在 Approved PRP allowlist 内，且列名/指标方向存在不一致风险，因此本报告不采纳该指标，不基于该指标作出判断。

### 6.3 Store coverage and name aggregates

| Check | Result | Rate / boundary |
|---|---:|---|
| `dim_product.store_id` populated rows | 2,446 / 2,446 | 100.00% |
| Product rows matching `dim_store` by approved aggregate join | 2,446 / 2,446 | 100.00% |
| Product rows matching `dim_store_config` by approved aggregate join | 2,446 / 2,446 | 100.00% |
| `dim_store.store_name` null or blank | 0 / 9 | 0.00% |
| `dim_store_config.store_name` null or blank | 0 / 10 | 0.00% |
| `dim_store` conflicting names for one `store_id` | 0 groups | No within-table conflict found. |
| `dim_store_config` conflicting names for one `store_id` | 0 groups | No within-table conflict found. |

当前报告无法确认该 100% 匹配统计的实际连接粒度，因此不将其作为 OD-3 关闭证据，仅作为待复核线索。

脱敏结果没有提供 `dim_product.store_name` 缺失率，也没有提供 `dim_store` 与 `dim_store_config` 之间按同一 `store_id` 比较名称是否一致的聚合。因此不能用本轮结果证明两张店铺表名称相同，也不能证明旧三层 fallback 没有必要。

## 7. ItemID / SKU / MSKU Risks

- `item_id` 和 `msku` 在 2,446 行中均无空值，但单列分别存在 227 和 273 个重复组；其唯一性必须按 `platform + store_id + item_id + msku` 组合粒度理解。
- SKU 有 662 行为空或空字符串，缺失率为 27.06%，不能作为必填字段或产品保留条件。
- SKU 存在 271 个重复组，不能被视为全局唯一身份。
- 3 个 ItemID 关联多个非空 SKU；192 个 SKU 关联多个非空 ItemID。该交叉映射证据支持保留歧义状态，禁止自动合并或互相推导。
- SKU/MSKU 缺少独立索引。未来接口如按这些字段过滤或排序，必须在接口 PRP 中单独评估查询计划与性能；本报告不批准索引变更。

## 8. Store ID / Store Name Risks

- 脱敏结果记录 `dim_product.store_id` 覆盖率为 100%，并记录产品行对两张店铺表均为 100% 匹配；当前报告无法确认匹配统计的实际连接粒度，因此仅作为待复核线索。
- 两张店铺表在自身范围内均无 `store_id` 或 `store_name` 空值，且未发现同一 `store_id` 对应多个名称的表内冲突组。
- `dim_store` 与 `dim_store_config` 的记录数不同，但当前脱敏聚合证据不足以判断两表 `store_id` 键集合是否不同，也不足以判断差异原因。
- 两张表的 `store_name` 都不是唯一键；结构和表内聚合不足以决定业务权威来源。
- 缺少跨表名称一致性聚合和 `dim_product.store_name` 缺失率，OD-3 仍不能据此关闭。

## 9. Update-field and Freshness Risks

本节只使用字段存在性、名称、类型、nullable、默认值和注释，不包含 null rate、min、max 或实际时间范围。

| Table | Structural candidate | Structural evidence | Risk |
|---|---|---|---|
| `dim_product` | `updated_at` | `datetime`, non-null, default/current auto-update, comment “更新时间” | 表示旧行最后变更的候选时间，不证明 Walmart/Lingxing 来源更新时间、业务日期或同步成功时间。 |
| `dim_store` | `updated_at` | `datetime`, non-null, default/current auto-update, comment “更新时间” | 同样只能作为行变更时间候选。 |
| `dim_store_config` | `updated_at` | `datetime`, non-null, default/current auto-update, comment “更新时间” | 同样只能作为行变更时间候选。 |
| `dim_store_config` | `first_seen_at`, `last_seen_at` | `datetime`, nullable, no default；注释分别为首次发现、最近一次在领星出现 | 名称上更接近来源发现时间，但 nullable、时区、写入方和更新保证均未由本次结构证据确认。 |

`created_at` 仅能表示旧行创建候选时间。排除域专用更新时间字段不用于产品基础信息新鲜度判断。本轮没有可证明 source update、sync run、时区或业务日口径的字段，因此新鲜度仍是阻塞风险。

## 10. Preliminary Evidence for OD-1

本轮证据对 OD-1 提供“结构上有条件支持”，但不是负责人批准：

- 三表存在，精确规模分别为 2,446、9、10 行。
- `dim_product` 的 `item_id`、`msku`、`store_id` 无空值，且组合唯一键明确。
- 脱敏结果记录产品行对两张店铺表均为 100% 匹配，但实际连接粒度无法确认，仅作为待复核线索。
- 主要连接键具备适用的单列或组合索引结构。

保留风险：SKU 缺失和多对多歧义明显；SKU/MSKU 无独立索引；名称字段和来源新鲜度未充分验证；接口分页、过滤、超时、并发、只读账号权限边界与可验证退出里程碑仍未定义。因此 OD-1 仍需 Project Owner 明确决定。

## 11. Preliminary Evidence for OD-3

两张店铺表在结构上都具备 `platform + store_id` 唯一键。脱敏结果记录产品行对两表均达到 100% 匹配，但当前报告无法确认该统计的实际连接粒度，因此不将其作为 OD-3 关闭证据，仅作为待复核线索。两表各自的名称缺失和表内冲突聚合均为 0。

但本轮没有跨表名称一致性聚合，且 `dim_product.store_name` 缺失率未提供。三张表中哪张是唯一权威来源、是否展示 `store_name`、如何处理别名或冲突，均不能由现有证据决定。OD-3 必须保持 `NEED_OWNER_DECISION`。

## 12. Source Decision Update Recommendation

建议架构师在只读 Review 后更新 Source Decision，加入以下已验证证据：

1. 三张候选旧表真实存在，规模和关键结构已确认。
2. ItemID、MSKU、`store_id` 完整，但列级重复与跨身份歧义存在。
3. SKU 缺失率为 27.06%，且不能作为全局唯一身份。
4. 脱敏结果记录两张店铺表均达到 100% 匹配，但实际连接粒度无法确认，且唯一权威来源仍未确定。
5. 旧表只有行变更/发现时间候选，不能证明外部来源新鲜度。

不得由本报告自动把 Source Decision 改为 `READY_FOR_PRP`。该状态变化仍需架构师复审和负责人解决 OD-1、OD-3 及其他未决门禁。

## 13. Remaining Owner Decisions and Evidence Gaps

| Item | State | Required owner / review action |
|---|---|---|
| OD-1 temporary legacy read | `NEED_OWNER_DECISION` | 决定是否接受有条件临时只读，并定义表/字段范围、分页、性能、只读账号、风险提示与退出里程碑。 |
| OD-3 store-name authority | `NEED_OWNER_DECISION` | 选择唯一权威来源或要求新的、单独批准的跨表脱敏聚合证据。 |
| Cross-table store-name agreement | Evidence gap | 本轮脱敏结果未提供，禁止猜测。 |
| `dim_product.store_name` completeness | Evidence gap | 字段结构为 nullable，但本轮未提供缺失聚合。 |
| Source freshness | Evidence gap | 结构候选不能证明来源更新时间、同步完成时间、时区或实际新鲜度。 |

## 14. Safety and Non-disclosure Confirmation

- 未导出、展示或写入任何真实 SKU、MSKU、ItemID、`store_id` 或 `store_name` 明细。
- 未导出真实业务样本或样本行。
- 未查询或报告成本、价格、利润、库存、广告、结算、退款、负责人、生命周期等禁用字段值。
- 未读取或输出密码、token、secret、连接字符串或其他凭据。
- 未使用 root SSH 或 MySQL root。
- 未写库，未执行 DML、DDL、migration、回填或同步。
- 未建表、改表、建索引、建 view 或创建临时表。
- 未修改 `backend/`、`frontend/` 或 `old-system/`。
- 未调用任何外部 API，未部署或重启服务。

## 15. Stop Conditions

报告生成阶段未触发新的停止条件。第一条只读聚合因 `ONLY_FULL_GROUP_BY` 报错后未产生写入；等价聚合修正由负责人在本机终端执行，并产生本报告使用的脱敏输出。对缺失或列名不一致的统计，本报告保留证据缺口，没有重新连接数据库、执行补充 SQL 或扩大范围。

## 16. Conclusion

OD-9 已形成可供架构师复审的脱敏数据库证据。三表结构上可支持有限的产品基础信息临时只读候选，但 SKU 完整性、身份歧义、店铺名称权威来源和来源新鲜度风险尚未解决。

OD-1 和 OD-3 仍需负责人决定；本报告不批准接口 PRP、API、schema、migration、同步、写库或 Source Decision 状态变化。

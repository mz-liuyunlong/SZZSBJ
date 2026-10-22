# Walmart Monitor Target Source 数据源决策

- 调查日期：2026-10-22
- 调查人：Codex（只读仓库证据调查）
- 目标 method/path：`GET /api/integrations/walmart-monitor/targets`
- 业务用途：向独立监控程序提供当前 Listing 监控目标、类目和稳定业务键
- 接口总体状态：`READY_FOR_PRP`
- 是否包含 `NEED_OWNER_DECISION`：否
- 负责人批准状态：已批准本期未归档 Listing 具备资格、保留资格字段；归档 Listing 不返回
- 关联证据：`backend/app/modules/data_pages/models.py`、`repository.py`、`service.py`、监控端 `lib/integrations/product-source.ts`
- 决策文件路径：`docs/data-sources/decisions/walmart-monitor-target-source-decision.md`
- 后续接口 PRP：`PRPs/walmart-monitor-target-source.md`

## 1. 前置调查

| 前置调查项 | 证据位置与调查结论 |
|---|---|
| 旧页面 | 不适用；本接口无页面。 |
| 旧 API | 当前监控端曾读取旧商品来源接口；新接口不复用旧接口或旧数据库。 |
| 旧接口文件位置 | 不读取、不修改 `old-system/**`；仅以监控端当前 client contract 作为消费者证据。 |
| 读取表 | `mart_listing_management_current`，现有 L9 Listing 当前态读模型。 |
| 表写入方 | 现有 DATA-PAGES Listing MART refresh；本接口不写表。 |
| cron / 脚本 / 外部 API | MART 由既有同步更新；HTTP 请求期间不调用 Lingxing/Walmart/Decodo，不触发 Celery。 |
| 人工写库入口 | 无；资格字段 V1 是接口派生常量，不落库。 |
| 外部平台重新获取可能性 | 由既有同步负责；本接口只读取已同步数据，不在 route 中回源。 |
| 少量配置数据可行性 | 仅需要部署环境中的只读 bearer secret；不新增业务配置表。 |
| 短期策略 | 分页读取 Listing MART，映射批准字段，资格固定 `true`。 |
| 长期策略 | 资格要求出现后，以独立 Source Decision/PRP 增加治理规则；保持响应字段兼容。 |

## 2. 数据集分类

| 数据集或字段组 | 业务用途 | 当前权威来源 | 分类 | 短期策略 | 长期策略 | 退出条件或切换点 | 需负责人确认 |
|---|---|---|---|---|---|---|---|
| Listing identity/描述/类目/库存当前态 | 监控目标来源 | Lingxing 等既有同步经标准化后生成的 Listing MART | `REBUILD_SYNC` | API 只读现有 MART，不实时回源 | 继续由既有 integration 更新 | MART 被批准的新 canonical read model 替代 | 否 |
| `monitoring_eligible` | 控制监控程序排队 | 新系统接口规则 | `NEW_SYSTEM_OWNED` | 对返回的未归档 Listing 固定 `true`，不依赖库存 | 后续按批准规则计算 | 负责人提出并批准新资格规则 | 否 |
| service token 和访问判定 | 机器最小权限认证 | 新系统配置和 auth policy | `NEW_SYSTEM_OWNED` | 精确 GET 路径、独立只读 permission | 可迁移到统一 service identity | 统一机器身份治理上线 | 否 |

## 3. 数据血缘

| 接口字段 | 源表 | 原始字段 | 转换 | 新鲜度/风险 |
|---|---|---|---|---|
| `source_account_ref` | `mart_listing_management_current` | 同名 | 原样 | 稳定键，非空 |
| `store_id` / `item_id` | 同上 | 同名 | 原样 | 与账号共同唯一 |
| `store_name` | 同上 | 同名 | 原样可空 | 描述字段 |
| `sku` | 同上 | `local_sku` | 原样可空 | 不从 MSKU/ItemID 推断 |
| `msku` | 同上 | 同名 | 原样可空 | 不从 SKU 推断 |
| `owner` | 同上 | `owner_ref` | 原样可空 | 仅批准的来源描述 |
| `product_name` | 同上 | `local_name` | 原样可空 | 不以页面 title 覆盖本地品名 |
| `product_category` | 同上 | `category` | 原样可空 | 商品来源类目，不等于页面抓取类目 |
| `wfs_inventory` | 同上 | `wfs_available_quantity` | Decimal 字符串或 `null` | 不把未知值伪造为 0 |
| `monitoring_eligible` | 接口规则 | 无物理字段 | V1 固定 `true` | 不以库存高低决定资格 |

## 4. 安全与数据范围

- permissionKey：`integrations:walmart-monitor:read`。
- 独立 machine principal 仅能访问精确 GET 路径；token 至少 32 位 ASCII、constant-time compare、默认未配置即 fail closed。
- 数据范围：当前 Listing MART 中未归档的行；用 `listing_archive_states.listing_id` 与当前 MART ID 关联并排除 `is_archived=true`；不复用用户组织/角色，也不授予其他 API。
- 响应不含价格、利润、成本、GPT、归档、备注、URL、payload 或密钥。
- 每页最多 500；固定稳定排序，避免分页重复或漏行。

## 5. 最终建议

- 接口总体状态：`READY_FOR_PRP`
- 推荐短期策略：只读现有 Listing MART，并显式返回资格和可空库存。
- 推荐长期策略：资格变化时另立规则 PRP；不预建资格表。
- 旧库退出条件：新接口部署并联调后，监控端删除旧商品来源 URL 配置；运行时无旧库 fallback。
- 迁移或同步边界：不新增 migration，不改同步任务，不回填历史。
- 主要风险：服务 token 泄漏、分页漂移、库存 null 被误解释；由精确权限、稳定排序和契约测试控制。
- 待负责人决定：无。

## 6. 负责人决定记录

- 决定：批准进入 PRP 并完成本地实现。
- 批准范围：当前未归档 Listing 具备监控资格，归档 Listing 不返回；保留 `monitoring_eligible`；新系统提供商品来源和 RAW 接收接口。
- 约束：本批准不包含生产部署、配置 secret、生产数据库操作、真实监控或外部 API 调用。
- 批准日期：2026-10-22。

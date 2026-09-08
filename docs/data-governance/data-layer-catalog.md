# 数据层目录（Data Layer Catalog）

> 规则状态：仅在负责人 Review 并合并后成为 `approved` 基线。
> 实现状态：除非引用独立实现证据，以下能力均为 `planned`。
> Scope: 逻辑分层与数据流边界。
> Non-goals: 不创建表、不要求一层一表，也不授权迁移。

本文按核心数据管道、治理支撑、平台能力三个视角重组既有 L0-L19 标准，但不替代 `docs/data-sources/database-layering-standard.md`。层级较高不自动代表数据正确；字段或数据集的权威性必须由已批准的 Source Decision 指定。

## A. Core Data Pipeline

| layer_code | layer_name | 中文名称 | purpose | typical_data | typical_tables | allowed_writers | allowed_readers | frontend_access | ai_access | authority_level | retention_policy | forbidden_usage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| L0 | Source System | 来源系统层 | 登记来源、责任人与获取方式 | 外部 API、文件、旧库、人工来源的元数据 | 来源注册表，不复制来源系统 | 来源负责人、治理维护流程 | 调查与获批采集任务 | 禁止 | 仅可读元数据 | 外部证据/候选 | 按来源契约 | 把“存在”当“已批准”；前端直连 |
| L1 | Ingestion / Landing | 摄取/落地区 | 解析前接收不可变批次 | 文件、payload envelope、交付元数据 | 对象存储、批次 manifest | 获批采集任务 | 解析、恢复任务 | 禁止 | 禁止业务使用 | 传输证据 | 明确的短期恢复窗口 | 业务查询；静默修改；混合批次 |
| L2 | RAW/Bronze | 原始证据层 | 保留原始载荷与采集上下文 | 原始记录、source/run/ingested 元数据 | `raw_*`、只追加分区 | 获批 connector | 标准化、重放、审计 | 禁止 | 仅限获批且受控的证据提取 | 来源证据，非业务权威 | 按来源单独定义 | 人工编辑；直接对外服务；保存密钥 |
| L3 | Standardized/Cleansed | 标准化清洗层 | 统一类型、名称、单位、时间与空值 | 带 DQ 状态的类型化来源记录 | `stg_*`、`std_*` | 幂等清洗任务 | 规范化与 DQ Review | 禁止 | 仅限获批范围 | 候选 | 可重建，法规另有要求除外 | 编造值；覆盖 RAW；猜测身份 |
| L4 | Core/Canonical | 核心规范层 | 跨来源统一业务语义与来源优先级 | 规范字段、确定性规则结果 | `core_*`、canonical model | 获批转换任务 | DIM/FACT 构建、受保护 service | 仅通过 API | 受控使用 | 由字段级决策确定 | 业务留存并保留血缘 | 泄漏来源字段；未记录 fallback；无版本改历史 |
| L7 | DIM/MASTER | 维度/主数据层 | 维护稳定实体身份与描述属性 | 产品、店铺、用户、账号 | `dim_*`、`master_*` | 获批 MDM、同步或人工覆盖流程 | FACT/MART、受保护 repository | 仅通过 API | 仅经授权 API/read model | 已批准属性可为高权威 | 按实体保留历史/SCD | 弱自然键当主身份；绕过 MDM；泄漏敏感字段 |
| L8 | FACT | 事实层 | 保存可审计业务事实与度量 | 销售、库存变动、广告、结算 | `fact_*` | 获批事件/同步管道 | MART、对账、受保护 repository | 仅通过 API | 仅聚合且受权限控制 | 已批准度量可为高权威 | 不可变或版本化更正 | 改写已结算历史；金额用 float；混合粒度 |
| L9 | MART/READ MODEL | 主题集市/读模型 | 为单一查询契约提供高效读取 | 页面/API 专用联结与聚合 | `mart_*`、`read_*` | 获批重建任务或投影 | 单一受限 API/模块 | 仅通过 API | 仅限批准用途和字段 | 派生 | 可重建；声明刷新与过期 | 第二权威源；隐藏公式；跨模块垃圾桶 |
| L10 | MANUAL/OVERRIDE | 人工维护/覆盖层 | 不破坏来源事实地记录人工更正 | override、审批、原因、生效期 | `manual_*`、`override_*` | 有权限且有审计的用户/服务 | 规范解析与审计 | 仅经受保护 action/API | 默认不可用于训练 | 仅在批准字段、范围和时段内有权威 | 完整历史 | 修改 RAW；无审计覆盖；默认全局生效 |
| L18 | ARCHIVE/RETENTION | 归档/留存层 | 按政策保存非活跃证据 | 冷数据、退役批次、旧版本 | 归档存储/表 | 留存任务 | 审计、法律、获批恢复 | 禁止 | 通常禁止 | 历史证据 | 明确法规/业务期限 | 服务活跃 API；默认永久保留；静默恢复 |

## B. Governance and Audit Support

| layer_code | layer_name | 中文名称 | purpose | typical_data | typical_tables | allowed_writers | allowed_readers | frontend_access | ai_access | authority_level | retention_policy | forbidden_usage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| META-CFD | Canonical Field Dictionary | 规范字段字典 | 定义规范名称、类型、语义、敏感性、owner 与来源映射 | 字段定义、映射规则 | 元数据注册表/文档 | 数据 owner 与获批治理流程 | PRP、schema/API Review、转换任务 | 仅文档/API 元数据 | 仅元数据 | 治理权威 | 永久版本化 | 保存业务值；未审查重命名；重复定义 |
| L5 | Reference Data | 参考数据层 | 治理少量受控代码集 | 币种、平台、国家、状态字典 | `ref_*` | 获批配置流程 | 校验、转换、API | 仅通过 API | 获批 lookup | 对已批准代码有权威 | 版本化，必要时含生效期 | 用自由文本替代码；破坏性更新 |
| L6 | Identity Mapping/MDM | 身份映射/主数据层 | 解析跨来源身份、别名与合并 | 内部 ID、外部 ID、置信度、合并历史 | `identity_*`、`mdm_*`、mapping 表 | 获批确定性同步或人工 Review | Core/DIM、受保护 service | 仅通过 API | 受限且按目的 | 仅批准解析后为高权威 | 保留完整映射与合并历史 | 猜测匹配；SKU 当全局身份；静默合并 |
| L11 | Business Event | 业务事件层 | 记录获批业务流程发生的领域事件 | created、approved、synced、settled 事件 | event log/outbox | 事务 service/outbox | worker、审计、投影 | 禁止直读 | 需单独批准 | 事件证据 | 声明重放与留存 | 把日志当状态；事件含密钥；擅自启用 CDC |
| L12 | Audit/Lineage | 审计/血缘层 | 证明谁/什么改变数据以及输出如何形成 | 审计动作、run ID、字段血缘、版本 | audit log、lineage edge、run manifest | 平台控制与获批任务 | Review、运维、事故处理 | 仅受保护审计 API | 仅 provenance | 证据权威 | 防篡改并按政策留存 | 保存业务真相；可编辑历史；缺 actor/run ID |

### Event、Audit、Lineage 与 CDC 的区别

| 能力 | 记录什么 | 是否业务权威 | 本轮状态 | 禁止混用 |
| --- | --- | --- | --- | --- |
| Business Event | 已获批业务流程发生的领域事件 | 仅是事件证据，不是当前状态本身 | planned | 不用作操作审计或数据库变更镜像 |
| Audit Log | actor 在何时对何目标执行何动作及结果 | 责任证据 | planned | 不作为主数据或业务事件流 |
| Lineage Record | 来源、原始记录、转换规则与目标之间的推导 | 血缘证据 | planned | 不保存业务 effective value |
| CDC | 数据库行变化流 | 非权威复制机制 | candidate；本轮不批准实现 | 不等同领域事件，不得绕过 Source Decision |

## C. Platform Capability

| layer_code | layer_name | 中文名称 | purpose | typical_data | typical_tables | allowed_writers | allowed_readers | frontend_access | ai_access | authority_level | retention_policy | forbidden_usage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| L13 | DOC/Knowledge | 文档/知识层 | 保存受治理文档与知识单元 | SOP、API 文档、政策、获批原文 | document registry/chunk | 获批发布与摄取任务 | 搜索/RAG、文档 UI | 仅通过 API | 带来源与 ACL | 仅文档权威 | 按来源和版本 | 生成文本当来源；摄取密钥；丢失版本 |
| L14 | Search/Vector | 检索/向量层 | 加速关键词或语义检索 | index、embedding、chunk reference | search index/vector store | 可重建索引任务 | 获批搜索/RAG service | 仅通过 API | 只用于检索 | 派生 | 可重建；删除需级联 | 当权威源；绕过 ACL；孤儿向量 |
| L15 | AI/Intelligence | AI/智能层 | 保存受治理 AI 运行与派生输出 | prompt、model metadata、citation、review status | AI run/output registry | 获批 adapter/workflow | 有权 reviewer 与应用 | 仅通过 API | 原生用途 | 人审前为派生/候选 | 按用途与敏感级别 | 自动写回权威数据；无引用结论；擅自训练 |
| L16 | Feature Store | 特征层 | 在确有需要时复用版本化模型特征 | point-in-time feature 与定义 | feature registry/store | 获批 feature pipeline | 获批模型/service | 禁止 | 仅批准模型 | 派生 | 声明时间点与留存 | 预建空壳；标签泄漏；业务 API 数据源 |
| L17 | Cache/Snapshot | 缓存/快照层 | 提升延迟或冻结声明时点视图 | cache response、snapshot、materialized extract | cache key/snapshot table | 所属 service/job | 所属 service | 经所属 API | 不可独立使用 | 非权威 | 必须有 TTL/过期 | 永久真相；隐形陈旧 fallback；key 存密钥 |
| L19 | Sandbox | 沙箱层 | 隔离临时分析且不得形成生产依赖 | 测试聚合、可丢弃实验 | 临时 schema/file | 明确获批任务 | 任务 owner | 禁止 | 禁止生产训练/使用 | 无 | 自动过期 | 生产依赖；敏感导出；未经 PRP 晋升 |

## 数据流与最小分层

默认流向为 `L0 → L1 → L2 → L3 → L4 → L7/L8 → L9 → API`；Reference、Identity、Manual、Event、Audit 与平台能力只在实际需要时加入。

任务可不建立某个物理层，但 PRP 必须同时证明：来源可恢复或无需重放且理由成立；转换与字段血缘可 Review；API 不直查 RAW、不承担批量清洗；身份、权限、新鲜度、留存和 DQ 边界明确；回滚只移除本任务产物。

禁止流向包括：`frontend → database`、`frontend → external platform`、`RAW → public API`、`route handler → external platform 批量实时拉取`、`manual edit → RAW`、`AI output → authoritative data`（未经人审晋升）。

### Cache 与 Snapshot 的区别

| 能力 | 生命周期 | 恢复方式 | 权威性 | 必须记录 |
| --- | --- | --- | --- | --- |
| Cache | 短期 TTL，可随时过期 | 从获批来源重建 | 非权威 | cache key 边界、TTL、source version/freshness |
| Snapshot | 代表声明时点；有业务价值时按政策留存 | 从原始输入/版本化规则重现，或受控恢复 | 非权威历史视图 | snapshot time、grain、source/rule version、retention |

## 层级硬规则

1. RAW 不得被前端直接查询，也不得被业务接口直接当最终口径。
2. Standardized/Cleansed 只做可解释标准化，不得随意改变业务含义。
3. DIM/MASTER 不保存每日变化事实；FACT 不保存人工备注或主数据定义。
4. MART/READ MODEL 是派生服务层，不是权威真源。
5. MANUAL/OVERRIDE 不能直接覆盖外部同步字段，二者必须分开存储并按批准规则解析。
6. ARCHIVE/RETENTION 不能成为热业务接口依赖。
7. DOC、Search/Vector、AI、Feature Store、Cache/Snapshot、Sandbox 都是平台能力，不是业务权威真源。
8. Cache 是可过期、可重建的临时副本；Snapshot 是某个声明时点的历史视图，只有具备业务价值并定义留存策略时才保存。
9. Search/Vector index 必须可重建并追溯到原文档或主数据；AI 输出不能自动覆盖业务数据。
10. Feature Store 只为获批模型/评分/异常检测服务，不得成为业务事实源；Sandbox 必须有负责人、过期时间且不得进入生产接口。

## 示例（非实现）

| 场景 | 推荐分层 | status |
| --- | --- | --- |
| 外部 CSV 批次 | Source Registry → Landing → RAW → Standardized；后续层由 Source Decision 决定 | candidate |
| 页面聚合查询 | 受保护 API 读取获批 MART/READ MODEL，权威字段仍回溯 Core/DIM/FACT | candidate |
| 旧库历史清洗表 | 标记 `legacy_reference`/`legacy_derived`，不得改名冒充 RAW | legacy_reference |

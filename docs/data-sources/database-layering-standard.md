# Database Layering Standard

```text
Status: Active after merge to main
Owner Approval Required: Yes through PR review and merge
Applies To: All new database design, data source decisions, backend API PRPs, sync tasks, mart/read-model design, AI data usage, and document knowledge indexing
```

## 1. Purpose and authorization boundary

This standard defines where data belongs and which layers may depend on it. It is a classification and review rule, not implementation approval.

- It does not authorize a table, schema, migration, synchronization job, worker, API, database connection, or deployment.
- Real tables, migrations, synchronization work and APIs require their own approved PRP and owner-authorized execution prompt.
- Data-source authority is decided separately through `docs/delivery/backend-data-source-decision-gate.md`.
- A page may query a MART / READ MODEL, but that read model is not the authoritative source.
- Frontend-facing business APIs must not query RAW directly.
- A legacy database may only be used through an approved `READ_LEGACY_TEMPORARILY` read-only transition with a defined exit condition.
- AI output may be stored as a suggestion or analysis artifact, but must not automatically overwrite business master or fact data.
- SOPs, policies, manuals, PRPs and rules must be versioned, statused and permission-controlled when indexed or served as knowledge.
- Every new backend API PRP must state the queried layer, authoritative source, lineage, permissions and data-quality risks.

Layer names and example artifacts below are architectural categories. They do not assert that the named physical tables exist or are approved.

## 2. Core flow and selection rules

The default governed flow is:

```text
L0 Source
  → L1 Landing
  → L2 RAW
  → L3 Standardized
  → L4 Canonical
  → L5 Reference / L6 Identity
  → L7 DIM or L8 FACT
  → L9 MART / READ MODEL
  → Backend API
  → Frontend
```

Not every use case needs every physical layer. A PRP may omit a layer only when it records why lineage, replayability, authority and quality controls remain intact. Priority in the table means governance importance when the layer is relevant; it is not an instruction to build all layers in advance.

## 3. Data layers L0–L19

| Layer | Name | Chinese Name | Purpose | What Belongs Here | Typical Tables / Artifacts | Primary Users | Allowed Usage | Forbidden Usage | Naming Convention | Priority |
|---|---|---|---|---|---|---|---|---|---|---|
| L0 | Source System | 来源系统 | Identify the system that originally owns or emits data. | External platforms, legacy applications, files and human-operated source systems. | Walmart, Lingxing, Feishu, legacy MySQL, approved imports. | Architects, integration engineers, source owners. | Source discovery, contract verification and approved ingestion. | Treating an external schema or legacy table as a new-system contract without a Source Decision. | Preserve official source name and source identifier. | P0 evidence boundary. |
| L1 | Ingestion / Landing | 接入落地区 | Receive source payloads before business transformation. | Delivery envelopes, import batches, request metadata and ingestion manifests. | `landing_<source>_<object>`, batch manifests. | Integration and data engineers. | Validate delivery, deduplicate batches and hand off to RAW. | Serving business APIs or silently changing business meaning. | `landing_<source>_<object>`. | P0 when ingestion exists. |
| L2 | RAW / Bronze | 原始留痕层 | Preserve replayable source evidence. | Immutable or append-only source payloads, source keys and receipt metadata. | `raw_<source>_<object>`, raw files with checksums. | Integration, audit and incident investigation. | Replay, reconciliation and evidence inspection under permission. | Direct frontend/business API queries; treating RAW as authoritative business truth; manual correction in place. | `raw_<source>_<object>`. | P0 for external sync. |
| L3 | Standardized / Cleansed | 标准化清洗层 | Apply typed, documented, reversible cleaning. | Parsed types, normalized nulls, units, currencies, timestamps and source-preserving fields. | `stg_<domain>_<object>`, `std_<domain>_<object>`. | Data and backend engineers. | Feed canonical models after quality checks. | Declaring business authority or silently discarding source value and lineage. | `stg_` or `std_`; one convention per PRP. | P0 before canonical use. |
| L4 | Canonical / Conformed | 统一语义层 | Express one governed cross-source business representation. | Conformed grains, canonical fields and explicit source precedence. | `canonical_<domain>_<entity>`. | Architects, data and backend engineers. | Feed master/fact models after Source Decision. | Inventing semantics from field names or merging sources without precedence. | `canonical_<domain>_<entity>`. | P0 for multi-source domains. |
| L5 | Reference Data | 参考数据层 | Govern stable codes, enums and controlled vocabularies. | Platform codes, country codes, status mappings, units and currencies. | `ref_platform`, `ref_currency`, `ref_status_mapping`. | All application and data layers. | Validate and translate approved values with versioning where needed. | Embedding conflicting copies of enums in routes, marts or clients. | `ref_<subject>`. | P0 when shared codes exist. |
| L6 | Identity Mapping / MDM | 身份映射与主数据匹配层 | Resolve identities without collapsing distinct source IDs. | Crosswalks, match evidence, survivorship and merge history. | `map_product_listing`, `mdm_entity_match`. | Data stewards, backend and integration engineers. | Map external IDs to internal IDs with auditability. | Inferring SKU, MSKU and ItemID from one another; destructive merge without approval. | `map_<a>_<b>` or `mdm_<entity>_<purpose>`. | P0 for cross-source identity. |
| L7 | DIM / MASTER | 维度与主数据层 | Hold governed descriptive entities at a declared grain. | Products, listings, stores and other approved master attributes. | `dim_products`, `dim_product_listings`, `dim_stores`. | Backend APIs, facts and marts. | Read/write through approved ownership and audit rules. | Absorbing transactions, daily metrics, AI guesses or unscoped manual overrides. | `dim_<plural_entity>` or approved project convention. | P0 core business model. |
| L8 | FACT | 事实层 | Store measurable events or periodic snapshots at a declared grain. | Sales, inventory, advertising, profit and other dated measures. | `fact_sales_daily`, `fact_inventory_daily`. | Analytics, marts and governed APIs. | Aggregate with explicit grain, time, currency and rule versions. | Mixing descriptive master ownership into facts or storing measures without grain. | `fact_<subject>_<grain>`. | P0 for metrics. |
| L9 | MART / READ MODEL | 数据集市与读模型层 | Optimize a specific page, report or API query. | Denormalized projections and precomputed views derived from governed layers. | `mart_product_management_list`, `rm_<module>_<use_case>`. | Backend query services and reports. | Serve scoped reads with documented refresh and lineage. | Being the only truth source, receiving source/manual writes, or hiding transformation logic. | `mart_<module>_<use_case>` or `rm_<module>_<use_case>`. | P1, create only for measured need. |
| L10 | MANUAL / OVERRIDE | 人工维护与覆盖层 | Isolate human-entered values and approved corrections. | Tags, notes, ownership, aliases, lifecycle decisions and correction proposals. | `manual_product_overrides`, `override_<domain>_<field>`. | Authorized operators and audited services. | Apply explicit precedence, effective dates, permissions and audit logs. | Writing directly into external-sync, RAW, master or fact tables without a governed merge rule. | `manual_` or `override_`. | P0 when manual input exists. |
| L11 | EVENT / CDC | 事件与变更捕获层 | Record changes for asynchronous processing and traceability. | Domain events, outbox records and approved CDC envelopes. | `event_<domain>_<action>`, `cdc_<source>_<object>`. | Workers, integrations and audit consumers. | Publish idempotent, schema-versioned events. | Treating an event stream as current-state authority or exposing secrets. | `event_` / `cdc_` plus subject. | P1 when asynchronous flow exists. |
| L12 | AUDIT / LINEAGE | 审计与血缘层 | Prove who changed what, where data came from and which checks ran. | Audit events, lineage edges, DQ runs and reconciliation results. | `audit_<subject>`, `lineage_<subject>`, `dq_run_<subject>`. | Security, operations, architects and auditors. | Immutable review, incident tracing and compliance reporting. | Using audit records as editable operational state or deleting evidence outside retention rules. | `audit_`, `lineage_`, `dq_run_`. | P0 for sensitive or mutable data. |
| L13 | DOC / KNOWLEDGE | 文档与知识层 | Govern versioned textual knowledge separately from business facts. | SOPs, policies, manuals, PRPs, rules and approved source documents. | `doc_<collection>`, `knowledge_<collection>` plus repository documents. | Users, support and approved AI retrieval. | Version, status, permission, cite and retire knowledge artifacts. | Treating drafts or retrieved text as approved business facts. | `doc_` / `knowledge_`; preserve document identity and version. | P1 when knowledge services exist. |
| L14 | SEARCH / VECTOR INDEX | 搜索与向量索引层 | Provide rebuildable retrieval acceleration. | Search documents, tokens, embeddings and index metadata. | `search_<collection>`, `vector_<collection>`. | Search and retrieval services. | Rebuild from governed source; retain source/version references. | Acting as authority, storing untraceable text, or bypassing document permissions. | `search_` / `vector_`. | P2, only when retrieval needs it. |
| L15 | AI / INTELLIGENCE | AI 与智能结果层 | Store bounded AI outputs, provenance and review state. | Summaries, classifications, recommendations, confidence and prompt/model metadata. | `ai_<use_case>_result`, `insight_<subject>`, `suggestion_<subject>`. | Authorized users and review workflows. | Present as assistive output with provenance, confidence and approval state. | Automatically overwriting master/fact data or presenting generated output as verified fact. | `ai_`, `insight_`, `suggestion_`. | P2, separate AI PRP required. |
| L16 | FEATURE STORE | 特征层 | Reuse governed model features consistently. | Versioned offline/online features with event time and freshness. | `feature_<entity>_<name>`. | Approved ML training and inference. | Serve documented features with leakage and freshness checks. | Building speculatively, mixing labels into online features, or bypassing AI governance. | `feature_<entity>_<name>`. | P3, only for approved ML need. |
| L17 | CACHE / SNAPSHOT | 缓存与快照层 | Improve latency or preserve a point-in-time read copy. | Expiring caches and reproducible snapshots. | `cache_<use_case>`, `snapshot_<subject>_<grain>`. | Application and reporting services. | Rebuild or expire from an authoritative source; expose freshness. | Becoming authority, receiving permanent manual edits, or hiding stale data. | `cache_` / `snapshot_`. | P2, performance-driven only. |
| L18 | ARCHIVE / RETENTION | 归档与保留层 | Retain inactive data under explicit legal and operational policy. | Cold history, retired datasets and deletion/retention manifests. | `archive_<subject>`, retention manifests. | Audit, legal and operations. | Controlled restore, retention and deletion. | Serving default online business queries or indefinite retention without policy. | `archive_<subject>`. | P1 when lifecycle requires it. |
| L19 | SANDBOX / EXPERIMENT | 沙箱与实验层 | Isolate temporary analysis and prototypes from production contracts. | Disposable datasets, experiments and non-production outputs. | `sandbox_<owner>_<subject>`, `exp_<subject>`. | Analysts and engineers under task scope. | Time-bounded experiments with synthetic or approved data. | Feeding production APIs, becoming authority, or retaining production data without approval. | `sandbox_` / `exp_`, with owner and expiry. | P3, temporary only. |

## 4. Governance planes G1–G10

Governance planes apply across layers; they are not additional storage layers.

| Governance | Name | Purpose | Problem Prevented | Required Artifacts | Consequence If Missing | Tasks That Must Reference It |
|---|---|---|---|---|---|---|
| G1 | Metric / Semantic | Define business metrics, grain and meaning. | Conflicting formulas and misleading reports. | Metric dictionary, formula, grain, owner, effective version. | Metric work remains blocked or draft. | Facts, marts, reports and metric APIs. |
| G2 | Data Quality | Define measurable completeness, uniqueness, validity and freshness. | Silent bad data and false confidence. | DQ rules, thresholds, run records and remediation owner. | Data cannot be claimed ready or reliable. | Syncs, canonical models, masters, facts and marts. |
| G3 | Data Contract | Stabilize producer/consumer schemas and compatibility. | Undetected breaking changes. | Versioned schema, required fields, nullability and compatibility policy. | Producer changes cannot be safely released. | Ingestion, events, APIs and shared datasets. |
| G4 | Permission / Data Scope | Control page, action, row and field access. | Sensitive-data exposure. | `permissionKey`, data-scope rules, field sensitivity and audit plan. | Sensitive fields and endpoints must not ship. | APIs, marts, exports, AI and document retrieval. |
| G5 | Business Rules / Config | Version decisions that change outcomes. | Hard-coded policy and rewritten history. | Rule owner, version, effective dates, approval and rollback. | Rule-dependent outputs remain unapproved. | Costs, profit, lifecycle, status and manual override logic. |
| G6 | Field Standardization | Define canonical fields and reversible cleaning. | Duplicate names, type drift and lost source meaning. | Field dictionary and `field-standardization-standard.md` evidence. | Field cannot enter a contract or canonical layer. | Ingestion, models, mappings and API responses. |
| G7 | Schema Registry | Track machine-readable versions and compatibility. | Producers and consumers disagreeing silently. | Registered schema/version and compatibility checks. | Cross-service or event changes are blocked. | Events, CDC, files and integration contracts. |
| G8 | Lifecycle / Retention | Define retention, archival and deletion. | Indefinite storage or premature loss. | Retention class, archive/delete rule, legal hold and owner. | Dataset cannot move to archive or be safely deleted. | RAW, audit, documents, AI outputs and snapshots. |
| G9 | AI Governance | Bound models, prompts, data use and human review. | Untraceable AI decisions or unauthorized writes. | Use-case PRP, model/prompt versions, provenance, evaluation, budget and review policy. | AI output remains advisory and cannot affect business state. | AI, feature store, vector retrieval and agent workflows. |
| G10 | Knowledge Governance | Control document authority, version and access. | Draft or stale documents being treated as policy. | Document owner, status, version, permissions, citation and retirement rule. | Knowledge cannot be presented as approved authority. | SOPs, policies, PRPs, search and RAG/indexing. |

## 5. Read, write and authority boundaries

1. Online business reads should use L7/L8 directly only when the query remains bounded; otherwise use a justified L9 read model.
2. L9, L14 and L17 are projections or accelerators and must be rebuildable from a documented authority.
3. L2 preserves evidence; L3 cleans representation; L4 conforms meaning. None becomes authoritative merely by being cleaner.
4. L10 must retain actor, reason, effective time and original value, and must declare how an override is applied.
5. L13–L16 never bypass G4, G8, G9 or G10.
6. Every layer transition must record source, destination, grain, transformation, writer, freshness and evidence path.

## 6. Product Management example

This example illustrates intended layering; it does not approve tables or implementation.

### 6.1 Short-term transition

```text
Frontend Product Management
  → Backend API
  → Legacy Readonly Repository
  → legacy dim_product / dim_store / dim_store_config
```

- This path is allowed only after the interface Source Decision is approved and OD-9 database inventory is completed.
- Access must remain read-only and limited to the approved product-basic-information scope, pagination and performance boundaries.
- It must carry a measurable exit condition; it does not make the legacy database the permanent new-system authority.

### 6.2 Long-term target

```text
Frontend Product Management
  → Backend API
  → mart_product_management_list
  → dim_products / dim_product_listings / dim_stores
  → fact_inventory_daily / fact_sales_daily / fact_ads_daily / fact_profit_daily
  → manual_product_overrides
  → audit / data quality / lineage
```

- `mart_product_management_list` is a page read model, not the source of truth.
- `dim_products` and related master tables must not absorb sales, inventory, advertising, profit, refunds or settlement facts.
- Owners, tags, lifecycle decisions, notes and corrections belong in MANUAL / OVERRIDE with permissions and audit, not in external-sync fields.
- AI summaries and suggestions belong in AI / INTELLIGENCE and must never automatically overwrite master data.
- SOPs, company policies, manuals, PRPs and rules belong in DOC / KNOWLEDGE, not in a business fact table.
- Search and vector indexes are rebuildable derivatives and never authority.
- The named long-term artifacts remain proposals until separate Source Decisions and approved PRPs authorize them.

## 7. Mandatory PRP and Source Decision declarations

Any affected PRP must declare:

| Required item | Minimum answer |
|---|---|
| Business grain | What one row represents. |
| Queried/written layer | L0–L19 and why that layer is appropriate. |
| Authoritative source | Approved Source Decision and owner conclusion. |
| Lineage | Source fields, transformations, destinations and evidence paths. |
| Writer and reader | Exactly which job/service writes and which service reads. |
| Freshness | Update chain, expected delay and stale-data behavior. |
| Permissions | Page/action/data/field scope and sensitive fields. |
| Data quality | Null, duplicate, validity, reconciliation and alert thresholds. |
| Retention/audit | Required history, actor/reason and deletion/archival boundary. |
| Rollback/exit | How to disable, rebuild, revert or leave a temporary legacy source. |

## 8. Prohibited patterns

- Frontend-facing business APIs must not query `raw_*` directly.
- RAW must not be declared business authority merely because it preserves source payloads.
- FACT fields must not be placed in DIM / MASTER tables.
- Manual overrides must not be written directly into external-sync tables.
- AI output must not automatically write or overwrite master/fact data.
- A MART / READ MODEL must not be the only truth source.
- Legacy databases must not receive new-system writes, migrations or temporary tables.
- New tables, migrations, ORM models or synchronization jobs must not be created without an approved PRP.
- A business API must not be implemented without field lineage and a completed Source Decision.
- Cost, profit, procurement, settlement and similarly sensitive fields must not be exposed without field permissions and an approved scope.
- Search indexes, vector indexes, caches and snapshots must not be treated as authority.
- Sandbox or experiment data must not feed a production API.

## 9. Review checklist

- [ ] The task identifies each relevant L0–L19 layer without creating speculative layers.
- [ ] The authoritative source is supported by a completed Source Decision.
- [ ] RAW, MART, SEARCH, CACHE and SANDBOX are not treated as authority.
- [ ] Master, fact and manual override responsibilities are separated.
- [ ] Relevant G1–G10 controls are referenced.
- [ ] Fields follow `field-standardization-standard.md`.
- [ ] Permissions, data quality, lineage, retention and rollback are explicit.
- [ ] Any real implementation has a separate approved PRP and owner execution authorization.

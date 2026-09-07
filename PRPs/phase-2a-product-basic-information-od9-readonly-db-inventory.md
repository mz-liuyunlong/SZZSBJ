# Phase 2A Product Basic Information OD-9 Readonly DB Inventory PRP

```text
Status: Approved
Owner Approval Required: Yes
Execution Allowed Before Merge: No
Database Access Used In This PRP Task: No
Server Access Used In This PRP Task: No
External API Used In This PRP Task: No
```

## 1. Authorization boundary

This PRP defines the scope and safety boundary for a later OD-9 read-only inventory of three legacy database tables. It is not the inventory report and does not authorize database access or SQL execution on this branch.

- This PRP does not authorize creating or changing tables.
- This PRP does not authorize a migration, ORM model, backend API or frontend implementation.
- This PRP does not authorize a mart/read model, synchronization task, external API call or data migration.
- This PRP does not authorize reading or exporting business-detail samples.
- The owner must change `Status` from `Draft` to `Approved` before merge; merging a file that still says `Draft` is not execution authorization.
- Only after Architect review passes, the owner changes the status to `Approved`, and the approved PRP is merged may the Backend Engineer execute the inventory within the exact approved boundary.
- Merge authorizes only the bounded read-only inventory described here. It does not authorize any subsequent API, schema, migration, synchronization or data-write work.

## 2. Background

The Product Basic Information Source Decision remains `BLOCKED_BY_OWNER_DECISION` and is not `READY_FOR_PRP` because OD-9 has not been completed.

OD-9 must determine whether these legacy tables can support the first-phase Product Management basic-information query:

- `dim_product`
- `dim_store`
- `dim_store_config`

The inventory is evidence gathering only. This PRP plans that inventory and its safety controls; it does not perform it.

Related decisions and rules:

- `docs/data-sources/decisions/products-basic-information-query-decision.md`
- `PRPs/phase-2a-product-basic-information-source-discovery.md`
- `docs/delivery/backend-data-source-decision-gate.md`
- `docs/data-sources/database-layering-standard.md`
- `docs/data-sources/field-standardization-standard.md`
- `docs/DATA_SOURCE_AND_LINEAGE_RULES.md`
- `docs/OLD_SYSTEM_READONLY_RULES.md`

## 3. Objective

After merge, collect the minimum read-only metadata and aggregate evidence needed to:

1. verify whether the three allowed tables exist and contain relevant structural fields;
2. assess identity-field completeness and ambiguity without exposing values;
3. assess `store_id` coverage and `store_name` reliability without exporting store names;
4. identify candidate freshness/update fields without declaring them authoritative;
5. support owner decisions OD-1 and OD-3;
6. produce one sanitized inventory report for architecture review.

The inventory must not decide or design an API method/path/schema, database model, canonical field dictionary, migration or read model.

## 4. Approved Owner Decisions

The following owner decisions are fixed inputs to OD-9 and must not be reopened or expanded by the inventory:

| Decision | Approved boundary                                                                                                                                      |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| OD-2     | First-phase product name prefers `item_name`; do not default-fallback to `product_name`.                                                               |
| OD-4     | SKU, MSKU and ItemID may be displayed. SKU is not a globally unique identity, may be null, and must not be inferred or used to discard a product.      |
| OD-5     | `brand` and `category` are excluded from phase one.                                                                                                    |
| OD-6     | Status is excluded from phase one. Any later Walmart publish-status work requires separate evaluation.                                                 |
| OD-7     | `product_type` and CS-prefix derivation are deferred to an operations or lifecycle module.                                                             |
| OD-8     | Store aliases, SKU mapping and manual-correction write capabilities are deferred to separate PRPs.                                                     |
| OD-10    | Long-term external-source verification order is Walmart Listing first, then Lingxing local product if needed. No external API call is authorized here. |

## 5. Pending decisions supported by OD-9

OD-9 supplies evidence for, but does not approve, these decisions:

| Decision | Evidence needed                                                                                                                       | Decision owner |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------- | -------------- |
| OD-1     | Whether the three-table legacy source is structurally usable, bounded and safe enough for a temporary read-only phase-one dependency. | Project Owner  |
| OD-3     | Whether `store_name` can be shown in phase one and which table, if any, is its unique authoritative source.                           | Project Owner  |

OD-9 evidence cannot change the Source Decision automatically. After the report is reviewed, the Source Decision must be updated and the owner must explicitly decide whether its state can become `READY_FOR_PRP`.

## 6. Allowed tables

The execution phase may inspect only:

```text
dim_product
dim_store
dim_store_config
```

No view, table, temporary table, backup table, RAW table, log table or system outside the minimum metadata catalogs needed to describe these three tables may be inspected. Metadata catalogs may be used only to retrieve existence, column, key and index metadata for the three names above.

## 7. Allowed inventory scope

### 7.1 Table metadata

For each allowed table, the execution phase may collect:

- whether the table exists;
- relevant column names and structure;
- data types;
- nullability;
- default values;
- column comments, when present;
- primary-key metadata;
- index names, uniqueness, column order and indexed columns.

Schema discovery does not authorize reading values from out-of-scope columns. The report must focus on keys, identity/name fields and candidate update fields needed by OD-1 and OD-3. If metadata reveals cost, price, profit, inventory, advertising, settlement, refund, owner or lifecycle columns, do not query their values or expand the report into those domains.

### 7.2 Aggregate statistics only

Only the non-identifying aggregate statistics explicitly listed in this PRP may be collected:

- table row count, with the report marking whether it is exact or estimated;
- null counts and null rates for `item_id`, `sku` and `msku` where those fields exist;
- duplicate-value counts for `item_id`, `sku` and `msku`, with the grouping grain stated and no offending values listed;
- aggregate count of ItemIDs associated with multiple SKUs;
- aggregate count of SKUs associated with multiple ItemIDs;
- `store_id` populated-row count and coverage rate;
- `store_name` missing count and rate;
- aggregate store-name conflict counts across the allowed tables, without listing names or IDs;
- candidate update/freshness fields based only on whether the field exists, whether its name clearly indicates an update-time candidate, its type, nullability, default value and column comment, when present;
- a summarized data-quality risk assessment.

An aggregate join is allowed only among the three approved tables, only for OD-3, and only after confirming that its join keys are indexed or otherwise safe at the observed scale. If safety cannot be established without running the query, stop.

Duplicate counts are evidence, not automatic defects. The report must state the evaluated grain and must not infer a global identity rule from column names or aggregate counts.

### 7.3 Performance controls

- Inspect table/index metadata before proposing aggregate queries.
- Prefer metadata estimates for row counts when an exact count may cause material load; label estimates clearly.
- Run only one reviewed read-only aggregate at a time.
- Do not use unbounded result sets, full-row retrieval, temporary tables or write-capable sessions.
- Do not run a query when its expected scan, join or lock behavior cannot be assessed as safe.
- Stop rather than adding hints, changing indexes, creating helper objects or escalating privileges.

This PRP intentionally does not contain executable SQL. The execution report must record the purpose and result type of each approved check without recording credentials or sensitive values.

## 8. Forbidden scope and operations

The execution phase must not:

- use `SELECT *`;
- export or display real business-detail samples;
- export or display real SKU, MSKU, ItemID, `store_id` or `store_name` values;
- query cost, price, profit, inventory, advertising, settlement, refund, owner or lifecycle values;
- inspect tables beyond `dim_product`, `dim_store` and `dim_store_config`;
- connect through root SSH or use MySQL root;
- request or output credentials, connection strings, secrets, tokens or passwords;
- use credentials supplied through chat, committed files, command history or logs;
- write, update, delete, backfill, repair or synchronize data;
- create or alter a database, schema, table, index, view or temporary table;
- run migration tooling or create a migration;
- create an ORM model;
- implement a backend API or frontend feature;
- create a mart/read model;
- migrate data;
- call Walmart, Lingxing, Feishu or any other external API;
- execute old-system scripts, install old-system dependencies or modify `old-system/**`;
- deploy or restart a service.

## 9. Required output

The later execution phase must create exactly one report:

```text
docs/data-sources/db-inventory/product-basic-information-od9-db-inventory.md
```

The report must contain:

1. execution boundary confirmation;
2. inventory date, execution role and read-only access statement;
3. actual inventoried tables, with no extra table;
4. table-existence results;
5. relevant column/type/nullability/default/comment summaries;
6. primary-key and index summaries;
7. allowed aggregate statistics, including exact-versus-estimated method labels;
8. ItemID/SKU/MSKU completeness, duplicate and cross-mapping risks;
9. `store_id` coverage and `store_name` missing/conflict risks;
10. candidate update-field and freshness risks;
11. evidence that may support OD-1, clearly separated from the final owner decision;
12. evidence that may support OD-3, clearly separated from the final owner decision;
13. recommendation on whether the Source Decision should be updated;
14. remaining owner decisions or evidence gaps;
15. confirmation that no real business sample or identifying value was exported;
16. confirmation that no write, DDL, temporary table, migration, code or external API action occurred.

The report must contain aggregate results only. It must not include credentials, server addresses, connection commands, raw SQL containing sensitive values, or identifying business records.

## 10. Stop conditions

Stop immediately and report without attempting a workaround if:

- answering a question requires a table outside the three-table allowlist;
- a real business-detail sample or identifying value appears necessary;
- any write, repair, schema change, temporary table or migration appears necessary;
- root SSH, MySQL root or broader privileges appear necessary;
- the approved read-only account lacks the required minimum permission;
- actual structure materially differs from the expected table/field scope;
- an aggregate query may materially affect production performance;
- query cost or lock/scan behavior cannot be assessed safely;
- a sensitive or excluded field must be queried;
- the work would expand into inventory, sales, profit, advertising, settlement, refund, owner or lifecycle modules;
- a secret, token, password or unapproved connection detail is encountered;
- any legacy structure would need to change;
- a long-running query would be required and its risk cannot be bounded;
- the report would need to reveal a real SKU, MSKU, ItemID, store name or other business-detail value.

A stop condition does not authorize broader access. The engineer must retain only non-sensitive observations already obtained and request owner direction.

## 11. Execution roles and skill boundary

```text
Main Execution Role: Backend Engineer
```

After merge, the Backend Engineer may use these Agent Skills only within this PRP:

- `engineering-minimal-change-engineer` for strict scope control;
- `engineering-technical-writer` for the sanitized report;
- `testing-evidence-collector` for non-identifying evidence records;
- `engineering-backend-architect` for source/read-path interpretation;
- `engineering-database-optimizer` only for static schema/index interpretation and read-query risk assessment; it grants no extra database or SQL permission.

Agent Skills are work modes, not people or permission principals. They cannot expand the allowlist, escalate privileges, authorize Git writes, deployment, database writes or external API calls, or replace owner approval.

The Architect:

- authors and reviews this PRP;
- does not execute the database inventory;
- reviews the inventory report and recommends Source Decision updates.

The Project Owner:

- approves and merges this PRP;
- supplies any database password locally during execution, without placing it in chat, files or the repository;
- controls the read-only account and connection scope;
- decides OD-1, OD-3 and whether the Source Decision may advance.

## 12. Review requirements

Before merge, an Architect read-only review must confirm:

- only the three named tables are allowed;
- only metadata and aggregate statistics are allowed;
- business-detail samples and identifying values are forbidden;
- writes, table changes, temporary tables, migrations and ORM models are forbidden;
- root SSH and MySQL root are forbidden;
- the report path is exact and unique;
- stop conditions and performance controls are explicit;
- no backend API, frontend implementation, mart/read model or data migration is authorized;
- the PRP follows `database-layering-standard.md`;
- the PRP follows `field-standardization-standard.md`;
- the PRP follows `backend-data-source-decision-gate.md`;
- the PRP follows `DATA_SOURCE_AND_LINEAGE_RULES.md` and `OLD_SYSTEM_READONLY_RULES.md`;
- the Source Decision remains blocked until report review and owner decisions are complete.

## 13. Validation plan for this PRP task

This branch performs documentation validation only:

```bash
git status --short --untracked-files=all
git diff --check
bash scripts/check-rule-pack.sh
sed -n '1,260p' PRPs/phase-2a-product-basic-information-od9-readonly-db-inventory.md
```

If the PRP exceeds 260 lines, continue with:

```bash
sed -n '261,520p' PRPs/phase-2a-product-basic-information-od9-readonly-db-inventory.md
```

No frontend/backend tests, service, database client, SQL, migration or dependency-install command belongs to this PRP-authoring task.

## 14. Rollback boundary

Before merge, rollback is limited to the owner discarding this single untracked PRP file. After merge, rollback of the documentation change is a normal docs-only revert by the owner.

No database rollback exists because this PRP-authoring task performs no database operation. A later inventory is read-only and must not create database state requiring rollback.

## 15. Owner approval checklist

- [ ] Confirm the PRP remains `Draft` before review and is not execution authorization on this branch.
- [ ] After Review PASS, change `Status` to `Approved` before merge; do not execute from a merged `Draft`.
- [ ] Confirm the allowlist contains only `dim_product`, `dim_store` and `dim_store_config`.
- [ ] Confirm metadata and aggregate-only evidence is sufficient for OD-1 and OD-3.
- [ ] Confirm no business-detail sample or identifying value may be exported.
- [ ] Confirm cost, price, profit, inventory, advertising, settlement, refund, owner and lifecycle data remain excluded.
- [ ] Confirm root SSH, MySQL root, writes, DDL, temporary tables and migrations remain forbidden.
- [ ] Confirm the owner will supply any required password only locally during execution.
- [ ] Confirm the report path is `docs/data-sources/db-inventory/product-basic-information-od9-db-inventory.md`.
- [ ] Confirm PRP merge authorizes only the bounded read-only inventory and no implementation.
- [ ] Confirm the inventory report must receive Architect review before the Source Decision is changed.
- [ ] Confirm OD-1 and OD-3 remain owner decisions after evidence collection.

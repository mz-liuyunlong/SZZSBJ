# Field Standardization Standard

```text
Status: Active after merge to main
Owner Approval Required: Yes through PR review and merge
Applies To: All source ingestion, ODS, canonical fields, API contracts, mart/read models, AI feature generation, and document-derived structured data
```

## 1. Purpose and authority boundary

All new-system data must follow a documented, reversible field-standardization path. Standardization makes representation consistent; it does not approve a source, business meaning, metric or interface field.

- Source authority remains governed by the interface Source Decision in `docs/delivery/backend-data-source-decision-gate.md`.
- Every standardized value must preserve its source field, source system and transformation lineage.
- A field name alone is not evidence of business meaning.
- A cleaned field is not automatically an approved metric, enum, identity or business definition.
- Every new API response field must be defined in an approved field dictionary or versioned data contract before implementation.
- This standard applies to business data, AI-derived data, document parsing, manual imports and external integrations.
- Standardization work does not authorize a database connection, source call, table, migration, cleaning job, API or write to business data; those require separate approval and PRP as applicable.

## 2. Required twelve-step standardization flow

Steps may be implemented in one approved pipeline, but none may be silently skipped. If a step is not applicable, the mapping must record `not_applicable` and the reason.

| Step | Purpose | Input Example | Output Example | Required Record | Forbidden Shortcut |
|---|---|---|---|---|---|
| 1. Source Field Capture | Preserve exact source evidence before interpretation. | Source key `Item ID`, raw value `00123`. | Raw `item_id_source = "00123"`. | Source system, object, field, payload/batch ID, received time and evidence path. | Keeping only the cleaned value or dropping the original key/value. |
| 2. Field Name Normalize | Map source names to one candidate canonical name. | `Item ID`, `itemId`, `item_id`. | Candidate `item_id`. | Mapping version, source field and canonical field status. | Inferring that similarly named fields have identical meaning. |
| 3. Data Type Normalize | Convert to the approved type without loss. | External ID `00123`, numeric text `12.50`. | ID string `00123`, approved numeric `12.5000`. | Source type, target type, parser and rejected-value behavior. | Casting external IDs to numbers or silently truncating precision. |
| 4. Null Normalize | Convert approved source placeholders to null. | `""`, `N/A`, `暂无`. | `null` when the source-specific rule allows it. | Placeholder list by source/field and raw value retention. | Applying one global placeholder list where `-` or `N/A` may be valid data. |
| 5. Trim / Text Clean | Remove transport noise while preserving meaning. | Leading spaces or invisible control characters. | Trimmed text with approved Unicode handling. | Cleaning rule, before/after trace or reproducible rule version. | Silent translation, case changes or rewriting business text. |
| 6. Enum Normalize | Map raw values to a governed reference value. | `WM`, `Walmart`, `沃尔玛`. | `walmart_us` when approved by reference data. | Raw value, mapping version, standard value and unmapped behavior. | Treating the raw value as the standard enum or inventing a mapping in code. |
| 7. Unit Normalize | Preserve source units and convert to a standard unit. | `10 lb`. | Raw `10/lb`; standard `4.5359237/kg`. | Raw value/unit, standard value/unit, formula and precision. | Storing a measurement without a unit or overwriting the raw measurement. |
| 8. Currency Normalize | Pair every monetary value with currency and governed conversion metadata. | `12.34 USD`. | `amount=12.3400`, `currency_code=USD`. | Source currency, target currency, rate/date/source when converted. | Naked amounts, assumed currency or unrecorded exchange rates. |
| 9. Timezone Normalize | Preserve source time context and store a canonical instant/date. | Walmart business timestamp in Los Angeles time. | UTC timestamp plus source timezone and business-date rule. | Raw timestamp, source timezone, UTC value, business timezone and ambiguity handling. | Parsing local time as UTC or omitting timezone meaning. |
| 10. Identity Mapping | Link source identities to internal identities without conflation. | `item_id`, `sku`, `msku`, `store_id`. | Audited mapping to internal `listing_id` or `product_id`. | Match rule, evidence, confidence, mapping status and history. | Deriving SKU/MSKU/ItemID from each other or destructive auto-merge. |
| 11. Data Quality Check | Measure whether standardized data is usable. | Null SKU, duplicate listing identity, unknown enum. | DQ result with severity and disposition. | Rule ID, threshold, result, affected count, run time and owner. | Dropping failures silently or declaring quality from one sample. |
| 12. Lineage Record | Make the entire transformation reproducible. | Source payload through cleaned/master/mart fields. | Source-to-target lineage edge. | Source, target, transformation version, writer, run/batch, time and evidence path. | Publishing a field with no traceable source or transformation. |

## 3. Canonical field dictionary

Every canonical or externally served field must have one dictionary entry with these properties:

| Dictionary property | Requirement |
|---|---|
| `canonical_field` | Unique lower snake-case field name within the governed scope. |
| `business_meaning` | Plain-language meaning, grain and exclusions. |
| `data_type` | Exact logical type and precision/length where relevant. |
| `nullable` | Whether null is valid and what it means. |
| `source_system` | Approved source system or `pending_source_decision`. |
| `source_fields` | Exact source objects and fields; multiple fields require explicit precedence. |
| `cleaning_rule` | Reproducible transformation or `none`. |
| `enum_mapping` | Reference-data mapping and unmapped behavior. |
| `timezone_rule` | Source, storage, display and business timezone behavior. |
| `currency_rule` | Currency field, precision and conversion policy. |
| `identity_mapping_rule` | Mapping grain, keys, match status and collision behavior. |
| `owner` | Accountable business/data owner. |
| `status` | One allowed dictionary status. |
| `first_supported_module` | First approved module/contract using the field. |
| `evidence_path` | Source Decision, contract, source documentation or code evidence. |
| `notes` | Risks, exclusions, deprecation or unresolved decisions. |

Allowed statuses are:

| Status | Meaning |
|---|---|
| `Draft` | Proposed definition; must not be treated as a production contract. |
| `Approved` | Owner-approved meaning and source for the stated scope. |
| `Deprecated` | Kept only for compatibility or historical interpretation; replacement is recorded. |
| `Blocked` | Cannot proceed because a required prerequisite is unresolved. |
| `Needs Owner Decision` | Temporary blocking state requiring a named owner decision. |

Only `Approved` entries may enter a new production API response. Approval remains scoped to the recorded module, grain and contract; it does not authorize implementation by itself.

## 4. Product Management candidate example

This example defines separation and cleaning expectations only. It does not resolve the currently blocked Product Basic Information Source Decision or authorize a schema/API.

| Candidate field | Intended distinction | Required standardization rule | Approval note |
|---|---|---|---|
| `product_id` | New-system internal product identity. | Generate only in an approved new-system ownership model; store separately from every external ID. | Must not be derived from SKU, MSKU or ItemID. |
| `listing_id` | New-system internal platform-listing identity. | Map through an approved identity rule at listing grain. | Must remain distinct from `product_id` and external `item_id`. |
| `item_id` | Platform item/listing identifier. | Preserve as string, including leading zeros and source system. | It is not the internal `product_id`. |
| `sku` | Source/local SKU label. | Nullable string; trim only by approved rule and preserve case. | It may be empty and is not a global unique identity. |
| `msku` | Marketplace seller SKU / operational identifier. | Preserve source value and case; map explicitly if used for identity. | It may aid operations but does not automatically equal `product_id`. |
| `item_name` | Source/platform item name candidate. | Preserve raw text; clean transport noise only. | Priority versus `product_name` requires the applicable Source Decision/owner decision. |
| `product_name` | ERP or source product name candidate. | Preserve raw text; do not silently translate or merge with `item_name`. | Fallback semantics require owner approval. |
| `store_id` | Source store/account identifier. | Preserve as string and include source platform/system. | Cross-system mapping requires L6 identity evidence. |
| `store_name` | Store display name. | Normalize text only after selecting an authoritative source. | Authority requires the Source Decision or OD-9 outcome; legacy multi-table fallback is not automatically a contract. |
| `platform` | Canonical marketplace/platform code. | Map raw labels through approved Reference Data. | Use one code such as `walmart_us`, not mixed labels. |
| `source_system` | System that supplied the value. | Required controlled code on ingested/derived records. | Must not be inferred solely from a table name. |
| `raw_status` | Exact status emitted by the source. | Preserve source value and source enum version. | Must not be overwritten by `standard_status`. |
| `standard_status` | Governed status used by the new system. | Map through versioned Reference Data; retain unmapped state. | A normalized result is not the source value. |
| `source_created_at` | Creation timestamp reported by the source. | Preserve raw timestamp/timezone and normalize to UTC when unambiguous. | Do not substitute new-system row creation time. |
| `source_updated_at` | Update timestamp reported by the source. | Preserve source timezone and normalized UTC value. | Does not equal ingestion/sync time. |
| `synced_at` | Time the new system completed ingestion/synchronization. | Store UTC and associate with run/batch ID. | Indicates pipeline freshness, not source business update time. |
| `created_at` | Time the new-system record was created. | Store UTC and manage through the owning service/database. | Must remain separate from source timestamps. |
| `updated_at` | Time the new-system record was last updated. | Store UTC with writer/audit context where required. | Must not be presented as source freshness without qualification. |

For all of these fields, `source_system`, exact `source_field`/`source_fields` and `evidence_path` must remain traceable. Field names are candidates until their dictionary status is `Approved`.

## 5. Special field rules

### 5.1 Nulls

- Preserve the raw value before null normalization.
- Empty string, whitespace-only text, case-insensitive `N/A`, literal `null`, `-` and `暂无` may map to null only when the source-and-field mapping confirms they are placeholders.
- Do not use a global replacement when a token can be a legitimate business value.
- API contracts must distinguish nullable, missing and empty collection semantics.

### 5.2 Time

- Database timestamps are stored in UTC.
- Source timezone and raw timestamp must be retained or traceable; unknown timezone remains blocked/unknown, not guessed.
- Default frontend display timezone is `Asia/Taipei`.
- Walmart business dates use `America/Los_Angeles` where the business definition requires it.
- Reports must declare their statistics/business timezone independently of display timezone.
- `source_created_at`, `source_updated_at`, `synced_at`, `created_at` and `updated_at` have different meanings and must not be substituted for one another.

### 5.3 Currency

- Monetary values use the project precision policy and must be paired with `currency_code`; a naked amount is invalid.
- Currency must not be inferred from platform, store or user locale.
- A conversion must record the exchange-rate value/date/source concepts (`exchange_rate`, `exchange_rate_date`, `exchange_rate_source`). Project canonical persistence names are `fx_rate`, `fx_date`, `fx_source`; differently named source fields must map to them with lineage.
- Historical values must retain the conversion basis used at the relevant business date.

### 5.4 Status enums

- Keep `raw_status` and `standard_status` separate.
- `raw_status` preserves the source value; `standard_status` references versioned L5 Reference Data.
- Unknown raw values remain unmapped and trigger a DQ result; they must not be silently coerced to a convenient default.

### 5.5 Platform enums

- Use governed codes such as `walmart_us`, `amazon_us` and `temu_us` after approval.
- Raw forms such as Walmart, `walmart`, 沃尔玛 and `WM` must not coexist as canonical values.
- Preserve the original raw platform label and mapping version.

### 5.6 Units

- Dimensions, weight and volume must retain raw value/unit and standard value/unit.
- Conversion formulas, precision and rounding rules must be recorded.
- A numeric field without an explicit unit must not enter a contract when the business unit is material.

### 5.7 Text cleaning

- Trim approved leading/trailing whitespace and remove documented invisible transport characters.
- Preserve case unless the field dictionary explicitly permits normalization; SKU/MSKU case must not be changed by default.
- Do not silently translate, rewrite, summarize or correct business meaning.
- Retain original text for audit when a transformation changes representation.

### 5.8 Identity fields

- External IDs are strings to prevent loss of leading zeros and precision.
- SKU, MSKU and ItemID must not be inferred from or substituted for one another.
- Internal `product_id` and `listing_id` remain distinct from all external IDs.
- Identity matches require evidence, collision behavior, confidence/status and history.

### 5.9 Sensitive fields

- Cost, procurement price, profit, settlement and advertising-spend fields require explicit permission and data-scope design.
- Sensitive fields must not be added to an API response by a PRP that lacks field permission, masking and audit requirements.
- Standardization, marts, AI output or document extraction must not be used to bypass those controls.

## 6. Contract and implementation requirements

Before a new field, mapping, cleaning task or API response is implemented, the approved PRP must reference:

1. the applicable Source Decision and its overall status;
2. the canonical field dictionary entries and statuses;
3. source fields and evidence paths;
4. the twelve-step mapping, including explicit not-applicable steps;
5. type, null, enum, unit, currency and timezone rules;
6. identity grain and collision behavior;
7. DQ thresholds and failure handling;
8. permissions and sensitive-field handling;
9. lineage writer, batch/run identity and freshness;
10. rollback, replay and deprecation behavior.

## 7. Prohibited patterns

- Do not use multiple canonical names for the same business field in the same governed scope.
- Do not return an undefined field in an API response.
- Do not store or return a monetary amount without currency.
- Do not use a time field without documented source, storage, display and business timezone behavior.
- Do not mix empty string, `N/A`, `-`, literal `null` and null without an explicit normalization rule.
- Do not treat `raw_status` as `standard_status`.
- Do not derive SKU, MSKU or ItemID from one another.
- Do not drop `source_system`, `source_field`/`source_fields` or `evidence_path` during cleaning.
- Do not promote a candidate field to a production field without a completed Source Decision.
- A cleaning task must not directly modify business master data unless an approved PRP defines the governed write path.
- AI must not invent a field and write it into a business table.
- Document-parsed fields must pass through the field dictionary and Source Decision before entering business layers.

## 8. Review checklist

- [ ] Every field has one name, business meaning, grain, type and null rule.
- [ ] Raw values and source metadata remain traceable.
- [ ] Identity, enum, unit, currency and time rules are explicit where applicable.
- [ ] DQ checks identify unknown, invalid, duplicate and stale values without silently dropping them.
- [ ] API fields are present in an approved dictionary/contract and have an approved Source Decision.
- [ ] Sensitive fields have field-level permission, masking and audit design.
- [ ] AI/document-derived fields remain proposals until approved.
- [ ] Any real table, pipeline, API or write path has separate PRP and owner authorization.

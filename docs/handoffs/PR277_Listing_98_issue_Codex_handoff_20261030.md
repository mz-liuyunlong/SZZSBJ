# SZZSBJ Listing Management PR #277 - Complete Codex Handoff (98 Issues)

## Ground truth, ownership, and execution boundary

- Repository: https://github.com/mz-liuyunlong/SZZSBJ
- Existing DRAFT PR: https://github.com/mz-liuyunlong/SZZSBJ/pull/277. DO NOT open a replacement PR.
- Existing branch: `codex/listing-management-full-repair-20261030`. Stay on this exact head branch for all commits.
- Audit HEAD (2026-10-30): `8276b81b6bc7b3ea2558d1eeca4a7d3c44a3618b`. Confirm remote head before making changes; fast-forward if advanced.
- PR baseline: 63 commits and 28 changed files at audit HEAD. Original issue list: LM-001 through LM-098.
- Original accepted workbook: `SZZSBJ_Listing管理_98项统一修复确认版_20261030.xlsx` (see attached named XLSX). All 98 items are requested remediation scope; NOT all are proven production defects.
- PRODUCTION BOUNDARY: Do not deploy, alter production DB, execute production migrations, backfill historical data, enable scheduler, publish grades, or merge main without explicit authorization. Implement schema/migrations/code/test ONLY in branch and isolated fixtures.
- Progress convention: report at least 30 DISTINCT original LM IDs for an implementation batch, not 30 commits/line edits. Final remainder may be smaller. Keep completed/partial/unverified separate.
- CI convention from owner: implement all function fixes before final CI. Use `[skip ci]` during intermediate commits IF the workflow honors it; still run local targeted static checks when practical. At final functional completion run full CI once and fix all failures.
- Previous assistant report of 29/98 "code-fixed" is historical, not verified closed tickets. The conservative static code-change classification below does NOT prove acceptance or production behavior.

## Current static audit breakdown (NOT acceptance-closed)

- `PATCHED_UNVERIFIED`: 25 issues have targeted code changes that appear to cover core behavior; still require acceptance checks.
- `PARTIAL`: 52 issues have only partial implementation, unresolved risk, or business-semantics gaps.
- `OPEN`: 21 issues have no implementation of the core original acceptance criterion evident in PR #277.
- `ACCEPTED`: 0 of 98. The PR HEAD has not undergone final full CI, E2E, isolated DB migration or production read-only acceptance.

These classifications are code review triage, not precise ticket close numbers. Never convert them to "done" without tests.

## Blocking defects and regression risks that MUST be reviewed first

1. **P0 [LM-002/006/007/020/021/022/024/025] Only unpublished diagnostic candidates; no trusted ad/fee publish proof.** File: `backend/app/modules/listing_rule_config/{batch,preview,evaluation}.py`. Acceptance: No production write until explicit gate; publish+rollback+audit tests in isolated DB.
2. **P0 [LM-062/063] Same-day partial run is terminal; retries delete historical evidence.** File: `backend/app/modules/listing_rule_config/batch.py`. Acceptance: Immutable per-attempt snapshots, replay idempotency, no destructive retry.
3. **P0 [LM-082/083/092] Tag definitions are global; list/update leaks across tenant; no DB unique name constraint.** File: `backend/app/modules/data_pages/{models,repository,router}.py`. Acceptance: Tenant scoped ownership/schema/migration/API tests.
4. **P0 [LM-028/027] Unknown archive states included as active in default summary.** File: `backend/app/modules/data_pages/repository.py`. Acceptance: Unknown must be separate unless business rule approved; counts reconciled.
5. **P0 [LM-084] CSV list branch bypasses formula-prefix sanitization.** File: `backend/app/modules/data_pages/service.py`. Acceptance: Escape after flatten; fuzz tests for =,+,-,@,TAB,CR,LF.
6. **P1 [LM-040] Client page sorting mixed with backend raw MART sorting.** File: `frontend/src/pages/products/components/ListingManagementTable.tsx`. Acceptance: Use remote sorter only, mapped to same effective display projection.
7. **P1 [LM-050/041] Static pageStateKey and seen row cache survive account changes.** File: `frontend/src/pages/products/ListingManagementPage.tsx`. Acceptance: Account scoped selection, cache clearing, cross-account E2E.
8. **P1 [LM-036/086] Missing currency is silently rendered as USD.** File: `frontend/src/pages/products/{listingManagementApi.ts,components/ListingManagementTable.tsx}`. Acceptance: Do not guess currency; atomic price+currency provenance.
9. **P1 [LM-047/043/042] Batch list POST but export still GET; limit 10000 returns 422.** File: `frontend/src/pages/products/listingManagementApi.ts`. Acceptance: Selected/batch/all export supports safe POST/streaming/jobs and RBAC.
10. **P1 [LM-077/078/079] Trusted listing start is still null for new records; WFS/launch semantics not audited.** File: `backend/app/modules/integration_sync/data_pages_real_sync.py`. Acceptance: Verified distinct field sources, LA/CN/UTC contract and backfill plan.
11. **P1 [LM-051/052/053/054] Legacy mock charts remain as fallback; no true keyword/event/replenish API.** File: `frontend/src/shared/listing-analysis/ListingAnalysisModal.tsx`. Acceptance: Disable all demo data in production; real scoped API or unavailable.
12. **P1 [LM-015/016/017/018] Historical archive/stage transitions not replayable from current state.** File: `backend/app/modules/listing_rule_config/preview.py`. Acceptance: Append-only history and as-of cutoff tests.
13. **P1 [LM-085] Owner pairing source row selected lexicographically not by authority/time.** File: `backend/app/modules/data_pages/repository.py`. Acceptance: Use trusted latest effective source row with deterministic tie break.
14. **P1 [LM-031/025] Some NULL ad amount preserved but daily complete zero publication absent.** File: `backend/app/modules/integration_sync/data_pages_real_sync.py`. Acceptance: Ad/fee completeness manifest and certified zero days.

## 12 engineering work packages and recommended execution sequence

- **1 / Core field contract [LM-026..040, LM-073..080, LM-085..086]:** Make a single explicit source/provenance/known/freshness mapping shared by API, cards, grid, detail, CSV. Never invent currency or zero data.
- **2 / Monitoring RAW audit [LM-037/038/055/056/071..074/080]:** Sanitized RAW-key inventory and approved projection matrix; handle success/failure timestamp, stale or failed values, images and restricted audit evidence.
- **3 / Dates [LM-035/076..079]:** Separate platform listing publish UTC, first sellable, first WFS quantity>0, original evidence, LA/CN date; verified source and migration plan.
- **4 / Summary and filtering [LM-026..028, LM-033/034/039/088/094]:** Reconcile online/offline/unknown/archive counts, split product enable vs platform publish, server-side raw state filters.
- **5 / Search, pagination, export [LM-040..047/084/097]:** Account-scoped search and stable sortable fields; POST 1000 ID and large export; escape CSV; zero silent truncations.
- **6 / Tags and archive [LM-028/041/048/049/081..083/087/089..093/095/096/098]:** Decide tenant/store/item tag identity, migration/unique constraints, permission tests, destructive action preview, immutable archive events.
- **7 / Lifecycle engine [LM-001/004/005/009..019]:** Initialize all Listings safely, FBM/WFS and unknown fulfillment, certified zero business days, event based transitions and as-of historical replay.
- **8 / Financial grade contract [LM-002/003/006/020..025/031]:** One scoring core, certified ads/fees/refunds by account/date, zero-proof, stage provenance. No unverifiable publish.
- **9 / Jobs and release [LM-007/059..066]:** Manual all-Listing run with progress, immutable attempt snapshots, bounded parallelism, retry, explicit publish/rollback permission gate.
- **10 / Genuine analysis [LM-051..054/057/058]:** Eliminate mock numbers, scope all joins to account/store/item/msku, bring real 7/14/30d sales/ad/profit/event/replenishment or show unavailable.
- **11 / Operator workflow [LM-067..069]:** C/D follow-up after authorized publication, overdue China-time reminders, audited actor and dynamic scheduler status.
- **12 / Tests/rollout [LM-008/050/070]:** Isolated Postgres and migrations, authorization matrix, import/export, Playwright, performance, production read-only version/data audit.

## All 98 original items: original issue, source evidence, implementation review, next acceptance

State legend: `PATCHED_UNVERIFIED` = targeted edits, NOT accepted; `PARTIAL` = not fully implemented; `OPEN` = core acceptance not implemented. The original workbook source notes are historical and are not evidence of current production after Oct 29.

### LM-001 | 生命周期 | P0 | PARTIAL
- Original issue (生产已验证): **全部Listing生命周期为空**
- Recorded condition: 生产查询3,331/3,331条lifecycle_status为空；系统缺少初始化流程
- Original acceptance: 对全部Listing执行状态判定；有可信依据则生成阶段，无依据显示待确认并保留原因
- PR #277 review / Codex TODO: A provisional candidate can now be inferred, but the Listing MART lifecycle_status is still not populated by a controlled publication/init pipeline. Implement provenance and initial-state publish gate.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/models.py

### LM-002 | 等级评级 | P0 | OPEN
- Original issue (生产已验证): **全部Listing正式等级为空**
- Recorded condition: 生产查询3,331/3,331条product_grade为空；财务模拟不能写回正式结果
- Original acceptance: 完成受控发布、审计和结果回填，不能直接写入未认证模拟值
- PR #277 review / Codex TODO: Formal product_grade remains unpublished. Diagnostic results are blocked and published=false; do not auto-write unapproved values.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/models.py

### LM-003 | 等级评级 | P0 | PARTIAL
- Original issue (生产已验证): **空生命周期导致全部不参与评级**
- Recorded condition: 只读试算3,331条均标记LIFECYCLE_EXCLUDED_FROM_GRADING
- Original acceptance: 解除首次阶段计算的循环依赖，评级按可信阶段与证据独立评估
- PR #277 review / Codex TODO: Preview can consume a candidate stage; formal grade still depends on trusted as-of stage and complete financial evidence. Test all-null baseline.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview.py

### LM-004 | 生命周期 | P0 | PARTIAL
- Original issue (源码已确认): **缺少可信的生命周期初始阶段规则**
- Recorded condition: 新Listing同步不赋值lifecycle_status，已有算法要求预先存在阶段
- Original acceptance: 设计首发、未上架、经营、清货和归档的初始化规则及可追溯来源
- PR #277 review / Codex TODO: New initial stage inference uses >=7 observed sales days. No verified launch/clearance/approval event contract; missing days cannot be assumed zero.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/integration_sync/data_pages_real_sync.py

### LM-005 | 生命周期 | P0 | PARTIAL
- Original issue (源码已确认): **生命周期完整趋势逻辑仅覆盖WFS**
- Recorded condition: 完整趋势计算要求fulfillment_type为1；非WFS跳过主流程
- Original acceptance: 所有履约方式统一进入生命周期判定；库存规则按履约方式区分
- PR #277 review / Codex TODO: WFS-only entry guard removed, FBM sales trend is provisional. Need verified FBM inventory/availability, lifecycle applicability tests.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview.py

### LM-006 | 等级评级 | P0 | OPEN
- Original issue (生产已验证): **广告和费用完整性没有正式发布证明**
- Recorded condition: 试算3,331条均有ADS_COST_PUBLICATION_PROOF_MISSING
- Original acceptance: 建立广告、成本、退款等完整性认证；不可把缺数据认成0
- PR #277 review / Codex TODO: ADS_COST_PUBLICATION_PROOF_MISSING remains a deliberate blocker. Build per-store/day/item completeness manifests and provenance; no zero imputation.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview.py

### LM-007 | 等级评级 | P0 | OPEN
- Original issue (源码已确认): **等级和生命周期缺少正式发布链路**
- Recorded condition: BatchService只写unpublished/blocked快照，不更新Listing正式字段
- Original acceptance: 通过授权门禁后按规则版本受控发布，支持审计、回滚和回放
- PR #277 review / Codex TODO: Batch writes only unpublished ListingEvaluationSnapshot; needs authorized transactional publish, immutable audit, compensating rollback, idempotency.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/batch.py

### LM-008 | 部署与版本 | P1 | OPEN
- Original issue (生产已验证): **生产进程运行的版本不是较新目录**
- Recorded condition: 进程CWD为423a9129；另有9bff308d发布目录存在（不等于已审核可切换）
- Original acceptance: 建立发布版本校验、迁移兼容性检查及部署清单
- PR #277 review / Codex TODO: Old 2026-10-29 production evidence does not establish current production SHA. Add read-only deployment/version/DB head checks and runbook; no deployment.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/tasks.py

### LM-009 | 生命周期 | P0 | PARTIAL
- Original issue (源码已确认): **完整生命周期判断限制WFS**
- Recorded condition: 代码同时检查fulfillment_type=1、未归档、已有有效阶段
- Original acceptance: 不以WFS作为生命周期管理入口，所有Listing均输出可解释的阶段或待确认
- PR #277 review / Codex TODO: Lifecycle preview now considers FBM, but cannot claim all Listings have authoritative lifecycle; pipeline only diagnostic.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview.py

### LM-010 | 生命周期 | P0 | PARTIAL
- Original issue (源码已确认): **已有阶段是再次计算阶段的前置条件**
- Recorded condition: lifecycle_status in known_stages形成初始化循环依赖
- Original acceptance: 增加首次阶段推断与初始化服务，避免空字段永久无法计算
- PR #277 review / Codex TODO: Initial stage can be guessed conditionally, but formal initialization and preservation of initial evidence are missing.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview.py

### LM-011 | 生命周期 | P0 | PARTIAL
- Original issue (源码已确认): **无库存快照的商品不能正常计算趋势**
- Recorded condition: 趋势证据依赖有效库存日，无库存事实与缺失库存快照未分开
- Original acceptance: 零库存、缺库存、未销售仍能判定经营状态；缺证据单独提示
- PR #277 review / Codex TODO: Sales trend decoupled from stock availability in one evaluator. Missing/zero business days and stock evidence still need independent completeness markers.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview.py

### LM-012 | 生命周期 | P0 | PARTIAL
- Original issue (需求缺口): **非WFS履约没有匹配的库存规则**
- Recorded condition: 库存算法围绕WFS可售数量，FBM等来源未形成适用策略
- Original acceptance: 不同履约模式使用对应可售/断货依据，不强制读取WFS库存
- PR #277 review / Codex TODO: FBM entry is provisional and does not yet use a proven FBM inventory fact. Do not use WFS zero to classify FBM stockout.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview.py

### LM-013 | 生命周期 | P1 | PARTIAL
- Original issue (源码已确认): **真实零销量日与漏数日未区分**
- Recorded condition: 缺失日期不生成零销售日的业务证明
- Original acceptance: 零销量作为合法事实，缺失或接口同步失败明确标记
- PR #277 review / Codex TODO: Explicit zero in BusinessDay differs from None, but missing daily MART rows are not independently certified as no-sales days.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview.py

### LM-014 | 生命周期 | P1 | PARTIAL
- Original issue (源码已确认): **销量趋势与WFS库存有效日强耦合**
- Recorded condition: 全部3,331条试算出现趋势有效有货天数不足；部分为流程阻断
- Original acceptance: 以经营记录判定趋势可计算性，库存用于缺货影响归因
- PR #277 review / Codex TODO: Trend now uses valid sales days instead of WFS-stock days, but source publishing and sufficient window completeness are not established.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview.py

### LM-015 | 生命周期 | P1 | OPEN
- Original issue (源码已确认): **断货恢复缺少历史阶段上下文**
- Recorded condition: 试算缺PREVIOUS_LIFECYCLE_STAGE_UNVERIFIED，恢复时难回到正确阶段
- Original acceptance: 保留断货前经营阶段及恢复条件，验证阶段恢复路径
- PR #277 review / Codex TODO: No immutable previous-stage snapshots for stockout recovery. Do not infer recovery baseline from current stage.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview.py

### LM-016 | 生命周期 | P1 | OPEN
- Original issue (源码已确认): **长期断货修复历史未闭环**
- Recorded condition: 缺少连续断货、恢复、库存修复累计历史的可信事件
- Original acceptance: 建立时序事件和恢复证据，重算不丢失轨迹
- PR #277 review / Codex TODO: No durable stockout/recovery event timeline and cumulative repair-valid days. Add event replay tests.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview.py

### LM-017 | 生命周期 | P1 | PARTIAL
- Original issue (源码风险待验收): **历史日试算混用当前归档状态**
- Recorded condition: 归档状态读取当前表，不能保证和LA截止日一致
- Original acceptance: 历史试算按as-of快照重建阶段及归档状态
- PR #277 review / Codex TODO: A post-cutoff archive safeguard exists, but restore-after-cutoff cannot reconstruct historical archived=true. Need as-of event log.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview.py

### LM-018 | 生命周期 | P1 | OPEN
- Original issue (需求缺口): **测品、清货、归档等流程历史不完整**
- Recorded condition: 历史审批事件和生命周期初始化证据未通过确认
- Original acceptance: 明确人工审批覆盖与自动规则优先级，保存不可变事件
- PR #277 review / Codex TODO: Prelaunch, testing, clearance, archive workflow history is not proven; encode human approval precedence and append-only events.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview.py

### LM-019 | 生命周期 | P1 | PARTIAL
- Original issue (业务口径待确认): **低库存被用于断货期判定**
- Recorded condition: 可配置为连续库存不高于阈值进入断货；低库存不等于零库存
- Original acceptance: 确认“低库存”和“断货期”的命名及阈值业务口径
- PR #277 evidence: `stockout_candidate` and `lifecycle_listing` require observed WFS zero stock; positive low stock does not trigger stockout. The rule drawer now labels the consecutive threshold as zero-stock days. Business sign-off for the wider lifecycle policy remains pending.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview.py

### LM-020 | 等级评级 | P0 | PARTIAL
- Original issue (源码已确认): **财务试算与正式评级证据门槛不一致**
- Recorded condition: basic_financial_candidate可算等级，但正式发布需要更严格财务证明
- Original acceptance: 同一评分算法核心、独立证据状态和正式发布门禁
- PR #277 review / Codex TODO: basic_financial_candidate and grade_listing are separate formulas/evidence interpretations. Unify pure evaluator and gate publication separately.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview.py

### LM-021 | 等级评级 | P0 | OPEN
- Original issue (生产已验证): **缺广告费用完整性认证**
- Recorded condition: 3,331条含ADS_COST_PUBLICATION_PROOF_MISSING，未正式认证
- Original acceptance: 广告报表完整覆盖、币种和归因校验通过后才评级
- PR #277 review / Codex TODO: Walmart ad data complete coverage, currency, attribution and no-data proof are not certified, so official rating must remain blocked.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview.py

### LM-022 | 等级评级 | P0 | OPEN
- Original issue (源码已确认): **正式等级缺少发布写回服务**
- Recorded condition: 生产正式字段均空；batch.py不修改正式Listing MART
- Original acceptance: 建立原子发布、幂等、权限、变更日志及回滚
- PR #277 review / Codex TODO: No formal atomic grade/lifecycle write-back. Need publish permissions, audit, replay, rollback and frozen rule version.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/batch.py

### LM-023 | 等级评级 | P1 | PARTIAL
- Original issue (源码已确认): **等级依赖没有初始化的生命周期**
- Recorded condition: 空阶段被排除；无法消费原本有效的财务数据
- Original acceptance: 阶段可信来源确定后再评估参与评级范围
- PR #277 review / Codex TODO: Candidate stage may unblock diagnostic grade, but source-of-truth stage and historical cutoffs remain provisional.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview.py

### LM-024 | 等级评级 | P1 | PARTIAL
- Original issue (源码风险待验收): **等级与生命周期可能使用不同步的阶段**
- Recorded condition: 评分使用当前lifecycle_status，阶段候选可能同时改变
- Original acceptance: 同一截止日、同一规则版本、经确认的阶段一致出结果
- PR #277 review / Codex TODO: Use identical business cutoff, lifecycle as-of evidence, rule version and cost/ad manifests for one published grade.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview.py

### LM-025 | 等级评级 | P1 | PARTIAL
- Original issue (源码已确认): **零销售日与成本完整性没有独立证据**
- Recorded condition: 缺少可信的零业务日发布标记；财务天数可能不足
- Original acceptance: 分离完整零销售天、成本缺失、费用未结算状态
- PR #277 review / Codex TODO: Daily zero-business-day publication proof is absent. Explicitly distinguish certified zero from missing ad, fee, refund and source data.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview.py

### LM-026 | 统计卡 | P0 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **“在售商品”按WFS库存而非在线状态统计**
- Recorded condition: online_condition为wfs_available_quantity>0；遗漏FBM、零库存但仍在线商品
- Original acceptance: 按平台在线状态定义在售；库存独立统计
- PR #277 review / Codex TODO: Summary and online filter changed from WFS>0 to listing_status online set. Validate platform enum, freshness, category counts and FBM.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/repository.py

### LM-027 | 统计卡 | P1 | PARTIAL
- Original issue (源码风险待验收): **归档商品混入常规运营统计**
- Recorded condition: 无归档筛选时统计基于全体Listing，是否应默认排除未明确
- Original acceptance: 明确总数、在售及异常统计是否含已归档，并逐卡落地
- PR #277 review / Codex TODO: Default archive_status=active added; SQL treats missing archive rows as active. Clarify card denominators and unknown-state policy.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/repository.py

### LM-028 | 归档恢复 | P1 | PARTIAL
- Original issue (生产已验证): **归档未知状态被视为正常**
- Recorded condition: 584条无归档状态；前端is_archived空转false
- Original acceptance: 未知与未归档分离，或明确可信的默认正常策略
- PR #277 review / Codex TODO: archive_state_known field exposes unknown in rows, but active filter includes NULL archive-state rows; 584 missing in old snapshot. Fix semantics.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/service.py

### LM-029 | 列表字段 | P1 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **前端“近90天销量”应统一改为“近30天销量”**
- Recorded condition: 当前前端字段 sales90Days 实际读取 sales_30d；页面表头与数据周期不匹配。用户明确要求展示近30天。
- Original acceptance: 前端表头、列配置、字段键名、筛选/排序/tooltip与测试统一为“近30天销量”；继续使用现有 sales_30d，不新增90天聚合；导出保持近30天口径。
- PR #277 review / Codex TODO: sales90Days renamed to sales30Days and mapped to existing sales_30d across table, API, tests; verify details/CSV and no old key in saved views.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/listingManagementApi.ts

### LM-030 | 列表字段 | P1 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **空金额、评分、库存默认显示0**
- Recorded condition: numberValue(value??0)把未知值变成0
- Original acceptance: null显示—/待同步；真实零单独显示0
- PR #277 evidence: list and detail now respect known flags for price, inventory, rating and reviews; detail preserves observed zero inventory rather than a missing-value marker. Sorting and browser acceptance remain pending; numberValue still stores 0 as internal fallback.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/listingManagementApi.ts

### LM-031 | 列表字段 | P1 | PARTIAL
- Original issue (源码已确认): **缺失广告数据被当成零金额**
- Recorded condition: 同步使用coalesce(ad_spend_30d,0)
- Original acceptance: 保留数据完整性状态，真实0与无记录区分
- PR #277 review / Codex TODO: One SQL sync path removed coalesce(ad_spend,0) for missing facts. Existing data backfill and daily MART source completeness still unresolved.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/integration_sync/data_pages_real_sync.py

### LM-032 | 列表字段 | P1 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **跟卖状态未知显示为“否”**
- Recorded condition: 前端is_hijacked ? 是 : 否；null被视作false
- Original acceptance: 增加“待确认”，导出与表格一致
- PR #277 evidence: frontend, detail, and CSV distinguish true/false/null as 是/否/待确认; targeted CSV and detail tests cover the unknown state. Monitoring fallback and browser acceptance remain pending.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/listingManagementApi.ts

### LM-033 | 列表字段 | P1 | PARTIAL
- Original issue (源码已确认): **产品启停状态与Listing在线状态混用**
- Recorded condition: productStatus由disabled_reason是否为空决定
- Original acceptance: 产品启停、平台发布、可售三个状态单独定义
- PR #277 review / Codex TODO: productStatus still derived only from disabled_reason, not independent product enablement state. Define 3 separate state sources.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/listingManagementApi.ts

### LM-034 | 筛选搜索 | P1 | PARTIAL
- Original issue (源码已确认): **产品类型筛选实际使用类目**
- Recorded condition: product_type_value取effective_category
- Original acceptance: 区分产品类型和Walmart类目，核实筛选含义
- PR #277 review / Codex TODO: UI label switched to platform category but separate product-type dimension/filter not implemented. Confirm requirements.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/components/ListingManagementToolbar.tsx

### LM-035 | 时间与日期 | P1 | PARTIAL
- Original issue (源码已确认): **已有上架日期来源未被前端使用**
- Recorded condition: 前端只看listing_start_at_utc，忽略source_raw/launch_date_cn
- Original acceptance: 明确平台上架、首次可售、首次WFS有货及优先级
- PR #277 review / Codex TODO: Raw start source and WFS evidence exposed; authoritative platform listing start and first sellable date still unverified.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/listingManagementApi.ts

### LM-036 | 列表字段 | P1 | PARTIAL
- Original issue (源码已确认): **价格统一显示美元符号**
- Recorded condition: 表格写死$，未使用返回币种
- Original acceptance: 以金额+原币种成组展示，不跨源拼接
- PR #277 evidence: table and detail render a known price with its source currency code or `币种未知`; neither silently defaults to USD. Detail no longer labels the unverified ad-spend currency as dollars. CSV/source parity still needs isolated API acceptance.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/listingManagementApi.ts

### LM-037 | 监控数据 | P1 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **检查时间展示的是MART计算时间**
- Recorded condition: checkedAt取calculated_at，不是监控observed_at
- Original acceptance: 展示最近监控采集时间并与同步时间区分
- PR #277 review / Codex TODO: monitor_observed_at is exposed and distinct from calculated_at. Ensure it is latest successful observation, not failed capture.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/listingManagementApi.ts

### LM-038 | 监控数据 | P1 | PARTIAL
- Original issue (源码已确认): **监控图片未成为表格优先来源**
- Recorded condition: 监控存储image_urls_json，表格仍用旧picture_url
- Original acceptance: 增加图片主图/列表及回退策略和来源标记
- PR #277 review / Codex TODO: Primary monitor image and popup gallery exist; image provenance, invalid URLs, fallback/error handling and dedup need E2E.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/walmart_monitor/models.py

### LM-039 | 筛选搜索 | P1 | PARTIAL
- Original issue (源码风险待验收): **平台状态筛选选项不全**
- Recorded condition: UI主要以启用/停用类状态筛选，与SYSTEM PROBLEM等平台状态不同
- Original acceptance: 加入Listing原始状态及标准化状态的独立筛选
- PR #277 review / Codex TODO: Raw problem statuses added inside combined product-state filter; dedicated raw/normalized Listing filter is not implemented.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/components/ListingManagementToolbar.tsx

### LM-040 | 表格分页 | P1 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **列头排序只在当前页完成**
- Recorded condition: 前端table sorter本地排序，后端固定排序分页
- Original acceptance: 排序字段传API，由后端排序后分页
- PR #277 evidence: all 16 sortable table keys use AntD remote `sorter: true` and have backend sort mappings before pagination. Price/rating/review/check-time mappings use the effective monitor projection. Cross-page browser sorting and null ordering still need E2E acceptance.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/components/ListingManagementTable.tsx

### LM-041 | 批量操作 | P1 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **跨页勾选的部分Listing被批量遗漏**
- Recorded condition: selectedListingRows只从当前rows过滤选中ID
- Original acceptance: 按全部选中ID跨页定位并执行，逐个报告结果
- PR #277 evidence: selection is transient per mounted page, while filter changes clear both selected IDs and seen rows. Cross-page batch execution and partial-failure retry have targeted tests; browser/account-switch E2E remains pending.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/ListingManagementPage.tsx

### LM-042 | 导出 | P1 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **导出已选没有将选中ID传后端**
- Recorded condition: exportListingManagementRows只带当前筛选/columns
- Original acceptance: 增加selected_ids，确保只导出选择行
- PR #277 review / Codex TODO: selected_ids now passed to scoped export query. Test selected-only, unauthorized IDs, pagination, large selection and partial-scoped sets.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/listingManagementApi.ts

### LM-043 | 导出 | P1 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **导出超过1万条可能静默截断**
- Recorded condition: export_listings固定limit(max_rows=10000)
- Original acceptance: 超限告警/分批任务导出，提供准确总数
- PR #277 evidence: production route uses `iter_export_listing_csv` with 500-row partitions; a synthetic 10,001-row test confirms no truncation. The non-streaming helper still guards its own 10,000-row limit. Live large-export throughput and browser download remain unverified.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/repository.py

### LM-044 | 数据缓存 | P1 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **操作后缓存可能仍返回旧值**
- Recorded condition: 5分钟resource cache；归档等仅刷新token不一定强制清空缓存
- Original acceptance: 写操作后精准失效行/汇总/筛选缓存
- PR #277 review / Codex TODO: clearResourceCache prefix and refresh dependencies added. Verify tag create/update, permissions, filter options and mutation-specific invalidation.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/shared/preload/resourceCache.ts

### LM-045 | 错误处理 | P1 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **请求失败显示成0条数据**
- Recorded condition: rows catch清空rows与total，summary catch置零
- Original acceptance: 保留上次成功数据、显示错误和重试，不伪装空表
- PR #277 review / Codex TODO: Rows and summary retain prior data on failure; ensure stale banner, independent error states and retry are accurate and not falsely current.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/ListingManagementPage.tsx

### LM-046 | 列配置 | P2 | PARTIAL
- Original issue (源码已确认): **列模板保存未接入接口**
- Recorded condition: 代码TEMPLATE_PENDING常量，提示列模板待接入
- Original acceptance: 完整持久化个人列模板，支持加载及恢复默认
- PR #277 review / Codex TODO: Personal column template stored only in browser pageStateCache; no server/account persistence and incomplete restore-default behavior.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/ListingManagementPage.tsx

### LM-047 | 筛选搜索 | P2 | PATCHED_UNVERIFIED
- Original issue (源码风险待验收): **千行批量搜索与HTTP请求长度不匹配**
- Recorded condition: 前端最多1000行，最终拼为GET查询参数
- Original acceptance: 大批量查询采用POST体，覆盖超长及特殊字符
- PR #277 evidence: batch list/summary and batch/selected export use POST bodies. A 1,000-value frontend regression test verifies the export path and body; isolated API size/permission testing remains pending.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/components/ListingManagementToolbar.tsx

### LM-048 | 标签管理 | P1 | PARTIAL
- Original issue (业务口径待确认): **跨店铺标签按账号+Item ID共享**
- Recorded condition: 标签关联键不含store_id/msku
- Original acceptance: 确定标签的归属粒度，按业务键实现不误标
- PR #277 review / Codex TODO: Tag assignment identity still (account,item_id); same Item across stores intentionally shares tags. User must approve granularity, then migrate safely.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/repository.py

### LM-049 | 标签管理 | P2 | PARTIAL
- Original issue (源码已确认): **页面批量标签入口只支持追加**
- Recorded condition: 后端有replace/remove模式，主页面入口固定append
- Original acceptance: 在界面安全暴露替换/移除，并提供预览
- PR #277 evidence: append/replace/remove modes exist and the shared assignment modal requires explicit danger confirmation for replace/remove, including clear-all count. A per-Listing impact preview and browser acceptance remain pending.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/ListingManagementPage.tsx

### LM-050 | 页面状态 | P2 | PARTIAL
- Original issue (源码风险待验收): **筛选、排序与页面恢复未完整端到端验收**
- Recorded condition: 使用pageStateCache保留页面状态，跨账号及刷新情形需测试
- Original acceptance: E2E覆盖导航返回、刷新、换账号及筛选复原
- PR #277 evidence: pageStateKey includes `preferenceScope`, while selected IDs are transient; filter changes clear selection. Navigation, refresh, and permission-change E2E remain pending.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/ListingManagementPage.tsx

### LM-051 | 经营分析 | P0 | PARTIAL
- Original issue (源码已确认): **经营分析使用硬编码演示指标**
- Recorded condition: ListingAnalysisModal中有静态经营数据
- Original acceptance: 全部经营数据接真实API；无数据明确不可用
- PR #277 review / Codex TODO: Listing entry now uses verifiedListing summary instead of sample trends. Shared modal still has hardcoded periodData fallback; no real trend APIs.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/shared/listing-analysis/ListingAnalysisModal.tsx

### LM-052 | 经营分析 | P0 | PARTIAL
- Original issue (源码已确认): **调价广告评论等经营事件为示例**
- Recorded condition: 经营事件缺少完整真实事件流水
- Original acceptance: 仅显示真实事件，含日期、账号、操作者与来源
- PR #277 review / Codex TODO: Sample events hidden for verified Listing path but authentic dated actor/source event feed not implemented.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/shared/listing-analysis/ListingAnalysisModal.tsx

### LM-053 | 经营分析 | P1 | PARTIAL
- Original issue (源码风险待验收): **关键词可能与当前Listing不匹配**
- Recorded condition: 演示关键词未严格按Item/MSKU/店铺查询
- Original acceptance: 关键词按账户+店铺+Listing+时间范围关联
- PR #277 review / Codex TODO: No scoped account+store+Item/MSKU+date keyword analysis API; do not show sample keywords or cross-Listing aggregates.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/shared/listing-analysis/ListingAnalysisModal.tsx

### LM-054 | 经营分析 | P1 | PARTIAL
- Original issue (源码已确认): **库存补货建议使用演示值**
- Recorded condition: 分析弹窗补货区缺少可信库存/交期模型
- Original acceptance: 接真实销售、库存、采购交期及履约规则
- PR #277 review / Codex TODO: No proven replenishment model using sales velocity, WFS/FBM stock, purchasing lead times and warehouses.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/shared/listing-analysis/ListingAnalysisModal.tsx

### LM-055 | 监控数据 | P1 | PARTIAL
- Original issue (源码已确认): **过期监控值没有明确警告**
- Recorded condition: 最新成功监控值持续覆盖页面，无新鲜度提示
- Original acceptance: 展示observed_at、过期门槛及退回策略
- PR #277 review / Codex TODO: Age badge threshold 48h added; needs stale source precedence and fallback policy, freshness SLA by source.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/repository.py

### LM-056 | 监控数据 | P1 | PARTIAL
- Original issue (源码风险待验收): **表格与导出监控字段口径可能不一致**
- Recorded condition: 多层有效值投影；各展示链路需统一验收
- Original acceptance: 列、筛选、导出、详情共享同一字段投影
- PR #277 review / Codex TODO: Some monitor data is projected through backend/API/CSV/table; field contract still not audited end-to-end, with source timestamps.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/repository.py

### LM-057 | 商品详情 | P2 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **详情与经营分析入口定位混乱**
- Recorded condition: 主表“详情”打开ListingAnalysisModal，另有ListingDetailModal组件
- Original acceptance: 明确详情与分析职责，统一导航入口
- PR #277 review / Codex TODO: Detail button now opens ListingDetailModal, distinct from analysis; verify modal UX, links and independent route tests.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/ListingManagementPage.tsx

### LM-058 | AI链接 | P2 | OPEN
- Original issue (业务口径待确认): **GPT分析仅存链接，不等于AI分析**
- Recorded condition: 当前入口保存关键词和广告链接
- Original acceptance: 明确保留链接模式还是整合AI中心数据
- PR #277 review / Codex TODO: GPT analysis remains URL storage, business decision between link mode and AI center must be documented.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/router.py

### LM-059 | 手动计算 | P0 | OPEN
- Original issue (源码已确认): **缺少全部Listing手动计算入口**
- Recorded condition: 现有批量试算最多50个ID，无完整全量任务入口
- Original acceptance: 有权限触发、后台分批、进度及逐条结果
- PR #277 review / Codex TODO: There is still no permission-gated all-Listing manual recomputation run with progress, audit and results; 50-ID preview is not it.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview_router.py

### LM-060 | 自动任务 | P0 | OPEN
- Original issue (生产已验证): **自动调度未启用**
- Recorded condition: 生产进程无scheduler flag且默认false
- Original acceptance: 明确权限审批后按时执行并有监控告警
- PR #277 review / Codex TODO: Scheduler task exists but flag is default-disabled; operator approval and monitoring/alerting are not implemented/activated.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/tasks.py

### LM-061 | 自动任务 | P0 | PARTIAL
- Original issue (源码已确认): **诊断批次成功不等于正式发布**
- Recorded condition: batch标注candidate_only/blocked，published=false
- Original acceptance: 计算状态与发布状态分离显示
- PR #277 review / Codex TODO: published_count shown separately from candidate counters, but no official publishing workflow exists.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/batch.py

### LM-062 | 自动任务 | P1 | PARTIAL
- Original issue (源码已确认): **同日成功/部分成功后不能重新执行**
- Recorded condition: run_daily_diagnostic遇到succeeded或partial直接返回旧run
- Original acceptance: 受控重算，保留规则版本和历史批次
- PR #277 evidence: failed/partial runs get new immutable attempts; succeeded runs require an explicit `replay_succeeded=True` caller. Retries freeze the original rule version and reject a changed cutoff. An authorized operator trigger and isolated DB replay acceptance remain pending.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/batch.py

### LM-063 | 自动任务 | P1 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **重试删除已有诊断快照**
- Recorded condition: retry_existing会delete旧run的snapshots
- Original acceptance: 快照不可变、按attempt留痕，支持增量重试
- PR #277 evidence: retry creates a new run ID and does not delete prior snapshots; targeted attempt tests pass and the unique `(schedule_date_cn, attempt_count)` migration was exercised in an isolated PostgreSQL run. Runtime replay/history E2E remains pending.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/batch.py

### LM-064 | 自动任务 | P1 | PARTIAL
- Original issue (源码风险待验收): **批次逐Listing独立查询成本高**
- Recorded condition: 循环evaluator.evaluate逐条查询多张表
- Original acceptance: 批量预取、游标分页、吞吐与资源基准测试
- PR #277 evidence: each keyset page now prefetches sales, inventory, prior-stock identity, archive, and monitor evidence in five bounded queries; the shared calculator preserves the single-item formula. Synthetic tests cover two accounts, NULL/MSKU identity, duplicate/oversized pages and query count. Isolated PostgreSQL throughput and index-plan benchmark remain pending.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/batch.py

### LM-065 | 自动任务 | P1 | PARTIAL
- Original issue (源码已确认): **计算结果缺少逐商品错误详情**
- Recorded condition: run列表主要为计数与状态
- Original acceptance: 按Listing展示候选值、来源、错误和证据缺失
- PR #277 review / Codex TODO: Snapshot contains missing evidence but no per-Listing drill-down API with source/error or actionable failure details.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/batch.py

### LM-066 | 权限安全 | P1 | PARTIAL
- Original issue (源码已确认): **批次总体计数可能泄露其他账号规模**
- Recorded condition: 以可见快照过滤run，但返回run的全局统计
- Original acceptance: 分账号重算指标或控制查看权限
- PR #277 review / Codex TODO: Run counters now scoped via snapshots; ensure status/attempt and paginated run metadata do not reveal global tenant counts.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/preview_router.py

### LM-067 | 运营跟进 | P1 | OPEN
- Original issue (源码已确认): **C/D正式跟进任务没有闭环**
- Recorded condition: 仅针对已发布快照生成C/D任务，实际无发布
- Original acceptance: 正式发布后按负责人生成并跟踪C/D待办
- PR #277 review / Codex TODO: C/D follow-up creation depends on published=true but no publish service, so operational follow-ups cannot run end-to-end.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/batch.py

### LM-068 | 运营跟进 | P2 | OPEN
- Original issue (源码已确认): **提醒时间及逾期通知未实际执行**
- Recorded condition: 配置界面说明为未来提醒服务参数
- Original acceptance: 按中国时间触发消息和逾期记录
- PR #277 review / Codex TODO: No actual China-time notification and overdue job with audit/acknowledgement, despite config UI.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/listing_rule_config/batch.py

### LM-069 | 规则配置 | P2 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **配置页说明与真实功能状态不一致**
- Recorded condition: 写着尚未接入/未来服务，Celery任务实际存在但关停
- Original acceptance: 显示已安装、未启用、可试算及权限状态
- PR #277 evidence: the existing rule-config read now reports live preview/scheduler/publish flags and the original drawer displays them separately from task execution evidence. The endpoint does not activate a scheduler; isolated browser acceptance remains pending.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/components/ListingRuleConfigDrawer.tsx

### LM-070 | 质量验收 | P1 | OPEN
- Original issue (源码风险待验收): **验证范围不足以证明全页面正确**
- Recorded condition: 现有主要是静态源码+局部生产只读与单元测试
- Original acceptance: 隔离库整链路API、权限、导出和真实页E2E验收
- PR #277 review / Codex TODO: Latest HEAD is unvalidated; build isolated Postgres, API RBAC, CSV, Playwright E2E and migration replay before declaring done.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/tests/modules/test_walmart_monitor_projection.py

### LM-071 | 监控数据 | P0 | OPEN
- Original issue (需求缺口): **监控RAW的字段没有全量盘点**
- Recorded condition: 当前parsed_result开放JSON，解析器只提取固定名单
- Original acceptance: 建立实际RAW键清单，逐项决定标准化/API/前端/审计去向
- PR #277 review / Codex TODO: No comprehensive real sanitized RAW-key inventory with mapping to normalized fields, public UI fields and restricted audit evidence.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/walmart_monitor/projection.py

### LM-072 | 监控数据 | P1 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **监控商品图片列表没有展示**
- Recorded condition: image_urls_json在monitor current中，Listing API未返回
- Original acceptance: 图片轮播/主图/回退和图片失效处理
- PR #277 review / Codex TODO: Monitor image list and gallery added; verify image validity, fallback to ERP, multiple images and no untrusted URL schemes.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/walmart_monitor/models.py

### LM-073 | 监控数据 | P1 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **真实监控采集时间未进入页面**
- Recorded condition: observed_at已存但API未返回
- Original acceptance: 页面展示上次成功观察时间和数据年龄
- PR #277 review / Codex TODO: observed_at in API/table, monitored age. Verify success-only timestamp, timezone and persisted provenance.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/walmart_monitor/models.py

### LM-074 | 监控数据 | P1 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **监控结果失败原因在页面不可见**
- Recorded condition: monitor_outcome/source/error_code存储但页面未展示
- Original acceptance: 详情提供可解释诊断和失败信息，RAW继续受保护
- PR #277 review / Codex TODO: monitor source/outcome/error code added; ensure failure diagnostics are not misreported as latest successful business value.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/docs/data-sources/decisions/walmart-monitor-listing-projection-decision.md

### LM-075 | 列表字段 | P1 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **本地品名和监控标题的优先级不清**
- Recorded condition: productName先local_name而title优先monitor
- Original acceptance: 分列本地品名与平台标题，来源明确
- PR #277 review / Codex TODO: Local product name and platform title now separated by labels. Verify each originates from authoritative different source.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/listingManagementApi.ts

### LM-076 | 时间与日期 | P1 | PARTIAL
- Original issue (源码已确认): **上架时间仅依赖旧字段**
- Recorded condition: 前端toListingStartText只看listing_start_at_utc
- Original acceptance: 平台真实上架时间设立可核验权威来源
- PR #277 review / Codex TODO: listing_start_at_utc still null on normal new sync and lacks authoritative verified source; raw text alone is not a verified date.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/listingManagementApi.wfsDate.test.ts

### LM-077 | 时间与日期 | P1 | PARTIAL
- Original issue (业务口径待确认): **上架日期、首次可售、WFS首库存概念混淆**
- Recorded condition: 存在listing_start、launch_date_cn、first_wfs_seen_at_utc多个概念
- Original acceptance: 字段独立，明确首次可售与WFS首次有货不等价
- PR #277 review / Codex TODO: UI maps firstWfsAvailableAt from launch_date_cn and also has first_wfs_seen_at_utc. Verify semantic mapping, date/timestamp/timezone.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/integration_sync/wfs_first_stock.py

### LM-078 | 时间与日期 | P1 | PARTIAL
- Original issue (源码已确认): **日期直接截取字符串前10位**
- Recorded condition: toDateText(value) return value.slice(0,10)
- Original acceptance: 按来源时区与业务日期类型统一格式化
- PR #277 review / Codex TODO: toListingStartText now parses to UTC date, but platform local/LA and date-only business semantics are not established.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/listingManagementApi.ts

### LM-079 | 时间与日期 | P1 | OPEN
- Original issue (源码已确认): **新Listing的标准上架时间常规同步不填**
- Recorded condition: _listing_mart_refresh_sql新记录写NULL，冲突更新保留旧值
- Original acceptance: 正确来源校验后写入，保留原始值和验证状态
- PR #277 review / Codex TODO: _listing_mart_refresh_sql still inserts NULL::timestamptz for new listing_start_at_utc and preserves existing. Need trusted normalizer.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/integration_sync/data_pages_real_sync.py

### LM-080 | 监控数据 | P2 | PARTIAL
- Original issue (需求缺口): **监控来源与时效不可追溯**
- Recorded condition: 页面隐藏source、observed_at和原始证据引用
- Original acceptance: 提供运营层摘要和受控审计入口
- PR #277 review / Codex TODO: Monitor source and age are visible, but restricted evidence IDs/audit route and approved field matrix do not exist.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/walmart_monitor/projection.py

### LM-081 | 权限安全 | P0 | PARTIAL
- Original issue (源码已确认): **查看权限可执行归档、标签和GPT链接写操作**
- Recorded condition: router写接口使用listing_principal即查看权限
- Original acceptance: 所有变更操作单设write/action权限和服务端校验
- PR #277 review / Codex TODO: Original ticket suspected view access could write; actual require_permission() calls permission_for_request() action-policy. Re-test RBAC, do not duplicate guards blindly.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/router.py

### LM-082 | 权限安全 | P0 | PARTIAL
- Original issue (源码已确认): **删除共享标签可能删除跨账号关联**
- Recorded condition: 全局标签表删除时delete assignment where tag_id，无账号条件
- Original acceptance: 标签所有权/管理权限独立；跨账号删除受控
- PR #277 review / Codex TODO: Delete-tag rejects if foreign usage exists, but global definition owner is absent; update/delete/list may still affect or disclose other tenants.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/repository.py

### LM-083 | 权限安全 | P1 | OPEN
- Original issue (源码已确认): **可见标签列表可能跨账号**
- Recorded condition: list_tags无定义级账号过滤，仅usage对账号筛选
- Original acceptance: 标签定义按租户/账号作用域显示或明确公用标签策略
- PR #277 review / Codex TODO: list_tags queries ALL active ProductCustomTag definitions and scopes only usage counts. Must enforce tenant ownership or explicit shared/global policy.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/repository.py

### LM-084 | 导出 | P1 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **CSV外部文本未防公式注入**
- Recorded condition: _csv_value对标题、SKU、卖家等字符串直接输出
- Original acceptance: 危险前缀字符进行CSV公式安全防护并测试
- PR #277 evidence: `_csv_value` flattens list cells before checking formula prefixes; synthetic tests cover =, +, -, @, TAB, CR, LF and a list-valued cell. Spreadsheet application behavior remains unverified.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/service.py

### LM-085 | 数据关联 | P1 | PARTIAL
- Original issue (源码风险待验收): **负责人多列MAX可能组成错误配对**
- Recorded condition: owner_lookup对owner_uid/name等字段分别max聚合
- Original acceptance: 以同一可信产品记录联动关联负责人和开发人
- PR #277 review / Codex TODO: owner_lookup now selects UID/name from a single row using row_number, but lexicographic order is not latest/most trusted source.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/repository.py

### LM-086 | 数据关联 | P1 | PARTIAL
- Original issue (源码风险待验收): **监控金额与币种可能来自不同来源**
- Recorded condition: effective_price与effective_currency各自coalesce
- Original acceptance: 金额币种原子成组回退，不允许跨来源拼接
- PR #277 evidence: monitor price/currency fallback is paired via CASE, and list/detail no longer claim USD when currency is unknown. End-to-end source provenance and CSV parity remain pending.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/repository.py

### LM-087 | 归档恢复 | P1 | PATCHED_UNVERIFIED
- Original issue (业务口径待确认): **恢复后历史归档原因仍显示**
- Recorded condition: 恢复标记撤销但旧archive_reason仍可返回
- Original acceptance: 若保留审计原因，分离历史原因与当前生效原因
- PR #277 review / Codex TODO: Restore clears current archive reason; history is lost rather than stored as append-only archive/restoration event log.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/repository.py

### LM-088 | 筛选搜索 | P1 | PATCHED_UNVERIFIED
- Original issue (源码风险待验收): **含逗号筛选值被错误拆分**
- Recorded condition: 前端用逗号连接多选，后端_csv_values按逗号split
- Original acceptance: 改重复参数/POST JSON，保留特殊字符
- PR #277 review / Codex TODO: Multi-select filters use JSON and backend parses JSON; POST batch prevents comma split. Add Unicode/commas/escaping tests.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/components/ListingManagementToolbar.tsx

### LM-089 | 标签管理 | P1 | PATCHED_UNVERIFIED
- Original issue (源码风险待验收): **跨店铺同Item ID批量标签可能产生冲突**
- Recorded condition: assignment唯一键账号+Item ID+标签ID；重复Listing可插入两次
- Original acceptance: 批量去重稳定业务键，明确共享标签粒度
- PR #277 review / Codex TODO: Same account+Item ID selected in multiple stores is deduped before tag inserts; granularity approval still pending.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/models.py

### LM-090 | 标签管理 | P1 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **替换为空标签无法清空**
- Recorded condition: _resolve_tags返回空时提前return，未执行replace删除
- Original acceptance: replace空集合明确实现清空或禁止并提示
- PR #277 review / Codex TODO: replace mode with [] now clears tags; test scoped atomicity and explicit user confirmation.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/repository.py

### LM-091 | 标签管理 | P1 | PATCHED_UNVERIFIED
- Original issue (源码风险待验收): **停用标签可能重新分配**
- Recorded condition: 按名称查找未过滤is_active，可能返回停用标签
- Original acceptance: 只允许激活标签分配，或显式恢复流程
- PR #277 review / Codex TODO: Inactive tag rejected for assignment; tests should cover IDs, names and reactivation workflow.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/repository.py

### LM-092 | 标签管理 | P1 | PARTIAL
- Original issue (源码风险待验收): **标签名称缺少DB唯一约束**
- Recorded condition: 代码校验重名，但表级没有唯一索引
- Original acceptance: 增加数据库安全唯一约束，处理并发创建
- PR #277 review / Codex TODO: Advisory transaction lock added to duplicate-name checks, but DB has no UNIQUE INDEX and auto-creation in _resolve_tags bypasses the lock.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/models.py

### LM-093 | 标签管理 | P2 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **Listing表格统一蓝色标签**
- Recorded condition: 管理模块有color，表格Tag渲染固定blue
- Original acceptance: 使用标签真实颜色并保持对比度
- PR #277 review / Codex TODO: Real tag color passed to table, but global tag names and missing tenant scope may cause wrong color provenance.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/components/ListingManagementTable.tsx

### LM-094 | 统计卡 | P1 | PATCHED_UNVERIFIED
- Original issue (源码已确认): **归档/恢复操作不触发统计卡重取**
- Recorded condition: summary effect仅依赖normalizedFilters，不依赖listingRefreshToken
- Original acceptance: 变更后同时失效/重取summary和表格
- PR #277 review / Codex TODO: Refresh token added to summary effect and cache invalidation. Verify all write operations refresh both table and cards.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/ListingManagementPage.tsx

### LM-095 | 归档恢复 | P1 | PATCHED_UNVERIFIED
- Original issue (源码风险待验收): **归档覆盖状态可能遮住服务器新结果**
- Recorded condition: archiveStateOverrides在displayedRows持续覆盖后台状态
- Original acceptance: 成功后失效覆盖、以服务端状态为准，处理并发变化
- PR #277 review / Codex TODO: Persistent archive override removed; individual optimistic changes still update local row and may retain stale seenListingRows cache.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/ListingManagementPage.tsx

### LM-096 | 批量操作 | P1 | PARTIAL
- Original issue (源码风险待验收): **批量归档恢复未限并发**
- Recorded condition: 对所有targetRows Promise.allSettled同时发请求
- Original acceptance: 控制并发与幂等、失败重试及进度
- PR #277 review / Codex TODO: Batch archive/restore now groups 5 requests, but retry/partial progress/idempotency and per-ID failure details remain missing.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/frontend/src/pages/products/ListingManagementPage.tsx

### LM-097 | 表格分页 | P1 | PATCHED_UNVERIFIED
- Original issue (源码风险待验收): **后端分页排序缺少唯一键兜底**
- Recorded condition: order_by(WFS库存、店铺、SKU、item_id)未含唯一Listing键
- Original acceptance: 稳定追加id兜底，跨页无重复遗漏
- PR #277 review / Codex TODO: Unique ListingManagementCurrentMart.id added as stable sort tie-breaker; test concurrent refresh/keyset semantics.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/repository.py

### LM-098 | 标签管理 | P1 | PATCHED_UNVERIFIED
- Original issue (源码风险待验收): **未知标签ID在批量处理时可静默忽略**
- Recorded condition: _resolve_tags查询存在的ID，未对请求集合严格比对
- Original acceptance: 不存在/越权标签明确报错，原子回滚
- PR #277 review / Codex TODO: Unknown/inactive tag ID now raises ValueError; test full transaction rollback with mixed valid and invalid IDs.
- Original source at old baseline: https://github.com/mz-liuyunlong/SZZSBJ/blob/9bff308dcb9a82dc6039763defa03c414fbfef14/backend/app/modules/data_pages/repository.py

## Mandatory Codex execution instructions - COPY INTO CODEX

You are working in the PRIVATE SZZSBJ repository on existing DRAFT PR #277. You are NOT authorized to create a new branch, fork, draft PR, merge, deploy or touch production. Restore branch exactly:

```bash
git fetch origin
git status --short
git switch codex/listing-management-full-repair-20261030 || git switch --track origin/codex/listing-management-full-repair-20261030
git pull --ff-only origin codex/listing-management-full-repair-20261030
git branch --show-current
git rev-parse HEAD
gh pr view 277 --json number,headRefName,baseRefName,isDraft,url
```

If the working directory contains uncommitted user edits or the branch does not match the PR head, STOP any destructive action, preserve files and reconcile safely. Do NOT reset --hard, force push, checkout main, or overwrite user work.

Treat EVERY original LM-001..LM-098 as in scope, including source risk and business-semantic review. Start from the tracker workbook and this Markdown handoff. Existing targeted edits are a starting point, not necessarily correct. First remove P0 regressions in the risk tracker, then implement the 12 work packages. For each LM issue attach: root cause, impacted files, implementation commit, isolated test, observed outcome, provenance and acceptance notes. Maintain a versioned `docs/.../pr277-98-issue-ledger.md` in THIS SAME BRANCH.

Do not pretend missing upstream ad/fee proof is zero, unknown archive is active, a WFS stock date is platform publish date, diagnostic candidate is official published grade, or sample trends are genuine. Do not bypass RBAC or external API rules. Where valid provider evidence is impossible, keep the result unknown/blocked with reason, document evidence gap and request approval only at production write boundary.

Perform local targeted validation as functions are changed, but defer full CI until all code and tests are ready, as owner directed. Final gates:

```bash
bash scripts/ci-preflight.sh frontend
bash scripts/ci-preflight.sh backend
bash scripts/ci-preflight.sh rules
(cd backend && uv run pytest -q tests/modules/data_pages tests/modules/listing_rule_config tests/core/test_permission_policy_v2.py)
(cd frontend && npm run build && npm run lint && npm run test -- --run)
```

Use isolated PostgreSQL for Alembic upgrade/downgrade, pagination/permission/tenant tests, snapshot replay and publishing rollback. Execute Playwright end-to-end against dev fixtures. Never run migration or backfill on production without separate explicit user approval.

Each batch should cover >=30 newly VERIFIED DISTINCT LM IDs (unless fewer remain), but NEVER pad the count. Report closed/partial/not-started and evidence separately, with commit SHAs. Use same existing PR #277, push to its exact head branch. Do not set PR Ready for Review or merge until owner instructs.

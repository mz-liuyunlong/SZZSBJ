# 打包单审批功能交接：WFS、比例建议与到货

日期：2026-10-28。当前负责人已恢复测试，并授权修复检查问题、同步测试文档、推送 develop 后重新执行全量 CI。以下早期“暂停测试”记录保留为历史，不代表本轮状态。未授权合并 main、生产迁移或部署。

## 本轮 CI 修复与验收范围

- 基准提交 `b190a61` 的 CI 曾为 7 项成功、3 项失败：三个后端文件 Ruff 格式、数量建议单测仍查找“确定”、历史 0054 表清单与当前 ORM 新表混用。
- 数量建议单测已改为查找“保存”，保留修改数量的提交断言；新增浏览器契约用例，验证修改发送 `PUT /pending/{candidate_id}/draft`，不调用审批入口，刷新后仍显示已修改未审批及保存数量。
- 0054 的真实 PostgreSQL 测试固定核对数据库当时的 20 张表，继续执行逐表 ORM 查询及额外分配表严格结构检查；不将未来 0062 表强行加入历史版本。
- 新增 `test_packing_pending_edit_postgresql.py`，使用同一专用 CI 集群中每次新建且由测试拥有的可销毁数据库，分别验证空库、0049、0061 → 当前 0062。核对 21 张国内仓表、草稿表完整结构、0049 合成数据保留及重复 upgrade 不写重复数据。
- 新专项实际调用草稿保存、刷新合并、源版本过期、审批清理及幂等；在提交前注入失败并 flush，验证订单、分配、事件、草稿删除和 PK 序列一起回滚。候选来源及 Listing 证据是合成注入，测试实例仅对已经通过专用集群安全检查的临时数据库绕过本地固定库名写入限制；不将其描述为真实来源数据或生产权限验证。
- 0062 的完整 revision 为 `20261028_0062_packing_pending_edit`，依赖 `20261027_0061_merge_purchase_main`。本轮没有新增迁移、重编号或修改历史迁移。
- 本地后端 Ruff 检查与格式检查通过，建议规则与静态迁移回归 33 passed；新增 PostgreSQL 用例已完成收集，必须以本轮远端实际执行结果验收，不能以本地 skip 代替通过。

修复提交 `e01051828e813082828fd6e633cc542134d75364` 的全量 CI（运行 `40642011374`，可在 PR #262 的 Checks 中查看）已完成，10/10 jobs success，0 failure。旧运行 `40626269042` 的三项失败已在本次修复提交验证通过，保留为历史。

| 本轮远端验收 | 实际结果 |
|---|---|
| Linux 后端全量 | 1802 passed、121 skipped、1 warning；Ruff lint/format、应用导入通过 |
| 国内仓 PostgreSQL 16 专项 | 59 passed、0 failed、0 skipped；包含原 56 项和新增 3 项 0062 升级/草稿事务场景 |
| 前端 | 69 文件、308 Vitest tests passed；lint、TypeScript/Vite 构建通过 |
| 浏览器 Playwright | 28 passed、7 skipped；包含新增 PUT 草稿保存和刷新恢复用例 |
| 其他数据库任务 | IAM、Walmart、PMC PostgreSQL 14、WFS、审批、操作日志全部成功 |

普通后端套件中的 3 项新 PostgreSQL 用例依赖显式隔离库配置，已由上述独立 PostgreSQL job 全部实际执行；其他 opt-in 跳过用例及 7 项需专用 API/bridge 的 E2E 不得笼统记作通过。本轮没有执行真实生产数据或外部提供商联调，也没有处理全项目既有 mypy 诊断和此前独立审查发现的采购备注版本选择问题。

## 授权范围与结果

| 确认项 | 当前改动 |
|---|---|
| 商品完成 WFS 转换才能通过 | 自动候选仍可展示履约类型 0，但标 WFS_NOT_CONVERTED；目标选择与最终审批要求类型 1 |
| blocked 保留待审 | 保持待补资料及具体原因，不自动驳回 |
| ItemID 来源 | 保持批次采购备注＋Listing 共享解析；未迁移历史货件追溯或人工对照表 |
| 多 ItemID 自动预填、人工可改 | 计划数量权重、整箱取整、尾差提示；证据不足保留人工填写；原共享库存上限不变 |
| 采购已到、未到 | 采购 DWD 原明细去重，关联成功同步采购明细 ODS：已到取 payload_json.quantity_entry，未到取 quantity_receive；缺失和版本不一致保持未知 |
| 部分、分批到货 | 到货状态不再固定 unknown；独立分批标记、观测批数／序号和 split_arrival 筛选 |
| 历史领星人工单 | 本轮未接入 |
| PK／OWS 关联 | 继续只生成系统 PK；本轮未增加 OWS 回填或建单 |

## 代码位置

均相对于仓库根目录。

- `backend/app/modules/pmc_domestic/packing_suggestions.py`：纯到货状态、观测分批与建议数量计算。
- `backend/app/modules/pmc_domestic/packing_procurement_repository.py`：成功同步 ODS 最新版本、采购计划权重、原采购行去重、唯一产品箱规投影；只读，不创建 Session，不提交事务。
- `backend/app/modules/pmc_domestic/packing_repository.py`：组合候选、受阻原因、共享库存、累计到货及数量建议；修正过时的“GET 不访问 ODS”说明。
- `backend/app/modules/pmc_domestic/packing_schemas.py`：到货枚举、新增兼容响应字段及 split_arrival 查询。
- `backend/app/modules/pmc_domestic/packing_service.py`、`packing_manual_service.py`：目标 WFS 校验及手工来源到货信息重验；原库存、幂等与审批事务保留。
- `frontend/src/pages/pmc/domestic-warehouse/approval/`：API/类型、Toolbar 分批筛选、Table 到货／分批／建议展示、DecisionModal 建议及人工修改提示。
- `backend/tests/modules/pmc_domestic/test_packing_suggestions.py`：合成数据规则／投影测试，不连接配置数据库。
- 同前端目录 `PackingApprovalTable.test.tsx`、`PackingQuantitySuggestion.test.tsx`，以及 `frontend/e2e/domestic-packing-allocation-arrival.spec.ts`：相关合成验收场景。
- `frontend/playwright.packing.config.ts`：专项 E2E 配置，复用原配置，以当前 Node 直接启动 Vite，避免当前机器没有 npm 可执行文件导致无法启动；未更改依赖或全局配置。

## 数据库与数据源

**没有新增／修改物理表、物理字段、约束、索引或 Alembic revision。没有执行迁移或任何真实数据库读写。** 本轮测试使用合成对象；原需真实数据库的 fixture 未启用。

只读依赖：当前 published 入库 MART／publication、Listing DIM、采购行 DWD、成功同步的采购计划／采购明细 ODS、产品资料当前 DWD。审批命令将新增说明保存在原订单 JSON 快照中，沿用 PostgreSQL 订单、库存分配、审批快照和审计事件。用户实际执行审批时会走原写入流程，本轮并未代用户审批。

引用：

- [数据源决策](../data-sources/decisions/pmc-packing-approval-allocation-arrival-decision.md)
- [实施 PRP](../../PRPs/pmc-packing-approval-allocation-arrival.md)
- [接口与完整字段说明](../api/pmc-domestic-packing-approval-allocation-arrival-api.md)
- [操作说明](../sop/pmc-domestic-packing-approval.md)

## 重要口径和限制

1. 一张采购计划不能唯一确定 ItemID、候选缺少计划份额或数量无效时，不凭空等分。一个计划关联多采购行时分摊权重，避免重复计计划总量。
2. 产品 box_pcs 必须在同账号同 SKU 下唯一且为正整数，才用于整箱建议；否则按件数建议并提示。人工可修改，最终仍由库存校验决定能否审批。
3. 建议数量不是自动审批结果。建议为 0 时不能直接提交；尾差需人工确认。已审批份额不自动重新分配给其他身份。
4. 采购已到量来自最新成功采购明细 payload_json.quantity_entry（到货入库量），未到取同版本 quantity_receive（待到货量）；不是 30 天内事件求和，不使用当前库存或差值替代。DWD 与 ODS 原采购数量不一致时不拼出假精确值。上轮将 quantity_receive 当已到的实现与说明已纠正；此次修复未运行测试。
5. 观测分批以当前已发布入库单为范围，跨店重复行去重，包含零余额单。缺完整历史覆盖时，单张单据不能证明“不是分批”。当前代码仅在历史覆盖完整且到齐时给 false，其余可能仍为 null。
6. 候选仍会随当前采购备注、Listing 和证据重新计算；没有新增身份冻结版本表。当前候选版本校验保留。审批旧快照保持原值，不补写历史。
7. 商品资料和采购数据是否已在实际本地数据库同步完整，尚未验证；文档不得把字段实现写成真实数据已联调。

## 已执行检查与暂停状态

**后续字段纠错记录：**负责人明确要求修复 quantity_receive。仅调整上述两个读取／计算文件、对应合成用例及说明；原始字段依据为领星 LX-D332F931885E 和旧项目339行。未执行测试或迁移，不能把下表纠错前的通过结果当作此次修复验收。当前工作区存在其他审批编辑和迁移改动，不属于此次字段修复，未回退或执行。

以下检查发生在负责人提出“暂时不要测试”之前；之后没有继续启动测试。

| 检查 | 实际结果 |
|---|---|
| 后端 scoped pytest（建议规则、批次 ItemID、审批、手工、生命周期、报关） | 46 passed、19 skipped；跳过的是需要显式真实本地数据库授权的集成场景 |
| 前端审批目录 Vitest，串行 | 7 文件、13 tests passed |
| TypeScript `tsc -b --pretty false` | 当时检查通过；后续新增专项 E2E 配置未再次执行该命令 |
| 修改后端文件 scoped Ruff | 当时通过；最后补充的测试 fixture 随后改动未再跑 lint |
| Playwright 首轮专项与原审批结构场景 | 原审批结构 2 项通过；新增场景在 Select 输入被展示层遮挡的点击定位处超时，前面的到货、建议与 blocked 展示断言已通过 |
| E2E 定位修正 | 已改为点击可见选项标题；**尚未重跑**，不能记为通过 |
| E2E / 测试进程 | 已按负责人要求中断仍在等待的 E2E 运行；早先并行 Vitest 运行已中断，后续串行结果如上 |
| 真实本地数据库、真实接口联调、生产验证 | 未执行 |

主要命令：`python -m pytest -p no:cacheprovider ... -q`；`node node_modules/vitest/vitest.mjs run src/pages/pmc/domestic-warehouse/approval --maxWorkers=1 --no-file-parallelism`；`node node_modules/typescript/bin/tsc -b --pretty false`；`python -m ruff check/format <本轮后端文件>`；`node node_modules/@playwright/test/cli.js test --config=playwright.packing.config.ts ... --workers=1`。使用本地现有运行时，没有安装依赖。

## 回滚与后续

仅回退本轮精确代码与文档 diff 即可，不需要数据库结构回滚。不要用 reset/clean 覆盖后续其他修改。后续由负责人明确恢复验收后，再重跑新增 E2E、实际本地接口联调及必要的最终检查；在此之前不标记 ready，不提交、推送、部署或同步生产数据。

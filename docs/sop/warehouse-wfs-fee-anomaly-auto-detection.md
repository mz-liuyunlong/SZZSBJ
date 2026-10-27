# 页面使用说明：WFS 费用异常自动检测

## 1. 功能位置

仓库 → WFS费用异常。

## 2. 这个页面是干嘛的？

页面展示已有 WFS 异常案件及其检测证据。管理员可对数据库中已经完成采集的证据运行只读检测预览；预览不会请求领星，也不会创建案件。

## 3. 谁需要使用？

- 具备页面查看权限且有相应来源账号数据范围的运营人员。
- dry-run 预览当前仅限真实超级管理员。
- 跟进、归档、复核与标记追回继续使用各自既有动作权限。

## 4. 操作步骤

1. 选择筛选条件并查看案件列表。
2. 打开详情，核对实际主要 WFS、标准费来源、有效订单/件数、三类金额、最新结算日、销量覆盖、WFS 范围证据及质量状态。
3. 超级管理员可点击“检测预览”，确认日期窗口后运行 dry-run。
4. 查看 `would_create`、`already_exists`、`review_required`、`skipped` 和 `failed`；预览结果不能当作已建案或已索赔。
5. 资料不足、过期或默认标准费未确认时转人工复核，不得强制确认。

## 5. 字段说明

| 字段 | 解释 |
|---|---|
| 当前标准 WFS | Product Management 当前计算结果；来源为默认未确认时只作复核依据 |
| 实际主要 WFS | 60 天窗口内按有效订单次数计算的众数 |
| 有效费用订单数 | 进入费用众数计算的订单数量 |
| 有效结算销售件数 | 有费用证据订单的销量合计，不等于历史累计销量 |
| 逐单理论超额 | 仅对高于适用标准的订单差额求和 |
| 全样本净差额 | 全部有效样本的正负差额净和 |
| 旧口径估算 | 主要费率差 × 历史累计销量；不是确认索赔额 |
| 数据时效/异常状态 | 说明证据是否新鲜、完整及是否可以进入案件候选 |
| 销量覆盖状态 | `complete` 必须有生命周期起点及连续同步窗口证明；`partial/missing/unknown` 不能当作 0 或生命周期总销量 |
| WFS 范围证据 | `verified_wfs` 才可进入自动候选；`unverified` 表示接口字段尚不足以证明全部费用属于 WFS |
| 自动立案资格 | 只说明代码门槛是否全部满足；不代表已立案、已审批或已确认索赔 |

## 6. 数据来源

领星 WFS 结算证据经 Integration Sync RAW/事实层持久化；销量来自新系统 Daily Sales MART；标准费来自 Product Management。系统不依赖服务器临时 JSONL 或旧系统运行时数据。

## 7. 权限与安全

- 账号/店铺/MSKU 必须精确匹配，不跨店铺推断。
- 页面不会显示 Token、签名、Authorization 或 RAW payload。
- dry-run 没有写入能力；自动建案与自动检测是两个独立且默认关闭的开关。

## 8. 常见状态

- `OVERCHARGE_CANDIDATE`：证据满足候选条件，不等于索赔已确认。
- `REVIEW_REQUIRED`：默认规则未确认或历史适用性不足。
- `INSUFFICIENT_EVIDENCE`：有效样本不足。
- `STALE`：结算证据超过时效阈值。
- `IDENTITY_UNRESOLVED` / `STANDARD_FEE_UNAVAILABLE`：身份或标准费无法安全确定。
- `COLLECTION_PARTIAL`：采集不完整；不得进入正式检测发布。
- `FUTURE_EVIDENCE`：结算日晚于检测日，必须人工核对时间口径。

## 9. 注意事项

- `would_create` 是预览，不是数据库已新增。
- “逐单理论超额”和“旧口径估算”都不是“已追回金额”。
- 生产迁移、真实采集、案件写入、每日调度和部署必须分别获 Owner 批准。
- Collection 已验证不代表费用类型已验证；WFS 范围与销量覆盖是两个独立门禁。
- 历史窗口重跑不会把旧结算数据变“新”；正式时效始终使用实际检测日期。

## 10. 版本记录

- 2026-10-26：PR #257 Owner-review hardening：店铺级 collection、销量覆盖水位、真实检测时效、append-only detection evidence、分页拆分和批量读取；当前代码待评审，未部署。
- 2026-10-27：本地最终补修 `064bad82`：`current_only` 标准费阻断建案、部分店铺失败令 run 失败、增加固定范围 Provider probe 与只读 0061 preflight；未推送、未连接 Provider/数据库，远端 CI 尚未覆盖该提交。

## 11. Owner 标准费用确认清单

解除单个范围的标准费阻断前，Owner 必须留存以下字段；缺一项继续 `REVIEW_REQUIRED`：

| 字段 | 必须确认的内容 |
|---|---|
| `rule_key` / `rule_version` | 规则身份与不可变版本 |
| `source_account_ref` | 适用来源账号 |
| `store_scope` / `item_scope` | 是账号全量还是明确店铺、Item、MSKU；当前模型不支持的窄范围不得口头放宽 |
| `effective_from` / `effective_to` | 生效窗口及历史订单处理方式 |
| `standard_fee_source` | 官方费率来源、Product Management 公式版本 |
| measurement evidence | 重量、包装尺寸的来源、观测时间与是否可用于历史窗口 |
| `approved_by` / `approved_at` | Owner 身份与批准时间 |

当前已知 MSKU 的 $6.55 是当前默认公式结果，`ACTIVE_RULE_COUNT=0`，不是已批准业务规则。本 SOP 不授权创建或修改规则记录。

## 12. 生产启用顺序

1. **代码合并**：仅在正式 Review 与 checks 通过后；三个 WFS 开关保持关闭。
2. **数据库准备**：验证可恢复备份、锁风险和低峰窗口后，单独授权 0061；不同时启用采集。只读预检工具为 `backend/scripts/preflight_wfs_0061.py`，默认拒绝且不执行 DDL/DML。
3. **单店 Provider 验证**：一个账号、一个领星多平台店铺 `store_id`、一个 MSKU、最多 3 页、零数据库/RAW/案件写入。使用默认拒绝的 `backend/scripts/wfs_settlement_probe.py`，确认 WFS 专用字段与非 WFS 排除规则。
4. **单店 collection/detection dry-run**：仅在 Provider scope、标准规则和 0061 均批准后；检查 store/window 守恒、销量覆盖、时效和身份，不建案。
5. **多店 dry-run**：逐店输出成功/失败/候选/复核/跳过，不允许部分成功掩盖失败。
6. **受控自动建案**：限定账号、店铺和批次；验证 insert-only、幂等及人工状态保护后再扩大。
7. **Celery 调度**：最后单独批准；核对 T-2/60 天、洛杉矶日期/DST、租约、重试、监控和急停。

任一阶段发现分页不完整、未知费用类型、默认未确认标准、销量覆盖不足、证据过期、身份冲突、锁等待、备份不可恢复或旧案件被改变，立即停止并保持/恢复对应开关为 `false`。数据库回滚仅在 0061 新表为空时可用；有证据数据后必须保留数据并走前向修复。

## 13. 当前验收结论

- 代码：远端 PR HEAD `6695114a8594ad585e0556e6491a3b0f7e1f430e` 的 13 个 GitHub checks 全绿，`mergeStateStatus=BLOCKED`；本地补修提交 `064bad82d356077c9c9f43a6645040d489b6cbf4` 已通过 Ruff、WFS `157 passed, 9 skipped`、全后端 `1783 passed, 127 skipped`、应用导入和 Alembic heads，但尚未推送，远端 CI 尚未覆盖，仍待正式 Reviewer/Owner approval。
- Provider：未真实调用；合同仅离线/Mock 验证，WFS scope 未确认。
- 标准费：默认公式可计算；`current_only` 已在代码层阻断建案，但 Owner 规则/范围/历史适用仍未批准。
- Migration：隔离 PostgreSQL 16 往返通过；只读 preflight 已准备但未连接任何数据库，生产备份、锁预检和执行授权未完成。
- 生产：未迁移、未采集、未建案、未启用调度、未部署。

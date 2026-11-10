# PRP：PMC WFS › 设置 —— 后端存储（一期）

状态：`Approved（待 CI 回执后正式放行）`（Rocky 2026-11-03 内容通过；迁移号从 0077 起）

- 起草：PMC 总览组代码 AI（设置归本组，2026-11-03 分工）· 需求方 Rocky（2026-11-03「把 DEMO 已经完成的板块全部上线到 5173」）
- 数据源决策：`docs/data-sources/decisions/pmc-wfs-settings-decision.md`
- 业务来源：8088 DEMO `features/pmc-wfs-shipment/drafts/src/app-d.jsx` 第 114–205 行 `TabSettings`（七块）、`app-b.jsx` 第 95–96 行创建默认值；`features/pmc-wfs-shipment/context/decisions.md`（10-10 异常规则定稿）
- 现状：5173 的「WFS › 设置」是 `WfsSupportPages.tsx`，只有三个数字、只存在本页、刷新恢复；#282 已合 main（迁移 0068–0075）；分支 `pmc/wfs-creation-walmart`（#284，未合 main，需先 rebase）有 `ops_wfs_store_settings`（其迁移 0072 与 #282 编号冲突，本单不沿用）+ `GET/PUT /api/pmc/wfs/settings/stores` + 店铺设置页
- 关联：`PRPs/pmc-wfs-logistics-group.md`（异常中心规则引擎读本 PRP 的阈值；物流商 / 渠道字典 S3）、`PRPs/pmc-overview.md`

---

## 0. 需要负责人决定的事

| # | 事项 | 选项 | 建议 |
|---|---|---|---|
| S1 | 店铺设置从哪来 | a 从 #284 只摘「店铺设置」部分（`store_settings_models.py` / `store_settings_router.py`、前端店铺页、测试），**不沿用迁移 0072**：建表改写成本单新迁移，编号 0077 起（#282 占 0068–0075，#302 已占 0076），`down_revision` 指向届时的 main head；#284 需先 rebase 到最新 main，并去掉 `20261031_0073_walmart_call_audit.py` 与 `walmart_audit.py`（随建货件留到二期）；b 等 #284 整体合并 | a。店铺设置本身不调 Walmart，可以先上；建货件仍按红线二期 |
| S2 | 时效 / 提醒规则存法 | a 版本表：每次保存生成新版本（生效日 + 操作人 + 原因），异常中心按案件发生日取当时生效的版本；b 单行覆盖 + 操作日志 | a，与仓库已有 `ref_store_commission_rule_versions`、`biz_listing_grade_rule_versions` 同做法；异常中心 `rule_version` 有据可查 |
| S3 | 8088 标「示例」的阈值（预计到仓已过 7 / 提前 2、创建后长期未发货 7、Dispute 临近截止 5、到港 → Delivered 美西 5 / 美东 8） | a 照 8088 默认值入库，页面标「示例 · 待定」，异常中心照常用；b 入库但停用，Rocky 定值后再启用 | a（照 8088 现在的行为），页面明显标出。**注意：启用后异常中心会按这 5 条未定值报警，报出的异常数量取决于示例值；列为「待 Rocky 定值」，定值前页面和异常中心都标「按示例阈值」** |
| S4 | 通知渠道（钉钉 / 飞书 / 企业微信开关） | a 一期不做，页面显示「通知未接入」；b 一期存开关、不发送 | a。8088 也只是界面，推送全部关闭；国内仓「通知设置」同样移出本期 |
| S5 | 上架缓冲 10 天的归属：WFS 预计可售日、自动补货提前期、总看板都用 | a 设置页这一项只读，值引用自动补货规则版本（一个数只存一处）；b 设置页可改，三处都读这里 | a；要改由自动补货规则版本改 |

---

## 1. Goal

把 8088「WFS › 设置」做成正式系统里能保存的设置：改了刷新还在，异常中心与创建表单读同一份，谁在什么时候改了什么有记录。

## 2. Scope

### In scope（一期）

| 块（8088 顺序） | 一期做法 |
|---|---|
| ① 时效 / 提醒规则（11 条：节点 × 地区 × 物流商 × 渠道 → 阈值天数、提前提醒天数、生效日、通知对象、备注、已定 / 示例） | 可改、版本化（S2 / S3）；可新增规则行（8088「+ 新增规则」） |
| ② 店铺设置（ITS、Walmart 店铺代码、可创建开关、联系人 / 设施、发货地址簿） | 复用 #284 店铺设置（S1）；加联系人、设施 / 本地仓库名称、电话、邮箱四列（8088 `STORE_SETTINGS_INIT`；不传 Walmart）；发货地址簿只读（取历史货件退货地址去重，WFS 组已同步的数据） |
| ③ Walmart 仓库地区映射（22 个 FC → 美西 / 美中 / 美东 / 待定） | 可改；FC 代码 / 邮编 / 城市 / 州取领星货件真实值 |
| ④ 创建货件默认值（运输类型 LTL、预计发货 = 创建 + 15 天、托盘 = 箱数 / 16 向上取整、混装箱 0、承运人 自选） | 可改、存本系统；只给创建表单带默认值，一期不建货件 |
| ⑤ 物流商 / 渠道字典（领星 61 条） | 只读，读 WFS 组 S3 `dim_logistics_channels` |
| ⑥ 通知渠道 | 不做（S4） |
| ⑦ 数量与时间取值口径 | 静态说明文字，照 8088 |

### Out of scope

- 发送任何通知；Walmart / 领星调用；建货件（#284 适配器，二期按红线）
- 改异常中心规则引擎本身（WFS 组做，只改成读本 PRP 的表）
- 共享文件（`main.py` 路由注册、`model_registry.py`、权限目录）交 PMC 总负责 AI 排队

## 3. Permissions

- 读：`page:pmc:wfs:view`（同 WFS 其他页）
- 写：`action:pmc:wfs-settings:manage`（#284 已用此键）
- 5173 按 R-6 写按钮置灰；8443 上线时开启

## 4. 表（`pmc_wfs` 模块内，命名照仓库 ops_ / ref_ 习惯）

| 表 | 内容 | 写入方 |
|---|---|---|
| `ops_wfs_store_settings`（S1：本单新迁移 0077 起建表，表结构同 #284 模型） | 店铺 × Walmart 代码、ITS、可创建、备注，加 `contact_name`、`facility_name`、`contact_phone`、`contact_email` | 设置页 PUT |
| `ref_wfs_rule_setting_versions` | 版本号、生效日、操作人、原因、创建时间（只追加） | 设置页保存规则 |
| `ref_wfs_rule_settings` | 版本 × 行：`rule_key`（deliveredNotSigned / draftRemind / internalWarn / etaOverdue / diffTol / signNoReceipt / receivingStuck / pendingNoShip / disputeUrgent / portToDelivered / 自定义）、地区、物流商 ID、渠道 ID（空 = 全部）、阈值天数、提前提醒天数、通知对象（文字）、备注、`decided`（已定 / 示例） | 同上；迁移种子 = 8088 `RULE_ROWS_INIT` 11 行 |
| `ref_wfs_fc_regions` | FC 代码（主键）、名称、邮编、城市、州、地区、操作人、更新时间 | 迁移种子 = 8088 `FC_MAP` 22 行；设置页 PUT |
| `ref_wfs_creation_defaults` | 来源账号 × 键值（transport / ship_date_offset / pallet_boxes / mixed_boxes / carrier_opt）、操作人、更新时间 | 迁移种子 = 8088 `CREATE_DEFAULTS_INIT` |
| `evt_wfs_settings_changes` | 每次修改的前后值、操作人、时间、原因（只追加） | 所有 PUT |

不改 RAW / ODS；不删历史版本。

## 5. API（前缀 `/api/pmc/wfs/settings`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/stores` | #284 已有（加联系人四列、发货地址簿只读） |
| PUT | `/stores/{store_id}` | #284 已有（加联系人四列） |
| GET | `/rules` | 当前生效版本 + 全部行；`?at=YYYY-MM-DD` 取当日生效版本（异常中心用） |
| POST | `/rules/versions` | 保存一个新版本（整表提交 + 生效日 + 原因）；生效日不早于今天 |
| GET | `/rules/versions` | 版本历史 |
| GET | `/fc-regions` | 22 个 FC 与地区 |
| PUT | `/fc-regions/{fc}` | 改地区（美西 / 美中 / 美东 / 待定） |
| GET | `/creation-defaults` | 创建默认值 |
| PUT | `/creation-defaults` | 改默认值（校验：偏移 ≥ 0、托盘箱数 ≥ 1、混装 ≥ 0、枚举值） |
| GET | `/logistics-channels` | 只读字典（转读 WFS 组 S3） |
| GET | `/changes` | 修改记录 |

统一 envelope、`response_model`、错误码；写接口记操作人与原因。

## 6. 前端

- 替换 `WfsSupportPages.tsx` 的本地三项表单，按 8088 七块排版（复用 #284 `WfsStoreSettingsPage`、`storeSettingsApi`）。
- 每条规则标「已定 / 示例」；示例行底色提示。
- 5173 写按钮置灰（R-6），保存前弹窗填原因。

## 7. Implementation Plan

1. **PR-S1**：前置：#284 rebase 到最新 main，去掉 `0073_walmart_call_audit` / `walmart_audit.py`。从 #284 摘店铺设置（模型、路由、测试、前端页）到新分支，不带 Walmart 适配器；建表写成新迁移（编号 0077 起，#302 已占 0076，`down_revision` = 届时 main head，开分支时再核一次 head），一次建好含联系人四列；不带 0072 文件。
2. **PR-S2**：规则版本表 + FC 地区 + 创建默认值 + 修改记录；迁移种子；API；测试（版本按日期取、示例标记、校验）。
3. **PR-S3**：前端七块。
4. 异常中心改读 `GET /rules?at=`：由 WFS 组在其 C 步做（本 PRP 提供函数 `get_effective_rules(at)`）。

每步：从最新 main 建 `ai/YYYYMMDD-task`；lint / test / build / `scripts/check-rule-pack.sh` / `git diff --check`；本地检查通过即合进 `pmc/local-preview`，给 Rocky「5173 改动清单」。

### 允许路径

`backend/app/modules/pmc_wfs/store_settings_*`、`backend/app/modules/pmc_wfs/settings_*`（新）、`backend/alembic/versions/<本单新迁移>`、`backend/tests/modules/pmc_wfs/test_*settings*`、`frontend/src/pages/pmc/wfs/WfsSupportPages.tsx`、`WfsStoreSettingsPage.tsx`、`storeSettingsApi.ts`、`settings*`（新）、`docs/api/pmc-wfs-settings-api.md`、本 PRP 与决策文件。

### 禁止路径

共享文件（PMC_OWNERS §4）；`pmc_wfs` 其他文件（WFS 组）；`walmart_gateway.py` / `walmart_audit.py` / 迁移 0072、0073（#284 原迁移，不沿用）；`old-system/`；凭证；服务器与定时任务；`main`。

## 8. Validation Gates

```bash
cd backend && uv run ruff check . && uv run pytest tests/modules/pmc_wfs -k settings
cd frontend && npm run lint && npx vitest run src/pages/pmc/wfs && npm run build
scripts/check-rule-pack.sh && git diff --check
```

验收：七块内容与 8088 逐项一致（11 条规则默认值、22 个 FC 地区、5 个创建默认值、8 家店 ITS 与 #284 一致）；改值刷新后仍在；修改记录可查；`GET /rules?at=` 按日期取版本正确。

## 9. Rollback

新表、新接口：回退 = downgrade 本单迁移（0077 起，种子数据可重建）。开发库若已按 #284 跑过 0072，先由部署AI按票据核对 alembic 版本再处理，不直接删表。

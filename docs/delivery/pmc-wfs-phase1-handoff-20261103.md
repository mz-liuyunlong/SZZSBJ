# PMC WFS 第一期交接（8088 规则，只读，2026-11-03）

- 分支：`ai/20261103-pmc-wfs-phase1`，基于 `pmc/wfs-v2-20261029`（ab61bd8，#282 的分支）
- PRP：`PRPs/pmc-wfs-logistics-group.md`（#298）。**#298 尚未经项目负责人确认，PR 保持 Draft，不得合并。**
- 数据源决策：`docs/data-sources/decisions/pmc-wfs-logistics-phase1-decision.md`
- 计划与进度：`.planning/current/pmc-wfs-phase1/`

## 做了什么

1. 迁移 0076：`raw_pmc_wfs_source_files` + 6 张 ODS 表（Walmart 货件 / 逐 Item / 上架流水，众壹订单 / 轨迹，领星渠道）。显式 DDL，测试对照 ORM；有数据时拒绝降级。
2. 文件加载 `source_loader.py`：只读已校验的采集文件，sha256 重复跳过，新文件成为当前文件、旧文件保留。不调任何外部接口。
3. 看板事实与 8088 规则移植（`board_facts.py`、`board_view.py`、`shipment_board_service.py`）：到仓、可售、分段、差异、产品维度、异常，规则版本 `WFS-RULES-20261010`。
4. 异常中心规则引擎 `exception_detector.py`：命中建单 / 刷新；不再命中系统自动解决；只重开系统解决的案件；测试货件不建单。
5. 待发货打包单：打包完成满 3 天仍有箱子未安排到货件标红，可按此筛选。
6. 页面：货件看板 8088 列、统计卡、负责人 / 分段筛选、抽屉的到仓·可售 / 异常 / 产品明细；待发货标红。
7. 本地回放脚本 `scripts/replay_pmc_wfs_daily.py`：只允许本地库，要 `PMC_WFS_REPLAY_AUTHORIZED=true`。

## 核对结果（2026-11-02 数据）

到仓 897/897、货件字段 25 项、异常 84/84（含描述）、产品行 635/635 与 8088 逐条一致。异常检测首次建 84 条，重跑新建 0 条。

## 本地检查

后端全量 2325 passed / 185 skipped；pmc_wfs PostgreSQL 隔离 62 passed；Vitest 76 文件 353 passed；tsc、eslint、vite build、rule pack 通过；Playwright（模拟接口）新增 2 passed，原有 WFS 待发货、PMC 导航 3 passed。远端 CI 以推送后的 Actions 为准。

## 未做 / 待批准

- 生产迁移 0076、生产文件加载、异常检测定时任务、部署：另行批准。
- 产品维度和 Item ID 依赖 `dim_walmart_listings`，上线环境要先确认维表有数据。
- 写回 Walmart / 领星、箱规写回：第二期。WFS 设置页：D 组。物流板块：下一个 PR。
- 导航 / 路由 / main.py 等共享文件未改动。

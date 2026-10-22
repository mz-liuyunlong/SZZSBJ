# CODEX_HANDOFF.md

## Project

SZZSBJ — Project Rule Pack V1.0

## Current status

Walmart Monitor Target Source V1 已在独立 worktree 完成本地实现，状态为 `approved_for_implementation`，尚未提交、推送、创建 PR、合并或部署。

## Completed work

- 完成接口数据源决策与已批准 PRP。
- 新增 `GET /api/integrations/walmart-monitor/targets`。
- 新增独立 machine Bearer Token、最小只读 principal 和 `integrations:walmart-monitor:read`。
- 从 `mart_listing_management_current` 返回未归档 Listing 的稳定业务键、来源类目、可空库存与 V1 资格字段；归档过滤同时作用于总数和分页。
- 完成 route/schema/service/repository、统一 envelope、错误响应、OpenAPI、Markdown API 文档及 synthetic tests。
- 完成模块、数据接口、任务登记。

## Files changed

- `backend/.env.example`
- `backend/app/core/auth.py`
- `backend/app/core/config.py`
- `backend/app/core/permission_policy_v2.py`
- `backend/app/main.py`
- `backend/app/modules/walmart_monitor_targets/`
- `backend/tests/modules/test_walmart_monitor_target_source.py`
- `docs/api/walmart-monitor-target-source.md`
- `docs/api/README.md`
- `docs/BACKEND_MODULE_CATALOG.md`
- `docs/data-registry/DATA_INTERFACE_REGISTRY.md`
- `docs/tasks/TASK_REGISTRY.md`
- `docs/data-sources/decisions/walmart-monitor-target-source-decision.md`
- `docs/tasks/walmart-monitor-target-source-initial-feature.md`
- `PRPs/walmart-monitor-target-source.md`
- `.planning/current/`

## Commands run

```bash
pytest -q -p no:cacheprovider backend/tests/modules/test_walmart_monitor_target_source.py
ruff format/check <target files>
git diff --check
bash scripts/check-rule-pack.sh
```

此外执行了完整 backend pytest、完整 Ruff、compileall、OpenAPI、offline Alembic head、rule-pack 和差异检查。

## Tests run

- Targeted synthetic API/auth/repository/service tests: `5 passed`。
- Full backend: `1325 passed, 28 skipped`；skip 为仓库既有显式数据库 opt-in suites。
- Full Ruff format/lint、compileall、OpenAPI contract、offline Alembic head (`0047`)、rule-pack 和 `git diff --check`: PASS。

## Decisions

- 数据源为现有 `mart_listing_management_current`，不新增表。
- 稳定业务键为 `source_account_ref + store_id + item_id`。
- `product_name` 只取 `local_name`，不以页面标题替代。
- `wfs_inventory` 缺失时返回 `null`，不会因此取消资格。
- 当前负责人决策为未归档 Listing 可监控，因此返回行的 V1 `monitoring_eligible=true`；归档 Listing 不返回，以后增加其他资格规则必须另开任务。
- 来源类目与监控页面观察类目语义不同，后者进入统一 RAW 事件。

## Risks / blockers

- 真实联调需要先分别评审、合并并部署本接口与 RAW receiver，再安全配置两端 Token；本任务未授权这些动作。
- 接口返回账号、店铺与商品业务标识，只允许专用 machine principal，Token 必须通过生产 secret 管理且不得回显。
- 当前无持久化资格配置；若以后要求按资格过滤，需独立 Source Decision/PRP。

## Next recommended task

- 先进行只读 review。合并/部署后，再单独授权 synthetic smoke 与监控端端到端联调；不要直接运行正式监控。

## Safety confirmation

- [x] Did not modify old-system
- [x] Did not modify production DB
- [x] Did not expose secrets
- [x] Did not deploy
- [x] Updated PRP/planning files

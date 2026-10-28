# Walmart 官方 API 基础模块 V1 — PRP 候选

状态：**Draft / 待负责人批准**（2026-10-26）

## Goal
在 `backend/app/integrations/walmart/` 建立 Walmart 官方直连接口的离线、默认拒绝基础规划模块。供主服务器未来业务模块复用，不在本 PR 打通真实环境。

## In scope
- 9 家店铺均允许进入授权流程；目前 8 家有专用出口映射，CN2502 尚缺专用出口，拒绝实际请求规划。
- 同事 worker 源代码已有的四类 GET 接口目录：wfs_inventory、inbound_shipments、inbound_shipment_items、inventory_log。
- 不允许调用者指定 URL、HTTP 方法或请求头；只接受白名单参数。
- Python plan_call 与 pytest 离线拒绝测试。
- 数据源决策与审查文档。

## Out of scope
- 真实 SSM、SCF、Walmart Token、SSH、联网请求、生产网关。
- 全部 141/185 目录项开发或可用性声明、广告、写操作。
- FastAPI route、Celery 生产任务、RAW/ODS/MART、数据库迁移、页面。
- 主服务器和 Lighthouse 生产变更。

## Source / Owner decisions
- 决策文件：`docs/data-sources/decisions/walmart-official-api-foundation-decision.md`
- 状态：**BLOCKED_BY_OWNER_DECISION**，禁止真实接口。
- 待确认：SCF 内部执行边界与 Invoke 权限；主服务器管理员 Token 可见性；官方逐接口参数与账号权限；固定出口与 SSH 授权。
- Client Secret 必须只在受保护云端读取，且任何测试都不能输出 Token。

## Internal contract
```python
plan_call("HK2615", "wfs_inventory", {"limit": 20},
          allowed_stores=frozenset({"HK2615"}))
```
返回纯数据 WalmartPlan，没有发送请求，不代表完成真实 API。

## Validation
```bash
cd backend
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run python -c "import app.main"
uv run pytest -q tests/integrations/walmart/test_planner.py
```
本次 GitHub 提交没有在仓库完整后端环境执行以上命令，需 CI 及用户本地验收。无 UI 变更，不要求 Playwright。

## Rollback
仅撤销新增的 provider、测试及文档，不修改现有路由/数据库/部署设置。

## Acceptance
- [ ] GitHub 范围审查
- [ ] Python 3.13 Ruff/pytest 通过
- [ ] 模拟测试验证 CN2502 缺少出口时失败、未知/越权店铺、未知接口及参数非法
- [ ] 无生产外部调用或 secret
- [ ] 负责人审阅数据源决策并另批正式接入

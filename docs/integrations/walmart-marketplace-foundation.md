# Walmart Marketplace API 离线基础模块（候选）

**状态：Mock-only；不支持真实 API。**

新增 `backend/app/integrations/walmart/planner.py` 提供 9 店路由（含 CN2502 停用）和同事 `run_worker.py` 已实现的 4 类只读 GET 接口的规划校验。

调用示例：

```python
from app.integrations.walmart.planner import plan_call

plan = plan_call(
    "HK2615", "wfs_inventory", {"limit": 20, "offset": 0},
    allowed_stores=frozenset({"HK2615"}),
)
assert plan.path == "/v3/wfs/inventory"
```

该模块只返回请求规划，不会读取 SSM、申请 Token、SSH 登录、访问 Walmart 或写入数据库。它也不是全接口目录，所有新增官方 API 仍需按来源决策、权限、版本契约进行逐项批准。

代码风险：
- IP 映射根据 2026-10-15 同事交接文档静态登记，**不是**实时网络验证。
- `allowed_stores` 仅本地附加限制，不替代生产执行网关的强制身份与店铺权限校验。
- 未来 Gateway 必须独立校验调用方、店铺、方法、参数、速率、写入审批，并在受保护环境处理短期 Token。
- 若必须保证主服务器管理员也无法获得 Access Token，就不能把 Token 返回给主服务器或让其直接管理远程采集进程。

验收命令：

```bash
cd backend
uv run pytest -q tests/integrations/walmart/test_planner.py
uv run ruff check app/integrations/walmart tests/integrations/walmart
uv run ruff format --check app/integrations/walmart tests/integrations/walmart
```

完整项目 CI 以 `.github/workflows/ci.yml` 为准，当前未声称通过。

真实 SCF 角色绑定、SSM、Walmart 真实 API、SSH、生产部署和数据库修改**全部未执行**。

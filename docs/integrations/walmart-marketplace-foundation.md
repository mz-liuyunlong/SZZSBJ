# Walmart Marketplace API 离线基础模块（候选）

**状态：Mock-only；不支持真实 API。**

新增 `backend/app/integrations/walmart/planner.py` 提供 9 店路由（CN2502 不再禁止，但专用出口尚未配置）和同事 `run_worker.py` 已实现的 4 类只读 GET 接口的规划校验。

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
- IP 映射根据 2026-10-15 同事交接文档静态登记，**不是**实时网络验证。CN2502 无专属出口配置时返回 `WALMART_EXIT_UNAVAILABLE`，不借用其他店铺 IP。
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


## 新增：OpenAPI 3.x 通用契约注册与可审查写接口门禁

`backend/app/integrations/walmart/contracts.py` 提供 `ContractRegistry.from_openapi(spec, approved_keys=frozenset(...))`，把一份**人工核对过**的 OpenAPI 3.x 快照映射到本地方法/参数/路径校验。默认 `approved_keys` 为空，所有接口不可调用。这个入口没有网络 I/O，不会从网上自动拉取不可信定义；不支持任意 `$ref`、复杂 schema 的全部验证或 Walmart 广告单独授权。

```python
from app.integrations.walmart.contracts import ContractRegistry

registry = ContractRegistry.from_openapi(
    {
        "openapi": "3.0.3",
        "paths": {"/v3/items": {
            "get": {"operationId": "listItems",
                    "parameters": [{"name": "limit", "in": "query",
                                    "schema": {"type": "integer", "maximum": 100}}]}
        }},
    },
    approved_keys=frozenset({"listItems"}),
)
request = registry.prepare("listItems", params={"limit": 20})
assert request.method == "GET"
```

生成的 `PreparedRequest` 仅是离线请求对象，不能发给公网执行。真实网关须独立验证服务身份、店铺与操作权限、HTTP method、参数及每次写操作的审批。复杂嵌套 requestBody、multipart/Feed、分页游标与响应模型须按官方契约补专用验证器；本模块不会误称它们已经完成。

新测试：`backend/tests/integrations/walmart/test_contracts.py`；CI 与本地测试仍须独立执行。

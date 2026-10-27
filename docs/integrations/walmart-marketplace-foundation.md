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

## 2026-10-27 实现进展：独立运行代码（仍需线下验收）

此前文档中的“Mock-only”仅描述最初版本；当前分支新增了可由受保护运行环境使用的**实际传输实现**，但它**没有部署、没有绑定真实云端角色，未进行真实 Walmart API 请求**。不能把具备网络调用代码当作“已可生产执行”。

| 模块 | 作用 | 当前边界 |
|---|---|---|
| `client.py` | 统一 `WalmartClient.call()` SDK | 默认无网关；授权店铺范围由调用方提供 |
| `contracts.py` | OpenAPI 3.x 请求契约导入、五类 HTTP 方法、校验 | 默认全部禁用；复杂 Body / multipart / XML 尚未支持 |
| `wfs_catalog.py` | 四类原 Worker GET 接口候选 | 仅获批键才启用；权限和参数仍需官方逐项核对 |
| `scf_bridge.py` | 对 SCF 请求/响应做额外店铺核对 | 不持有 Walmart 密钥 |
| `routed_scf.py` | 一店一 SCF 函数映射 | 同一函数绑定多店会拒绝；无自动跨店故障转移 |
| `tencent_api.py` | 通过 TC3 调用腾讯云 SSM GetSecretValue、SCF Invoke | 运行时临时身份注入；不提供根账号/永久密钥 |
| `tencent_ssm.py` | SCF 内按批准店铺读取 SSM | 只接受 `walmart-{store}` 形式 |
| `tencent_scf.py` | 用 `ClientContext` 进行同步 Invoke | 不创建公开函数 URL |
| `cloud_executor.py` | 云端独立验证店铺、操作及写入审批 | 实际授权政策必须由受保护运行环境注入 |
| `https_transport.py` | 私网 CONNECT 出口下的 Walmart HTTPS / client-credentials Token | 依赖已存在的**受保护私有代理**；无直连 fallback |
| `scf_runtime.py` | SCF 部署入口、每函数固定一家店铺 | 默认禁用真实调用；当前仅支持获批只读操作 |

调用链（获批后才可以执行）：

```text
当前项目 / WalmartClient
  -> RoutedScfGateway（每店独立函数）
  -> TencentScfInvoker（TC3 / Invoke）
  -> SCF main_handler（绑定唯一店铺，独立身份）
  -> CloudExecutor（二次操作/店铺鉴权）
  -> TencentSsmResolver（仅本店 SSM 密钥）
  -> WalmartHttpsTransport（Token + TLS CONNECT）
  -> 本店专属私有代理 -> 固定出口 IP -> Walmart
```

### 主服务器调用示例（仅在审核环境演练）

```python
from app.integrations.walmart.routed_scf import create_scoped_client
from app.integrations.walmart.tencent_api import TemporaryTencentIdentity, TencentApiClient
from app.integrations.walmart.wfs_catalog import wfs_registry

sdk = create_scoped_client(
    wfs_registry(approved_keys=frozenset({"wfs_inventory"})),
    allowed_stores=frozenset({"HK2615"}),  # 必须来自可信后端权限，不可相信前端
    function_by_store={"HK2615": "walmart-HK2615-isolated"},
    cloud_api=TencentApiClient(TemporaryTencentIdentity.from_environment()),
)
# 真实调用仅在云端身份、代理、来源决策/PRP、授权和测试完成后允许：
# result = sdk.call("HK2615", "wfs_inventory", params={"limit": 1})
```

### SCF 部署条件（默认不满足）

- SCF 各函数独立绑定 `PROJECT_WALMART_BOUND_STORE`；例如 CN2502 的函数只可绑定 CN2502。CN2502 未配置专属代理前照样拒绝实际执行，不会降级使用其他出口。
- 各函数必须各自拥有受限的 SSM 读取身份，主服务器身份只能执行必要的 SCF Invoke，不能读取 SSM。角色配置、云函数版本发布、固定出口代理与私网安全组不在本 PR 的自动部署范围。
- 需要安全负责人设置 `PROJECT_WALMART_PRIVATE_PROXIES`（只含本店私网 CONNECT 地址）、`PROJECT_WALMART_APPROVED_READ_KEYS`、`PROJECT_WALMART_SECRET_VERSION`；人工审查后才可启用 `PROJECT_WALMART_LIVE_MODE=owner-approved-read-only`。
- `PROJECT_WALMART_CONTRACT_FILE` 与 `PROJECT_WALMART_CONTRACT_SHA256` 可指定已经审核的 OpenAPI 3.x 快照；快照不等于接口权限获批。
- 代理必须由安全负责人实施私网接入认证、只允许 CONNECT 到 Walmart:443、出口 IP 绑定、日志脱敏；单纯配置一个私有 IP 并不能证明所有这些措施已生效。
- Walmart API Token 只应在受保护 SCF 内存中使用，不得回传 SDK 或作为 SSH stdin 发送给普通开发人员可管理的机器。

### 必须在声明“全部完成”前补齐

真实执行端身份与 9 家店的独立固定出口逐店验收、当前全部 Walmart 官方接口与账号 scope 快照、复杂 schema 与 feed/分页适配、端点级限流和跨进程幂等写入审批、RAW→标准化→DQ→发布、Celery 管理与数据中心接口文档。当前 `scf_runtime` 强制拒绝所有写操作，不具备完整生产能力。

验收（不需要生产凭据）：

```bash
cd backend
uv run ruff format --check .
uv run ruff check .
uv run pytest -q tests/integrations/walmart
uv run python -c "import app.main"
```

**生产调用、密钥配置、数据库迁移、部署和真实写接口都没有在本 PR 中执行。**

文档中使用的 `PROJECT_WALMART_` 是示意前缀，实际变量以 `scf_runtime.py` 为准；此处不重复硬编码项目私有环境变量名。

# Walmart 统一只读 SDK / 服务器预检（PR #259）

## 定位与边界

- 历史目录：192 项业务能力 / 143 个物理方法与路径；**仅发现，不是 192 项已实现**。
- `load_unified_registry` 复用当前 22 项候选契约，并可加载已审核的 OpenAPI 3.x 本地 JSON 快照；该快照必须有精确 SHA256，禁止动态 URL / 外部 $ref。
- 每次调用都要求**店铺授权 + operation key 明确批准 + SCF 内独立验证**。默认不发请求，不允许写操作。
- 旧四接口由 `WalmartReadAPI.original_worker` 复用；一般 GET 使用 `.call`，分页使用 `.pages`。需要的字段未写入契约时，必须先核准新快照；不能直接传任意请求参数。
- Walmart Connect、Feeds 上传与文件类 Reports、POST 写接口和 9 店真实部署**不在本离线实现范围内**。

## 业务代码复用

```python
from app.integrations.walmart.unified_api import WalmartReadAPI, load_unified_registry
from app.integrations.walmart.routed_scf import create_scoped_client

registry = load_unified_registry(frozenset({"wfs_inventory"}))
client = create_scoped_client(
    registry,
    allowed_stores=frozenset({"HK2615"}),
    function_by_store={"HK2615": "OWNER_REVIEWED_SCF_FUNCTION"},
    cloud_api=approved_tencent_cloud_api,
)
result = WalmartReadAPI(client).call("HK2615", "wfs_inventory", params={"limit": 50})
```

示例必须在独立可信的 SCF / SSM / 固定出口配置及店铺审批完成后才能执行；`approved_tencent_cloud_api` 由可信运行环境注入，不能在主服务器存放 Walmart 长期密钥。

## 服务器检查（默认无网络）

在 `backend/` 下执行：

```bash
uv run python -m app.integrations.walmart.server_probe
```

检查指定已批准接口（参数写入本机访问受限的 JSON 文件；不会在日志中回显）：

```bash
SZZSBJ_WALMART_APPROVED_READ_KEYS=wfs_inventory \
uv run python -m app.integrations.walmart.server_probe \
  --store HK2615 --operation wfs_inventory
```

只在负责人确认云端环境后，设置 `SZZSBJ_WALMART_LIVE_MODE=owner-approved-read-only`、
`SZZSBJ_WALMART_ALLOW_PROBE=1`、`SZZSBJ_WALMART_TEST_STORE`、
`SZZSBJ_WALMART_SCF_FUNCTION_BY_STORE`（**仅一个店铺**）、临时腾讯云身份和审批的 read keys，再追加 `--live`。
该命令仅返回 HTTP 状态，不打印响应体、密钥或令牌。**不能用本命令跳过既有真实访问审批、SSM 凭据隔离、固定出口和业务 RAW 审批。**

扩展官方契约：设置 `SZZSBJ_WALMART_CONTRACT_FILE` 和
`SZZSBJ_WALMART_CONTRACT_SHA256`，然后按批准的 `operationId` 设置 read keys。
不能把原始 `app.js` 目录直接当作 OpenAPI 契约。

## 测试

```bash
cd backend
uv run ruff format --check .
uv run ruff check .
uv run pytest tests/integrations/walmart
```

状态：离线 SDK 接口。本 PR 保持 Draft；未调用真实店铺、未部署、未做生产数据库操作。

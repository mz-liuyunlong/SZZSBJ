# SZZSBJ Walmart SCF 只读调用接入（密钥隔离）

> 状态：代码审查用；**不代表已经部署**。本 PR 不修改腾讯云函数、SSM、生产数据库或 Walmart 凭据。

## 业务代码只调用一个入口

```python
from app.integrations.walmart.scf_read_factory import make_walmart_read_api

api = make_walmart_read_api(
    allowed_stores=frozenset({"HK2613"}),  # 必须由服务端鉴权确定
    approved_read_keys=frozenset({"wfs_inventory"}),
    function_by_store={
        "HK2613": "szzsbj-walmart-hk2613-executor",
    },
    cvm_role="SZZSBJ-CVM-SCF-Invoker",
    target_role_arn=("qcs::cam::uin/100013426561:roleName/SZZSBJ-CrossAccount-SCF-Invoker"),
    function_qualifier="stable",
)
result = api.call("HK2613", "wfs_inventory", params={"limit": 1})
# result.status_code / result.data
```

- 把 `api` 在后端集成层创建并注入 Service/Celery；不要在前端或 FastAPI Route 里处理 Tencent 签名或 Walmart Token。
- 上例只展示 **已审核** 的 `wfs_inventory`。其它 operation 需要在两端分别有契约和明确批准。
- 避免每次请求重新构造 API：建议每个进程复用 `CachedScfAssumeRoleIdentity` 实例，保留内存中的 STS 缓存；多个 Celery 进程分别缓存。
- `allowed_stores` 只能来自可信服务端鉴权，不能直接来自用户上传的店铺数组。
- **不要将示例映射直接覆盖 `server_probe.py` 的单店测试变量**：该脚本要求测试作用域恰好一家店。

## 从服务器到 Walmart 的链路

```text
SZZSBJ Service / Celery
  -> WalmartReadAPI.call(store_code, operation, params)
  -> Tencent CVM instance role（无 Walmart 凭据）
  -> STS AssumeRole -> 账号 B 短期 Tencent 身份
  -> Tencent SCF Invoke（仅指定店铺的受控函数）
  -> 账号 B SCF 验证绑定店铺 + API 契约 + 只读策略
  -> 账号 B SCF 读取本店 SSM -> 获取 Walmart Access Token
  -> SCF 发出 Walmart HTTPS GET -> 返回获授权业务数据
```

主服务器不得获取 Walmart Client ID、Client Secret、Access Token 或账号 B 的 SSM GetSecretValue 权限；仅持有腾讯云 *短期* 调用身份。SCF 的运行角色、密钥范围、出网和请求日志必须独立审计。把 Walmart 数据返回服务器不等于把 Walmart Token 返回服务器。

## 9 家店铺 SCF 映射

```json
{
  "HK2612": "szzsbj-walmart-hk2612-executor",
  "HK2613": "szzsbj-walmart-hk2613-executor",
  "HK2614": "szzsbj-walmart-hk2614-executor",
  "HK2615": "szzsbj-walmart-hk2615-executor",
  "CN2501": "szzsbj-walmart-cn2501-executor",
  "CN2502": "szzsbj-walmart-cn2502-executor",
  "CN2601": "szzsbj-walmart-cn2601-executor",
  "CN2602": "szzsbj-walmart-cn2602-executor",
  "CN2603": "szzsbj-walmart-cn2603-executor"
}
```

此为 **目标路由映射**，不应替代任何生产配置。当前仓库 `planner.py` 的 CN2502 出口注释过时，需独立核对实际部署。

## SCF 收到的事件

```json
{
  "version": 1,
  "operation": "marketplace_call",
  "store_code": "HK2613",
  "api_key": "wfs_inventory",
  "method": "GET",
  "path": "/v3/wfs/inventory",
  "query": {"limit": 1},
  "body": null,
  "approval_ref": null
}
```

请求只包含店铺、已批准 API、路径和动态参数，绝不包含 Walmart 凭据或 Token。

成功时 SCF 返回：

```json
{
  "success": true,
  "status_code": 200,
  "store_code": "HK2613",
  "api_key": "wfs_inventory",
  "data": {}
}
```

`data` 为获授权业务响应，此处省略实际字段和业务记录。失败返回稳定的 `status` 错误码，不返回认证头与原始异常。

## 已验证 / 未完成的边界

- 2026-10-28 人工测试：CVM 身份成功、STS AssumeRole 成功、九店 SCF `$LATEST` Health 成功、九店 `wfs_inventory` HTTP 200。
- 当前仓库 `TencentScfInvoker` 默认 `stable`，且禁止把 `$LATEST` 作为正式别名；**该 PR 不发布云函数、不创建别名**。
- 本 PR 仅新增进程内短期 STS 提供者和业务 API 构造入口。尚未接入真实业务路由/定时同步，未验证生产数据入库、订单/退款/广告等 API。
- 账号 B 云端已验证的出口行为与仓库 `scf_runtime.py` 私有代理实现不完全一致；上线前应读取实际部署版本和环境配置核对，**不能直接覆盖已运行的 SCF**。
- 未来要移除九家逐店维护接口白名单，必须设计安全的集中策略分发；不能把 192 项历史 API 目录当作全部批准。

## 审查与验收

1. 离线测试：`pytest -q tests/integrations/walmart/test_tenc_sts_identity.py tests/integrations/walmart/test_scf_read_factory.py`
2. 运行 `ruff format --check .`、`ruff check .`、`pytest`、`python -c "import app.main"`，以 GitHub CI 为准。
3. 在账号 A 和账号 B 核对最小权限：CVM 可 AssumeRole；受限角色仅 Invoke；主服务器无 SSM 读权限、无 SCF 修改权限。
4. 验收拒绝跨店调用、未批准操作、服务端用户无权店铺；确认日志中无 Token 和认证头。
5. **在单独生产变更审批后**核对云端代码并发布不可变版本、设定 `stable`，再跑九店测试。
6. 业务同步、分页、RAW/审计、DQ、幂等和 Celery 任务作为后续独立验收，不在本 PR 启用。

## WFS 写操作（2026-10-31 新增，默认关闭）

PMC「WFS 货件创建」需要 6 个写调用，契约在 `wfs_write_catalog.py`（全部 `mutating=True`，按 9–10 月真实执行过的请求体写 `request_schema`）：

| key | 调用 | 备注 |
|---|---|---|
| `wfs_inbound_shipment_create` | POST /v3/fulfillment/inbound-shipments | 幂等键 = inboundOrderId（业务侧建前 GET 查重） |
| `wfs_shipment_label` | POST /v3/fulfillment/shipment-label | 返回 PDF（`response_kind="pdf"`） |
| `wfs_inbound_preview` | POST /v3/fulfillment/inbound-preview | 查询型，但仍按写审批 |
| `wfs_inbound_shipment_cancel` | DELETE /v3/fulfillment/inbound-shipments/{inboundOrderId} | 临时 5xx/520 由业务侧重试 ≤3 |
| `wfs_shipment_quantities` | PUT /v3/fulfillment/shipment-quantities | |
| `wfs_shipment_tracking` | POST /v3/fulfillment/shipment-tracking | 追加语义 |

入口：`scf_write_factory.make_walmart_write_api(..., approved_write_keys=...)` → `WalmartWriteAPI.call(store, key, approval_ref=<业务操作 UUID>, body=...)`。读 API 仍然不能发写；写 key 不能通过 `approved_keys`（读审批）启用；OpenAPI 快照不能启用写。

链路差异（桥协议 v2，只有写工厂使用）：
- 事件多一个 `accept`（`json` / `pdf`）。
- Walmart 返回 4xx/5xx 时云函数**不再报 `WALMART_PROVIDER_ERROR`**，而是 `success=true, status_code=4xx, provider_error=<Walmart 错误体（去敏）>`，`WalmartResult.provider_error` 给业务侧展示原因。
- 箱唛 PDF 以 base64 回传（≤5MB），桥解码并校验 `%PDF` 头，`WalmartResult.pdf` 是字节。
- 协议 v1（现有只读路径）行为不变。

云函数部署要求（由云端负责人发布到 `stable`）：
- `SZZSBJ_WALMART_LIVE_MODE=owner-approved-read-write`（原值 `owner-approved-read-only` 继续只读）。
- `SZZSBJ_WALMART_APPROVED_WRITE_KEYS=wfs_inbound_shipment_create,wfs_shipment_label,...`（只能是上表的 key）。
- 读 key 仍走 `SZZSBJ_WALMART_APPROVED_READ_KEYS`；WFS 看板需要加 `inbound_shipments,inbound_shipment_items`（2026-10-31 实测当前只批了 `wfs_inventory`，调 `inbound_shipments` 返回 `WALMART_OPERATION_NOT_APPROVED`）。
- 写模式下传输超时 90 秒、透传 Walmart 错误体；策略 `StoreWritePolicy` 要求写事件带 `approval_ref`。

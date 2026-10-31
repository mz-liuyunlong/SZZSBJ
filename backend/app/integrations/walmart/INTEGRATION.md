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

## 协议 v3：签名契约（2026-10-31，回应云函数所有者的架构要求；按其 10-31 六项补充修订）

目标：新增一个 Walmart 接口不再需要修改八个云函数的 `APPROVED_READ_KEYS` / `APPROVED_WRITE_KEYS` 并重新发布。设计全文见 `features/pmc-handover/chapters/76_walmart_unified_gateway_design.md`。

**适用范围**：本协议和云函数传输层固定 `https://marketplace.walmartapis.com` + `/v3/...`，覆盖的是 Walmart **Marketplace** 接口（含 WFS），不等于所有 Walmart 服务的 API。要支持其他官方域名或协议版本，需要独立审核并升级云函数。

### 签名覆盖什么（`contract_signing.signing_payload`）

协议版本 `v`、`kid`、目标店铺 `store_code`、目标云函数 `function_name`、`operation_key`、HTTP `method`、实际 `path`、`params_sha256`（路径+查询参数值）、`body_sha256`、`contract_sha256`、`response_kind`（json/pdf）、`risk`（read/write）、调用人 `actor_kind` / `actor_uid`、`request_id`、`issued_at`、`expires_at`、`approval_ref`。Ed25519，签名放在事件 `auth` 里（`kid / request_id / issued_at / expires_at / sig`）。调用人身份改一个字、approval_ref 改一个字，签名即失效。

规范化 JSON（两端同一函数 `contracts.canonical_json`）：UTF-8、键排序、分隔符 `,` `:` 无空格、非 ASCII 原样、拒绝 NaN/Infinity、数字按 Python `json` 规则（整数精确，浮点 `repr`）。两端跑同一模块，同一请求算出同一摘要。

### 有效期、重放、轮换

- 服务器默认签 120 秒有效（`ttl_seconds`，上限 300）；云函数拒绝 `expires_at` 已过、`issued_at` 超前 > 60 秒、TTL 不在 1–300 秒的签名。
- `request_id`（uuid4）每次调用新生成；云函数在验签通过后对 `(kid, request_id)` 做**原子首次领取**（`ReplayStore.claim`），领不到 → `WALMART_SIGNATURE_REPLAYED`。三种实现：`MemoryReplayStore`（本实例内存，只够读）、`FileReplayStore`（所有实例共同挂载的 CFS 目录，`open(O_CREAT|O_EXCL)` 原子建标记文件，`SZZSBJ_WALMART_REPLAY_DIR`）、`RedisReplayStore`（`SET NX PX`，`SZZSBJ_WALMART_REPLAY_REDIS_URL`）。**写操作只在共享存储（File/Redis）下执行**，否则 `WALMART_REPLAY_STORE_REQUIRED`——跨实例重放由云端自己挡住，不把主服务器账本当替代；账本和 Walmart `inboundOrderId` 唯一性是另外两层。
- 轮换：云函数 `SZZSBJ_WALMART_CONTRACT_PUBLIC_KEYS` 可同时放最多 4 把 `{"kid": 公钥}`；先加新公钥 → 服务器切新 `kid` 与私钥 → 观察无 `WALMART_SIGNATURE_KEY_UNKNOWN` 后删旧公钥。

### 契约来源

- 事件里的 `actor`（`{"kind": "user|system", "uid"}`）在签名之内，云函数验签时同时校验形状。
- `ContractSigner` 构造时绑定一个注册中心（生产 = `unified_api.reviewed_registry()`），**只签该注册中心里的契约**（按契约摘要比对）；业务代码临时拼的 method/path/schema、或 `prepare()` 之后被改过的契约，一律 `WALMART_CONTRACT_NOT_REGISTERED`。
- 云函数用事件里的契约 `operation_from_contract()` 重建 Operation（形状校验：方法集合、`/v3` 路径正则、字段结构、禁止 authorization/cookie 等受限参数名）再跑一遍 `prepare()`；调用方自报的 method/path/accept 只用来比对。
- 传输层（`https_transport`）仍固定域名、HTTPS、`/v3` 路径、不跟随重定向、不接受任何调用方请求头、请求 ≤ 2MB、响应 ≤ 5MB。v3 事件没有 headers 字段，多余字段整体拒绝。

### 风险等级（云函数自己判断）

`risk_for(method, key)`：GET = read；POST/PUT/PATCH/DELETE = write，除非 key 在云端代码常量 `READ_SEMANTIC_NON_GET_KEYS`（目前为空；WFS inbound-preview 是 POST，按写处理）。云函数不信契约里的 `mutating` 字段单独判读；服务器声明的 `risk` 与云端计算不一致 → `WALMART_RISK_MISMATCH`。每店唯一开关 `SZZSBJ_WALMART_MAX_RISK=read|write`（`write` 还需 `LIVE_MODE=owner-approved-read-write`）；write 还要求 `approval_ref`。

### 与 v1/v2 的关系

- v1/v2 事件走原有代码路径和原有环境变量白名单（`APPROVED_READ_KEYS` / `APPROVED_WRITE_KEYS`），**不会因为注册中心全量启用而多出任何操作**（测试 `test_legacy_v1_keeps_its_own_allowlist_and_v3_is_off_without_keys`）。
- 云函数未配置公钥时 v3 事件直接 `WALMART_PROTOCOL_NOT_ENABLED`。
- 主服务器 `SZZSBJ_WALMART_SCF_PROTOCOL=1|3` 切换；回滚 = 改回 1（八店只读仍走 v1 白名单）。

### 云函数首次升级与回滚

1. 隔离环境（非 stable 的新版本号或独立测试函数）验证 v1 健康、v1 只读、v3 只读。
2. 灰度：仅 HK2613 发布新版本 + 配 `SZZSBJ_WALMART_CONTRACT_PUBLIC_KEYS`、`SZZSBJ_WALMART_MAX_RISK=read`、（可选）`SZZSBJ_WALMART_FUNCTION_NAME`；写入阶段再加 CFS 挂载 + `SZZSBJ_WALMART_REPLAY_DIR`（或 Redis）；切 `stable`；服务器 PROTOCOL=3 下跑库存、发货单、分页、4xx/5xx 错误处理；确认无异常。
3. 其余七店同样步骤。
4. 回滚：`stable` 别名指回旧版本号（环境变量多出的两项无害），服务器 PROTOCOL 改回 1。
5. 生产写入：代码验收 + 业务权限 + 幂等账本 + 审计通过后，才把某店 `MAX_RISK` 改 `write`；开发期间不做真实写。

仍需升级云函数的情况：协议版本、json/pdf 之外的响应类型、Walmart 域名或 `/v3` 基路径变化、运行时安全更新。密钥轮换和风险上限只改环境变量。**加接口、改契约、加业务模块不需要。**

测试：`tests/integrations/walmart/test_protocol_v3.py`（契约往返与形状校验、签名覆盖项逐一篡改含 actor、过期/超前/TTL、同实例与**跨实例**重放、Redis 实现、密钥轮换、未注册契约拒签、v3 读写执行、无共享存储拒写、风险上限与 POST 读语义、跨店/跨函数、v1 白名单不变、桥接端到端、PDF、provider_error、运行时门禁）；`tests/integrations/walmart/test_gateway.py`（授权矩阵、无账本拒写、审计失败拒写 + outbox 重放、账本稳定码）；`tests/modules/walmart_scf/test_persistence.py`（SQLite 生命周期、进程重启、插入竞争；设置 `SZZSBJ_PG_TEST_URL` 时跑 PostgreSQL 8 线程 FOR UPDATE / 唯一约束并发）。

## 统一网关 `gateway.WalmartGateway`（2026-10-31）

业务模块只用这一个入口，不再各自包一层读/写客户端：

```python
from app.integrations.walmart.gateway import Actor, WalmartGateway

gw = WalmartGateway.from_env()  # 读 SZZSBJ_WALMART_SCF_*；PROTOCOL=3 时加载签名私钥
actor = Actor.from_principal(
    principal, store_codes=verified_store_codes
)  # 用户：RBAC 权限 + 店铺范围
worker = Actor.system(
    "pmc-wfs-creation", operations={"inbound_shipments", "wfs_inbound_shipment_create"}
)

res = gw.call(
    "HK2614", "inbound_shipments", actor=actor, params={"fromCreatedDate": a, "toCreatedDate": b}
)
rows = gw.pages(
    "HK2614", actor=actor, contract=PageContract(...), params={"shipmentId": sid}, page_size=50
)
many = gw.call_many(["HK2614", "HK2613"], "wfs_inventory", actor=actor, params={"limit": 50})
res = gw.call(
    "HK2614",
    "wfs_inbound_shipment_create",
    actor=worker,
    body=payload,
    approval_ref=f"wfs-ticket:{tid}",
)
```

授权在服务器侧 `authorize()`：操作必须在注册中心；店铺必须在服务器映射且在 actor 的店铺范围内；actor 必须有该操作的 `permission`（`action:walmart:<family>:read` / `action:walmart:wfs:shipments:write` / `action:walmart:wfs:shipments:cancel`，`*` 表示全部）；system actor 只能用自己代码里列出的 operations；写操作必须带 `approval_ref`（审计引用，不是权限）。失败抛 `GatewayError(code)`；Walmart 4xx/5xx 作为结果返回（`provider_error`），传输/云函数异常抛 `WALMART_GATEWAY_UNAVAILABLE` 等稳定码，业务侧按 UNKNOWN 处理、不得重发。

RBAC 落点：权限 key 由注册中心定义（`Operation.permission`），不是调用方传的；`Actor.from_principal` 只接受服务端登录身份（`Principal`）和服务端解析出的店铺范围（来源账号 + 店铺数据范围 → 店铺代码映射），普通用户无法自己传 permission、store_code 或 approval_ref 来获得权限——这三样都在服务端生成或校验。Celery / worker 用 `Actor.system(uid, operations=...)`，允许的操作写死在该任务代码里。

写操作幂等（`WriteLedger`，**持久化**）：`call()` 对写操作要求 `idempotency_key`（业务身份，如 `wfs-create:<inboundOrderId>`）。调用前 `begin` = 原子领取（PostgreSQL `SELECT … FOR UPDATE` + 唯一约束，并发只有一个赢家，输家得 `WALMART_WRITE_PENDING_REVIEW`），然后持久化一条 `attempt` 审计——**两者都成功，请求才会离开服务器**；调用后 `finish`（ok / provider_error / unknown）。上一次 attempting 或 unknown 的 key → `WALMART_WRITE_PENDING_REVIEW`，必须先回查（读 Walmart）再 `resolve`；已 ok 的 key → `WALMART_WRITE_ALREADY_DONE`；同 key 不同请求体 → `WALMART_WRITE_PAYLOAD_CHANGED`。进程重启后状态只在数据库里，新进程看到的就是真实状态（`open_keys()` 给对账任务）。实现：`app/modules/walmart_scf/persistence.py` 的 `DbWriteLedger`（表 `integration_walmart_write_ledger`，迁移 `20261031_0069_walmart_gateway_ledger`）。网关**默认不带账本**（`RefusingLedger`：任何写 → `WALMART_LEDGER_REQUIRED`，读不受影响）；`from_env()` 拒绝不传持久化账本/审计，也拒绝 `InMemoryWriteLedger`（它只能在测试里显式构造）。生产只用 `persistence.build_production_gateway(session_factory)`。

审计（**数据库，可靠**）：每次调用（含被拒绝的）产生一条 `CallRecord`（店、操作、风险、actor、approval_ref、幂等 key、契约与请求摘要、状态码、结果、耗时；不含参数/请求体/响应体），由 `DbAuditSink` 写入 `integration_walmart_calls`（同一迁移）。sink 失败不再静默降级：记录进内存 outbox 并写日志；**写操作在 outbox 非空或 attempt 行写不进去时直接拒绝**（`WALMART_AUDIT_UNAVAILABLE`，并把刚领取的账本项 finish 为 failed）；下一次调用先重放 outbox。读操作照常返回结果，其证据在 outbox + 日志里等待重放。

主服务器环境变量：

| 变量 | 说明 |
|---|---|
| `SZZSBJ_WALMART_SCF_PROTOCOL` | `1`（默认，沿用 APPROVED_*_KEYS 白名单）或 `3`（签名契约；云函数升级后再切） |
| `SZZSBJ_WALMART_SCF_STORE_ID_MAP` / `_CVM_ROLE` / `_TARGET_ROLE_ARN` | 已有，不变 |
| `SZZSBJ_WALMART_CONTRACT_SIGNING_KEY_FILE` | 私钥 PEM（默认 `/etc/szzsbj/walmart-contract-signing.pem`，root:szzsbj 640，不进仓库） |
| `SZZSBJ_WALMART_CONTRACT_SIGNING_KEY_ID` | kid，与云函数 `SZZSBJ_WALMART_CONTRACT_PUBLIC_KEYS` 里的键一致 |

云函数环境变量（v3 新增）：`SZZSBJ_WALMART_CONTRACT_PUBLIC_KEYS`（必需）、`SZZSBJ_WALMART_MAX_RISK=read|write`（默认 read）、`SZZSBJ_WALMART_REPLAY_DIR`（CFS 挂载目录）或 `SZZSBJ_WALMART_REPLAY_REDIS_URL`（二选一；**没有则该函数只能读**）、可选 `SZZSBJ_WALMART_FUNCTION_NAME`（默认取 Tencent 的 `SCF_FUNCTIONNAME`）。

生成密钥（部署 AI，在主服务器上执行一次，私钥不离开服务器）：`python -c "from app.integrations.walmart.contract_signing import ContractSigner as S; from app.integrations.walmart.unified_api import reviewed_registry as R; s=S.generate(kid='szzsbj-2026-10', registry=R()); open('/etc/szzsbj/walmart-contract-signing.pem','wb').write(s.private_pem()); print(s.public_key_b64())"`，然后 `chmod 640` + `chown root:szzsbj`，输出的公钥交给云函数所有者。

新增一个 Walmart 接口的步骤：在对应 catalog 加 `Operation`（方法、路径、字段 schema、`mutating`、`response_kind`）→ `reviewed_registry()` 自动带上权限 → 写契约测试（参数校验、v3 事件往返）→ 业务模块通过 `gw.call` 使用 → 合并即生效，云函数不变。

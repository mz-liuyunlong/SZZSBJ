# Lingxing Query-Sign Authentication Official Evidence

Status: `Official Evidence Partially Captured — Owner-Approved Supplemental Protocol Evidence for Python Mock-Only Implementation`

Evidence capture date: `2026-09-11`

## 1. 文档定位

本文记录领星官方“API 接入指南”中业务接口 Query Params 鉴权与签名规则，以及 Owner 提供的已跑通参考协议所补充的最小实现证据。本文本身不授权真实 Token 请求、真实业务 API 调用、ProductLists sampling 或 RAW/DB/Redis 写入；Python mock-only implementation 的批准边界以 `PRPs/lingxing-product-list-controlled-validation.md` 为准。

官方来源：

- 领星 API 接入指南：<https://apidoc.lingxing.com/#/docs/Guidance/newInstructions>
- 接口签名生成测试入口：<https://apidoc.lingxing.com/#/docs/TestSign/signature>

本次仅只读查看官方页面；未向签名测试入口提交参数，未生成或记录签名。官方页面中的 credential、Token、签名示例值和业务数据均未复制到本文。

## 2. Evidence completeness

| 证据项 | 官方页面确认结果 | 当前判断 |
|---|---|---|
| 公共 Query Params | `access_token`、`app_key`、`timestamp`、`sign` | 已确认 |
| `app_key` 来源 | 官方将其说明为应用的 APP ID | 已确认来源；新系统配置映射尚未实现 |
| 时间窗口 | 使用实时 timestamp；固定 timestamp 生成的签名有效期为 2 分钟，不应缓存 | 已确认窗口；单位与时区未明确 |
| 签名输入 | 全部业务请求参数，加 `access_token`、`app_key`、`timestamp` | 已确认高层字段集合 |
| 排序 | 官方原文使用 `ASII` 表述 | 精确 comparator 未确认，不擅自改写为完整 ASCII canonical rule |
| 拼接 | 排序后按 `key=value`，字段间用 `&` 连接 | 已确认 |
| 空值 | 空值不参与；`null` 参与 | 已确认高层规则；`null` 的精确字符串表示未确认 |
| 集合参数 | body 中的集合需转为字符串后参与签名 | 已确认高层规则；确定性序列化格式未确认 |
| 摘要 | 32 位 MD5，结果转大写 | 已确认 |
| 二次处理 | AES/ECB/PKCS5PADDING，key 为 appId | 已确认算法、mode、padding 与 key 来源 |
| 传输编码 | `sign` 生成后需要 URL encoding | 已确认边界 |
| AES 结果输出编码 | 官方页面未说明是 Base64、hex 或其他编码 | 官方未确认；Owner 补充协议证据确认为 Base64，仅用于 mock-only 实现 |
| 可复核非密钥向量 | 页面未提供一组可安全入库的确定输入与预期最终签名 | 官方未确认；mock-only PR 必须使用 synthetic tests，真实验证仍需单独批准 |

结论：官方原始规则页面已定位，并补齐多数高层算法步骤；官方证据自身仍不完整。Owner 于 2026-09-12 接受已跑通参考协议作为补充证据，只批准 Python mock-only query-sign adapter；这不等于官方 contract 已完整，也不批准真实 API validation。

## 3. Query auth parameters

官方接入指南将以下四项作为业务接口公共 Query Params：

| 参数 | 官方语义 | 是否参与签名输入 |
|---|---|---|
| `access_token` | 由授权 Token 接口取得的访问令牌 | Yes |
| `app_key` | APP ID | Yes |
| `timestamp` | 当前请求时间戳 | Yes |
| `sign` | 根据其他签名输入生成的结果 | No；它是签名输出，生成后加入 Query Params |

指南说明公共参数不完整时请求会失败。该证据足以确认 ProductLists 需要这些 Query Params；本文不据此声称已逐一验证全部领星业务 endpoint。

### 3.1 `app_key` 与现有授权字段的关系

- 官方将 `app_key` 的来源标为应用 APP ID。
- Token 获取接口使用的表单字段名是 `appId`；两者表达同一应用身份概念，但在协议中的参数名不同。
- 新系统未来应通过单一 secret/config reference 提供该应用标识，不得让调用方自由传入；具体 settings 字段和注入方式必须在独立 implementation gate 中批准。
- `app_key` 不是 access token，也不是 app secret。

## 4. Timestamp rule

官方确认：

- 使用实时时间戳生成签名。
- 在 timestamp 固定的情况下，签名有效期为 2 分钟。
- 签名不得长期缓存或跨请求复用。
- 公共参数列表未包含 nonce。

官方文档未确认：

- timestamp 的正式单位。
- timestamp 的时区语义。
- 服务端允许的正负时钟偏差细节。

官方示例形态与十位 Unix 秒时间戳兼容，但示例形态不能替代正式单位定义。

## 5. Sign input and sorting

官方高层步骤为：

1. 收集本次请求的全部业务参数。
2. 加入 `access_token`、`app_key`、`timestamp` 三个固定输入。
3. 按官方页面所写的 `ASII` 顺序排序。
4. 以 `key=value` 形成每个片段，再以 `&` 拼接。
5. 对拼接结果执行 32 位 MD5，并将摘要转为大写。
6. 以 appId 为 key，使用 AES/ECB/PKCS5PADDING 处理大写摘要。
7. 将最终 `sign` 做 URL encoding 后放入 Query Params。

`sign` 是上述流程的输出，不参与自身排序或拼接。

### 5.1 未确认的排序细节

官方页面写作 `ASII`，未进一步定义：

- 是否明确指 ASCII byte order。
- key 比较是否区分大小写。
- 非 ASCII key 的处理。
- locale 或稳定排序要求。

官方证据自身不足以确定语言运行时排序行为。Owner 补充协议证据确认 mock-only 实现采用默认字符串顺序；Python 实现必须集中封装并用 synthetic tests 固定该行为，真实验证前仍保留互操作风险。

## 6. Serialization rule

| 数据形态 | 已确认 | 未确认 |
|---|---|---|
| scalar | 作为 `key=value` 片段参与拼接 | 数字、布尔的精确文本格式未逐项说明 |
| empty value | 不参与签名 | “空值”是否同时覆盖空字符串、空数组、空对象未逐项说明 |
| `null` | 参与签名 | 最终拼接中的精确文本表示未说明 |
| array / collection | body 中集合先转成字符串再参与签名 | 元素顺序、空格、分隔符、转义和 Unicode 规则未说明 |
| nested JSON | 属于需转字符串的集合/复杂值范畴 | object key 顺序、紧凑格式、布尔/null 表示和嵌套 canonicalization 未说明 |

GET 请求的业务参数与公共参数位于 URL；POST 请求的业务参数位于 JSON body，公共参数位于 Query Params。两类业务参数都进入签名输入。官方页面只说明集合需转为字符串，没有给出足以跨语言复现的 canonical serialization 规范。

Owner 补充协议证据确认 ProductLists mock-only 实现只排除严格空字符串 `""`，保留 `null`、`0`、`false`，并对 array/object 使用 compact JSON serialization。该规则是 Owner 批准的参考协议，不改写为官方文档事实。

## 7. Encoding and cryptographic rule

- 拼接字符串的字符编码：官方文档未确认。
- URL encoding：发生在签名结果生成后，用于传输 `sign`；不应先把所有输入做 URL encoding 再签名，除非后续官方证据另有说明。
- 摘要：32 位 MD5，uppercase。
- 二次处理：AES/ECB/PKCS5PADDING。
- AES key：appId。
- AES 结果输出编码：官方文档未确认；Owner 补充协议证据确认为 Base64，仅供 Python mock-only 实现。
- 是否还有 AES 之外的二次编码/包装：官方文档未确认。

仅凭官方文字仍无法得到确定的最终 query value；Owner 补充协议证据为 mock-only 实现补足 Base64 输出选择。Python 实现必须集中封装字符编码和密码学步骤，真实互操作性仍待后续独立 controlled validation。

## 8. Test vector status

官方指南包含签名调用示意和签名测试入口，但本次只读证据中没有一组同时满足以下条件的测试向量：

- 输入全部为不可复用占位值。
- 明确给出数组/嵌套 body 的 canonical string。
- 明确给出排序后拼接字符串。
- 明确给出 MD5 uppercase 中间值。
- 明确给出 AES 后、URL encoding 前的输出。
- 明确给出最终 expected `sign`。

本任务未向官方签名测试工具提交任何值，也未生成真实或 synthetic sign。后续 mock-only implementation 可以使用不可复用的 synthetic inputs 验证 Owner 批准的确定性行为，但不得把自行计算结果冒充官方测试向量或真实 API validation。

## 9. Security boundary

以下为项目安全边界，不是对官方平台存储行为的推断：

- 文档、测试夹具和错误信息不得包含 credential、Token、Authorization 或可复用签名值。
- `access_token`、`app_key`、`timestamp`、`sign` 等认证 Query Params 不得进入 RAW、DB、Redis、业务 envelope、日志或异常文本。
- 签名仅在单次请求边界内构造和使用，不持久化。
- client/transport 的 URL、query、request capture 与 provider error 必须先脱敏再允许记录。
- appId/app secret 必须由安全配置边界注入，上层业务不得手工拼装认证材料。

## 10. ProductLists impact

- ProductLists 的 path、JSON body、分页和 response envelope 官方证据不受本文改变。
- Owner 补充协议证据确认 `app_key = appId`、Unix 秒级 timestamp、默认字符串排序、严格空字符串排除、复杂值 compact JSON、MD5 uppercase、AES ECB + PKCS5/PKCS7、Base64 与 query encoder URL encoding。
- `PRPs/lingxing-product-list-controlled-validation.md` 已更新为 `Approved for Python Mock-Only Implementation`。
- 本批准只允许 Python backend mock-only contract、signer 与 tests；不得引入 Node/npm/JavaScript runtime，也不得另写 Token Manager。
- 官方证据的精确 comparator、字符编码、正式 timestamp 语义和 official expected-sign vector 缺口继续记录为真实互操作风险。
- 真实 ProductLists validation、P0 sampling、Token 请求和 RAW/DB/Redis 写入仍需另一项明确 Owner 授权。

## 11. 后续证据建议

优先从官方 SDK 源码、官方可下载签名实现或官方支持回复中补齐：

1. 集合与嵌套 JSON 的逐字节 canonical serialization。
2. 排序 comparator 与字符编码。
3. AES 输出编码。
4. timestamp 单位、时区与容差。
5. 一组不可复用 credential 的官方 expected-sign 测试向量。

这些官方证据缺口不再阻塞 Owner 已批准的 Python mock-only implementation，但仍阻塞真实 ProductLists validation。后续不得用 mock-only 测试结果宣称真实 API 已验证。

## 12. 明确未执行

- 未修改 backend、frontend、admin-frontend 或 old-system。
- 未请求 access token 或 refresh token。
- 未调用 ProductLists 或任何 Lingxing 业务 API。
- 未执行 P0 endpoint sampling。
- 未读取 `.env` 或业务 secret 文件。
- 未生成、记录或持久化真实 sign。
- 未写 RAW、DB 或 Redis，未连接数据库或服务器。

## 13. Owner 补充协议与批准记录

Owner approval date: `2026-09-12`

- Owner 提供的已跑通参考项目只作为协议证据，不是本项目的运行依赖或实现模板。
- 新系统后续必须用 Python 独立实现同等协议规则，并复用现有 `LingxingTokenManager`。
- 签名输入为 business body params、`access_token`、`app_key`、`timestamp`，不包含 `sign` 自身。
- key 使用默认字符串顺序；只排除严格空字符串；复杂值使用 compact JSON；MD5 hex uppercase 后，以 appId 为 key 执行 AES ECB + PKCS5/PKCS7 padding，输出 Base64，再由 query encoder URL encode。
- 允许后续 backend PR 在当前 Python 依赖没有 AES 支持时增加 `cryptography`；本 docs PR 不修改依赖。
- Python mock-only implementation 已批准；真实 ProductLists 调用、Real Business API Validation 与 P0 Sampling 均未批准。

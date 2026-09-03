# PROJECT_CONTEXT

最后核对：2026-07-31  
核对来源：本地仓库、生产只读采集（crontab -l 全量、systemd 服务清单、.env 键名清单、端口监听面、context 目录对账）——见 TASK_CHANGE_LOG 2026-07-31 context 收口条目。

> 代码上线流程（本地仓库 → 生产机：白名单 scp、备份对账、重启验收）见 context/CODE_DEPLOY_SOP.md。

## 公司背景

公司业务是 Amazon/Walmart 等跨境电商，模式为精铺小精品：大量产品开发、本土采购测品、数据筛选、利润优先、成功款复制放大。

系统目标：提单、提利润、提效率，通过 AI 自动化降低人工成本。

## 系统定位

当前系统定位为数据中台 + Admin 后台 + GPT 经营分析 + 规则引擎。

主要组成：
- `company-ai:/opt/lingxing-auto`：Admin 前后端、领星/飞书同步、DIM/FACT 构建、B 线规则、通知/报表任务。
- `company-ai:/opt/ads-ai-api`：Custom GPT 只读查询 API、`/api/ops/analyze`、利润 ETL。
- 海外中转机 `38.244.59.150`：`gpt-api.giginana.com` HTTPS 入口、Nginx 反代、SSH 反向隧道落点。
- MySQL `walmart_ai_data`：RAW/DIM/FACT/EVENT/AI 分层中台。
- 生产 systemd 服务（2026-07-31 核实运行中）：`lingxing-admin`(:3001 Admin 前后端聚合入口) / `lingxing-api-key-manager`(:3456 LLM 切换器) / `ads-ai-api` / `asin-kw-backend`(:8000) / `gpt-api-tunnel`(SSH 反向隧道)。前端另有 :3000 广告 Next.js、:8081 会议分析静态页。

## 数据分层与 AI 边界（唯一权威定义）

> 本节是全仓库关于「分层链路」与「AI 边界」的**唯一权威定义**。
> 其他任何文件（DATABASE_MAP / SYSTEM_MAP / PIPELINE_MAP / TASK_CHANGE_LOG / 交付件 / 部署提示词）
> **只允许引用本节，禁止复述**。引用写法：见 `PROJECT_CONTEXT.md`「数据分层与 AI 边界」。
> 复述必然漂移——2026-08-14 已实证：全仓曾并存**三套**链路定义（本文件、`DATABASE_MAP:401`、`README.md:10`），其中 `DATABASE_MAP` 那套还额外授权了「AI 只写 AI/BIZ 层」，与第 3 节原则第 4 条直接冲突。
> 校验命令：`bash scripts/check_layer_definition_unique.sh`

### 1. 分层链路

```text
数据源
  |
RAW                    原始留存，不加工
  |
DIM / FACT             维度与事实，客观口径
  |
BIZ                    派生 / 聚合 / 确定性规则 / 状态快照 / 规则信号
  |---------------> EVENT          确定性程序直接生成的业务事件
  |---------------> AI RESULT      模型推理产物
                        |
                  Workflow / 人工评审（Gate）
                        |
                      EVENT

HUMAN / MANUAL（权威输入通道，不是层）
  |-> 写入 DIM 的人工列（如 dim_product.manual_lifecycle_stage）
  |-> 写入 BIZ 的人工定稿表与人工列（如 biz_finance_opening_cost、各表 remark）
  |-> 评审 AI RESULT（审核态 / remark），即 Gate 的人工分支

消费侧：BIZ / EVENT / AI RESULT / HUMAN -> APP / REPORT / NOTIFY
```

要点：
1. 外部数据必须先入 RAW 留存原始数据。
2. 前端/GPT 只读 DIM/FACT/BIZ/EVENT/AI RESULT 或后端聚合 API，禁止新功能直查 RAW。
3. **AI RESULT 不得直接写 EVENT**；模型只能「提议」事件，是否落 EVENT 由确定性程序或人工评审（Gate）决定。
4. **HUMAN / MANUAL 是横切的权威输入通道，不是数据仓库层**，其权威高于一切计算层；因此保护必须落到**列级**（见第 6 节），不是层级。
5. 建表/改表前必须核对真实主键、唯一键、人工备注字段和现有写入链路。
6. 不可覆盖运营人工记录，不删除历史，不清空数据表。

### 2. 归属判定题（新功能落层，先答这一题）

> **同样的输入，输出是否必然完全相同？**
> **必然相同 -> BIZ；不必然 -> AI RESULT。**

推论（不设例外）：
- 只要调用了模型，即使 `temperature=0`，也算不确定（模型版本会变），一律进 AI RESULT。
- **自动化 != AI，规则引擎 != AI，报表 != AI，通知 != AI。** 判据是确定性，不是「这功能聪不聪明」。
- 反向同样禁止：不得为规避 AI 层的追溯/评价/Gate 要求，把本该由模型做的主观判断硬写成 if-else 塞进 BIZ。BIZ 侧规则必须带 `rule_version` 与可解释的阈值来源。
- 判定结果写进交付清单（见 CODE_DEPLOY_SOP §3.5），不靠记忆。

历史误判归属修正（2026-08-14 生产实证；**表名一律保留不改，归属以本节为准**）：

| 对象 | 现名 | 实际归属 | 依据 |
|---|---|---|---|
| 产品业务状态快照 | `dim_product_business_state` | **BIZ** | 按 `stat_date` 天粒度重算的快照，非维度粒度；`dim_` 为历史前缀，因跨 `/opt/ads-ai-api` 与外部 GPT Schema，不改表名 |
| 系统规则信号 | `biz_product_rule_signal_daily` | **BIZ** | 确定性规则引擎，无模型调用 |
| 报表运行登记 | `ai_business_report` | **BIZ / APP** | 实证 `AI_BASE_URL` 计数为 0，全链路零模型调用；`ai_` 为历史前缀 |
| 月报问题清单 | `ai_monthly_issue_item` | **BIZ** | 清单生成器产物，无模型调用 |
| 「AI财务」模块 | `aiFinanceRoutes.ts` / `aiFinanceIcpV2Routes.ts` | **BIZ** | 实证 `AI_BASE_URL` 计数为 0，确定性财务计算 |

当前全库真正的 AI RESULT 仅三张：`ai_analysis_result`（预留，0 行）、`ai_ops_log_review_item`、`ai_ops_log_review_summary`。（2026-08-14 全库列扫描实证）

### 3. AI 六条原则

1. **AI 不拥有业务事实。**
2. **AI 不定义基础业务状态。**
3. **AI 不高于人工记录。**
4. **AI 不直接修改 DIM / FACT / BIZ / HUMAN。**
5. **AI 只消费可信数据与规则结果，输出分析、建议、判断。**
6. **AI 输出必须可追溯（模型 / 提示词版本 / 输入快照）、可评价、可审计。**

### 4. AI 产物必须声明评价机制

每一类 AI 产物建表时必须声明它如何被评价，**禁止出现没有任何评价字段的 AI 表**：
- **建议型**（补货建议 / 广告优化建议 / PMC 建议）：采纳态 `pending / adopted / rejected / ignored` + 采纳人 + 采纳时间。
- **生成型**（会议摘要 / 日志评分 / 月报总结）：纠错或评分通道（如 `remark` 人工列，系统不覆盖）。
- 确实无法评价的：必须在表注释写明理由。

留存分级按「是否被采信」决定：被采纳并驱动过动作的进永久审计、不得删除（符合「不删历史」）；从未被采纳且从未被读取的可归档或清理。不做一刀切 TTL。

### 5. AI RESULT 表的强制字段与幂等

- **可追溯**：`model_name`、`prompt_version`、输入快照（如 `input_snapshot_json`）。输入快照只写不读、不可 JOIN、**不作规则真源**，仅为复现模型调用的证据。
- **幂等**：`input_hash` + **明确的唯一键**。禁止只有自增主键——`ai_analysis_result` 当前即为此缺陷（仅 `PRIMARY(analysis_id)` + 3 个普通索引），**须在 0 行期内补齐**。
- 唯一键涉及的列一律 `NOT NULL DEFAULT ''`：MySQL 唯一索引对 NULL 不去重，允许 NULL 会让 `ON DUPLICATE KEY UPDATE` 的幂等静默失效。
- 同一张表避免并存多个唯一键（多键同时冲突时 `ON DUPLICATE KEY UPDATE` 只按先命中者更新，行为不可预期）。
- 作废用标记不用删除，预留 `superseded_by`。

### 5.1 AI RESULT 幂等口径（2026-08-14 需求方拍板，长期有效）

**表定位**：`ai_analysis_result` 是「**每日 AI 结果快照**」，**不是**「每次 API 调用日志」。逐次 LLM 请求的运行日志将来另建 `company_ai_runtime` 调用日志表，**不得塞进本表**。

**「同一次 AI 结果」的定义**（12 项，顺序固定，即 `dedup_key` 的组成）：

```text
analysis_date + analysis_type + platform + store_id + item_id + msku
+ keyword(完整值) + model_name + prompt_version
+ input_hash_version + input_hash + dedup_key_version
```

数据库层面**不用大联合唯一键**，而是把这 12 项算成 `dedup_key BINARY(32)` 并对它做 UNIQUE（理由与通用规范见 5.4）。原字段宽度全部保留：`model_name VARCHAR(128)`、`prompt_version VARCHAR(64)`、`keyword VARCHAR(512)` 均不缩短、不取前缀。

- 同一天 / 同对象 / 同模型 / 同 Prompt / 同输入 → **不重复调用模型、不重复写结果**
- 换模型、换 Prompt、或输入变化 → **新起一行，旧行保留**（旧行标 `superseded_by`）
- 跨天即使输入完全一样 → **当天仍保留一行**，标 `reused_from_analysis_id`，**不重新付费调用模型**

**为什么每天必须有行**：下游永远可以直接 `WHERE analysis_date = 当天`，不需要「找 ≤ 今天的最近一条」的回溯逻辑。回溯逻辑的危害已有实证——2026-08-13 周报「未闭环问题恒为 0」的根因，正是 `signal_date == WIN_END` 精确匹配取不到当日信号；若 AI 结果按输入变化稀疏落行，每一个下游消费方都会重踩这个坑，且是静默的。

**`reused_from_analysis_id`**：`NULL` = 当天真实调用模型生成；非 `NULL` = 复用历史结论，指向被复用的 `analysis_id`。复用行的 `tokens_in/tokens_out/latency_ms` 恒为 0，真实成本记在被指向的源行。

**同一天输入变化的处理与下游读取口径（必须遵守）**：

```text
同一天输入变化 -> 可以产生新结果行
                -> 旧行 superseded_by 指向新行

下游读取「当天最终结果」固定写法：
  WHERE analysis_date = 当天
    AND superseded_by IS NULL
```

不这样写，同一天数据变化后会出现多行，下游不知道该取哪条。写入方设置 `superseded_by` 是方案 A 纪律的一部分（见 5.5）。

⚠️ **已知边界**：`superseded_by IS NULL` 的语义是「未被取代」，不是「唯一一行」。当同一天**故意并行跑多个模型或多个 Prompt 做对比**时，各自都未被取代，该条件会返回多行。此时下游必须再指定 `model_name` / `prompt_version`。若将来出现「同日多模型并行」的常态需求，再引入 `is_primary` 标志，届时须回写本节。

### 5.2 input_hash 规范化规则（Canonical JSON，v1）

**算法**：SHA-256，基于 UTF-8 编码的 Canonical JSON。

**输入范围**：只覆盖**真正送给模型的业务证据数据**。

- **包含**：任何会影响模型判断的实际业务数据。
- **不包含**：`model_name`、`prompt_version`、`request_id`、`created_at`、抓取时间等无业务意义的运行元数据。（`model_name` / `prompt_version` 已是独立键列，纳入 hash 会重复，且会让「同数据、不同模型」的横向对比做不了。）

**Canonical JSON 规则（写死）**：

1. JSON object 的 key 按字典序排序。
2. 删除无意义空白。
3. 数字统一标准格式——`1`、`1.0`、`1.00` 必须算同一个值。
4. `null` 与「字段缺失」必须区分。
5. 数组顺序：有业务顺序的保留原序；无业务顺序的按稳定业务键排序后再 hash。
6. 时间统一 ISO 8601 + 固定时区。
7. 不得加入运行时间、`trace_id` 等易变字段。
8. SHA-256 基于 UTF-8 canonical JSON。

**`input_hash_version`**（`VARCHAR(16) NOT NULL DEFAULT 'v1'`）：规范化规则一旦变更（加字段、改精度、改排序）**必须升版**，否则无法区分「规则变了」与「数据变了」，历史 hash 也不可比。

### 5.3 可复现的四个正交维度

不要让 `input_hash` 一个人承担全部「可复现」职责：

| 维度 | 载体 | 状态 |
|---|---|---|
| 输入数据版本 | `input_hash` + `input_hash_version` | 已落地 |
| Prompt 版本 | `prompt_version` | 已落地 |
| 模型版本 | `model_name` | 已落地 |
| 规则 / 知识版本 | `knowledge_version` / `context_version` | **待建**，真正用到知识库后再加 |

这样将来知识库规则改变时，即使销售数据完全没变，也能回答「AI 结论为什么变了」。

### 5.4 联合业务唯一键过宽时：一律用 dedup_key，禁止 VARCHAR 前缀（2026-08-14 需求方定稿）

> **联合业务唯一键过宽时，不使用 VARCHAR 前缀拼唯一性；统一生成 deterministic `dedup_key`，并由数据库对 `dedup_key` 做 UNIQUE。**

本条对 AI 财务 / AI PMC / 知识库等后续模块**直接复用**。

理由：InnoDB 单个索引键上限 3072 字节，业务列一多就必然触顶。用前缀拼唯一性会带来两个问题——被截断的列会**静默撞键**（不报错，只是悄悄合并成一行），且每次新增键列都要重算字节预算。改用固定 32 字节的 `dedup_key` 后，这两个问题一次性消失，原字段宽度全部保留不动。

实施要点：

- `dedup_key BINARY(32)`，对**全部业务判别项按固定顺序**做 SHA-256；唯一键只有 `UNIQUE KEY (dedup_key)` 一个。
- 优先做成 **STORED GENERATED 列**：组成规则直接显示在 `SHOW CREATE TABLE` 中，可见、不隐蔽，且杜绝应用侧写错 key。（这与否决 Trigger 不矛盾——反对的是**隐蔽**，不是反对数据库强制。）
- 所有组成列必须 `NOT NULL`。
- 查看用 `HEX(dedup_key)`，BINARY 列直接 SELECT 不可读。

**编码规则一：长度前缀，不依赖禁止字符。**

拼接一律写成 `长度:值` 依次相连（`CHAR_LENGTH(x), ':', x`）。该编码可唯一解码——读数字到 `:` 得长度 N，再读 N 个字符，循环——因此拼接必然单射，`('ab','c')` 与 `('a','bc')` 不可能撞键。

**不采用「选一个业务值不会出现的分隔符」的方案**（如 `CHAR(31)`）：那依赖一个假设，一旦将来某个 `keyword` / `model_name` 真的包含该字符就产生歧义。长度前缀不依赖任何禁止字符，才适合作为长期规范。

日期等非字符串列必须显式格式化（如 `DATE_FORMAT(d,'%Y-%m-%d')`），不依赖隐式类型转换。

**编码规则二：版本分支永不删除。**

⚠️ STORED 生成列的表达式**只有一份、对全表所有行生效**。若直接把 v1 规则改写成 v2 规则，`ALTER` 会用新表达式**重算全表历史行**，历史结果的身份被追溯性重新解释——把版本号放进 hash 输入**并不能**阻止这件事。因此表达式必须按版本分支：

```sql
CASE dedup_key_version
  WHEN 'v1' THEN SHA256(v1 规则)
  WHEN 'v2' THEN SHA256(v2 规则)   -- 将来新增
  ELSE NULL
END
```

- **旧版本分支一个字符都不许改、不许删**，包括格式化、把 `CHAR_LENGTH` 换成 `LENGTH` 这类「无害重构」——都会静默重算历史行。
- `ELSE NULL` 必须配 `dedup_key ... NOT NULL`，构成响亮失败：出现未知版本时 INSERT 直接报错。若允许写入 NULL，**NULL 在 UNIQUE 索引中不参与去重**，会造成静默重复。
- **已落行的 `dedup_key_version` 不得 UPDATE**，否则该行身份会被就地改写。
- `dedup_key_version` 与 `input_hash_version` 是两个独立版本：前者管**组成项列表**，后者管**输入数据的规范化规则**。

### 5.5 已 adopted 行的防覆盖：方案 A（写入方纪律，不做 Trigger）

写入方在每次写入前：

```text
查 input_hash + model_name + prompt_version
  相同 -> 直接复用，不重新调用模型（当天落行并标 reused_from_analysis_id）
  不同 -> INSERT 新结果，并把旧结果标记 superseded_by
```

**不使用数据库 Trigger**：Trigger 太隐蔽，日后排查「AI 为什么写不进去」成本很高。


### 6. 写入者必须可辨识

`created_by` / `updated_by` 目前混装三类主体（2026-08-14 实证：`刘华媛`、`unmatchedOwnerNotify`、`财务Excel回传20260813` 同列并存），导致无法用一句 SQL 回答「这一行是人写的还是程序写的」。
**而「AI 不高于人工记录」的前提，就是能分辨哪些是人工记录。**
新表必须带 `writer_type`（`human` / `program` / `import` / `ai`）；存量表按需补列，**不改既有取值语义**。

### 7. 权限按服务授权，不按表名前缀

账号按**服务**授权，**禁止按表名前缀授权**——表名前缀已被证明不可靠（`ai_business_report` 并非 AI 表），且 MySQL `GRANT` 本就不支持表名通配。
已有先例：`ads_ai_reader` 只读 `walmart_ai_data`、`ads_etl_writer` 限权写 `fact_profit_daily`。
**任何新增 AI 写入模块，上线前必须使用受限账号**（读 DIM/FACT/BIZ、只写指定 AI RESULT 表）；EVENT 写权限仅授予 Gate 程序。此条是前置条件，不是待办事项。

## 开发铁律

1. 改前核查代码、真实表结构，禁止臆测字段/接口/环境变量。
2. 禁删原有功能；无明确指令不得改动 crontab、systemd timer、生产定时任务。
3. 密钥统一读环境变量，严禁硬编码；context 文档只写路径/变量名，不写值。
4. 新功能隔离开发，最小改动旧页面。
5. 高风险变更先标注风险 + 替代方案。
6. 改动必须配套测试命令 + 验收标准。
7. 中文逻辑写入 UTF-8 文件；终端命令尽量短、ASCII、可复制。
8. 安全验收纪律与“终端命令尽量短、ASCII、可复制”并列为通用执行红线：验收输出不得打印密钥、token、cookie、Authorization、`.env` 明文值；涉及敏感配置时，只允许回传 `has_xxx=true/false`、`config_exists=true/false`、`service active/inactive`、接口返回状态、字段是否命中；如必须定位密钥类问题，只能脱敏展示（例如前4后4，中间 `****`）；执行 `curl`、`grep`、`cat .env`、systemd/环境变量检查时，默认不得把敏感值原样回传。

- **通报测试铁律（2026-08-05）**：所有飞书通报（新增/改文案）上线前必须先 `--test-send` 发测试群、需求方确认后才允许真实发送；详见 CODE_DEPLOY_SOP 同名节。

## 已确认架构决策

- 利润口径 = 运营端毛利，已扣广告费，不含退款。
- `fact_profit_daily.net_profit` 当前全为默认 0，非真实财务净利，不得用于财务净利分析。
- GPT 与页面必须“一处计算，两处读取”：B 线状态统一由 `dim_product_business_state` 输出，订单利润 Beta 与 `/api/ops/analyze` 读取同一状态表。
- 境内服务器对 OpenAI 出口不可达，Custom GPT 必须走海外中转 + SSH 反向隧道。
- `/api/ops/analyze` 认证使用 Bearer，Token 指针：`/opt/ads-ai-api/.env` 的 `ADS_AI_API_TOKEN`。
- ads-ai-api 数据库只读账号用途：`ads_ai_reader` 读 `walmart_ai_data`；利润 ETL 写账号用途：`ads_etl_writer` 限权写 `fact_profit_daily`；lingxing-auto 写账号用途：DIM/FACT/RAW 同步写入。只记录用途，不记录密码。
- `raw_feishu_table.sheet_id='<REDACTED_FEISHU_SHEET_ID>'` 是订单利润 Beta 的 RAW 快照，不是飞书真实 sheet。
- 2026-07-11 起，订单利润 Beta 的负责人筛选口径固定为“按当前 `dim_product.owner` 筛商品，保留该商品在查询窗口内的全部 RAW 行做聚合”；禁止按 `raw_feishu_table.row_json.负责人` 直接预聚合过滤，否则会把完整窗口错误截成历史负责人有值的局部窗口。
- 2026-07-11 起，花名册唯一来源固定为飞书公司通讯录：在册=`active`，不在册=`left`；旧固定群只允许做诊断对照，不得用于在职/离职判断。
- `refreshFeishuMembers.ts` 保留无姓名硬安全阀：只要通讯录成员姓名无法解析到 0，任务即 `exit 2` 且零写入，不允许带空名落库。
- `POST /api/feishu-raw-sales/product-management/update-owner` 仅允许把商品分配给 `dim_feishu_member.employment_status='active'` 的人员；离职/不在册人员必须 400 拦截。
- 离职负责人保留规则固定为：标记 `left` 后保留负责人 7 天，第 8 天由 `clearDepartedOwners.ts --execute` 自动清空；若运营已人工改派，则后续自动任务不得再次清空。
- `dim_feishu_member.name` 与 `dim_product.owner` 当前生产排序规则不同，凡跨表按姓名比较的 SQL，必须显式使用 `COLLATE utf8mb4_unicode_ci`，避免通报/清空链路出现 `Illegal mix of collations`。
- 飞书 `<REDACTED_FEISHU_SHEET_ID>` 已降级为 RAW 历史镜像/初始化备份/排查对账，不再作为负责人、WFS 配送费、产品状态、缺负责人通知的主业务口径。
- B 线第 1 期已落地 `dim_product_business_state`；20:30 每日 crontab 已于 2026-07-07 上线，2026-07-08 巡检 `MAX(stat_date)=2026-07-05`，与 FACT 同步。
- 2026-07-09 已完成经营指标窗口“近30天 -> 近14天”的跨仓库口径文案同步：`/opt/ads-ai-api/main.py` 的 `/api/ops/analyze -> summary.state_note` 已从“近30天口径快照”改为“近14天口径快照”，与 `buildProductBusinessState.ts`、`buildProductRuleSignalsDaily.ts`、运营提醒展示、GPT Builder Instructions 保持一致。
- 经营指标窗口变更的强制同步清单固定为 4 处：`/opt/lingxing-auto/src/buildProductBusinessState.ts`、`/opt/lingxing-auto/src/buildProductRuleSignalsDaily.ts`、`/opt/ads-ai-api/main.py`、GPT Builder Instructions。以后只要调整 `METRICS_WINDOW_DAYS`，必须逐项复核，避免计算口径、规则口径、API 文案、GPT Instructions 不一致。
- 2026-07-09 `/api/ops/analyze` 已升级到 Phase 2 v6：A线分类默认排除 `archived`，响应新增 `api_version='v6'`，并在请求带 `item_id/msku` 时返回顶层 `queried_product_states`。若状态表无当日快照，则兜底查 `dim_product` 返回最小状态结构；归档品会显式标记 `archived=true` 并附说明 note，而不是静默消失或报 500。
- 2026-08-02 单品现金利润模块口径定稿（需求方拍板）：模块=收入/支出分开累计不做月度固定费摊派；**单品现金利润 = 实际收入合计 − 实际支出合计**（本模块最大价值数据，新品前期只有支出为负属正常）；**投产比 = 收入合计 ÷ 支出合计**（现金口径总投产比，不是广告ROAS）；"当前库存成本"=库存资金占用列的定名（含入库后成本口径）；"账期"列必须展示到具体更新日期时间，不能只写月份。字段口径说明必须做进表头悬停 ⓘ 图标（对齐领星"实际总量ⓘ"交互），见 UI_STANDARDS。
- 2026-08-02 广告费数据源定稿（真账单核验，探针6~10）：按品广告费唯一口径=`fact_ads_keyword_daily.ad_spend`；领星结算报表广告字段（platformAdvertisingFee 等）是摊派/近零值，禁止使用；手动型活动数据已验证与 Walmart Connect 发票分毫不差；自动型活动缺口根因与修法已定位（campaignType 放宽），改造涉及生产定时任务，待需求方拍板后单独立项；SBV 不做属预期。详见 DATABASE_MAP `fact_ads_keyword_daily` 特别说明。
- 2026-08-02 自动广告花费口径定稿（需求方拍板，探针11/12证据）：自动广告**花费合计=API商品级(reportAdItemSpList)为准**（发票100%验证、ITEMID原生归属）；CSV路(walmart_auto_csv)只含搜索位花费(~71%且各品比例离散)，角色=搜索词明细+14天出单归因刷新，**不计入广告费合计**。
- 2026-08-03 按品广告费落库结论（探针13，重大简化）：API商品级数据**早已在 `fact_ads_product_daily` 每日落库**（syncLingxingDailyToDb 第4步，manual+auto，至少04-01起），发票级审计100%通过、7月全覆盖——**keyword表V3改造正式取消，零生产改动**。按ItemID广告费统一读 `fact_ads_product_daily`；`fact_ads_keyword_daily`（含CSV路）仅限搜索词分析，禁止金额汇总。
- 2026-08-03 AI财务模块成本口径（需求方拍板）：采购成本/头程按"采购单 order_time 记账+每周复核次月末收口 + 发货单真实头程"自算；**历史遗留数据缺失时从领星批次成本接口 getBatchDetailList 补**（与08-01财务双口径立规的批次成本口径衔接）。

- 2026-08-18 **时间日界统一口径定稿（长期有效，需求方拍板）**：全系统业务数据的"日"一律以**美西时间（America/Los_Angeles，自动含夏令时PDT/UTC-7与冬令时PST/UTC-8切换）**为日界，与 saleStat 族（fact_sales_daily/fact_profit_daily 业务日）同源对齐。规则：①任何新数据链的归因日期列必须按美西日换算（禁止北京日界/UTC日界混入，实证教训：促销折扣曾按北京日归因，与销售额美西日错位产生行级负净销售额，YC00097-1C 08-11 案例）；②时区换算一律用 IANA 时区 America/Los_Angeles 做（代码侧 Intl/tz库，禁止硬编码固定偏移-7或-8，否则冬夏令时切换出错）；③RAW 层原文时间戳保持接口原样留存不改；换算只发生在提取列/FACT归因列；④接口返回时间的时区必须先探测定性（对照领星界面）再定换算公式，禁臆测。
- 2026-08-10 **销量统一口径定稿（长期有效）**：权威=saleStat 族（fact_sales_daily→<REDACTED_FEISHU_SHEET_ID>明细派生；订单利润RAW→fact_profit_daily ETL），族内日度必须完全相等【零容差】，P7哨兵每日校验；fact_mp_sales_channel_daily 降级为 WFS/非WFS 判定专用（v5豁免依赖），禁止用于销量金额统计对比；两源日期归因差为源特性非缺陷。详见 DATABASE_MAP 同名节。
- 2026-08-05 **归档产品到货提醒卡（长期机制）**：归档且 WFS>5（ARCHIVED_RESTOCK_MIN_WFS）每日 09:40 发交互卡（恢复在售/继续归档），keep=暂停提醒、库存超上次确认基线自动复提；事件表 event_archived_restock_alert（uq_ar_item），回调 biz=archived_restock。详见 SYSTEM_MAP/PIPELINE_MAP。

## 当前风险基线

- 【2026-07-31 复核】端口暴露面：`3001/3456/8081` 监听 `0.0.0.0`，`3000` 监听 `*`；服务器内 iptables 无针对性限制；nginx 大量 `proxy_pass 127.0.0.1:3001`（主站 :80 反代）。与 07-09 相比的变化：2026-07-25 起全站统一登录（app_session JWT）已上线，3001 直连不再是"无认证"，:3456 亦已于 07-31 并入 SSO（仅放行陈佳聪）；剩余风险=端口直连暴露面大 + 腾讯云安全组入站规则未核实（服务器内查不到，需控制台确认）。处置为单独立项：优先安全组收紧 3001/3456/8081 到可信来源；未经用户拍板不得动网络配置。
- `dim_product_business_state` 每日 20:30 crontab 已上线；2026-07-08 巡检最大 `stat_date=2026-07-05`，与 FACT 同步。20:15/20:30 两任务日志尚无 cron 触发记录，2026-07-08 晚必须复查日志是否正常生成。
- 09:30 `sync:feishu-item-owner` cron 已按退役口径于 2026-07-07 注释停用（当日曾短暂恢复后再停）；脚本保留且为 RAW-only，不写 `dim_product` / `dim_product_owner` / `dim_product_cost_config`。
- 2026-07-09 已按最小改动更新 `unmatchedOwnerNotify`：仅调整通知格式（删除按店铺分组，正文改为编号 `MSKU + ItemID` 列表），`fetchUnmatchedProducts` / `sendToFeishuBot` / `main` / SQL 查询逻辑保持不变；cron 已从 `10:00` 调整为 `09:10`。缺负责人判定口径未变：`dim_product.owner` 为空或 `未分配`，且 `product_management_status='active'`。
- 2026-07-11 花名册正式同步后，`dim_feishu_member` 当前状态分布为 `active=29 / left=2 / total=31`；新增在册 `蔡皓煜`，离职 `肖扬`、`苏逸雅`。两位离职人员当前 Walmart 非归档商品数均为 0。
- `dim_product.product_name` 已于 2026-07-08 通过领星本地产品详情回填 1354 条；仍未命中的 187 条继续依赖 `item_name/sku/msku/item_id` fallback。`dim_product.store_name` 生产当前仍为空。
- `manual_lifecycle_*` 只允许产品管理 `update-lifecycle` 接口写入；同步脚本、ETL、状态表任务只能读取或透出，不得覆盖人工生命周期。2026-07-08 起白名单按产品类型分流：CS 测品仅允许 `测品期/测品结束/空值`，常规产品仅允许 `新品期/上升期/稳定期/清货期/空值`。`manual_lifecycle_system_snapshot` 记录人工确认时的系统生命周期快照，仅由 `update-lifecycle` 后端写入或清空，用于蓝/红高亮基线。
- CS 测品系统生命周期为库存两态规则：`msku LIKE 'CS%'`；按 `platform + store_id + item_id + msku` 取每个商品自己的 `fact_inventory_daily.MAX(snapshot_date)` 上 `available_stock`，`available_stock > 0` 为 `测品期`，`available_stock = 0` 或 NULL 为 `测品结束`，不再允许 NULL。CS Beta 的 `non_wfs_available_stock` 继续用于测品过程分析；CS 生命周期是管理视角有货/没货，两者并存不混用。
- 2026-07-11 起，CS 测品不使用毛利或 A/B/C/D 利润等级评价。CS 判断依据固定为：生命周期、首次广告日期、销量、广告花费、广告销售额、ACOS、库存、`problem_tags`、`rule_signals`、`suggested_action`。
- GPT 查询 CS 时必须显式传 `product_type=cs`。其中 `cs_summary` 表示完整统计，`cs_attention_products` 表示默认关注范围明细（全部测品期 + 首次广告日期近30天内的测品结束产品）。
- CS 的 `first_ad_date` 直接复用 `launch_date`；`launch_date` 由 20:15 `derive-launch-date` 任务维护，CS 分支按首次广告花费日推导。该复用决策基于只读核实：按真实 item 级关联时，CS `launch_date` 与广告事实首花费日一致率约 `95.47%`。
- GPT 消费接口响应体积必须按 **UTF-8 字节数** 计算，统一红线 `50KB`；回归样例优先使用存在性检查，不使用容易随维度波动的精确行数。
- `fact_profit_daily` 当前成本字段未完整配置，常规产品 `gross_profit` 仍属于现有运营粗口径；后续如成本字段补齐，必须重新评估常规产品利润等级与毛利口径。CS 视角已于 v7.3.1 主动隐藏毛利字段，避免 GPT 用粗口径毛利评价测品。
- 汇总类页面的负责人筛选规则固定为：按当前 `dim_product.owner` 筛商品并保留完整查询窗口；如需“历史负责人归因”，必须单独口径、单独实现，不得与订单利润 / GPT 这类窗口汇总口径混用。
- `fact_ads_product_daily.msku` 生产当前全空，广告商品事实应按 item 级解释，不能强行当 MSKU 级。
- 2026-07-11 起，所有读取 MySQL `DATE/DATETIME` 的 Node 定时任务默认必须优先使用 `mysql2 dateStrings:true`，或在写库前做 `YYYY-MM-DD` 正则校验；禁止继续使用 `String(value).slice(0, 10)` 直接截日期。
- `deriveLaunchDate.ts` 当前固定约束：`--execute` 与 `--confirm-write` 等价；只允许更新 `launch_date IS NULL`；候选日期必须先通过 `YYYY-MM-DD` 正则校验，非法日期仅计数告警，不得写库。
- 2026-07-11 起，飞书通报新约束固定为：统一走 `src/feishuNotify.ts`；接收人通过环境变量 + 花名册解析得到；禁止在业务脚本里硬编码 `open_id`、`chat_id`、webhook。
- 业绩日报 webhook 已从 `performanceSummaryReport.ts` 硬编码迁移到 `.env` 的 `FEISHU_PERF_WEBHOOK_URL`；只允许记录 `has_xxx` / 路径指针，禁止在任何验收输出或 context 中记录真实值。
- 通报 dry-run 必须满足零发送、零写入、零真实 ID 暴露。当前验收基线要求输出中不得出现 `tenant_access_token`、`app_secret`、`open_id`、`union_id`、`ou_` 人员 ID、`oc_` 群 ID、完整 webhook URL。
- 自动广告导入检查当前生产口径为“双模式日期列探测”：先做前 5 行表头探测，失败后回退到位置/数据形态识别；当前 `sheet=1HeaCn` 实测走 `positional`，日期列固定为第 3 列（0-based=2）。
- 自动广告导入检查在 dry-run 下禁止解析真实花名册、禁止取 tenant token、禁止构造真实接收端 ID；仅允许输出安全预览与模拟 SendResult。
- `unmatchedOwnerNotify.ts` 本轮零修改；当前生产 SHA256 固定为 `c41f220559f13dbb32f2f8cfed914ef49cb409c0eef5d2e4b8f6d2af10de46b7`，后续相关批次若未明确要求，不得顺手改动。
- 2026-07-11 “批B测试模式”已完成正式验收闭环：四条通报均新增 `--test-send` 旁路，且测试成功判定必须同时满足 `exit 0` 和输出 `NOTIFY_TEST_SENT=1`，两项缺一不可。
- 批B测试模式正式闭环还必须满足人工实收门禁：即使 runner 已通过 4/4，也必须由需求方确认测试群实际收到消息、标题与内容正确、未误发生产目标、且无异常重复；只有自动验收和人工实收都通过，才允许在 context 中标记为正式闭环。
- 公共生产凭证与专用测试凭证的代码路径已隔离：`getTenantToken()` 只读公共 `FEISHU_APP_ID/SECRET`；`getNotifyTenantToken()` 才读取 `FEISHU_NOTIFY_APP_ID/SECRET`，且专用变量必须成对配置。
- 当前测试通道通过 `getNotifyTenantToken()` 工作，在 `FEISHU_NOTIFY_APP_ID/SECRET` 均未配置时按代码设计回退现有公共飞书应用；本次 2026-07-11 测试群实发即走该回退路径并已验收通过。
- `FEISHU_NOTIFY_APP_ID` 与 `FEISHU_NOTIFY_APP_SECRET` 必须始终“同时存在”或“同时缺失”；禁止只配置其中一项。独立通报应用后续需要单独立项：新建独立飞书应用、配置独立 App ID/Secret、单独完成权限、群机器人和生产发送验收，不能表述为“只差补一个 Secret”。
- `FEISHU_NOTIFY_MIN_INTERVAL_MS` 当前仅是单进程内串行节流：同一 Node 进程内有效，不同 cron 进程之间仍没有统一发送队列或跨进程节流/分布式锁；后续若全部生产通报迁移 App 机器人，需单独建设统一队列。
- 批B测试模式的正式验收证据归档为：`/opt/lingxing-auto/logs/notify_test_all_20260711_221950.log`。长期证据统一引用该永久路径，不再引用临时路径。
- 本轮及批B测试模式闭环均未修改任何生产 cron，也未改变现有生产接收端；不带 `--test-send` 的自然任务仍应保持批B第5版行为。
- 运营日志 Tab（Task H-Stage2.1~3.2）已从只读演进到“仅运营日志列可写”：`system_base && is_locked=0` 行可通过 `POST /api/feishu-raw-sales/operation-log/update` 更新 `log_content`，`updated_by='admin_ui'`；`feishu_migration` 与锁定行只读。20:50 `build:operation-log-base` 不碰 `log_content`，人工写入与系统基础刷新不冲突。
- `biz_event` 现 **834 行**（2026-07-27 生产核实；此前记「0 行」已过期）；`ai_analysis_result` 仍 0 行。有表不代表 EVENT/AI 层都已有业务产物。
- 仍有备份/旧表：`backup_dim_product_before_owner_fix_20260703072959`、`backup_dim_product_owner_before_owner_fix_20260703072959`、`dim_product_cost_config_cs_backup_20260707`、`walmart_ad_keyword_rows`、`walmart_ad_tasks`、`tasks` 等，清理前必须确认用途。

## 生产任务现状摘要（2026-07-31 快照）

- crontab：约 49 条 active 任务（另有 daily-operation-log-base、sync:feishu-item-owner 等已停用注释保留；`gptKwOwnerSummary` 为 7-28 一次性任务已过期未清）。逐行权威清单见 PIPELINE_MAP `Active cron snapshot as of 2026-07-31` 节。
- 链路族：领星/店铺/成员/广告词/订单利润/产品成本/利润ETL 主数据链；DIM/FACT 构建链（20:15~20:55）；通知报表链（不出单/缺负责人/低毛利/绩效/清货三卡/到货/订单下滑/CS测品/运营不动作/月度规划催办/月度规划未填扣分09:25·8号起/清货无目标特批09:35·8号起）；周报确认+排队生成链；月报链(4日06:00生成→09:00推送)；考勤链（00:45 同步、09:50 缺卡推送、21:50 缺卡重发）；AI 周评（周四 23:00 aiOpsLogReview）。
- AI 层 LLM 出口：`.env` AI_BASE_URL/AI_MODEL/AI_API_KEY 单一出口，由 :3456 LLM 切换器管理多套配置；2026-07-31 因 yunwu.ai 出海外超时已切换 openlux（周报/智能PMC/AI周评共用此出口）。

## 当前待办

### 2026-08-10 已拍板待执行队列（需求方点名勿忘）
1. ~~<REDACTED_FEISHU_SHEET_ID> 明细 6/1–6/26 重生成~~（✅2026-08-10 已完成:6月30天/24137行恢复,前端复验537行;6/15=1032行系零值广告行扩底座属正常）。
2. ~~P7 数据完整性哨兵~~（✅2026-08-10 已上线:cron 20:15主检/9-23整点提醒/周一周报;首捕msku空串已闭环）：每日20:15;检查①三表恒等T-2~T-4零容差②<REDACTED_FEISHU_SHEET_ID>行数≥600③当日库存快照存在(当天必救)④msku空串增量⑤渠道表仅查有无。仅通报陈佳聪;异常才发+周一09:00周汇总;报警附标准修复命令;v1不自动写库;连续2天升级标注;先测试群。
3. ~~ai_monthly_issue_item 唯一键+生成器upsert~~（✅2026-08-11 已上线：uq_issue(plan_month,platform,store_id,item_id)+生成器 ON DUPLICATE KEY UPDATE+收尾DELETE同月残留行,假月2099-01双插实测通过,真实分布不变670/465；欠9/4 06:00 cron首跑终验:REPORT_ID/ISSUE_ROWS/PURGED_STALE+2026-09无重复）。
4. **订单利润V2**（已批方案:新Tab并行,读fact_profit_daily,销量取extra_json.sales_qty;COUNT/合计/数据页一次查询;新旧对账1-2周后需求方拍板下线旧Beta｜方案终稿=交付件/订单利润V2_完整方案_20260814.md(退货数据链/促销折扣列/仓储费日摊,四批计划)；批1退货链✅2026-08-18上线(60天1889单$36945守恒+幂等实证);批2折扣链+仓储日摊✅2026-08-18上线(YC00095-1A对照过/仓储守恒31413.49);批3/批4/整改9轮✅2026-08-19全部上线收官(广告口径升级SP+SB+SV+SEM/美西日界统一/店铺id修复/空msku清理/多选筛选/列配置/币种切换/哨兵第⑦守恒/帮助文/cron/对账报告reportV2Reconcile)。**当前=对账观察期(至2026-09-01前后)**,观察期值守清单:①每晚20:15哨兵七项checks_ok(第⑦盯V2三链守恒,首验2026-08-19晚);②每日cron首跑日志核验(refund_sync.log 07:50/promo_discount_sync.log 08:05,首验2026-08-19);③对账报告按需手跑 npx ts-node src/reportV2Reconcile.ts(重点看恒等自检差≈0/广告增量/V2利润vs Beta毛利差值可解释);④领星三方销售额抽查(saleStat同源逐分一致);⑤下次仓储CSV导入验证daily_expand_triggered钩子;⑥期满需求方拍板下线旧Beta→随后排<REDACTED_FEISHU_SHEET_ID>命名治理B。
5. **<REDACTED_FEISHU_SHEET_ID>命名治理B**（2026-08-10拍板,与V2同排期做）：sheet_id '<REDACTED_FEISHU_SHEET_ID>'→语义名(如daily_sales_detail)迁移+历史行UPDATE+全部读写方同步改;raw_feishu_table等飞书遗产命名一并评估;迁移前文档一律"中文语义名(原标识)"双写。
6. ~~领星工单~~（2026-08-10 需求方拍板去掉，不提工单）：负责人权威源维持 dim_product.owner，运营暂不在领星维护负责人。
7. 分渠道(WFS/自发货)利润拆解：2026-08-10 需求方拍板【不考虑】，不列入财务系统设计输入。
8. P7 哨兵通报人=陈佳聪（需求方指定），上线走通报测试铁律。
12. **智能PMC·WFS费用异常跟进版块**（2026-08-11 立项,Demo v0.5 已确认,进入开发）：判定=实收WFS配送费>成本配置人工值即多收【全部订单口径】,预估追回=单件差×累计订单;流程=每日检测立案(待运营确认)→飞书卡片通知负责人→需要跟进(Case号必填可多个)→跟进中/无需跟进(填理由)→林翔审批(同意关闭/驳回强制跟进,放弃跟进同样送审)→完成按钮(填索赔/追回金额)闭环;跟进日志=可编辑保存文本区(每周必写,系统每周检查未更新扣绩效,写法四要素:时间/第几次/做了什么/下一步);默认排序=跟进中最前按立案时间升序;帮助中心=简版SOP(五步+Case英文模板+日志示例,交付件已存);已验证案例=2026-08-06 GTIN 00465195807511 追回$544.16。前置探测:订单利润RAW是否有实收配送费字段(决定检测链路怎么搭)。
10. ~~P7哨兵 sales_family_eq 三表全空漏报洞~~（✅2026-08-11 已修上线：verifyCheck 加销量表 rows>0 守卫，销量表0行直接报"疑三源全空"；20:15终验✅ checks_ok=8/anomalies=0）。
11. ~~dim_product_business_state 历史洞 07-01/02/04~~（✅2026-08-11 已回填闭环：builder --date 重建各756行,extra_json.backfill='sentinel_20260811_approx' 标注；756 vs 邻日1502 系当前维表回算的已知边界,需求方拍板【接受,不再追补】,现已归档品该三日仍无行走兜底。防再发：P7 新增第⑥检查 business_state_snapshot,目标日 T-3——注意 20:30 构建器写 stat_date=最新可用业务日(当天T-2),20:15 时点最新只能到 T-3,T-1/T-2 都会误报）。
9. **245条msku空行定性**（2026-08-10新增）：与同日正常msku行并存的历史空行,需判定 重复计数(删) vs 双listing拆分(留);或与6月销量表>订单利润RAW差额有关。备份已存 _bak/fact_sales_blank_msku_bak_20260810_231416.sql。



（2026-07-31 刷新）
1. `3001/3456/8081` 安全组收敛：待用户在腾讯云控制台核实入站规则后单独立项执行（高风险运维项）。
2. context 收口执行：生产 TASK_CHANGE_LOG 部署侧独有条目并回 Mac 仓库 → 单向同步生产为只读镜像。
3. README.md 重写（当前仍是早期"领星 API 连接测试"描述，误导接手人）。
4. `.bak` 历史备份隔离至 `_bak/`（先隔离不删）+ 检索规范排除 `*.bak*`。
5. 07-11 遗留观察项（B线第5期通报、v8 配额观察等）状态未逐一复核，见历史 TASK_CHANGE_LOG，如仍需推进单独立项。
6. （2026-08-02 新增）`syncManualAdKeywordDaily.ts` 自动广告补全改造：campaignType 放宽为 manual+auto（探针10已验证修法正确），**动生产定时任务，需需求方明确同意后实施**；实施方案必须同时回答两个设计题：①与 `walmart_auto_csv` 人工CSV导入这路的防重/去留（涉及翁骏在维护的人工流程与17:25监控cron）；②ITEM_PATH 商品粒度行落进 keyword 粒度表的 keyword/keyword_type/source_type 占位口径（source_type 隔离可不改表结构）。
   ↳（2026-08-02 更新）两个设计题已随探针11/12+需求方拍板全部解决：①CSV路保留不停（搜索词明细+14天归因价值），花费合计排除 walmart_auto_csv、以API商品级新来源为准，无重复计数；②占位口径=keyword固定占位符+独立source_type（不改表结构，唯一键天然隔离）。最终状态：**2026-08-03 正式取消**——探针13证实所需数据早已在 `fact_ads_product_daily` 每日落库（发票级审计100%通过），无需任何生产改动。本条留档仅作调查过程记录。
7. （2026-08-03 更新）**AI财务模块**（需求方定名）：新建独立模块"AI财务"，首个 tab="单品现金利润"（HTML DEMO 第3版已交付在审）。数据源就绪度：收入侧结算接口✅、广告费=fact_ads_product_daily✅（探针13审计通过）、成本口径已拍板（采购单+发货单自算，历史缺失补批次成本）；**2026-08-03 全部数据源闭环**：①结算数据实为月度账期（settlementDate粒度=月，探针14b），同步设计=每日重拉当月+前2月滚动窗口；②零销量SKU仓储费从沃尔玛后台「仓储」报告CSV取（SKU级真实账单，零销量样本全命中，SKU加总=店铺总额分毫不差）。完整数据与计算逻辑已定稿于 `docs/AI财务_单品现金利润_数据与计算逻辑定稿_v1.md`，**待需求方逐节确认后开工（前后端并行，需求方定）**；开工前不写任何生产代码。

## context 使用规约

每个新任务开工前必须先读：
1. `/opt/lingxing-auto/context/PROJECT_CONTEXT.md`
2. `/opt/lingxing-auto/context/DATABASE_MAP.md`
3. `/opt/lingxing-auto/context/SYSTEM_MAP.md`
4. `/opt/lingxing-auto/context/PIPELINE_MAP.md`

执行规则：
- 发现 context 与真实代码/表结构/生产配置不符，以真实扫描为准，并当场修订对应 MAP。
- 每个任务完工必须更新 `/opt/lingxing-auto/context/TASK_CHANGE_LOG.md`，并同步修订涉及的 MAP 章节。
- context 不替代实扫；它用于降低探测成本，不能作为臆测字段和接口的理由。
- 任何涉及 `dim_product`、`fact_*`、`dim_product_business_state` 写入逻辑的新部署（含 `syncLingxingDailyToDb` 草稿），开工前必读 `DATABASE_MAP.md` 对应表条目的口径与护栏；部署清单中必须包含“已核对字段口径”确认项。

## context 单写入方制度（2026-07-31 定稿，长期有效）

- **文本真源 = Mac git 仓库 `context/`**；生产 `/opt/lingxing-auto/context/` 为只读镜像。
- **事实真源 = 生产运行态**（crontab -l、已部署文件 md5、真实表结构、.env 键名）；context 与生产不符时以生产实扫为准并回改 Mac 版。
- 写入规则：context 只在 Mac 仓库编写与提交；部署 AI 部署后**单向覆盖同步** Mac→生产，不得直接编辑生产 context；部署侧只回传事实（md5/验收/crontab），落档动作归开发侧。
- 未部署的功能不得在 context 写"已上线"口径；部署验收通过后才可标记闭环。
- 任何新增模块 / cron / 表结构 / 页面入口，必须同步改至少一个主 MAP（SYSTEM/DATABASE/PIPELINE），**未改 MAP 的任务不算闭环**。
- 分叉历史：2026-07-31 收口前生产与 Mac 两侧并行书写导致五份主文档分叉；生产独有部署条目（07-27/07-28 internal-readonly 修复、API 文档页上线等）已并回，此后不再允许双写。

## 敏感信息红线

禁止在 context 写入 Token、数据库密码、Cookie、SSH 私钥、Webhook URL 的真实值。

验收输出同样禁止回传以上真实值。涉及密钥/配置的执行结果，默认只汇报：
- `has_xxx=true/false`
- `config_exists=true/false`
- `service active/inactive`
- 接口返回状态
- 字段是否命中

如必须定位密钥相关问题，只允许脱敏展示，例如前4后4，中间 `****`；不得原样打印 `Authorization`、Cookie、Token、`.env` 明文值。

允许写指针：
- ads-ai-api Token：`/opt/ads-ai-api/.env` -> `ADS_AI_API_TOKEN`
- ads-ai-api DB 只读连接：`/opt/ads-ai-api/.env` -> `MYSQL_*`
- profit ETL 写账号：`/opt/ads-ai-api/scripts/etl.env` -> `ETL_MYSQL_*`
- lingxing-auto DB/AI/飞书/领星配置：`/opt/lingxing-auto/.env` -> 对应环境变量
- SSH 隧道私钥：`company-ai:/root/.ssh/gpt_api_tunnel`

每日销售明细负责人筛选口径：快照行内负责人优先；仅行内为空时按 dim_product 同店铺同 item 当前负责人兜底。<REDACTED_FEISHU_SHEET_ID> 自 2026-07-13 起退出“每日销售明细 /data 负责人筛选判定链路”。
feishuRawSalesRoutes.ts 为高频改动文件：部署必须基于当前生产完整 SHA，采用最小锚点补丁或基于最新生产文件生成交付；禁止使用非当前生产基线整文件覆盖。

## 方案B运行规范

- `backfillDailyChain` 生产执行必须显式传入 `--deadline`；当前 cron 使用 `--execute --deadline=19:10`，手动真实试跑曾使用单独批准的临时 deadline。
- `backfillDailyChain` 的单实例锁、cleanup 锁、unsafe 活动子进程标记位于 `/tmp/lingxing-backfill-daily-chain.lock*`。任何 unsafe 标记、cleanup 锁残留、锁释放失败、`childExitUnconfirmed=true`、`dirtyDates` 非空或 `status!=success` 都按 fail-closed 处理，必须人工核查日志、进程、锁文件、数据快照和 `SUMMARY_JSON`，不得直接删除锁或自动重跑。
- 方案B的五步处置流程以代码日志和“方案B第14版”交接包为准；context 只记录运行红线，不替代现场实扫。

## 帮助中心同步规约（2026-07-22 需求方定稿，长期有效）

- 帮助中心任何文章/通报变更（新增、改时间、转正式、停用、口径调整），必须同批：①更新对应文章；②同步更新 `notify_overview` 通报总览时间轴；③写入 context（TASK_CHANGE_LOG + 涉及 MAP）。三者缺一不为完成。
- 会话产出的交付件必须当场落盘本地仓库/生产（`交付件/` 或部署），禁止只存在会话沙盒（2026-07-22 规格丢失事故教训）。
- 待认领产品绩效扣分口径（已拍板）：周一日报=第1次提醒，周四仍在=第2次提醒且当期即扣5分/产品；谁认领谁承担；认领+扣分随下期日报公布并同步黄少如；退出清单再出现轮次清零重算；扣分入 `biz_perf_deduction` 台账（AI智能人事板块数据底座，板块下阶段做）。



## 目标管理 8 月新规摘要（2026-08-04，M1–M8 已上线）
- 周期：7号截止、8号起每人每天扣5分(不封顶)、过8号超管代填。谁填：全量在营(非CS/非新品/非豁免)均填并定目标、考核全量。豁免 v5：上月整月WFS库存MAX=0且WFS销量=0且在途=0、清货期不豁免、新品走公司公式。
- 新增/变更 cron：09:25 月度规划未填扣分(checkMonthlyPlanDeduction·8号起)、09:35 清货无目标特批(checkClearanceNoTargetAlert·8号起)、月报生成 4日06:00(原03:00·M8)。
- 新增表：event_monthly_plan_unfilled(EVENT,每人每天一行)；biz_perf_deduction 新增 biz_type=monthly_plan_unfilled。清单 ai_monthly_issue_item(AI层,plan_month=报告月+1)。
- 逐条细节见 TASK_CHANGE_LOG.md 2026-08-03~04 节；表/管道见 DATABASE_MAP / PIPELINE_MAP；帮助中心 dim_page_help(monthly_plan/weekly_report/hr_performance) 已同步。

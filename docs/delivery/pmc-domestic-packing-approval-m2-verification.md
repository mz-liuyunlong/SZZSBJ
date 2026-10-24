# 打包审批M2本地验收记录（2026-10-21）

## 最终结果

当前dev实现手工添加打包单及审批前商品修改，删除误加的系统打包单管理入口和接口。先选择入库单×SKU，目标店铺/ItemID从同SKU有效Listing选择；GTIN/MSKU跟随Listing。提交仅保存待审批，通过才发PK并分配原来源库存。跨店铺保留原入库依据和双快照。资料缺失默认不报关并标记default。

## 本地数据库

仅127.0.0.1:55432/LOCAL_DATABASE_NAME。0051、0052应用前各有完整本地备份及pg_restore目录核验。现有head=20261021_0052_domestic_packing_manual。

|表|最终影响/实测数量|
|---|---|
|ops_domestic_packing_manual_requests|今天新增，申请/来源外键/双快照/幂等请求；0条（验收已回滚）|
|ops_domestic_pk_sequences|沿用北京日发号，提交申请不发号|
|ops_domestic_packing_orders|沿用并增加原快照/最终身份等字段；4条原审批|
|ops_domestic_packing_allocations|沿用来源库存分配；3条原分配|
|evt_domestic_packing_events|沿用不可变审批审计；4条原事件|
|ops_domestic_packing_ows_links|0051误加；0052核对空表后删除，当前不存在|
|app_permissions|定义manual-create；停用3个撤回动作，不调整角色/用户授权|
|MART/GOV/IAM|历史MART2908、发布版本2、用户29，未改原业务数据|

合成MART行0；手工申请和审批验收在外层回滚事务内完成。临时本地8012桥接服务及4173测试Vite已停，正常用户服务未停止。

## 验证

- 后端test_packing_approval.py、test_packing_lifecycle.py（最终仅商品规则）、test_packing_manual.py：26通过。覆盖不提前占库、审批分配、幂等、来源变化、数量和独立动作权限；已删除系统接口返回404。
- 前端Vitest三文件：6通过（接口传输、筛选及既有复制单元格）。
- Playwright：3通过。只读按钮、错误重试、手工来源选择→提交待审批→通过→审批记录完整流程。
- TypeScript构建检查、审批目录及页面ESLint通过。
- 前端真实业务请求经隔离的本地测试桥接进入真实本地数据库，鉴权与来源范围是显式合成fixture；这不等于已使用某个真人账号验证登录或授权。不在正常服务放宽认证。

## 交付边界与生产迁移

未提交、推送、发布或访问生产，保留原有dirty启动/preflight/复制单元格等改动。测试不会留下真实业务手工申请。

系统打包单列表、OWS关联、作废、业务测试切换均已删除；0051剩余兼容字段不代表功能开放。当前审批仍为local-only/is_test，历史覆盖及标准到货事实不齐，不创建领星OWS、不调用WFS。

负责人要求后续本地不自动新增/执行迁移版本；本次不增加0053。0051和0052目前仍属本地开发历史，不能直接当成生产发布方案。合并迁移文件本身不会写库，但生产执行upgrade head会运行它们；只部署代码不补所需结构会报缺表/字段。生产上线前另行整理最终迁移及权限启用方案，从生产实际版本做备份、升级和业务回归；不要直接删除0051造成0052父版本失联，不对本地现有数据强制降级。

接口补充见docs/api/pmc-domestic-packing-approval-m2-api.md；操作见docs/sop/pmc-domestic-packing-approval.md。按项目backend-module-designer与react-component-architect技能实施，最终来源决策及PRP已统一为手工范围。

## 2026-10-21 报关与操作列最终调整

下拉仅有“报关”和“不报关”，列表、手工添加、审批弹窗一致，没有可选“默认规则”。初次显示服务端自动结果，未修改时内部命令仍为default，并非前端第三个选项；用户选择后命令declare/skip，结果标记manual，随审批保存，列表暂存不直接写库。

优先产品purchase_remark（当前DWD产品快照所指原始成功响应，按商品ID精确匹配）。字段存在但为空视为无明确备注，默认false；字段不可用时回退同账号同SKU当前DWD所指ODS采购计划/采购明细item_purchase_remark/remark/plan_remark。否定词优先。采购兜底最新明确不报关优先，否则任一历史当前单据明确报关则报关，否则默认false。单据只读取DWD当前版本所指ODS，不能累加同一单据历史旧版本；拆分采购行去重。

既有MART payload新增customs_proof：value(bool)、source(default/product_remark/purchase_remark)、rule(domestic.customs.v1)、field、remark(最多500字)、ref(来源RAW引用或ODS记录UUID)、observed_at。Candidate映射customs_default、customs_default_src与customs_proof，来源证据进入candidate_version；default命令由后端取当前自动结果，人工选择记manual。订单现有customs_value/customs_src及JSON快照/不可变事件保存审批结果，不覆盖历史。旧无证据快照兼容默认false，不追写历史审批。

数据整理在既有发布流程完成，正常业务GET不访问RAW/ODS、不调用领星；CSV不带该新增数据库备注证据，不能声称CSV和本次备注富化字段相同。未改库存、商品身份和到仓日期。

本地备份后重建当前1454行发布版本，其中155行产品采购备注判定报关，1299行默认不报关；旧发布版本保留，MART历史总4362。迁移仍0052，无新表/字段/约束、无0053，历史4审批/3分配/4事件和用户29保留。

操作列“修改”普通按钮、“审批通过”蓝色主按钮、“驳回”普通按钮，统一间距和最小280px列宽（兼容已有窄列设置），权限/业务阻断逻辑不变。当前仅进行本地本模块验证，不进行全局测试；全局回归待用户后续功能全部完成后统一安排。

最终本地结果：60项本模块后端检查通过（含原入库发布兼容；现有Pydantic测试1个弃用提示），3项Playwright页面验收通过；相关前端ESLint通过，双选项实现阶段TS检查通过。本轮不是全局测试。一次与临时回滚E2E事务并行的后端运行出现2项发号锁等待超时；停止临时事务后单独重跑60项全部通过，未修改业务锁逻辑。

只读本地真实数据库、合成鉴权路由核对：pending HTTP200/44行（4 product_remark报关、40 default不报关）；inbound HTTP200/1454行。最终4审批/3分配/4事件、0手工申请/0合成MART、用户29。GOV3发布版本/MART历史4362，旧版保留；数据库版本仍0052。临时8012与4173验证服务已停止。普通用户实际登录态和全局回归不由合成鉴权验收替代，待后续功能全部开发完统一测试。没有提交推送、生产连接或生产修改。


> 占位名称说明：`LOCAL_DATABASE_NAME` 与 `ISOLATED_TEST_DATABASE_NAME` 分别表示负责人已批准的本地开发库和隔离测试库；执行前必须与获批本地配置中的实际数据库名逐字核对，并同时核对环境、host、port及连接后数据库身份。占位名称不是可直接执行的数据库名，也不授权其他本地库或生产库。历史数量、指纹及备份哈希保持原记录。

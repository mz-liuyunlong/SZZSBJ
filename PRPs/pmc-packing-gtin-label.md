# 打包审批 GTIN 标签 PDF

状态：待负责人确认，禁止据此直接实现。日期：2026-10-28。

## 1. Goal / 2. Why
GTIN 列增加截图所示“标签”入口，提供与当前目标商品一致、可预览下载的产品标签，避免误贴旧身份条码。

## 3. Scope / 4. Navigation
仅 PMC → 国内仓看板 → 打包单审批的 GTIN 标签。新建只读标签服务及页面入口。排除审批通过/口令、OWS、仓库页、数据库迁移、库存分配、历史订单标签。

## 5. Permissions
沿用 page:pmc:domestic-warehouse-board:view 和来源账号数据范围；不得凭猜测候选 ID 越权。无高危写操作。

## 6. Data Source
引用 ../docs/data-sources/decisions/pmc-packing-gtin-label-decision.md，READY_FOR_PRP；NEW_SYSTEM_OWNED 派生 PDF，复用已同步 dim_walmart_listings。负责人实现审批：待确认。无旧库、外部调用、新表或同步。

## 7. API Contract（拟定）
GET /api/pmc/domestic/packing-approval/pending/{candidate_id}/label，参数 source_account_ref、candidate_version、listing_version。后端解析当前目标身份并验证来源范围和版本，禁止采用客户端自由 GTIN/MSKU。

使用标准 success/data/error/meta/request_id JSON envelope 和显式 Pydantic response_model；data 包含 mime_type=application/pdf、filename、pdf_base64；meta 标注数据表及标签模板版本。前端解码为 Blob，在用户点击时建立的新标签页中预览并释放对象 URL。失败不遗留空白页，明确显示错误。标签为单页小文件，不提供批量生成。

401 未登录、403 范围或权限不足、404 候选不存在、409 来源/Listing 已变化、422 GTIN/MSKU 不合格；使用项目错误码约定。

## 8. UI Requirements
GTIN 文本保留复制，在旁边显示“标签”；无 GTIN/MSKU 时禁用并解释。模板参考旧样式：50×30 mm、Code128 编码完整 14 位 GTIN，下方号码、底部 MSKU 与 Made in China。产地文案为本 PRP 待确认模板内容。长 MSKU 必须适配，不裁切、不遮挡条码。

## 9. SOP / API Docs
实施时补 OpenAPI、Markdown API、现有 SOP、数据接口 registry 和 handoff；复用现有页面帮助。

## 10. Implementation Plan
先核对新版候选修改状态；后端依既有分层新写生成逻辑，不复制旧代码。评估 reportlab 作为 PDF/条码依赖，通过 uv 管理并核对官方文档；之后接入入口。实施时应用项目后端 Skill 和 PDF 验证流程。

## 11. Validation Gates
pytest：范围隔离、唯一身份、版本冲突、缺失/无效 GTIN、前导零与无副作用；PDF 渲染检查尺寸及长 MSKU，独立条码解码校验；Vitest/Playwright mock 覆盖点击、PDF 内容响应及错误。运行相关 lint/type/build 和 git diff --check；不调用真实平台或生产库。

## 12. Forbidden / 13. Rollback
不改审批、OWS、生产、环境密钥或旧项目。只回滚本任务的入口、路由、生成逻辑及其依赖；无数据库回滚。

## 14. Acceptance Checklist
- [ ] 负责人确认 PRP 后才实施
- [ ] 来源与身份校验、权限、PDF 模板及独立条码验证通过
- [ ] 页面入口、错误反馈和新标签页行为通过验证
- [ ] API/SOP/registry/handoff 更新完成

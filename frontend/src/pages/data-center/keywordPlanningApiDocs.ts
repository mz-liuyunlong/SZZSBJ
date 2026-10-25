import type { ApiDocItem, ApiDocModule, ApiMethod } from './apiDocsTypes';

const prefix = '/api/v1/keyword-planning';
const account = { name: 'source_account_ref', type: 'string', required: true,
  description: '服务端校验当前用户可访问的账户范围' };

type Entry = [ApiMethod, string, string, string, string];
const entries: Entry[] = [
  ['GET', 'products/{product_id}/source-state', '读取商品来源状态', 'products:read', '已确认事实、上传 ID、ASIN 数量'],
  ['POST', 'sources/walmart/confirm', '确认已保存的 Walmart 页面与商品事实', 'products:write', '不可变事实和页面快照 ID'],
  ['POST', 'sources/amazon/asin', '导入已保存的 ASIN 来源', 'products:write', 'ASIN 快照 ID 与图片数量'],
  ['POST', 'imports/xlsx', '保存关键词 Excel 原件和原始行', 'products:write', '上传 ID、状态和行数'],
  ['GET', 'preflight', '检查分析证据与规则审批', 'products:read', '可复核状态和阻断代码'],
  ['POST', 'analyses', '创建冻结的内部分析批次', 'products:write', '批次 ID、状态和词数'],
  ['GET', 'products/{product_id}/runs', '读取商品历史分析', 'products:read', '批次列表与分页'],
  ['GET', 'runs/{run_id}', '读取冻结批次', 'products:read', '批次详情'],
  ['GET', 'runs/{run_id}/keywords', '读取逐词证据与结果', 'products:read', '逐词类型、六维、承接和拒绝原因'],
  ['GET', 'runs/{run_id}/internal-workbook', '下载内部五表', 'products:read', '内部 XLSX；不是官方上传模板'],
  ['GET', 'products/{product_id}/library', '查询商品持久词库', 'products:read', '来源种类、观测数和最新等级'],
  ['POST', 'products/{product_id}/library/manual', '人工补充待复核词', 'products:write', '接受数和新来源事件数'],
  ['GET', 'rulesets', '读取规则集', 'products:read', '规则集列表'],
  ['GET', 'rulesets/{rule_set_id}/versions', '读取规则版本', 'products:read', '版本及冻结配置哈希'],
  ['POST', 'rulesets', '创建禁用规则集', 'super_admin', '规则集 ID'],
  ['POST', 'rulesets/{rule_set_id}/drafts', '创建新规则草稿', 'super_admin', '草稿 ID 和配置哈希'],
  ['GET', 'rules/{version_id}/decisions', '读取 D01–D08 审批与事件', 'products:read', '决策状态与审计事件'],
  ['POST', 'rules/{version_id}/decisions/{key}/submit', '提交具体决策方案', 'action:ai-center:keyword-rules:submit', '待审状态'],
  ['POST', 'rules/{version_id}/decisions/{key}/review', '独立复核方案', 'action:ai-center:keyword-rules:review', '通过或驳回状态'],
  ['POST', 'rules/{version_id}/publish', '核验八项批准并发布冻结版本', 'action:ai-center:keyword-rules:publish', '发布收据'],
  ['POST', 'rules/{version_id}/retire', '退役已发布版本', 'super_admin', '退役收据'],
];

const apis: ApiDocItem[] = entries.map(([method, suffix, title, permission, result], index) => ({
  id: `keyword-v11-${index}`,
  moduleKey: 'keyword-planning-v11', moduleName: '关键词 V1.1',
  levelName: '本地复核接口', levelDesc: '未部署；不授权 Walmart 正式投放',
  method, title, path: `${prefix}/${suffix}`,
  purpose: `${title}；详见 docs/api/keyword-planning-v11.md。`,
  requestMode: method === 'GET' ? 'Query / 路径参数' : 'JSON Body 或原始 XLSX',
  successReturn: result,
  scenario: '本地 V1.1 开发与页面验收，生产尚未开放。',
  authScope: `${permission} + source_account_ref 数据范围`,
  queryParams: [account], bodyParams: [],
  returnFields: [{ name: 'data', type: 'object', required: true, description: result }],
  requestExample: { method, url: `${prefix}/${suffix}`, query: { source_account_ref: '<authorized-account>' } },
  responseExample: suffix.endsWith('/internal-workbook')
    ? { content_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', note: '内部分析，不可上传' }
    : { success: true, data: { note: result }, error: null, meta: null, request_id: '<request-id>' },
}));

export const keywordPlanningApiDocs: ApiDocModule = {
  key: 'keyword-planning-v11', name: '关键词 V1.1', icon: '🔎',
  desc: '本地开发契约；D01–D08 与官方模板未批准，不可正式投放',
  levels: [{ name: '本地复核接口', desc: '服务端账户范围、证据冻结与独立审批', apis }],
};

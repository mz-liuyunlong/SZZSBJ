import type { ApprovalFilters, ApprovalItem } from "./approvalTypes";
import { fetchApprovals } from "./approvalApi";

export interface DemoSeed {
  id: string;
  approval_type: string;
  title: string;
  business_ref: string;
  applicant: string;
  store: string;
  status: "submitted" | "approved" | "rejected";
  risk: "low" | "medium" | "high";
  amount: string | null;
  submitted_at: string;
  reason: string;
  evidence: string;
  sku: string;
  plan: string;
}

export const demoSeeds: readonly DemoSeed[] = [
  {
    id: "DEMO-PO-001",
    approval_type: "purchase_exception",
    title: "采购金额超预算申请",
    business_ref: "DEMO-PO-202610-001",
    applicant: "演示运营A",
    store: "演示美区一店",
    status: "submitted",
    risk: "medium",
    amount: "2860",
    submitted_at: "2026-10-29T03:20:00Z",
    reason: "本批次原材料报价上涨，申请追加采购预算。",
    evidence: "演示供应商报价单、采购测算资料",
    sku: "DEMO-SKU-101",
    plan: "追加预算后由采购部门独立执行",
  },
  {
    id: "DEMO-PO-002",
    approval_type: "purchase_exception",
    title: "紧急补货采购申请",
    business_ref: "DEMO-PO-202610-002",
    applicant: "演示运营B",
    store: "演示美区二店",
    status: "approved",
    risk: "high",
    amount: "5420",
    submitted_at: "2026-10-28T05:10:00Z",
    reason: "预计库存不足三周，申请提前安排补货。",
    evidence: "演示销量预测与供应商交期",
    sku: "DEMO-SKU-102",
    plan: "批准后等待采购部门确认供应商交期",
  },
  {
    id: "DEMO-PO-003",
    approval_type: "purchase_exception",
    title: "采购数量调整申请",
    business_ref: "DEMO-PO-202610-003",
    applicant: "演示运营C",
    store: "演示美区三店",
    status: "rejected",
    risk: "low",
    amount: "1680",
    submitted_at: "2026-10-26T08:40:00Z",
    reason: "申请提高测试产品首批采购数量。",
    evidence: "演示测试销售记录",
    sku: "DEMO-SKU-103",
    plan: "演示驳回原因：暂不扩大首批采购量",
  },
  {
    id: "DEMO-CLR-001",
    approval_type: "clearance_request",
    title: "滞销库存清货申请",
    business_ref: "DEMO-CLR-001",
    applicant: "演示运营A",
    store: "演示美区一店",
    status: "submitted",
    risk: "high",
    amount: null,
    submitted_at: "2026-10-29T04:15:00Z",
    reason: "预计售罄天数超过清货规则阈值，需要降低库存压力。",
    evidence: "演示库存库龄、30天销售和利润资料",
    sku: "DEMO-SKU-201",
    plan: "计划清货120件，采用分阶段促销",
  },
  {
    id: "DEMO-CLR-002",
    approval_type: "clearance_request",
    title: "季末库存处理申请",
    business_ref: "DEMO-CLR-002",
    applicant: "演示运营B",
    store: "演示美区二店",
    status: "approved",
    risk: "medium",
    amount: null,
    submitted_at: "2026-10-27T09:30:00Z",
    reason: "季末库存需要按批准计划进行去化。",
    evidence: "演示库存成本及目标清货数量",
    sku: "DEMO-SKU-202",
    plan: "计划清货80件，月底前完成",
  },
  {
    id: "DEMO-CLR-003",
    approval_type: "clearance_request",
    title: "低毛利商品清货申请",
    business_ref: "DEMO-CLR-003",
    applicant: "演示运营C",
    store: "演示美区三店",
    status: "rejected",
    risk: "medium",
    amount: null,
    submitted_at: "2026-10-25T12:30:00Z",
    reason: "商品近期毛利下降，申请提前清货。",
    evidence: "演示利润率与广告占比分析",
    sku: "DEMO-SKU-203",
    plan: "演示驳回原因：库存压力不足，继续观察",
  },
  {
    id: "DEMO-LST-001",
    approval_type: "listing_archive",
    title: "长期停用 Listing 归档",
    business_ref: "DEMO-LST-001",
    applicant: "演示运营A",
    store: "演示美区一店",
    status: "submitted",
    risk: "low",
    amount: null,
    submitted_at: "2026-10-29T06:10:00Z",
    reason: "Listing 长期停用，申请归档以清理无效运营记录。",
    evidence: "演示 Listing 停用记录",
    sku: "DEMO-SKU-301",
    plan: "归档前核对剩余库存与未完成订单",
  },
  {
    id: "DEMO-LST-002",
    approval_type: "listing_archive",
    title: "重复 Listing 归档",
    business_ref: "DEMO-LST-002",
    applicant: "演示运营B",
    store: "演示美区二店",
    status: "approved",
    risk: "low",
    amount: null,
    submitted_at: "2026-10-27T08:00:00Z",
    reason: "重复 Listing 已确认保留主刊登。",
    evidence: "演示主副 Listing 对照资料",
    sku: "DEMO-SKU-302",
    plan: "归档副 Listing，保留原审批记录",
  },
  {
    id: "DEMO-LST-003",
    approval_type: "listing_archive",
    title: "旧版本 Listing 归档",
    business_ref: "DEMO-LST-003",
    applicant: "演示运营C",
    store: "演示美区三店",
    status: "rejected",
    risk: "medium",
    amount: null,
    submitted_at: "2026-10-26T02:20:00Z",
    reason: "旧版本准备归档，但仍存在库存。",
    evidence: "演示库存和在售状态",
    sku: "DEMO-SKU-303",
    plan: "演示驳回原因：先完成库存核对",
  },
  {
    id: "DEMO-PRC-001",
    approval_type: "price_adjustment",
    title: "售价下调审批",
    business_ref: "DEMO-PRC-001",
    applicant: "演示运营A",
    store: "演示美区一店",
    status: "submitted",
    risk: "medium",
    amount: null,
    submitted_at: "2026-10-29T07:35:00Z",
    reason: "竞品降价后转化率下降，申请临时调整售价。",
    evidence: "演示竞品价格与利润测算",
    sku: "DEMO-SKU-401",
    plan: "售价由19.99美元调整为17.99美元",
  },
  {
    id: "DEMO-PRC-002",
    approval_type: "price_adjustment",
    title: "利润改善提价审批",
    business_ref: "DEMO-PRC-002",
    applicant: "演示运营B",
    store: "演示美区二店",
    status: "approved",
    risk: "low",
    amount: null,
    submitted_at: "2026-10-27T10:30:00Z",
    reason: "近期转化稳定，申请提高正常售价。",
    evidence: "演示价格弹性及利润测算",
    sku: "DEMO-SKU-402",
    plan: "售价由14.99美元调整为15.99美元",
  },
  {
    id: "DEMO-PRC-003",
    approval_type: "price_adjustment",
    title: "促销价格调整审批",
    business_ref: "DEMO-PRC-003",
    applicant: "演示运营C",
    store: "演示美区三店",
    status: "rejected",
    risk: "high",
    amount: null,
    submitted_at: "2026-10-25T04:40:00Z",
    reason: "申请低于正常毛利控制线的促销售价。",
    evidence: "演示销售预估和促销计划",
    sku: "DEMO-SKU-403",
    plan: "演示驳回原因：预计利润不足",
  },
];

const demoTypes = new Set(demoSeeds.map((seed) => seed.approval_type));

export function isDemoApproval(
  item: Pick<ApprovalItem, "id"> | undefined,
): boolean {
  return Boolean(item?.id.startsWith("DEMO-"));
}

export function getDemoSeed(id: string): DemoSeed | undefined {
  return demoSeeds.find((seed) => seed.id === id);
}

function toApprovalItem(seed: DemoSeed): ApprovalItem {
  return {
    id: seed.id,
    version: 1,
    approval_type: seed.approval_type,
    business_ref: seed.business_ref,
    title: `【演示】${seed.title}`,
    source_account_ref: seed.store,
    applicant_id: seed.applicant,
    status: seed.status,
    risk_level: seed.risk,
    amount: seed.amount,
    currency_code: seed.amount === null ? null : "USD",
    submitted_at: seed.submitted_at,
    reviewed_at: seed.status === "submitted" ? null : seed.submitted_at,
    reviewed_by: seed.status === "submitted" ? null : "演示审批人",
    reason: seed.reason,
    can_review: false,
    requires_verification: false,
    case_review: false,
    follow_log: null,
  };
}

export function getFilteredDemoItems(
  filters: ApprovalFilters,
): ApprovalItem[] {
  return demoSeeds
    .filter((seed) =>
      !filters.approval_type ||
      seed.approval_type === filters.approval_type,
    )
    .filter((seed) =>
      filters.tab === "pending"
        ? seed.status === "submitted"
        : seed.status === filters.tab,
    )
    .filter((seed) =>
      !filters.risk_level ||
      seed.risk === filters.risk_level,
    )
    .filter((seed) => {
      const keyword = filters.keyword?.trim().toLowerCase();

      if (!keyword) return true;

      return [
        seed.id,
        seed.title,
        seed.business_ref,
        seed.reason,
        seed.sku,
      ].join(" ").toLowerCase().includes(keyword);
    })
    .sort((a, b) =>
      b.submitted_at.localeCompare(a.submitted_at),
    )
    .map(toApprovalItem);
}

type ApprovalResponse = Awaited<ReturnType<typeof fetchApprovals>>;

export async function fetchWorkbenchList(
  filters: ApprovalFilters,
): Promise<ApprovalResponse> {
  // WFS 查询完全交给原有真实接口处理。
  if (filters.approval_type === "wfs_case_abandon") {
    return fetchApprovals(filters);
  }

  // 未纳入演示的其他类型，保持原有接口。
  if (filters.approval_type &&
      !demoTypes.has(filters.approval_type)) {
    return fetchApprovals(filters);
  }

  const mockItems = getFilteredDemoItems(filters);
  const offset = (filters.page - 1) * filters.page_size;

  // 采购、清货、Listing、价格四类：仅使用本地演示记录。
  if (filters.approval_type) {
    return {
      data: {
        items: mockItems.slice(
          offset,
          offset + filters.page_size,
        ),
      },
      meta: {
        page: filters.page,
        page_size: filters.page_size,
        total: mockItems.length,
      },
    } as ApprovalResponse;
  }

  // 全部业务：真实 WFS + 演示记录。
  // WFS 先展示，后面接演示记录，保持分页 total 准确。
  const real = await fetchApprovals({
    ...filters,
    approval_type: "wfs_case_abandon",
  });

  const realTotal = real.meta.total;
  const realCountOnPage = Math.max(
    0,
    Math.min(filters.page_size, realTotal - offset),
  );

  const demoStart = Math.max(
    0,
    offset + realCountOnPage - realTotal,
  );

  const demoCapacity = filters.page_size - realCountOnPage;

  const mockPageItems = mockItems.slice(
    demoStart,
    demoStart + demoCapacity,
  );

  return {
    ...real,
    data: {
      ...real.data,
      items: [
        ...real.data.items,
        ...mockPageItems,
      ],
    },
    meta: {
      ...real.meta,
      total: realTotal + mockItems.length,
    },
  };
}

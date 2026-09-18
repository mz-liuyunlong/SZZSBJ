import { backendRequest } from "@/api/backendApi";
import type {
  WfsFeeAlertFollowFormValues,
  WfsFeeAlertRow,
} from "@/pages/warehouse/wfsFeeAlertTypes";

interface BackendWfsFeeAlert {
  id: string;
  business_date_la: string;
  store_id: string;
  store_name: string | null;
  owner_ref: string | null;
  item_id: string;
  msku: string;
  local_sku: string | null;
  product_name: string | null;
  order_count: string;
  sales_qty: string;
  cost_quantity: string;
  expected_fee_amount: string | null;
  actual_fee_amount: string | null;
  variance_amount: string | null;
  variance_rate: string | null;
  expected_unit_amount: string | null;
  actual_unit_amount: string | null;
  status: WfsFeeAlertRow["status"];
  case_no: string | null;
  reason: string | null;
  priority: WfsFeeAlertRow["level"];
  recovered_amount: string;
  case_opened_at: string | null;
  next_follow_at: string | null;
  latest_follow: string | null;
}

interface BackendWfsFeeAlertData {
  items: BackendWfsFeeAlert[];
}

interface BackendMeta {
  page: number;
  page_size: number;
  total: number;
}

const numberValue = (value: string | null | undefined) => Number(value ?? 0);

const toRow = (item: BackendWfsFeeAlert): WfsFeeAlertRow => ({
  id: item.id,
  imageLabel: item.product_name ?? item.local_sku ?? item.item_id,
  imageSymbol: "📦",
  sku: item.local_sku ?? "-",
  msku: item.msku,
  store: item.store_name ?? item.store_id,
  owner: item.owner_ref ?? "未分配",
  productId: item.item_id,
  productName: item.product_name ?? item.local_sku ?? item.item_id,
  category: "-",
  orders: numberValue(item.order_count),
  units: numberValue(item.cost_quantity),
  chargedFee: numberValue(item.actual_fee_amount),
  standardFee: numberValue(item.expected_fee_amount),
  unitCharged: numberValue(item.actual_unit_amount),
  unitStandard: numberValue(item.expected_unit_amount),
  overFee: numberValue(item.variance_amount),
  unitOverFee: numberValue(item.actual_unit_amount) - numberValue(item.expected_unit_amount),
  recoveredAmount: numberValue(item.recovered_amount),
  status: item.status,
  caseNo: item.case_no ?? "",
  reason: item.reason ?? "WFS实际费用高于预计费用",
  discoveredAt: item.business_date_la,
  caseOpenedAt: item.case_opened_at?.slice(0, 10) ?? "",
  nextFollowAt: item.next_follow_at ?? "-",
  level: item.priority,
  latestFollow: item.latest_follow ?? "",
});

export async function fetchWfsFeeAlerts(
  startDate?: string,
  endDate?: string,
): Promise<WfsFeeAlertRow[]> {
  const rows: WfsFeeAlertRow[] = [];
  const pageSize = 500;
  for (let page = 1; page <= 10_000; page += 1) {
    const search = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (startDate) search.set("start_date", startDate);
    if (endDate) search.set("end_date", endDate);
    const envelope = await backendRequest<BackendWfsFeeAlertData, BackendMeta>(
      `/api/warehouse/wfs-fee-alerts?${search.toString()}`,
    );
    rows.push(...envelope.data.items.map(toRow));
    if (rows.length >= envelope.meta.total || envelope.data.items.length < pageSize) return rows;
  }
  throw new Error("WFS fee alert pagination exceeded the safety limit");
}

export async function updateWfsFeeAlertCase(
  id: string,
  values: WfsFeeAlertFollowFormValues,
  claimAmount: number,
): Promise<void> {
  await backendRequest<{ updated: boolean }, null>(
    `/api/warehouse/wfs-fee-alerts/${encodeURIComponent(id)}/case`,
    {
      method: "PUT",
      body: JSON.stringify({
        status: values.status,
        case_no: values.caseNo,
        reason: "",
        priority: "中",
        claim_amount: claimAmount,
        recovered_amount: values.recoveredAmount,
        next_follow_at: values.nextFollowAt === "-" ? null : values.nextFollowAt,
        latest_follow: values.latestFollow,
      }),
    },
  );
}

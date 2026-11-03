/** 物流看板 API (read-only). Row fields keep the 8088 pmc-logistics names (app-a.jsx enrich). */
import { backendRequest } from "@/api/backendApi";

export const logisticsPrefix = "/api/pmc/logistics";

export type Sev = "high" | "mid" | "low";

export interface LogisticsAlert {
  type: string;
  sev: Sev;
  desc: string;
  since: string;
  missing?: boolean;
  cargo?: string;
}

export interface LogisticsGood {
  cargo: string;
  store_id: string;
  store: string;
  msku: string;
  sku: string;
  name: string;
  gtin: string;
  qty: number;
  apply: number;
  boxes: number;
  per: number;
  box_kg: string;
  head_cost: number;
  value_source: string;
}

export interface LogisticsCargo {
  code: string;
  status: string;
  store?: string;
  declare: number;
  received: number;
  to_closed?: string;
}

export interface LogisticsRow {
  code: string;
  status: string;
  created: string;
  creator: string;
  provider_id: string;
  provider: string;
  channel_id: string;
  channel: string;
  method: string;
  fc: string;
  region: string;
  fee_type: string;
  tracking: string[];
  cost: { transport: number; other: number; currency: string };
  t: { delivery: string; actual_delivery: string; sail: string; expected_arrival: string; arrival: string; actual_due: string };
  stores: string[];
  store_id: string;
  goods: LogisticsGood[];
  cargos: LogisticsCargo[];
  qty: number;
  boxes: number;
  gw: number;
  stage: string;
  done: boolean;
  etd: string;
  atd: string;
  eta: string;
  ata: string;
  pickup: string;
  arrivalPlan: string;
  arrivalPlanSrc: string;
  arrivalActual: string;
  arrivalActualSrc: string;
  arrivalDate: string;
  arrivalSrc: string;
  cyc: number | null;
  cycSrc: string;
  daysToArrival: number | null;
  wmReceiptStart: string;
  wmFirstReceive: string;
  wmLastReceipt: string;
  wmReceiptDone: boolean;
  wmActualDelivery: string;
  wmClosed: string;
  wmSign: string;
  deliveredCarrier: string;
  signGap: number | null;
  signCheck: "none" | "ok" | "late" | "overdue" | "waiting" | "closed" | "nodata";
  sellableDate: string;
  sellableSrc: string;
  daysToSellable: number | null;
  deadline: string;
  remain: number | null;
  overdue: boolean;
  soon: boolean;
  usedDays: number | null;
  overdueDays: number;
  penalty: number;
  chargeWeight: number | null;
  ct: number | null;
  missing: string[];
  declared: number;
  received: number;
  ex: LogisticsAlert[];
  tr: { number: string; status: string; trackCn: string; lastTrack: string; totalWeightKg: number } | null;
}

export interface Option {
  value: string;
  label: string;
}

export interface LogisticsBoard {
  today: string;
  rows: LogisticsRow[];
  stages: string[];
  stage_counts: Record<string, number>;
  providers: Option[];
  channels: (Option & { provider_id: string })[];
  stores: Option[];
  regions: string[];
  rules: {
    remind_before: number;
    delivered_not_signed: number;
    penalty_per_kg_day: number;
    wm_receive_buffer: number;
    receive_diff_buffer: number;
    region_total: Record<string, number>;
  };
  sources: Record<string, unknown>;
}

export interface LogisticsTrack {
  number: string;
  customerNumber: string;
  status: string;
  totalWeightKg: number;
  trackCn: string;
  trackEn?: string;
  lastTrack?: string;
  nodes: Record<string, string>;
  tracks?: { t: string; cn: string; en?: string }[];
}

export interface LogisticsDetail {
  today: string;
  row: LogisticsRow;
  track: LogisticsTrack | null;
  walmart: {
    code: string;
    status: string;
    actualDelivery: string;
    firstReceipt: string;
    lastReceipt: string;
    receiptUnits: number;
    receivedUnits: number;
  }[];
}

export const getBoard = (signal?: AbortSignal) =>
  backendRequest<LogisticsBoard>(`${logisticsPrefix}/board`, { signal });

export const getShippingList = (code: string, signal?: AbortSignal) =>
  backendRequest<LogisticsDetail>(`${logisticsPrefix}/shipping-lists/${encodeURIComponent(code)}`, { signal });

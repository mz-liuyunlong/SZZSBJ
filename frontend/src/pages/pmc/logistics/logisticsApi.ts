/** 物流 API (read-only, server-side paging). Row fields keep the 8088 pmc-logistics names
 * (app-a.jsx enrich, app-b.jsx tabs). */
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

export interface LogisticsRules {
  remind_before: number;
  delivered_not_signed: number;
  penalty_per_kg_day: number;
  wm_receive_buffer: number;
  receive_diff_buffer: number;
  region_total: Record<string, number>;
}

export interface LogisticsOptions {
  today: string;
  total: number;
  stages: string[];
  stage_counts: Record<string, number>;
  providers: Option[];
  channels: (Option & { provider_id: string })[];
  stores: Option[];
  regions: string[];
  owners: string[];
  carrier_statuses: Option[];
  alert_types: string[];
  rules: LogisticsRules;
  sources: Record<string, unknown>;
}

export interface LogisticsList<Row, Summary> {
  items: Row[];
  total: number;
  page: number;
  page_size: number;
  summary: Summary;
}

/** 物流总览 table row: the SP row without goods / cargo lines (the drawer loads those). */
export type OverviewRow = Omit<LogisticsRow, "goods" | "cargos" | "tr"> & { cargo_count: number };
export type OverviewCard = "all" | "transit" | "soon" | "over" | "signed" | "miss" | "month";
export interface OverviewSummary {
  cards: Record<OverviewCard, number>;
  shipped: number;
  penalty_total: number;
  month_start: string;
  all: number;
  qty: number;
  boxes: number;
}

export interface AlertRow extends LogisticsAlert {
  id: string;
  code: string;
  stage: string;
  provider: string;
  provider_id: string;
  channel: string;
  fc: string;
  region: string;
  stores: string[];
}
export interface AlertSummary {
  types: Record<string, number>;
  all: number;
}

export interface ForecastLine {
  code: string;
  cargo: string;
  /** 运单号（发货单上的物流商单号，可多张） */
  tracking: string[];
  provider: string;
  stage: string;
  fc: string;
  region: string;
  ship: number;
  sign: number;
  shelf: number;
  bucket: string;
  arr: string;
  arrSrc: string;
  arrReal: boolean;
  sell: string;
  sellReal: boolean;
  days: number | null;
}
export type BucketKey = "bOver" | "b15" | "b30" | "b60" | "b60p" | "bNone";
export interface ForecastRow extends Record<BucketKey, number> {
  key: string;
  store: string;
  store_id: string;
  sku: string;
  msku: string;
  gtin: string;
  name: string;
  item_id: string;
  owner: string;
  total: number;
  signedNP: number;
  aShip: number;
  aSign: number;
  aShelf: number;
  anom: number;
  nextArr: string;
  nextSell: string;
  /** 关联物流：发货单号 / 货件单号 / 运单号（去重，按出现顺序） */
  codes: string[];
  cargos: string[];
  trackings: string[];
  lines: ForecastLine[];
}
export interface ForecastSummary extends Record<BucketKey, number> {
  total: number;
  signedNP: number;
  aShip: number;
  aSign: number;
  aShelf: number;
  anom: number;
  products: number;
  rows: number;
  buffer: number;
  region_total: Record<string, number>;
}

export interface CarrierTrack {
  t: string;
  cn: string;
  en: string;
  bl: string;
  lat: string;
  lng: string;
}
export interface CarrierOrder {
  number: string;
  customerNumber: string;
  status: string;
  provider_id: string;
  provider: string;
  serviceNumber: string;
  kg: number;
  weight: number;
  cbm: number;
  sp: string;
  sp_status: string;
  sp_boxes: number;
  fc: string;
  region: string;
  store_id: string;
  store: string;
  trackCn: string;
  trackEn: string;
  lastTrack: string;
  nTracks: number;
  staleDays: number | null;
  stale: boolean;
  tracks?: CarrierTrack[];
}
export interface CarrierMissing {
  kind: "查不到" | "无运单号";
  tracking: string;
  sp: string;
  sp_status: string;
  store: string;
  why: string;
}
export interface CarrierSummary {
  orders: number;
  linked: number;
  unlinked: number;
  stale: number;
  stale_days: number;
  queried: number;
  zy_sps: number;
  status_counts: Record<string, number>;
  providers: { value: string; label: string; count: number }[];
  missing: CarrierMissing[];
  not_found: number;
  no_tracking: number;
}

export interface RulesView {
  today: string;
  thresholds: { key: string; value: number; unit: string; label: string }[];
  region_total: Record<string, number>;
  counts: Record<RuleSection, number>;
  editable: boolean;
  edit_hint: string;
}
export type RuleSection = "cycles" | "contracts" | "fcs";
export interface CycleRow {
  channel_id: string;
  channel: string;
  provider: string;
  method: string;
  regions: string[];
  toSail: number | null;
  voyage: number | null;
  days: number | null;
  src: string;
  sps: number;
}
export interface ContractRow { provider_id: string; provider: string; channel_id: string; channel: string; region: string; days: number; remind: number; sps: number }
export interface FcRow { fc: string; addr: string; city: string; state: string; zip: string; region: string; n: number }

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

type Params = Record<string, string | number | boolean | undefined | null>;

/** Query string without empty values (the API rejects unknown keys, not empty ones). */
export function toQuery(params: Params): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "" || v === false) continue;
    q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

const get = <T,>(path: string, signal?: AbortSignal) => backendRequest<T>(`${logisticsPrefix}${path}`, { signal });

export const getOptions = (signal?: AbortSignal) => get<LogisticsOptions>("/options", signal);
export const getOverview = (params: Params, signal?: AbortSignal) =>
  get<LogisticsList<OverviewRow, OverviewSummary>>(`/overview${toQuery(params)}`, signal);
export const getAlerts = (params: Params, signal?: AbortSignal) =>
  get<LogisticsList<AlertRow, AlertSummary>>(`/alerts${toQuery(params)}`, signal);
export const getForecast = (params: Params, signal?: AbortSignal) =>
  get<LogisticsList<ForecastRow, ForecastSummary>>(`/forecast${toQuery(params)}`, signal);
export const getCarriers = (params: Params, signal?: AbortSignal) =>
  get<LogisticsList<CarrierOrder, CarrierSummary>>(`/carriers${toQuery(params)}`, signal);
export const getCarrierOrder = (number: string, signal?: AbortSignal) =>
  get<{ today: string; order: CarrierOrder }>(`/carriers/${encodeURIComponent(number)}`, signal);
export const getRules = (signal?: AbortSignal) => get<RulesView>("/rules", signal);
export const getRuleList = <Row,>(section: RuleSection, params: Params, signal?: AbortSignal) =>
  get<LogisticsList<Row, { all: number }>>(`/rules/${section}${toQuery(params)}`, signal);
export const getShippingList = (code: string, signal?: AbortSignal) =>
  backendRequest<LogisticsDetail>(`${logisticsPrefix}/shipping-lists/${encodeURIComponent(code)}`, { signal });

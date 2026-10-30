/** Local preview rows for the WFS screens. They do not come from an API. */

export type PendingPackingState = "ok" | "used" | "blocked";

export interface PendingPackingRow {
  id: string;
  pk: string;
  test: boolean;
  who: string;
  at: string;
  store: string;
  sku: string;
  name: string;
  itemId: string;
  gtin: string;
  qty: number;
  ows: string;
  customs: "Y" | "N";
  packageLabel: string | null;
  boxes: number;
  units: number;
  boxDetail: string;
  boxNote: string;
  reboxed: boolean;
  state: PendingPackingState;
  why: string;
}

/** Approved orders that have not been packed. They stay off the table. */
export const pendingNotReady = { total: 0, noBox: 0, filledNotDone: 0 };

export interface SystemShipmentRow {
  id: string;
  draft: string;
  receivedAt: string;
  action: string;
  store: string;
  plan: string;
  systemNo: string;
  summary: string;
  status: "pending" | "approved" | "executed" | "failed";
  badge: string;
  result: string;
}

export interface BoardRow {
  id: string;
  store: string;
  shipmentId: string;
  owner: string;
  status: string;
  declared: number;
  shipped: number;
  received: string;
  fc: string;
  arrival: string;
  sellable: string;
  test: boolean;
  sku: string;
  gtin: string;
  title: string;
}

export interface ExceptionRow {
  id: string;
  shipmentId: string;
  store: string;
  kind: string;
  detail: string;
}

export interface ProbeRow {
  id: string;
  name: string;
  store: string;
  gtin: string;
  note: string;
}

export interface CreateBoardRow {
  id: string;
  draft: string;
  store: string;
  step: string;
  note: string;
}

export const WFS_STORES = ["HK2615-邓业(港澳国际)", "HK2614-李镜颜(几米智航)"] as const;

export const pendingPackingRows: PendingPackingRow[] = [];

export const systemShipmentRows: SystemShipmentRow[] = [
  {
    id: "ws-006", draft: "WS261017-006", receivedAt: "吴雅婷 10-17 14:24",
    action: "建货件 + 取箱唛", store: WFS_STORES[0], plan: "BUH-1792222460273",
    systemNo: "PMC-HK2615-20261017-01", summary: "1 SKU · 10 箱 · 150 件 · ITS",
    status: "executed", badge: "人工后自建",
    result: "后台人工已建货件 3349164WFB。货件号来自 10-20 领星 wfs_cargos，状态 PENDING_SHIPMENT_DETAILS。",
  },
  {
    id: "ws-005", draft: "WS261017-005", receivedAt: "吴雅婷 10-17 14:24",
    action: "建货件 + 取箱唛", store: WFS_STORES[1], plan: "RITT-1792222707447",
    systemNo: "PMC-HK2614-20261017-02", summary: "1 SKU · 25 箱 · 100 件 · ITS",
    status: "executed", badge: "人工后自建",
    result: "后台人工已建货件 3349573WFB。货件号来自 10-20 领星 wfs_cargos，状态 PENDING_SHIPMENT_DETAILS。",
  },
  {
    id: "ws-004", draft: "WS261017-004", receivedAt: "吴雅婷 10-17 14:24",
    action: "建货件 + 取箱唛", store: WFS_STORES[1], plan: "RIDE-1792222612949",
    systemNo: "PMC-HK2614-20261017-01", summary: "1 SKU · 25 箱 · 100 件 · ITS",
    status: "executed", badge: "人工后自建",
    result: "后台人工已建货件 3349573WFB。货件号来自 10-20 领星 wfs_cargos，状态 PENDING_SHIPMENT_DETAILS。",
  },
];

export const boardRows: BoardRow[] = [
  {
    id: "b-1", store: WFS_STORES[0], shipmentId: "3349164WFB", owner: "邓业",
    status: "PENDING_SHIPMENT_DETAILS", declared: 150, shipped: 150, received: "0 / 150",
    fc: "ITS", arrival: "—", sellable: "—", test: false,
    sku: "BUH-SET-01", gtin: "00612345678901", title: "浴室置物套装",
  },
  {
    id: "b-2", store: WFS_STORES[1], shipmentId: "3349573WFB", owner: "李镜颜",
    status: "PENDING_SHIPMENT_DETAILS", declared: 100, shipped: 100, received: "0 / 100",
    fc: "ITS", arrival: "—", sellable: "—", test: false,
    sku: "RITT-CUP-02", gtin: "00612345678918", title: "随行杯",
  },
  {
    id: "b-3", store: WFS_STORES[0], shipmentId: "PMC-TEST-20261020", owner: "邓业",
    status: "测试", declared: 2, shipped: 2, received: "—",
    fc: "—", arrival: "—", sellable: "—", test: true,
    sku: "TEST-SKU", gtin: "00000000000000", title: "测试货件",
  },
];

export const supplyBoardRows = boardRows.filter((row) => !row.test);

export const exceptionRows: ExceptionRow[] = [
  {
    id: "ex-1", shipmentId: "3349164WFB", store: WFS_STORES[0], kind: "签收未回",
    detail: "本期示例没有 Walmart 签收进度。正式接入前不判断为异常结论。",
  },
  {
    id: "ex-2", shipmentId: "3349573WFB", store: WFS_STORES[1], kind: "上架日未知",
    detail: "没有 Receipt 日期，可售日保持未知，不用到仓日加 10 天冒充。",
  },
];

export const probeRows: ProbeRow[] = [
  { id: "p-1", name: "示例探测 A", store: WFS_STORES[0], gtin: "00612345678901", note: "演示流程，不调用 Walmart。" },
  { id: "p-2", name: "示例探测 B", store: WFS_STORES[1], gtin: "00612345678918", note: "演示流程，不调用 Walmart。" },
];

export const createBoardRows: CreateBoardRow[] = [
  { id: "c-1", draft: "DEMO-CREATE-01", store: WFS_STORES[0], step: "待处理", note: "演示流程，不创建货件。" },
  { id: "c-2", draft: "DEMO-CREATE-02", store: WFS_STORES[1], step: "待处理", note: "演示流程，不创建货件。" },
];

export const shipmentStatusLabel: Record<SystemShipmentRow["status"], string> = {
  pending: "待批准",
  approved: "已批准待执行",
  executed: "已执行",
  failed: "执行失败",
};

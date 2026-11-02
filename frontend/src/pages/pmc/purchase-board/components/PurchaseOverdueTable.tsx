/**
 * 待采购超时 (card): one list in the board body.
 *
 * Rocky 2026-11-01: 待下单采购单 and 未转单计划 are the same state ("已审批、还没真正下出去"),
 * so both are shown together here instead of in a drawer. Rows are merged client-side
 * (both sources are fetched completely, see ``usePurchaseOverdueRows``) and sorted by
 * overdue days, then pending days, descending.
 */
import { Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type {
  PendingPurchasePlan,
  PurchaseBoardRow,
  PurchaseStoreRef,
} from "@/pages/pmc/purchase-board/purchaseBoardTypes";

export interface PurchaseOverdueRow {
  key: string;
  kind: "order" | "plan";
  docSn: string;
  planSn: string | null;
  sku: string | null;
  productName: string | null;
  store: PurchaseStoreRef;
  quantity: number | null;
  createdDate: string | null;
  pendingDays: number | null;
  pendingEstimated: boolean;
  overdueDays: number;
  ownerName: string | null;
  remarkItemId: string | null;
}

const daysSince = (iso: string | null, today: Date) => {
  if (!iso) return null;
  const start = new Date(`${iso.slice(0, 10)}T00:00:00Z`).getTime();
  if (Number.isNaN(start)) return null;
  const now = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
  return Math.max(0, Math.round((now - start) / 86_400_000));
};

export function overdueRowFromOrder(row: PurchaseBoardRow, today = new Date()): PurchaseOverdueRow {
  return {
    key: `order:${row.id}`,
    kind: "order",
    docSn: row.purchaseOrderSn,
    planSn: row.planSn,
    sku: row.sku,
    productName: row.productName,
    store: row.store,
    quantity: row.quantityTotal,
    createdDate: row.orderCreateDate ?? row.planCreateDate,
    pendingDays: daysSince(row.stage.stageStart, today),
    pendingEstimated: row.stage.stageStartEstimated,
    overdueDays: row.stage.overdueDays,
    ownerName: row.owner.name,
    remarkItemId: null,
  };
}

export function overdueRowFromPlan(plan: PendingPurchasePlan): PurchaseOverdueRow {
  return {
    key: `plan:${plan.planSn}`,
    kind: "plan",
    docSn: plan.planSn,
    planSn: plan.planSn,
    sku: plan.sku,
    productName: plan.productName,
    store: plan.store,
    quantity: plan.quantityPlan,
    createdDate: plan.planCreateDate,
    pendingDays: plan.pendingDays,
    pendingEstimated: plan.pendingSinceEstimated,
    overdueDays: plan.overdueDays,
    ownerName: null,
    remarkItemId: plan.remarkItemId,
  };
}

export function mergeOverdueRows(orders: PurchaseBoardRow[], plans: PendingPurchasePlan[], today = new Date()) {
  return [
    ...orders.map((row) => overdueRowFromOrder(row, today)),
    ...plans.map(overdueRowFromPlan),
  ].sort((a, b) => (
    b.overdueDays - a.overdueDays
    || (b.pendingDays ?? -1) - (a.pendingDays ?? -1)
    || a.docSn.localeCompare(b.docSn)
  ));
}

const dash = <Typography.Text type="secondary">—</Typography.Text>;

const columns = (onOpenOrder: (orderSn: string) => void): ColumnsType<PurchaseOverdueRow> => [
  {
    key: "kind",
    title: "类型",
    width: 110,
    render: (_, row) => (row.kind === "order" ? <Tag color="blue">待下单采购单</Tag> : <Tag>未转单计划</Tag>),
  },
  {
    key: "docSn",
    title: "单号",
    width: 150,
    render: (_, row) => (
      row.kind === "order"
        ? <Typography.Link onClick={() => onOpenOrder(row.docSn)}>{row.docSn}</Typography.Link>
        : row.docSn
    ),
  },
  { key: "sku", title: "SKU", dataIndex: "sku", width: 110, render: (value: string | null) => value ?? dash },
  { key: "productName", title: "产品名", dataIndex: "productName", ellipsis: true, width: 200, render: (value: string | null) => value ?? dash },
  {
    key: "store",
    title: "店铺",
    width: 170,
    render: (_, row) => (row.store.attributed ? row.store.name ?? row.store.id ?? dash : <Typography.Text type="warning">未归属店铺</Typography.Text>),
  },
  { key: "quantity", title: "数量", dataIndex: "quantity", width: 80, render: (value: number | null) => value ?? dash },
  { key: "created", title: "创建日期", dataIndex: "createdDate", width: 110, render: (value: string | null) => (value ? value.slice(0, 10) : dash) },
  {
    key: "pending",
    title: "待采购天数",
    width: 110,
    render: (_, row) => (
      row.pendingDays === null
        ? dash
        : (
          <span>
            {row.pendingDays} 天
            {row.pendingEstimated && <Typography.Text type="secondary">（估算）</Typography.Text>}
          </span>
        )
    ),
  },
  {
    key: "overdue",
    title: "超时",
    width: 100,
    render: (_, row) => (row.overdueDays > 0 ? <Tag color="red">超时 {row.overdueDays} 天</Tag> : <Tag>未超时</Tag>),
  },
  { key: "owner", title: "负责人", dataIndex: "ownerName", width: 90, render: (value: string | null) => value ?? dash },
  { key: "remark", title: "备注 ItemID", dataIndex: "remarkItemId", width: 130, render: (value: string | null) => value ?? dash },
];

interface PurchaseOverdueTableProps {
  rows: PurchaseOverdueRow[];
  loading: boolean;
  thresholdDays: number | null;
  currentPage: number;
  pageSize: number;
  onPageChange: (page: number, pageSize: number) => void;
  onOpenOrder: (orderSn: string) => void;
}

function PurchaseOverdueTable({
  rows,
  loading,
  thresholdDays,
  currentPage,
  pageSize,
  onPageChange,
  onOpenOrder,
}: PurchaseOverdueTableProps) {
  const orders = rows.filter((row) => row.kind === "order").length;
  return (
    <div className="purchase-board__overdue">
      <Typography.Paragraph type="secondary" className="purchase-board__hint">
        待采购超时：已审批、尚未真正下出去的采购需求，包含待下单采购单 {orders} 行与未转单计划 {rows.length - orders} 行，
        超时阈值 {thresholdDays === null ? "—" : `${thresholdDays} 天`}（规则表 s2_pending_days）；未归属店铺的计划不计超时。
      </Typography.Paragraph>
      <Table<PurchaseOverdueRow>
        rowKey="key"
        size="small"
        loading={loading}
        columns={columns(onOpenOrder)}
        dataSource={rows}
        scroll={{ x: 1360 }}
        locale={{ emptyText: "当前没有待采购超时的采购单或计划。" }}
        pagination={{
          current: currentPage,
          pageSize,
          total: rows.length,
          showSizeChanger: true,
          pageSizeOptions: ["50", "100", "200"],
          showTotal: (count) => `共 ${count.toLocaleString()} 条待采购超时`,
          onChange: onPageChange,
        }}
      />
    </div>
  );
}

export default PurchaseOverdueTable;

/** Purchase-order detail: header, lines × ItemID, receipts, plan chain and SKU cycle samples. */
import { Alert, Descriptions, Modal, Skeleton, Table, Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { MoneyCell } from "@/components/report-table/cells";
import EmptyState from "@/shared/states/EmptyState";
import {
  ItemIdCell,
  SkuCycleSamplesTooltip,
  StageCell,
} from "@/pages/pmc/purchase-board/components/PurchaseBoardCells";
import {
  EMPTY,
  currencySign,
  progressText,
  purchaseCycleText,
  skuCycleSourceLabels,
} from "@/pages/pmc/purchase-board/purchaseBoardDisplay";
import type {
  PurchaseBoardRow,
  PurchaseOrderDetail,
  PurchaseOrderPlanRef,
  SkuCycle,
} from "@/pages/pmc/purchase-board/purchaseBoardTypes";

interface PurchaseOrderDetailModalProps {
  orderSn?: string;
  detail?: PurchaseOrderDetail;
  loading: boolean;
  errorText?: string;
  onClose: () => void;
}

const lineColumns: ColumnsType<PurchaseBoardRow> = [
  { key: "sku", title: "SKU", dataIndex: "sku", render: (value: string | null) => value ?? EMPTY },
  { key: "productName", title: "产品名", dataIndex: "productName", ellipsis: true, render: (value: string | null) => value ?? EMPTY },
  {
    key: "store",
    title: "店铺",
    render: (_, row) => (row.store.attributed ? row.store.name ?? row.store.id ?? EMPTY : <Typography.Text type="warning">未归属店铺</Typography.Text>),
  },
  { key: "itemId", title: "ItemID", render: (_, row) => <ItemIdCell row={row} /> },
  { key: "gtin", title: "GTIN", render: (_, row) => row.itemId.gtin ?? EMPTY },
  { key: "plan", title: "计划号", render: (_, row) => (row.planSns.length > 0 ? row.planSns.join(" / ") : EMPTY) },
  { key: "qty", title: "分配量 / 单总量", render: (_, row) => `${row.quantityAllocated} / ${row.quantityTotal ?? "—"}` },
  { key: "progress", title: "收货进度", render: (_, row) => progressText(row) },
  { key: "cycle", title: "采购交期", render: (_, row) => purchaseCycleText(row.purchaseCycleDays) },
  {
    key: "amount",
    title: "分配金额",
    align: "right",
    render: (_, row) => <MoneyCell value={row.amountAllocated} currency={currencySign(row.currencyCode)} />,
  },
];

const planColumns: ColumnsType<PurchaseOrderPlanRef> = [
  { key: "planSn", title: "计划号", dataIndex: "planSn" },
  { key: "status", title: "计划状态", dataIndex: "planStatus", render: (value: number | null) => value ?? EMPTY },
  { key: "created", title: "创建日期", dataIndex: "planCreateDate", render: (value: string | null) => value ?? EMPTY },
  { key: "qty", title: "计划量", dataIndex: "quantityPlan", render: (value: number | null) => value ?? EMPTY },
  { key: "remark", title: "备注 ItemID", dataIndex: "remarkItemId", render: (value: string | null) => value ?? EMPTY },
  { key: "store", title: "店铺 ID", dataIndex: "storeId", render: (value: string | null) => value ?? EMPTY },
];

const cycleColumns: ColumnsType<SkuCycle> = [
  { key: "sku", title: "SKU", dataIndex: "sku" },
  {
    key: "value",
    title: "实际采购交期",
    render: (_, cycle) => (
      cycle.valueDays === null
        ? <Typography.Text type="secondary">{skuCycleSourceLabels[cycle.source]}</Typography.Text>
        : (
          <Tooltip title={<SkuCycleSamplesTooltip samples={cycle.samples} />} placement="left">
            <span className="purchase-board__cycle-cell">
              {cycle.valueDays.toFixed(1)} 天
              <Typography.Text type="secondary">（{skuCycleSourceLabels[cycle.source]}，{cycle.sampleCount} 样本）</Typography.Text>
              {cycle.unstable && <Tag color="orange">不稳定</Tag>}
            </span>
          </Tooltip>
        )
    ),
  },
  { key: "baseline", title: "基准", render: (_, cycle) => (cycle.baselineDays === null ? EMPTY : `${cycle.baselineDays} 天${cycle.baselineSetOn ? `（${cycle.baselineSetOn} 起）` : ""}`) },
  { key: "range", title: "极差", render: (_, cycle) => (cycle.rangeDays === null ? EMPTY : `${cycle.rangeDays} 天`) },
  {
    key: "samples",
    title: "近 5 单样本",
    render: (_, cycle) => (
      cycle.samples.length === 0
        ? EMPTY
        : (
          <span className="purchase-board__sample-list">
            {cycle.samples.slice(0, 5).map((sample) => (
              <Typography.Text key={sample.purchaseOrderSn} type={sample.used ? undefined : "secondary"} delete={!sample.used}>
                {sample.purchaseOrderSn} {sample.cycleDays} 天
              </Typography.Text>
            ))}
          </span>
        )
    ),
  },
];

function PurchaseOrderDetailModal({
  orderSn,
  detail,
  loading,
  errorText,
  onClose,
}: PurchaseOrderDetailModalProps) {
  return (
    <Modal
      title={`采购单详情 ${orderSn ?? ""}`}
      open={Boolean(orderSn)}
      width={1080}
      footer={null}
      destroyOnHidden
      onCancel={onClose}
      className="purchase-board__detail-modal"
    >
      {errorText && <Alert type="error" showIcon message={errorText} />}
      {!errorText && loading && !detail && <Skeleton active paragraph={{ rows: 6 }} />}
      {!errorText && !loading && !detail && (
        <EmptyState title="暂无详情" description="未找到该采购单的看板数据。" compact />
      )}
      {detail && (
        <div className="purchase-board__detail">
          <Descriptions size="small" column={4} bordered>
            <Descriptions.Item label="状态" span={2}><StageCell stage={detail.stage} /></Descriptions.Item>
            <Descriptions.Item label="下单日期">{detail.orderDate ?? EMPTY}</Descriptions.Item>
            <Descriptions.Item label="创建日期">{detail.orderCreateDate ?? EMPTY}</Descriptions.Item>
            <Descriptions.Item label="收货进度">
              {progressText({
                quantityReceived: detail.quantityReceived,
                quantityAllocated: detail.quantityTotal ?? 0,
                progressRatio: detail.progressRatio,
              })}
            </Descriptions.Item>
            <Descriptions.Item label="到仓日期">{detail.arrivalDate ?? EMPTY}</Descriptions.Item>
            <Descriptions.Item label="单据金额" span={2}>
              <MoneyCell value={detail.amountTotal} currency={currencySign(detail.currencyCode)} />
              {detail.currencyCode && <Typography.Text type="secondary"> {detail.currencyCode}</Typography.Text>}
            </Descriptions.Item>
          </Descriptions>

          <section aria-label="明细 × ItemID">
            <Typography.Title level={5}>明细 × ItemID</Typography.Title>
            <Table<PurchaseBoardRow>
              rowKey="id"
              size="small"
              pagination={false}
              columns={lineColumns}
              dataSource={detail.lines}
              scroll={{ x: 1100 }}
            />
          </section>

          <section aria-label="收货记录">
            <Typography.Title level={5}>收货记录</Typography.Title>
            {detail.receipts.length === 0
              ? <Typography.Text type="secondary">暂无收货单</Typography.Text>
              : (
                <span className="purchase-board__receipts">
                  {detail.receipts.map((receipt) => (
                    <Tag key={receipt.receiptOrderSn} color={receipt.isArrivalReceipt ? "green" : "default"}>
                      {receipt.receiptOrderSn}{receipt.isArrivalReceipt ? "（到仓）" : ""}
                    </Tag>
                  ))}
                </span>
              )}
            <Typography.Paragraph type="secondary" className="purchase-board__hint">
              仅显示收货单号；到仓 = 累计收货首次达到采购量 × 到仓比例的那一单。
            </Typography.Paragraph>
          </section>

          <section aria-label="计划链">
            <Typography.Title level={5}>计划链</Typography.Title>
            <Table<PurchaseOrderPlanRef>
              rowKey="planSn"
              size="small"
              pagination={false}
              columns={planColumns}
              dataSource={detail.plans}
              locale={{ emptyText: "该采购单未关联采购计划" }}
            />
          </section>

          <section aria-label="交期样本">
            <Typography.Title level={5}>SKU 实际采购交期</Typography.Title>
            <Table<SkuCycle>
              rowKey="sku"
              size="small"
              pagination={false}
              columns={cycleColumns}
              dataSource={detail.skuCycles}
              locale={{ emptyText: "暂无交期数据" }}
            />
          </section>
        </div>
      )}
    </Modal>
  );
}

export default PurchaseOrderDetailModal;

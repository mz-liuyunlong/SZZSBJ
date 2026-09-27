/** 待采购计划 drill-down (S2 card): approved plans not yet on any purchase order. */
import { Alert, Drawer, Switch, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { PendingPurchasePlan, PendingPurchasePlanListResult } from "@/pages/pmc/purchase-board/purchaseBoardTypes";

interface PendingPlansDrawerProps {
  open: boolean;
  data?: PendingPurchasePlanListResult;
  loading: boolean;
  errorText?: string;
  page: number;
  pageSize: number;
  overdueOnly: boolean;
  onPageChange: (page: number, pageSize: number) => void;
  onOverdueOnlyChange: (checked: boolean) => void;
  onClose: () => void;
}

const columns: ColumnsType<PendingPurchasePlan> = [
  { key: "planSn", title: "计划号", dataIndex: "planSn" },
  { key: "sku", title: "SKU", dataIndex: "sku", render: (value: string | null) => value ?? "—" },
  { key: "productName", title: "产品名", dataIndex: "productName", ellipsis: true, render: (value: string | null) => value ?? "—" },
  {
    key: "store",
    title: "店铺",
    render: (_, plan) => (plan.store.attributed ? plan.store.name ?? plan.store.id ?? "—" : <Typography.Text type="warning">未归属店铺</Typography.Text>),
  },
  { key: "qty", title: "计划量", dataIndex: "quantityPlan", render: (value: number | null) => value ?? "—" },
  { key: "created", title: "创建日期", dataIndex: "planCreateDate", render: (value: string | null) => value ?? "—" },
  {
    key: "pending",
    title: "待采购天数",
    render: (_, plan) => (
      plan.pendingDays === null
        ? "—"
        : (
          <span>
            {plan.pendingDays} 天
            {plan.pendingSinceEstimated && <Typography.Text type="secondary">（估算）</Typography.Text>}
          </span>
        )
    ),
  },
  {
    key: "overdue",
    title: "超时",
    render: (_, plan) => (plan.overdueDays > 0 ? <Tag color="red">超时 {plan.overdueDays} 天</Tag> : <Tag>未超时</Tag>),
  },
  { key: "remark", title: "备注 ItemID", dataIndex: "remarkItemId", render: (value: string | null) => value ?? "—" },
];

function PendingPlansDrawer({
  open,
  data,
  loading,
  errorText,
  page,
  pageSize,
  overdueOnly,
  onPageChange,
  onOverdueOnlyChange,
  onClose,
}: PendingPlansDrawerProps) {
  return (
    <Drawer
      title="待采购计划（已审批未转单）"
      open={open}
      width={960}
      onClose={onClose}
      destroyOnHidden
      extra={(
        <label className="purchase-board__followup-toggle">
          <Switch size="small" aria-label="仅看超时" checked={overdueOnly} onChange={onOverdueOnlyChange} />
          <span>仅看超时</span>
        </label>
      )}
    >
      {errorText && <Alert type="error" showIcon message={errorText} />}
      <Typography.Paragraph type="secondary" className="purchase-board__hint">
        采购计划不进看板主表；此处列出领星状态为“已审批待采购”且尚未出现在任何采购单明细上的计划。
        超时阈值 {data ? `${data.thresholdDays} 天` : "—"}（规则表 s2_pending_days）；未归属店铺的计划不计超时。
      </Typography.Paragraph>
      <Table<PendingPurchasePlan>
        rowKey="planSn"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={data?.rows ?? []}
        scroll={{ x: 1000 }}
        pagination={{
          current: page,
          pageSize,
          total: data?.total ?? 0,
          showSizeChanger: true,
          pageSizeOptions: ["50", "100", "200"],
          showTotal: (count) => `共 ${count.toLocaleString()} 条计划`,
          onChange: onPageChange,
        }}
      />
    </Drawer>
  );
}

export default PendingPlansDrawer;

/** Read-only static structure for inspecting one product-ID order-profit row. */
import {
  AppstoreOutlined,
  BarChartOutlined,
  DollarCircleOutlined,
  LineChartOutlined,
  NotificationOutlined,
  RiseOutlined,
  RollbackOutlined,
  ShopOutlined,
  TagsOutlined,
} from "@ant-design/icons";
import { Button, Card, Modal, Typography } from "antd";
import type { OrderProfitRow } from "@/pages/sales/orderProfitTypes";

interface OrderProfitDetailModalProps {
  row?: OrderProfitRow;
  onClose: () => void;
}

function OrderProfitDetailModal({ row, onClose }: OrderProfitDetailModalProps) {
  if (!row) return null;

  const money = (value: number | null) => value == null ? "—" : `${value.toFixed(2)}`;
  const percent = (value: number | null) => value == null ? "—" : `${value.toFixed(2)}%`;

  const items = [
    { label: "商品ID / 品名", value: `${row.productId} / ${row.productName}`, icon: <TagsOutlined />, tone: "green" },
    { label: "SKU / MSKU", value: `${row.sku} / ${row.msku}`, icon: <AppstoreOutlined />, tone: "purple" },
    { label: "平台 / 店铺 / 负责人", value: `${row.platform} · ${row.store} · ${row.owner}`, icon: <ShopOutlined /> },
    { label: "销量 / 订单量 / 销售额", value: `${row.salesVolume} / ${row.orderCount} / $${row.salesAmount.toFixed(2)}`, icon: <BarChartOutlined /> },
    { label: "退款 / 广告", value: `$${(row.refundAmount ?? 0).toFixed(2)} / $${row.adSpend.toFixed(2)}`, icon: <RollbackOutlined />, tone: "orange" },
    { label: "配送 / 佣金", value: `${money(row.wfsDeliveryFee)} / ${row.commission.toFixed(2)}`, icon: <NotificationOutlined />, tone: "red" },
    { label: "总成本", value: `${money(row.totalCost)} / ${row.costStatus}`, icon: <DollarCircleOutlined />, tone: "gray" },
    { label: "订单利润", value: `${money(row.orderProfit)} / ${percent(row.profitMargin)}`, icon: <RiseOutlined />, tone: "purple" },
    { label: "近 7 天趋势", value: row.sevenDaySales.join(" / "), icon: <LineChartOutlined />, tone: "green" },
  ];

  return (
    <Modal
      className="order-profit-detail-modal"
      title="订单利润详情"
      open
      centered
      destroyOnHidden
      width="min(1100px, calc(100vw - 32px))"
      footer={<Button onClick={onClose}>关闭</Button>}
      onCancel={onClose}
    >
      <Typography.Paragraph type="secondary">
        当前内容仅用于 No-API 商品ID维度利润页面结构验收，不代表真实销售、费用或利润口径。
      </Typography.Paragraph>
      <div className="order-profit-detail-modal__grid">
        {items.map((item) => (
          <Card key={item.label} size="small" className={`order-profit-detail-modal__card order-profit-detail-modal__card--${item.tone ?? "blue"}`}>
            <span className="order-profit-detail-modal__icon" aria-hidden="true">{item.icon}</span>
            <span className="order-profit-detail-modal__copy">
              <Typography.Text type="secondary">{item.label}</Typography.Text>
              <Typography.Text>{item.value}</Typography.Text>
            </span>
          </Card>
        ))}
      </div>
    </Modal>
  );
}

export default OrderProfitDetailModal;

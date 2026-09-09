/** Read-only static structure for inspecting one daily-sales acceptance row. */
import {
  AppstoreOutlined,
  BarChartOutlined,
  FileTextOutlined,
  LineChartOutlined,
  NotificationOutlined,
  RiseOutlined,
  RollbackOutlined,
  ShopOutlined,
  TagsOutlined,
} from "@ant-design/icons";
import { Button, Card, Modal, Typography } from "antd";
import type { DailySalesRow } from "@/pages/sales/dailySalesTypes";

interface SalesDetailModalProps {
  row?: DailySalesRow;
  onClose: () => void;
}

function SalesDetailModal({ row, onClose }: SalesDetailModalProps) {
  if (!row) return null;

  const items = [
    { label: "基础信息", value: `${row.date} · ${row.store} · ${row.owner}`, icon: <ShopOutlined /> },
    { label: "MSKU / 商品ID", value: `${row.msku} / ${row.productId}`, icon: <TagsOutlined />, tone: "green" },
    { label: "SKU / 品名", value: `${row.sku} / ${row.productName}`, icon: <AppstoreOutlined />, tone: "purple" },
    { label: "销量 / 订单量 / 销售额", value: `${row.salesVolume} / ${row.orderCount} / $${row.salesAmount.toFixed(2)}`, icon: <BarChartOutlined /> },
    { label: "退货 / 退款", value: `${row.returnCount} / $${row.refundAmount.toFixed(2)}`, icon: <RollbackOutlined />, tone: "orange" },
    { label: "广告 / 成本", value: `$${row.adSpend.toFixed(2)} / ${row.costStatus}`, icon: <NotificationOutlined />, tone: "red" },
    { label: "利润", value: `$${row.orderProfit.toFixed(2)} / ${row.profitMargin.toFixed(2)}%`, icon: <RiseOutlined />, tone: "purple" },
    { label: "近 7 天趋势", value: row.sevenDaySales.join(" / "), icon: <LineChartOutlined />, tone: "green" },
    { label: "运营日志摘要", value: row.operationLog, icon: <FileTextOutlined />, tone: "gray" },
  ];

  return (
    <Modal
      className="daily-sales-detail-modal"
      title="销售详情"
      open
      centered
      destroyOnHidden
      width="min(1100px, calc(100vw - 32px))"
      footer={<Button onClick={onClose}>关闭</Button>}
      onCancel={onClose}
    >
      <Typography.Paragraph type="secondary">
        当前内容仅用于 No-API 页面结构验收，不代表真实销售、费用或利润口径。
      </Typography.Paragraph>
      <div className="daily-sales-detail-modal__grid">
        {items.map((item) => (
          <Card key={item.label} size="small" className={`daily-sales-detail-modal__card daily-sales-detail-modal__card--${item.tone ?? "blue"}`}>
            <span className="daily-sales-detail-modal__icon" aria-hidden="true">{item.icon}</span>
            <span className="daily-sales-detail-modal__copy">
              <Typography.Text type="secondary">{item.label}</Typography.Text>
              <Typography.Text>{item.value}</Typography.Text>
            </span>
          </Card>
        ))}
      </div>
    </Modal>
  );
}

export default SalesDetailModal;

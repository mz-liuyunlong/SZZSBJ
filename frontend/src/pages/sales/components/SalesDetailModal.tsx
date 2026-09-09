/** Read-only static structure for inspecting one daily-sales acceptance row. */
import { Descriptions, Modal, Typography } from "antd";
import type { DailySalesRow } from "../dailySalesTypes";

interface SalesDetailModalProps {
  row?: DailySalesRow;
  onClose: () => void;
}

function SalesDetailModal({ row, onClose }: SalesDetailModalProps) {
  if (!row) return null;

  const items = [
    ["基础信息", `${row.date} · ${row.store} · ${row.owner}`],
    ["MSKU / 商品ID", `${row.msku} / ${row.productId}`],
    ["SKU / 品名", `${row.sku} / ${row.productName}`],
    ["销量 / 订单量 / 销售额", `${row.salesVolume} / ${row.orderCount} / $${row.salesAmount.toFixed(2)}`],
    ["退货 / 退款", `${row.returnCount} / $${row.refundAmount.toFixed(2)}`],
    ["广告 / 成本", `$${row.adSpend.toFixed(2)} / ${row.costStatus}`],
    ["利润", `$${row.orderProfit.toFixed(2)} / ${row.profitMargin.toFixed(2)}%`],
    ["近 7 天趋势", row.sevenDaySales.join(" / ")],
    ["运营日志摘要", row.operationLog],
  ].map(([label, children]) => ({ key: label, label, children }));

  return (
    <Modal
      title="销售详情"
      open
      centered
      destroyOnHidden
      width="min(880px, calc(100vw - 32px))"
      footer={null}
      onCancel={onClose}
    >
      <Typography.Paragraph type="secondary">
        当前内容仅用于 No-API 页面结构验收，不代表真实销售、费用或利润口径。
      </Typography.Paragraph>
      <Descriptions bordered size="small" column={{ xs: 1, sm: 2 }} items={items} />
    </Modal>
  );
}

export default SalesDetailModal;

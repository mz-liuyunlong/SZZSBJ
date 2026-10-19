/** Details use the backend trace contract; missing outbound publication stays explicitly unknown. */
import { Alert, Button, Descriptions, Drawer, Empty, List, Spin, Tag, Typography } from "antd";
import { domesticErrorText } from "../domesticWarehouseApi";
import { useDomesticTrace } from "../domesticWarehouseQueries";
import { formatQuantity } from "../domesticWarehouseTypes";

export default function DomesticBatchDetail({ id, scope, onClose }: { id?: string; scope: string; onClose: () => void }) {
  const query = useDomesticTrace(id, scope);
  const trace = query.data?.data;
  const batch = trace?.batch;
  return <Drawer title="收货批次详情" width={640} open={Boolean(id)} onClose={onClose} destroyOnClose>
    {query.isPending && <Spin tip="正在加载批次详情"><div className="domestic-board__detail-loading" /></Spin>}
    {query.error && <Alert type="error" showIcon message={domesticErrorText(query.error)}
      action={<Button onClick={() => void query.refetch()}>重试</Button>} />}
    {batch && <div className="domestic-board__detail">
      <Alert type="info" showIcon message="到仓日期取收货单实际收货日期；缺失时保持未知，不使用入库日期代替。" />
      <Descriptions bordered size="small" column={2} items={[
        { key: "receipt", label: "收货单号", children: batch.receipt_order_sn, span: 2 },
        { key: "purchase", label: "采购单号", children: batch.purchase_order_sn ?? "—", span: 2 },
        { key: "sku", label: "SKU", children: batch.sku ?? "—" },
        { key: "warehouse", label: "仓库 ID", children: batch.source_warehouse_id ?? "—" },
        { key: "date", label: "到仓日期（收货单）", children: batch.received_business_date ?? "待核实" },
        { key: "days", label: "在仓天数", children: batch.days_in_warehouse === null ? "—" : `${batch.days_in_warehouse} 天` },
        { key: "quantity", label: "实收数量", children: formatQuantity(batch.received_qty) },
        { key: "line", label: "收货明细行", children: batch.line_ordinal + 1 },
      ]} />
      <Typography.Title level={5}>库存批次关联</Typography.Title>
      <List dataSource={batch.links} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未关联库存批次" /> }}
        renderItem={(link) => <List.Item>
          <List.Item.Meta title={link.batch_order_sn ?? "入库单待核实"}
            description={`批次 ${link.batch_no ?? "—"} · 店铺 ${link.store_id ?? "—"} · 对应 ${formatQuantity(link.mapped_qty)} 件`} />
          <Tag color={link.mapping_status === "matched" ? "success" : "warning"}>
            {link.mapping_status === "matched" ? "已关联" : "待关联"}</Tag>
        </List.Item>} />
      <Alert type="warning" showIcon message="出库追溯尚未接入"
        description="目前不能据此判断已发出数量或出仓周期，未接入不代表尚未发货。" />
    </div>}
  </Drawer>;
}

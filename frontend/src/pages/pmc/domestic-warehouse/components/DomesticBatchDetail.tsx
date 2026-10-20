import { Alert, Button, Descriptions, Drawer, Spin, Table, Typography } from "antd";
import { domesticErrorText } from "../domesticWarehouseApi";
import { useDomesticTrace } from "../domesticWarehouseQueries";
import { arrivalSourceText, formatQuantity, type BatchComponent, type InboundEvent } from "../domesticWarehouseTypes";

export default function DomesticBatchDetail({ id, scope, expectedPublication, onClose }: {
  id?: string; scope: string; expectedPublication?: string | null; onClose: () => void;
}) {
  const query = useDomesticTrace(id, scope, true);
  const trace = query.data?.data;
  const batch = trace?.batch;
  const versionChanged = expectedPublication && batch && batch.publication_id !== expectedPublication;
  return <Drawer title="入库批次核对 · 接口数据" width={900} open={Boolean(id)} onClose={onClose} destroyOnHidden>
    {query.isPending && <Spin tip="正在加载详情"><div className="domestic-board__detail-loading" /></Spin>}
    {query.error && <Alert type="error" showIcon message={domesticErrorText(query.error)} action={<Button onClick={() => void query.refetch()}>重试详情</Button>} />}
    {versionChanged && <Alert type="warning" showIcon message="数据已更新，详情与列表版本不同" description="请关闭详情并刷新列表后重新核对，避免比较不同采集版本。" />}
    {batch && <div className="domestic-board__detail">
      <Alert type="info" showIcon message="入库总量属于 IB×SKU，跨店铺行不可相加。批次余额为当前快照，不代表未发货数量。"
        description="到仓日期来自入库流水；批次日期补充会单独标明。历史窗口有限，未声明全历史完整。" />
      <Descriptions bordered size="small" column={2} items={[
        { key: "inbound", label: "入库单号", children: batch.inbound_order_sn }, { key: "sku", label: "SKU", children: batch.sku },
        { key: "product", label: "产品", children: batch.product_name || "—", span: 2 },
        { key: "purchase", label: "采购单号", children: batch.purchase_order_sns.join(" / ") || "—", span: 2 },
        { key: "account", label: "来源账号", children: batch.source_account_ref }, { key: "warehouse", label: "仓库", children: `${batch.warehouse_name ?? ""} ${batch.source_warehouse_id}` },
        { key: "store", label: "店铺", children: batch.store_id ? `${batch.store_name ?? ""} ${batch.store_id}` : "归属未知" },
        { key: "parent", label: "入库总量（IB×SKU）", children: formatQuantity(batch.parent_inbound_qty) },
        { key: "storeQty", label: "店铺分摊入库量", children: "未知（无分摊证据）" }, { key: "balance", label: "当前批次余额", children: formatQuantity(batch.balance_num) },
        { key: "date", label: "到仓日期（入库）", children: batch.arrival_business_date ?? "待核实" },
        { key: "source", label: "日期来源", children: arrivalSourceText[batch.arrival_source] },
        { key: "raw", label: "来源时间原值", children: batch.inbound_at_raw ?? "—" },
        { key: "days", label: "在仓天数", children: batch.days_in_warehouse === null ? "—" : `${batch.days_in_warehouse} 天` },
        { key: "version", label: "发布版本", children: batch.publication_id ?? "—", span: 2 },
      ]} />
      <Typography.Title level={5}>批次组成与余额</Typography.Title>
      <Table<BatchComponent> size="small" rowKey={(r) => JSON.stringify([r.batch_no, r.store_id])} pagination={false} dataSource={batch.batch_details} scroll={{ x: 700 }} columns={[
        { title: "批次号", dataIndex: "batch_no" }, { title: "店铺 ID", dataIndex: "store_id", render: (v: string | null) => v ?? "未知" },
        { title: "余额", dataIndex: "balance_num", render: (v: number | null) => formatQuantity(v) },
        { title: "来源批次", dataIndex: "source_batch_nos", render: (v: string[]) => v.join(" / ") || "—" },
        { title: "收货单关联", dataIndex: "receipt_order_sns", render: (v: string[]) => v.join(" / ") || "—" },
      ]} locale={{ emptyText: "尚无关联批次，余额保持未知" }} />
      <Typography.Title level={5}>入库流水证据</Typography.Title>
      <Table<InboundEvent> size="small" rowKey={(r) => JSON.stringify([r.statement_id, r.order_sn, r.opt_time])} pagination={false} dataSource={trace.inbound_events} scroll={{ x: 700 }} columns={[
        { title: "流水 ID", dataIndex: "statement_id" }, { title: "单号", dataIndex: "order_sn" }, { title: "子类型", dataIndex: "sub_type" },
        { title: "数量（原值）", dataIndex: "product_total" }, { title: "质检数量（原值）", dataIndex: "product_qc_num" }, { title: "操作时间（原值）", dataIndex: "opt_time" },
      ]} locale={{ emptyText: "采集窗口内没有入库流水；批次历史补充不代表历史数量已核实" }} />
      <Alert type="warning" showIcon message="出库与打包追溯尚未接入" description="不能据此判断是否已发货、出仓周期或打包状态。" />
    </div>}
  </Drawer>;
}

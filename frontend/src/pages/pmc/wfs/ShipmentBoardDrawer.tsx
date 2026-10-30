import { Descriptions, Drawer, List, Table, Tag, Timeline, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listCases } from "./exceptionCenterApi";
import { boardError, getShipment } from "./shipmentBoardApi";
import { STATUS_TONE, type ShipmentGoodsLine } from "./shipmentBoardTypes";

const labelTone: Record<string, string> = { READY: "success", PENDING: "processing", FAILED: "error" };
const fmt = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", dateStyle: "short", timeStyle: "short" });
const time = (v?: string | null) => (v ? fmt.format(new Date(v)) : "—");
const num = (v?: number | null) => (v === null || v === undefined ? "—" : String(v));
const str = (v: unknown) => (v === null || v === undefined || v === "" ? "—" : String(v));

export default function ShipmentBoardDrawer({ rowId, scope, onClose }: { rowId: string; scope: string; onClose: () => void }) {
  const detail = useQuery({
    queryKey: ["wfs-shipment-board", scope, "detail", rowId],
    queryFn: ({ signal }) => getShipment(rowId, signal),
    enabled: Boolean(rowId),
  });
  const data = detail.data?.data;
  const related = useQuery({
    queryKey: ["wfs-exception-center", scope, "related", data?.shipment_id],
    queryFn: ({ signal }) =>
      listCases(
        {
          keyword: "",
          keyword_field: "shipment",
          shipment_id: data!.shipment_id,
          only_test: false,
          due_soon: false,
        },
        1,
        20,
        signal,
      ),
    enabled: Boolean(data?.shipment_id),
    retry: false,
  });
  const timeline = data
    ? [
        { key: "created", label: "创建", at: data.created_at, done: Boolean(data.created_at) },
        { key: "await", label: "待送达（已发往仓库）", at: data.to_await_at, done: Boolean(data.to_await_at) },
        { key: "receive", label: "开始收货", at: data.to_receive_at, done: Boolean(data.to_receive_at) },
        data.to_cancelled_at
          ? { key: "cancel", label: "已取消", at: data.to_cancelled_at, done: true }
          : { key: "closed", label: "已关闭", at: data.to_closed_at, done: Boolean(data.to_closed_at) },
      ]
    : [];
  return (
    <Drawer width={760} open title={data?.shipment_id ?? "货件详情"} onClose={onClose} destroyOnClose>
      {detail.isError && <Typography.Text type="danger">{boardError(detail.error, "detail")}</Typography.Text>}
      {data && <>
        <Typography.Title level={5}>货件</Typography.Title>
        <Descriptions size="small" bordered column={2} items={[
          { key: "status", label: "状态", children: <Tag color={data.lingxing_sync_status === "PENDING" ? "error" : STATUS_TONE[String(data.status)] ?? "default"}>{data.status_label}</Tag> },
          { key: "sync", label: "领星同步", children: data.lingxing_sync_status === "SYNCED" ? `已同步（${data.cargo_sync_status ?? "—"}）` : "待领星同步" },
          { key: "inbound", label: "入库单号", children: str(data.inbound_order_id) },
          { key: "store", label: "店铺", children: data.store_name ?? data.store_id },
          { key: "pk", label: "系统打包单", children: data.pk ?? "人工 / 外部创建" },
          { key: "type", label: "货件类型", children: data.its === null || data.its === undefined ? "—" : data.its ? "ITS" : "WFS" },
          { key: "creator", label: "领星创建人", children: str(data.creator) },
          { key: "test", label: "测试标记", children: data.business_test ? "业务测试" : "正式" },
          { key: "addr", label: "配送地址", children: str(data.distribution_addresses), span: 2 },
        ]} />

        <Typography.Title level={5} style={{ marginTop: 16 }}>节点</Typography.Title>
        <Timeline
          items={timeline.map((t) => ({
            key: t.key,
            color: t.done ? "green" : "gray",
            children: <span>{t.label}<span className="wfs-pending__sub" style={{ marginLeft: 8 }}>{time(t.at)}</span></span>,
          }))}
        />

        <Typography.Title level={5} style={{ marginTop: 8 }}>商品（申报 / 发出 / Received / 破损）</Typography.Title>
        {data.lingxing_note && <Typography.Paragraph type="secondary">{data.lingxing_note}</Typography.Paragraph>}
        <Table<ShipmentGoodsLine>
          size="small"
          pagination={false}
          rowKey={(g, i) => `${g.msku ?? g.sku ?? ""}-${i}`}
          dataSource={data.goods}
          locale={{ emptyText: "领星未返回商品行" }}
          columns={[
            { title: "MSKU", dataIndex: "msku", width: 140 },
            { title: "SKU · 品名", render: (_, g) => <span>{g.sku ?? "—"}<br /><span className="wfs-pending__sub">{g.product_name ?? "—"}</span></span> },
            { title: "GTIN", dataIndex: "gtin", width: 140 },
            { title: "申报", width: 70, render: (_, g) => num(g.declare_num) },
            { title: "发出", width: 70, render: (_, g) => num(g.shipments_num) },
            { title: "Received", width: 90, render: (_, g) => num(g.received_num) },
            { title: "破损", width: 70, render: (_, g) => num(g.damaged_qty) },
          ]}
          summary={() => (
            <Table.Summary.Row>
              <Table.Summary.Cell index={0} colSpan={3}>合计</Table.Summary.Cell>
              <Table.Summary.Cell index={3}>{num(data.declared_units)}</Table.Summary.Cell>
              <Table.Summary.Cell index={4}>{num(data.shipped_units)}</Table.Summary.Cell>
              <Table.Summary.Cell index={5}>{num(data.received_units)}</Table.Summary.Cell>
              <Table.Summary.Cell index={6}>{num(data.damaged_units)}</Table.Summary.Cell>
            </Table.Summary.Row>
          )}
        />

        <Typography.Title level={5} style={{ marginTop: 16 }}>领星发货单（SP）</Typography.Title>
        {data.shipping_lists.length === 0 ? (
          <Typography.Paragraph type="secondary">领星尚无关联发货单；发货仓 / 物流 / 到港以发货单为准。</Typography.Paragraph>
        ) : (
          <List
            size="small"
            dataSource={data.shipping_lists}
            renderItem={(s) => (
              <List.Item>
                <Descriptions size="small" column={3} items={[
                  { key: "code", label: "发货单", children: str(s.shipping_code) },
                  { key: "st", label: "状态", children: str(s.shipping_status) },
                  { key: "wh", label: "发货仓", children: str(s.warehouse_id) },
                  { key: "lg", label: "物流", children: `${str(s.logistics_code)} / 渠道 ${str(s.logistics_channel_id)}` },
                  { key: "num", label: "运单", children: Array.isArray(s.logistics_numbers) && s.logistics_numbers.length ? (s.logistics_numbers as string[]).join(", ") : "—" },
                  { key: "box", label: "箱 / 件", children: `${str(s.box_num_total)} / ${str(s.shipments_num_total)}` },
                  { key: "dep", label: "实际发货", children: str(s.actual_delivery_time) },
                  { key: "arr", label: "到港", children: str(s.arrival_time) },
                  { key: "eta", label: "预计到港", children: str(s.expected_arrival_time) },
                ]} />
              </List.Item>
            )}
          />
        )}

        {data.ticket_id && (
          <>
            <Typography.Title level={5} style={{ marginTop: 16 }}>本系统创建记录</Typography.Title>
            <Descriptions size="small" bordered column={2} items={[
              { key: "op", label: "创建状态", children: `${data.creation_state ?? "—"} / 票 ${data.ticket_number ?? "—"}` },
              { key: "label", label: "箱唛", children: <Tag color={labelTone[data.label_state ?? "PENDING"]}>{data.label_state ?? "—"}</Tag> },
              { key: "alloc", label: "分箱", children: data.allocation ? `${str(data.allocation.boxes)} 箱 / ${str(data.allocation.units)} 件` : "—" },
              { key: "exp", label: "预计送达", children: str(data.expected_delivery_at) },
            ]} />
          </>
        )}

        <Typography.Title level={5} style={{ marginTop: 16 }}>关联异常</Typography.Title>
        {(related.data?.data.items.length ?? 0) === 0 ? (
          <Typography.Paragraph type="secondary">当前货件暂无异常案件。</Typography.Paragraph>
        ) : (
          <List
            size="small"
            dataSource={related.data?.data.items ?? []}
            renderItem={(item) => (
              <List.Item>
                <Link to={`/pmc/wfs/exceptions?case=${item.id}`}>{item.rule_label}</Link>
                <Tag style={{ marginLeft: 8 }}>{item.status_label}</Tag>
              </List.Item>
            )}
          />
        )}
      </>}
    </Drawer>
  );
}

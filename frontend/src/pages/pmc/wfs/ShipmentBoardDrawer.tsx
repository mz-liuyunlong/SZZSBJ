import { Descriptions, Drawer, List, Tag, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listCases } from "./exceptionCenterApi";
import { boardError, getShipment } from "./shipmentBoardApi";

const labelTone: Record<string, string> = { READY: "success", PENDING: "processing", FAILED: "error" };
const time = (v?: string | null) => v ? new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Taipei", dateStyle: "short", timeStyle: "short" }).format(new Date(v)) : "—";

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
  return (
    <Drawer width={680} open title={data?.shipment_id ?? "货件详情"} onClose={onClose} destroyOnClose>
      {detail.isError && <Typography.Text type="danger">{boardError(detail.error, "detail")}</Typography.Text>}
      {data && <>
        <Typography.Title level={5}>创建信息</Typography.Title>
        <Descriptions size="small" bordered column={1} items={[
          { key: "pk", label: "系统打包单", children: data.pk },
          { key: "store", label: "店铺", children: data.store_name ?? data.store_id },
          { key: "type", label: "货件类型", children: data.its ? "ITS" : "WFS" },
          { key: "created", label: "创建时间", children: time(data.created_at) },
          { key: "op", label: "创建状态", children: `${data.creation_state} / 票 ${data.ticket_number}` },
        ]} />
        <Typography.Title level={5} style={{ marginTop: 16 }}>标签状态</Typography.Title>
        <Tag color={labelTone[data.label_state]}>{data.label_state}</Tag>
        <Typography.Title level={5} style={{ marginTop: 16 }}>商品与 PK</Typography.Title>
        <Descriptions size="small" bordered column={1} items={[
          { key: "sku", label: "SKU · 品名", children: `${data.sku ?? "—"} · ${data.product_name ?? "—"}` },
          { key: "item", label: "Item / GTIN / MSKU", children: `${data.item_id ?? "—"} / ${data.gtin ?? "—"} / ${data.msku ?? "—"}` },
          { key: "test", label: "测试标记", children: data.business_test ? "业务测试" : "正式" },
        ]} />
        <Typography.Title level={5} style={{ marginTop: 16 }}>领星履约（M1 占位）</Typography.Title>
        <Typography.Paragraph type="secondary">{data.lingxing_note}</Typography.Paragraph>
        <Descriptions size="small" bordered column={1} items={[
          { key: "sync", label: "同步状态", children: "待领星同步" },
          { key: "ship", label: "实际发货 / 申报 / Received", children: "— / — / —" },
        ]} />
        <Typography.Title level={5} style={{ marginTop: 16 }}>关联异常</Typography.Title>
        {(related.data?.data.items.length ?? 0) === 0 ? (
          <Typography.Paragraph type="secondary">当前货件暂无异常案件（M1 需规则命中或测试数据）。</Typography.Paragraph>
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

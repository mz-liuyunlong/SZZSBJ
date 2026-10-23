/** Warehouse history reuses immutable packing events, with scope-isolated pagination. */
import { Alert, Button, Descriptions, Drawer, Pagination, Space, Table } from "antd";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getWarehouseEvents, getWarehouseOrder, warehouseError } from "./packingWarehouseApi";
export default function PackingWarehouseDetails({ id, scope, onClose }: { id: string; scope: string; onClose: () => void }) {
  const [page, setPage] = useState(1);
  const detail = useQuery({ queryKey: ["domestic-packing-warehouse", scope, "detail", id], queryFn: ({ signal }) => getWarehouseOrder(id, signal) });
  const events = useQuery({ queryKey: ["domestic-packing-warehouse", scope, "events", id, page], queryFn: ({ signal }) => getWarehouseEvents(id, page, signal) });
  const auditTime = (value: string) => new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
  const packageSources: Record<string, string> = { warehouse_measurement: "仓库实填", warehouse_draft: "仓库暂存实填", product_snapshot: "产品资料" };
  const row = detail.data?.data; const error = detail.error ?? events.error;
  const kinds: Record<string, string> = { approve: "审批通过", boxes: "保存装箱", done: "打包完成", customs: "修改报关", note: "延迟备注", unpacked: "未装处置", rebox: "改装箱", ib: "登记补入库单", sync: "同步校验" };
  return <Drawer open title="仓库打包单详情与审计" width={860} onClose={onClose}>
    {error && <Alert type="error" message={warehouseError(error)} action={<Button onClick={() => { void detail.refetch(); void events.refetch(); }}>重试</Button>} />}
    {row && <Descriptions bordered size="small" column={2} items={[{ key: "pk", label: "PK", children: row.pk }, { key: "sku", label: "SKU", children: row.sku }, { key: "arrival", label: "到仓日期（入库日）", children: row.arrival_date ?? "未知" }, { key: "receipt", label: "实际收货日", children: row.received_dates.join(" / ") || "待核实" }, { key: "extra", label: "额外库存来源", children: row.extra_allocations?.length ? row.extra_allocations.map((a) => `${a.inbound_order_sn}：${a.quantity} 件`).join("；") : "无额外占用" }, { key: "qty", label: "审批 / 装箱件数", children: `${row.approved_quantity} / ${row.box_set?.total_qty ?? "—"}` }, { key: "reason", label: "数量差异原因", children: row.box_set?.variance_reason ?? row.variance_case?.reason ?? "—" }, { key: "complete", label: "完成时间", children: row.box_set?.completed_at ? auditTime(row.box_set.completed_at) : "未完成" }, { key: "source", label: "包装资料来源", children: packageSources[row.box_set?.package_snapshot?.source ?? ""] ?? (row.product_requirement.state === "complete" ? "产品资料完整" : "资料待核实") }, { key: "external", label: "发货 / 领星箱规", children: "未接入，不代表已发货或已写入" }, { key: "v", label: "订单 / 装箱版本", children: `${row.version} / ${row.box_set?.version ?? "—"}` }]} />}
    <Table size="small" rowKey="id" loading={events.isFetching} dataSource={events.data?.data.items ?? []} pagination={false} expandable={{ expandedRowRender: (event) => <Space direction="vertical"><span>原因：{event.reason ?? "—"}</span><details><summary>查看事件前后快照</summary><pre className="domestic-packing__audit">{JSON.stringify({ before: event.before, result: event.result }, null, 2)}</pre></details></Space> }} columns={[{ title: "操作", dataIndex: "kind", render: (kind: string, event) => event.result.command_outcome === "blocked" ? `${kinds[kind] ?? kind}受阻` : kinds[kind] ?? kind }, { title: "操作人", dataIndex: "actor_uid" }, { title: "订单版本", dataIndex: "order_version" }, { title: "操作时间（北京时间）", dataIndex: "occurred_at", render: auditTime }]} />
    <Pagination current={page} pageSize={20} total={events.data?.data.total ?? 0} onChange={setPage} />
  </Drawer>;
}

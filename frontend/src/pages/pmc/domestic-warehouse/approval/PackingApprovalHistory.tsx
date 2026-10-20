/** Immutable local approval outcomes and per-order audit trail. */
import { Alert, Button, Descriptions, Drawer, Empty, Table, Tag } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { approvalErrorText, getPackingEvents, type PackingOrder } from "./packingApprovalApi";
interface Props { open: boolean; onClose: () => void; rows: PackingOrder[]; total: number; page: number; onPage: (page: number) => void; loading: boolean; error: unknown; retry: () => void; scope: string }
export default function PackingApprovalHistory(p: Props) {
  const [selected, setSelected] = useState<PackingOrder>();
  const events = useQuery({ queryKey: ["packing-events", p.scope, selected?.id], queryFn: ({ signal }) => getPackingEvents(selected!.id, signal), enabled: !!selected && p.open });
  return <Drawer title="打包审批记录（本地验证）" open={p.open} onClose={p.onClose} width={980}>
    {p.error ? <Alert type="error" message={approvalErrorText(p.error)} action={<Button onClick={p.retry}>重试</Button>} /> : null}
    <Table<PackingOrder> rowKey="id" size="small" loading={p.loading} dataSource={p.error ? [] : p.rows}
      pagination={{ current: p.page, pageSize: 20, total: p.total, onChange: p.onPage }} locale={{ emptyText: <Empty description="暂无审批记录" /> }} columns={[
        { title: "打包单号", render: (_, r) => r.pk ?? "驳回（未发PK）" },
        { title: "入库单 / SKU", render: (_, r) => `${r.snapshot.inbound_order_sn} / ${r.snapshot.sku}` },
        { title: "状态", render: (_, r) => <Tag color={r.status === "approved" ? "success" : "error"}>{r.status === "approved" ? "已通过" : "已驳回"}</Tag> },
        { title: "数量", dataIndex: "qty" }, { title: "记录", render: (_, r) => <Button onClick={() => setSelected(r)}>查看审计</Button> },
      ]} />
    <Drawer title="审批审计" open={!!selected && p.open} onClose={() => setSelected(undefined)} width={620}>
      {selected && <Descriptions column={1} items={[
        { key: "pk", label: "打包单", children: selected.pk ?? "未发号" },
        { key: "actor", label: "审批人UID", children: selected.actor_uid },
        { key: "date", label: "审批时间", children: selected.created_at },
        { key: "note", label: "原因", children: selected.note ?? "—" },
        { key: "source", label: "来源版本", children: selected.snapshot.publication_id },
      ]} />}
      {events.error ? <Alert type="error" message={approvalErrorText(events.error)} action={<Button onClick={() => void events.refetch()}>重试</Button>} /> : null}
      <Table rowKey="id" size="small" loading={events.isFetching} pagination={false} dataSource={events.error ? [] : events.data?.data.items ?? []} columns={[
        { title: "动作", dataIndex: "event_kind" }, { title: "操作者", dataIndex: "actor_uid" }, { title: "时间", dataIndex: "occurred_at" },
      ]} />
    </Drawer>
  </Drawer>;
}

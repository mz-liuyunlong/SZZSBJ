import { Alert, Button, Modal, Space, Table, Tag } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { creationLabels, downloadCreationLabel, listCreationOperations, recoverCreation } from "./creationApi";
import { pendingError } from "./pendingPackingApi";

export default function CreationRecords({ orderId, scope, permissions, onClose, onRefresh }: {
  orderId: string; scope: string; permissions: string[]; onClose: () => void; onRefresh: () => Promise<void>;
}) {
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const query = useQuery({ queryKey: ["wfs-creation-records", scope, orderId, page], queryFn: ({ signal }) => listCreationOperations(orderId, page, signal), refetchInterval: 5000 });
  const can = (key: string) => permissions.includes("*") || permissions.includes(`action:pmc:wfs-pending-packing:${key}`);
  const perform = async (action: () => Promise<unknown>) => {
    setBusy(true); setError(undefined);
    try { await action(); await query.refetch(); await onRefresh(); } catch (e) { setError(pendingError(e)); }
    finally { setBusy(false); }
  };
  return <Modal open width={1000} title="创建记录" onCancel={onClose} footer={<Button onClick={onClose}>关闭</Button>}>
    {(error || query.error) && <Alert type="error" message={error ?? pendingError(query.error)} />}
    <Button onClick={() => void query.refetch()}>刷新记录</Button>
    <Table size="small" rowKey="id" loading={query.isFetching} dataSource={query.data?.data.items} pagination={{ current: page, pageSize: 10, total: query.data?.data.total, onChange: setPage }} columns={[
      { title: "创建记录", dataIndex: "id" },
      { title: "审批", render: (_, r) => r.automatically_approved_at ? "程序自动审批通过" : "待核实" },
      { title: "状态", render: (_, r) => <Tag>{creationLabels[r.state]}</Tag> },
      { title: "计划票数 / 实际货件数", render: (_, r) => `${r.tickets.length} / ${r.tickets.reduce((n, t) => n + t.shipments.length, 0)}` },
      { title: "操作", render: (_, r) => <Space>{can("reconcile") && <Button size="small" disabled={busy} onClick={() => void perform(() => recoverCreation(r.id, "reconcile"))}>核实结果</Button>}{can("label-retry") && <Button size="small" disabled={busy} onClick={() => void perform(() => recoverCreation(r.id, "labels/retry"))}>补取箱唛</Button>}</Space> },
    ]} expandable={{ defaultExpandAllRows: true, expandedRowRender: (op) => <Table size="small" rowKey="id" pagination={false} dataSource={op.tickets} columns={[
      { title: "计划票", dataIndex: "number" }, { title: "箱 / 件", render: (_, t) => `${t.allocation.boxes} / ${t.allocation.units}` },
      { title: "状态", render: (_, t) => creationLabels[t.state] },
      { title: "实际货件 / 箱唛", render: (_, t) => t.shipments.map((s) => <div key={s.shipment_id}>{s.shipment_id} · {s.label_state === "READY" ? <Button type="link" disabled={busy} onClick={() => void perform(() => downloadCreationLabel(op.id, s.shipment_id))}>下载箱唛</Button> : s.label_state === "FAILED" ? "获取失败待补取" : "待获取"}</div>) },
    ]} /> }} />
  </Modal>;
}

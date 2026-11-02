import { Alert, Button, Input, Modal, Space, Table, Tag } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { approveCreation, creationLabels, downloadCreationLabel, listCreationOperations, recoverCreation } from "./creationApi";

const APPROVAL_REF = /^[A-Za-z0-9][\w.:/#-]{2,127}$/;
import { pendingError } from "./pendingPackingApi";

export default function CreationRecords({ orderId, scope, permissions, onClose, onRefresh }: {
  orderId: string; scope: string; permissions: string[]; onClose: () => void; onRefresh: () => Promise<void>;
}) {
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [approving, setApproving] = useState<string>();
  const [approvalRef, setApprovalRef] = useState("");
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
      { title: "批准", render: (_, r) => r.approved_at ? `已批准 · ${r.approved_by ?? ""} · ${r.approval_ref ?? ""}` : r.automatic_checks_at ? "程序检查已通过，待人工批准" : "待人工批准" },
      { title: "状态", render: (_, r) => <Tag>{creationLabels[r.state]}</Tag> },
      { title: "计划票数 / 实际货件数", render: (_, r) => `${r.tickets.length} / ${r.tickets.reduce((n, t) => n + t.shipments.length, 0)}` },
      { title: "操作", render: (_, r) => <Space>{r.state === "AWAITING_APPROVAL" && can("approve") && <Button size="small" type="primary" disabled={busy} onClick={() => { setApprovalRef(""); setApproving(r.id); }}>批准执行</Button>}{r.approved_at && can("reconcile") && <Button size="small" disabled={busy} onClick={() => void perform(() => recoverCreation(r.id, "reconcile"))}>核实结果</Button>}{r.approved_at && can("label-retry") && <Button size="small" disabled={busy} onClick={() => void perform(() => recoverCreation(r.id, "labels/retry"))}>补取箱唛</Button>}</Space> },
    ]} expandable={{ defaultExpandAllRows: true, expandedRowRender: (op) => <Table size="small" rowKey="id" pagination={false} dataSource={op.tickets} columns={[
      { title: "计划票", dataIndex: "number" }, { title: "箱 / 件", render: (_, t) => `${t.allocation.boxes} / ${t.allocation.units}` },
      { title: "状态", render: (_, t) => creationLabels[t.state] },
      { title: "实际货件 / 箱唛", render: (_, t) => t.shipments.map((s) => <div key={s.shipment_id}>{s.shipment_id} · {s.label_state === "READY" ? <Button type="link" disabled={busy} onClick={() => void perform(() => downloadCreationLabel(op.id, s.shipment_id))}>下载箱唛</Button> : s.label_state === "FAILED" ? "获取失败待补取" : "待获取"}</div>) },
    ]} /> }} />
    <Modal open={approving !== undefined} title="批准执行（会调用 Walmart 创建货件）" okText="确认批准" okButtonProps={{ disabled: busy || !APPROVAL_REF.test(approvalRef) }} onCancel={() => setApproving(undefined)} onOk={() => { const id = approving; if (id) void perform(() => approveCreation(id, approvalRef)).then(() => setApproving(undefined)); }}>
      <p>程序检查不是批准。请填写本次书面批准的编号（例如 rocky-written:2026-11-01#1），批准人和时间由系统记录。</p>
      <Input aria-label="书面批准编号" value={approvalRef} maxLength={128} onChange={(e) => setApprovalRef(e.target.value.trim())} />
    </Modal>
  </Modal>;
}

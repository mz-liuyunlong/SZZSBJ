import { Button, Descriptions, Drawer, Form, Input, Space, Tag, Timeline, Typography, message } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { assignCase, exceptionError, getCase, postCaseEvent } from "./exceptionCenterApi";
const severityTone: Record<string, string> = { HIGH: "error", MEDIUM: "warning", LOW: "default" };
const statusTone: Record<string, string> = {
  OPEN: "error",
  IN_PROGRESS: "processing",
  WAITING_EXTERNAL: "gold",
  RESOLVED: "success",
  CLOSED: "default",
};
const time = (v?: string | null) =>
  v ? new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Taipei", dateStyle: "short", timeStyle: "short" }).format(new Date(v)) : "—";

export default function ExceptionCenterDrawer({
  caseId,
  scope,
  onClose,
}: {
  caseId: string;
  scope: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [assignee, setAssignee] = useState("");
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [platformRef, setPlatformRef] = useState("");
  const detail = useQuery({
    queryKey: ["wfs-exception-center", scope, "detail", caseId],
    queryFn: ({ signal }) => getCase(caseId, signal),
    enabled: Boolean(caseId),
  });
  const data = detail.data?.data;
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["wfs-exception-center", scope] });
  };
  const assignMut = useMutation({
    mutationFn: () => assignCase(caseId, { assignee_user_id: assignee.trim(), expected_version: data!.version }),
    onSuccess: () => { message.success("已分配负责人"); invalidate(); detail.refetch(); },
    onError: (e) => message.error(exceptionError(e, "detail")),
  });
  const eventMut = useMutation({
    mutationFn: (action: string) =>
      postCaseEvent(caseId, {
        action,
        expected_version: data!.version,
        note: note.trim(),
        reason: reason.trim(),
        platform_case_ref: platformRef.trim() || undefined,
      }),
    onSuccess: () => { message.success("已保存"); setNote(""); setReason(""); invalidate(); detail.refetch(); },
    onError: (e) => message.error(exceptionError(e, "detail")),
  });
  return (
    <Drawer width={720} open title={data?.shipment_id ?? "异常详情"} onClose={onClose} destroyOnClose>
      {detail.isError && <Typography.Text type="danger">{exceptionError(detail.error, "detail")}</Typography.Text>}
      {data && (
        <>
          <Space wrap style={{ marginBottom: 12 }}>
            <Tag color={severityTone[data.severity]}>{data.severity}</Tag>
            <Tag color={statusTone[data.status]}>{data.status_label}</Tag>
            <Tag>{data.rule_label}</Tag>
            {data.business_test && <Tag color="purple">业务测试</Tag>}
          </Space>
          <Descriptions size="small" bordered column={1} items={[
            { key: "store", label: "店铺", children: data.store_name ?? data.store_id },
            { key: "pk", label: "系统打包单", children: data.pk ?? "—" },
            { key: "item", label: "Item / GTIN / MSKU", children: `${data.item_id ?? "—"} / ${data.gtin ?? "—"} / ${data.msku ?? "—"}` },
            { key: "found", label: "最早发现", children: time(data.first_detected_at) },
            { key: "due", label: "期限", children: data.due_at ? `${time(data.due_at)}${data.due_basis ? `（${data.due_basis}）` : ""}` : "待核实" },
            { key: "owner", label: "负责人", children: data.assignee_user_id ?? "—" },
            { key: "platform", label: "平台案件编号", children: data.platform_case_ref ?? "—" },
            { key: "summary", label: "异常说明", children: data.summary },
          ]} />
          <Typography.Title level={5} style={{ marginTop: 16 }}>数量对账（M1）</Typography.Title>
          <Typography.Paragraph type="secondary">{data.quantity_reconciliation_note}</Typography.Paragraph>
          <Typography.Title level={5} style={{ marginTop: 16 }}>处理</Typography.Title>
          <Form layout="vertical">
            <Form.Item label="分配负责人">
              <Space.Compact style={{ width: "100%" }}>
                <Input value={assignee} onChange={(e) => setAssignee(e.target.value)} placeholder="用户 ID" />
                <Button type="primary" loading={assignMut.isPending} onClick={() => assignMut.mutate()}>分配</Button>
              </Space.Compact>
            </Form.Item>
            <Form.Item label="平台案件编号">
              <Input value={platformRef} onChange={(e) => setPlatformRef(e.target.value)} placeholder="保存时随备注类操作一并提交" />
            </Form.Item>
            <Form.Item label="跟进备注">
              <Input.TextArea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
            </Form.Item>
            <Space wrap>
              <Button onClick={() => eventMut.mutate("note")}>保存备注</Button>
              <Button onClick={() => eventMut.mutate("mark_waiting")}>待外部反馈</Button>
              <Button onClick={() => eventMut.mutate("resolve")}>标记已解决</Button>
            </Space>
            <Form.Item label="关闭 / 重开原因" style={{ marginTop: 12 }}>
              <Input.TextArea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
            </Form.Item>
            <Space wrap>
              <Button danger onClick={() => eventMut.mutate("close")}>关闭案件</Button>
              <Button onClick={() => eventMut.mutate("reopen")}>重开</Button>
            </Space>
          </Form>
          <Typography.Title level={5} style={{ marginTop: 16 }}>时间线</Typography.Title>
          <Timeline items={data.timeline.map((item) => ({
            children: (
              <div key={item.id}>
                <Typography.Text>{time(item.created_at)} · {item.message}</Typography.Text>
                {item.actor_uid && <Typography.Text type="secondary"> · {item.actor_uid}</Typography.Text>}
              </div>
            ),
          }))} />
        </>
      )}
    </Drawer>
  );
}

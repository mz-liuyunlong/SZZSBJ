import { useEffect, useState } from "react";
import { Alert, Button, Input, List, Modal, Select, Space, Typography } from "antd";
import { backendRequest } from "@/api/backendApi";
import { hasPermission } from "@/shared/permissions/mockAccess";

const CONFIRMATION = "CONFIRM_LISTING_LIFECYCLE";
const stages = ["测品期", "打品期", "启动期", "上升期", "稳定期", "下滑期", "断货期", "修复期"];

interface Adjustment {
  id: string;
  expected_stage: string | null;
  requested_stage: string;
  reason: string;
  status: string;
  requested_by: string;
  requested_at: string;
  decided_by: string | null;
  decision_note: string | null;
}

interface Props {
  listingId: string;
  permissions: readonly string[];
  onApplied: () => void;
}

export default function ListingLifecycleAdjustmentPanel({ listingId, permissions, onApplied }: Props) {
  const canRequest = hasPermission(permissions, "action:products:listing-management:request-lifecycle");
  const canApprove = hasPermission(permissions, "action:products:listing-management:approve-lifecycle");
  const [enabled, setEnabled] = useState(false);
  const [rows, setRows] = useState<Adjustment[]>([]);
  const [stage, setStage] = useState<string>();
  const [reason, setReason] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [decision, setDecision] = useState<{ row: Adjustment; kind: "approved" | "rejected" }>();
  const [decisionNote, setDecisionNote] = useState("");
  const [decisionConfirmation, setDecisionConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!canRequest && !canApprove) return;
    let active = true;
    void Promise.resolve().then(async () => {
      const [ruleResult, historyResult] = await Promise.allSettled([
        backendRequest<{ publish_enabled: boolean }>("/api/listings/rule-config"),
        backendRequest<{ items: Adjustment[]; total: number }>(
          `/api/listings/lifecycle-adjustments?listing_id=${encodeURIComponent(listingId)}`,
        ),
      ]);
      if (!active) return;
      setEnabled(ruleResult.status === "fulfilled" && ruleResult.value.data.publish_enabled);
      if (historyResult.status === "fulfilled") setRows(historyResult.value.data.items);
      else setError("人工调整历史加载失败，请确认权限及数据库版本。");
    });
    return () => { active = false; };
  }, [listingId, canRequest, canApprove]);

  if (!canRequest && !canApprove) return null;
  if (!enabled) return null;

  const refresh = async () => {
    const result = await backendRequest<{ items: Adjustment[]; total: number }>(
      `/api/listings/lifecycle-adjustments?listing_id=${encodeURIComponent(listingId)}`,
    );
    setRows(result.data.items);
  };

  const submit = async () => {
    if (!stage || reason.trim().length < 5 || confirmation !== CONFIRMATION) return;
    setBusy(true);
    setError("");
    try {
      await backendRequest("/api/listings/lifecycle-adjustments", {
        method: "POST",
        body: JSON.stringify({
          listing_id: listingId, requested_stage: stage, reason: reason.trim(), confirmation: CONFIRMATION,
        }),
      });
      await refresh();
      setStage(undefined);
      setReason("");
      setConfirmation("");
    } catch {
      setError("申请未保存：请确认权限、当前阶段及服务状态。");
    } finally {
      setBusy(false);
    }
  };

  const decide = async () => {
    if (!decision || decisionNote.trim().length < 5 || decisionConfirmation !== CONFIRMATION) return;
    setBusy(true);
    setError("");
    try {
      await backendRequest(
        `/api/listings/lifecycle-adjustments/${encodeURIComponent(decision.row.id)}/decision`,
        {
          method: "POST",
          body: JSON.stringify({
            decision: decision.kind, note: decisionNote.trim(), confirmation: CONFIRMATION,
          }),
        },
      );
      await refresh();
      if (decision.kind === "approved") onApplied();
      setDecision(undefined);
      setDecisionNote("");
      setDecisionConfirmation("");
    } catch {
      setError("审批未完成：申请人不能自行审批，且原阶段必须保持不变。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Typography.Title level={5} style={{ marginTop: 20 }}>人工生命周期调整</Typography.Title>
      <Typography.Paragraph type="secondary">
        人工调整须由另一名有权限的人审批；原阶段改变时申请自动失效。历史记录保留，可再次申请修正。
      </Typography.Paragraph>
      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} />}
      {canRequest && <Space direction="vertical" style={{ width: "100%" }}>
        <Select style={{ width: "100%" }} placeholder="选择新生命周期" value={stage} onChange={setStage}
          options={stages.map((value) => ({ label: value, value }))} />
        <Input.TextArea value={reason} onChange={(event) => setReason(event.target.value)}
          rows={2} maxLength={500} placeholder="填写调整原因（至少5个字符）" />
        <Input value={confirmation} onChange={(event) => setConfirmation(event.target.value)}
          placeholder={`输入 ${CONFIRMATION} 进行二次确认`} />
        <Button loading={busy} disabled={!stage || reason.trim().length < 5 || confirmation !== CONFIRMATION}
          onClick={() => void submit()}>提交调整申请</Button>
      </Space>}
      <List size="small" style={{ marginTop: 16 }} dataSource={rows} locale={{ emptyText: "暂无人工调整记录" }}
        renderItem={(row) => (
          <List.Item actions={canApprove && row.status === "pending" ? [
            <Button key="approve" size="small" onClick={() => setDecision({ row, kind: "approved" })}>审批通过</Button>,
            <Button key="reject" size="small" onClick={() => setDecision({ row, kind: "rejected" })}>驳回</Button>,
          ] : []}>
            <List.Item.Meta title={`${row.expected_stage ?? "未设置"} → ${row.requested_stage} · ${row.status}`}
              description={`${row.reason} · 申请人 ${row.requested_by}`} />
          </List.Item>
        )}
      />
      <Modal title={decision?.kind === "approved" ? "审批生命周期调整" : "驳回生命周期调整"}
        open={Boolean(decision)} confirmLoading={busy} okButtonProps={{
          disabled: decisionNote.trim().length < 5 || decisionConfirmation !== CONFIRMATION,
        }} onOk={() => void decide()} onCancel={() => setDecision(undefined)}>
        <Input.TextArea value={decisionNote} onChange={(event) => setDecisionNote(event.target.value)}
          rows={3} maxLength={500} placeholder="填写审批说明（至少5个字符）" />
        <Input style={{ marginTop: 12 }} value={decisionConfirmation}
          onChange={(event) => setDecisionConfirmation(event.target.value)}
          placeholder={`输入 ${CONFIRMATION} 进行二次确认`} />
      </Modal>
    </>
  );
}

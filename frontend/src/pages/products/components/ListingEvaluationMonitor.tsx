/** Read-only monitoring for Listing evaluation runs and published C/D follow-ups. */
import { useEffect, useRef, useState } from "react";
import { Alert, Button, Descriptions, Drawer, Empty, Input, Modal, Spin, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { backendRequest } from "@/api/backendApi";

interface EvaluationRun {
  id: string;
  schedule_date_cn: string;
  cutoff_date_la: string;
  status: string;
  rule_version: number;
  total_listings: number;
  processed_listings: number;
  grade_candidate_count: number;
  lifecycle_candidate_count: number;
  blocked_count: number;
  published_count?: number;
  attempt_count: number | null;
  started_at: string | null;
  finished_at: string | null;
  error_code: string | null;
}
interface FollowUp {
  id: string;
  item_id: string;
  msku: string | null;
  grade: "C" | "D";
  cutoff_date_la: string;
  due_date_cn: string;
  owner_ref: string | null;
  status: string;
  resolution_note: string | null;
}
interface EvaluationSnapshot {
  id: string;
  item_id: string;
  msku: string | null;
  cutoff_date_la: string;
  current_lifecycle: string | null;
  current_grade: string | null;
  lifecycle_candidate: string | null;
  grade_candidate: string | null;
  rule_version: number;
  rule_source: string;
  missing_evidence: string[];
  publication_error_code: string | null;
  publication_status: string;
  published: boolean;
  reverted_at: string | null;
}
interface ManualRequest {
  id: string;
  schedule_date_cn: string;
  status: string;
  error_code: string | null;
}
interface Props { open: boolean; onClose: () => void; permissions?: readonly string[]; }

const runColumns: ColumnsType<EvaluationRun> = [
  { title: "执行日期（中国）", dataIndex: "schedule_date_cn", width: 135 },
  { title: "LA截止日期", dataIndex: "cutoff_date_la", width: 125 },
  { title: "状态", dataIndex: "status", width: 95, render: (value: string) => <Tag>{value === "scoped_snapshots" ? "可见诊断快照" : value}</Tag> },
  { title: "已处理", dataIndex: "processed_listings", width: 90 },
  { title: "等级候选", dataIndex: "grade_candidate_count", width: 90 },
  { title: "生命周期候选", dataIndex: "lifecycle_candidate_count", width: 105 },
  { title: "待核查", dataIndex: "blocked_count", width: 90 },
  { title: "已正式发布", dataIndex: "published_count", width: 105, render: (value?: number) => value ?? 0 },
];
const followUpColumns: ColumnsType<FollowUp> = [
  { title: "Item ID", dataIndex: "item_id", width: 150 },
  { title: "MSKU", dataIndex: "msku", width: 140 },
  { title: "等级", dataIndex: "grade", width: 70, render: (value: string) => <Tag color={value === "D" ? "red" : "orange"}>{value}</Tag> },
  { title: "LA日期", dataIndex: "cutoff_date_la", width: 115 },
  { title: "截止日期（中国）", dataIndex: "due_date_cn", width: 135 },
  { title: "负责人", dataIndex: "owner_ref", width: 130, render: (value: string | null) => value ?? "未分配" },
  { title: "状态", dataIndex: "status", width: 100 },
];

export default function ListingEvaluationMonitor({ open, onClose, permissions = [] }: Props) {
  const canCalculateAll = permissions.includes("*") || permissions.includes("action:products:listing-management:calculate-all");
  const canRevert = permissions.includes("*") || permissions.includes("action:products:listing-management:revert-evaluation");
  const [runs, setRuns] = useState<EvaluationRun[]>([]);
  const [followUps, setFollowUps] = useState<FollowUp[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [dataLoadComplete, setDataLoadComplete] = useState(false);
  const [runLoaded, setRunLoaded] = useState(false);
  const [followUpLoaded, setFollowUpLoaded] = useState(false);
  const [activeFollowUp, setActiveFollowUp] = useState<FollowUp | null>(null);
  const [resolutionNote, setResolutionNote] = useState("");
  const [savingFollowUp, setSavingFollowUp] = useState(false);
  const [activeRun, setActiveRun] = useState<EvaluationRun | null>(null);
  const [snapshots, setSnapshots] = useState<EvaluationSnapshot[]>([]);
  const [snapshotTotal, setSnapshotTotal] = useState(0);
  const [snapshotPage, setSnapshotPage] = useState(1);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [snapshotError, setSnapshotError] = useState("");
  const [manualEnabled, setManualEnabled] = useState(false);
  const [manualSubmitting, setManualSubmitting] = useState(false);
  const [manualRequests, setManualRequests] = useState<ManualRequest[]>([]);
  const [manualConfirmOpen, setManualConfirmOpen] = useState(false);
  const [revertTarget, setRevertTarget] = useState<EvaluationSnapshot | null>(null);
  const [revertReason, setRevertReason] = useState("");
  const [reverting, setReverting] = useState(false);
  const snapshotRequestId = useRef(0);

  useEffect(() => {
    if (!open) return;
    let active = true;
    void Promise.resolve().then(async () => {
      if (!active) return;
      setLoading(true);
      setError("");
      setDataLoadComplete(false);
      setRunLoaded(false);
      setFollowUpLoaded(false);
      setRuns([]);
      setFollowUps([]);
      setManualEnabled(false);
      setManualRequests([]);
      try {
        const [runResult, followUpResult, ruleResult, manualResult] = await Promise.allSettled([
          backendRequest<{ items: EvaluationRun[]; total: number }>("/api/listings/evaluation-runs?limit=20"),
          backendRequest<{ items: FollowUp[]; total: number }>("/api/listings/evaluation-followups?limit=100"),
          canCalculateAll ? backendRequest<{ manual_enabled: boolean }>("/api/listings/rule-config") : Promise.resolve(null),
          canCalculateAll ? backendRequest<ManualRequest[]>("/api/listings/evaluation-runs/manual") : Promise.resolve(null),
        ]);
        if (active) {
          if (runResult.status === "fulfilled") setRuns(runResult.value.data.items);
          if (followUpResult.status === "fulfilled") setFollowUps(followUpResult.value.data.items);
          setRunLoaded(runResult.status === "fulfilled");
          setFollowUpLoaded(followUpResult.status === "fulfilled");
          if (ruleResult.status === "fulfilled") setManualEnabled(ruleResult.value?.data.manual_enabled ?? false);
          if (manualResult.status === "fulfilled") setManualRequests(manualResult.value?.data ?? []);
          setDataLoadComplete(runResult.status === "fulfilled" && followUpResult.status === "fulfilled");
          setError([
            runResult.status === "rejected" ? "计算记录加载失败。" : "",
            followUpResult.status === "rejected" ? "C/D跟进加载失败。" : "",
          ].filter(Boolean).join(" "));
        }
      } finally {
        if (active) setLoading(false);
      }
    });
    return () => { active = false; };
  }, [open, canCalculateAll]);

  const calculateAll = async () => {
    setManualSubmitting(true);
    try {
      const result = await backendRequest<ManualRequest>("/api/listings/evaluation-runs/manual", {
        method: "POST", body: JSON.stringify({ confirmation: "CONFIRM_LISTING_CALCULATE_ALL" }),
      });
      setManualRequests((current) => [result.data, ...current]);
      setManualConfirmOpen(false);
      setError("");
    } catch {
      setError("全部 Listing 诊断提交失败，请确认权限和后台状态。");
    } finally {
      setManualSubmitting(false);
    }
  };

  const completeFollowUp = async () => {
    if (!activeFollowUp || resolutionNote.trim().length < 3) return;
    setSavingFollowUp(true);
    try {
      const result = await backendRequest<FollowUp>(
        "/api/listings/evaluation-followups/" + encodeURIComponent(activeFollowUp.id),
        { method: "PATCH", body: JSON.stringify({ status: "completed", resolution_note: resolutionNote.trim() }) },
      );
      setFollowUps((current) => current.map((item) => item.id === result.data.id ? result.data : item));
      setActiveFollowUp(null);
      setResolutionNote("");
    } catch {
      setError("保存跟进结果失败，请确认权限和服务状态。");
    } finally {
      setSavingFollowUp(false);
    }
  };

  const revertPublication = async () => {
    if (!revertTarget || revertReason.trim().length < 5 || !activeRun) return;
    setReverting(true);
    try {
      await backendRequest(`/api/listings/evaluation-snapshots/${encodeURIComponent(revertTarget.id)}/revert`, {
        method: "POST",
        body: JSON.stringify({
          reason: revertReason.trim(),
          confirmation: "CONFIRM_LISTING_EVALUATION_REVERT",
        }),
      });
      setRevertTarget(null);
      setRevertReason("");
      await loadSnapshots(activeRun, snapshotPage);
    } catch {
      setSnapshotError("撤回失败：记录可能已被后续发布或人工调整，请刷新核查。");
    } finally {
      setReverting(false);
    }
  };

  const loadSnapshots = async (run: EvaluationRun, page: number) => {
    const requestId = ++snapshotRequestId.current;
    setActiveRun(run);
    setSnapshotPage(page);
    setSnapshotLoading(true);
    setSnapshotError("");
    try {
      const result = await backendRequest<{ items: EvaluationSnapshot[]; total: number }>(
        `/api/listings/evaluation-runs/${encodeURIComponent(run.id)}/snapshots?limit=50&offset=${(page - 1) * 50}`,
      );
      if (requestId === snapshotRequestId.current) {
        setSnapshots(result.data.items);
        setSnapshotTotal(result.data.total);
      }
    } catch {
      if (requestId === snapshotRequestId.current) {
        setSnapshots([]);
        setSnapshotTotal(0);
        setSnapshotError("逐商品计算结果加载失败，请确认权限和服务状态。");
      }
    } finally {
      if (requestId === snapshotRequestId.current) setSnapshotLoading(false);
    }
  };

  return (
    <Drawer title="Listing 计算记录与C/D跟进" open={open} onClose={() => { snapshotRequestId.current += 1; setActiveRun(null); onClose(); }} width={1080}>
      <Alert type="warning" showIcon style={{ marginBottom: 16 }}
        message="诊断结果与正式发布状态分开显示"
        description="诊断候选不等于正式评级。正式结果及C/D跟进仅以已发布记录为准；缺少经审核的广告费用或历史事件证据时不得发布。" />
      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}
      <Spin spinning={loading}>
        <Typography.Title level={5}>最近计算批次</Typography.Title>
        {canCalculateAll && <div style={{ marginBottom: 12 }}>
          <Button disabled={!manualEnabled} loading={manualSubmitting} onClick={() => setManualConfirmOpen(true)}>计算全部 Listing</Button>
          {!manualEnabled && <Typography.Text type="secondary"> 手动计算开关未启用</Typography.Text>}
          {manualRequests[0] && <Typography.Text type="secondary"> 最近手动请求：{manualRequests[0].status}{manualRequests[0].error_code ? `（${manualRequests[0].error_code}）` : ""}</Typography.Text>}
        </div>}
        {runs.length ? <Table<EvaluationRun> rowKey="id" size="small" columns={[...runColumns,
          { title: "详情", key: "details", width: 90, render: (_, row) => <Button size="small" onClick={() => void loadSnapshots(row, 1)}>逐商品</Button> },
        ]}
          dataSource={runs} pagination={false} scroll={{ x: 850 }} /> : <Empty description={runLoaded ? "暂无计算批次记录" : "计算记录尚未加载"} />}
        <Typography.Title level={5} style={{ marginTop: 28 }}>C/D级每日跟进</Typography.Title>
        <Descriptions size="small" column={1} style={{ marginBottom: 12 }}>
          <Descriptions.Item label="生成条件">仅从已正式发布、证据完整的C/D级快照生成</Descriptions.Item>
          <Descriptions.Item label="当前状态">{
            (runLoaded && runs.some((run) => (run.published_count ?? 0) > 0)) || (followUpLoaded && followUps.length > 0)
              ? "已查询到正式发布记录或C/D跟进任务"
              : dataLoadComplete
                ? "本次查询未发现已发布评级或正式跟进任务"
                : "数据未全部加载，发布状态暂不能确认"
          }</Descriptions.Item>
        </Descriptions>
        {followUps.length ? <Table<FollowUp> rowKey="id" size="small" columns={[
          ...followUpColumns,
          { title: "操作", key: "action", width: 100, render: (_, row) => (
            <Button size="small" disabled={row.status === "completed" || row.status === "canceled"}
              onClick={() => { setActiveFollowUp(row); setResolutionNote(""); }}>完成检查</Button>
          ) },
        ]} dataSource={followUps} pagination={{ pageSize: 10 }} scroll={{ x: 950 }} /> : <Empty description={followUpLoaded ? "暂无正式C/D跟进任务" : "C/D跟进尚未加载"} />}
      </Spin>
      <Modal title="计算全部 Listing？" open={manualConfirmOpen} okText="确认提交"
        confirmLoading={manualSubmitting} onOk={() => void calculateAll()}
        onCancel={() => setManualConfirmOpen(false)}>
        仅提交后台诊断，不会自动发布评级。计算前会重新核对账号数据范围。
      </Modal>
      <Modal title="完成C/D每日检查" open={activeFollowUp !== null}
        confirmLoading={savingFollowUp} okText="保存完成记录" cancelText="取消"
        onCancel={() => setActiveFollowUp(null)} onOk={() => void completeFollowUp()}
      >
        <Typography.Paragraph type="secondary">
          {activeFollowUp?.item_id} / {activeFollowUp?.msku ?? "-"} · {activeFollowUp?.grade}级
        </Typography.Paragraph>
        <Input.TextArea rows={4} maxLength={1000} value={resolutionNote}
          onChange={(event) => setResolutionNote(event.target.value)}
          placeholder="填写今天检查了什么、采取了什么措施及结果（至少3个字符）" />
      </Modal>
      <Drawer title="逐商品计算结果" open={activeRun !== null} onClose={() => { snapshotRequestId.current += 1; setActiveRun(null); }} width={1040}>
        {snapshotError && <Alert type="error" showIcon message={snapshotError} style={{ marginBottom: 16 }} />}
        <Table<EvaluationSnapshot> rowKey="id" size="small" loading={snapshotLoading} dataSource={snapshots}
          columns={[
            { title: "Item ID", dataIndex: "item_id", width: 140 },
            { title: "MSKU", dataIndex: "msku", width: 130, render: (value: string | null) => value ?? "-" },
            { title: "LA截止日", dataIndex: "cutoff_date_la", width: 120 },
            { title: "生命周期 当前→候选", key: "stage", width: 175, render: (_, row) => `${row.current_lifecycle ?? "待确认"} → ${row.lifecycle_candidate ?? "待确认"}` },
            { title: "等级 当前→候选", key: "grade", width: 130, render: (_, row) => `${row.current_grade ?? "待评级"} → ${row.grade_candidate ?? "待评级"}` },
            { title: "证据／错误码", key: "evidence", width: 250, render: (_, row) =>
              [...row.missing_evidence, ...(row.publication_error_code ? [row.publication_error_code] : [])].join("、") || "无" },
            { title: "发布状态", dataIndex: "publication_status", width: 115 },
            ...(canRevert ? [{ title: "操作", key: "revert", width: 90, render: (_: unknown, row: EvaluationSnapshot) =>
              row.published && !row.reverted_at
                ? <Button size="small" danger onClick={() => { setRevertTarget(row); setRevertReason(""); }}>撤回</Button>
                : null }] : []),
          ]}
          pagination={{ current: snapshotPage, pageSize: 50, total: snapshotTotal,
            onChange: (page) => { if (activeRun) void loadSnapshots(activeRun, page); } }}
          scroll={{ x: 1050 }}
        />
      </Drawer>
      <Modal title="撤回正式评级发布？" open={revertTarget !== null} okText="确认撤回"
        okButtonProps={{ danger: true, disabled: revertReason.trim().length < 5 }}
        confirmLoading={reverting} onOk={() => void revertPublication()}
        onCancel={() => setRevertTarget(null)}>
        仅撤回这次发布。若已有后续发布或人工调整，服务端会拒绝撤回。
        <Input.TextArea rows={3} maxLength={500} value={revertReason}
          onChange={(event) => setRevertReason(event.target.value)}
          placeholder="填写撤回原因（至少5个字符）" />
      </Modal>
    </Drawer>
  );
}

/** Read-only monitoring for Listing evaluation runs and published C/D follow-ups. */
import { useEffect, useState } from "react";
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
interface Props { open: boolean; onClose: () => void; }

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

export default function ListingEvaluationMonitor({ open, onClose }: Props) {
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
      try {
        const [runResult, followUpResult] = await Promise.allSettled([
          backendRequest<{ items: EvaluationRun[]; total: number }>("/api/listings/evaluation-runs?limit=20"),
          backendRequest<{ items: FollowUp[]; total: number }>("/api/listings/evaluation-followups?limit=100"),
        ]);
        if (active) {
          if (runResult.status === "fulfilled") setRuns(runResult.value.data.items);
          if (followUpResult.status === "fulfilled") setFollowUps(followUpResult.value.data.items);
          setRunLoaded(runResult.status === "fulfilled");
          setFollowUpLoaded(followUpResult.status === "fulfilled");
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
  }, [open]);

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

  return (
    <Drawer title="Listing 计算记录与C/D跟进" open={open} onClose={onClose} width={1080}>
      <Alert type="warning" showIcon style={{ marginBottom: 16 }}
        message="诊断结果与正式发布状态分开显示"
        description="诊断候选不等于正式评级。正式结果及C/D跟进仅以已发布记录为准；缺少经审核的广告费用或历史事件证据时不得发布。" />
      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}
      <Spin spinning={loading}>
        <Typography.Title level={5}>最近计算批次</Typography.Title>
        {runs.length ? <Table<EvaluationRun> rowKey="id" size="small" columns={runColumns}
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
    </Drawer>
  );
}

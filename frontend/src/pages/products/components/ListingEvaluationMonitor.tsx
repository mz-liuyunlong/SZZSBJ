/** Read-only monitoring for Listing evaluation runs and published C/D follow-ups. */
import { useEffect, useState } from "react";
import { Alert, Button, Descriptions, Drawer, Empty, Space, Spin, Table, Tag, Typography } from "antd";
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
  attempt_count: number;
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
}
interface Props { open: boolean; onClose: () => void; }

const runColumns: ColumnsType<EvaluationRun> = [
  { title: "执行日期（中国）", dataIndex: "schedule_date_cn", width: 135 },
  { title: "LA截止日期", dataIndex: "cutoff_date_la", width: 125 },
  { title: "状态", dataIndex: "status", width: 95, render: (value: string) => <Tag>{value}</Tag> },
  { title: "已处理", dataIndex: "processed_listings", width: 90 },
  { title: "等级候选", dataIndex: "grade_candidate_count", width: 90 },
  { title: "生命周期候选", dataIndex: "lifecycle_candidate_count", width: 105 },
  { title: "待核查", dataIndex: "blocked_count", width: 90 },
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

  useEffect(() => {
    if (!open) return;
    let active = true;
    void Promise.resolve().then(async () => {
      if (!active) return;
      setLoading(true);
      setError("");
      try {
        const [runResponse, followUpResponse] = await Promise.all([
          backendRequest<{ items: EvaluationRun[]; total: number }>("/api/listings/evaluation-runs?limit=20"),
          backendRequest<{ items: FollowUp[]; total: number }>("/api/listings/evaluation-followups?limit=100"),
        ]);
        if (active) {
          setRuns(runResponse.data.items);
          setFollowUps(followUpResponse.data.items);
        }
      } catch {
        if (active) setError("计算记录接口暂不可用或当前账号无权查看。");
      } finally {
        if (active) setLoading(false);
      }
    });
    return () => { active = false; };
  }, [open]);

  return (
    <Drawer title="Listing 计算记录与C/D跟进" open={open} onClose={onClose} width={1080}>
      <Alert type="warning" showIcon style={{ marginBottom: 16 }}
        message="当前运行只保存未发布的诊断快照"
        description="广告费用完整性与历史业务事件证据通过审核之前，不会覆盖正式Listing等级，也不会生成正式C/D运营任务。" />
      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}
      <Spin spinning={loading}>
        <Typography.Title level={5}>最近计算批次</Typography.Title>
        {runs.length ? <Table<EvaluationRun> rowKey="id" size="small" columns={runColumns}
          dataSource={runs} pagination={false} scroll={{ x: 850 }} /> : <Empty description="暂无计算批次记录" />}
        <Typography.Title level={5} style={{ marginTop: 28 }}>C/D级每日跟进</Typography.Title>
        <Descriptions size="small" column={1} style={{ marginBottom: 12 }}>
          <Descriptions.Item label="生成条件">仅从已正式发布、证据完整的C/D级快照生成</Descriptions.Item>
          <Descriptions.Item label="当前状态">没有已发布评级，因此不会创建或虚构跟进任务</Descriptions.Item>
        </Descriptions>
        {followUps.length ? <Table<FollowUp> rowKey="id" size="small" columns={followUpColumns}
          dataSource={followUps} pagination={{ pageSize: 10 }} scroll={{ x: 850 }} /> : <Empty description="暂无正式C/D跟进任务" />}
      </Spin>
    </Drawer>
  );
}

import { useState } from "react";
import { Alert, Button, Card, Form, Input, InputNumber, Modal, Select, Space, Table, Tag, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  decideNewProductPurchase,
  getNewProductWorkflows,
  requestNewProductPurchase,
  reviewNewProductLaunch,
  saveMarketScore,
  type NewProductWorkflowList,
  type NewProductWorkflowRecord,
} from "./newProductApi";

type Action = "market" | "request" | "decision" | "review";
type Draft = { score?: number; quantity?: number; reason: string; decision?: "approved_draft" | "rejected"; result?: "observe" | "optimize"; nextReview?: string };

export default function NewProductLivePanel({ canScore, canRequest, canApprove, canReview }: {
  canScore: boolean; canRequest: boolean; canApprove: boolean; canReview: boolean;
}) {
  const [account, setAccount] = useState("");
  const [data, setData] = useState<NewProductWorkflowList | null>(null);
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [record, setRecord] = useState<NewProductWorkflowRecord | null>(null);
  const [action, setAction] = useState<Action>("market");
  const [draft, setDraft] = useState<Draft>({ reason: "" });
  const [api, context] = message.useMessage();

  async function load(next = page) {
    setBusy(true);
    try {
      const result = await getNewProductWorkflows(account.trim(), next);
      setData(result);
      setPage(next);
    } catch (error) {
      api.error(error instanceof Error ? error.message : "读取真实数据失败");
    } finally {
      setBusy(false);
    }
  }

  function open(row: NewProductWorkflowRecord, nextAction: Action) {
    setRecord(row);
    setAction(nextAction);
    setDraft({ reason: "" });
  }

  async function submit() {
    if (!record) return;
    if (draft.reason.trim().length < 5) {
      api.warning("原因至少填写5个字");
      return;
    }
    const version = record.row_version ?? 0;
    const id = record.sku_identity_id;
    setBusy(true);
    try {
      if (action === "market") {
        if (!canScore || draft.score == null) throw new Error("没有评分权限或评分为空");
        await saveMarketScore(id, version, draft.score, draft.reason);
      } else if (action === "request") {
        if (!canRequest || !draft.quantity) throw new Error("没有申请权限或数量为空");
        await requestNewProductPurchase(id, version, draft.quantity, draft.reason);
      } else if (action === "decision") {
        if (!canApprove || !draft.decision) throw new Error("没有审批权限或决定为空");
        await decideNewProductPurchase(id, version, draft.decision, draft.reason);
      } else {
        if (!canReview || !draft.result) throw new Error("没有复盘权限或结果为空");
        await reviewNewProductLaunch(id, version, draft.result, draft.reason, draft.nextReview);
      }
      setRecord(null);
      api.success("已记录到新品草稿流程");
      await load(page);
    } catch (error) {
      api.error(error instanceof Error ? error.message : "提交失败");
    } finally {
      setBusy(false);
    }
  }

  const columns: ColumnsType<NewProductWorkflowRecord> = [
    { title: "SKU", dataIndex: "sku", width: 150 },
    { title: "商品名称", dataIndex: "product_name", ellipsis: true },
    { title: "类目", dataIndex: "category", width: 125 },
    { title: "账户", dataIndex: "source_account_ref", width: 130 },
    { title: "市场评分", dataIndex: "market_score", width: 95, render: v => v ?? "待评分" },
    { title: "申请采购量", dataIndex: "purchase_request_qty", width: 110, render: v => v ?? "—" },
    { title: "业务状态", dataIndex: "status", width: 130, render: v => <Tag>{({
      pending_market: "待市场评分", scored: "已评分", pending_purchase: "待审核",
      approved_draft: "草稿已批准", rejected: "已驳回",
    } as Record<string, string>)[v || "pending_market"] ?? v}</Tag> },
    { title: "操作", key: "actions", width: 250, render: (_, row) => {
      const state = row.status ?? "pending_market";
      return <Space wrap size={0}>
        {canScore && state === "pending_market" && <Button type="link" onClick={() => open(row, "market")}>市场评分</Button>}
        {canRequest && (state === "scored" || state === "rejected") && <Button type="link" onClick={() => open(row, "request")}>采购申请</Button>}
        {canApprove && state === "pending_purchase" && <Button type="link" onClick={() => open(row, "decision")}>草稿审批</Button>}
        {canReview && state === "approved_draft" && <Button type="link" onClick={() => open(row, "review")}>复盘</Button>}
      </Space>;
    } },
  ];

  return <Card title="正式数据 · 新品工作流" size="small">
    {context}
    <Typography.Paragraph type="secondary">此入口读取数据库中的 SKU 身份及新品业务记录。没有选定账户时不会查询；采购审批只生成草稿决定，不会创建 PMC 采购单。</Typography.Paragraph>
    <Space wrap style={{ marginBottom: 16 }}>
      <Input style={{ width: 250 }} placeholder="输入有权限的 source_account_ref" value={account}
        onChange={event => { setAccount(event.target.value); setData(null); setPage(1); }} />
      <Button type="primary" loading={busy} disabled={!account.trim()} onClick={() => void load(1)}>加载真实数据</Button>
    </Space>
    <Table rowKey="sku_identity_id" dataSource={data?.items ?? []} columns={columns} loading={busy}
      scroll={{ x: 1150 }} pagination={{ current: page, pageSize: 50, total: data?.total ?? 0,
        onChange: next => void load(next), showSizeChanger: false }} />
    <Modal title={action === "market" ? "市场评分" : action === "request" ? "申请采购" :
      action === "decision" ? "审批采购草稿" : "打品复盘"} open={!!record} confirmLoading={busy}
      onCancel={() => setRecord(null)} onOk={() => void submit()} okText="保存">
      <Form layout="vertical">
        <Typography.Paragraph>{record?.sku} · {record?.product_name}</Typography.Paragraph>
        {action === "market" && <Form.Item label="市场评分（0–10）" required>
          <InputNumber min={0} max={10} precision={0} value={draft.score}
            onChange={value => setDraft(s => ({ ...s, score: value ?? undefined }))} style={{ width: "100%" }} />
        </Form.Item>}
        {action === "request" && <Form.Item label="申请采购量" required>
          <InputNumber min={1} precision={0} value={draft.quantity}
            onChange={value => setDraft(s => ({ ...s, quantity: value ?? undefined }))} style={{ width: "100%" }} />
        </Form.Item>}
        {action === "decision" && <Form.Item label="审批决定" required>
          <Select value={draft.decision} onChange={value => setDraft(s => ({ ...s, decision: value }))}
            options={[{ label: "批准草稿（不生成采购单）", value: "approved_draft" },
              { label: "驳回", value: "rejected" }]} />
        </Form.Item>}
        {action === "review" && <>
          <Form.Item label="复盘状态" required>
            <Select value={draft.result} onChange={value => setDraft(s => ({ ...s, result: value }))}
              options={[{ label: "继续观察", value: "observe" }, { label: "需要优化", value: "optimize" }]} />
          </Form.Item>
          {draft.result === "optimize" && <Form.Item label="下次复核日期（YYYY-MM-DD）" required>
            <Input value={draft.nextReview} placeholder="2026-11-30"
              onChange={event => setDraft(s => ({ ...s, nextReview: event.target.value }))} />
          </Form.Item>}
        </>}
        <Form.Item label="理由（至少5字）" required>
          <Input.TextArea rows={3} value={draft.reason}
            onChange={event => setDraft(s => ({ ...s, reason: event.target.value }))} />
        </Form.Item>
      </Form>
      <Alert type="info" showIcon message="正式采购执行需走现有采购/审批模块，不在此草稿界面直接生成订单。" />
    </Modal>
  </Card>;
}

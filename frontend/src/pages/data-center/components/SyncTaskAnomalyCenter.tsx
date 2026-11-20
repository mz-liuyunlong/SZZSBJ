import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Checkbox, Descriptions, Drawer, Input, Select, Space, Table, Tag, Typography, message } from "antd";
import { backendRequest } from "@/api/backendApi";
import { describeSyncAnomaly } from "@/pages/data-center/syncTaskAnomalyGuidance";

interface Anomaly {
  id: string;
  run_id: string;
  source_account_ref: string;
  interface_key: string;
  business_date: string;
  error_code: string;
  store_id: string | null;
  item_id: string | null;
  msku: string | null;
  local_sku: string | null;
  platform_order_no: string | null;
  campaign_name: string | null;
  status: string;
  details: Record<string, unknown>;
  occurrence_count: number;
  owner_note: string | null;
  first_seen_at: string;
  last_seen_at: string;
}

interface AnomalyDiagnosis {
  status: "manual_review" | "needs_identity" | "blocked_by_salestat" | "source_missing" |
    "ready_for_replay" | "verified";
  explanation: string;
  next_action: string;
  recognized_zero_paid_orders: number | null;
  recognized_zero_paid_qty: string | null;
  approved_sample_qty: string | null;
  approved_sample_amount: string | null;
  salestat_qty: string | null;
  salestat_amount: string | null;
  mart_sample_qty: string | null;
  mart_gross_qty: string | null;
}

interface AnomalyAudit {
  id: string;
  actor_ref: string;
  from_status: string;
  to_status: string;
  note: string;
  created_at: string;
}

const statusNames: Record<string, string> = {
  pending: "待核对",
  investigating: "核对中",
  fix_pending: "待修复",
  review_pending: "待复验",
  resolved: "已解决",
  dismissed: "误报关闭",
};

const display = (value: string | null | undefined) => value?.trim() || "待定位";

export default function SyncTaskAnomalyCenter() {
  const [items, setItems] = useState<Anomaly[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<Anomaly | null>(null);
  const [status, setStatus] = useState<string>("all");
  const [keyword, setKeyword] = useState("");
  const [searchText, setSearchText] = useState("");
  const [note, setNote] = useState("");
  const [nextStatus, setNextStatus] = useState("investigating");
  const [saving, setSaving] = useState(false);
  const [history, setHistory] = useState<AnomalyAudit[]>([]);
  const [messageApi, contextHolder] = message.useMessage();
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [diagnosis, setDiagnosis] = useState<AnomalyDiagnosis | null>(null);
  const [diagnosisLoading, setDiagnosisLoading] = useState(false);
  const [recheckLoading, setRecheckLoading] = useState(false);
  const [replayLoading, setReplayLoading] = useState(false);
  const [confirmReplayScope, setConfirmReplayScope] = useState(false);
  const selectedGuide = selected ? describeSyncAnomaly(selected) : null;
  const selectedNeedsReview = nextStatus === "dismissed";

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const query = new URLSearchParams({ page: String(page), page_size: "20" });
      if (status !== "all") query.set("status", status);
      if (searchText.trim()) query.set("keyword", searchText.trim());
      const result = await backendRequest<{ items: Anomaly[] }, { total?: number }>(
        `/api/integrations/sync-anomalies?${query.toString()}`
      );
      setItems(result.data.items);
      setTotal(result.meta.total ?? result.data.items.length);
    } catch {
      messageApi.error("异常列表加载失败，请检查接口权限与异常表迁移状态");
    } finally {
      setLoading(false);
    }
  }, [page, status, searchText, messageApi]);

  useEffect(() => {
    // Defer the request to avoid synchronous state updates during effect execution.
    void Promise.resolve().then(refresh);
  }, [refresh]);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    void backendRequest<{ items: AnomalyAudit[] }>(
      `/api/integrations/sync-anomalies/${selected.id}/history`
    ).then(result => {
      if (!cancelled) setHistory(result.data.items);
    }).catch(() => {
      if (!cancelled) setHistory([]);
    });
    return () => { cancelled = true; };
  }, [selected]);

  const inspect = async (anomalyId: string) => {
    setDiagnosisLoading(true);
    try {
      const response = await backendRequest<AnomalyDiagnosis>(
        `/api/integrations/sync-anomalies/${anomalyId}/diagnosis`
      );
      setDiagnosis(response.data);
    } catch {
      messageApi.error("当前无法读取真实核对结果，请检查接口或权限");
    } finally {
      setDiagnosisLoading(false);
    }
  };

  const recheck = async () => {
    if (!selected) return;
    setRecheckLoading(true);
    try {
      const response = await backendRequest<AnomalyDiagnosis>(
        `/api/integrations/sync-anomalies/${selected.id}/recheck`,
        { method: "POST" },
      );
      setDiagnosis(response.data);
      messageApi.success(response.data.status === "verified"
        ? "复核通过：数据已一致，异常已自动关闭"
        : "复核完成：问题尚未解决，保留异常等待处理");
      await refresh();
    } catch {
      messageApi.error("重新核对失败，异常状态没有改变；请检查操作权限");
    } finally {
      setRecheckLoading(false);
    }
  };

  const replay = async () => {
    if (!selected) return;
    if (note.trim().length < 12) {
      messageApi.warning("提交重算前请说明数据已确认的依据，至少12个字符");
      return;
    }
    if (!confirmReplayScope) {
      messageApi.warning("重算会涉及本来源账号指定日期的全部店铺，请先确认影响范围");
      return;
    }
    setReplayLoading(true);
    try {
      const result = await backendRequest<{ run_id: string }>(
        `/api/integrations/sync-anomalies/${selected.id}/replay`,
        { method: "POST", body: JSON.stringify({ reason: note.trim(), confirm_all_stores_for_day: confirmReplayScope }) },
      );
      messageApi.success("已提交指定日期重新同步及重算任务：" + result.data.run_id +
        "；任务完成后请再点击重新核对");
      await refresh();
    } catch {
      messageApi.error("未提交重算：数据尚不满足安全重算条件、任务配置不可用或缺少执行权限");
    } finally {
      setReplayLoading(false);
    }
  };

  const submit = async () => {
    if (!selected || note.trim().length < (selectedNeedsReview ? 30 : 3)) {
      messageApi.warning(selectedNeedsReview
        ? "人工判定误报需有完整依据，至少30个字符"
        : "请填写至少3个字符的核对说明");
      return;
    }
    setSaving(true);
    try {
      await backendRequest(`/api/integrations/sync-anomalies/${selected.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus, note: note.trim() }),
      });
      messageApi.success(selectedNeedsReview
        ? "已登记人工核对结论；本操作未重算销售和利润"
        : "已记录核对进度；本操作未修改原始数据");
      setSelected(null);
      setNote("");
      await refresh();
    } catch {
      messageApi.error("保存失败，未改变异常状态");
    } finally {
      setSaving(false);
    }
  };
  const visible = items;

  return (
    <section className="sync-task__card" aria-label="同步异常中心">
      {contextHolder}
      <Space wrap style={{ marginBottom: 16 }}>
        <Input.Search placeholder="搜索 SKU / Item ID / 订单号 / 店铺 / 日期" value={keyword}
          onChange={event => setKeyword(event.target.value)}
          onSearch={value => { setPage(1); setSearchText(value); }}
          style={{ width: 340 }} allowClear />
        <Select value={status} onChange={value => { setStatus(value); setPage(1); }}
          style={{ width: 140 }}
          options={[{ value: "all", label: "全部状态" },
            ...Object.entries(statusNames).map(([value, label]) => ({ value, label }))]} />
        <Button onClick={() => { void refresh(); }}>刷新异常</Button>
      </Space>
      <Table<Anomaly> size="small" rowKey="id" loading={loading}
        dataSource={visible}
        scroll={{ x: 1100 }}
        pagination={{
          current: page, pageSize: 20, total,
          onChange: value => setPage(value),
        }}
        columns={[
          { title: "业务日期", dataIndex: "business_date", width: 120 },
          { title: "店铺 ID", dataIndex: "store_id", width: 120, render: display },
          { title: "SKU / MSKU", width: 170, render: (_, row) => display(row.local_sku || row.msku) },
          { title: "订单号", dataIndex: "platform_order_no", width: 160, render: display },
          { title: "接口", dataIndex: "interface_key", width: 160 },
          { title: "异常原因", dataIndex: "error_code", width: 250,
            render: (value: string, row: Anomaly) => <Space direction="vertical" size={0}>
              <Typography.Text>{describeSyncAnomaly(row).title}</Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }} copyable={{ text: value }}>
                {value}
              </Typography.Text>
            </Space> },
          { title: "状态", dataIndex: "status", width: 105,
            render: value => <Tag>{statusNames[value] ?? value}</Tag> },
          { title: "次数", dataIndex: "occurrence_count", width: 70 },
          { title: "操作", key: "view", fixed: "right", width: 90,
            render: (_, row) => <Button type="link" onClick={() => {
              setHistory([]); setDiagnosis(null); setConfirmReplayScope(false); setSelected(row);
              setNote(row.owner_note ?? ""); setNextStatus(row.status);
              void inspect(row.id);
            }}>核对详情</Button> },
        ]}
      />
      <Drawer title="异常核对详情" width={680} open={!!selected}
        onClose={() => { setSelected(null); setHistory([]); setDiagnosis(null); setConfirmReplayScope(false); }}>
        {selected && <>
          <Alert type="info" showIcon style={{ marginBottom: 16 }}
            message={selectedGuide?.title ?? "异常待核对"}
            description={selectedGuide?.explanation} />
          {selectedGuide?.comparison && <Alert type="warning" showIcon style={{ marginBottom: 16 }}
            message="发现的数据差异" description={selectedGuide.comparison} />}
          <Typography.Title level={5}>当前真实数据核对</Typography.Title>
          <Space direction="vertical" style={{ width: "100%", marginBottom: 16 }}>
            {diagnosisLoading && <Typography.Text type="secondary">正在从最新数据检查…</Typography.Text>}
            {diagnosis && <Alert showIcon type={
              diagnosis.status === "verified" ? "success" :
                diagnosis.status === "ready_for_replay" ? "info" : "warning"
            } message={diagnosis.explanation} description={diagnosis.next_action} />}
            {diagnosis?.approved_sample_qty !== null && diagnosis?.approved_sample_qty !== undefined && (
              <Descriptions size="small" column={2} bordered items={[
                { key: "zero", label: "零元未取消订单数", children: diagnosis.recognized_zero_paid_orders ?? "—" },
                { key: "sample", label: "已核实送样数量", children: diagnosis.approved_sample_qty },
                { key: "salestat", label: "SaleStat 数量", children: diagnosis.salestat_qty ?? "—" },
                { key: "mart", label: "每日销售送样量", children: diagnosis.mart_sample_qty ?? "未计算" },
              ]} />
            )}
            <Space wrap>
              <Button loading={recheckLoading} onClick={() => { void recheck(); }}>重新核对并尝试自动关闭</Button>
              {diagnosis?.status === "ready_for_replay" && <Button type="primary" loading={replayLoading}
                onClick={() => { void replay(); }}>提交单日重算</Button>}
            </Space>
            {diagnosis?.status === "ready_for_replay" && <>
              <Checkbox checked={confirmReplayScope} onChange={event => setConfirmReplayScope(event.target.checked)}>
                我已了解：本次会重跑该来源账号在指定业务日的全部店铺，不只是当前商品；提交后还要再次复核
              </Checkbox>
              <Typography.Text type="secondary">
                提交前请在下方填写至少12字核对理由。历史锁账日不会自动重算；任务入队不代表成功。
              </Typography.Text>
            </>}
          </Space>
          <Typography.Title level={5}>你需要先做什么？</Typography.Title>
          <ol>{selectedGuide?.checks.map(step => <li key={step}>{step}</li>)}</ol>
          <Typography.Title level={5}>需要准备哪些资料？</Typography.Title>
          <ul>{selectedGuide?.requiredEvidence.map(item => <li key={item}>{item}</li>)}</ul>
          <Alert type="info" showIcon style={{ marginBottom: 16 }}
            message="下一步处理建议" description={selectedGuide?.safeNextStep} />
          <Descriptions column={1} bordered size="small" items={[
            { key: "date", label: "美国业务日期", children: selected.business_date },
            { key: "account", label: "来源账号", children: selected.source_account_ref },
            { key: "run", label: "关联任务 Run ID", children: <Typography.Text copyable>{selected.run_id}</Typography.Text> },
            { key: "store", label: "店铺 ID", children: <Typography.Text copyable>{display(selected.store_id)}</Typography.Text> },
            { key: "sku", label: "本地 SKU", children: <Typography.Text copyable>{display(selected.local_sku)}</Typography.Text> },
            { key: "msku", label: "MSKU", children: <Typography.Text copyable>{display(selected.msku)}</Typography.Text> },
            { key: "item", label: "Item ID", children: <Typography.Text copyable>{display(selected.item_id)}</Typography.Text> },
            { key: "order", label: "订单号", children: <Typography.Text copyable>{display(selected.platform_order_no)}</Typography.Text> },
            { key: "campaign", label: "Campaign", children: <Typography.Text copyable>{display(selected.campaign_name)}</Typography.Text> },
            { key: "source", label: "接口", children: selected.interface_key },
            { key: "error", label: "错误码", children: selected.error_code },
            { key: "count", label: "累计发现次数", children: selected.occurrence_count },
            { key: "last", label: "最近发现", children: selected.last_seen_at },
          ]} />
          <Typography.Title level={5} style={{ marginTop: 20 }}>核对依据和原始信息</Typography.Title>
          <Typography.Title level={5}>异常证据（仅展示安全摘要）</Typography.Title>
          <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
            {JSON.stringify(selected.details, null, 2)}
          </pre>
          <Typography.Title level={5}>历史核对记录</Typography.Title>
          <Table<AnomalyAudit> size="small" rowKey="id" dataSource={history}
            pagination={false} columns={[
              { title: "时间", dataIndex: "created_at", width: 170 },
              { title: "操作人", dataIndex: "actor_ref", width: 120 },
              { title: "处理状态", dataIndex: "to_status", width: 100,
                render: value => statusNames[value] ?? value },
              { title: "核对备注", dataIndex: "note" },
            ]} />
          <Typography.Title level={5}>记录你的核对结果</Typography.Title>
          <Alert type="warning" showIcon style={{ marginBottom: 12 }}
            message="注意：这里保存的是处理记录，不是补数或重算"
            description="保存核对记录不会补数或重算。请使用上方的重新核对或符合条件时的单日重算；需要人工纠正来源字段时仍须走独立审核。" />
          <Space direction="vertical" style={{ width: "100%" }}>
            <Select value={nextStatus} onChange={setNextStatus}
              options={Object.entries(statusNames).filter(([value]) => value !== "resolved")
                .map(([value, label]) => ({ value, label }))} />
            {selectedNeedsReview && <Alert type="warning" showIcon
              message="你正在人工关闭一条异常"
              description="此操作只适用于已明确证明为误报或合法口径差异的情况；填写不少于30字的来源凭据。真正的数据修复只能经过重新核对，不能靠人工关闭。" />}
            <Input.TextArea rows={4} value={note} onChange={event => setNote(event.target.value)}
              placeholder="填写证据：订单号/商品ID、来源报表、美国业务日期、核实数量或金额、凭据链接或存放位置，以及是否需要补数据。误报关闭至少30字。" />
            <Button type="primary" loading={saving} onClick={() => { void submit(); }}>
              {selectedNeedsReview ? "凭据确认并关闭误报（不重算）" : "保存人工补充证据和处理状态"}
            </Button>
          </Space>
        </>}
      </Drawer>
    </section>
  );
}

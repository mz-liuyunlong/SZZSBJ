import { Alert, Button, Checkbox, Form, Input, InputNumber, Modal, Select, Space, Spin, Tag, Typography, message } from "antd";
import { useEffect, useRef, useState } from "react";
import type { ApprovalItem } from "../approvalTypes";
import { riskNames } from "../approvalTypes";
import { approvalBusinessLabel } from "../approvalBusiness";
import LegacyBulkApprovalModal from "./BulkApprovalModal";
import { pendingBatchRow, prepareBatchRow, submitBatchRow, validBatchRow, type BatchRow } from "../batchApproval";

interface Props { rows: ApprovalItem[]; permissions: readonly string[]; onCancel(): void; onUpdated(): void }
export default function UnifiedBulkApprovalModal(props: Props) {
  // Preserve the existing atomic, low-risk operations-plan batch endpoint.
  if (props.rows.length > 0 && props.rows.length <= 20 && props.rows.every(r =>
    r.approval_type === "operations_plan_ack" && r.risk_level === "low")) {
    return <LegacyBulkApprovalModal rows={props.rows} onCancel={props.onCancel} onUpdated={() => {props.onCancel();props.onUpdated();}}/>;
  }
  // Remount between selections; never retain confirmations or purchase values across batches.
  return props.rows.length ? <BatchInner key={JSON.stringify(props.rows.map(r => [r.id, r.version]))} {...props}/> : null;
}
function BatchInner({rows, permissions, onCancel, onUpdated}: Props) {
  const [entries, setEntries] = useState<BatchRow[]>(() => rows.map(pendingBatchRow));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState("");
  const [progress, setProgress] = useState(0);
  const [outcome, setOutcome] = useState<{submitted: number; closed: number; unknown: string[]} | null>(null);
  const savingRef = useRef(false);
  const [api, holder] = message.useMessage();
  useEffect(() => {
    let active = true;
    void (async () => {
      const next: BatchRow[] = [];
      for (let i = 0; i < rows.length; i += 4) {
        if (!active) return;
        next.push(...await Promise.all(rows.slice(i, i + 4).map(row => prepareBatchRow(row, permissions))));
      }
      if (active) { setEntries(next); setLoading(false); }
    })();
    return () => { active = false; };
  }, [rows, permissions]);
  const update = (index: number, patch: Partial<BatchRow>) =>
    setEntries(old => old.map((entry, i) => i === index ? {...entry, ...patch} : entry));
  const close = () => {
    if (savingRef.current) return;
    onCancel();
  };
  const ready = !loading && !saving && !outcome && entries.length > 0 &&
    entries.every(validBatchRow) && new Set(entries.map(e => e.row.id)).size === entries.length;
  const save = async () => {
    if (!ready || savingRef.current) return;
    if (note.trim().length < 5) { void api.warning("请填写至少5个字的审批意见"); return; }
    savingRef.current = true;
    setSaving(true);
    let submitted = 0, closed = 0;
    const unknown: string[] = [];
    try {
      for (const [index, entry] of entries.entries()) {
        try {
          const result = await submitBatchRow(entry, permissions, note.trim());
          if (result === "closed") closed++; else submitted++;
        } catch {
          unknown.push(entry.row.title + " / " + entry.row.business_ref);
        }
        setProgress(index + 1);
      }
      setOutcome({submitted, closed, unknown});
      if (entries.some(e => e.row.approval_type === "clearance_request")) {
        window.dispatchEvent(new Event("szzsbj-clearance-application-updated"));
      }
      // Refresh the list, including when a request outcome was uncertain.
      onUpdated();
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };
  return <>{holder}<Modal title={`批量审批（${rows.length}条）`} open centered width={960}
    onCancel={close} onOk={() => {if(outcome) close(); else void save();}}
    okText={outcome ? "关闭" : "确认批量审批"} cancelText="取消"
    closable={!saving} maskClosable={!saving} keyboard={!saving}
    cancelButtonProps={{disabled:saving, style:outcome ? {display:"none"} : undefined}}
    okButtonProps={{loading:saving,disabled:!outcome && (!ready || note.trim().length < 5)}}>
    {outcome ? <Space direction="vertical" style={{width:"100%"}}>
      <Alert showIcon type={outcome.unknown.length ? "warning" : "success"}
        message={`已提交审批 ${outcome.submitted} 条，库存售罄关闭 ${outcome.closed} 条，结果未确认 ${outcome.unknown.length} 条`}
        description="各单独立提交，最终状态以刷新后的审批记录为准。未确认记录可能已提交，请勿直接重复审批。"/>
      {outcome.unknown.map((label, i) => <Typography.Text key={i}>{label}</Typography.Text>)}
    </Space> : <>
      <Alert showIcon type="info" message="确认每条申请后统一提交"
        description="不同业务可一起处理，采购逐条确认店铺及数量；每条继续使用正式审批接口、原权限及业务规则。各单独立提交。"/>
      {loading ? <div style={{padding:24,textAlign:"center"}}><Spin/> 正在核实审批资料</div> :
        <div style={{maxHeight:"48vh",overflowY:"auto",marginTop:12}}>
          {entries.map((entry,index) => {
            const row = entry.detail ?? entry.row;
            const purchase = row.approval_type === "new_product_purchase";
            const high = row.risk_level === "high";
            return <div key={row.id} style={{padding:"12px 4px",borderBottom:"1px solid #e5e7eb"}}>
              <Space wrap><Typography.Text strong>{row.title}</Typography.Text>
                <Tag>{approvalBusinessLabel(row.approval_type)}</Tag>
                <Tag color={high ? "red" : undefined}>{riskNames[row.risk_level] ?? row.risk_level}</Tag>
              </Space>
              <div><Typography.Text type="secondary">{row.business_ref} · {row.reason || "无申请说明"}</Typography.Text></div>
              {row.amount !== null && <div>关联金额：{row.amount} {row.currency_code || ""}</div>}
              {row.follow_log && <div style={{whiteSpace:"pre-wrap"}}>跟进记录：{row.follow_log}</div>}
              {entry.detail?.evidence && <div style={{whiteSpace:"pre-wrap"}}>业务依据：{entry.detail.evidence}</div>}
              {entry.error ? <Alert type="error" showIcon message={entry.error}/> : <>
                {purchase && <Space wrap style={{margin:"8px 0"}}>
                  <span>采购店铺</span><Select style={{width:260}} showSearch optionFilterProp="label"
                    value={entry.storeId} disabled={saving}
                    options={entry.stores.map(s => ({value:s.store_id,label:s.store_name}))}
                    onChange={storeId => update(index,{storeId,confirmed:false})}/>
                  <span>采购数量</span><InputNumber min={1} max={100000} precision={0}
                    value={entry.quantity} disabled={saving}
                    onChange={quantity => update(index,{quantity,confirmed:false})}/>
                  <Typography.Text type="secondary">申请 {row.purchase_details?.requested_qty ?? "—"} 件 · 建议 {row.purchase_details?.suggested_qty ?? "—"} 件</Typography.Text>
                </Space>}
                {row.approval_type === "clearance_request" && <div>申请清货量：{row.clearance_details?.requested_qty ?? "—"} 件（批准时重新核实库存）</div>}
                {row.case_review && !row.applicant_id && <div><Checkbox checked={entry.identityConfirmed} disabled={saving}
                  onChange={e => update(index,{identityConfirmed:e.target.checked,confirmed:false})}>已核查申请人身份记录缺失的审核风险</Checkbox></div>}
                <div><Checkbox checked={entry.confirmed} disabled={saving}
                  onChange={e => update(index,{confirmed:e.target.checked})}>
                  {high ? "已逐项核对高风险业务金额、申请原因、历史跟进及关联证据，同意批准"
                    : purchase ? "确认本单采购店铺、数量及申请依据" : "已核对本单业务依据，同意批准"}
                </Checkbox></div>
              </>}
            </div>;
          })}
          <Button type="link" disabled={saving || entries.some(e => !!e.error)} onClick={() =>
            setEntries(old => old.map(e => {
              const row = e.detail ?? e.row;
              return !e.error && row.risk_level !== "high" && row.approval_type !== "new_product_purchase" &&
                !(row.case_review && !row.applicant_id) ? {...e, confirmed:true} : e;
            }))}>确认所有普通事项（采购、高风险、身份待核实须单独确认）</Button>
        </div>}
      <Form layout="vertical" style={{marginTop:12}}><Form.Item label="批量审批意见（必填）">
        <Input.TextArea rows={3} maxLength={4000} showCount value={note} disabled={saving}
          onChange={e => setNote(e.target.value)}/>
      </Form.Item></Form>
      {saving && <Typography.Text>正在处理 {progress}/{rows.length} 条，请勿关闭页面。</Typography.Text>}
    </>}
  </Modal></>;
}

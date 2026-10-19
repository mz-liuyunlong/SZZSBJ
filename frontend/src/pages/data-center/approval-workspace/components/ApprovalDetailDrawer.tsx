import { Alert, Button, Drawer, Form, Input, Modal, Space, Spin, Timeline, Typography, message } from "antd";
import { useEffect, useState } from "react";
import type { ApprovalDetail, ApprovalItem, Decision } from "../approvalTypes";
import { decideApproval, fetchApprovalDetail, fetchLegacyApprovalDetail, supplementApproval } from "../approvalApi";
import { statusNames } from "../approvalTypes";
import { WfsCaseApprovalDetail } from "./WfsCaseApprovalDetail";
import GenericApprovalDetail from "./GenericApprovalDetail";
import LegacyReattestModal from "./LegacyReattestModal";

interface Props {
 selected?: ApprovalItem;
 canReview: boolean;
 canAdmin: boolean;
 canSupplement: boolean;
 canPurchaseSupplement: boolean;
 onClose(): void;
 onUpdated(): void;
}
export default function ApprovalDetailDrawer({ selected, canReview, canAdmin, canSupplement, canPurchaseSupplement, onClose, onUpdated }: Props) {
 const [detail, setDetail] = useState<ApprovalDetail>();
 const [loading, setLoading] = useState(false);
 const [failedDetailId, setFailedDetailId] = useState<string>();
 const [saving, setSaving] = useState(false);
 const [decision, setDecision] = useState<Decision>();
 const [reattestCase, setReattestCase] = useState<string>();
 const [note, setNote] = useState("");
 const [evidence, setEvidence] = useState("");
 const [messageApi, holder] = message.useMessage();
 useEffect(() => {
  if (!selected) return;
  let live = true;
  void (selected.status === "legacy_unverified" ? fetchLegacyApprovalDetail(selected.id) : fetchApprovalDetail(selected.id)).then((value) => {
   if (live) { setDetail(value); setFailedDetailId(undefined); }
  }).catch(() => { if (live) { setFailedDetailId(selected.id); void messageApi.error("无法加载审批详情"); } })
   .finally(() => { if (live) setLoading(false); });
  return () => { live = false; };
 }, [selected, messageApi]);

 const save = async () => {
  if (!shown || !decision || saving) return;
  if ((decision !== "approved" || shown.status === "info_required") && note.trim().length < 5) {
   void messageApi.warning("请填写不少于5个字的意见");
   return;
  }
  setSaving(true);
  try {
   if (shown.status === "info_required") {
    await supplementApproval(shown.id, shown.version, note, evidence);
   } else {
    await decideApproval(shown.id, shown.version, decision, note);
   }
   setDecision(undefined); setNote(""); setEvidence("");
   onClose(); onUpdated();
   void messageApi.success("操作成功");
  } catch {
   void messageApi.error("操作失败，请检查审批状态、权限与业务数据变化");
  } finally { setSaving(false); }
 };
 const shown = detail?.id === selected?.id ? detail : undefined;
 const mayApprove = !shown?.requires_verification && (shown?.approval_type === "wfs_case_abandon" ? canReview : canAdmin) && shown?.can_review && !shown.data_changed && shown.status === "submitted";
 const maySupplement = shown?.can_supplement && (shown.approval_type === "wfs_case_abandon"
  ? canSupplement
  : canAdmin || (shown.approval_type === "purchase_exception" && canPurchaseSupplement));
 return <>
  {holder}
  <Drawer title={selected?.title || "审批详情"} open={!!selected} width={1020}
   destroyOnHidden onClose={onClose}
   footer={shown ? <Space style={{ display: "flex", justifyContent: "flex-end" }}>
    <Button onClick={onClose}>关闭</Button>
    {canSupplement && shown.requires_verification && <Button type="primary" onClick={() => setReattestCase(shown.business_ref)}>补充核验并提交</Button>}
    {maySupplement &&
     <Button onClick={() => { setDecision("info_required"); setNote(""); }}>补充资料后重新提交</Button>}
    {mayApprove && <>
     <Button onClick={() => { setDecision("info_required"); setNote(""); }}>要求补资料</Button>
     <Button danger onClick={() => { setDecision("rejected"); setNote(""); }}>驳回申请</Button>
     <Button type="primary" onClick={() => { setDecision("approved"); setNote(""); }}>审批通过</Button>
    </>}
   </Space> : null}>
   {failedDetailId === selected?.id && <Alert type="error" showIcon message="审批详情加载失败" description="请关闭后重新打开或刷新列表重试" />}
   {(loading || (!!selected && !shown && failedDetailId !== selected.id)) && <Spin />}
   {shown && <>
    <Alert showIcon type="info" message={"审批状态：" + statusNames[shown.status]}
      description={shown.requires_verification ? "历史 Case ID：" + shown.business_ref + " · 原始申请人身份待核验" : "审批ID：" + shown.id + " · 申请人：" + (shown.applicant_id || "未知")} />
    {shown.requires_verification && <Alert type="warning" showIcon message="历史待核验 · 禁止直接审批" description="历史申请理由与证据未完整保留；申请人身份及时间来源尚未核验。本记录仅供核查，不是正式审批单。" />}
    {shown.approval_type === "wfs_case_abandon" ? <WfsCaseApprovalDetail detail={shown}/> :
      <GenericApprovalDetail detail={shown} />}
    <Typography.Title level={5}>{shown.requires_verification ? "历史审批事件（未经正式记录）" : "审批事件"}</Typography.Title>
    <Timeline items={shown.events.map((e) => ({
     children: <div><b>{e.event_type}</b> · {e.actor_id} · {e.created_at}
      {e.note && <Typography.Paragraph>{e.note}</Typography.Paragraph>}</div>,
    }))} />
   </>}
  </Drawer>
  <LegacyReattestModal caseId={reattestCase} onClose={() => setReattestCase(undefined)}
   onSuccess={() => { onClose(); onUpdated(); }}/>
  <Modal open={!!decision} title={decision === "approved" ? "确认审批通过？" :
   decision === "rejected" ? "驳回申请" : "要求补充资料"}
   onCancel={() => setDecision(undefined)} onOk={() => void save()}
   okButtonProps={{ loading: saving, danger: decision === "approved" }}>
   <Form layout="vertical">
    <Form.Item label="审批意见"><Input.TextArea value={note} rows={4} maxLength={4000}
     onChange={(e) => setNote(e.target.value)} /></Form.Item>
    {detail?.status === "info_required" && <Form.Item label="补充材料">
     <Input.TextArea value={evidence} rows={3} maxLength={4000}
      onChange={(e) => setEvidence(e.target.value)} /></Form.Item>}
   </Form>
  </Modal>
 </>;
}

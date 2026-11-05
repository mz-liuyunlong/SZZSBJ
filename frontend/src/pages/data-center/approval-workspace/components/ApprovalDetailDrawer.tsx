import {
  Alert,
  Button,
  Checkbox,
  Drawer,
  Form,
  Input,
  Modal,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from "antd";
import {
  CheckCircleOutlined,
  CloseOutlined,
  CopyOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  MessageOutlined,
} from "@ant-design/icons";
import { useEffect, useState } from "react";
import type { ApprovalDetail, ApprovalItem, Decision } from "../approvalTypes";
import {
  decideApproval,
  decideCurrentWfsCase,
  fetchApprovalDetail,
  fetchWfsCaseReviewDetail,
  supplementApproval,
} from "../approvalApi";
import { riskNames, statusNames } from "../approvalTypes";
import { WfsCaseApprovalDetail } from "./WfsCaseApprovalDetail";
import BusinessApprovalDetail from "./BusinessApprovalDetail";

type ReviewAction = Decision | "resubmit";

interface Props {
  reviewOnly?: boolean;
  directReviewAction?: "approved" | "rejected";
  selected?: ApprovalItem;
  canReview: boolean;
  canAdmin: boolean;
  canSupplement: boolean;
  canPurchaseSupplement: boolean;
  onClose(): void;
  onUpdated(): void;
}

const timeText = (value: string | null | undefined) => {
  if (!value) return "时间未记录";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("zh-CN");
};

const reviewTitle: Record<ReviewAction, string> = {
  approved: "审批通过确认",
  rejected: "驳回申请",
  info_required: "要求补充资料",
  resubmit: "补充资料后重新提交",
};

export default function ApprovalDetailDrawer(props: Props) {
  return <ApprovalDetailDrawerInner key={props.selected?.id ?? "closed"} {...props} />;
}

function ApprovalDetailDrawerInner({
  selected,
  reviewOnly = false,
  directReviewAction,
  canReview,
  canAdmin,
  canSupplement,
  canPurchaseSupplement,
  onClose,
  onUpdated,
}: Props) {
  const [detail, setDetail] = useState<ApprovalDetail>();
  const [loading, setLoading] = useState(false);
  const [failedDetailId, setFailedDetailId] = useState<string>();
  const [saving, setSaving] = useState(false);
  const [action, setAction] = useState<ReviewAction>();
  const [note, setNote] = useState("");
  const [evidence, setEvidence] = useState("");
  const [riskConfirmed, setRiskConfirmed] = useState(false);
  const [identityConfirmed, setIdentityConfirmed] = useState(false);
  const [messageApi, holder] = message.useMessage();

  useEffect(() => {
    if (!selected) return;
    let live = true;
    const fetcher = selected.case_review
      ? fetchWfsCaseReviewDetail(selected.id)
      : fetchApprovalDetail(selected.id);
    void fetcher.then((data) => {
      if (live) setDetail(data);
    }).catch(() => {
      if (live) {
        setFailedDetailId(selected.id);
        void messageApi.error("无法加载审批详情");
      }
    }).finally(() => {
      if (live) setLoading(false);
    });
    return () => { live = false; };
  }, [selected, messageApi]);

  const shown = detail?.id === selected?.id ? detail : undefined;
  const mayApprove = Boolean(
    shown && !shown.requires_verification && (shown.status === "submitted" || (shown.case_review && shown.status === "info_required")) &&
    shown.can_review && !shown.data_changed &&
    (shown.approval_type === "wfs_case_abandon" ? canReview : canAdmin),
  );
  // Derived review action opens the decision modal without a state update in an effect.
  const resolvedAction: ReviewAction | undefined = action ?? (
    reviewOnly && directReviewAction && mayApprove ? directReviewAction : undefined
  );

  const maySupplement = Boolean(
    shown && shown.can_supplement &&
    (shown.approval_type === "wfs_case_abandon"
      ? canSupplement
      : canAdmin || (shown.approval_type === "purchase_exception" && canPurchaseSupplement)),
  );

  const openAction = (next: ReviewAction) => {
    setNote("");
    setEvidence("");
    setRiskConfirmed(false);
    setIdentityConfirmed(false);
    setAction(next);
  };

  const closeAction = () => {
    if (saving) return;
    setAction(undefined);
    if (reviewOnly && directReviewAction) onClose();
  };

  const save = async () => {
    if (!shown || !resolvedAction || saving || shown.requires_verification) return;
    if (resolvedAction === "resubmit" ? !maySupplement : !mayApprove) return;
    if (resolvedAction !== "approved" && note.trim().length < 5) {
      void messageApi.warning("请填写至少 5 个字的处理意见");
      return;
    }
    if (shown.case_review && !shown.applicant_id && !identityConfirmed) {
      void messageApi.warning("请确认申请人身份记录缺失的审核风险");
      return;
    }
    if (resolvedAction === "approved" && shown.risk_level === "high" && !riskConfirmed) {
      void messageApi.warning("请确认已审阅高风险业务依据");
      return;
    }
    setSaving(true);
    try {
      if (resolvedAction === "resubmit") {
        await supplementApproval(shown.id, shown.version, note.trim(), evidence.trim());
      } else if (shown.case_review) {
        await decideCurrentWfsCase(shown.business_ref, shown.version, resolvedAction, note.trim(), identityConfirmed);
      } else {
        await decideApproval(shown.id, shown.version, resolvedAction, note.trim());
      }
      setAction(undefined);
      onClose();
      onUpdated();
      void messageApi.success("操作成功");
    } catch {
      void messageApi.error("操作失败，请检查审批权限、版本及业务状态");
    } finally {
      setSaving(false);
    }
  };

  const copyId = async () => {
    if (!shown) return;
    try {
      await navigator.clipboard.writeText(shown.id);
      void messageApi.success("编号已复制");
    } catch {
      void messageApi.warning("复制失败，请手动复制编号");
    }
  };

  const detailName = shown?.approval_type === "wfs_case_abandon" ? "WFS费用" : "业务审批";
  const riskLevel = shown?.risk_level ?? selected?.risk_level;
  const isWfs = shown?.approval_type === "wfs_case_abandon";

  return <>
    {holder}
    <Drawer
      className="approval-review-drawer"
      title={null}
      closable={false}
      open={Boolean(selected) && !reviewOnly}
      width={1040}
      destroyOnHidden
      onClose={onClose}
      styles={{ header: { display: "none" }, body: { padding: 0, overflow: "hidden" }, footer: { padding: 0 } }}
      footer={shown ? <div className="approval-review__footer">
        <div className="approval-review__footer-context">
          <strong>{shown.title}</strong>
          <span>{`申请人 ${shown.applicant_id || "未记录"} · ${timeText(shown.submitted_at)}`}</span>
        </div>
        <Space wrap size={8}>
          {!mayApprove && !maySupplement ? <Tag color="default">"当前无可用审核操作"</Tag> : null}
          {maySupplement ? <Button icon={<FileTextOutlined />} onClick={() => openAction("resubmit")}>补充资料后重新提交</Button> : null}
          {mayApprove ? <>
            <Button icon={<MessageOutlined />} onClick={() => openAction("info_required")}>要求补充资料</Button>
            <Button danger icon={<CloseOutlined />} onClick={() => openAction("rejected")}>驳回</Button>
            <Button type="primary" icon={<CheckCircleOutlined />} onClick={() => openAction("approved")}>审批通过</Button>
          </> : null}
        </Space>
      </div> : undefined}
    >
      <div className="approval-review__shell">
        <header className="approval-review__header">
          <div className="approval-review__header-main">
            <div className="approval-review__tags">
              <Tag color="blue">{detailName}</Tag>
              {riskLevel ? <Tag color={riskLevel === "high" ? "red" : riskLevel === "medium" ? "orange" : "green"}>{riskNames[riskLevel]}</Tag> : null}
              <Tag color="processing">{shown ? statusNames[shown.status] : selected ? statusNames[selected.status] : "加载中"}</Tag>
            </div>
            <h2>{shown?.title || selected?.title || "审批详情"}</h2>
            <div className="approval-review__subline">
              <span>{shown ? (shown.case_review ? `WFS Case ${shown.id}` : `审批单 ${shown.id}`) : "正在读取审批信息"}</span>
              {shown ? <span>业务对象：{shown.business_ref}</span> : null}
              <span>{shown ? timeText(shown.submitted_at) : ""}</span>
            </div>
          </div>
          <Space size={8}>
            {shown ? <Button aria-label="复制审批编号" icon={<CopyOutlined />} onClick={() => void copyId()} /> : null}
            <Button aria-label="关闭审批详情" icon={<CloseOutlined />} onClick={onClose} />
          </Space>
        </header>

        <div className="approval-review__scroll">
          {failedDetailId === selected?.id ?
            <Alert showIcon type="error" message="审批详情加载失败" description="请关闭后重新打开或刷新列表重试" /> : null}
          {loading || (selected && !shown && failedDetailId !== selected.id) ?
            <div className="approval-review__center"><Spin tip="正在读取审批详情"><div className="approval-review__spin-placeholder" /></Spin></div> : null}
          {shown ? <>
            {isWfs ? <WfsCaseApprovalDetail detail={shown} /> :
              <div className="approval-review__generic"><BusinessApprovalDetail detail={shown} /></div>}
          </> : null}
        </div>
      </div>
    </Drawer>

    <Modal
      className="approval-review__decision-modal"
      open={Boolean(resolvedAction)}
      title={<div><div className="approval-review__modal-eyebrow">APPROVAL DECISION</div>{resolvedAction ? reviewTitle[resolvedAction] : "审批操作"}</div>}
      onCancel={closeAction}
      onOk={() => void save()}
      okText={resolvedAction === "approved" ? "确认通过" : resolvedAction === "rejected" ? "确认驳回" : resolvedAction === "resubmit" ? "重新提交" : "发送补充要求"}
      okButtonProps={{ loading: saving, danger: resolvedAction === "rejected" }}
      okType={resolvedAction === "rejected" ? "default" : "primary"}
      cancelButtonProps={{ disabled: saving }}
      maskClosable={!saving}
      destroyOnHidden
    >
      {shown ? <div className="approval-review__modal-context">
        <ExclamationCircleOutlined />
        <div><strong>{shown.title}</strong><span>{riskLevel ? riskNames[riskLevel] : ""} · {`申请人 ${shown.applicant_id || "未记录"}`}</span></div>
      </div> : null}
      <Form layout="vertical" style={{ marginTop: 18 }}>
        <Form.Item label={resolvedAction === "approved" ? "审批意见（选填）" : resolvedAction === "rejected" ? "驳回原因（至少 5 个字）" : resolvedAction === "resubmit" ? "补充说明（至少 5 个字）" : "需补充的材料（至少 5 个字）"}>
          <Input.TextArea rows={4} value={note} onChange={(event) => setNote(event.target.value)} maxLength={4000} showCount placeholder={resolvedAction === "approved" ? "填写审批依据，便于后续追溯" : "请明确原因与下一步要求"} />
        </Form.Item>
        {resolvedAction === "resubmit" ? <Form.Item label="补充证据"><Input.TextArea rows={3} value={evidence} onChange={(event) => setEvidence(event.target.value)} maxLength={4000} showCount /></Form.Item> : null}
        {shown?.case_review && !shown.applicant_id ? <Checkbox checked={identityConfirmed} onChange={(event) => setIdentityConfirmed(event.target.checked)}>
          我确认本 Case 缺少可验证的申请人身份，已核查业务资料并承担当前审核决定。
        </Checkbox> : null}
        {resolvedAction === "approved" && riskLevel === "high" ? <Checkbox checked={riskConfirmed} onChange={(event) => setRiskConfirmed(event.target.checked)}>我已核对业务金额、申请原因、历史跟进与关联证据，并了解通过后的业务影响。</Checkbox> : null}
        <Typography.Text type="secondary" className="approval-review__modal-hint">本操作将使用当前登录账号提交，由后端校验权限、业务状态、版本及审批记录。</Typography.Text>
      </Form>
    </Modal>
  </>;
}

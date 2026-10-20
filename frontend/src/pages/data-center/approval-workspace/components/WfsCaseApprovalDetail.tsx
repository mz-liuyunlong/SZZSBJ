import { Alert, Tag, Timeline } from "antd";
import {
  FileTextOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import type { ReactNode } from "react";
import type { ApprovalDetail } from "../approvalTypes";
import { parseFollowLog } from "../followLog";
import { formatMoney } from "@/shared/formatters/money";

const display = (value: unknown) => value === null || value === undefined || value === "" ? "—" : String(value);
const money = (value: unknown, currency: unknown) => value === null || value === undefined || value === ""
  ? "—" : formatMoney(value, { currency: String(currency || "USD") });
interface Props {
  detail: ApprovalDetail;
}

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return <section className="approval-review__section">
    <div className="approval-review__section-title"><strong>{title}</strong>{hint ? <span>{hint}</span> : null}</div>
    {children}
  </section>;
}

function FollowTimeline({ lines }: { lines: string[] }) {
  if (!lines.length) return <div className="approval-review__note-empty">暂无运营跟进记录</div>;
  return <Timeline items={[...lines].reverse().map((line, index) => ({
    color: index === 0 ? "blue" : "gray",
    children: <div className="approval-review__timeline-item">
      <div><strong>第 {lines.length - index} 条跟进</strong>{index === 0 ? <Tag color="blue">最新</Tag> : null}</div>
      <p>{line}</p>
    </div>,
  }))} />;
}

function Facts({ data }: { data: [string, unknown][] }) {
  return <div className="approval-review__facts">
    {data.map(([label, value]) => <div
        className={`approval-review__fact${label === "产品名称" ? " approval-review__fact--product" : ""}`}
        key={label}
      >
      <span>{label}</span><strong title={display(value)}>{display(value)}</strong>
    </div>)}
  </div>;
}

export function WfsCaseApprovalDetail({ detail }: Props) {
  const item = detail.snapshot;
  const lines = parseFollowLog(item.follow_log);
  const legacy = Boolean(detail.requires_verification);
  const currentCaseReview = Boolean(detail.case_review);
  const unit = item.unit_fee_diff;
  const risk = detail.risk_level;
  const amount = money(item.pending_recover_amount, item.currency_code);
  const caseStatusNames: Record<string, string> = {
    archive_pending: "待归档审核",
    archived: "已归档",
    rejected: "已驳回",
    closed: "已关闭",
    recovered: "已追回",
    following: "跟进中",
    open: "已开Case",
    unopened: "未开Case",
  };

  const caseStatusText =
    caseStatusNames[String(item.status ?? "")] ??
    (item.status ? "未知状态" : "—");

  const openedAt = item.case_opened_at ?? item.first_alert_at;
  const openedDate = openedAt ? new Date(openedAt) : null;
  const openedText = openedDate && !Number.isNaN(openedDate.getTime())
    ? openedDate.toLocaleString("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

  const facts: [string, unknown][] = [
    ["平台 / 店铺", item.store_name_snapshot || item.store_id],
    ["SKU / MSKU", [item.local_sku_snapshot, item.msku].filter(Boolean).join(" / ")],
    ["产品名称", item.product_name_snapshot],
    ["Item ID", item.item_id],
    ["运营负责人", item.owner_name_snapshot],
    ["平台 Case 编号", item.case_nos || "尚未填写"],
    [
      currentCaseReview
        ? "当前 Case 状态"
        : legacy
          ? "来源 Case 状态"
          : "申请前业务状态",
      caseStatusText,
    ],
    ["立案时间", openedText],
    ["受影响计费数量", item.affected_units],
    [
      "实收 / 人工费率",
      `${money(item.actual_unit_fee, item.currency_code)} / ${money(item.manual_unit_fee, item.currency_code)}`,
    ],
    ["索赔申报金额", money(item.claim_amount, item.currency_code)],
  ];

  const tiles: [string, string, string][] = [
    ["预计追回", money(item.estimated_recover_amount, item.currency_code), "原业务记录"],
    ["已追回", money(item.recovered_amount, item.currency_code), "已记录到账"],
    ["待追回", amount, "尚未追回金额"],
    ["单件差额", money(unit, item.currency_code), "按原费率数据"],
    ["运营跟进", `${lines.length} 次`, "完整记录如下"],
    ["Case 编号", display(item.case_nos), "Walmart 平台编号"],
  ];

  return <div className="approval-review__columns">
    <div className="approval-review__primary">
      <Section title="01 / 审批决策摘要" hint={currentCaseReview ? "当前业务数据 · Case 审核" : legacy ? "当前业务数据 · 非正式提交快照" : "申请快照与当前业务对照"}>
        <div className="approval-review__amount-summary">
          <div><span>当前待追回金额</span><strong>{amount}</strong><small>{legacy ? "来源数据待核验" : "审批关联金额"}</small></div>
          <Tag color={risk === "high" ? "red" : risk === "medium" ? "orange" : "green"}>{risk === "high" ? "高风险" : risk === "medium" ? "中风险" : "低风险"}</Tag>
        </div>
        {detail.data_changed ? <Alert showIcon type="error" message="申请后业务数据已发生变化" description="当前业务值与申请快照不一致，正式审核接口会阻止直接审批。" /> : null}
        {legacy ? <div className="approval-review__insight"><SafetyCertificateOutlined />本记录是历史 Case 资料，缺少可信的正式提交身份与审批事件；审核前须建立可追溯的新申请。</div> : null}
        {!item.case_nos ? <div className="approval-review__insight"><FileTextOutlined />尚未填写 Walmart Case 编号，请检查是否已提交平台申诉。</div> : null}
        {item.walmart_response_summary ? <div className="approval-review__insight">平台回复：{display(item.walmart_response_summary)}</div> : null}
      </Section>
      <Section title="02 / 业务关键指标" hint="按真实来源字段展示">
        <div className="approval-review__tiles">{tiles.map(([label, value, note]) => <div className="approval-review__tile" key={label}>
          <span>{label}</span><strong title={value}>{value}</strong><small>{note}</small>
        </div>)}</div>
      </Section>
      <Section title="03 / 业务对象详情"><Facts data={facts} /></Section>

    </div>
    <aside
      className="approval-review__secondary"
      style={{
        minWidth: 0,
        alignSelf: "start",
        maxHeight: "calc(100vh - 230px)",
        overflowY: "auto",
        overflowX: "hidden",
        overflowWrap: "anywhere",
      }}
    >
      <Section title="申请人">
        <div className="approval-review__copy">
          {detail.applicant_id || "未记录申请人"}
        </div>
      </Section>

      <Section title="放弃申请原因">
        <div
          className="approval-review__copy"
          style={{
            whiteSpace: "pre-wrap",
            overflowWrap: "anywhere",
          }}
        >
          {detail.reason?.trim() || "未记录放弃申请原因"}
        </div>
      </Section>

      <Section
        title="完整运营跟进"
        hint={`共 ${lines.length} 条 · 最新在前`}
      >
        <div style={{ minWidth: 0, overflowWrap: "anywhere" }}>
          <FollowTimeline lines={lines} />
        </div>
      </Section>
    </aside>
  </div>;
}

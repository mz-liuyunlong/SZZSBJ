import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  DollarOutlined,
  ExclamationCircleOutlined,
  FileSearchOutlined,
  PlusOutlined,
  UndoOutlined,
} from "@ant-design/icons";
import { Card } from "antd";
import {
  formatWfsMoney,
  getWfsFeeAlertSummary,
  type WfsFeeAlertCurrency,
  type WfsFeeAlertRow,
} from "@/pages/warehouse/wfsFeeAlertTypes";

interface WfsFeeAlertSummaryCardsProps {
  rows: WfsFeeAlertRow[];
  currency: WfsFeeAlertCurrency;
}

function WfsFeeAlertSummaryCards({ rows, currency }: WfsFeeAlertSummaryCardsProps) {
  const summary = getWfsFeeAlertSummary(rows);
  const cards = [
    {
      key: "alertSkuCount",
      label: "异常SKU",
      value: summary.alertSkuCount.toLocaleString("zh-CN"),
      hint: "WFS费用多收",
      icon: <ExclamationCircleOutlined aria-hidden="true" />,
      tone: "red",
    },
    {
      key: "totalOverFee",
      label: "多收金额",
      value: formatWfsMoney(summary.totalOverFee, currency),
      hint: "应追回",
      icon: <DollarOutlined aria-hidden="true" />,
      tone: "orange",
    },
    {
      key: "recoveredAmount",
      label: "已追回",
      value: formatWfsMoney(summary.totalRecoveredAmount, currency),
      hint: "已入账/确认",
      icon: <CheckCircleOutlined aria-hidden="true" />,
      tone: "green",
    },
    {
      key: "pendingAmount",
      label: "待追回",
      value: formatWfsMoney(summary.pendingAmount, currency),
      hint: "多收-已追回",
      icon: <UndoOutlined aria-hidden="true" />,
      tone: "purple",
    },
    {
      key: "openedCaseCount",
      label: "已开Case",
      value: summary.openedCaseCount.toLocaleString("zh-CN"),
      hint: "含跟进中",
      icon: <FileSearchOutlined aria-hidden="true" />,
      tone: "blue",
    },
    {
      key: "unopenedCaseCount",
      label: "未开Case",
      value: summary.unopenedCaseCount.toLocaleString("zh-CN"),
      hint: "需要处理",
      icon: <PlusOutlined aria-hidden="true" />,
      tone: "orange",
    },
    {
      key: "followDueCount",
      label: "待跟进",
      value: summary.followDueCount.toLocaleString("zh-CN"),
      hint: "今日/明日到期",
      icon: <ClockCircleOutlined aria-hidden="true" />,
      tone: "red",
    },
  ];

  return (
    <section className="wfs-fee-alert__summary" aria-label="WFS费用异常统计">
      {cards.map((card) => (
        <Card key={card.key} size="small" className={`wfs-fee-alert__summary-card wfs-fee-alert__summary-card--${card.tone}`}>
          <span className="wfs-fee-alert__summary-icon">{card.icon}</span>
          <span>
            <span className="wfs-fee-alert__summary-label">{card.label}</span>
            <strong>{card.value}</strong>
            <small>{card.hint}</small>
          </span>
        </Card>
      ))}
    </section>
  );
}

export default WfsFeeAlertSummaryCards;

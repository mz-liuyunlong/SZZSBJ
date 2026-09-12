import {
  AppstoreOutlined,
  CheckOutlined,
  CloseOutlined,
  PlayCircleOutlined,
  SyncOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { Card } from "antd";
import type { ReactNode } from "react";
import type { SyncTaskRow } from "@/pages/data-center/syncTaskTypes";

interface SyncTaskSummaryCardsProps {
  rows: SyncTaskRow[];
}

interface MetricItem {
  key: string;
  title: string;
  value: string;
  icon: ReactNode;
  tone: "blue" | "green" | "red" | "purple" | "orange";
  trend: string;
  trendTone: "up" | "down" | "flat";
}

function SyncTaskSummaryCards({ rows }: SyncTaskSummaryCardsProps) {
  const todaySuccess = rows.reduce((total, row) => total + row.todaySuccess, 0);
  const todayFailed = rows.reduce((total, row) => total + row.todayFailed, 0);
  const metrics: MetricItem[] = [
    {
      key: "total",
      title: "任务总数",
      value: rows.length.toLocaleString("zh-CN"),
      icon: <AppstoreOutlined />,
      tone: "blue",
      trend: "全部",
      trendTone: "flat",
    },
    {
      key: "auto",
      title: "自动同步中",
      value: rows.filter((row) => row.autoSync).length.toLocaleString("zh-CN"),
      icon: <PlayCircleOutlined />,
      tone: "green",
      trend: "+2",
      trendTone: "up",
    },
    {
      key: "success",
      title: "今日成功",
      value: todaySuccess.toLocaleString("zh-CN"),
      icon: <CheckOutlined />,
      tone: "green",
      trend: "+12.5%",
      trendTone: "up",
    },
    {
      key: "failed",
      title: "今日失败",
      value: todayFailed.toLocaleString("zh-CN"),
      icon: <CloseOutlined />,
      tone: "red",
      trend: "-8.1%",
      trendTone: "down",
    },
    {
      key: "running",
      title: "运行中",
      value: rows.filter((row) => row.lastStatus === "运行中").length.toLocaleString("zh-CN"),
      icon: <SyncOutlined spin />,
      tone: "purple",
      trend: "当前",
      trendTone: "flat",
    },
    {
      key: "partial",
      title: "部分成功",
      value: rows.filter((row) => row.lastStatus === "部分成功").length.toLocaleString("zh-CN"),
      icon: <WarningOutlined />,
      tone: "orange",
      trend: "需看",
      trendTone: "down",
    },
  ];

  return (
    <section className="sync-task__summary" aria-label="同步任务指标">
      {metrics.map((metric) => (
        <Card
          key={metric.key}
          size="small"
          className={`sync-task__summary-card sync-task__summary-card--${metric.tone}`}
        >
          <span className="sync-task__summary-icon" aria-hidden="true">
            {metric.icon}
          </span>
          <span className="sync-task__summary-content">
            <span className="sync-task__summary-title">{metric.title}</span>
            <strong>{metric.value}</strong>
          </span>
          <span className={`sync-task__summary-trend sync-task__summary-trend--${metric.trendTone}`}>
            {metric.trend}
          </span>
        </Card>
      ))}
    </section>
  );
}

export default SyncTaskSummaryCards;

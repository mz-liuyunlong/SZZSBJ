import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Card, Space, Tabs, Tag, Typography, message } from "antd";
import { useMemo, useState } from "react";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import { MoneyCell, PercentCell, RoiCell } from "@/components/report-table/cells";
import {
  campaignRows,
  reportTaskRows,
  searchTermRows,
} from "@/pages/ads/campaigns/adsCampaignMockData";
import type {
  AdsCampaign,
  ReportTaskRow,
  SearchTermRow,
} from "@/pages/ads/campaigns/adsCampaignTypes";

type ReportTabKey = "today" | "center" | "searchTerms";

const reportStatusColor: Record<ReportTaskRow["status"], string> = {
  completed: "success",
  running: "processing",
  failed: "error",
};

function AdsReportsTab() {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [activeTab, setActiveTab] = useState<ReportTabKey>("today");

  const todaySummary = useMemo(() => {
    const spend = campaignRows.reduce((total, row) => total + row.spend, 0);
    const sales = campaignRows.reduce((total, row) => total + row.sales, 0);
    const clicks = campaignRows.reduce((total, row) => total + row.clicks, 0);
    const orders = campaignRows.reduce((total, row) => total + row.orders, 0);
    return {
      spend,
      sales,
      acos: sales > 0 ? spend / sales * 100 : 0,
      clicks,
      orders,
    };
  }, []);

  const todayColumns: ProColumns<AdsCampaign>[] = [
    { title: "广告活动", dataIndex: "name", width: 260, ellipsis: true },
    { title: "花费", dataIndex: "spend", width: 100, render: (_, row) => <MoneyCell value={row.spend} /> },
    { title: "销售额", dataIndex: "sales", width: 110, render: (_, row) => <MoneyCell value={row.sales} /> },
    { title: "订单", dataIndex: "orders", width: 80 },
    { title: "ACOS", dataIndex: "acos", width: 90, render: (_, row) => <PercentCell value={row.acos} /> },
    { title: "ROAS", dataIndex: "roas", width: 90, render: (_, row) => <RoiCell value={row.roas} /> },
    {
      title: "预算消耗",
      key: "budgetUse",
      width: 100,
      render: (_, row) => <PercentCell value={row.dailyBudget > 0 ? row.spend / row.dailyBudget * 100 : null} />,
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 90,
      render: (_, row) => <Tag color={row.status === "enabled" ? "success" : "default"}>{row.status === "enabled" ? "进行中" : "已暂停"}</Tag>,
    },
  ];

  const taskColumns: ProColumns<ReportTaskRow>[] = [
    { title: "任务ID", dataIndex: "id", width: 120 },
    { title: "报表类型", dataIndex: "reportType", width: 130 },
    { title: "日期范围", dataIndex: "dateRange", width: 190 },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (_, row) => <Tag color={reportStatusColor[row.status]}>{row.status === "completed" ? "已完成" : row.status === "running" ? "生成中" : "失败"}</Tag>,
    },
    { title: "生成时间", dataIndex: "createdAt", width: 170 },
    {
      title: "操作",
      valueType: "option",
      width: 110,
      render: (_, row) => (
        <Button type="link" onClick={() => void messageApi.info(`字段说明：${row.reportType}`)}>
          字段说明
        </Button>
      ),
    },
  ];

  const searchTermColumns: ProColumns<SearchTermRow>[] = [
    { title: "搜索词", dataIndex: "term", width: 220 },
    { title: "活动", dataIndex: "campaignName", width: 220, ellipsis: true },
    { title: "关键词", dataIndex: "keyword", width: 150 },
    { title: "花费", dataIndex: "spend", width: 90, render: (_, row) => <MoneyCell value={row.spend} /> },
    { title: "点击", dataIndex: "clicks", width: 80 },
    { title: "订单", dataIndex: "orders", width: 80 },
    { title: "销售额", dataIndex: "sales", width: 100, render: (_, row) => <MoneyCell value={row.sales} /> },
    { title: "ACOS", dataIndex: "acos", width: 90, render: (_, row) => <PercentCell value={row.acos} /> },
    {
      title: "建议",
      dataIndex: "suggestion",
      width: 100,
      render: (_, row) => <Tag color={row.suggestion === "negative" ? "error" : "success"}>{row.suggestion === "negative" ? "否定" : "加词"}</Tag>,
    },
    {
      title: "操作",
      valueType: "option",
      width: 120,
      render: (_, row) => (
        <Button type="link" onClick={() => void messageApi.success(row.suggestion === "negative" ? "已加入否定词" : "已加入关键词")}>
          {row.suggestion === "negative" ? "加入否定词" : "加入关键词"}
        </Button>
      ),
    },
  ];

  return (
    <div className="ads-campaigns-reports">
      {messageContextHolder}
      <Tabs
        className="ads-campaigns-sub-tabs"
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as ReportTabKey)}
        items={[
          { key: "today", label: "今日数据" },
          { key: "center", label: "报表中心" },
          { key: "searchTerms", label: "搜索词数据" },
        ]}
      />

      {activeTab === "today" && (
        <>
          <section className="ads-campaigns-kpi-grid">
            <Card size="small"><Typography.Text type="secondary">今日花费</Typography.Text><strong>${todaySummary.spend.toFixed(2)}</strong></Card>
            <Card size="small"><Typography.Text type="secondary">今日销售额</Typography.Text><strong>${todaySummary.sales.toFixed(2)}</strong></Card>
            <Card size="small"><Typography.Text type="secondary">今日 ACOS</Typography.Text><strong>{todaySummary.acos.toFixed(2)}%</strong></Card>
            <Card size="small"><Typography.Text type="secondary">点击</Typography.Text><strong>{todaySummary.clicks}</strong></Card>
            <Card size="small"><Typography.Text type="secondary">订单</Typography.Text><strong>{todaySummary.orders}</strong></Card>
          </section>
          <ReportTableShell label="今日广告活动数据" className="ads-campaigns-table-shell">
            <div className="ads-campaigns-table-head">
              <Typography.Text strong>今日广告活动数据</Typography.Text>
            </div>
            <ProTable<AdsCampaign>
              rowKey="id"
              size="small"
              search={false}
              options={false}
              columns={todayColumns}
              dataSource={campaignRows}
              pagination={{ pageSize: 10 }}
              scroll={{ x: 980 }}
            />
          </ReportTableShell>
        </>
      )}

      {activeTab === "center" && (
        <>
          <Card size="small" className="ads-campaigns-toolbar">
            <Space wrap>
              <Button type="primary" onClick={() => void messageApi.success("报表任务已创建")}>
                创建报表任务
              </Button>
              <Button onClick={() => void messageApi.info("keyword / adItem 最新报表日期：2026-10-06")}>
                查看最新报表日期
              </Button>
              <Typography.Text type="secondary">
                支持 keyword / adItem / itemKeyword / attributedPurchases
              </Typography.Text>
            </Space>
          </Card>
          <ReportTableShell label="报表任务" className="ads-campaigns-table-shell">
            <div className="ads-campaigns-table-head">
              <Typography.Text strong>报表任务</Typography.Text>
            </div>
            <ProTable<ReportTaskRow>
              rowKey="id"
              size="small"
              search={false}
              options={false}
              columns={taskColumns}
              dataSource={reportTaskRows}
              pagination={false}
              scroll={{ x: 880 }}
            />
          </ReportTableShell>
        </>
      )}

      {activeTab === "searchTerms" && (
        <ReportTableShell label="搜索词数据" className="ads-campaigns-table-shell">
          <div className="ads-campaigns-table-head">
            <Typography.Text strong>搜索词数据</Typography.Text>
            <Button type="primary" onClick={() => void messageApi.success("批量加入否定词已提交")}>
              批量加入否定词
            </Button>
          </div>
          <ProTable<SearchTermRow>
            rowKey="id"
            size="small"
            search={false}
            options={false}
            columns={searchTermColumns}
            dataSource={searchTermRows}
            pagination={{ pageSize: 10 }}
            scroll={{ x: 1180 }}
          />
        </ReportTableShell>
      )}
    </div>
  );
}

export default AdsReportsTab;

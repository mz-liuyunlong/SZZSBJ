/** Enterprise approval workbench. Reuses shared table, search and column components. */
import { Button, Card, Popover, Segmented, Space, Spin, message } from "antd";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import {
  SettingOutlined,
  ReloadOutlined,
  ClockCircleOutlined,
  WarningOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
  ArrowRightOutlined,
} from "@ant-design/icons";
import { useCallback, useEffect, useMemo, useState } from "react";
import PageShell from "@/components/page/PageShell";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ManagementStatCards, {
  type ManagementStatCardItem,
} from "@/components/report-table/ManagementStatCards";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import RuntimeColumnConfigDrawer from "@/components/report-table/RuntimeColumnConfigDrawer";
import StatusTag from "@/shared/status/StatusTag";
import EmptyState from "@/shared/states/EmptyState";
import { formatMoney } from "@/shared/formatters/money";
import { fetchApprovalSummary, fetchApprovals } from "./approvalApi";
import ApprovalDetailDrawer from "./components/ApprovalDetailDrawer";
import BulkApprovalModal from "./components/BulkApprovalModal";
import type { ApprovalFilters, ApprovalItem, ApprovalSummary, ApprovalTab } from "./approvalTypes";
import { approvalColumnFields, approvalTabs, riskNames, statusNames } from "./approvalTypes";
import { parseFollowLog } from "./followLog";
import type { NavigationPage } from "@/config/navigation";
import { hasPermission } from "@/shared/permissions/mockAccess";
import "./ApprovalWorkspacePage.css";

type ApprovalStatKey =
  | "pending"
  | "high"
  | "info"
  | "approved";

const defaultFilters: ApprovalFilters = {
 tab: "pending", page: 1, page_size: 50,
};
const defaultKeys = approvalColumnFields.map((field) => field.key);
const defaultWidths: Record<string, number> = {
   title: 280, approval_type: 138, follow_log: 300, risk_level: 110, amount: 128,
 case_opened_at: 165, follow_count: 105,
 applicant_id: 135, submitted_at: 173, status: 120, action: 94,
};
const statusTone: Record<string, "success" | "warning" | "error" | "default"> = {
 submitted: "warning", approved: "success", rejected: "error",
 info_required: "warning", withdrawn: "default", legacy_unverified: "warning",
};
export default function ApprovalWorkspacePage({ page, permissions }: {
 page: NavigationPage;
 permissions: readonly string[];
}) {
 const [messageApi, holder] = message.useMessage();
 const [filters, setFilters] = useState<ApprovalFilters>(defaultFilters);
 const [rows, setRows] = useState<ApprovalItem[]>([]);
 const [count, setCount] = useState(0);
 const [summary, setSummary] = useState<ApprovalSummary>({ pending:0, high_risk:0, info_required:0, approved:0, legacy_unverified:0 });
 const [loading, setLoading] = useState(true);
 const [loadError, setLoadError] = useState(false);
 const [selected, setSelected] = useState<ApprovalItem>();
 const [reviewOnly, setReviewOnly] = useState(false);
 const [directReviewAction, setDirectReviewAction] =
  useState<"approved" | "rejected">();
 const [reloadToken, setReloadToken] = useState(0);
 const [columnsOpen, setColumnsOpen] = useState(false);
 const [selectedBulkKeys, setSelectedBulkKeys] = useState<React.Key[]>([]);
 const [bulkRows, setBulkRows] = useState<ApprovalItem[]>([]);
 const selectedRows = rows.filter((row) => selectedBulkKeys.includes(row.id));
 const bulkEligible = selectedRows.length > 0 && selectedRows.every((row) =>
  row.approval_type === "operations_plan_ack" && row.risk_level === "low" &&
  row.status === "submitted" && row.can_review && !row.case_review
 );
 const [columnKeys, setColumnKeys] = useState(defaultKeys);
 const [widths, setWidths] = useState(defaultWidths);
 const change = useCallback((patch: Partial<ApprovalFilters>) => {
  setSelectedBulkKeys([]);
  setLoading(true);
  setFilters((f) => ({ ...f, ...patch, page: patch.page ?? 1 }));
 }, []);
 useEffect(() => {
  let active = true;
  void Promise.all([fetchApprovals(filters), fetchApprovalSummary()])
   .then(([list, stats]) => {
    if (!active) return;
    setLoadError(false);
    setRows(list.data.items);
    setCount(list.meta.total);
    setSummary(stats);
   }).catch(() => {
    if (active) { setLoadError(true); setRows([]); setCount(0); void messageApi.error("审批数据加载失败"); }
   }).finally(() => { if (active) setLoading(false); });
  return () => { active = false; };
 }, [filters, reloadToken, messageApi]);
 const reload = () => { setLoading(true); setReloadToken((current) => current + 1); };
 const columns = useMemo((): ProColumns<ApprovalItem>[] => {
  const map: Record<string, ProColumns<ApprovalItem>> = {
   approval_type: { key:"approval_type", render:(_,r) => <div className="approval-list__type"><span className={`approval-list__category approval-list__category--${r.approval_type === "wfs_case_abandon" ? "wfs" : "other"}`}>{r.approval_type === "wfs_case_abandon" ? "WFS费用" : r.approval_type === "operations_plan_ack" ? "运营事项" : r.approval_type}</span><span className="approval-list__reference" title={r.id}>{r.id.slice(0,8)}</span></div> },
   title: { key:"title", dataIndex:"title", render:(_,row) => <div className="approval-list__subject"><button type="button" onClick={() => setSelected(row)}>{row.title}</button><span title={row.reason}>{row.reason || "暂无申请说明"}</span></div> },
   follow_log: { key:"follow_log", render:(_,r) => {
    const logs = parseFollowLog(r.follow_log);
    if (!logs.length) return <span style={{ color: "#94a3b8" }}>暂无跟进记录</span>;
    const latest = logs[logs.length - 1];
    return <Popover
      placement="bottomLeft"
      trigger="hover"
      mouseEnterDelay={0.15}
      title={`完整运营跟进（${logs.length} 条）`}
      content={<div style={{ width: 420, maxWidth: "min(420px, 80vw)", maxHeight: 400, overflowY: "auto", overflowX: "hidden" }}>
        {[...logs].reverse().map((line,index) => <div key={index} style={{ padding: "10px 2px", borderBottom: index < logs.length-1 ? "1px solid #edf0f4" : undefined, overflowWrap: "anywhere", whiteSpace: "pre-wrap" }}>
          <div style={{ fontWeight: 600, marginBottom: 4, color: "#475569" }}>{`第 ${logs.length-index} 条跟进${index===0 ? " · 最新" : ""}`}</div>
          <div>{line}</div>
        </div>)}
      </div>}
    >
      <span style={{ display: "-webkit-box", WebkitBoxOrient: "vertical", WebkitLineClamp: 2, overflow: "hidden", overflowWrap: "anywhere", cursor: "help", lineHeight: "20px", maxHeight: 40 }}>{latest}</span>
    </Popover>;
  } },
   case_opened_at: {
     key: "case_opened_at",
     render: (_, r) => {
       if (!r.case_opened_at) return "—";
       const date = new Date(r.case_opened_at);
       return Number.isNaN(date.getTime())
         ? "—"
         : date.toLocaleString("zh-CN", {
             year: "numeric",
             month: "2-digit",
             day: "2-digit",
             hour: "2-digit",
             minute: "2-digit",
           });
     },
   },
   follow_count: {
     key: "follow_count",
     render: (_, r) =>
       r.follow_count == null
         ? "—"
         : `${r.follow_count} 次`,
   },
  risk_level: { key:"risk_level", render:(_,r) => <span className={`approval-list__risk approval-list__risk--${r.risk_level}`}><span className="approval-list__risk-dot"/>{riskNames[r.risk_level]}</span> },
   amount: { key:"amount", render:(_,r) => <div className="approval-list__money"><strong>{r.amount === null ? "—" : formatMoney(r.amount,{currency:r.currency_code || "USD"})}</strong><span>{r.amount === null ? "非金额事项" : "关联金额"}</span></div> },
   applicant_id: { key:"applicant_id", render:(_,r) => <div className="approval-list__applicant"><span>{r.applicant_id || "申请人待核实"}</span></div> },
   submitted_at: { key:"submitted_at", render:(_,r) => <div className="approval-list__time"><span>{r.submitted_at ? new Date(r.submitted_at).toLocaleString("zh-CN", {month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"}) : "—"}</span></div> },
   status: { key:"status", render:(_,r) => <StatusTag label={statusNames[r.status]} semantic={statusTone[r.status]}/> },
   action: { key:"action", render:(_,r) => <div className="approval-list__actions"><Button size="small" type="text" onClick={() => setSelected(r)}>详情 <ArrowRightOutlined/></Button>{filters.tab === "pending" && r.can_review && <><Button size="small" onClick={() => {
          setDirectReviewAction("approved");
          setReviewOnly(true);
          setSelected(r);
        }}>通过</Button>
        <Button
          size="small"
          danger
          ghost
          className="approval-list__reject-button"
          onClick={() => {
          setDirectReviewAction("rejected");
          setReviewOnly(true);
          setSelected(r);
        }}>驳回</Button></>}</div> },
  };
  return columnKeys.map((key) => {
   const base = map[key]; const field = approvalColumnFields.find((f) => f.key === key);
   const width = widths[key] || 125;
   return { ...base, title: <ResizableColumnTitle label={field?.title || key} minWidth={90} width={width}
    onWidthChange={(next) => setWidths((current) => ({...current,[key]:next}))} />, width };
  });
 }, [columnKeys, widths, filters.tab]);

 const statCards: ManagementStatCardItem<ApprovalStatKey>[] = [
  {
   key: "pending",
   title: "待审批",
   subtitle: "当前待处理审批事项",
   value: summary.pending,
   tone: "normal",
   icon: <ClockCircleOutlined />,
  },
  {
   key: "high",
   title: "高风险",
   subtitle: "需要重点关注的审批",
   value: summary.high_risk,
   tone: "danger",
   icon: <WarningOutlined />,
  },
  {
   key: "info",
   title: "需补资料",
   subtitle: "等待补充申请材料",
   value: summary.info_required,
   tone: "warning",
   icon: <FileTextOutlined />,
  },
  {
   key: "approved",
   title: "已审批",
   subtitle: "已完成审批事项",
   value: summary.approved,
   tone: "success",
   icon: <CheckCircleOutlined />,
  },
 ];

 return <PageShell page={page}>
  {holder}
  <div className="approval-workspace">
   <div className="approval-workspace__heading">
    <div><h3>审批工作台</h3><p>统一处理业务审批 · 所有审批结论均留痕</p></div>
    <Space>{selectedBulkKeys.length>0 && <Button type="primary" onClick={() => {
      if (!bulkEligible) { void messageApi.warning("所选审批包含不支持批量处理的事项；WFS 请逐条审核"); return; }
      setBulkRows(selectedRows);
     }}>批量审批（{selectedBulkKeys.length}）</Button>}
     <Button icon={<ReloadOutlined/>} onClick={reload}>刷新</Button>
     <Button icon={<SettingOutlined/>} onClick={() => setColumnsOpen(true)}>列配置</Button></Space>
   </div>
   <ManagementStatCards<ApprovalStatKey>
    ariaLabel="审批工作台统计"
    className="approval-workspace__metrics"
    cards={statCards}
    activeKey={
     filters.tab === "approved"
      ? "approved"
      : filters.tab === "pending" && filters.risk_level === "high"
       ? "high"
       : "pending"
    }
    onCardClick={(key) => {
     if (key === "approved") {
      change({ tab: "approved", risk_level: undefined });
     } else if (key === "high") {
      change({ tab: "pending", risk_level: "high" });
     } else {
      change({ tab: "pending", risk_level: undefined });
     }
    }}
   />
   <Card className="approval-workspace__toolbar-card" size="small">
    <Segmented
     className="approval-workspace__primary-tabs"
     options={approvalTabs}
     value={filters.tab}
     onChange={(value) => change({ tab: value as ApprovalTab, risk_level: undefined })}
    />
   </Card>
   <ReportTableShell label="审批任务列表" className="approval-workspace__table">
    {loading ? <Spin /> : loadError ? <EmptyState compact title="审批数据加载失败" description="请检查接口、权限或网络状态，点击刷新重试"/> : count === 0 ? <EmptyState compact title="暂无审批事项" description="当前状态下没有审批任务"/> :
     <ProTable<ApprovalItem> rowKey="id" columns={columns} dataSource={rows}
      rowSelection={{
       columnWidth:48,
       selectedRowKeys:selectedBulkKeys,
       onChange:(keys)=>setSelectedBulkKeys(keys),
       preserveSelectedRowKeys:false,
      }}
      search={false} options={false} toolBarRender={false} bordered={false} size="small"
      scroll={{x:"max-content",y:"100%"}} pagination={{
       current:filters.page,pageSize:filters.page_size,total:count,
       showSizeChanger:true,pageSizeOptions:["20","50","100","200"],
       onChange:(p,s)=>change({page:p,page_size:s}),
      }}/>
    }
   </ReportTableShell>
  </div>
  <BulkApprovalModal rows={bulkRows} onCancel={() => setBulkRows([])}
   onUpdated={() => {setSelectedBulkKeys([]);reload();}}/>
  <RuntimeColumnConfigDrawer open={columnsOpen}
   groups={[{title:"审批列表字段",fields:approvalColumnFields}]} fixedKeys={["title"]}
   appliedKeys={columnKeys} defaultKeys={defaultKeys} onApply={setColumnKeys}
   onClose={() => setColumnsOpen(false)} onSaveTemplate={() => void messageApi.info("列模板暂未接入")}/>
  <ApprovalDetailDrawer reviewOnly={reviewOnly} directReviewAction={directReviewAction}
   selected={selected}
   canReview={hasPermission(permissions, "action:warehouse:wfs-fee-alert:archive-review")}
   canAdmin={hasPermission(permissions, "*")}
   canSupplement={hasPermission(permissions, "action:warehouse:wfs-fee-alert:archive-request")}
   canPurchaseSupplement={hasPermission(permissions, "action:pmc:purchase-board:override")}
   onClose={() => { setSelected(undefined); setReviewOnly(false); setDirectReviewAction(undefined); }}
   onUpdated={reload}
  />
 </PageShell>;
}

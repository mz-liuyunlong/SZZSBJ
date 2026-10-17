/** Enterprise approval workbench. Reuses shared table, search and column components. */
import { Button, Card, Segmented, Space, Spin, message } from "antd";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { SettingOutlined, ReloadOutlined } from "@ant-design/icons";
import { useCallback, useEffect, useMemo, useState } from "react";
import PageShell from "@/components/page/PageShell";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import RuntimeColumnConfigDrawer from "@/components/report-table/RuntimeColumnConfigDrawer";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import ReportFacetSelect from "@/shared/report-filters/ReportFacetSelect";
import StatusTag from "@/shared/status/StatusTag";
import EmptyState from "@/shared/states/EmptyState";
import { formatMoney } from "@/shared/formatters/money";
import { fetchApprovalSummary, fetchApprovals } from "./approvalApi";
import ApprovalDetailDrawer from "./components/ApprovalDetailDrawer";
import ApprovalRequestModal from "./components/ApprovalRequestModal";
import ApprovalRulesDrawer from "./components/ApprovalRulesDrawer";
import ApprovalNotificationsDrawer from "./components/ApprovalNotificationsDrawer";
import type { ApprovalFilters, ApprovalItem, ApprovalSummary, ApprovalRisk, ApprovalTab, ApprovalView } from "./approvalTypes";
import { approvalColumnFields, riskNames, statusNames } from "./approvalTypes";
import type { NavigationPage } from "@/config/navigation";
import { hasPermission } from "@/shared/permissions/mockAccess";
import "./ApprovalWorkspacePage.css";

const defaultFilters: ApprovalFilters = {
 tab: "pending", view: "mine", keyword: "", page: 1, page_size: 50,
};
const defaultKeys = approvalColumnFields.map((field) => field.key);
const defaultWidths: Record<string, number> = {
 title: 280, approval_type: 138, risk_level: 110, amount: 128,
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
 const [reloadToken, setReloadToken] = useState(0);
 const [columnsOpen, setColumnsOpen] = useState(false);
 const [requestOpen, setRequestOpen] = useState(false);
 const [rulesOpen, setRulesOpen] = useState(false);
 const [notificationsOpen, setNotificationsOpen] = useState(false);
 const [columnKeys, setColumnKeys] = useState(defaultKeys);
 const [widths, setWidths] = useState(defaultWidths);
 const [draftSearch, setDraftSearch] = useState({ searchField:"keyword", keyword:"" });
 const change = useCallback((patch: Partial<ApprovalFilters>) =>
  setFilters((f) => ({ ...f, ...patch, page: patch.page ?? 1 })), []);
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
 const reload = () => setReloadToken((current) => current + 1);
 const columns = useMemo((): ProColumns<ApprovalItem>[] => {
  const map: Record<string, ProColumns<ApprovalItem>> = {
   title: { key:"title", dataIndex:"title", fixed:"left", render:(_,row) => <Button type="link" onClick={() => setSelected(row)}>{row.title}</Button> },
   approval_type: { key:"approval_type", dataIndex:"approval_type", render:(_,r) => r.status === "legacy_unverified" ? "WFS · 历史待核验" : r.approval_type === "wfs_case_abandon" ? "WFS 费用异常" : r.approval_type },
   risk_level: { key:"risk_level", render:(_,r) => <StatusTag label={riskNames[r.risk_level]} color={r.risk_level === "high" ? "red" : r.risk_level === "medium" ? "orange" : "default"}/> },
   amount: { key:"amount", render:(_,r) => r.amount === null ? "—" : formatMoney(r.amount,{currency:r.currency_code || "USD"}) },
   applicant_id: { key:"applicant_id", dataIndex:"applicant_id" },
   submitted_at: { key:"submitted_at", render:(_,r) => r.submitted_at ? new Date(r.submitted_at).toLocaleString("zh-CN") : "—" },
   status: { key:"status", render:(_,r) => <StatusTag label={statusNames[r.status]} semantic={statusTone[r.status]}/> },
   action: { key:"action", render:(_,r) => <Button size="small" onClick={() => setSelected(r)}>查看详情</Button> },
  };
  return columnKeys.map((key) => {
   const base = map[key]; const field = approvalColumnFields.find((f) => f.key === key);
   const width = widths[key] || 125;
   return { ...base, title: <ResizableColumnTitle label={field?.title || key} minWidth={90} width={width}
    onWidthChange={(next) => setWidths((current) => ({...current,[key]:next}))} />, width };
  });
 }, [columnKeys, widths]);
 const tabs: { label: string; value: ApprovalTab }[] = [
  {label:"待审批",value:"pending"},{label:"已审批",value:"approved"},{label:"驳回记录",value:"rejected"},
  ...(hasPermission(permissions, "action:warehouse:wfs-fee-alert:archive-review") ? [{label:"历史待核验 ("+summary.legacy_unverified+")",value:"legacy" as ApprovalTab}] : []),
 ];
 return <PageShell page={page}>
  {holder}
  <div className="approval-workspace">
   <div className="approval-workspace__heading">
    <div><h3>审批工作台</h3><p>统一处理业务审批 · 所有审批结论均留痕</p></div>
    <Space><Button type="primary" onClick={() => setRequestOpen(true)}>发起审批</Button>
     {hasPermission(permissions, "action:settings:role-management:configure-permissions") && <Button onClick={() => setRulesOpen(true)}>审批规则</Button>}
     <Button onClick={() => setNotificationsOpen(true)}>审批提醒</Button>
     <Button icon={<ReloadOutlined/>} onClick={reload}>刷新</Button>
     <Button icon={<SettingOutlined/>} onClick={() => setColumnsOpen(true)}>列配置</Button></Space>
   </div>
   <div className="approval-workspace__metrics">
    {([
     ["待我审批",summary.pending, {tab:"pending",risk_level:undefined}],
     ["高风险",summary.high_risk, {tab:"pending",risk_level:"high" as ApprovalRisk}],
     ["需补资料",summary.info_required,{tab:"pending",risk_level:undefined}],
     ["已审批",summary.approved,{tab:"approved",risk_level:undefined}],
    ] as const).map(([label,value,patch]) =>
     <button key={label} type="button" className="approval-workspace__metric" onClick={() => change(patch)}>
      <span>{label}</span><strong>{value}</strong>
     </button>)}
   </div>
   <Card className="approval-workspace__toolbar-card" size="small">
    <Segmented options={tabs} value={filters.tab} onChange={(value) => change({tab:value as ApprovalTab})}/>
    <div className="approval-workspace__controls">
     <Segmented size="small" value={filters.view} onChange={(value) => change({view:value as ApprovalView})}
      options={[{label:"待我审批",value:"mine"},{label:"我发起的",value:"created"},{label:"全部可见",value:"all"}]}/>
     <ReportFacetSelect ariaLabel="审批类型" placeholder="审批类型"
      value={filters.approval_type} options={[{label:"WFS 费用异常",value:"wfs_case_abandon"},{label:"采购异常",value:"purchase_exception"},{label:"财务例外",value:"finance_exception"},{label:"权限变更",value:"access_change"}]}
      onChange={(value) => change({approval_type: typeof value === "string" ? value : undefined})}/>
     <ReportFacetSelect ariaLabel="风险等级" placeholder="风险等级"
      value={filters.risk_level} options={[{label:"高风险",value:"high"},{label:"中风险",value:"medium"},{label:"低风险",value:"low"}]}
      onChange={(value) => change({risk_level: typeof value === "string" ? value as ApprovalRisk : undefined})}/>
     <CommittedSearch typeAriaLabel="搜索类型"
      typeOptions={[{label:"关键词",value:"keyword"}]} typeValue={draftSearch.searchField}
      inputAriaLabel="搜索审批事项" inputPlaceholder="审批事项、原因"
      inputValue={draftSearch.keyword} onCommit={({ keyword }) => {setDraftSearch({ searchField:"keyword", keyword });change({keyword});}}/>
     <ResetButton onClick={() => {setFilters(defaultFilters);setDraftSearch({searchField:"keyword",keyword:""});}} />
    </div>
   </Card>
   <ReportTableShell label="审批任务列表" className="approval-workspace__table">
    {loading ? <Spin /> : loadError ? <EmptyState compact title="审批数据加载失败" description="请检查接口、权限或网络状态，点击刷新重试"/> : count === 0 ? <EmptyState compact title="暂无审批事项" description="当前筛选条件下没有审批任务"/> :
     <ProTable<ApprovalItem> rowKey="id" columns={columns} dataSource={rows}
      search={false} options={false} toolBarRender={false} bordered size="small"
      scroll={{x:"max-content",y:"100%"}} pagination={{
       current:filters.page,pageSize:filters.page_size,total:count,
       showSizeChanger:true,pageSizeOptions:["20","50","100","200"],
       onChange:(p,s)=>change({page:p,page_size:s}),
      }}/>
    }
   </ReportTableShell>
  </div>
  <ApprovalRequestModal open={requestOpen} onClose={() => setRequestOpen(false)} onUpdated={reload}/>
  <ApprovalRulesDrawer open={rulesOpen} onClose={() => setRulesOpen(false)}/>
  <ApprovalNotificationsDrawer open={notificationsOpen} onClose={() => setNotificationsOpen(false)} onRefresh={reload}/>
  <RuntimeColumnConfigDrawer open={columnsOpen}
   groups={[{title:"审批列表字段",fields:approvalColumnFields}]} fixedKeys={["title"]}
   appliedKeys={columnKeys} defaultKeys={defaultKeys} onApply={setColumnKeys}
   onClose={() => setColumnsOpen(false)} onSaveTemplate={() => void messageApi.info("列模板暂未接入")}/>
  <ApprovalDetailDrawer
   selected={selected}
   canReview={hasPermission(permissions, "action:warehouse:wfs-fee-alert:archive-review")}
   canAdmin={permissions.includes("*")}
   canSupplement={hasPermission(permissions, "action:warehouse:wfs-fee-alert:archive-request")}
   onClose={() => setSelected(undefined)}
   onUpdated={reload}
  />
 </PageShell>;
}

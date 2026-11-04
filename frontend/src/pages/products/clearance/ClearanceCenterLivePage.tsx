/** Database-backed WFS Clearance Center. Never falls back to local demo data. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert, AutoComplete, Button, Card, DatePicker, Descriptions, Drawer, Form,
  Input, InputNumber, Modal, Select, Space, Statistic, Switch, Table, Tabs, Tag,
  Typography, message, type TableColumnsType,
} from "antd";
import { FileAddOutlined, ReloadOutlined, SettingOutlined } from "@ant-design/icons";
import type { Dayjs } from "dayjs";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import {
  fetchClearanceListings, fetchClearanceRequests, fetchClearanceSummary,
  fetchEligibleListings, fetchClearanceDetail, fetchClearanceRequestDetail,
  fetchClearanceRules, fetchClearanceReadiness, fetchClearanceFacets, saveClearanceRules, submitClearance,
  updateClearanceProgress, pauseClearance, resumeClearance, withdrawClearance,
  type ClearanceRow, type ClearanceRequest, type ClearanceRequestDetail,
  type ClearanceMethod, type ClearanceRules, type ClearanceSummary, type ClearanceReadiness, type ClearanceFacets,
} from "./clearanceApi";
import "../ClearanceCenterPage.css";

const methods: ClearanceMethod[] = ["降价", "广告清货"];
const reasons = ["长期滞销", "库存资金占用", "质量或售后问题", "季节性商品过季", "经营策略调整", "其他原因"];
const riskLabel: Record<string,string> = {high:"高风险",medium:"中风险",low:"低风险",unknown:"待核实"};
const taskLabel: Record<string,string> = {
  pending:"待审批",approved:"待执行",rejected:"已驳回",
  withdrawn:"已撤回",running:"执行中",paused:"已暂停",done:"已完成",
};
const riskColor: Record<string,string> = {high:"red",medium:"orange",low:"default",unknown:"default"};
const amount = (value: string | null | undefined) =>
  value === null || value === undefined ? "—" : `$${Number(value).toFixed(2)}`;
const display = (value: unknown) =>
  value === null || value === undefined || value === "" ? "—" : String(value);
const qty = (value: unknown) => value == null ? "—" : `${Number(value)} 件`;
const statusColor = (status: string) =>
  status === "approved" || status === "done" ? "blue" :
  status === "rejected" ? "error" : status === "running" ? "processing" : "default";

type ApplyData = {
  target_qty: number;
  reason: string;
  remark: string;
  methods: ClearanceMethod[];
  due_date?: Dayjs;
  proposed_price?: string;
};

type ProgressData = {sold: number; removed: number; disposed: number};

export default function ClearanceCenterLivePage({page}:{page:NavigationPage}) {
  const [messageApi, holder] = message.useMessage();
  const [tab,setTab] = useState("analysis");
  const [store,setStore] = useState("");
  const [sourceAccount,setSourceAccount] = useState("");
  const [facets,setFacets] = useState<ClearanceFacets>({stores:[],accounts:[]});
  const [keyword,setKeyword] = useState("");
  const [searchDraft,setSearchDraft] = useState("");
  const [risk,setRisk] = useState("");
  // Visible rows grow as the table scrolls; SQL still fetches 50 rows at a time.
  const nextListingPage = useRef(2);
  const listingEpoch = useRef(0);
  const listingFetching = useRef(false);
  const listingRowsRef = useRef<ClearanceRow[]>([]);
  const listingTotalRef = useRef(0);
  const [loadingMore,setLoadingMore] = useState(false);
  const [taskPage,setTaskPage] = useState(1);
  const [rows,setRows] = useState<ClearanceRow[]>([]);
  const [tasks,setTasks] = useState<ClearanceRequest[]>([]);
  const [summary,setSummary] = useState<ClearanceSummary | null>(null);
  const [readiness,setReadiness] = useState<ClearanceReadiness | null>(null);
  const [listTotal,setListTotal] = useState(0);
  const [taskTotal,setTaskTotal] = useState(0);
  const [loading,setLoading] = useState(false);
  const [error,setError] = useState("");
  const [inspect,setInspect] = useState<ClearanceRow | null>(null);
  const [manualOpen,setManualOpen] = useState(false);
  const [chooseStep,setChooseStep] = useState<0|1>(0);
  const [eligible,setEligible] = useState<ClearanceRow[]>([]);
  const [eligibleTotal,setEligibleTotal] = useState(0);
  const eligibleNextPage = useRef(2);
  const eligibleEpoch = useRef(0);
  const eligibleFetching = useRef(false);
  const eligibleRowsRef = useRef<ClearanceRow[]>([]);
  const [eligibleLoading,setEligibleLoading] = useState(false);
  const [eligibleKeyword,setEligibleKeyword] = useState("");
  const [chosen,setChosen] = useState<ClearanceRow | null>(null);
  const [applicationSource,setApplicationSource] = useState<"manual"|"auto">("manual");
  const [submitting,setSubmitting] = useState(false);
  const [selectedTask,setSelectedTask] = useState<ClearanceRequestDetail | null>(null);
  const [progress,setProgress] = useState<ProgressData>({sold:0,removed:0,disposed:0});
  const [rulesOpen,setRulesOpen] = useState(false);
  const [ruleAccount,setRuleAccount] = useState("");
  const [ruleConfig,setRuleConfig] = useState<ClearanceRules | null>(null);
  const [ruleSaving,setRuleSaving] = useState(false);
  const [form] = Form.useForm<ApplyData>();

  const reload = useCallback(async () => {
    const epoch = ++listingEpoch.current;
    listingFetching.current = true;
    nextListingPage.current = 2;
    listingRowsRef.current = [];
    listingTotalRef.current = 0;
    setRows([]);
    setLoading(true);
    setLoadingMore(false);
    try {
      const [l,t,summaryData,readinessData,options] = await Promise.all([
        fetchClearanceListings({page:1,page_size:50,store_id:store,
          source_account_ref:sourceAccount,keyword,
          risk_level:risk||undefined}),
        fetchClearanceRequests({page:taskPage,page_size:50,store_id:store,
          source_account_ref:sourceAccount}),
        fetchClearanceSummary(store,sourceAccount),
        fetchClearanceReadiness(store,sourceAccount),
        fetchClearanceFacets(),
      ]);
      if (listingEpoch.current !== epoch) return;
      listingRowsRef.current = l.items;
      listingTotalRef.current = l.total;
      setRows(l.items);
      setListTotal(l.total);
      setTasks(t.items);
      setTaskTotal(t.total);
      setSummary(summaryData);
      setReadiness(readinessData);
      setFacets(options);
      setError("");
    } catch {
      if (listingEpoch.current !== epoch) return;
      setError("清货中心真实数据读取失败，请检查接口权限、数据版本与网络连接。");
      listingRowsRef.current = [];
      listingTotalRef.current = 0;
      setRows([]);
      setListTotal(0);
      setTasks([]);
      setSummary(null);
      setReadiness(null);
    } finally {
      if (listingEpoch.current === epoch) {
        listingFetching.current = false;
        setLoading(false);
      }
    }
  }, [taskPage,store,sourceAccount,keyword,risk]);
  useEffect(()=>{ void Promise.resolve().then(() => reload()); },[reload]);

  const loadMoreListings = useCallback(async () => {
    if (listingFetching.current ||
        listingRowsRef.current.length >= listingTotalRef.current) return;
    const epoch = listingEpoch.current;
    const pageNumber = nextListingPage.current;
    listingFetching.current = true;
    setLoadingMore(true);
    try {
      const result = await fetchClearanceListings({
        page:pageNumber,page_size:50,store_id:store,
        source_account_ref:sourceAccount,keyword,risk_level:risk||undefined,
      });
      if (listingEpoch.current !== epoch) return;
      const seen = new Set(listingRowsRef.current.map(row=>row.listing.id));
      const additions = result.items.filter(row=>!seen.has(row.listing.id));
      listingRowsRef.current = [...listingRowsRef.current,...additions];
      nextListingPage.current = pageNumber+1;
      listingTotalRef.current = result.total;
      setListTotal(result.total);
      setRows(listingRowsRef.current);
    } catch {
      if (listingEpoch.current === epoch) {
        void messageApi.error("加载后续 Listing 失败，请向下滚动重试");
      }
    } finally {
      if (listingEpoch.current === epoch) {
        listingFetching.current = false;
        setLoadingMore(false);
      }
    }
  }, [store,sourceAccount,keyword,risk,messageApi]);

  const stores = useMemo(()=>Array.from(new Map(facets.stores
    .filter(x=>!sourceAccount||x.source_account_ref===sourceAccount).map(x=>[
      x.store_id,{value:x.store_id,label:`${x.store_name||x.store_id} · ${x.source_account_ref}`},
    ])).values()),[facets,sourceAccount]);
  const accountOptions = useMemo(()=>facets.accounts.map(x=>({value:x,label:x})),
    [facets]);

  const loadEligible = useCallback(async (pageNumber:number, search:string) => {
    if (pageNumber > 1 && eligibleFetching.current) return;
    const epoch = pageNumber === 1 ? ++eligibleEpoch.current : eligibleEpoch.current;
    if (pageNumber === 1) {
      eligibleRowsRef.current = [];
      eligibleNextPage.current = 2;
      setEligibleKeyword(search);
      setEligible([]);
      setEligibleTotal(0);
    }
    eligibleFetching.current = true;
    setEligibleLoading(true);
    try {
      const result = await fetchEligibleListings({
        page:pageNumber,page_size:50,keyword:search,
        store_id:store,source_account_ref:sourceAccount,
      });
      if (eligibleEpoch.current !== epoch) return;
      const existing = new Set(eligibleRowsRef.current.map(row=>row.listing.id));
      const next = result.items.filter(row=>!existing.has(row.listing.id));
      eligibleRowsRef.current = pageNumber === 1
        ? result.items : [...eligibleRowsRef.current,...next];
      eligibleNextPage.current = pageNumber+1;
      setEligible(eligibleRowsRef.current);
      setEligibleTotal(result.total);
    } catch {
      if (eligibleEpoch.current !== epoch) return;
      if (pageNumber === 1) {
        eligibleRowsRef.current = [];
        setEligible([]);
        setEligibleTotal(0);
      }
      void messageApi.error("无法读取符合WFS库存条件的商品");
    } finally {
      if (eligibleEpoch.current === epoch) {
        eligibleFetching.current = false;
        setEligibleLoading(false);
      }
    }
  },[store,sourceAccount,messageApi]);

  const openApply = (selected:ClearanceRow|null=null, source:"manual"|"auto"="manual") => {
    setChosen(selected);
    setApplicationSource(source);
    setChooseStep(selected?1:0);
    form.resetFields();
    if (selected) form.setFieldsValue({target_qty:Math.max(1,selected.evaluation.suggested_qty||1),
      methods:["降价"],reason:"长期滞销",remark:""});
    setManualOpen(true);
    if (!selected) void loadEligible(1,"");
  };
  const chooseListing = (record:ClearanceRow) => {
    setChosen(record);
    form.setFieldsValue({target_qty:Math.max(1,record.evaluation.suggested_qty||1),
      methods:["降价"],reason:"长期滞销"});
  };
  const submit = async (values:ApplyData) => {
    if (!chosen || submitting) return;
    setSubmitting(true);
    try {
      await submitClearance({
        listing_id:chosen.listing.id, target_qty:values.target_qty,
        methods:values.methods,reason:values.reason,remark:values.remark,
        due_date:values.due_date?.format("YYYY-MM-DD")||null,
        proposed_price:values.proposed_price||null,source:applicationSource,
      });
      void messageApi.success("清货申请已提交至统一审批工作台");
      setManualOpen(false);setChosen(null);setChooseStep(0);
      setTab("management");setTaskPage(1);
      void reload();
    } catch {void messageApi.error("提交失败，请核对当前WFS可售库存、审批权限及重复申请状态");}
    finally {setSubmitting(false);}
  };
  const openTask = async (item:ClearanceRequest) => {
    try {
      const value = await fetchClearanceRequestDetail(item.id);
      setSelectedTask(value);
      setProgress({sold:item.sold_qty,removed:item.removed_qty,disposed:item.disposed_qty});
    } catch {void messageApi.error("无法读取清货任务详情");}
  };
  const refreshTask = async () => {
    if (!selectedTask) return;
    try {const d=await fetchClearanceRequestDetail(selectedTask.request.id);setSelectedTask(d);}
    catch {setSelectedTask(null);}
    void reload();
  };
  const saveProgress = async () => {
    const current=selectedTask?.request;
    if (!current) return;
    try {
      await updateClearanceProgress(current.id, {
        sold_qty:progress.sold,removed_qty:progress.removed,disposed_qty:progress.disposed,
        expected_version:current.version,
      });
      void messageApi.success("执行进度已记录");
      await refreshTask();
    } catch {void messageApi.error("更新失败：版本已变化或数量超过批准目标");}
  };
  const switchTaskStatus = async (action:"pause"|"resume"|"withdraw") => {
    const current=selectedTask?.request;
    if (!current) return;
    try {
      if(action==="pause")await pauseClearance(current.id);
      else if(action==="resume")await resumeClearance(current.id);
      else await withdrawClearance(current.id);
      void messageApi.success("清货任务状态已更新");
      await refreshTask();
    } catch{void messageApi.error("当前任务状态或权限不允许此操作");}
  };
  const openRules = async () => {
    const account=ruleAccount||sourceAccount||facets.accounts[0]||"";
    if(!account){void messageApi.warning("请先选择有数据的账号");return;}
    setRulesOpen(true);setRuleAccount(account);
    try{setRuleConfig(await fetchClearanceRules(account));}
    catch{setRuleConfig(null);void messageApi.error("规则配置读取失败");}
  };
  const selectRuleAccount = async (account:string) => {
    setRuleAccount(account);
    try{setRuleConfig(await fetchClearanceRules(account));}
    catch{setRuleConfig(null);void messageApi.error("规则配置读取失败");}
  };
  const saveRules = async () => {
    if(!ruleConfig||ruleSaving)return;
    setRuleSaving(true);
    try{
      const result=await saveClearanceRules(ruleConfig);
      setRuleConfig({...ruleConfig,version:result.version,rules:result.rules});
      void messageApi.success("规则版本已保存，将在下次美国太平洋时间 00:00 评估时生效");
      setRulesOpen(false);
      void reload();
    }catch{void messageApi.error("规则保存失败，请检查参数或配置版本是否已更新");}
    finally{setRuleSaving(false);}
  };

  const listingColumns:TableColumnsType<ClearanceRow>=[
    {title:"商品 ID / 品名",key:"name",width:220,render:(_,r)=><div>
      <Button type="link" size="small" style={{padding:0,fontWeight:600}} onClick={()=>{
        void fetchClearanceDetail(r.listing.id).then(setInspect).catch(()=>messageApi.error("详情加载失败"));
      }}>{r.listing.title||r.listing.item_id}</Button>
      <div style={{fontSize:12,color:"#64748b"}}>{r.listing.item_id}</div>
    </div>},
    {title:"SKU / MSKU",key:"sku",width:145,render:(_,r)=><div>{display(r.listing.local_sku)}
      <div style={{fontSize:12,color:"#64748b"}}>{display(r.listing.msku)}</div></div>},
    {title:"店铺 / 负责人",key:"store",width:145,render:(_,r)=><div>{r.listing.store_name||r.listing.store_id}
      <div style={{fontSize:12,color:"#64748b"}}>{display(r.listing.owner_ref)}</div></div>},
    {title:"风险等级",key:"risk",width:105,render:(_,r)=>
      <Tag color={riskColor[r.evaluation.risk_level]}>{riskLabel[r.evaluation.risk_level]}</Tag>},
    {title:"WFS可售",key:"stock",width:95,align:"right",render:(_,r)=>qty(r.evaluation.current_wfs_available)},
    {title:"预计售罄",key:"coverage",width:110,align:"right",
      render:(_,r)=>r.evaluation.coverage_days==null?"—":`${r.evaluation.coverage_days} 天`},
    {title:"30天销量",key:"sales",width:100,align:"right",render:(_,r)=>qty(r.evaluation.sales_30d)},
    {title:"30天利润率",key:"margin",width:115,align:"right",
      render:(_,r)=>r.evaluation.margin_30d_percent==null?"待核实":`${Number(r.evaluation.margin_30d_percent).toFixed(1)}%`},
    {title:"退款率",key:"refund",width:100,align:"right",
      render:(_,r)=>r.evaluation.refund_rate_percent==null?"待核实":`${Number(r.evaluation.refund_rate_percent).toFixed(1)}%`},
    {title:"库存成本",key:"capital",width:115,align:"right",render:(_,r)=>amount(r.evaluation.stock_capital_usd)},
    {title:"操作",key:"action",width:115,fixed:"right",render:(_,r)=><Button type="link" size="small"
      disabled={r.evaluation.current_wfs_available==null||Number(r.evaluation.current_wfs_available)<=0||
        r.evaluation.warnings.includes("WFS_STOCK_UNAVAILABLE_OR_STALE")}
      onClick={()=>openApply(r,r.evaluation.candidate_status==="auto"?"auto":"manual")}>申请清货</Button>},
  ];
  const taskColumns:TableColumnsType<ClearanceRequest>=[
    {title:"申请单号",dataIndex:"id",width:160,render:(v:string)=><Typography.Text copyable={{text:v}}>{v.slice(0,8)}</Typography.Text>},
    {title:"Item ID",dataIndex:"item_id",width:140},
    {title:"店铺",dataIndex:"store_id",width:140},
    {title:"申请人",dataIndex:"requester_id",width:110},
    {title:"申请原因",dataIndex:"reason",width:150},
    {title:"清货方式",dataIndex:"methods",width:200,render:(v:ClearanceMethod[])=>v.join("、")},
    {title:"目标量",dataIndex:"target_qty",width:110,align:"right"},
    {title:"完成量",key:"processed",width:100,align:"right",render:(_,r)=>
      r.sold_qty+r.removed_qty+r.disposed_qty},
    {title:"审批状态",dataIndex:"status",width:110,
      render:(v:string)=><Tag color={statusColor(v)}>{taskLabel[v]||v}</Tag>},
    {title:"操作",key:"actions",width:120,render:(_,r)=><Button type="link" size="small"
      onClick={()=>void openTask(r)}>任务详情</Button>},
  ];
  const eligibleColumns:TableColumnsType<ClearanceRow>=[
    {title:"商品ID / 品名",key:"title",render:(_,r)=><div><strong>{r.listing.title||r.listing.item_id}</strong>
      <div style={{fontSize:12,color:"#64748b"}}>{r.listing.item_id}</div></div>},
    {title:"SKU / MSKU",key:"sku",render:(_,r)=><div>{display(r.listing.local_sku)}
      <div style={{fontSize:12,color:"#64748b"}}>{display(r.listing.msku)}</div></div>},
    {title:"WFS可售",key:"stock",render:(_,r)=>qty(r.evaluation.current_wfs_available)},
    {title:"操作",key:"choose",render:(_,r)=><Button type={chosen?.listing.id===r.listing.id?"primary":"link"}
      size="small" onClick={()=>chooseListing(r)}>{chosen?.listing.id===r.listing.id?"已选择":"选择商品"}</Button>},
  ];
  const detailTabs = (row:ClearanceRow) => [
    {key:"analysis",label:"经营分析",children:<Descriptions size="small" column={3} bordered>
      <Descriptions.Item label="近30天销量">{qty(row.evaluation.sales_30d)}</Descriptions.Item>
      <Descriptions.Item label="预计售罄">{row.evaluation.coverage_days==null?"不可计算":`${row.evaluation.coverage_days} 天`}</Descriptions.Item>
      <Descriptions.Item label="30天利润率">{row.evaluation.margin_30d_percent==null?"待核实":`${row.evaluation.margin_30d_percent}%`}</Descriptions.Item>
      <Descriptions.Item label="退款率">{row.evaluation.refund_rate_percent==null?"待核实":`${row.evaluation.refund_rate_percent}%`}</Descriptions.Item>
      <Descriptions.Item label="库存资金占用">{amount(row.evaluation.stock_capital_usd)}</Descriptions.Item>
      <Descriptions.Item label="建议清货量">{qty(row.evaluation.suggested_qty)}</Descriptions.Item>
    </Descriptions>},
    {key:"inventory",label:"库存与风险",children:<Descriptions size="small" column={3} bordered>
      <Descriptions.Item label="WFS可售库存">{qty(row.evaluation.current_wfs_available)}</Descriptions.Item>
      <Descriptions.Item label="30天有货天数">{row.evaluation.positive_stock_days_30d}</Descriptions.Item>
      <Descriptions.Item label="库存快照覆盖">{row.evaluation.snapshot_coverage_days_30d}</Descriptions.Item>
      <Descriptions.Item label="Listing评分">{display(row.listing.average_rating)}</Descriptions.Item>
      <Descriptions.Item label="评论数">{display(row.listing.review_count)}</Descriptions.Item>
      <Descriptions.Item label="建议清货量">{qty(row.evaluation.suggested_qty)}</Descriptions.Item>
      <Descriptions.Item label="补货及购物车提醒" span={3}>
        {row.evaluation.conflict_alerts?.length
          ? row.evaluation.conflict_alerts.map(alert=>alert==="INBOUND_STOCK_PRESENT"
            ? "存在在途库存" : alert==="BUYBOX_ISSUE" ? "购物车异常" : alert).join("、")
          : "无已确认提醒"}
      </Descriptions.Item>
      <Descriptions.Item label="风险依据" span={3}>{row.evaluation.risk_reasons.join("、")||"暂无自动风险依据"}</Descriptions.Item>
      {row.evaluation.warnings.length?<Descriptions.Item label="数据待核实" span={3}>
        {row.evaluation.warnings.join("、")}</Descriptions.Item>:null}
    </Descriptions>},
  ];
  const rulesFields=[
    ["high_coverage_days","高风险售罄天数"],["medium_coverage_days","中风险售罄天数"],
    ["assisted_coverage_days","辅助准入天数"],["min_stock_positive_days","30天最少有货天数"],
    ["min_listing_days","零销量保护上架天数"],["sales_drop_percent","销量下滑百分比"],
    ["ad_ratio_growth_points","广告占比上升百分点"],["margin_below_percent","低利润率阈值"],
    ["refund_rate_percent","退款率阈值"],["holding_days","建议保留销售天数"],
    ["safety_stock_units","安全库存件数"],["high_stock_capital_usd","高库存占资美元"],
  ] as const;
  const rulesSwitches=[
    ["enable_margin_signal","低利润率"],["enable_refund_signal","退款率"],
    ["enable_rating_signal","低评分"],["enable_new_listing_protection","新品保护"],
    ["enable_recovery_protection","销量恢复保护"],
  ] as const;
  return <PageShell page={page}>
    {holder}
    <div className="clearance-center">
      <div className="clearance-heading"><div><Typography.Title level={4}>WFS 清货中心</Typography.Title>
        <Typography.Text type="secondary">Listing库存积压分析 · 主动申请 · 统一审批 · 执行记录</Typography.Text>
        <div style={{fontSize:12,color:"#64748b",marginTop:5}}>
          美国太平洋时间每天 00:00 自动评估 · 分析截至上一完整销售日
        </div>
      </div></div>
      <Card size="small" className="clearance-main-card">
        <Tabs activeKey={tab} onChange={setTab} items={[
          {key:"analysis",label:`清货分析 ${listTotal}`},
          {key:"management",label:`清货管理 ${taskTotal}`},
        ]} tabBarExtraContent={<Button type="text" icon={<SettingOutlined/>}
          onClick={()=>void openRules()}>规则配置</Button>}/>
        {error?<Alert type="error" showIcon message={error} style={{marginBottom:12}}/>:null}
        {summary?.evaluation_status==="not_ready" && !error?<Alert type="warning"
          showIcon message="每日清货评估尚未生成"
          description="清货分析暂不展示未验证的风险结果；主动申请仍使用最新有效 WFS 可售库存。"
          style={{marginBottom:12}}/>:null}
        {summary?.evaluation_status==="stale" && !error?<Alert type="warning"
          showIcon message="今日美国太平洋时间的清货评估尚未成功"
          description={`上次成功评估：${summary.run_date_la||"未知"}。历史结果不会作为今日自动风险候选；主动申请仍读取实时有效 WFS 库存。`}
          style={{marginBottom:12}}/>:null}
        {summary?.evaluation_status==="ready" && !error?<Alert type="info"
          showIcon message={`最近评估：${summary.run_date_la}（美国太平洋时间）· 经营数据截至 ${summary.as_of_date_la}`}
          description={readiness?.not_evaluated_listings
            ? `有 ${readiness.not_evaluated_listings} 条 Listing 尚未纳入本次评估`
            : undefined}
          style={{marginBottom:12}}/>:null}
        <div style={{display:"grid",gridTemplateColumns:"repeat(4,minmax(0,1fr))",gap:12,marginBottom:12}}>
          {[
            {title:"高风险Listing",value:summary?.evaluation_status==="ready"?summary.high:"—"},
            {title:"中风险Listing",value:summary?.evaluation_status==="ready"?summary.medium??"—":"—"},
            {title:"观察中Listing",value:summary?.evaluation_status==="ready"?summary.observe??"—":"—"},
            {title:"待核实Listing",value:summary?.evaluation_status==="ready"?summary.review_required??"—":"—"},
          ].map(card=><Card key={card.title} size="small" style={{height:100}}>
            <Statistic title={card.title} value={card.value} valueStyle={{fontSize:23}}/>
          </Card>)}
        </div>
        <div className="clearance-toolbar" style={{display:"flex",gap:10,alignItems:"center",marginBottom:12}}>
          <Select value={sourceAccount} style={{width:150}}
            options={[{value:"",label:"全部账号"},...accountOptions]}
            onChange={v=>{setSourceAccount(v);setStore("");setTaskPage(1);}}/>
          <Select value={store} style={{width:170}} options={[{value:"",label:"全部店铺"},...stores]}
            onChange={v=>{setStore(v);setTaskPage(1);}}/>
          {tab==="analysis"?<Select value={risk} style={{width:132}} options={[
            {value:"",label:"全部风险"},...Object.entries(riskLabel).map(([value,label])=>({value,label}))]}
            onChange={v=>{setRisk(v);}}/>:null}
          <Input.Search style={{maxWidth:340,flex:1}} placeholder="搜索 Item ID / SKU / MSKU / 品名"
            value={searchDraft} onChange={e=>setSearchDraft(e.target.value)}
            onSearch={v=>{setKeyword(v.trim());}}/>
          <div style={{flex:1}}/>
          <Button type="primary" icon={<FileAddOutlined/>} onClick={()=>openApply()}>申请 SKU</Button>
          <Button icon={<ReloadOutlined/>} onClick={()=>void reload()}>刷新</Button>
        </div>
        {tab==="analysis"?<div>
          <Table<ClearanceRow> className="clearance-live-list" size="small" bordered
            rowKey={r=>r.listing.id} columns={listingColumns} dataSource={rows}
            loading={loading} scroll={{x:1580,y:460}} pagination={false}
            onScroll={event=>{
              const area=event.currentTarget;
              if (area.scrollHeight-area.scrollTop-area.clientHeight<=120) {
                void loadMoreListings();
              }
            }}/>
          <div style={{textAlign:"center",padding:"8px 0",fontSize:12,color:"#64748b"}}>
            {loadingMore?"正在加载后续 Listing…":
              rows.length<listTotal?`已加载 ${rows.length} / ${listTotal} 条，向下滚动继续加载`:
              `已加载全部 ${rows.length} 条 Listing`}
          </div>
        </div>:
          <Table<ClearanceRequest> size="small" bordered rowKey="id" columns={taskColumns}
            dataSource={tasks} loading={loading} scroll={{x:1440}}
            pagination={{current:taskPage,pageSize:50,total:taskTotal,showSizeChanger:false,
              onChange:p=>setTaskPage(p)}}/>}
      </Card>
    </div>
    <Drawer title="Listing 清货详情" width={860} open={Boolean(inspect)} onClose={()=>setInspect(null)}
      styles={{body:{overflow:"hidden"}}}
      footer={<div style={{textAlign:"center"}}>
        <Space><Button onClick={()=>setInspect(null)}>关闭</Button>
          <Button type="primary" disabled={!inspect?.evaluation.current_wfs_available||
            Number(inspect.evaluation.current_wfs_available)<=0||
            inspect.evaluation.warnings.includes("WFS_STOCK_UNAVAILABLE_OR_STALE")}
            onClick={()=>{if(inspect){openApply(inspect,"manual");setInspect(null);}}}>申请清货</Button>
        </Space></div>}>
      {inspect?<div>
        <Typography.Text strong>{inspect.listing.title||inspect.listing.item_id}</Typography.Text>
        <div style={{margin:"6px 0 14px",color:"#64748b",fontSize:12}}>
          Item ID {inspect.listing.item_id} · SKU {display(inspect.listing.local_sku)} ·
          MSKU {display(inspect.listing.msku)} · {display(inspect.listing.store_name||inspect.listing.store_id)}
        </div>
        {inspect.evaluation.daily_evaluation_status==="stale" ? <Alert
          type="warning" showIcon
          message="这条 Listing 展示的是历史评估结果"
          description="今日 LA 00:00 的评估尚未成功，历史风险不会作为今日自动候选；主动申请仍必须通过实时 WFS 库存复核。"
          style={{marginBottom:12}}
        /> : null}
        <Tabs items={detailTabs(inspect)} defaultActiveKey="analysis"/>
      </div>:null}
    </Drawer>
    <Modal title="主动申请 SKU" centered width={chooseStep===0?850:850} open={manualOpen}
      destroyOnHidden onCancel={()=>{setManualOpen(false);setChosen(null);setChooseStep(0);}}
      footer={chooseStep===0?<Space>
        <Button onClick={()=>setManualOpen(false)}>取消</Button>
        <Button type="primary" disabled={!chosen} onClick={()=>setChooseStep(1)}>下一步</Button>
      </Space>:<Space>
        <Button onClick={()=>setChooseStep(0)}>上一步</Button>
        <Button type="primary" loading={submitting} onClick={()=>form.submit()}>提交申请</Button>
      </Space>}>
      {chooseStep===0?<div>
        <Input.Search placeholder="搜索有WFS可售库存的商品" style={{marginBottom:12}}
          value={eligibleKeyword} onChange={e=>setEligibleKeyword(e.target.value)}
          onSearch={v=>void loadEligible(1,v.trim())}/>
        <Table size="small" rowKey={r=>r.listing.id} columns={eligibleColumns} dataSource={eligible}
          loading={eligibleLoading && eligible.length===0}
          pagination={false} scroll={{y:350,x:650}}
          onScroll={event=>{
            const area=event.currentTarget;
            if (area.scrollHeight-area.scrollTop-area.clientHeight<=100
                && eligibleRowsRef.current.length<eligibleTotal) {
              void loadEligible(eligibleNextPage.current,eligibleKeyword);
            }
          }}/>
        <div style={{textAlign:"center",padding:6,fontSize:12,color:"#64748b"}}>
          {eligibleLoading?"正在加载 WFS 商品…":
            eligible.length<eligibleTotal?`已加载 ${eligible.length} / ${eligibleTotal} 条，向下滚动继续加载`:
            `已加载全部 ${eligible.length} 条符合条件的商品`}
        </div>
      </div>:<div>
        <Typography.Paragraph strong>{chosen?.listing.title || "未选择Listing"}</Typography.Paragraph>
        <Typography.Text type="secondary">WFS可售：{qty(chosen?.evaluation.current_wfs_available)} ·
          SKU：{display(chosen?.listing.local_sku)} · Item ID：{display(chosen?.listing.item_id)}
        </Typography.Text>
        <Form form={form} onFinish={(v:ApplyData)=>void submit(v)} layout="vertical"
          style={{marginTop:16}} initialValues={{methods:["降价"],reason:"长期滞销"}}>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"0 16px"}}>
            <Form.Item name="reason" label="清货原因" rules={[{required:true,message:"请选择或填写原因"}]}>
              <AutoComplete options={reasons.map(value=>({value}))} placeholder="选择或自行输入清货原因"/>
            </Form.Item>
            <Form.Item name="methods" label="清货方式（可以多选）" rules={[{required:true,message:"至少选择一种方式"}]}>
              <Select mode="multiple" options={methods.map(value=>({value,label:value}))}/>
            </Form.Item>
            <Form.Item name="target_qty" label="目标清货量（所有方式共用）"
              rules={[{required:true,message:"请输入目标数量"}]}>
              <InputNumber style={{width:"100%"}} min={1}
                max={Number(chosen?.evaluation.current_wfs_available||0)} precision={0}/>
            </Form.Item>
            <Form.Item name="due_date" label="计划完成日期（选填）"><DatePicker style={{width:"100%"}}/></Form.Item>
          </div>
          <Form.Item name="remark" label="申请说明" rules={[{required:true,whitespace:true,message:"请填写申请说明"}]}>
            <Input.TextArea rows={3} style={{resize:"none"}} maxLength={4000}/>
          </Form.Item>
        </Form>
      </div>}
    </Modal>
    <Drawer title="清货任务详情" width={790} open={Boolean(selectedTask)}
      onClose={()=>setSelectedTask(null)}
      footer={selectedTask?<div style={{textAlign:"center"}}>
        <Space>
          <Button onClick={()=>setSelectedTask(null)}>关闭</Button>
          {selectedTask.request.status==="pending"?<Button
            onClick={()=>void switchTaskStatus("withdraw")}>撤回申请</Button>:null}
          {["approved","running"].includes(selectedTask.request.status)?<Button
            onClick={()=>void switchTaskStatus("pause")}>暂停记录</Button>:null}
          {selectedTask.request.status==="paused"?<Button
            onClick={()=>void switchTaskStatus("resume")}>继续记录</Button>:null}
          {["approved","running","paused"].includes(selectedTask.request.status)?<Button
            type="primary" onClick={()=>void saveProgress()}>保存执行进度</Button>:null}
        </Space></div>:null}>
      {selectedTask?<div>
        <Descriptions bordered size="small" column={2}>
          <Descriptions.Item label="审批状态"><Tag color={statusColor(selectedTask.request.status)}>
            {taskLabel[selectedTask.request.status]}</Tag></Descriptions.Item>
          <Descriptions.Item label="申请人">{selectedTask.request.requester_id}</Descriptions.Item>
          <Descriptions.Item label="Item ID">{selectedTask.request.item_id}</Descriptions.Item>
          <Descriptions.Item label="目标清货量">{qty(selectedTask.request.target_qty)}</Descriptions.Item>
          <Descriptions.Item label="清货方式" span={2}>{selectedTask.request.methods.join("、")}</Descriptions.Item>
          <Descriptions.Item label="清货原因" span={2}>{selectedTask.request.reason}</Descriptions.Item>
          <Descriptions.Item label="申请说明" span={2}>{selectedTask.request.remark}</Descriptions.Item>
        </Descriptions>
        {["approved","running","paused"].includes(selectedTask.request.status)?<div style={{marginTop:20}}>
          <Typography.Title level={5}>累计人工执行记录</Typography.Title>
          <Space style={{width:"100%"}} wrap>
            <label>已售出 <InputNumber min={selectedTask.request.sold_qty} max={selectedTask.request.target_qty}
              precision={0} value={progress.sold} onChange={v=>setProgress(p=>({...p,sold:v??0}))}/></label>
            <label>已移除 <InputNumber min={selectedTask.request.removed_qty} max={selectedTask.request.target_qty}
              precision={0} value={progress.removed} onChange={v=>setProgress(p=>({...p,removed:v??0}))}/></label>
            <label>已弃置 <InputNumber min={selectedTask.request.disposed_qty} max={selectedTask.request.target_qty}
              precision={0} value={progress.disposed} onChange={v=>setProgress(p=>({...p,disposed:v??0}))}/></label>
          </Space>
          <Typography.Paragraph type="secondary" style={{marginTop:12}}>
            完成量不能超过目标清货量。本记录不触发实际调价、广告、WFS移除或弃置。
          </Typography.Paragraph>
        </div>:null}
      </div>:null}
    </Drawer>
    <Drawer title="清货规则配置" width={610} open={rulesOpen} onClose={()=>setRulesOpen(false)}
      footer={<div style={{textAlign:"center"}}>
        <Space><Button onClick={()=>setRulesOpen(false)}>关闭</Button>
          <Button type="primary" disabled={!ruleConfig} loading={ruleSaving}
            onClick={()=>void saveRules()}>保存（下次零点生效）</Button></Space>
      </div>}>
      <Select style={{width:"100%",marginBottom:18}} placeholder="选择账号" value={ruleAccount||undefined}
        options={accountOptions} onChange={v=>void selectRuleAccount(v)}/>
      {ruleConfig?<div>
        <Typography.Text type="secondary">配置版本：{ruleConfig.version} ·
          仅使用系统已有数据库，不新增Walmart采集</Typography.Text>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"12px 18px",marginTop:18}}>
          {rulesFields.map(([key,label])=><div key={key}>
            <div style={{marginBottom:5,fontSize:12}}>{label}</div>
            <InputNumber style={{width:"100%"}} min={0} precision={key.includes("percent")||key.includes("points")?2:0}
              value={Number(ruleConfig.rules[key]||0)} onChange={value=>setRuleConfig(old=>old?{
                ...old,rules:{...old.rules,[key]:value??0}
              }:old)}/>
          </div>)}
        </div>
        <Typography.Title level={5} style={{marginTop:24}}>经营与保护开关</Typography.Title>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16}}>
          {rulesSwitches.map(([key,label])=><Space key={key}>
            <Switch checked={Boolean(ruleConfig.rules[key])} onChange={checked=>setRuleConfig(old=>old?{
              ...old,rules:{...old.rules,[key]:checked}
            }:old)}/>{label}</Space>)}
        </div>
      </div>:null}
    </Drawer>
  </PageShell>;
}

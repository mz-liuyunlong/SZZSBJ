import {usePageStateCache} from "@/shared/page-state/pageStateCache";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import type { PerformanceReportQuery } from "./NewProductPerformanceReport";
// PR337_TRACKING_EDITABLE_PENDING_V4
// PR337_TRACKING_OUTCOME_LOCK_V3
/* PR337_APPROVED_CARD_FILTER_V53 */
/* PR337_MANAGEMENT_STAT_FILTER_V51 */
// PR337_FLOW_ACCEPTANCE_20261111
import {useMemo, useState,type ReactNode, useCallback, useEffect, useRef} from "react";
import { Drawer as AntdDrawer } from "antd";
import ManagementStatCards from "@/components/report-table/ManagementStatCards";
import NewProductPerformanceReport from "./NewProductPerformanceReport";
import NewProductEvaluationReviewModal, {type ReviewReasonType} from "./NewProductEvaluationReviewModal";
import PageShell from "@/components/page/PageShell";
import type {NavigationPage} from "@/config/navigation";
import NativeBoard from "./TrackingBoardSwitch";
import dayjs from "dayjs";
import {withTrackingVisualSamples} from "./trackingBoardVisualSamples";
import type {TrackingDrillFilter} from "./trackingBoardDrilldown";
import NewProductTrackingReport from "./NewProductTrackingReport";
import {defaultConfig,bands,score,grade,suggestion,type Product,type Config} from "./nativeData";
import NewProductRulesPanel from "./NewProductRulesPanel";
import { getNewProductRules, applyNewProductRules, listNewProducts, getNewProductSummary,
  saveNewProductMarketScore, saveNewProductScoreCorrection, getNewProductPurchaseSnapshot, saveNewProductTrackingDecision, submitNewProductPurchase,
  reviewNewProductPurchase, exportNewProductListings,
  requestNewProductEvaluation,
  requestNewProductEvaluationReview,
  requestNewProductEvaluationRecheck } from "./newProductBusinessApi";
import {toPersistedProduct, type PersistedProduct} from "./newProductRealAdapter";
import { createInitialRuleDraft, cloneRuleDraft, retainFourAutomaticRisks, validateRuleDraft, validateTrackingRuleDraft, type RuleDraft } from "./NewProductRulesModel";
import TrackingRuleConfigPanel from "./components/TrackingRuleConfigPanel";
import NewProductDimensionEvidence from "./NewProductDimensionEvidence";
import NewProductManualRisk, {type ManualRiskCode} from "./NewProductManualRisk";
import NewProductEvaluationData from "./NewProductEvaluationData";
import "./nativeWorkflow.css";
import "./newProductReviewDrawer.css";
import "./newProductDimensionCards.css";
import "./newProductMarketCompetitionVisual.css";
import { Button as ReviewButton, Descriptions as ReviewDescriptions, Drawer as ReviewDrawer, Input as ReviewInput, Radio as ReviewRadio, Tag as ReviewTag } from "antd";
type Mode="performance"|"tracking";
const initialPerformanceQuery:PerformanceReportQuery = {
  page:1,pageSize:50,statuses:[],owners:[],ratings:[],
  searchField:"sku",keyword:"",phase:"all",
};
function performanceParams(q:PerformanceReportQuery) {
  const cardStatus:Record<string,string> = {
    evaluating:"测评中",market:"待市场评分",
    passed:"测评通过",failed:"测评未通过",
  };
  const selected = cardStatus[q.phase] ? [cardStatus[q.phase]] : [];
  const statuses = q.statuses.length
    ? (selected.length ? q.statuses.filter(s=>selected.includes(s)) : q.statuses)
    : selected;
  return {
    page:q.page,pageSize:q.pageSize,
    npStatuses: statuses.length===0 && selected.length>0 && q.statuses.length>0
      ? "__none__" : statuses.join(","),
    npOwners:q.owners.join(","),npRatings:q.ratings.join(","),
    keyword:q.searchField==="owner" ? "" : q.keyword,
    searchField:(q.searchField==="item"?"item_id":q.searchField==="name"?"title":"sku") as "sku"|"item_id"|"title",
    npOwnerKeyword:q.searchField==="owner" ? q.keyword : "",
  };
}
type Props={page:NavigationPage;mode:Mode;username?:string;canManage?:boolean;canConfigure?:boolean;canScore?:boolean;canRequest?:boolean;canReview?:boolean;canViewCost?:boolean};
type ModalType="detail"|"market"|"purchase"|"approval"|"resultApproval"|"review"|"config"|null | 'calculate' | 'evaluationReview' | 'recheck';
type Correction={id:number;sku:string;dimension:"speed"|"ad"|"profit"|"trust";from:number;to:number;reason:string;status:"待审核"|"已通过"|"已驳回"};
function Status({text}:{text:string}){return <span className={"badge "+(text.includes("审核")?"b-purple":text.includes("批准")||text.includes("成功")?"b-green":text.includes("失败")||text.includes("驳回")?"b-red":text.includes("待")?"b-orange":"b-blue")}>{text}</span>}
function LegacyDrawer({title,sub,close,children,footer,wide}:{title:string;sub:string;close:()=>void;children:ReactNode;footer:ReactNode;wide?:boolean}){return <div className="drawer-mask open" onMouseDown={e=>{if(e.target===e.currentTarget)close()}}><div className={"drawer "+(wide?"wide":"")} role="dialog" aria-modal="true"><div className="drawer-head"><div><h2>{title}</h2><p>{sub}</p></div><button className="close" onClick={close}>×</button></div><div className="drawer-body">{children}</div><div className="drawer-foot"><button className="btn" onClick={close}>取消</button><div className="right">{footer}</div></div></div></div>}

type AcceptanceDrawerProps = {
  title: string;
  sub: string;
  close: () => void;
  children: ReactNode;
  footer: ReactNode;
  wide?: boolean;
};

function Drawer(props: AcceptanceDrawerProps) {
  const isDetail = props.title === "新品测评详情";
  const isPurchase = props.title === "确认采购数量";
  const isConfig = props.title === "新品表现配置" || props.title === "新品分析配置" || props.title === "打品成功标准" || props.title === "打品辅助规则配置";

  if (!isDetail && !isPurchase && !isConfig) {
    return <LegacyDrawer {...props} />;
  }

  return (
    <AntdDrawer
      open
      placement="right"
      width={isConfig ? "min(900px, 96vw)" : isDetail ? "min(920px, 94vw)" : "min(840px, 94vw)"}
      rootClassName={isConfig ? "np-acceptance-drawer np-rules-topmost" : "np-acceptance-drawer"}
      zIndex={isConfig ? 10000 : 1000}
      onClose={props.close}
      title={
        <div className="np-acceptance-title">
          <strong>{props.title}</strong>
          <span>{props.sub}</span>
        </div>
      }
      footer={isConfig ? (
        <div className="np-original-v4 np-acceptance-footer">{props.footer}</div>
      ) : (
        <div className="np-original-v4 np-acceptance-footer">
          <button
            type="button"
            className="btn"
            onClick={props.close}
          >
            取消
          </button>
          <div className="np-acceptance-footer-actions">
            {props.footer}
          </div>
        </div>
      )}
    >
      <div className="np-original-v4 np-acceptance-content">
        {props.children}
      </div>
    </AntdDrawer>
  );
}

// PR337_MARKET_SCORE_FAST_V6: local input state prevents the full 365-item page rerender.
type MarketScoringDraftProps = {
  initialScore: number | null;
  initialReason: string;
  initialCompetitorIds: string[];
  initialNoCompetitors: boolean;
  saving: boolean;
  onSave: (value: number | null, reason: string, ids: string[], none: boolean) => void;
};
function MarketScoringDraft({initialScore, initialReason, initialCompetitorIds, initialNoCompetitors, saving, onSave}: MarketScoringDraftProps) {
  const [draftScore, setDraftScore] = useState<number | null>(initialScore);
  const [draftReason, setDraftReason] = useState(initialReason);
  const [draftCompetitors, setDraftCompetitors] = useState(initialCompetitorIds.join(", "));
  const [draftNone, setDraftNone] = useState(initialNoCompetitors);
  const submit = () => {
    const ids = draftNone ? [] : draftCompetitors.split(/[,\s，；;]+/).map(id => id.trim()).filter(Boolean);
    onSave(draftScore, draftReason, ids, draftNone);
  };
  return (
    <div className="np-market-v3-form">
      <div className="np-market-v3-form-row">
        <div className="np-market-v3-label">市场竞争分数 <span aria-hidden="true">*</span></div>
        <div className="np-market-v3-scale" role="group" aria-label="市场竞争分数">
          {Array.from({length: 11}, (_, i) => (
            <button type="button" key={i} disabled={saving}
              aria-pressed={draftScore === i}
              className={"market-score-btn " + (draftScore === i ? "active" : "")}
              onClick={() => setDraftScore(i)}>{i}</button>
          ))}
        </div>
      </div>
      <div className="np-market-v3-form-row np-market-v3-note-row">
        <div className="np-market-v3-label" style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
          <label htmlFor="np-market-v3-competitors">竞品 ID <span aria-hidden="true">*</span></label>
          <label style={{display:"inline-flex",alignItems:"center",gap:6,cursor:"pointer"}}>
            <input type="checkbox" checked={draftNone} disabled={saving}
              onChange={e=>setDraftNone(e.target.checked)} /> 无
          </label>
        </div>
        <div className="np-market-v3-textarea-shell">
          <textarea id="np-market-v3-competitors" className="textarea" rows={3}
            style={{resize:"none"}} disabled={saving || draftNone} value={draftCompetitors}
            aria-label="竞品 ID" aria-required={!draftNone}
            onChange={e=>{
              const value = e.target.value.replace(/[，；;]/g, ",");
              if (/^[A-Za-z0-9,\s]*$/.test(value)) setDraftCompetitors(value);
            }}
            placeholder={draftNone ? "已选择「无」，无需填写竞品 ID" : "填写竞品 ID，多个用逗号、空格或换行分隔"} />
        </div>
      </div>
      <div className="np-market-v3-form-row np-market-v3-note-row">
        <label htmlFor="np-market-v3-note" className="np-market-v3-label">市场竞争评价依据 <span aria-hidden="true">*</span></label>
        <div className="np-market-v3-textarea-shell">
          <textarea id="np-market-v3-note" className="textarea" rows={3}
            style={{resize:"none"}} disabled={saving}
            aria-label="市场竞争评价依据" value={draftReason}
            onChange={e => setDraftReason(e.target.value)}
            placeholder="填写竞品数量、价格、评价和差异化依据……" />
          <span className="np-market-v3-count">{draftReason.length} / 500</span>
        </div>
      </div>
      <div className="np-market-v3-actions">
        <button type="button" className="btn primary" disabled={saving}
          onClick={submit}>保存市场评分并计算</button>
      </div>
    </div>
  );
}

export default function NewProductPages({page,mode}:Props){
 const [items,setItems]=useState<Product[]>([]),[cfg,setCfg]=useState<Config>(defaultConfig);
 const [savedRuleDraft,setSavedRuleDraft]=useState<RuleDraft>(()=>createInitialRuleDraft(defaultConfig));
 const [ruleDraft,setRuleDraft]=useState<RuleDraft>(()=>createInitialRuleDraft(defaultConfig));
 // First visit opens analysis; store both modes in the shared page-state cache.
 // A stable cache key also works if React reuses this component across routes.
 const [boardViews,setBoardViews]=usePageStateCache<Record<Mode,"list"|"board">>(
   "new-product:board-views",{performance:"board",tracking:"board"});
 const tab=boardViews[mode]??"board";
 const setTab=(view:"list"|"board")=>setBoardViews((current)=>({...current,[mode]:view}));
 const [phase,setPhase]=useState("all"),[reportRevision,setReportRevision]=useState(0);
 const [modal,setModal]=useState<ModalType>(null),[selected,setSelected]=useState<string|null>(null),[scoreValue,setScoreValue]=useState<number|null>(null),[qty,setQty]=useState(0),[note,setNote]=useState(""),[review,setReview]=useState("继续观察");
 const [cfgTab,setCfgTab]=useState("weights"),[version,setVersion]=useState(0),[notice,setNotice]=useState("");
 const [ruleLoaded,setRuleLoaded]=useState(false);
 const [marketSaving,setMarketSaving]=useState(false);
 const [evaluationRequesting,setEvaluationRequesting]=useState<string|null>(null);
 const [evaluationReviewItem,setEvaluationReviewItem]=useState<string|null>(null);
 const [evaluationReviewSubmitting,setEvaluationReviewSubmitting]=useState(false);
  const [flowSaving,setFlowSaving]=useState(false);
  const [purchaseReviewSnapshot,setPurchaseReviewSnapshot]=useState<Awaited<ReturnType<typeof getNewProductPurchaseSnapshot>>|null>(null);
  const [purchaseReviewLoading,setPurchaseReviewLoading]=useState(false);
 // PR337_MANUAL_RISK_V1: selection stays local to risk component; ref avoids full page rerender.
 const riskSelectionRef=useRef<ManualRiskCode[]>([]);
 const queryClient=useQueryClient();
 const [remoteQuery,setRemoteQuery]=useState<PerformanceReportQuery>(initialPerformanceQuery);
 const onRemoteQueryChange=useCallback((next:PerformanceReportQuery)=>{
   setRemoteQuery(old=>JSON.stringify(old)===JSON.stringify(next)?old:next);
 },[]);
 const remoteEnabled=mode==="performance" && tab==="list";
 const summaryQuery=useQuery({
   queryKey:["np-performance","summary"],
   queryFn:({signal})=>getNewProductSummary({signal}),
   enabled:remoteEnabled,staleTime:15_000,retry:1,
 });
 const pagingQuery=useQuery({
   queryKey:["np-performance","page",remoteQuery],
   queryFn:({signal})=>listNewProducts(performanceParams(remoteQuery),{signal}),
   enabled:remoteEnabled,placeholderData:keepPreviousData,staleTime:15_000,retry:1,
 });
 const remoteProducts=useMemo(()=>(pagingQuery.data?.items??[]).map(toPersistedProduct),[pagingQuery.data]);
 const refreshAllReal=useCallback(async(isActive:()=>boolean=()=>true,progressive=false)=>{
   // Both dashboard and original ProTable consume one complete real Product[].
   // Performance shows completed pages early; final count is verified.
   const loaded:PersistedProduct[]=[];
   let pageNumber=1;
   let reportedTotal=0;
   do{
     const result=await listNewProducts({page:pageNumber,pageSize:200});
     if(pageNumber===1)reportedTotal=result.total;
     else if(result.total!==reportedTotal)throw new Error('商品列表更新中，请重新刷新');
     if(reportedTotal>5000)throw new Error('真实商品超过5000条，当前全量看板请按数据范围查询');
     loaded.push(...result.items.map(toPersistedProduct));
     if(result.items.length===0 && loaded.length<reportedTotal)throw new Error('商品分页缺失，已拒绝使用不完整列表');
     // NP_PERFORMANCE_PROGRESSIVE_PAGES_V1
     if(progressive && loaded.length<reportedTotal && isActive())setItems([...loaded]);
     pageNumber+=1;
   }while(loaded.length<reportedTotal);
   if(loaded.length!==reportedTotal)throw new Error('商品总数校验失败');
   // Ignore an obsolete fetch after navigation or effect cleanup.
   if(isActive())setItems(loaded);
   return loaded;
 },[]);
 const refreshReal=useCallback(async(isActive:()=>boolean=()=>true,progressive=false)=>{
   if(mode==="performance" && tab==="list"){
     void queryClient.invalidateQueries({queryKey:["np-performance","summary"]});
     const latest=await queryClient.fetchQuery({
       queryKey:["np-performance","page",remoteQuery],
       queryFn:({signal})=>listNewProducts(performanceParams(remoteQuery),{signal}),
       staleTime:0,
     });
     return latest.items.map(toPersistedProduct);
   }
   return refreshAllReal(isActive,progressive);
 },[mode,tab,remoteQuery,queryClient,refreshAllReal]);
 useEffect(()=>{
   if(mode==="performance" && tab==="list") return;
   let active=true;
   // Defer the initial fetch so this Effect never synchronously cascades a state update.
   // Errors are shown explicitly; do not restore the seven demo records.
   void Promise.resolve().then(()=>{
     if(!active)return;
     return refreshAllReal(()=>active,mode==="performance").catch(error=>{
       if(active){setItems([]);setNotice(`真实商品读取失败：${error instanceof Error?error.message:'未知错误'}`);}
     });
   });
   return ()=>{active=false};
 },[mode,tab,refreshAllReal]);
 const [approvalFocus,setApprovalFocus]=useState<string|null>(null);
 const [trackingDrill,setTrackingDrill]=useState<TrackingDrillFilter|null>(null);
 const [trackingSampleAnchor]=useState(()=>dayjs().format('YYYY-MM-DD'));
 // PR337_PHASE2_REAL_API_V1: hydrate the saved and applied rule; never fallback on fetch failure.
 useEffect(() => {
   if (mode !== "performance") return;
   let cancelled = false;
   getNewProductRules("performance").then(row => {
     if (cancelled) return;
     setVersion(row.version);
     setRuleLoaded(true);
     if (row.config) {
       const remote = retainFourAutomaticRisks(cloneRuleDraft(row.config as RuleDraft));
       setSavedRuleDraft(remote);
       setRuleDraft(cloneRuleDraft(remote));
       setCfg(current => ({...current,weights:{...remote.weights},remindDays:remote.remindDays,
         gradeBands:remote.gradeBands,quantities:remote.quantities,quantityStrategy:remote.quantityStrategy,
         penaltyRules:remote.penalties,vetoRules:remote.vetoes}));
     }
   }).catch((error:unknown) => {
     if (!cancelled) setNotice(`评分规则读取失败：${error instanceof Error ? error.message : "未知错误"}`);
   });
   return () => { cancelled = true; };
 }, [mode]);
 const trackingProducts=useMemo(()=>mode==='tracking'
   ?withTrackingVisualSamples(items,trackingSampleAnchor):items,[items,mode,trackingSampleAnchor]);
 const activeItems=remoteEnabled?remoteProducts:items;
 const p=activeItems.find(x=>x.id===selected);
 const reviewFinal = p?.tracking === "打品成功" || p?.tracking === "打品失败";
 // PR337 local Mock only: launch date + arrival date act as the tracking-start proxy.
 // Production must use an explicit "Listing is sellable" field instead.
 const reviewWaiting = Boolean(p &&
   (p.tracking === "等待开售" || p.tracking === "未判定") &&
   (p.backend ? !p.backend.firstWfsDate : !(p.launch?.trim() && p.arrival?.trim())));
 const reviewReadOnly = reviewFinal || reviewWaiting;
 const msg=(s:string)=>{setNotice(s);window.setTimeout(()=>setNotice(""),2600)};
 const patch=(id:string,change:Partial<Product>)=>setItems(prev=>prev.map(x=>x.id===id?{...x,...change}:x));
 const show=(kind:ModalType,id?:string)=>{
   const item=id?activeItems.find(x=>x.id===id):undefined;
   if(kind==="market"&&item?.backend&&!item.backend.firstWfsDate&&!item.launch){
     msg("WFS首次可售时间未核实，暂不能评分");return;
   }
   if(kind==="resultApproval"&&item&&!item.backend?.reviewApplication){
     msg("没有可查看的打品结果申请");return;
   }
    if(kind==="approval"&&item?.backend){
      if(!item.backend.purchaseId){msg("没有可审核的正式采购申请");return;}
      setSelected(item.id);
      setPurchaseReviewSnapshot(null);
      setPurchaseReviewLoading(true);
      setModal("approval");
      void getNewProductPurchaseSnapshot(item.backend.purchaseId).then(snapshot=>{
        setPurchaseReviewSnapshot(snapshot);
      }).catch(error=>msg(`采购评分证据读取失败：${error instanceof Error?error.message:'未知错误'}`))
        .finally(()=>setPurchaseReviewLoading(false));
      return;
    }
   if(kind==="calculate"&&item){
     if(!item.backend || item.backend.evaluation.grade!==null || !["测评中","待市场评分"].includes(item.evaluationStatus ?? "")){
       msg("仅尚未产生正式等级的测评商品允许立即计算");return;
     }
     if(evaluationRequesting===item.id)return;
     setEvaluationRequesting(item.id);
     void requestNewProductEvaluation(item.backend.identity)
       .then(result=>{
         msg(result.status==="completed" ? "当前商品自动评分已完成" :
           `已计算，证据不足：${(result.missing||[]).join("、")}`);
         return refreshReal();})
       .catch(error=>msg(`提交计算失败：${error instanceof Error?error.message:"请检查权限与数据证据"}`))
       .finally(()=>setEvaluationRequesting(null));
     return;
   }
   if(kind==="recheck"&&item){
     if(!item.backend || !item.evaluationReviewId || !item.evaluationRecheckRequired){
       msg("未找到已批准的纠错复核授权");return;
     }
     if(evaluationRequesting===item.id)return;
     setEvaluationRequesting(item.id);
     void requestNewProductEvaluationRecheck(item.evaluationReviewId)
       .then(()=>{msg("当前商品已完成纠错重新核算");return refreshReal();})
       .catch(error=>msg(`重新核算失败：${error instanceof Error?error.message:"请检查来源数据与审批权限"}`))
       .finally(()=>setEvaluationRequesting(null));
     return;
   }
   if(kind==="evaluationReview"&&item){
     if(!item.backend || item.evaluationStatus!=="测评未通过"){
       msg("仅测评未通过的真实商品可申请复核");return;
     }
     if(item.evaluationReviewStatus==="submitted"||item.evaluationReviewStatus==="info_required"){
       msg("已有进行中的复核申请");return;
     }
     setEvaluationReviewItem(item.id);return;
   }
   if(kind==="approval"&&item){
     if(!["审核中","采购审核中"].includes(item.status)){msg("仅审核中的商品可以查看申请");return}
     setModal(null);
     setSelected(null);
     setTab("list");
     setPhase("approval");
     setApprovalFocus(item.item);
     setReportRevision(n=>n+1);
     return;
   }
   if(kind==="purchase"&&item){
     if(!(item.backend ? item.evaluationStatus === "测评通过" : ["待采购确认","待采购","已驳回","采购已驳回"].includes(item.status))){
       msg("当前状态不能确认采购");return;
     }
     const finalGrade=grade(item,cfg);
     if(item.market===null||item.marketReason.trim().length<5||!finalGrade||
        finalGrade==="D"||finalGrade==="Pass"||suggestion(item,cfg)<1){
       msg("未完成有效测评或不符合采购条件，不能申请采购");return;
     }
   }
   setModal(kind==="market"?"detail":kind);
   if(item){
     setSelected(item.id);
     riskSelectionRef.current=[];
     setScoreValue(item.market);
     setQty(item.requestQty??suggestion(item,cfg));
     setNote(kind==="purchase"?(item.requestReason||""):(item.marketReason||""));
     setReview(item.tracking||"继续观察");
   }
 };
 const submitEvaluationReview=async (reasonType:ReviewReasonType,reason:string,evidence:string)=>{
   const item=activeItems.find(row=>row.id===evaluationReviewItem);
   if(!item?.backend || evaluationReviewSubmitting)return;
   setEvaluationReviewSubmitting(true);
   try{
     await requestNewProductEvaluationReview(item.backend.identity,reasonType,reason,evidence);
     setEvaluationReviewItem(null);
     await refreshReal();
     msg("测评复核申请已提交，请到审批工作台审核");
   }catch(error){
     msg(`复核申请失败：${error instanceof Error?error.message:"请检查权限及当前评级"}`);
   }finally{setEvaluationReviewSubmitting(false);}
 };
 const close=()=>{setModal(null);setNote("")};
 const reset=()=>{setPhase("all");setReportRevision(n=>n+1)};

 const openConfigPanel=()=>{
   setRuleDraft(cloneRuleDraft(savedRuleDraft));
   setModal("config");
 };
 const saveRuleConfiguration=async()=>{
   if(mode==="tracking"){
     const validation=validateTrackingRuleDraft(ruleDraft.success);
     if(validation){msg(validation);return;}
     setSavedRuleDraft(previous=>({...previous,success:{...ruleDraft.success}}));
     setCfg(current=>({...current,
       successQty:ruleDraft.success.sales30,
       successProfit:ruleDraft.success.margin,
       successAcos:ruleDraft.success.acos,
     }));
     setVersion(v=>v+1);
     close();
     msg("打品成功标准配置已保存");
     return;
   }
   if(!ruleLoaded){msg('评分规则尚未成功读取，不能保存');return;}
   const validation=validateRuleDraft(ruleDraft);
   if(validation){msg(validation);return;}
   const saved=cloneRuleDraft(ruleDraft);
   try {
     const result=await applyNewProductRules("performance",version,saved);
     setSavedRuleDraft(previous=>({...saved,success:previous.success}));
     setCfg(current=>({...current,
       weights:{...saved.weights},remindDays:saved.remindDays,gradeBands:saved.gradeBands,
       quantities:saved.quantities,quantityStrategy:saved.quantityStrategy,
       penaltyRules:saved.penalties,vetoRules:saved.vetoes,
     }));
     setVersion(result.version);
     close();
     try {await refreshReal();msg("评分规则已保存并应用");}
     catch(error){msg(`规则已生效，刷新商品失败：${error instanceof Error?error.message:'未知错误'}`);}
   }catch(error){
     msg(`保存并应用失败：${error instanceof Error?error.message:"请检查网络和权限"}`);
   }
 };
 const exportRows=()=>{
   exportNewProductListings().catch(error=>msg(`导出失败：${error instanceof Error?error.message:'未知错误'}`));
 };
 const performanceItems=useMemo(() => activeItems.map(x => x.evaluationStatus ? {...x,status:x.evaluationStatus}:x),[activeItems]);
 // Global statistics are loaded independently, never derived from a partial page.
 const saveMarket=async(chosenScore: number|null=scoreValue, chosenReason: string=note, competitorIds: string[]=p?.marketCompetitorIds??[], noCompetitors: boolean=p?.marketNoCompetitors??false)=>{
   if(!p||!p.backend){msg('仅真实商品允许保存市场评分');return;}
   if(marketSaving)return;
   if(riskSelectionRef.current.length===0){
     msg('风险条件为必填；如无风险，请主动选择「无」');return;
   }
   if(chosenScore===null||!Number.isInteger(chosenScore)||chosenScore<0||chosenScore>10||chosenReason.trim().length<5){
     msg('市场竞争分数与至少5个字符的评价依据均为必填');return;
   }
   if ((!noCompetitors && competitorIds.length === 0) || (noCompetitors && competitorIds.length > 0)) {
     msg('请填写竞品 ID，或勾选「无」');return;
   }
   setMarketSaving(true);
   try {
     await saveNewProductMarketScore(p.backend.identity,chosenScore,chosenReason.trim(),p.backend.marketVersion,riskSelectionRef.current,competitorIds,noCompetitors);
     try {
       const fresh=await refreshReal();
       const result=fresh.find(x=>x.id===p.id);
       if(result?.backend?.evaluation.grade&&result.backend.evaluation.total!==null){
         close();
         msg(['D','Pass'].includes(result.backend.evaluation.grade)
           ?`市场评分已保存，评级 ${result.backend.evaluation.grade}，当前不符合采购条件`
           :`市场评分已保存，评级 ${result.backend.evaluation.grade}，可按流程申请采购`);
       }else{
         // Preserve details: a market score is not proof of complete automatic evidence.
         msg(`市场评分已保存；${result?.backend?.evaluation.missing.join('、')||'后台评分证据尚未齐备'}，暂不生成评级`);
       }
     }catch(error){msg(`市场评分已保存，商品刷新失败：${error instanceof Error?error.message:'未知错误'}`);}
   }catch(error){
     msg(`市场评分保存失败：${error instanceof Error?error.message:'未知错误'}`);
   }finally{setMarketSaving(false)}
 };
 // SZZSBJ_LOCAL_REAL_FLOW_20261115: business writes use the existing guarded API.
 const sendPurchase=async()=>{
   if(p?.backend){
     if(flowSaving)return;
     if(p.evaluationStatus!=="测评通过"||!["S","A","B","C"].includes(p.backend.evaluation.grade??"")||p.backend.evaluation.total===null||(p.backend.suggestedQty??0)<1){
       msg('当前商品没有有效评级或采购建议，不能发起采购申请');return;
     }
     if(!Number.isInteger(qty)||qty<1){msg('请填写有效采购数量');return;}
     if(qty!==p.backend.suggestedQty&&note.trim().length<5){msg('调整数量需填写至少5字原因');return;}
     setFlowSaving(true);
     try{
       await submitNewProductPurchase(p.backend.identity,qty,note.trim(),p.backend.ruleVersion);
       await refreshReal();close();msg('正式采购申请已提交，进入审核中');
     }catch(error){msg(`采购申请失败：${error instanceof Error?error.message:'未知错误'}`);}
     finally{setFlowSaving(false);}
     return;
   }
   if(!p||!["待采购确认","待采购"].includes(p.status)){
     msg("当前状态不能提交采购申请");return;
   }
   const finalGrade=grade(p,cfg);
   if(p.market===null||p.marketReason.trim().length<5||!finalGrade||
      finalGrade==="D"||finalGrade==="Pass"||suggestion(p,cfg)<1){
     msg("请先完成有效市场评分并生成采购建议");return;
   }
   if(!Number.isInteger(qty)||qty<1){msg("请填写有效采购数量");return;}
   if(qty!==suggestion(p,cfg)&&note.trim().length<5){
     msg("调整采购数量必须填写至少5个字符的原因");return;
   }
   patch(p.id,{status:"审核中",requestQty:qty,
     requestReason:qty===suggestion(p,cfg)?"":note.trim()});
   close();
   msg("模拟采购申请已提交，正在等待审核");
 };
 const decide=async(pass:boolean)=>{
   if(p?.backend){
     if(flowSaving)return;
     if(!p.backend.purchaseId||!p.backend.purchaseVersion){msg('缺少正式采购审批单或版本号');return;}
     if(!purchaseReviewSnapshot||purchaseReviewSnapshot.id!==p.backend.purchaseId){msg("尚未加载采购申请评分快照");return;}
     if(!pass&&note.trim().length<5){msg('驳回原因至少5字');return;}
     setFlowSaving(true);
     try{
       await reviewNewProductPurchase(p.backend.purchaseId,pass?'approved':'rejected',note.trim(),p.backend.purchaseVersion);
       await refreshReal();close();msg(pass?'采购申请已审核通过':'采购申请已驳回');
     }catch(error){msg(`审批操作失败：${error instanceof Error?error.message:'未知错误'}`);}
     finally{setFlowSaving(false);}
     return;
   }
   if(!p)return;patch(p.id,{status:pass?"已批准":"已驳回",actualQty:pass?qty:p.actualQty,tracking:pass?"等待开售":p.tracking});close();msg(pass?"模拟审批通过":"模拟申请被驳回");
 };
 const saveReview=async()=>{
    if(p?.backend){
      if(flowSaving)return;
      if(reviewFinal){msg('成功或失败已锁定，不能修改');return;}
      if(!p.backend.firstWfsDate){msg('缺少真实 WFS 首次可售日期，不能判定');return;}
      if(!['继续观察','需要优化','打品成功','打品失败'].includes(review)){msg('请选择打品结果');return;}
      if(['需要优化','打品失败'].includes(review)&&note.trim().length<5){msg('请填写至少5字判定依据');return;}
      setFlowSaving(true);
      try{
        await saveNewProductTrackingDecision(p.backend.identity,review,note.trim(),p.backend.trackingVersion??0);
        await refreshReal();close();msg('正式打品判定已保存');
      }catch(error){msg(`打品判定失败：${error instanceof Error?error.message:'未知错误'}`);}
      finally{setFlowSaving(false);}
      return;
    }
    if (!p) return;

    if (p.tracking === "打品成功" ||
        p.tracking === "打品失败") {
      msg("最终打品结果已锁定，不可再次修改");
      return;
    }

    if ((p.tracking === "等待开售" || p.tracking === "未判定") &&
        !(p.launch?.trim() && p.arrival?.trim())) {
      msg("商品尚未达到开售且到货的追踪起点，不能判定打品结果");
      return;
    }

    if (!["继续观察", "需要优化",
          "打品成功", "打品失败"].includes(review)) {
      msg("请选择有效的打品结果");
      return;
    }
    if(!p)return;if(["需要优化","打品失败"].includes(review)&&note.trim().length<5){msg("请填写复盘说明");return}patch(p.id,{tracking:review,reasonFailure:note});close();msg("模拟复盘已保存")};
 // NP_OPERATOR_SCORE_CORRECTION_V1_20261119: direct operator write, not an approval.
 const correct=async(dimension:Correction["dimension"], requestedScore:number, requestedReason:string):Promise<{ok:boolean;error?:string}>=>{
   if(!p||!p.backend)return {ok:false,error:"当前商品不可修改"};
   if(!Number.isFinite(requestedScore)||requestedScore<0||requestedScore>10||requestedReason.trim().length<5){
     return {ok:false,error:"请输入0–10之间的分数及至少5字的修正依据"};
   }
   try{
     await saveNewProductScoreCorrection(p.backend.identity,dimension,requestedScore,requestedReason.trim(),p.backend.scoreCorrection?.revision??0);
     await refreshReal();
     msg("评分修正已保存，原始分数和修改记录已留存");
     return {ok:true};
   }catch(error){
     return {ok:false,error:error instanceof Error?error.message:"保存修正失败"};
   }
 };
 return <PageShell page={page}><div className="np-original-v4"><div className="content">

<header className="np-workspace-title">
  <strong>{mode==="performance"?"新品表现":"打品跟踪"}</strong>
  <span className="np-workspace-divider" aria-hidden="true"/>
  <span className="np-workspace-desc">
    {mode==="performance"
      ?"测品表现 · 自动评分 · 采购建议 · 运营确认 · 审核流转"
      :"测评通过不代表打品成功；按首批到货且 Listing 可售日期追踪经营结果"}
  </span>
</header>
<section className="np-workspace-panel">
  <div className="np-workspace-bar">
    <div className="np-native-tabs" role="tablist" aria-label="页面视图">
      <button type="button" role="tab"
        aria-selected={tab==="board"}
        className={tab==="board"?"active":""}
        onClick={()=>setTab("board")}>
        {mode==="performance"?"新品看板":"打品看板"}
      </button>
      <button type="button" role="tab"
        aria-selected={tab==="list"}
        className={tab==="list"?"active":""}
        onClick={()=>{if(mode==="tracking")setTrackingDrill(null);setTab("list");}}>
        {mode==="performance"?"新品详情":"打品详情"}
      </button>
    </div>
    <div className="np-workspace-actions">
      {tab==="list"&&
        <button className="btn" onClick={()=>{
          if(mode==="performance")reset();
          refreshReal().then(()=>msg('已刷新真实商品数据'))
            .catch(error=>msg(`刷新失败：${error instanceof Error?error.message:'未知错误'}`));
        }}>↻ 刷新</button>}

      {tab!=="board" && (<button className="btn" onClick={()=>{
        setCfgTab(mode==="performance"?"weights":"success");
        openConfigPanel();
      }}>
        ⚙ {mode==="performance"?"规则配置":"规则配置"}
      </button>)}
    </div>
  </div>

 <div className="np-workspace-body">
 {tab==="board"?<NativeBoard mode={mode} products={mode==="tracking"?trackingProducts:performanceItems} config={cfg} detail={()=>setTab("list")} onTrackingDrill={filter=>{setTrackingDrill(filter);setTab("list");}} open={(key,id)=>key==="export"?exportRows():show(key as ModalType,id)}/>:
 mode==="performance"?<>
 <ManagementStatCards ariaLabel="新品表现统计" className="np-performance-stats"
   activeKey={phase}
   cards={[
     {key:"all",title:"全部新品",subtitle:"当前全部测评商品",value:summaryQuery.data?.counts.all ?? "—",tone:"normal",icon:<span>▦</span>},
     {key:"evaluating",title:"测评中",subtitle:"等待满足正式自动测评条件",value:summaryQuery.data?.counts.evaluating ?? "—",tone:"normal",icon:<span>◷</span>},
     {key:"market",title:"待市场评分",subtitle:"自动评分完成，等待运营判断",value:summaryQuery.data?.counts.market ?? "—",tone:"normal",icon:<span>✎</span>},
     {key:"passed",title:"测评通过",subtitle:"已形成有效通过评级",value:summaryQuery.data?.counts.passed ?? "—",tone:"success",icon:<span>✓</span>},
     {key:"failed",title:"测评未通过",subtitle:"已形成有效未通过评级",value:summaryQuery.data?.counts.failed ?? "—",tone:"warning",icon:<span>▤</span>},
   ]}
   onCardClick={(key)=>{setPhase(key);setApprovalFocus(null);setReportRevision(n=>n+1);}}/>

 <NewProductPerformanceReport key={reportRevision} items={performanceItems} config={cfg} phase={phase} focusItemId={approvalFocus} calculatingItemId={evaluationRequesting} onOpen={(kind,id)=>show(kind,id)}
      remote={{loading:pagingQuery.isFetching,total:pagingQuery.data?.total??0,
        error:pagingQuery.isError?"LIST_FAILED":undefined,
        statusOptions:summaryQuery.data?.status_options??[],
        ownerOptions:summaryQuery.data?.owner_options??[],
        ratingOptions:summaryQuery.data?.rating_options??[],
        onQueryChange:onRemoteQueryChange}}
      onResetPhase={()=>{setApprovalFocus(null);setPhase("all")}}/>
 </>:<>
  <NewProductTrackingReport key={trackingDrill?JSON.stringify(trackingDrill):'manual'}
    products={trackingProducts} config={cfg} drill={trackingDrill}
    onClearDrill={()=>setTrackingDrill(null)} onReview={(id, sourceRow) => {
      const selectedRow = items.find(item => item.id === id) ?? sourceRow;
      if (!selectedRow) return;
      if (!items.some(item => item.id === id)) {
        if (!id.startsWith("PR337_PREVIEW_") && !id.startsWith("TRACK-LAYOUT-")) return;
        // Preview is local in-memory data: never calls the backend or writes to DB.
        setItems(previous => {
          const existing = new Set(previous.map(item => item.id));
          const missing = trackingProducts.filter(
            item => !existing.has(item.id)
          );
          return missing.length
            ? [...previous, ...missing]
            : previous;
        });
      }
      setSelected(id);
      setReview(selectedRow.tracking);
      setNote(selectedRow.reasonFailure || "");
      setModal("review");
    }}/>
 </>}
 </div>
</section>
{modal&&modal!=="review"&&<Drawer title={{detail:"新品测评详情",market:"市场竞争评分",purchase:"确认采购数量",approval:"新品采购审核",resultApproval:"打品结果审核申请",calculate:"立即计算",evaluationReview:"测评复核申请",recheck:"复核重新核算",review:"打品结果复盘",config:mode==="tracking"?"打品辅助规则配置":"新品表现配置"}[modal]} sub={p?p.sku+" · "+p.name:"当前规则 · 保存后立即生效"} close={close} wide={modal==="config"} footer={modal==="detail"||modal==="resultApproval"?null:modal==="market"?<button className="btn primary" onClick={() => { void saveMarket(); }}>保存市场评分</button>:modal==="purchase"?<button className="btn primary" onClick={()=>{void sendPurchase();}} disabled={flowSaving}>提交领导审核</button>:modal==="approval"?<><button className="btn" onClick={()=>{void decide(false);}} disabled={flowSaving||purchaseReviewLoading||!purchaseReviewSnapshot}>驳回</button><button className="btn primary" onClick={()=>{void decide(true);}} disabled={flowSaving||purchaseReviewLoading||!purchaseReviewSnapshot}>审核通过</button></>:mode==="tracking"?<span className="muted">请在面板右上角保存浏览器本地草稿</span>:<button className="btn primary" onClick={saveRuleConfiguration}>保存并应用</button>}>
 {p&&modal!=="config"&&(modal==="detail" ? (
   <div className="np-detail-identity-strip" aria-label="商品基础信息">
     <div className="np-detail-identity-fields">
       <span className="np-detail-identity-field"><span className="np-detail-identity-label">Item ID</span><strong>{p.item || "—"}</strong></span>
       <span className="np-detail-identity-separator" aria-hidden="true" />
       <span className="np-detail-identity-field"><span className="np-detail-identity-label">负责人</span><strong>{p.owner || "—"}</strong></span>
     </div>
     <div className="np-detail-identity-states">
       <Status text={mode==="performance" ? p.evaluationStatus ?? p.status : p.status}/>
       {grade(p,cfg) && <span className="np-detail-identity-grade">评级 {grade(p,cfg)}</span>}
     </div>
   </div>
 ) : (
   <div className="product-summary"><div className="thumb">▤</div><div><div className="summary-name">{p.name}</div><div className="summary-meta">{p.sku} · Item ID {p.item} · 负责人 {p.owner}</div><Status text={mode==="performance" ? p.evaluationStatus ?? p.status : p.status}/></div><div className="summary-right"><div className="score-main">{score(p,cfg)?.toFixed(2)||"—"}</div><div className="cell-sub">{grade(p,cfg)||"待评分"} 级</div></div></div>
 ))}
 {modal==="detail"&&p&&<><NewProductEvaluationData product={p} />
<div className="section-title">自动评分明细</div><div className="score-grid np-score-visual-grid">
  {(["speed","ad","profit","trust"] as const).map((d,i) => (
    <div className="score-item np-score-visual-card" key={d}>
      <div className="np-score-visual-header">
        <span className="np-score-visual-weight">权重 {cfg.weights[d]}%</span>
        <div className="np-score-visual-heading">
          <span className="np-score-visual-title">
            {["出单速度","广告有效性","利润空间","数据可信度"][i]}
          </span>
          <span className="np-score-visual-score">
            {p.backend && !p.backend.available[d]
              ? "—"
              : Number(p.overrides?.[d] ?? p.scores[d]).toFixed(2)}
            <span className="np-score-visual-out-of"> /10</span>
          </span>
        </div>
      </div>
      <NewProductDimensionEvidence
        product={p}
        dimension={d}
        parameters={savedRuleDraft.confirmedScoring}
        loaded={ruleLoaded}
        currentVersion={version}
        onRequestCorrection={(requestedScore, reason)=>correct(d,requestedScore,reason)}
      />
    </div>
  ))}
</div>
{/* PR337_MANUAL_RISK_V1: manually assessed, never preselected. */}
{<NewProductManualRisk key={`${p.id}:${p.backend?.marketVersion??0}`}
  disabled={marketSaving}
  systemRiskRules={savedRuleDraft.riskConditions}
  systemRiskDisplay={p.backend?.systemRiskDisplay}
  riskVersion={version}
  riskLoaded={ruleLoaded}
  onChange={names=>{riskSelectionRef.current=names;}} />}
<div className="np-market-v3">
  <div className="np-market-v3-weight">权重 {cfg.weights.market}%</div>
  <h3 className="np-market-v3-title">市场竞争评分{p.status === "待市场评分" ? "（必填）" : "（已保存）"}</h3>
  <div className="np-market-v3-rule-wrap">
    <table className="np-market-v3-rule-table" aria-label="市场竞争评分判断标准">
      <thead><tr><th>评分判断标准</th><th>评分区间</th></tr></thead>
      <tbody>
        {([
          ["竞争不大，评价少的也能卖，价格还能涨，有差异化空间", "9–10", "excellent"],
          ["有竞争，但大品牌没垄断，价格还能涨，后期靠价格、套装或规格抢销量", "7–8", "good"],
          ["竞争较强，售价上升空间小，但仍有少量切入机会", "5–6", "medium"],
          ["头部评价高，售价基本已经没有空间，同质化严重", "3–4", "low"],
          ["大品牌垄断，低价严重，低 review 新品几乎没有机会", "0–2", "poor"],
        ] as const).map(([description, range, tone]) => (
          <tr key={range}>
            <td><span className={`np-market-v3-dot np-market-v3-${tone}`} aria-hidden="true" />{description}</td>
            <td><span className={`np-market-v3-range np-market-v3-${tone}`}>{range}</span></td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
  {(p.backend || p.status === "待市场评分") ? (
    <MarketScoringDraft key={`${p.id}:${p.backend?.marketVersion??0}`} initialScore={p.market}
      initialReason={p.marketReason || ""} initialCompetitorIds={p.marketCompetitorIds || []}
      initialNoCompetitors={p.marketNoCompetitors === true} saving={marketSaving}
      onSave={(value, reason, ids, none) => { void saveMarket(value, reason, ids, none); }} />
  ) : (
    <div className="np-market-v3-saved">
      <div><strong>已保存分数：</strong>{p.market === null ? "未评分" : `${p.market} /10`}</div>
      <div><strong>竞品 ID：</strong>{p.marketNoCompetitors ? "无" : (p.marketCompetitorIds?.join(", ") || "—")}</div>
      <div><strong>评价依据：</strong>{p.marketReason || "—"}</div>
    </div>
  )}
</div>

    {p.market!==null&&p.marketReason.trim().length>=5&&score(p,cfg)!==null?(
      <>
        <div className="section-title">评分结果与采购建议</div>
        <div className="qty-hero">
          <div><div className="subline">最终得分 / 评级</div>
            <div className="big">{score(p,cfg)?.toFixed(2)}
              <span className="grade">{grade(p,cfg)}</span></div>
            <div className="delta">评级采购范围 {(cfg.quantities?.[grade(p,cfg)||"D"]??bands[grade(p,cfg)||"D"]).join("–")} 件</div>
          </div>
          <div style={{textAlign:"right"}}>
            <div className="subline">系统建议采购量</div>
            <div className="big">{suggestion(p,cfg)>0?`${suggestion(p,cfg)} 件`:"不建议采购"}</div>
            <div className="delta">{suggestion(p,cfg)>0?
              "严格限制在评级配置范围内":"当前评级不进入采购申请"}</div>
          </div>
        </div>
      </>
    ):<div className="info-box">{p.market===null
      ?"请先保存市场竞争评分。"
      :`市场评分已保存；${p.backend?.evaluation.missing.join('、')||'尚缺完整自动评分证据'}。证据核实前不生成总分、评级或采购建议。`}</div>}
    </>}
 {modal==="market"&&<><div className="section-title">市场竞争评分（0–10 分）</div><div className="market-scale">{Array.from({length:11},(_,i)=><button key={i} className={"market-score-btn "+(scoreValue===i?"active":"")} onClick={()=>setScoreValue(i)}>{i}</button>)}</div><div className="form-field"><label className="form-label">市场竞争评价依据</label><textarea className="textarea" rows={4} value={note} onChange={e=>setNote(e.target.value)} placeholder="竞品数量、售价、Review、差异化空间等"/></div></>}
 {modal==="resultApproval"&&p?.backend?.reviewApplication&&(
   <div className="kv-list" aria-label="打品结果审核申请">
     <div className="kv-row"><span className="kv-key">申请结果</span><b>{p.backend.reviewApplication.proposed_result}</b></div>
     <div className="kv-row"><span className="kv-key">申请说明</span><b>{p.backend.reviewApplication.reason || "—"}</b></div>
     <div className="kv-row"><span className="kv-key">申请时间</span><b>{p.backend.reviewApplication.created_at?.slice(0,10) || "—"}</b></div>
     <div className="kv-row"><span className="kv-key">审批状态</span><b>待审核</b></div>
   </div>
 )}
 {modal==="purchase"&&p&&<><div className="kv-list"><div className="kv-row"><span className="kv-key">系统建议采购量</span><b>{suggestion(p,cfg)} 件</b></div><div className="kv-row"><span className="kv-key">当前评级范围</span><span>{(cfg.quantities?.[grade(p,cfg)||"D"]??bands[grade(p,cfg)||"D"]).join("–")} 件</span></div></div><div className="form-field"><label className="form-label">运营申请采购数量</label><input className="input" type="number" min={1} value={qty} onChange={e=>setQty(Number(e.target.value))}/></div>{qty>(cfg.quantities?.[grade(p,cfg)||"D"]??bands[grade(p,cfg)||"D"])[1]&&<div className="warning-box">超过当前等级采购范围，需要说明原因。</div>}<div className="form-field"><label className="form-label">调整原因</label><textarea className="textarea" rows={4} value={note} onChange={e=>setNote(e.target.value)}/></div></>}
 {modal==="approval"&&p&&<>{purchaseReviewLoading?<div className="info-box">正在读取采购申请评分快照…</div>:purchaseReviewSnapshot?.score_snapshot&&<div className="kv-list">
    <div className="kv-row"><span className="kv-key">系统原始总分 / 评级</span><b>{purchaseReviewSnapshot.score_snapshot.score_correction?.system.total??purchaseReviewSnapshot.score_snapshot.evaluation.total??"—"} / {purchaseReviewSnapshot.score_snapshot.score_correction?.system.grade??purchaseReviewSnapshot.score_snapshot.evaluation.grade??"—"}</b></div>
    <div className="kv-row"><span className="kv-key">运营有效总分 / 评级</span><b>{purchaseReviewSnapshot.score_snapshot.evaluation.total??"—"} / {purchaseReviewSnapshot.score_snapshot.evaluation.grade??"—"}</b></div>
    {(purchaseReviewSnapshot.score_snapshot.score_correction?.history??[]).map(h=><div key={h.revision} className="kv-row"><span className="kv-key">{h.dimension} 修正记录 #{h.revision}</span><span className="kv-val">系统 {h.system_score} · {h.before} → {h.after}（{h.delta}） · {h.actor_id} · {h.at} · {h.reason}</span></div>)}
  </div>}<div className="kv-list">{[["系统建议",suggestion(p,cfg)+" 件"],["申请数量",(p.requestQty||qty)+" 件"],["申请原因",p.requestReason||"按建议提交"]].map(([k,v])=><div className="kv-row" key={k}><span className="kv-key">{k}</span><span className="kv-val">{v}</span></div>)}</div><div className="info-box">{p.backend?"正式采购申请：审核通过后更新批准数量；不自动生成采购订单。":"Mock 审批不会生成正式采购单或实际业务记录。"}</div></>}
 {modal==="config"&&(mode==="tracking"?<TrackingRuleConfigPanel />:<div className="np-rules-config"><div className="config-shell">
      {mode==="performance"&&<div className="card config-nav">{[["weights","评分权重"],["criteria","评分标准"],["grades","评级与采购数量"],["penalties","配置风险条件"],["version","规则版本"]].map(([key,name])=><button type="button" key={key} className={cfgTab===key?"active":""} onClick={()=>setCfgTab(key)}>{name}</button>)}</div>}
      <div className="card config-panel"><NewProductRulesPanel tab={cfgTab} draft={ruleDraft} onChange={setRuleDraft} version={version} products={items.filter(row=>!row.backend)}/></div>
    </div></div>)}
 </Drawer>}
   {/* PR337_TRACKING_REVIEW_DRAWER_V1: portal-based, above top and side navigation */}
  {modal === "review" && p && (
    <ReviewDrawer
      open
      placement="right"
      width={660}
      zIndex={9999}
      getContainer={document.body}
      rootClassName="np-tracking-review-root"
      title={
        <div className="np-review-heading">
          <strong>{reviewFinal ? "查看打品结果" : reviewWaiting ? "查看跟踪阶段" : "人工判定打品结果"}</strong>
          <span>{p.sku} · {p.name}</span>
        </div>
      }
      onClose={close}
      footer={
        <div className="np-review-footer">
          <span className="np-review-footer-note">{reviewFinal ? "成功与失败为最终判定，已锁定" : reviewWaiting ? "尚未开售，不产生打品结果" : "保存后更新当前商品的打品结果"}</span>
          <div className="np-review-footer-actions">
            <ReviewButton onClick={close}>{reviewReadOnly ? "关闭" : "取消"}</ReviewButton>
            {!reviewReadOnly && <ReviewButton type="primary" onClick={()=>{void saveReview();}} disabled={flowSaving}>保存打品结果</ReviewButton>}
          </div>
        </div>
      }
    >
      <section className="np-review-product">
        <div className="np-review-product-main">
          <strong>{p.name}</strong>
          <span>商品ID：{p.item} · SKU：{p.sku} · 负责人：{p.owner}</span>
        </div>
        <ReviewTag color={p.tracking === "打品成功" ? "green" :
          p.tracking === "打品失败" ? "red" :
          p.tracking === "需要优化" ? "orange" :
          p.tracking === "继续观察" ? "blue" : "default"}>
          {reviewWaiting ? "跟踪阶段：等待开售" :
           (p.tracking === "等待开售" || p.tracking === "未判定")
             ? "当前结果：未判定（已开售）" : `当前结果：${p.tracking}`}
        </ReviewTag>
      </section>

      <section className="np-review-card">
        <div className="np-review-section-heading">
          <h3>经营数据参考</h3><span>仅供人工判断，不自动定义结果</span>
        </div>
        <ReviewDescriptions bordered size="small" column={2} items={[
          {key:"sold", label:"30天销量", children:p.backend&&!p.backend.available.sales30?'—':`${p.sold30} 件`},
          {key:"profit", label:"利润率", children:p.backend&&!p.backend.available.margin?'—':`${p.margin}%`},
          {key:"acos", label:"ACOS", children:p.backend&&!p.backend.available.acos?'—':`${p.acos}%`},
          {key:"stock", label:"当前库存", children:p.backend&&!p.backend.available.inventory?'—':`${p.inventory} 件`},
          {key:"suggest", label:"系统建议量", children:p.backend&&p.backend.suggestedQty===null?'—':`${suggestion(p,cfg)} 件`},
          {key:"approved", label:"已有采购数量", children:p.actualQty > 0 ? `${p.actualQty} 件` : "—"},
          {key:"start", label:"追踪起点", children:p.arrival || "等待到货 / 可售", span:2},
        ]}/>
      </section>

      <section className="np-review-card np-review-decision">
        <div className="np-review-section-heading">
          <h3>打品结果 <span className="np-review-required">*</span></h3>
          <span>{reviewReadOnly ? "仅供查看" : "运营人工判定"}</span>
        </div>
        <p className="np-review-help">结合销量、利润、广告和库存表现，选择当前商品的经营结果。</p>
        <ReviewRadio.Group
          className="np-review-result-group"
          aria-label="人工选择打品结果"
          optionType="button"
          buttonStyle="solid"
          value={reviewWaiting ? undefined : review}
          disabled={reviewReadOnly}
          onChange={(event) => setReview(event.target.value)}
          options={[
            {label:"打品成功", value:"打品成功"},
            {label:"继续观察", value:"继续观察"},
            {label:"需要优化", value:"需要优化"},
            {label:"打品失败", value:"打品失败"},
          ]}
        />
        <div className="np-review-hint">
          {review === "打品成功" ? "已达成当前打品目标，可记录成功依据。" :
            review === "继续观察" ? "暂不作成功或失败判定，继续跟踪经营数据。" :
            review === "需要优化" ? "记录需要优化的具体原因和处理方向。" :
            review === "打品失败" ? "记录失败原因，便于后续复盘。" :
            "等待开售属于跟踪阶段，不是打品结果；开售后才能人工判定。"}
        </div>
      </section>

      <section className="np-review-card">
        <div className="np-review-section-heading">
          <h3>复盘说明 / 判定依据
            {(["需要优化", "打品失败"].includes(review)) &&
              <span className="np-review-required"> *</span>}
          </h3>
          <span>{["需要优化", "打品失败"].includes(review) ? "至少5个字符" : "选填"}</span>
        </div>
        <ReviewInput.TextArea
          aria-label="复盘说明与判定依据"
          value={note}
          readOnly={reviewReadOnly}
          onChange={(event) => setNote(event.target.value)}
          placeholder={review === "打品失败" ? "填写导致打品失败的经营原因" :
            review === "需要优化" ? "填写需优化的问题及后续建议" :
            "可补充判断依据、观察结论或下一步跟进情况"}
          autoSize={{ minRows: 4, maxRows: 7 }}
          style={{ resize: "none" }}
        />
      </section>
    </ReviewDrawer>
  )}

  {mode==="performance"&&evaluationReviewItem&&(()=>{
    const candidate=items.find(x=>x.id===evaluationReviewItem);
    return candidate?.backend ? <NewProductEvaluationReviewModal key={candidate.id}
      visible productName={candidate.name} itemId={candidate.item}
      submitting={evaluationReviewSubmitting}
      onClose={()=>{if(!evaluationReviewSubmitting)setEvaluationReviewItem(null);}}
      onSubmit={submitEvaluationReview}/> : null;
  })()}
  {notice&&<div className="np-native-toast">{notice}</div>}
 </div></div></PageShell>;
}

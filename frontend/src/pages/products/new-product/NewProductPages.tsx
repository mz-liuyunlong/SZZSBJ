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
import NewProductSkuProgressPage from "./NewProductSkuProgressPage";
import NewProductEvaluationReviewModal, {type ReviewReasonType} from "./NewProductEvaluationReviewModal";
import PageShell from "@/components/page/PageShell";
import type {NavigationPage} from "@/config/navigation";
import NativeBoard from "./TrackingBoardSwitch";
import type {TrackingDrillFilter} from "./trackingBoardDrilldown";
import NewProductTrackingReport from "./NewProductTrackingReport";
import {defaultConfig,bands,score,grade,suggestion,type Product,type Config} from "./newProductModel";
import NewProductRulesPanel from "./NewProductRulesPanel";
import { getNewProductRules, applyNewProductRules, listNewProducts, getNewProductSummary,
  saveNewProductMarketScore, saveNewProductManualDecision, confirmNewProductAndRequestPurchase,
  requestNewProductManualDecisionReview,
  saveNewProductScoreCorrection, confirmNewProductGrade, getNewProductPurchaseSnapshot, saveNewProductTrackingDecision, submitNewProductPurchase,
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
import { invalidateNewProductDetail, type FirstWfsDateRange } from "./newProductBusinessApi";
import { trackingReviewReasonLength, validTrackingReviewReason } from "./trackingReviewReason";
import { performanceStatusParam } from "./newProductPerformanceStages";
import "./nativeWorkflow.css";
import "./newProductAssessmentTabs.css";
import "./newProductReviewDrawer.css";
import "./newProductDimensionCards.css";
import "./newProductMarketCompetitionVisual.css";
import { Button as ReviewButton, Descriptions as ReviewDescriptions, Drawer as ReviewDrawer, Input as ReviewInput, InputNumber as ReviewInputNumber, Radio as ReviewRadio, Tag as ReviewTag, Select as ReviewSelect } from "antd";
type Mode="performance"|"tracking";
const initialPerformanceQuery:PerformanceReportQuery = {
  page:1,pageSize:50,statuses:[],owners:[],ratings:[],
  searchField:"sku",keyword:"",phase:"all",
};
function performanceParams(q:PerformanceReportQuery, firstWfsDateRange?:FirstWfsDateRange) {
  return {
    page:q.page,pageSize:q.pageSize,
    firstWfsStartDate:firstWfsDateRange?.[0],firstWfsEndDate:firstWfsDateRange?.[1],
    npStatuses:performanceStatusParam(q.phase,q.statuses),
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
  readOnly?: boolean;
  onSave: (value: number | null, reason: string, ids: string[], none: boolean) => void;
};
function MarketScoringDraft({initialScore, initialReason, initialCompetitorIds, initialNoCompetitors, saving, readOnly=false, onSave}: MarketScoringDraftProps) {
  const [draftScore, setDraftScore] = useState<number | null>(initialScore);
  const [draftReason, setDraftReason] = useState(initialReason);
  const [draftCompetitors, setDraftCompetitors] = useState(initialCompetitorIds.join(", "));
  const [draftNone, setDraftNone] = useState(initialNoCompetitors);
  const submit = () => {
    if(readOnly || saving)return;
    const ids = draftNone ? [] : draftCompetitors.split(/[,\s，；;]+/).map(id => id.trim()).filter(Boolean);
    onSave(draftScore, draftReason, ids, draftNone);
  };
  return (
    <div className={"np-market-v3-form"+(readOnly?" np-market-v3-readonly":"")}>
      <div className="np-market-v3-form-row">
        <div className="np-market-v3-label">市场竞争分数 <span aria-hidden="true">*</span></div>
        <div className="np-market-v3-scale" role="group" aria-label="市场竞争分数">
          {Array.from({length: 11}, (_, i) => (
            <button type="button" key={i} disabled={saving||readOnly}
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
            <input type="checkbox" checked={draftNone} disabled={saving||readOnly}
              onChange={e=>setDraftNone(e.target.checked)} /> 无
          </label>
        </div>
        <div className="np-market-v3-textarea-shell">
          <textarea id="np-market-v3-competitors" className="textarea" rows={3}
            style={{resize:"none"}} disabled={saving || draftNone || readOnly} value={draftCompetitors}
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
            style={{resize:"none"}} disabled={saving || readOnly}
            aria-label="市场竞争评价依据" value={draftReason}
            onChange={e => setDraftReason(e.target.value)}
            placeholder="填写竞品数量、价格、评价和差异化依据……" />
          <span className="np-market-v3-count">{draftReason.length} / 500</span>
        </div>
      </div>
      {!readOnly && <div className="np-market-v3-actions">
        <button type="button" className="btn primary" disabled={saving}
          onClick={submit}>保存市场评分并计算</button>
      </div>}
    </div>
  );
}

export default function NewProductPages({page,mode}:Props){
 const [items,setItems]=useState<Product[]>([]),[cfg,setCfg]=useState<Config>(defaultConfig);
 const [savedRuleDraft,setSavedRuleDraft]=useState<RuleDraft>(()=>createInitialRuleDraft(defaultConfig));
 const [ruleDraft,setRuleDraft]=useState<RuleDraft>(()=>createInitialRuleDraft(defaultConfig));
 // First visit opens analysis; store both modes in the shared page-state cache.
 // A stable cache key also works if React reuses this component across routes.
 const [boardViews,setBoardViews]=usePageStateCache<Record<Mode,"list"|"board"|"sku-progress">>(
   "new-product:board-views",{performance:"board",tracking:"board"});
 const savedTab=boardViews[mode]??"board";
 const skuPreviewEnabled=import.meta.env.DEV && mode==="performance";
 const tab=savedTab==="sku-progress"&&!skuPreviewEnabled?"board":savedTab;
 const setTab=(view:"list"|"board"|"sku-progress")=>setBoardViews((current)=>({...current,[mode]:view}));
 const [phase,setPhase]=useState("all"),[reportRevision,setReportRevision]=useState(0);
 const [modal,setModal]=useState<ModalType>(null),[selected,setSelected]=useState<string|null>(null),[scoreValue,setScoreValue]=useState<number|null>(null),[qty,setQty]=useState(0),[note,setNote]=useState(""),[review,setReview]=useState("继续观察");
 const [cfgTab,setCfgTab]=useState("weights"),[version,setVersion]=useState(0),[notice,setNotice]=useState("");
 const [ruleLoaded,setRuleLoaded]=useState(false);
 const [marketSaving,setMarketSaving]=useState(false);
 const [detailSection,setDetailSection]=useState<"details"|"assessment">("details");
 const [assessmentChoice,setAssessmentChoice]=useState<""|"passed"|"failed">("");
 const [assessmentReason,setAssessmentReason]=useState("");
 const [assessmentSaving,setAssessmentSaving]=useState(false);
 const [gradeConfirmSaving,setGradeConfirmSaving]=useState(false);
 const [gradePreview,setGradePreview]=useState(false);
 const [gradePreviewSaving,setGradePreviewSaving]=useState(false);
 const [assessmentQty,setAssessmentQty]=useState("");
 const [assessmentPurchaseReason,setAssessmentPurchaseReason]=useState("");
 const [,setAssessmentReviewOpen]=useState(false);
 const [assessmentReviewChoice]=useState<"passed"|"failed">("passed");
 const [assessmentReviewReason,setAssessmentReviewReason]=useState("");
 const [detailSnapshot,setDetailSnapshot]=useState<Product|null>(null);
 const [evaluationRequesting,setEvaluationRequesting]=useState<string|null>(null);
 const [evaluationReviewItem,setEvaluationReviewItem]=useState<Product|null>(null);
 const [evaluationReviewSubmitting,setEvaluationReviewSubmitting]=useState(false);
  const [flowSaving,setFlowSaving]=useState(false);
  const [purchaseReviewSnapshot,setPurchaseReviewSnapshot]=useState<Awaited<ReturnType<typeof getNewProductPurchaseSnapshot>>|null>(null);
  const [purchaseReviewLoading,setPurchaseReviewLoading]=useState(false);
 // PR337_MANUAL_RISK_V1: selection stays local to risk component; ref avoids full page rerender.
 const riskSelectionRef=useRef<ManualRiskCode[]>([]);
 const queryClient=useQueryClient();
 const [remoteQuery,setRemoteQuery]=useState<PerformanceReportQuery>(initialPerformanceQuery);
 // NP_FIRST_WFS_DATE_FILTER_V1: parent-owned range survives the keyed report remount on card selection.
 const [firstWfsDateRange,setFirstWfsDateRange]=useState<FirstWfsDateRange>();
 const onFirstWfsDateRangeChange=useCallback((range:FirstWfsDateRange|undefined)=>{
   setFirstWfsDateRange(old=>old?.[0]===range?.[0] && old?.[1]===range?.[1]?old:range);
   setRemoteQuery(old=>old.page===1?old:{...old,page:1});
 },[]);
 const onRemoteQueryChange=useCallback((next:PerformanceReportQuery)=>{
   setRemoteQuery(old=>JSON.stringify(old)===JSON.stringify(next)?old:next);
 },[]);
 // Let React's development-only effect replay settle before starting page reads.
 // Real navigation/filter changes still use AbortSignal and normal query cancellation.
 const [pageReadsReady,setPageReadsReady]=useState(false);
 useEffect(()=>{
   let active=true;
   queueMicrotask(()=>{if(active)setPageReadsReady(true);});
   return ()=>{active=false;};
 },[]);
 const remoteEnabled=mode==="performance" && tab==="list";
 const remoteParams=useMemo(()=>performanceParams(remoteQuery,firstWfsDateRange),[remoteQuery,firstWfsDateRange]);
 const summaryQuery=useQuery({
   queryKey:["np-performance","summary",firstWfsDateRange],
   queryFn:({signal})=>getNewProductSummary({signal},firstWfsDateRange),
   enabled:remoteEnabled && pageReadsReady,staleTime:15_000,retry:1,
 });
 const pagingQuery=useQuery({
   queryKey:["np-performance","page",remoteParams],
   queryFn:({signal})=>listNewProducts(remoteParams,{signal}),
   enabled:remoteEnabled && pageReadsReady,placeholderData:keepPreviousData,staleTime:15_000,retry:1,
 });
 const remoteProducts=useMemo(()=>(pagingQuery.data?.items??[]).map(toPersistedProduct),[pagingQuery.data]);
 const [boardActionItem,setBoardActionItem]=useState<PersistedProduct|null>(null);
 const refreshReal=useCallback(async()=>{
   // NP_DETAIL_CACHE_V4_REFRESH_GUARD: invalidate only on explicit refresh/mutation.
   void invalidateNewProductDetail();
   if(mode==="performance" && tab==="list"){
     void queryClient.invalidateQueries({queryKey:["np-performance","summary"]});
     const latest=await queryClient.fetchQuery({
       queryKey:["np-performance","page",remoteParams],
       queryFn:({signal})=>listNewProducts(remoteParams,{signal}),
       staleTime:0,
     });
     return latest.items.map(toPersistedProduct);
   }
   if(mode==="performance" && tab==="board"){
     void queryClient.invalidateQueries({queryKey:["np-board"]});
     if(!boardActionItem)return [];
     const listing=await listNewProducts({page:1,pageSize:200,keyword:boardActionItem.item,searchField:"item_id"});
     const found=listing.items.map(toPersistedProduct).find(p=>p.id===boardActionItem.id);
     if(!found)throw new Error("看板商品刷新未找到完整身份");
     setBoardActionItem(found);
     return [found];
   }
   await queryClient.invalidateQueries({queryKey:["np-tracking"]});
  return [];
 },[mode,tab,remoteParams,queryClient,boardActionItem]);
 const freshScoreProduct=async(item:Product):Promise<PersistedProduct>=>{
    if(!item.backend)throw new Error("Product identity is missing");
    const identity=item.backend.identity;
    const page=await listNewProducts({
      page:1,pageSize:200,keyword:identity.item_id,searchField:"item_id"
    });
    const current=page.items.map(toPersistedProduct).find(row=>
      row.backend.identity.source_account_ref===identity.source_account_ref &&
      row.backend.identity.store_id===identity.store_id &&
      row.backend.identity.item_id===identity.item_id);
    if(!current)throw new Error("Current product is not in the verified listing response");
    setDetailSnapshot(current);
    return current;
  };
 const [approvalFocus,setApprovalFocus]=useState<string|null>(null);
 const [trackingDrill,setTrackingDrill]=useState<TrackingDrillFilter|null>(null);
 // PR337_PHASE2_REAL_API_V1: hydrate the saved and applied rule; never fallback on fetch failure.
 useEffect(() => {
   if (mode !== "performance") return;
   let cancelled = false;
   // Defer until the effect is still live; do not issue an abandoned mount's GET.
   queueMicrotask(()=>{
   if(cancelled)return;
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
   });
   return () => { cancelled = true; };
 }, [mode]);
 const trackingProducts=items;
 const activeItems=remoteEnabled?remoteProducts:(mode==="performance" && tab==="board" ? (boardActionItem?[boardActionItem]:[]):items);
 const p=detailSnapshot?.id===selected ? detailSnapshot : activeItems.find(x=>x.id===selected);
 const reviewFinal = p?.tracking === "打品成功" || p?.tracking === "打品失败";
 // PR337 local Mock only: launch date + arrival date act as the tracking-start proxy.
 // Production must use an explicit "Listing is sellable" field instead.
 const reviewWaiting = Boolean(p &&
   (p.tracking === "等待开售" || p.tracking === "未判定") &&
   (p.backend ? !p.backend.firstWfsDate : !(p.launch?.trim() && p.arrival?.trim())));
 const reviewReadOnly = reviewFinal || reviewWaiting;
 const msg=(s:string)=>{setNotice(s);window.setTimeout(()=>setNotice(""),2600)};
 const patch=(id:string,change:Partial<Product>)=>setItems(prev=>prev.map(x=>x.id===id?{...x,...change}:x));
 const show=(kind:ModalType|"assessment",id?:string)=>{
   const item=id?activeItems.find(x=>x.id===id):undefined;
   setGradePreview(Boolean(
     item?.backend?.gradeConfirmation?.status==="pending" &&
     item.market!==null &&
     item.backend.evaluation.total!==null &&
     item.backend.evaluation.grade!==null
   ));
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
       .then(result=>{msg(result.next_status==="待等级确认"?"纠错重新核算已完成，请在待确认中重新确认等级":"当前商品已完成纠错重新核算");return refreshReal();})
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
     setEvaluationReviewItem(item);return;
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
     setSelected(item.id);
     setDetailSnapshot(item);
     setDetailSection("assessment");
     setAssessmentQty(String(item.backend?.suggestedQty ?? ""));
     setAssessmentPurchaseReason("");
     setModal("detail");
     return;
   }
   setDetailSection(kind==="assessment"?"assessment":"details");
   setModal(kind==="market"||kind==="assessment"?"detail":kind);
   if(item){
     setSelected(item.id);
      setDetailSnapshot(item);
     riskSelectionRef.current=[];
     setAssessmentChoice("");
     setAssessmentReason("");
     setAssessmentQty(String(item.backend?.suggestedQty ?? ""));
     setAssessmentPurchaseReason("");
     setScoreValue(item.market);
     setQty(item.requestQty??suggestion(item,cfg));
     setNote(item.marketReason||"");
     setReview(item.tracking||"继续观察");
   }
 };
 const submitEvaluationReview=async (reasonType:ReviewReasonType,reason:string,evidence:string)=>{
   const item=evaluationReviewItem;
   if(!item?.backend || evaluationReviewSubmitting)return;
   setEvaluationReviewSubmitting(true);
   try{
     if(reasonType==="manual_decision_change") {
       await requestNewProductManualDecisionReview(item.backend.identity,"passed",reason,evidence);
     } else {
       await requestNewProductEvaluationReview(item.backend.identity,reasonType,reason,evidence);
     }
     setEvaluationReviewItem(null);
     await refreshReal();
     msg("测评复核申请已提交，请到审批工作台审核");
   }catch(error){
     msg(`复核申请失败：${error instanceof Error?error.message:"请检查权限及当前评级"}`);
   }finally{setEvaluationReviewSubmitting(false);}
 };
 const close=()=>{setModal(null);setDetailSnapshot(null);setDetailSection("details");setGradePreview(false);setNote("")};
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
 const requestManualDecisionChange=async()=>{
   if(!p?.backend || !p.backend.evaluationDecision || assessmentSaving)return;
   if(assessmentReviewChoice===p.backend.evaluationDecision.decision ||
     Array.from(assessmentReviewReason.replace(/\s/g,"")).length<20){
     msg("请选择不同的结论，填写至少20字变更原因");return;
   }
   setAssessmentSaving(true);
   try{
     await requestNewProductManualDecisionReview(
       p.backend.identity,assessmentReviewChoice,assessmentReviewReason.trim());
     setAssessmentReviewOpen(false);setAssessmentReviewReason("");
     await refreshReal();msg("人工测评结论变更已提交审批，请等待复核");
   }catch(error){msg(`复核申请失败：${error instanceof Error?error.message:"未知错误"}`);}
   finally{setAssessmentSaving(false)}
 };
 void requestManualDecisionChange;
 const confirmManualAssessment=async(goPurchase=false)=>{
   if(!p?.backend || assessmentSaving)return;
   if(p.backend.gradeConfirmation?.status==="pending"){
     msg("请先确认等级，再确认测评结论");return;
   }
   if(assessmentChoice==="passed" && ["D","Pass"].includes(p.backend.evaluation.grade??"") && !p.evaluationManualException){
     msg("D/Pass 等级不能正常测评通过");return;
   }
   if(!assessmentChoice || Array.from(assessmentReason.replace(/\s/g,"")).length<20){
     msg("请选择测评结论并填写不少于20字的原因");return;
   }
   if(goPurchase){
     const requested=Number(assessmentQty);
     if(assessmentChoice!=="passed" || !/^[1-9]\d*$/.test(assessmentQty) ||
       !Number.isSafeInteger(requested) || requested>100000){
       msg("请填写1–100000之间的有效采购数量");return;
     }
     const systemQty=p.backend.suggestedQty;
     if(systemQty===null || systemQty===undefined){
       msg("系统建议采购数量尚未核实，不能合并发起采购");return;
     }
     if(requested!==systemQty &&
       Array.from(assessmentPurchaseReason.replace(/\s/g,"")).length<10){
       msg("采购数量不同于系统建议时，调整原因至少10个字符");return;
     }
   }
   setAssessmentSaving(true);
   try{
     if(goPurchase){
       await confirmNewProductAndRequestPurchase(
         p.backend.identity,assessmentReason.trim(),Number(assessmentQty),
         assessmentPurchaseReason.trim(),p.backend.ruleVersion);
     }else{
       await saveNewProductManualDecision(
         p.backend.identity,assessmentChoice,assessmentReason.trim());
     }
     const fresh=await listNewProducts({page:1,pageSize:200,keyword:p.item,searchField:"item_id"});
     const updated=fresh.items.map(toPersistedProduct).find(row=>row.id===p.id);
     if(updated)setDetailSnapshot(updated);
     await refreshReal();
     if(goPurchase){
       close();
       msg("人工测评通过且采购申请已提交，进入领导审核");
     }else{
       msg("人工测评结论已确认并锁定");
     }
   }catch(error){msg(`人工确认失败：${error instanceof Error?error.message:"未知错误"}`);}
   finally{setAssessmentSaving(false)}
 };
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
       let result=fresh.find(x=>x.id===p.id);
       if(!result){
         const direct=await listNewProducts({
           page:1,pageSize:200,keyword:p.item,searchField:"item_id"
         });
         result=direct.items.map(toPersistedProduct).find(x=>x.id===p.id);
       }
       if(!result)throw new Error("保存后未找到当前商品");
       setDetailSnapshot(result);
       if(result.backend?.evaluation.grade&&result.backend.evaluation.total!==null){
         const pending = result.backend.gradeConfirmation?.status === "pending";
         setGradePreview(Boolean(
           pending &&
           result.backend.evaluation.total!==null &&
           result.backend.evaluation.grade!==null
         ));
         if (pending && tab === "list") {
           setPhase("all");
           setReportRevision(current => current + 1);
         }
         setDetailSection(pending ? "details" : "assessment");
         msg(pending
           ? `市场评分已保存，计算等级 ${result.backend.evaluation.grade}；可继续修正分数，完成后点击计算等级`
           : `市场评分已保存，评级 ${result.backend.evaluation.grade}；请人工确认测评结论`);
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

 const submitConfirmedPurchase=async()=>{
   if(!p?.backend || p.backend.evaluationDecision?.decision!=="passed"){
     msg("请先确认测评通过");return;
   }
   if(flowSaving)return;
   if(["submitted","approved"].includes(p.backend.purchaseStatus??"")){
     msg("已有采购申请，请勿重复提交");return;
   }
   const requested=Number(assessmentQty);
   if(!/^[1-9]\d*$/.test(assessmentQty)||requested>100000){
     msg("请输入1至100000之间的整数采购数量");return;
   }
   const reason=assessmentPurchaseReason.trim();
   if(requested!==p.backend.suggestedQty &&
      Array.from(reason.replace(/\s/g,"")).length<10){
     msg("采购数量不同于系统建议时，请填写至少10个非空白字符的调整原因");
     return;
   }
   setFlowSaving(true);
   try{
     await submitNewProductPurchase(
       p.backend.identity,requested,reason,p.backend.ruleVersion
     );
     const fresh=await refreshReal();
     const updated=fresh.find(x=>x.id===p.id);
     if(updated?.backend){
       setDetailSnapshot(updated);
     }else{
       setDetailSnapshot({
         ...p,
         backend:{...p.backend,purchaseStatus:"submitted"}
       });
     }
     msg("采购申请已提交，等待领导审批");
   }catch(error){
     msg(`采购申请失败：${error instanceof Error?error.message:"未知错误"}`);
   }finally{
     setFlowSaving(false);
   }
 };
 void submitConfirmedPurchase;
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
 // TRACKING_INLINE_PURCHASE_V3
 const saveReview=async(review:string,note:string)=>{
    if(p?.backend){
      if(flowSaving)return;
      if(reviewFinal){msg('成功或失败已锁定，不能修改');return;}
      if(!p.backend.firstWfsDate){msg('缺少真实 WFS 首次可售日期，不能判定');return;}
      if(!['继续观察','需要优化','打品成功','打品失败'].includes(review)){msg('请选择打品结果');return;}
      if(!validTrackingReviewReason(note)){msg('复盘说明 / 判定依据至少填写10个字');return;}
      setFlowSaving(true);
      try{
        const saved=await saveNewProductTrackingDecision(
          p.backend.identity,review,note.trim(),
          p.backend.trackingVersion??0
        );
        if(review==="打品成功"){
          setDetailSnapshot({
            ...p,
            tracking:"打品成功",
            reasonFailure:note.trim(),
            backend:{
              ...p.backend,
              trackingVersion:saved.version
            }
          });
          msg("打品结果已保存，请填写采购数量及备注");
          try{
            await refreshReal();
          }catch{
            msg("打品结果已保存，列表刷新失败");
          }
        }else{
          await refreshReal();
          close();
          msg("正式打品判定已保存");
        }
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
    if(!validTrackingReviewReason(note)){msg("复盘说明 / 判定依据至少填写10个字");return;}
    patch(p.id,{tracking:review,reasonFailure:note.trim()});close();msg("模拟复盘已保存")};
 const calculateGrade=async()=>{
   if(!p?.backend || p.backend.gradeConfirmation?.status!=="pending" ||
     gradePreviewSaving || gradeConfirmSaving)return;
   setGradePreviewSaving(true);
   try{
     const fresh=await listNewProducts({
       page:1,pageSize:200,keyword:p.item,searchField:"item_id"
     });
     const updated=fresh.items.map(toPersistedProduct)
       .find(row=>row.id===p.id);
     if(!updated?.backend || updated.backend.gradeConfirmation?.status!=="pending"){
       throw new Error("商品不再处于待等级确认状态");
     }
     if(updated.backend.scoreCorrectionRevision===null ||
       updated.backend.scoreCorrectionState==="stale"){
       throw new Error("修正分数快照已失效，请核对后再计算等级");
     }
     if(updated.backend.evaluation.total===null ||
       updated.backend.evaluation.grade===null){
       throw new Error("尚无完整的已保存评分结果");
     }
     await refreshReal();
     setDetailSnapshot(updated);
     setGradePreview(true);
   }catch(error){
     msg(`计算等级失败：${error instanceof Error?error.message:"未知错误"}`);
   }finally{setGradePreviewSaving(false);}
 };
 const confirmGrade=async()=>{
   if(!p?.backend || p.backend.gradeConfirmation?.status!=="pending" ||
     !gradePreview || gradeConfirmSaving || gradePreviewSaving)return;
   const identity=p.backend.identity;
   setGradeConfirmSaving(true);
   try{
     const current=await freshScoreProduct(p);
     const expected=current.backend.scoreCorrectionRevision;
     if(current.backend.gradeConfirmation?.status!=="pending" ||
       expected===null || current.backend.scoreCorrectionState==="stale"){
       throw new Error("评分快照未核实，请刷新后再确认");
     }
     await confirmNewProductGrade(identity,expected);
     const updated=await freshScoreProduct(current);
     if(!updated || updated.backend.gradeConfirmation?.status!=="confirmed"){
       msg("等级已确认，请刷新核对最新数据");return;
     }
     setGradePreview(false);
     setDetailSnapshot(updated);
     await refreshReal();
     setDetailSection("assessment");
     msg("等级已确认并锁定，可以继续人工测评");
   }catch(error){
     msg(`等级确认失败：${error instanceof Error?error.message:"未知错误"}`);
   }finally{setGradeConfirmSaving(false);}
 };
 // NP_OPERATOR_SCORE_CORRECTION_V1_20261119: direct operator write, not an approval.
 const correct=async(dimension:Correction["dimension"], requestedScore:number, requestedReason:string):Promise<{ok:boolean;error?:string}>=>{
   if(!p||!p.backend)return {ok:false,error:"当前商品不可修改"};
   if(p.backend.evaluation.grade !== null && p.backend.evaluation.total !== null &&
     p.backend.gradeConfirmation?.status!=="pending")
     return {ok:false,error:"等级已确认或属于历史评分，不允许直接修改"};
   if(!Number.isFinite(requestedScore)||requestedScore<0||requestedScore>10||requestedReason.trim().length<5){
     return {ok:false,error:"请输入0–10之间的分数及至少5字的修正依据"};
   }
   try{
     const current=await freshScoreProduct(p);
     const expected=current.backend.scoreCorrectionRevision;
     if(expected===null || current.backend.scoreCorrectionState==="stale"){
       return {ok:false,error:"评分修正快照未核实，已阻止覆盖正式数据"};
     }
     if(current.backend.gradeConfirmation?.status!==p.backend.gradeConfirmation?.status){
       return {ok:false,error:"商品等级状态已变化，请刷新核对"};
     }
     const saved=await saveNewProductScoreCorrection(
       current.backend.identity,dimension,requestedScore,
       requestedReason.trim(),expected
     );
     const updated=await freshScoreProduct(current);
     await refreshReal();
     if(updated.backend.scoreCorrectionRevision!==saved.revision ||
       updated.backend.scoreCorrectionState!=="applied"){
       return {ok:false,error:"修正已保存，但有效分数尚未核实，请刷新核对"};
     }
     setDetailSnapshot(updated);
     msg("评分修正已保存，原始分数和修改记录已留存");
     return {ok:true};
   }catch(error){
     return {ok:false,error:error instanceof Error?error.message:"保存修正失败"};
   }
 };
 const openBoardMarket=async(id:string)=>{
   try{
     const parts=id.split("::");
     if(parts.length!==3 || !parts.every(Boolean))throw new Error("商品身份无效");
     const result=await listNewProducts({page:1,pageSize:200,keyword:parts[2],searchField:"item_id"});
     const found=result.items.map(toPersistedProduct).find(item=>item.id===id);
     if(!found || !found.backend)throw new Error("未找到对应账号与店铺的真实商品");
     setBoardActionItem(found);
     setSelected(found.id);
     riskSelectionRef.current=[];
     setScoreValue(found.market);
     setQty(found.requestQty??suggestion(found,cfg));
     setNote(found.marketReason||"");
     setModal("detail");
   }catch(error){msg(`读取待评分商品失败：${error instanceof Error?error.message:"未知错误"}`);}
 };
 const gradeSummary=p?(<>
        <div className="section-title np-assessment-result-heading"><span aria-hidden="true"><svg viewBox="0 0 24 24" width="31" height="31" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="4" width="16" height="18" rx="2"/><rect x="9" y="2" width="6" height="4" rx="1" fill="currentColor" stroke="none"/><path d="m8 14 3 3 5-6"/></svg></span>评分结果与采购建议</div>
        <div className="qty-hero np-assessment-hero">
          <div><span className="np-assessment-hero-icon" aria-hidden="true"><svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m12 2 3.1 6.5 7.1 1-5.1 5 .9 7.1-6-3.3-6 3.3.9-7.1-5.1-5 7.1-1L12 2Z"/></svg></span><div className="subline">最终得分 / 评级</div>
            <div className="big">{score(p,cfg)?.toFixed(2)}
              <span className="grade">{grade(p,cfg)}</span></div>
            <div className="delta">评级采购范围 {(cfg.quantities?.[grade(p,cfg)||"D"]??bands[grade(p,cfg)||"D"]).join("–")} 件</div>
          </div>
          <div style={{textAlign:"right"}}>
            <span className="np-assessment-hero-icon" aria-hidden="true"><svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m12 2 9 5v10l-9 5-9-5V7l9-5Z"/><path d="m3 7 9 5 9-5M12 12v10"/></svg></span><div className="subline">系统建议采购量</div>
            <div className="big">{suggestion(p,cfg)>0?`${suggestion(p,cfg)} 件`:"不建议采购"}</div>
            <div className="delta">{suggestion(p,cfg)>0?
              "严格限制在评级配置范围内":"当前评级不进入采购申请"}</div>
          </div>
        </div>
 </>):null;
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
      {skuPreviewEnabled&&<button type="button" role="tab" aria-selected={tab==="sku-progress"} className={tab==="sku-progress"?"active":""} onClick={()=>setTab("sku-progress")}>SKU进度</button>}
    </div>
    <div className="np-workspace-actions">
      {tab==="list"&&
        <button className="btn" onClick={()=>{
          if(mode==="performance")reset();
          refreshReal().then(()=>msg('已刷新真实商品数据'))
            .catch(error=>msg(`刷新失败：${error instanceof Error?error.message:'未知错误'}`));
        }}>↻ 刷新</button>}

      {tab==="list" && (<button className="btn" onClick={()=>{
        setCfgTab(mode==="performance"?"weights":"success");
        openConfigPanel();
      }}>
        ⚙ {mode==="performance"?"规则配置":"规则配置"}
      </button>)}
    </div>
  </div>

 <div className="np-workspace-body">
 {tab==="sku-progress"?<NewProductSkuProgressPage/>:tab==="board"?<NativeBoard mode={mode} products={mode==="tracking"?trackingProducts:performanceItems} config={cfg} detail={()=>setTab("list")} onTrackingDrill={filter=>{setTrackingDrill(filter);setTab("list");}} open={(key,id)=>key==="export"?exportRows():(mode==="performance"&&key==="market"&&id?void openBoardMarket(id):show(key as ModalType,id))}/>:
 mode==="performance"?<>
 <ManagementStatCards ariaLabel="新品表现统计" className="np-performance-stats"
   activeKey={phase}
   cards={[
     {key:"all",title:"全部新品",subtitle:"全部新品（含待到货）",value:summaryQuery.data?.stage_counts?.all ?? "—",tone:"normal",icon:<span>▦</span>},
     {key:"evaluating",title:"测评中",subtitle:"已首次可售，正在测评",value:summaryQuery.data?.stage_counts?.evaluating ?? "—",tone:"normal",icon:<span>◷</span>},
     {key:"pending",title:"待确认",subtitle:"市场评分、等级及测评确认",value:summaryQuery.data?.stage_counts?.pending ?? "—",tone:"normal",icon:<span>◉</span>},
     {key:"passed",title:"测评通过",subtitle:"含采购审批各阶段",value:summaryQuery.data?.stage_counts?.passed ?? "—",tone:"success",icon:<span>✓</span>},
     {key:"failed",title:"测评未通过",subtitle:"含测评复核各阶段",value:summaryQuery.data?.stage_counts?.failed ?? "—",tone:"warning",icon:<span>▤</span>},
   ]}
   onCardClick={(key)=>{
     setPhase(key);setApprovalFocus(null);
     setRemoteQuery(old=>({...old,phase:key,statuses:[],page:1}));
     setReportRevision(n=>n+1);
   }}/>

 <NewProductPerformanceReport key={reportRevision} items={performanceItems} config={cfg} phase={phase} focusItemId={approvalFocus} calculatingItemId={evaluationRequesting} onOpen={(kind,id)=>show(kind,id)}
      remote={{loading:pagingQuery.isFetching,total:pagingQuery.data?.total??0,
        error:pagingQuery.isError?"LIST_FAILED":undefined,
        statusOptions:summaryQuery.data?.flow_status_options??[],
        initialQuery:remoteQuery,
        ownerOptions:summaryQuery.data?.owner_options??[],
        ratingOptions:summaryQuery.data?.rating_options??[],
        firstWfsDateRange,onFirstWfsDateRangeChange,
        onQueryChange:onRemoteQueryChange}}
      onResetPhase={()=>{setApprovalFocus(null);setPhase("all");setRemoteQuery(initialPerformanceQuery)}}/>
 </>:<>
  <NewProductTrackingReport key={trackingDrill?JSON.stringify(trackingDrill):'manual'}
    products={trackingProducts} config={cfg} drill={trackingDrill}
    onClearDrill={()=>setTrackingDrill(null)} onReview={(id, sourceRow) => {
      const selectedRow = items.find(item => item.id === id) ?? sourceRow;
      if (!selectedRow) return;
      setSelected(id);
      setDetailSnapshot(selectedRow);
      setReview(selectedRow.tracking);
      setNote(selectedRow.reasonFailure || "");
      setModal("review");
    }}/>
 </>}
 </div>
</section>
{modal&&modal!=="review"&&<Drawer title={{detail:"新品测评详情",market:"市场竞争评分",purchase:"确认采购数量",approval:"新品采购审核",resultApproval:"打品结果审核申请",calculate:"立即计算",evaluationReview:"测评复核申请",recheck:"复核重新核算",review:"打品结果复盘",config:mode==="tracking"?"打品辅助规则配置":"新品表现配置"}[modal]} sub={p?p.sku+" · "+p.name:"当前规则 · 保存后立即生效"} close={close} wide={modal==="config"} footer={modal==="detail"||modal==="resultApproval"?null:modal==="market"?<button className="btn primary" onClick={() => { void saveMarket(); }}>保存市场评分</button>:modal==="approval"?<><button className="btn" onClick={()=>{void decide(false);}} disabled={flowSaving||purchaseReviewLoading||!purchaseReviewSnapshot}>驳回</button><button className="btn primary" onClick={()=>{void decide(true);}} disabled={flowSaving||purchaseReviewLoading||!purchaseReviewSnapshot}>审核通过</button></>:mode==="tracking"?<span className="muted">请在面板右上角保存浏览器本地草稿</span>:<button className="btn primary" onClick={saveRuleConfiguration}>保存并应用</button>}>
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
 {modal==="detail"&&p&&<>
      {p.backend?.evaluationDecision &&
        <div className="np-assessment-tabs" role="tablist" aria-label="新品测评详情标签">
          <button type="button" role="tab" aria-selected={detailSection==="details"}
            className={detailSection==="details"?"active":""}
            onClick={()=>setDetailSection("details")}>测评详情</button>
          <button type="button" role="tab" aria-selected={detailSection==="assessment"}
            className={detailSection==="assessment"?"active":""}
            onClick={()=>setDetailSection("assessment")}>测评结论与采购申请</button>
        </div>}
      {!p.backend?.evaluationDecision && p.backend &&
        p.backend.gradeConfirmation?.status!=="pending" &&
        p.backend.evaluation.grade!==null &&
        p.backend.evaluation.total!==null && detailSection==="details" &&
        <div className="np-assessment-pending-action">
          <span>正式评级已保存，等待人工测评确认</span>
          <button type="button" className="btn primary"
            onClick={()=>setDetailSection("assessment")}>确认测评</button>
        </div>}
      {detailSection==="details" && <>
      <NewProductEvaluationData product={p} />
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
        readOnly={Boolean(p.backend && p.backend.evaluation.grade !== null &&
          p.backend.evaluation.total !== null &&
          (p.backend.gradeConfirmation?.status!=="pending" || gradePreview))}
        onRequestCorrection={(requestedScore, reason)=>correct(d,requestedScore,reason)}
      />
    </div>
  ))}
</div>
{/* PR337_MANUAL_RISK_V1: manually assessed, never preselected. */}
{<NewProductManualRisk key={`${p.id}:${p.backend?.marketVersion??0}`}
  disabled={marketSaving}
  readOnly={Boolean(p.backend && p.backend.evaluation.grade !== null &&
    p.backend.evaluation.total !== null &&
    (p.backend.gradeConfirmation?.status!=="pending" || gradePreview))}
  editableSaved={p.backend?.gradeConfirmation?.status==="pending"}
  identity={p.backend?.identity}
  marketVersion={p.backend?.marketVersion??0}
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
  <MarketScoringDraft
    key={`${p.id}:${p.backend?.marketVersion??0}:${p.market!==null &&
      !(p.backend?.gradeConfirmation?.status==="pending" && !gradePreview)
      ?"saved":"editing"}`}
    initialScore={p.market}
    initialReason={p.marketReason || ""}
    initialCompetitorIds={p.marketCompetitorIds || []}
    initialNoCompetitors={p.marketNoCompetitors === true}
    saving={marketSaving}
    readOnly={p.market!==null &&
      !(p.backend?.gradeConfirmation?.status==="pending" && !gradePreview)}
    onSave={(value, reason, ids, none) => { void saveMarket(value, reason, ids, none); }}
  />

</div>

      </>}
    {(p.backend?.gradeConfirmation?.status!=="pending" || gradePreview) &&
      p.market!==null&&p.marketReason.trim().length>=5&&score(p,cfg)!==null?(
      <>
        {(detailSection==="assessment" ||
          p.backend?.gradeConfirmation?.status!=="pending" ||
          gradePreview) && gradeSummary}

        {detailSection==="details" &&
          p.backend?.gradeConfirmation?.status==="pending" && (
          <div className="np-grade-confirm-actions">
            {gradePreview ? <>
              <button type="button" className="btn np-grade-back-btn"
                disabled={gradeConfirmSaving}
                onClick={()=>setGradePreview(false)}>
                <svg viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="2"
                  strokeLinecap="round" strokeLinejoin="round"
                  aria-hidden="true">
                  <path d="m12 19-7-7 7-7M5 12h14"/>
                </svg>
                <span>返回修改</span>
              </button>
              <button type="button" className="btn primary np-grade-confirm-btn"
                disabled={gradeConfirmSaving||gradePreviewSaving}
                onClick={()=>{void confirmGrade();}}>
                <svg viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="2"
                  strokeLinecap="round" strokeLinejoin="round"
                  aria-hidden="true">
                  <circle cx="12" cy="12" r="9"/>
                  <path d="m8 12 2.5 2.5L16 9"/>
                </svg>
                <span>{gradeConfirmSaving?"确认中…":"确认等级"}</span>
              </button>
            </> : (
              <button type="button" className="btn primary"
                disabled={gradePreviewSaving||gradeConfirmSaving||marketSaving}
                onClick={()=>{void calculateGrade();}}>
                {gradePreviewSaving?"计算中…":"计算等级"}
              </button>
            )}
          </div>
        )}
        {detailSection==="assessment" && p.backend && p.backend.gradeConfirmation?.status!=="pending" && <div className="np-assessment-panel">
          {!p.backend.evaluationDecision &&
            <button type="button" className="np-assessment-back" onClick={()=>setDetailSection("details")}>
              ← 返回测评详情
            </button>}
          <div className="section-title np-assessment-panel-title">
            <span aria-hidden="true"><svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M13 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h9"/><path d="M7 8h8M7 12h4"/><path d="m13 18 6.8-6.8a1.8 1.8 0 0 1 2.6 2.6L15.6 20.6 12 21l1-3Z"/></svg></span>
            {p.backend.evaluationDecision?"人工测评结论与采购记录":"提交采购申请（基于人工测评结论）"}
          </div>
          {p.backend.evaluationDecision ? <div className="np-assessment-confirmed">
  <div className="np-assessment-form">

    <div className="form-field">
      <label className="form-label">是否测评通过</label>
      <select className="input"
        value={p.backend.evaluationDecision.decision}
        disabled>
        <option value="passed">测评通过</option>
        <option value="failed">测评不通过</option>
      </select>
    </div>

    <div className="form-field">
      <label className="form-label">测评原因（至少20字符）</label>
      <textarea className="textarea" rows={4}
        value={p.backend.evaluationDecision.reason || ""}
        disabled readOnly />
    </div>

    <div className="form-field">
      <label className="form-label">申请采购数量（件）</label>
      <input className="input" type="text"
        value={p.requestQty == null ? "—" : String(p.requestQty)}
        disabled readOnly />
    </div>

    <div className="form-field">
      <label className="form-label">采购数量调整原因</label>
      <textarea className="textarea" rows={4}
        value={p.requestReason || ""}
        disabled readOnly />
    </div>

    <div className="form-field">
      <label className="form-label">确认人</label>
      <input className="input" type="text"
        value={String(p.backend.evaluationDecision.actor_id ?? "—")}
        disabled readOnly />
    </div>

    <div className="form-field">
      <label className="form-label">确认时间</label>
      <input className="input" type="text"
        value={p.backend.evaluationDecision.confirmed_at?.slice(0,10) || "—"}
        disabled readOnly />
    </div>

    <div className="form-field">
      <label className="form-label">采购状态</label>
      <input className="input" type="text"
        value={
          p.backend.purchaseStatus === "submitted" ? "等待领导审批" :
          p.backend.purchaseStatus === "approved" ? "已审批通过" :
          p.backend.purchaseStatus === "rejected" ? "已驳回" :
          "尚未提交采购申请"
        }
        disabled readOnly />
    </div>

  </div>
</div> : <div className="np-assessment-form">
            <div className="form-field">
              <label className="form-label">是否测评通过 *</label>
              <ReviewSelect<"passed" | "failed">
                className="np-assessment-choice"
                value={assessmentChoice || undefined}
                placeholder="请选择"
                options={[{value:"passed",label:"测评通过"},{value:"failed",label:"测评不通过"}]}
                onChange={value=>setAssessmentChoice(value)}
              />
            </div>
            <div className="form-field">
              <label className="form-label">测评原因 *（至少20字符）</label>
              <textarea className="textarea" rows={3} value={assessmentReason}
                onChange={e=>setAssessmentReason(e.target.value)}
                placeholder="请填写人工测评依据，不少于20字符"/>
              <div className="cell-sub">
                {Array.from(assessmentReason.replace(/\s/g,"")).length} / 20字符
              </div>
            </div>
            {assessmentChoice==="passed" && <>
              <div className="form-field">
                <label className="form-label">申请采购数量（件）</label>
                <input className="input" type="number" min={1} max={100000}
                  value={assessmentQty} onChange={e=>setAssessmentQty(e.target.value)}/>
                <div className="cell-sub">系统建议：
                  {p.backend.suggestedQty===null?"未核实":`${p.backend.suggestedQty} 件`}
                </div>
              </div>
              {Number(assessmentQty)!==p.backend.suggestedQty && <div className="form-field">
                <label className="form-label">采购数量调整原因 *（至少10字符）</label>
                <textarea className="textarea" rows={3} value={assessmentPurchaseReason}
                  onChange={e=>setAssessmentPurchaseReason(e.target.value)}
                  placeholder="说明申请数量不同于系统建议的具体原因"/>
                <div className="cell-sub">
                  {Array.from(assessmentPurchaseReason.replace(/\s/g,"")).length} / 10字符
                </div>
              </div>}
            </>}
            <div style={{display:"flex",gap:12,flexWrap:"wrap"}}>
              <button type="button" className="btn"
                disabled={!assessmentChoice||Array.from(assessmentReason.replace(/\s/g,"")).length<20||assessmentSaving}
                onClick={()=>{void confirmManualAssessment();}}>
                {assessmentChoice==="failed"?"确认测评不通过":"仅确认测评"}
              </button>
              {assessmentChoice==="passed" && <button type="button" className="btn primary"
                disabled={assessmentSaving||Array.from(assessmentReason.replace(/\s/g,"")).length<20||
                  !/^[1-9]\d*$/.test(assessmentQty)||Number(assessmentQty)>100000||
                  p.backend.suggestedQty==null||
                  (Number(assessmentQty)!==p.backend.suggestedQty&&
                    Array.from(assessmentPurchaseReason.replace(/\s/g,"")).length<10)}
                onClick={()=>{void confirmManualAssessment(true);}}>
                确认通过并提交采购申请
              </button>}
            </div>
          </div>}
        </div>}
      </>
    ):p.backend?.gradeConfirmation?.status==="pending" ? null
      :<div className="info-box">{p.market===null
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
    <IsolatedTrackingReviewDrawer
      key={p.id}
      p={p}
      cfg={cfg}
      initialReview={review}
      initialNote={note}
      reviewFinal={reviewFinal}
      reviewWaiting={reviewWaiting}
      reviewReadOnly={reviewReadOnly}
      flowSaving={flowSaving}
      close={close}
      saveReview={saveReview}
    />
  )}

  {mode==="performance"&&evaluationReviewItem&&(()=>{
    const candidate=evaluationReviewItem;
    return candidate?.backend ? <NewProductEvaluationReviewModal key={candidate.id}
      visible productName={candidate.name} itemId={candidate.item}
      manualPassAllowed={candidate.backend.failedAssessmentInfo?.manual_pass_allowed === true && candidate.backend.evaluationDecision?.decision === "failed"}
      legacyExceptionAllowed={["D","Pass"].includes(candidate.backend.evaluation.grade??"")}
      submitting={evaluationReviewSubmitting}
      onClose={()=>{if(!evaluationReviewSubmitting)setEvaluationReviewItem(null);}}
      onSubmit={submitEvaluationReview}/> : null;
  })()}
  {notice&&<div className="np-native-toast">{notice}</div>}
 </div></div></PageShell>;
}


/* TRACKING_DRAWER_PERFORMANCE_V4 */

type IsolatedTrackingReviewDrawerProps = {
  p: Product;
  cfg: Config;
  initialReview: string;
  initialNote: string;
  reviewFinal: boolean;
  reviewWaiting: boolean;
  reviewReadOnly: boolean;
  flowSaving: boolean;
  close: () => void;
  saveReview: (review: string, note: string) => Promise<void>;
};

function IsolatedTrackingReviewDrawer({
  p,
  cfg,
  initialReview,
  initialNote,
  reviewFinal,
  reviewWaiting,
  reviewReadOnly,
  flowSaving,
  close,
  saveReview,
}: IsolatedTrackingReviewDrawerProps) {
  const [review,setReview]=useState(initialReview);
  const [note,setNote]=useState(initialNote);
  const [trackingChosenResult,setTrackingChosenResult]=useState("");
  const [trackingPurchaseQty,setTrackingPurchaseQty]=useState<number|null>(null);
  const [trackingPurchaseRemark,setTrackingPurchaseRemark]=useState("");

  const trackingSelectedSuccess =
    p.tracking==="打品成功" ||
    (!reviewReadOnly && trackingChosenResult==="打品成功");

  return (
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
            <ReviewButton onClick={close} disabled={flowSaving}>{reviewReadOnly ? "关闭" : "取消"}</ReviewButton>
            {trackingSelectedSuccess&&(
              <ReviewButton
                type="primary"
                disabled
                title="专项采购接口尚未启用"
              >
                申请采购
              </ReviewButton>
            )}
            {!reviewReadOnly && ["继续观察","需要优化","打品失败"].includes(trackingChosenResult) && <ReviewButton type="primary" onClick={()=>{void saveReview(review,note);}} disabled={flowSaving || !validTrackingReviewReason(note) || !["继续观察","需要优化","打品成功","打品失败"].includes(review)}>保存打品结果</ReviewButton>}
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
          value={reviewWaiting ? undefined :
            reviewReadOnly ? review :
            trackingChosenResult || undefined}
          disabled={reviewReadOnly}
          onChange={(event) => {
            setReview(event.target.value);
            setTrackingChosenResult(event.target.value);
          }}
          options={[
            {label:"打品成功", value:"打品成功"},
            {label:"继续观察", value:"继续观察"},
            {label:"需要优化", value:"需要优化"},
            {label:"打品失败", value:"打品失败"},
          ]}
        />
        <div className="np-review-hint">
          {!reviewReadOnly && !trackingChosenResult
            ? "请选择打品结果"
            : review === "打品成功" ? "已达成当前打品目标，可记录成功依据。" :
            review === "继续观察" ? "暂不作成功或失败判定，继续跟踪经营数据。" :
            review === "需要优化" ? "记录需要优化的具体原因和处理方向。" :
            review === "打品失败" ? "记录失败原因，便于后续复盘。" :
            "等待开售属于跟踪阶段，不是打品结果；开售后才能人工判定。"}
        </div>
      </section>

      <section className="np-review-card">
        <div className="np-review-section-heading">
          <h3>复盘说明 / 判定依据
            {!reviewReadOnly && <span className="np-review-required"> *</span>}
          </h3>
          <span>{reviewReadOnly ? "仅供查看" : `至少10个字 · 已填写 ${trackingReviewReasonLength(note)} 字`}</span>
        </div>
        <ReviewInput.TextArea
          aria-label="复盘说明与判定依据"
          aria-required={!reviewReadOnly}
          value={note}
          readOnly={reviewReadOnly}
          onChange={(event) => setNote(event.target.value)}
          placeholder={review === "打品失败" ? "填写导致打品失败的经营原因" :
            review === "需要优化" ? "填写需优化的问题及后续建议" :
            "请填写判断依据、观察结论或下一步跟进情况（至少10个字）"}
          autoSize={{ minRows: 4, maxRows: 7 }}
          style={{ resize: "none" }}
        />
      </section>
      {trackingSelectedSuccess&&(
        <section
          key={"tracking-purchase-"+p.id}
          className="np-review-card"
        >
          <div className="np-review-section-heading">
            <h3>采购申请</h3>
            <span>待申请</span>
          </div>
          <div style={{marginTop:12}}>
            <label className="form-label">
              申请采购数量（件）
              <span className="np-review-required"> *</span>
            </label>
            <ReviewInputNumber
              min={1}
              max={100000}
              step={1}
              precision={0}
              value={trackingPurchaseQty}
              onChange={value=>setTrackingPurchaseQty(value)}
              placeholder="请输入采购数量"
              style={{width:"100%",marginTop:8}}
            />
          </div>
          <div style={{marginTop:16}}>
            <label className="form-label">
              采购备注
              <span className="np-review-required"> *</span>
            </label>
            <ReviewInput.TextArea
              value={trackingPurchaseRemark}
              onChange={event=>setTrackingPurchaseRemark(event.target.value)}
              placeholder="请填写采购原因及相关说明"
              maxLength={4000}
              autoSize={{minRows:3,maxRows:7}}
              style={{marginTop:8,resize:"none"}}
            />
          </div>
        </section>
      )}
    </ReviewDrawer>
  );
}

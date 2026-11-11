import {useLocation} from "react-router-dom";
// PR337_TRACKING_EDITABLE_PENDING_V4
// PR337_TRACKING_OUTCOME_LOCK_V3
/* PR337_APPROVED_CARD_FILTER_V53 */
/* PR337_MANAGEMENT_STAT_FILTER_V51 */
// PR337_FLOW_ACCEPTANCE_20261111
import {useMemo, useState,type ReactNode, useCallback} from "react";
import { Drawer as AntdDrawer } from "antd";
import ManagementStatCards from "@/components/report-table/ManagementStatCards";
import NewProductPerformanceReport from "./NewProductPerformanceReport";
import PageShell from "@/components/page/PageShell";
import type {NavigationPage} from "@/config/navigation";
import NativeBoard from "./TrackingBoardSwitch";
import dayjs from "dayjs";
import {withTrackingVisualSamples} from "./trackingBoardVisualSamples";
import type {TrackingDrillFilter} from "./trackingBoardDrilldown";
import NewProductTrackingReport from "./NewProductTrackingReport";
import {samples,defaultConfig,bands,score,grade,suggestion,type Product,type Config} from "./nativeData";
import { makeNewProductDevMockRows } from "./newProductDevelopmentFixtures";
import NewProductRulesPanel from "./NewProductRulesPanel";
import { createInitialRuleDraft, cloneRuleDraft, validateRuleDraft, validateTrackingRuleDraft, type RuleDraft } from "./NewProductRulesModel";
import TrackingRuleConfigPanel from "./components/TrackingRuleConfigPanel";
import "./nativeWorkflow.css";
import "./newProductReviewDrawer.css";
import { Button as ReviewButton, Descriptions as ReviewDescriptions, Drawer as ReviewDrawer, Input as ReviewInput, Radio as ReviewRadio, Tag as ReviewTag } from "antd";
type Mode="performance"|"tracking";
type Props={page:NavigationPage;mode:Mode;username?:string;canManage?:boolean;canConfigure?:boolean;canScore?:boolean;canRequest?:boolean;canReview?:boolean;canViewCost?:boolean};
type ModalType="detail"|"market"|"purchase"|"approval"|"review"|"config"|"correction"|null;
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

export default function NewProductPages({page,mode}:Props){
 const [items,setItems]=useState<Product[]>(()=>([...samples, ...(import.meta.env.DEV && mode === "performance" ? makeNewProductDevMockRows(samples) : [])].map(p=>({...p,scores:{...p.scores}})))),[cfg,setCfg]=useState<Config>(defaultConfig);
 const [savedRuleDraft,setSavedRuleDraft]=useState<RuleDraft>(()=>createInitialRuleDraft(defaultConfig));
 const [ruleDraft,setRuleDraft]=useState<RuleDraft>(()=>createInitialRuleDraft(defaultConfig));
 const pr337BoardLocation=useLocation();
 const pr337NavKey=`${mode}:${pr337BoardLocation.pathname}:${pr337BoardLocation.key}`;
 const [pr337BoardTabState,setPr337BoardTabState]=useState<{navKey:string;view:"list"|"board"}>(()=>({navKey:pr337NavKey,view:"board"}));
 const tab=pr337BoardTabState.navKey===pr337NavKey?pr337BoardTabState.view:"board";
 const setTab=useCallback((view:"list"|"board")=>setPr337BoardTabState({navKey:pr337NavKey,view}),[pr337NavKey]);
 const [phase,setPhase]=useState("all"),[reportRevision,setReportRevision]=useState(0);
 const [modal,setModal]=useState<ModalType>(null),[selected,setSelected]=useState<string|null>(null),[scoreValue,setScoreValue]=useState<number|null>(null),[qty,setQty]=useState(0),[note,setNote]=useState(""),[review,setReview]=useState("继续观察");
 const [correctionDim,setCorrectionDim]=useState<Correction["dimension"]>("speed"),[,setCorrections]=useState<Correction[]>([]),[cfgTab,setCfgTab]=useState("weights"),[version,setVersion]=useState(1),[notice,setNotice]=useState("");
 const [approvalFocus,setApprovalFocus]=useState<string|null>(null);
 const [trackingDrill,setTrackingDrill]=useState<TrackingDrillFilter|null>(null);
 const [trackingSampleAnchor]=useState(()=>dayjs().format('YYYY-MM-DD'));
 const trackingProducts=useMemo(()=>mode==='tracking'
   ?withTrackingVisualSamples(items,trackingSampleAnchor):items,[items,mode,trackingSampleAnchor]);
 const p=items.find(x=>x.id===selected);
 const reviewFinal = p?.tracking === "打品成功" || p?.tracking === "打品失败";
 // PR337 local Mock only: launch date + arrival date act as the tracking-start proxy.
 // Production must use an explicit "Listing is sellable" field instead.
 const reviewWaiting = Boolean(p &&
   (p.tracking === "等待开售" || p.tracking === "未判定") &&
   !(p.launch?.trim() && p.arrival?.trim()));
 const reviewReadOnly = reviewFinal || reviewWaiting;
 const msg=(s:string)=>{setNotice(s);window.setTimeout(()=>setNotice(""),2600)};
 const patch=(id:string,change:Partial<Product>)=>setItems(prev=>prev.map(x=>x.id===id?{...x,...change}:x));
 const show=(kind:ModalType,id?:string)=>{
   const item=id?items.find(x=>x.id===id):undefined;
   if(kind==="approval"&&item){
     if(item.status!=="审核中"){msg("仅审核中的商品可以查看申请");return}
     setModal(null);
     setSelected(null);
     setTab("list");
     setPhase("approval");
     setApprovalFocus(item.item);
     setReportRevision(n=>n+1);
     return;
   }
   if(kind==="purchase"&&item){
     if(item.status!=="待采购确认"){
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
     setScoreValue(item.market);
     setQty(item.requestQty??suggestion(item,cfg));
     setNote(kind==="purchase"?(item.requestReason||""):(item.marketReason||""));
     setReview(item.tracking||"继续观察");
   }
 };
 const close=()=>{setModal(null);setNote("")};
 const reset=()=>{setPhase("all");setReportRevision(n=>n+1)};

 const openConfigPanel=()=>{
   setRuleDraft(cloneRuleDraft(savedRuleDraft));
   setModal("config");
 };
 const saveRuleConfiguration=()=>{
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
     msg("打品成功标准草稿已保存（Demo）");
     return;
   }
   const validation=validateRuleDraft(ruleDraft);
   if(validation){msg(validation);return;}
   const saved=cloneRuleDraft(ruleDraft);
   setSavedRuleDraft(previous=>({...saved,success:previous.success}));
   setCfg(current=>({
     ...current,
     weights:{...saved.weights},
     remindDays:saved.remindDays,
     gradeBands:saved.gradeBands,
     quantities:saved.quantities,
     quantityStrategy:saved.quantityStrategy,
     penaltyRules:saved.penalties,
     vetoRules:saved.vetoes,
   }));
   setVersion(v=>v+1);
   close();
   msg("配置草稿已保存（Demo）");
 };
 const exportRows=()=>{const csv=["SKU,Item ID,品名,负责人,综合分,评级,建议量,状态",...items.map(x=>[x.sku,x.item,x.name,x.owner,score(x,cfg)??"",grade(x,cfg)??"",suggestion(x,cfg),x.status].join(","))].join("\n");const url=URL.createObjectURL(new Blob(["\uFEFF"+csv],{type:"text/csv;charset=utf-8"}));const a=document.createElement("a");a.href=url;a.download="新品表现Mock.csv";a.click();URL.revokeObjectURL(url)};
 const pending=items.filter(x=>x.status==="待市场评分").length,purchase=items.filter(x=>x.status==="待采购确认").length,approval=items.filter(x=>x.status==="审核中").length;
 const saveMarket=()=>{
   if(!p||p.status!=="待市场评分"){
     msg("当前商品不是待市场评分状态");return;
   }
   if(scoreValue===null||!Number.isInteger(scoreValue)||scoreValue<0||scoreValue>10||note.trim().length<5){
     msg("市场竞争分数与至少5个字符的评价依据均为必填");return;
   }
   const evaluated={...p,market:scoreValue,marketReason:note.trim()};
   const finalGrade=grade(evaluated,cfg);
   const nextStatus=finalGrade==="D"||finalGrade==="Pass"?"测评停止":"待采购确认";
   patch(p.id,{market:scoreValue,marketReason:note.trim(),status:nextStatus,
     risk:p.risk==="待人工评分"?"":p.risk});
   setNote(note.trim());
   msg(nextStatus==="测评停止"?"评分已保存，当前评级不进入采购流程":"评分已保存，已生成评级与采购建议");
   // Keep the detail drawer open; saved evaluation is rendered below, read-only.
 };
 const sendPurchase=()=>{
   if(!p||p.status!=="待采购确认"){
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
 const decide=(pass:boolean)=>{if(!p)return;patch(p.id,{status:pass?"已批准":"已驳回",actualQty:pass?qty:p.actualQty,tracking:pass?"等待开售":p.tracking});close();msg(pass?"模拟审批通过":"模拟申请被驳回")};
 const saveReview=()=>{
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
 const correct=()=>{if(!p||scoreValue===null||note.trim().length<5){msg("请填写分数和原因");return}setCorrections(s=>[...s,{id:s.length+1,sku:p.sku,dimension:correctionDim,from:p.scores[correctionDim],to:scoreValue,reason:note,status:"待审核"}]);close();msg("评分修正申请已提交")};
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
          msg("已刷新示例数据");
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
 {tab==="board"?<NativeBoard mode={mode} products={mode==="tracking"?trackingProducts:items} config={cfg} detail={()=>setTab("list")} onTrackingDrill={filter=>{setTrackingDrill(filter);setTab("list");}} open={(key,id)=>key==="export"?exportRows():show(key as ModalType,id)}/>:
 mode==="performance"?<>
 <ManagementStatCards ariaLabel="新品表现统计" className="np-performance-stats"
   activeKey={phase}
   cards={[
     {key:"all",title:"全部新品",subtitle:"当前全部测评商品",value:items.length,tone:"normal",icon:<span>▦</span>},
     {key:"market",title:"待市场评分",subtitle:"自动评分完成，等待运营判断",value:pending,tone:"normal",icon:<span>✎</span>},
     {key:"purchase",title:"待确认采购",subtitle:"已评级，等待确认采购数量",value:purchase,tone:"normal",icon:<span>▤</span>},
     {key:"approval",title:"审核中",subtitle:"包含数量调整申请",value:approval,tone:"warning",icon:<span>◷</span>},
     {key:"approved",title:"已通过",subtitle:"审批已通过的商品",value:items.filter(x=>["已批准","已通过","审批通过"].includes(x.status)).length,tone:"success",icon:<span>✓</span>},
   ]}
   onCardClick={(key)=>{setPhase(key);setApprovalFocus(null);setReportRevision(n=>n+1);}}/>

 <NewProductPerformanceReport key={reportRevision} items={items} config={cfg} phase={phase} focusItemId={approvalFocus} onOpen={(kind,id)=>show(kind,id)}
      onResetPhase={()=>{setApprovalFocus(null);setPhase(current=>current==="approval"||current==="approved"?current:"all")}}/>
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
{modal&&modal!=="review"&&<Drawer title={{detail:"新品测评详情",market:"市场竞争评分",purchase:"确认采购数量",approval:"新品采购审核",review:"打品结果复盘",config:mode==="tracking"?"打品辅助规则配置":"新品表现配置",correction:"评分修正申请"}[modal]} sub={p?p.sku+" · "+p.name:"规则草稿 · 仅影响 Mock"} close={close} wide={modal==="config"} footer={modal==="detail"?null:modal==="market"?<button className="btn primary" onClick={saveMarket}>保存市场评分</button>:modal==="purchase"?<button className="btn primary" onClick={sendPurchase}>提交领导审核</button>:modal==="approval"?<><button className="btn" onClick={()=>decide(false)}>驳回</button><button className="btn primary" onClick={()=>decide(true)}>审核通过</button></>:modal==="correction"?<button className="btn primary" onClick={correct}>提交申请</button>:mode==="tracking"?<span className="muted">请在面板右上角保存浏览器本地草稿</span>:<button className="btn primary" onClick={saveRuleConfiguration}>保存配置草稿</button>}>
 {p&&modal!=="config"&&<div className="product-summary"><div className="thumb">▤</div><div><div className="summary-name">{p.name}</div><div className="summary-meta">{p.sku} · Item ID {p.item} · 负责人 {p.owner}</div><Status text={p.status}/></div><div className="summary-right"><div className="score-main">{score(p,cfg)?.toFixed(2)||"—"}</div><div className="cell-sub">{grade(p,cfg)||"待评分"} 级</div></div></div>}
 {modal==="detail"&&p&&<><div className="section-title">自动评分明细</div><div className="score-grid">{(["speed","ad","profit","trust"] as const).map((d,i)=><div className="score-item" key={d}><div className="score-item-top"><span className="score-item-name">{["出单速度","广告有效性","利润空间","数据可信度"][i]}</span><span className="score-item-value">{p.overrides?.[d]??p.scores[d]} /10</span></div><p>源于业务经营数据 · 权重 {cfg.weights[d]}%</p><button className="btn small" onClick={()=>{setCorrectionDim(d);setScoreValue(p.scores[d]);setNote("");setModal("correction")}}>申请修正</button></div>)}</div>
<div className="section-title">市场竞争评分
      <span className="cell-sub">{p.status==="待市场评分"?"必填":"已保存"}</span>
    </div>
    {p.status==="待市场评分"?(
      <div className="score-item">
        <div className="score-item-top"><b>市场竞争分数（必填）</b>
          <b>{scoreValue===null?"未评分":`${scoreValue} /10`}</b>
        </div>
        <div className="market-scale">{Array.from({length:11},(_,i)=>(
          <button type="button" key={i}
            className={"market-score-btn "+(scoreValue===i?"active":"")}
            onClick={()=>setScoreValue(i)}>{i}</button>
        ))}</div>
        <div className="form-field"><label className="form-label">
          市场竞争评价依据（必填，至少5个字符）
        </label><textarea className="textarea" rows={3} style={{resize:"none"}}
          aria-label="市场竞争评价依据" value={note}
          onChange={e=>setNote(e.target.value)}
          placeholder="填写竞品数量、价格、评价和差异化依据" /></div>
        <div className="row-buttons"><button type="button" className="btn primary"
          onClick={saveMarket}>保存市场评分并计算</button>
          <span className="cell-sub">保存后显示评级与采购建议，无需下一步</span></div>
      </div>
    ):(
      <div className="score-item">
        <div className="score-item-top"><b>市场竞争分数（已保存）</b>
          <b>{p.market===null?"未评分":`${p.market} /10`}</b></div>
        <p>评价依据：{p.marketReason||"—"}</p>
      </div>
    )}
    <div className="section-title">测品数据</div>
    <div className="kv-list">
      <div className="kv-row"><span className="kv-key">首单与订单</span>
        <span className="kv-val">首单时间待接入 · 近7天 {p.qty7} 单 · 累计订单 {p.orders}</span></div>
      <div className="kv-row"><span className="kv-key">广告表现</span>
        <span className="kv-val">花费 ${p.spend} · 点击 {p.clicks} · ACOS {p.acos}%</span></div>
      <div className="kv-row"><span className="kv-key">盈利能力</span>
        <span className="kv-val">ROI {p.roi} · 毛利率 {p.margin}%</span></div>
      <div className="kv-row"><span className="kv-key">数据扣分</span>
        <span className="kv-val">{p.penalties>0?`当前示例扣 ${p.penalties} 分`:"当前示例未触发通用扣分"}</span></div>
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
    ):<div className="info-box">市场竞争评分未保存前，不生成最终评级和采购建议。</div>}
    </>}
 {modal==="market"&&<><div className="section-title">市场竞争评分（0–10 分）</div><div className="market-scale">{Array.from({length:11},(_,i)=><button key={i} className={"market-score-btn "+(scoreValue===i?"active":"")} onClick={()=>setScoreValue(i)}>{i}</button>)}</div><div className="form-field"><label className="form-label">市场竞争评价依据</label><textarea className="textarea" rows={4} value={note} onChange={e=>setNote(e.target.value)} placeholder="竞品数量、售价、Review、差异化空间等"/></div></>}
 {modal==="purchase"&&p&&<><div className="kv-list"><div className="kv-row"><span className="kv-key">系统建议采购量</span><b>{suggestion(p,cfg)} 件</b></div><div className="kv-row"><span className="kv-key">当前评级范围</span><span>{(cfg.quantities?.[grade(p,cfg)||"D"]??bands[grade(p,cfg)||"D"]).join("–")} 件</span></div></div><div className="form-field"><label className="form-label">运营申请采购数量</label><input className="input" type="number" min={1} value={qty} onChange={e=>setQty(Number(e.target.value))}/></div>{qty>(cfg.quantities?.[grade(p,cfg)||"D"]??bands[grade(p,cfg)||"D"])[1]&&<div className="warning-box">超过当前等级采购范围，需要说明原因。</div>}<div className="form-field"><label className="form-label">调整原因</label><textarea className="textarea" rows={4} value={note} onChange={e=>setNote(e.target.value)}/></div></>}
 {modal==="approval"&&p&&<><div className="kv-list">{[["系统建议",suggestion(p,cfg)+" 件"],["申请数量",(p.requestQty||qty)+" 件"],["申请原因",p.requestReason||"按建议提交"]].map(([k,v])=><div className="kv-row" key={k}><span className="kv-key">{k}</span><span className="kv-val">{v}</span></div>)}</div><div className="info-box">Mock 审批不会生成正式采购单或实际业务记录。</div></>}
 {modal==="correction"&&p&&<><div className="form-field"><label className="form-label">评分维度</label><select className="select" value={correctionDim} onChange={e=>setCorrectionDim(e.target.value as Correction["dimension"])}>{[["speed","出单速度"],["ad","广告有效性"],["profit","利润空间"],["trust","数据可信度"]].map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></div><div className="form-field"><label className="form-label">申请分数</label><input className="input" type="number" min={0} max={10} value={scoreValue??""} onChange={e=>setScoreValue(Number(e.target.value))}/></div><div className="form-field"><label className="form-label">修正依据</label><textarea className="textarea" rows={4} value={note} onChange={e=>setNote(e.target.value)}/></div></>}
 {modal==="config"&&(mode==="tracking"?<TrackingRuleConfigPanel />:<div className="np-rules-config"><div className="config-shell">
      {mode==="performance"&&<div className="card config-nav">{[["weights","评分权重"],["criteria","评分标准"],["grades","评级与采购数量"],["penalties","扣分与否决"],["version","规则版本"]].map(([key,name])=><button type="button" key={key} className={cfgTab===key?"active":""} onClick={()=>setCfgTab(key)}>{name}</button>)}</div>}
      <div className="card config-panel"><NewProductRulesPanel tab={cfgTab} draft={ruleDraft} onChange={setRuleDraft} version={version} products={items}/></div>
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
            {!reviewReadOnly && <ReviewButton type="primary" onClick={saveReview}>保存打品结果</ReviewButton>}
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
          {key:"sold", label:"30天销量", children:`${p.sold30} 件`},
          {key:"profit", label:"利润率", children:`${p.margin}%`},
          {key:"acos", label:"ACOS", children:`${p.acos}%`},
          {key:"stock", label:"当前库存", children:`${p.inventory} 件`},
          {key:"suggest", label:"系统建议量", children:`${suggestion(p,cfg)} 件`},
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

  {notice&&<div className="np-native-toast">{notice}</div>}
 </div></div></PageShell>;
}

import { completeClearanceApplication, getClearanceApplication, getClearanceListing, submitClearanceApplication, type ApplicationDetail } from "./clearanceApi";
import { BackendRequestError } from "@/api/backendApi";
import { QuestionCircleOutlined } from "@ant-design/icons";
import { useEffect, useState } from "react";
import { Button, Card, Checkbox, DatePicker, Divider, Form, Input, InputNumber, Modal, Progress, Select, Space, Switch, Table, Tag, Typography, message, Tooltip, Tabs } from "antd";
import dayjs from "dayjs";
import type { ColumnsType } from "antd/es/table";
import {
 CLEARANCE_PRODUCTS,
 DEFAULT_RULES,
 METHODS,
 REASONS,
 STATUS_NAMES,
 activeTaskFor,
 chinaToday,
 chinaNow,
 coverage,
 evaluateProduct,
 findProduct,
 taskProgress,
 taskQty,
 taskRemoved,
 taskSold,
 taskStore,
 validateRules,
 type ClearanceProduct,
 type ClearanceRules,
 type StoredClearance,
} from "./clearanceModel";
import { RiskTag, StatusTag } from "./clearanceUi";
import { CLEARANCE_RULE_GROUPS, CLEARANCE_RULE_SPECS, type ClearanceRuleSpec } from "./clearanceRuleCatalog";
import { integer, money, percent } from "./clearanceUiConfig";

interface Props {data:StoredClearance;onChange:(data:StoredClearance)=>void;role:string;readOnly?:boolean;onSaveRule?:(rules:ClearanceRules)=>Promise<void>}
export function ClearanceRulesPanel({data,readOnly=false,onSaveRule}:Props){
 const [draft,setDraft]=useState<ClearanceRules>(()=>({...DEFAULT_RULES,...data.rules}));
 const error=validateRules(draft);
 const same=JSON.stringify(draft)===JSON.stringify(data.rules);
 const apply=async()=>{
  if(readOnly||!onSaveRule)return;
  const invalid=validateRules(draft);if(invalid){void message.error(invalid);return;}
  if(same&&data.ruleVersion>0){void message.info("规则未发生变化");return;}
  try{await onSaveRule({...draft});}catch{/* Keep edited values on version conflict or failure. */}
 };
 const renderSpec=(f:ClearanceRuleSpec)=>{
  const title=<Tooltip
   overlayClassName="clearance-rule-plain-tooltip"
   styles={{ root: { pointerEvents: "none" } }}
   mouseEnterDelay={0.1}
   placement="top"
   title={<div className="clearance-rule-plain-content">
    <div className="clearance-rule-plain-title">{f.label}</div>
    <div className="clearance-rule-plain-row"><strong>这是干什么的</strong><div>{f.help}</div></div>
    <div className="clearance-rule-plain-row"><strong>举个例子</strong><div>{f.example}</div></div>
    <div className="clearance-rule-plain-row"><strong>怎么设置</strong><div>{f.adjust}</div></div>
    <div className="clearance-rule-plain-row"><strong>会有什么影响</strong><div>{f.effect}</div></div>
    {f.needs&&<div className="clearance-rule-plain-data">需要数据：{f.needs}。如果该数据尚未接入，这条规则不会凭空触发。</div>}
   </div>}>
   <span className="clearance-rule-explain-label" tabIndex={0}>{f.label}
    <QuestionCircleOutlined aria-label={f.label+"说明"} className="clearance-rule-help"/>
   </span>
  </Tooltip>;
  if(f.kind==="switch")return <label key={f.key} className="clearance-explain-toggle">
   <Switch size="small" checked={Boolean(draft[f.key])} onChange={v=>setDraft(old=>({...old,[f.key]:v}))}/>{title}
  </label>;
  if(f.kind==="lookback")return <label key={f.key} className="clearance-explain-field">{title}<Select size="small" value={draft.zeroLookback} options={[7,14,30].map(n=>({value:n,label:n+" 天"}))} onChange={v=>setDraft(old=>({...old,zeroLookback:v as 7|14|30}))}/></label>;
  return <label key={f.key} className="clearance-explain-field">{title}
   <div className="clearance-explain-number"><InputNumber size="small" min={0} style={{width:"100%"}} value={Number(draft[f.key])} onChange={v=>setDraft(old=>({...old,[f.key]:v??NaN}))}/><span>{f.unit}</span></div>
  </label>;
 };
 const tabItems=CLEARANCE_RULE_GROUPS.map((name,i)=>({key:name,label:name,children:<div className="clearance-explain-section" key={name}>
  <div className="clearance-explain-fields">{CLEARANCE_RULE_SPECS.filter(x=>x.group===name&&x.kind!=="switch").map(renderSpec)}</div>
  <div className="clearance-explain-switches">{CLEARANCE_RULE_SPECS.filter(x=>x.group===name&&x.kind==="switch").map(renderSpec)}</div>
  <div className="clearance-explain-section-note">{i===0?"库存准入决定是否进入风险候选":i===1?"经营指标须满足库存准入，不单独触发清货":i===2?"保护与冲突用于减少误判和提示协调，不自动调整库存":i===3?"优先级仅影响处理先后，不单独改变风险等级":"处理建议只提供参考，不自动降价、清货或提交审批"}</div>
 </div>}));
 return <div className="clearance-rule-page clearance-rule-explained-page">
  <Card title="自动识别条件" size="small" className="clearance-rule-explained-card">
   <Tabs size="small" className="clearance-rule-explained-tabs" items={tabItems} animated={false} destroyOnHidden={false}/>
   {error&&<Typography.Text type="danger" className="clearance-block">{error}</Typography.Text>}
   <div className="clearance-rule-actions clearance-rule-explained-actions">
    <Button className="clearance-rule-actions__default" onClick={()=>setDraft({...DEFAULT_RULES})}>默认值</Button>
    <Button className="clearance-rule-actions__save" type="primary" disabled={Boolean(error)||readOnly||(same&&data.ruleVersion>0)} onClick={()=>{void apply();}}>保存并应用</Button>
   </div>
  </Card>
 </div>;
}

interface ApplyDraft {ids:string[];editId?:string;source:"auto"|"manual"}
interface ApplyValues {reason:string;methods:string[];due:dayjs.Dayjs;remark:string;quantities:Record<string,number>}
interface ModalsProps extends Props {
 applicant:string|null;setApplicant:(x:string|null)=>void;
 manualOpen:boolean;setManualOpen:(x:boolean)=>void;
 taskId:string|null;setTaskId:(x:string|null)=>void;
 apply:ApplyDraft|null;setApply:(x:ApplyDraft|null)=>void;
}
interface SkuDeepAnalysisModalProps {
  product: ClearanceProduct;
  data: StoredClearance;
  role: string;
  onClose: () => void;
  onApply: () => void;
  onRemoveManual: () => void;
}
type SkuDetailTab = "business" | "inventory";

function SkuDeepAnalysisModal({ product, data, onClose, onApply, onRemoveManual }: SkuDeepAnalysisModalProps) {
  const [activeTab, setActiveTab] = useState<SkuDetailTab>("business");
  const [quantity, setQuantity] = useState<number>(product.avail);
  const [price, setPrice] = useState<number>(product.price);



  const risk = evaluateProduct(product, data.rules);
  const activeTask = activeTaskFor(data.tasks, product.id);
  const eligible = true;
  const safeQuantity = Math.max(0, Math.min(product.avail, Number(quantity) || 0));
  const safePrice = Number.isFinite(price)?Math.max(0,price):undefined;
  const estimatedRevenue = safePrice===undefined?Number.NaN:safeQuantity * safePrice;
  const remainingInventory = Math.max(0, product.avail - safeQuantity);
  const p7 = product.per[7];
  const riskMessages = [
    ...risk.reasons.filter(item => item !== "暂未达到自动清货准入条件"),
    ...risk.business,
  ];
  const advice: { title: string; description: string }[] = [];
  if (p7.units === 0 && p7.ads > 0) {
    advice.push({ title: "排查广告持续花费", description: `近7天没有销售，但广告费为${money(p7.ads)}。建议检查广告关键词、点击和订单归因。` });
  }
  if (risk.business.some(item => item.includes("下滑"))) {
    advice.push({ title: "关注近期销量下降", description: "近7天销量较前7天下降，建议结合近14天和30天趋势复核。" });
  }
  if (risk.business.some(item => item.includes("退货"))) {
    advice.push({ title: "检查退货情况", description: "当前退货指标达到现有规则阈值，建议查看退货数据和商品反馈。" });
  }
  if (risk.business.some(item => item.includes("评分"))) {
    advice.push({ title: "检查商品评价", description: `当前评分${product.rating.toFixed(1)}分，建议查看近期差评反馈。` });
  }
  if (advice.length === 0) {
    advice.push({
      title: risk.level === "low" ? "持续关注库存周转" : "根据当前风险进行复核",
      description: riskMessages[0] || "当前没有明显异常，可继续观察销售和库存变化。",
    });
  }

  const periodRows = [
    { key: "units", label: "销量" },
    { key: "daily", label: "日均销量" },
    { key: "revenue", label: "销售额" },
    { key: "ads", label: "广告费" },
    { key: "adRate", label: "广告占比" },
    { key: "profit", label: "利润" },
    { key: "margin", label: "利润率" },
  ];

  const renderPeriodValue = (key: string, days: 7 | 14 | 30) => {
    const metric = product.per[days];
    if (key === "units") return integer(metric.units);
    if (key === "daily") return Number.isFinite(metric.units) ? (metric.units / days).toFixed(2) : "—";
    if (key === "revenue") return money(metric.revenue);
    if (key === "ads") return money(metric.ads);
    if (key === "adRate") return percent(metric.adRate);
    if (key === "profit") return <span className={metric.profit < 0 ? "clearance-sku-value-negative" : metric.profit > 0 ? "clearance-sku-value-positive" : ""}>{money(metric.profit)}</span>;
    return <span className={metric.margin !== null && metric.margin < 0 ? "clearance-sku-value-negative" : metric.margin !== null && metric.margin > 0 ? "clearance-sku-value-positive" : ""}>{percent(metric.margin)}</span>;
  };

  return <Modal
    className="clearance-sku-deep-modal"
    open
    centered
    width="min(1360px, 92vw)"
    title={null}
    closable={false}
    footer={null}
    onCancel={onClose}
    destroyOnHidden
    styles={{ body: { padding: 0, height: "100%", overflow: "hidden" } }}
  >
    <div className="clearance-sku-dialog">
      <div className="clearance-sku-dialog__header">
        <div className="clearance-sku-dialog__avatar">S</div>
        <div className="clearance-sku-dialog__identity">
          <div className="clearance-sku-dialog__title">{product.name} · SKU 深度分析</div>
          <div className="clearance-sku-dialog__meta">
            <span>SKU <strong>{product.sku}</strong></span>
            <span>MSKU <strong>{product.msku}</strong></span>
            <span>{product.store}</span>
            <span>{product.owner}</span>
          </div>
        </div>
        <RiskTag level={risk.level} />
        <Button className="clearance-sku-dialog__close" aria-label={"关闭 SKU 详情"} onClick={onClose}>×</Button>
      </div>

      <div className="clearance-sku-dialog__tabs">
        <Tabs
          activeKey={activeTab}
          onChange={key => setActiveTab(key as SkuDetailTab)}
          items={[
            {
              key: "business",
              label: "经营分析",
              children: <div className="clearance-sku-tab-content clearance-sku-business">
                <div className={`clearance-sku-alert clearance-sku-alert--${risk.level}`}>
                  <div className="clearance-sku-alert__icon">!</div>
                  <div className="clearance-sku-alert__text">
                    <strong>{riskMessages[0] || "当前暂无明显风险"}</strong>
                    <span>{riskMessages.slice(1).join("；") || "风险等级按当前清货规则展示，仅供运营参考。"}</span>
                  </div>
                  <Tag color={risk.level === "high" ? "error" : risk.level === "medium" ? "warning" : "success"}>{risk.level === "high" ? "需优先关注" : risk.level === "medium" ? "建议关注" : "正常观察"}</Tag>
                </div>

                <div className="clearance-sku-metric-groups">
                  <div className="clearance-sku-metric-group">
                    <div className="clearance-sku-metric"><span>WFS 可售库存</span><strong>{integer(product.avail)} <small>件</small></strong><em>当前可售</em></div>
                    <div className="clearance-sku-metric"><span>预计售罄天数</span><strong>{coverage(product) === null ? "—" : integer(coverage(product) as number)} <small>天</small></strong><em>按近30天销量估算</em></div>
                  </div>
                  <div className="clearance-sku-metric-group">
                    <div className="clearance-sku-metric"><span>可售库存成本</span><strong>{money(product.avail * product.cost)}</strong><em>{integer(product.avail)} 件 × {money(product.cost)}</em></div>
                    <div className="clearance-sku-metric"><span>上架天数</span><strong>{integer(product.listingDays)} <small>天</small></strong><em>当前上架时长</em></div>
                  </div>
                  <div className="clearance-sku-metric-group">
                    <div className="clearance-sku-metric"><span>Listing 评分</span><strong className={product.rating < data.rules.ratingThreshold ? "clearance-sku-value-negative" : ""}>{Number.isFinite(product.rating)?product.rating.toFixed(1):"—"} <small>/ 5</small></strong><em>{integer(product.reviewCount)} 条评价</em></div>
                    <div className="clearance-sku-metric"><span>30 天退货率</span><strong>{product.per[30].units > 0 ? percent(product.returns / product.per[30].units * 100) : "—"}</strong><em>30 天退货 {integer(product.returns)} 次</em></div>
                  </div>
                </div>

                <div className="clearance-sku-business-grid">
                  <Card className="clearance-sku-panel" title="经营数据对比" extra="近 7 / 14 / 30 天">
                    <Table
                      className="clearance-sku-period-table"
                      size="small"
                      pagination={false}
                      rowKey="key"
                      dataSource={periodRows}
                      columns={[
                        { title: "经营指标", dataIndex: "label", width: 150 },
                        ...([7, 14, 30] as const).map(days => ({ title: `${days} 天`, align: "right" as const, render: (_: unknown, row: { key: string }) => renderPeriodValue(row.key, days) })),
                      ]}
                    />
                  </Card>
                  <Card className="clearance-sku-panel clearance-sku-advice-panel" title="运营建议" extra="按现有数据给出提示">
                    <div className="clearance-sku-advice-list">
                      {advice.map((item, index) => <div className="clearance-sku-advice" key={item.title}>
                        <strong>{index === 0 ? "优先" : "其次"}：{item.title}</strong>
                        <p>{item.description}</p>
                      </div>)}
                    </div>
                  </Card>
                </div>
              </div>,
            },
            {
              key: "inventory",
              label: "库存与风险",
              children: <div className="clearance-sku-tab-content clearance-sku-inventory">
                <div className="clearance-sku-inventory-grid">
                  <Card className="clearance-sku-panel" title="商品与价格" extra="清货定价参考">
                    <div className="clearance-sku-kv-grid clearance-sku-kv-grid--reference">
  <div><span>商品 ID</span><strong>{product.item}</strong></div>
  <div><span>当前售价</span><strong>{money(product.price)}</strong></div>
  <div><span>划线价</span><strong>—</strong></div>
  <div><span>购物车</span><strong>—</strong></div>
  <div><span>单件采购成本</span><strong>{money(product.cost)}</strong></div>
  <div><span>单件毛利空间</span><strong>—</strong></div>
</div>

                  </Card>

                  <Card className="clearance-sku-panel" title="风险与清货申请" extra="清货决策依据"><div className="clearance-sku-risk-summary">
  <RiskTag level={risk.level}/>
  <span>{riskMessages[0] || "当前没有触发明显风险，建议继续关注库存变化。"}</span>
</div>
<div className="clearance-sku-kv-grid clearance-sku-kv-grid--compact">
  <div>
    <span>识别来源</span>
    <strong>
      <Tag color={data.manual.includes(product.id) ? "purple" : "blue"}>
        {data.manual.includes(product.id) ? "运营主动" : "系统识别"}
      </Tag>
    </strong>
  </div>
  <div>
    <span>申请状态</span>
    <strong>{activeTask ? STATUS_NAMES[activeTask.status] : "暂无申请"}</strong>
  </div>
</div>
<div className="clearance-sku-risk-note">
  风险等级沿用系统现有判定，不以清货测算结果重新评级。
</div>
{data.manual.includes(product.id) && eligible &&
  <Button danger size="small" onClick={onRemoveManual}>移出人工清货候选</Button>}
</Card>
                </div>

                <Card className="clearance-sku-panel clearance-sku-plan-panel" title="清货方案测算" extra="修改数量和售价，结果实时更新">
                  <div className="clearance-sku-plan-grid">
                    <div className="clearance-sku-plan-inputs">
                      <div className="clearance-sku-plan-field">
                        <label htmlFor="clearance-sku-quote-quantity">清货数量 <span>件</span></label>
                        <InputNumber id="clearance-sku-quote-quantity" aria-label={"清货数量"} min={0} max={product.avail} precision={0} value={safeQuantity} onChange={value => setQuantity(Math.max(0, Math.min(product.avail, Number(value ?? 0))))} />
                        <small>可调整范围：0 - {integer(product.avail)} 件</small>
                      </div>
                      <div className="clearance-sku-plan-field">
                        <label htmlFor="clearance-sku-quote-price">清货售价 <span>USD / 件</span></label>
                        <InputNumber id="clearance-sku-quote-price" aria-label={"清货售价"} min={0} precision={2} prefix="$" value={safePrice} onChange={value => setPrice(Math.max(0, Number(value ?? 0)))} />
                        <small>当前售价：{money(product.price)}</small>
                      </div>
                    </div>
                    <div className="clearance-sku-plan-results">
                      <div><span>预计销售回款（未扣费用）</span><strong>{money(estimatedRevenue)}</strong></div>
                      <div className="clearance-sku-result-pending"><span>预计清货盈亏</span><strong>待定义</strong></div>
                      <div><span>最低保本售价</span><strong>待定义</strong></div>
                      <div><span>清货后剩余库存</span><strong>{integer(remainingInventory)} 件</strong></div>
                    </div>
                  </div>
                  <div className="clearance-sku-measure-note">当前仅预览销售回款和剩余数量。平台费、WFS 履约费及其他成本口径尚未定义，因此暂不计算盈亏和保本价。修改此处不会修改商品售价、WFS 库存或申请数据。</div>
                </Card>
              </div>,
            },
          ]}
        />
      </div>

      <div className="clearance-sku-dialog__footer">
        <Button onClick={onClose}>关闭</Button>
        <Button type="primary" disabled={!eligible} onClick={onApply}>申请清货</Button>
      </div>
    </div>
  </Modal>;
}


// CLEARANCE_COMPLETE_V53: the execution log is sourced exclusively from the
// real application detail API. Never infer sales or history from Mock state.

// CLEARANCE_DETAIL_DISPLAY_V54
function formatClearanceTaskDateV54(value?: string | null): string {
  const raw = String(value ?? "").trim();
  if (!raw || raw === "—") return "—";

  if (/T/.test(raw) && /(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw)) {
    const parsed = new Date(raw);
    if (!Number.isNaN(parsed.getTime())) {
      const parts = new Intl.DateTimeFormat("en-US", {
        timeZone: "America/Los_Angeles",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).formatToParts(parsed);

      const year = parts.find(p => p.type === "year")?.value;
      const month = parts.find(p => p.type === "month")?.value;
      const day = parts.find(p => p.type === "day")?.value;

      if (year && month && day)
        return `${year}/${month}/${day}`;
    }
  }

  const d = raw.match(/^(\d{4})[-/](\d{2})[-/](\d{2})/);
  return d ? `${d[1]}/${d[2]}/${d[3]}` : "—";
}

type ClearanceTaskEventV53 = ApplicationDetail["events"][number];
const CLEARANCE_EVENT_LABELS_V53: Record<string, string> = {
  submitted: "提交清货申请", approved: "审批通过", running: "审批通过，开始执行",
  rejected: "审批驳回", cancelled: "撤销清货申请", done: "完成清货",
  stock_closed: "库存售罄，任务关闭", sales_reconciled: "销售数量已核对",
};
function clearanceEventV53(event: ClearanceTaskEventV53) {
  const note = event.detail_json?.["reason"];
  const reason = typeof note === "string" && note.trim() ? note.trim() : "";
  const label = CLEARANCE_EVENT_LABELS_V53[event.event_type] ?? `任务操作：${event.event_type}`;
  return {
    at: event.created_at || "",
    who: event.actor_ref || "系统",
    text: event.event_type === "done" && reason ? `${label} · ${reason}` : label,
  };
}

export function ClearanceDialogs({data,onChange,role,readOnly=false,applicant,setApplicant,manualOpen,setManualOpen,taskId,setTaskId,apply,setApply}:ModalsProps){
 const [manualSelection,setManualSelection]=useState<string[]>([]);
 const [manualWizardActive,setManualWizardActive]=useState(false);
 const [manualSearch,setManualSearch]=useState("");

 const [removeTarget,setRemoveTarget]=useState<string|null>(null);
 const [removeNote,setRemoveNote]=useState("");
 const [completeOpenV53,setCompleteOpenV53]=useState(false);
 const [completeNoteV53,setCompleteNoteV53]=useState("");
 const [completingV53,setCompletingV53]=useState(false);
 // Store only completed asynchronous responses; loading is derived from the
 // active task key, so opening or switching tasks needs no setState in an effect.
 const [taskEventsV53,setTaskEventsV53]=useState<{
   key:string; events:ClearanceTaskEventV53[]; error:boolean;
 }|null>(null);
 const [form]=Form.useForm<ApplyValues>();
 const [progressForm]=Form.useForm<{lines:Record<string,{sold:number;removed:number;disposed:number}>}>();
 const product=applicant?findProduct(applicant):undefined;
 const task=taskId?data.tasks.find(t=>t.id===taskId):undefined;
const taskProductV7 = task ? findProduct(task.lines[0]?.id) : undefined;
 const taskCompletedV7 = task ? taskSold(task) + taskRemoved(task) : 0;
 const taskRemainingV7 = task ? Math.max(0, taskQty(task) - taskCompletedV7) : 0;
 const taskVersionV53 = task?.version;
 const taskEventsKeyV53 = taskId ? `${taskId}:${taskVersionV53 ?? "unknown"}` : null;
 useEffect(()=>{
   if(!taskId || !taskEventsKeyV53)return;
   let active=true;
   // No synchronous state update here: the previous response is ignored by
   // its task/version key until this asynchronous request has completed.
   void getClearanceApplication(taskId).then(detail=>{
     if(!active)return;
     if(detail.application?.id!==taskId || !Array.isArray(detail.events))
       throw new Error("清货详情不匹配或事件列表缺失");
     setTaskEventsV53({key:taskEventsKeyV53,events:detail.events,error:false});
   }).catch(error=>{
     if(!active)return;
     console.warn("Clearance execution history load failed",error);
     setTaskEventsV53({key:taskEventsKeyV53,events:[],error:true});
   });
   return ()=>{active=false;};
 },[taskId,taskEventsKeyV53]);
 const eventsCurrentV53 = Boolean(taskEventsKeyV53 && taskEventsV53?.key === taskEventsKeyV53);
 const eventsLoadingV53 = Boolean(taskEventsKeyV53 && !eventsCurrentV53);
 const eventsErrorV53 = Boolean(eventsCurrentV53 && taskEventsV53?.error);
 const taskHistoryV53 = eventsCurrentV53 && !eventsErrorV53
   ? taskEventsV53?.events.map(clearanceEventV53) ?? [] : [];
 const taskLatestV7 = taskHistoryV53[taskHistoryV53.length - 1];
 const taskApprovalV7 = !task ? "—" :
   ["ready","running","paused","done"].includes(task.status)
     ? "已通过" : STATUS_NAMES[task.status];
 const confirmCompleteV53=async()=>{
   if(!task || task.status!=="running" || completingV53)return;
   setCompletingV53(true);
   try {
     const result=await completeClearanceApplication(task.id,completeNoteV53.trim());
     if(result.id!==task.id || result.status!=="done")
       throw new Error("完成接口返回的任务 ID 或状态不匹配");
     setCompleteOpenV53(false);
     setCompleteNoteV53("");
     setTaskId(null);
     window.dispatchEvent(new Event("szzsbj-clearance-application-updated"));
     void message.success("清货任务已完成，实际销量保持原值");
   } catch (error) {
     console.warn("Clearance manual completion failed",error);
     void message.error("完成清货失败，请确认操作权限及任务是否仍在执行中");
   } finally {
     setCompletingV53(false);
   }
 };
 const change=(patch:Partial<StoredClearance>)=>{if(readOnly){void message.warning("当前仅开放真实清货数据查询");return;}onChange({...data,...patch});};
 const begin=(ids:string[],source:"auto"|"manual",editId?:string,preserveSelection=false)=>{
  if(!ids.length)return;
  const ps=ids.map(findProduct);
  if(ps.some(x=>!x)){void message.error("未找到商品 ID");return;}
  if(new Set(ps.map(x=>x?.store)).size!==1){void message.error("同一清货申请仅允许同一店铺的 SKU");return;}
  if(!preserveSelection)setManualSelection([]);setApply({ids,source,editId});setApplicant(null);setTaskId(null);
 };
 const closeApply=()=>{
  setApply(null);
  setManualOpen(false);
  setManualWizardActive(false);
  setManualSelection([]);
  setManualSearch("");
  form.resetFields();
 };
 const previousManualStep=()=>setManualOpen(true);

 const old=apply?.editId?data.tasks.find(x=>x.id===apply.editId):undefined;
 const applyProducts=apply?.ids.map(findProduct).filter((x):x is ClearanceProduct=>Boolean(x))??[];
const reasonAliases: Record<string,string> = {
  "库存滞销":"长期滞销",
  "WFS库龄过高":"仓储成本压力",
  "季节性清仓":"季节性商品过季",
  "产品升级换代":"商品计划停售",
  "准备停售":"商品计划停售",
  "质量问题":"质量或售后问题",
  "经营策略调整":"其他原因",
 };

 const initialReason = old?.reason
  ? reasonAliases[old.reason] ?? old.reason
  : undefined;

 const reasonOptions = [
  ...REASONS.map(x=>({label:x,value:x})),
  ...(initialReason&&!REASONS.includes(initialReason)
    ? [{label:initialReason,value:initialReason}]
    : [])
 ];

 const watchedQuantities = Form.useWatch(
  "quantities",form
 ) as Record<string,number>|undefined;

 // 沿用原申请表单的50%默认数量，不新增清货算法
 const recommendedQuantity = (x:ClearanceProduct) =>
  Math.max(1,Math.min(300,x.avail,Math.floor(x.avail*.5)));

 const quantityFor = (x:ClearanceProduct) => {
  const fallback = old?.lines.find(l=>l.id===x.id)?.qty
   ?? recommendedQuantity(x);
  const value = watchedQuantities?.[x.id] ?? fallback;
  return Math.max(0,Math.min(x.avail,Number(value)||0));
 };

 const totalAvailable = applyProducts.reduce(
  (sum,x)=>sum+x.avail,0
 );

 const totalPlannedQuantity = applyProducts.reduce(
  (sum,x)=>sum+quantityFor(x),0
 );

 const totalRecommended = applyProducts.reduce(
  (sum,x)=>sum+recommendedQuantity(x),0
 );

 const totalTargetCost = applyProducts.reduce(
  (sum,x)=>sum+quantityFor(x)*x.cost,0
 );

 const remainingAvailable = Math.max(
  0,totalAvailable-totalPlannedQuantity
 );

 const coveragePercent = totalAvailable>0
  ? Math.min(100,Math.round(totalPlannedQuantity/totalAvailable*100))
  : 0;
 const submit=async (values:ApplyValues)=>{
  if(!apply || applyProducts.length!==1){void message.error("一次只能申请一个WFS商品");return;}
  const selected=applyProducts[0];
  const identity=selected.id.split("::");
  if(identity.length!==3 || identity.some(x=>!x)){
    void message.error("仅支持真实WFS商品ID；演示数据不可提交审批");return;
  }
  const [source_account_ref,store_id,item_id]=identity;
  const requested=Number(values.quantities?.[selected.id]);
  if(!Number.isInteger(requested)||requested<1){void message.error("清货数量必须为正整数");return;}
  const methods=values.methods??[];
  if(!methods.length || methods.some(x=>!(["降价","广告清货"].includes(x)))){
    void message.error("清货方式只支持降价、广告清货");return;
  }
  try{
    const latest=await getClearanceListing({source_account_ref,store_id,item_id});
    if(!latest.available||latest.available<1){void message.error("WFS可售库存不足");return;}
    const qty=Math.min(requested,latest.available);
    if(qty!==requested)void message.info(`最新WFS库存为${qty}件，目标清货数量已自动调整`);
    await submitClearanceApplication({
      source_account_ref,store_id,item_id,qty,
      reason:values.reason,methods,note:values.remark?.trim()??"",
      planned_completion_date:values.due?.format("YYYY-MM-DD"),
    });
    closeApply();
    void message.success("清货申请已提交至统一审批工作台");
    window.dispatchEvent(new Event("szzsbj-clearance-application-updated"));
  }catch(error){
    // CLEARANCE_EXPLICIT_REJECTION_V57: only display real backend reasons.
    const errors:Record<string,string> = {
      CLEARANCE_LISTING_ARCHIVED:"该商品已归档，无法申请清货。请在Listing管理查看归档原因",
      CLEARANCE_STOCK_UNKNOWN:"当前无法确认WFS可售库存，请刷新数据后再申请",
      CLEARANCE_OUT_OF_STOCK:"当前WFS可售库存为0，无法申请清货",
      CLEARANCE_QUANTITY_EXCEEDED:"申请数量超过最新WFS可售库存，请刷新并调整数量",
      CLEARANCE_DUPLICATE_APPLICATION:"该商品已有待审批或执行中的清货申请，不能重复提交",
      FORBIDDEN:"当前账号没有该商品的清货申请权限",
      DATA_SCOPE_DENIED:"当前账号无法访问该店铺的商品",
      INVALID_REQUEST:"申请未通过后端校验，请确认商品归档状态、库存及重复申请",
    };
    const code = error instanceof BackendRequestError ? error.code ?? "" : "";
    void message.error(errors[code] ?? (code ? `清货申请失败（${code}），请核对数据后重试` : "清货申请失败，请检查网络或联系管理员"));
  }
 };
 const taskProgressSave=(values:{lines:Record<string,{sold:number;removed:number;disposed:number}>})=>{
  if(readOnly){void message.warning("当前仅开放真实清货数据查询");return;}
  if(!task||task.status!=="running"||task.owner!==role)return;
  const lines=task.lines.map(row=>({...row,...values.lines?.[row.id]}));
  for(const line of lines){
   const before=task.lines.find(x=>x.id===line.id)!;
   const nums=[line.sold,line.removed,line.disposed];
   if(nums.some((n,i)=>!Number.isInteger(n)||n<[before.sold,before.removed,before.disposed][i])||nums.reduce((a,b)=>a+b,0)>line.qty){void message.error("累计进度不得倒退、不得超过目标量，必须为整数");return;}
  }
  change({tasks:data.tasks.map(x=>x.id===task.id?{...x,lines,history:[...x.history,{at:chinaNow(),who:role,text:"更新累计执行进度"}]}:x)});
  setProgressOpen(false);void message.success("执行进度已保存（Mock）");
 };
 const [progressOpen,setProgressOpen]=useState(false);
 const selectables=CLEARANCE_PRODUCTS.filter(x=>
  [x.name,x.sku,x.item,x.msku].some(v=>
   String(v??"").toLowerCase().includes(manualSearch.trim().toLowerCase())
  )
 );
 const selectedProduct=manualSelection[0]?findProduct(manualSelection[0]):undefined;
 const eligible=(x:ClearanceProduct)=>Boolean(x);

 const manualFlow=manualOpen||(manualWizardActive&&apply?.source==="manual");
 const manualStep2=!manualOpen&&manualWizardActive&&apply?.source==="manual";
 const manualProductColumns:ColumnsType<ClearanceProduct>=[
  {title:"商品",width:460,render:(_,x)=>{
   const why="";
   return <div className="clearance-wizard-product">
    <span className="clearance-wizard-thumb">▦</span>
    <div className="clearance-wizard-product-text">
     <strong title={x.name}>{x.name}</strong>
     <small>{x.sku} · {x.msku}</small>
     {why&&<small className="clearance-wizard-blocked">{why}</small>}
    </div>
   </div>;
  }},
  {title:"WFS 可售",width:110,render:(_,x)=><div className="clearance-wizard-meta"><small>WFS 可售</small><strong>{x.avail.toLocaleString("en-US")} 件</strong></div>},
  {title:"当前售价",width:110,render:(_,x)=><div className="clearance-wizard-meta"><small>当前售价</small><strong>{money(x.price)}</strong></div>},
  {title:"风险",width:90,render:(_,x)=><RiskTag level={evaluateProduct(x,data.rules).level}/>},
  {title:"操作",width:124,render:(_,x)=>{
   // Existing tasks do not prohibit a new application.
   if(!eligible(x))return <Button size="small" disabled>不可申请</Button>;
   const chosen=manualSelection[0]===x.id;
   return <Button size="small" className={chosen?"clearance-wizard-select is-selected":"clearance-wizard-select"}
    onClick={()=>setManualSelection([x.id])}>{chosen?"已选择":"选择商品"}</Button>;
  }}
 ];
 const nextManual=()=>{
  const x=selectedProduct;
  if(!x){void message.warning("请先选择一个 SKU");return;}
  if(!eligible(x)){void message.error("该 SKU 不符合申请条件");return;}
  const same=apply?.source==="manual"&&apply.ids.length===1&&apply.ids[0]===x.id;
  if(!same){
   form.resetFields();
   begin([x.id],"manual",undefined,true);
  }
  // One React event changes panes; Modal never closes.
  setManualWizardActive(true);
  setManualOpen(false);
 };

 return <>
  {product && <SkuDeepAnalysisModal key={product.id + ":" + product.avail + ":" + product.price}
    product={product}
    data={data}
    role={role}
    onClose={() => setApplicant(null)}
    onApply={() => begin([product.id], data.manual.includes(product.id) ? "manual" : "auto")}
    onRemoveManual={() => setRemoveTarget(product.id)}
  />}

  <Modal
    rootClassName={manualFlow?"clearance-apply-modal clearance-wizard-modal":"clearance-apply-modal"}
    title={manualFlow?(
 <div className="clearance-apply-modal-title clearance-wizard-title">
  <span>CLEARANCE APPLICATION</span>
  <strong>主动申请 SKU</strong>
  <small>选择一个商品，填写清货申请信息</small>
  <div className="clearance-wizard-steps">
   <div className={manualOpen?"clearance-wizard-step active":"clearance-wizard-step done"}><b>1</b>选择商品</div>
   <div className={manualStep2?"clearance-wizard-step active":"clearance-wizard-step"}><b>2</b>填写申请</div>
  </div>
 </div>
):(<div className="clearance-apply-modal-title">
        <span>WFS CLEARANCE REQUEST</span>
        <strong>{old?"补充资料并重新提交":"提交 WFS 清货申请"}</strong>
        <small>完善清货计划与执行说明，核对库存影响后提交申请</small>
      </div>)}
    width={manualFlow?1072:"min(1280px, 92vw)"}
    centered
    open={manualOpen||Boolean(apply)}
    onCancel={closeApply}
    footer={manualFlow?(
 <div className="clearance-wizard-actions">
  <Button onClick={closeApply}>取消</Button>
  {manualOpen?(
   <Button type="primary" disabled={!selectedProduct||!eligible(selectedProduct)} onClick={nextManual}>下一步</Button>
  ):(<>
   <Button onClick={previousManualStep}>上一步</Button>
   <Button type="primary" onClick={()=>form.submit()}>提交申请</Button>
  </>)}
 </div>
):null}
    destroyOnHidden
    styles={{body:{padding:0,display:"flex",flexDirection:"column",minHeight:0}}}
  >
{/* PR285_ONE_MODAL_IN_PLACE_20261103 */}
  {manualFlow&&(
   <div className="clearance-wizard-pane" style={{display:manualOpen?"flex":"none"}}>
    <div className="clearance-wizard-rowtitle"><strong>选择清货商品</strong><small>一次仅能申请一个 SKU</small></div>
    <div className="clearance-wizard-search">
     <Input.Search allowClear placeholder="搜索商品名称、SKU、MSKU 或 ASIN"
      value={manualSearch} onChange={e=>setManualSearch(e.target.value)}/>
     <small>支持模糊搜索</small>
    </div>
    <Table<ClearanceProduct> rowKey="id" className="clearance-wizard-table"
     showHeader={false} size="small" tableLayout="fixed"
     dataSource={selectables} columns={manualProductColumns} pagination={false}
     scroll={{y:400}}
     rowClassName={x=>manualSelection[0]===x.id?"clearance-wizard-chosen":!eligible(x)?"clearance-wizard-ineligible":""}/>
   </div>
  )}
  <div className="clearance-wizard-existing-form" style={{display:manualOpen?"none":"flex"}}>

    <div className="clearance-apply-body">
      <div className="clearance-apply-content">

        <div className="clearance-apply-product-summary">
          <div className="clearance-apply-product-identity">
            <div className="clearance-apply-product-icon">▧</div>
            <div>
              <strong>
                {applyProducts.length===1
                  ? applyProducts[0]?.name
                  : "本次申请包含 "+applyProducts.length+" 个 SKU"}
              </strong>
              <span>
                {applyProducts.length===1
                  ? "SKU："+applyProducts[0]?.sku+"　MSKU："+applyProducts[0]?.msku
                  : applyProducts.map(x=>x.sku).join("、")}
              </span>
            </div>
          </div>

          <div className="clearance-apply-summary-metric">
            <span>WFS 可售</span>
            <strong>{integer(totalAvailable)} 件</strong>
          </div>

          <div className="clearance-apply-summary-metric">
            <span>{applyProducts.length===1?"单件库存成本":"SKU 数量"}</span>
            <strong>
              {applyProducts.length===1
                ? money(applyProducts[0]?.cost??0)
                : applyProducts.length+" 个"}
            </strong>
          </div>

          <div className="clearance-apply-summary-metric">
            <span>系统建议数量</span>
            <strong>{integer(totalRecommended)} 件</strong>
          </div>
        </div>

        <Form
          form={form}
          layout="vertical"
          className="clearance-apply-form"
          onFinish={submit}
          key={apply?.ids.join(",")+":"+(old?.id??"new")}
          initialValues={{
            reason:initialReason,
            methods:old?.methods?.map(method=>
              method==="广告调整"?"广告清货":
              method==="WFS移除"?"WFS 移除":method
            )??[],
            remark:old?.remark??"",
            due:dayjs(old?.due??chinaToday()),
            quantities:Object.fromEntries(
              applyProducts.map(x=>[
                x.id,
                old?.lines.find(l=>l.id===x.id)?.qty??recommendedQuantity(x)
              ])
            )
          }}
        >

          <div className="clearance-apply-layout">

            <Card
              className="clearance-apply-plan-card"
              title="清货计划"
              extra={<span>带 * 的项目为必填</span>}
            >

              <div className="clearance-apply-fields">

                <Form.Item
                  name="reason"
                  label="清货原因"
                  rules={[{required:true,message:"请选择清货原因"}]}
                >
                  <Select
                    size="large"
                    placeholder="请选择清货原因"
                    options={reasonOptions}
                  />
                </Form.Item>

                <Form.Item
                  name="due"
                  label="计划完成日期"
                  rules={[{required:true,message:"请选择计划完成日期"}]}
                >
                  <DatePicker
                    size="large"
                    style={{width:"100%"}}
                    format="YYYY/MM/DD"
                    disabledDate={current=>
                      Boolean(current&&current.isBefore(dayjs(chinaToday()),"day"))
                    }
                  />
                </Form.Item>

              </div>

              <div className="clearance-apply-quantity-section">
                <div className="clearance-apply-section-label">
                  <span className="required-mark">*</span>
                  计划清货数量
                </div>

                {applyProducts.map(x=>(
                  <div className="clearance-apply-quantity-row" key={x.id}>

                    {applyProducts.length>1&&(
                      <div className="clearance-apply-quantity-product">
                        <strong>{x.name}</strong>
                        <span>{x.sku} · WFS 可售 {integer(x.avail)} 件</span>
                      </div>
                    )}

                    <div className="clearance-apply-quantity-controls">

                      <Button
                        htmlType="button"
                        aria-label={"减少 "+x.sku+" 清货数量"}
                        onClick={()=>form.setFieldValue(
                          ["quantities",x.id],
                          Math.max(1,quantityFor(x)-1)
                        )}
                      >−</Button>

                      <Form.Item
                        name={["quantities",x.id]}
                        noStyle
                        rules={[{required:true,message:"请输入清货数量"}]}
                      >
                        <InputNumber
                          size="large"
                          controls={false}
                          min={1}
                          max={x.avail}
                          precision={0}
                          style={{width:"100%"}}
                          aria-label={"计划清货数量 "+x.sku}
                        />
                      </Form.Item>

                      <Button
                        htmlType="button"
                        aria-label={"增加 "+x.sku+" 清货数量"}
                        onClick={()=>form.setFieldValue(
                          ["quantities",x.id],
                          Math.min(x.avail,quantityFor(x)+1)
                        )}
                      >+</Button>

                    </div>

                    <Button
                      htmlType="button"
                      className="clearance-apply-recommended"
                      onClick={()=>form.setFieldValue(
                        ["quantities",x.id],
                        recommendedQuantity(x)
                      )}
                    >
                      使用建议数量
                    </Button>

                    <div className="clearance-apply-field-hint">
                      可手动调整，不超过 WFS 可售库存 {integer(x.avail)} 件
                      · 建议 {integer(recommendedQuantity(x))} 件
                    </div>

                  </div>
                ))}

              </div>

              <Divider/>

              <Form.Item
                name="methods"
                label={<span>清货方式 <span className="clearance-apply-multiple-hint">可多选</span></span>}
                rules={[{required:true,type:"array",min:1,message:"请选择至少一种清货方式"}]}
              >
                <Checkbox.Group
                  className="clearance-apply-methods"
                  options={METHODS.filter(x=>x==="降价"||x==="广告清货").map(x=>({label:x,value:x}))}
                />
              </Form.Item>

              <Form.Item
                name="remark"
                label="申请说明"
                rules={[
                  {required:true,whitespace:true,message:"请输入申请说明"},
                  {max:500,message:"申请说明不能超过500字"}
                ]}
              >
                <Input.TextArea
                  rows={4}
                  maxLength={500}
                  showCount
                  placeholder="说明计划采用的清货措施、预计执行安排及申请原因……"
                />
              </Form.Item>

            </Card>

            <Card
              className="clearance-apply-preview-card"
              title="库存影响预览"
              extra={<span>随计划清货数量自动更新</span>}
            >

              <div className="clearance-apply-cost-highlight">
                <span>目标库存成本</span>
                <strong>{money(totalTargetCost)}</strong>
                <small>计划清货数量 × 单件库存成本</small>
              </div>

              <div className="clearance-apply-preview-row">
                <span>计划清货数量</span>
                <strong>{integer(totalPlannedQuantity)} 件</strong>
              </div>

              <div className="clearance-apply-preview-row">
                <span>清货覆盖比例</span>
                <strong>{coveragePercent}%</strong>
              </div>

              <div className="clearance-apply-preview-row">
                <span>清货后可售库存</span>
                <strong className="clearance-apply-remaining">
                  {integer(remainingAvailable)} 件
                </strong>
              </div>

              <Progress
                percent={coveragePercent}
                showInfo={false}
                strokeColor="#1677ff"
                trailColor="#e7edf6"
              />

              <div className="clearance-apply-progress-labels">
                <span>计划清货</span>
                <span>剩余库存</span>
              </div>

              <div className="clearance-apply-measure-note">
                <strong>测算说明</strong>
                <p>
                  目标库存成本表示本次计划涉及的库存成本，
                  不等于预计回款或实际清货盈亏。
                </p>
              </div>

            </Card>

          </div>
        </Form>
      </div>

      <div className="clearance-apply-footer">
        <span>请核对商品、数量、处理方式及完成日期</span>
        <Space size={12}>
          <Button size="large" onClick={closeApply}>取消</Button>
          <Button size="large" type="primary" onClick={()=>form.submit()}>
            {old?"重新提交申请":"提交申请"}
          </Button>
        </Space>
      </div>
    </div>

  </div>
  </Modal>

  <Modal
  rootClassName="clearance-task-detail-v7-modal"
  title={null}
  width="calc(100vw - 32px)"
  centered
  open={Boolean(task)}
  onCancel={()=>setTaskId(null)}
  footer={null}
  closable={false}
  destroyOnHidden
  styles={{body:{padding:0,overflow:"hidden"}}}
>
{task&&<div className="clearance-task-detail-v7">

  <header className="task-v7-header">
    <div className="task-v7-eyebrow">CLEARANCE TASK · TASK DETAIL</div>

    <div className="task-v7-title-row">
      <strong>{taskProductV7?.name??"清货任务"}</strong>
      <Tag color={
        task.status==="running"?"warning":
        task.status==="done"?"success":
        task.status==="rejected"?"error":
        task.status==="ready"?"processing":"default"
      }>
        {STATUS_NAMES[task.status]}
      </Tag>
    </div>

    <div className="task-v7-meta">
      <span>任务编号：<b>{task.id}</b></span>
      <span>·</span>
      <span>{taskProductV7?.sku??"—"}</span>
      {task.lines.length>1?<span>等 {task.lines.length} 个 SKU</span>:null}
      <span>·</span>
      <span>{taskStore(task)||"—"}</span>
      <span>·</span>
      <span>负责人：{task.owner}</span>
    </div>

    <Button
      className="task-v7-close-icon"
      aria-label="关闭"
      onClick={()=>setTaskId(null)}
    >
      ×
    </Button>
  </header>

  <div className="task-v7-summary">

    <div className="task-v7-summary-item">
      <span>任务状态</span>
      <StatusTag status={task.status}/>
    </div>

    <div className="task-v7-summary-item">
      <span>申请数量</span>
      <strong>{taskQty(task).toLocaleString("en-US")}<small> 件</small></strong>
    </div>

    <div className="task-v7-summary-item">
      <span>已完成数量</span>
      <strong className="green">{taskCompletedV7.toLocaleString("en-US")}<small> 件</small></strong>
    </div>

    <div className="task-v7-summary-item">
      <span>剩余数量</span>
      <strong className="orange">{taskRemainingV7.toLocaleString("en-US")}<small> 件</small></strong>
    </div>

    <div className="task-v7-summary-item progress-item">
      <span>整体完成进度</span>
      <strong>{taskProgress(task)}%</strong>
      <Progress percent={taskProgress(task)} showInfo={false} strokeWidth={5}/>
    </div>

  </div>

  <div className="task-v7-body">

    <main className="task-v7-main">

      <section className="task-v7-panel task-v7-application">
        <header className="task-v7-panel-head">
          <strong>申请信息</strong>
          <span>申请提交后内容只读</span>
        </header>

        <div className="task-v7-info-grid">

          <div className="task-v7-info-item">
            <span>清货原因</span>
            <strong>{task.reason}</strong>
          </div>

          <div className="task-v7-info-item">
            <span>申请人</span>
            <strong>{task.requester}</strong>
          </div>

          <div className="task-v7-info-item">
            <span>申请时间</span>
            <strong>{formatClearanceTaskDateV54(task.submitted)}</strong>
          </div>

          <div className="task-v7-info-item">
            <span>清货方式</span>
            <div className="task-v7-methods">
              {task.methods.map(method=>
                <Tag key={method} color="blue">{method}</Tag>
              )}
            </div>
          </div>

          <div className="task-v7-info-item">
            <span>计划完成日期</span>
            <strong>{formatClearanceTaskDateV54(task.due)}</strong>
          </div>

          <div className="task-v7-info-item">
            <span>审批结果</span>
            <div>
              <Tag color={
                taskApprovalV7==="已通过"?"success":
                task.status==="rejected"?"error":"warning"
              }>
                {taskApprovalV7}
              </Tag>
              {taskApprovalV7==="已通过"
                ?<small className="task-v7-approval-source">审批工作台</small>
                :null}
            </div>
          </div>

          <div className="task-v7-info-item full">
            <span>申请说明</span>
            <strong>{task.remark||"—"}</strong>
          </div>

        </div>
      </section>

      <section className="task-v7-panel task-v7-execution">
        <header className="task-v7-panel-head">
          <strong>执行进度</strong>
          <span>各清货方式共同完成一单申请数量，不单独分配</span>
        </header>

        <div className="task-v7-table">

          <div className="task-v7-table-head">
            <span>清货方式</span>
            <span>执行内容</span>
            <span>当前状态</span>
            <span>最近更新</span>
            <span>明细</span>
          </div>

          {task.methods.map((method,index)=>(
            <div className="task-v7-table-row" key={`${method}-${index}`}>

              <strong>{method}</strong>

              <span className="task-v7-description">
                {method==="降价"
                  ?"按申请方案调整商品售价，跟踪实际订单售出情况"
                  :method==="促销"
                  ?"按申请方案执行促销，跟踪实际成交情况"
                  :method==="广告调整"
                  ?"按申请方案调整广告，跟踪归因成交情况"
                  :method==="WFS移除"
                  ?"按申请方案处理 WFS 移除，核对仓库处理结果"
                  :method==="弃置"
                  ?"按申请方案处理弃置，核对最终处理结果"
                  :"按申请方案执行清货，持续跟踪处理结果"
                }
              </span>

              <span>
                <Tag color={
                  task.status==="running"?"warning":
                  task.status==="done"?"success":
                  task.status==="rejected"?"error":"default"
                }>
                  {STATUS_NAMES[task.status]}
                </Tag>
              </span>

              <span className="task-v7-time">
                {formatClearanceTaskDateV54(taskLatestV7?.at)}
              </span>

              <Button
                type="link"
                size="small"
                onClick={()=>{
                  document.getElementById("task-v7-operation-record")
                    ?.scrollIntoView({behavior:"smooth",block:"nearest"});
                }}
              >
                查看
              </Button>

            </div>
          ))}

          {task.methods.length===0?
            <div className="task-v7-empty">暂无清货方式</div>:null}

        </div>

        <div className="task-v7-note">
          完成数量按实际订单售出、移除及弃置数量统计；最近更新展示整单最近操作记录，不代表各方式独立进度。
        </div>

      </section>

    </main>

    <aside
      id="task-v7-operation-record"
      className="task-v7-panel task-v7-timeline"
    >
      <header className="task-v7-panel-head">
        <strong>操作记录</strong>
        <span>按时间倒序记录</span>
      </header>

      <div className="task-v7-timeline-list">

        {[...taskHistoryV53].reverse().map((entry,index)=>(
          <div className="task-v7-timeline-item" key={`${entry.at}-${index}`}>
            <i className={
              entry.text.includes("提交")?"pending":"success"
            }/>

            <div>
              <strong>{entry.text}</strong>
              <small>{formatClearanceTaskDateV54(entry.at)} · {entry.who}</small>
            </div>
          </div>
        ))}

        {eventsLoadingV53?<div className="task-v7-empty">正在读取真实操作记录…</div>:null}
        {!eventsLoadingV53&&eventsErrorV53?
          <div className="task-v7-empty">操作记录读取失败，请关闭后重新打开任务详情</div>:null}
        {!eventsLoadingV53&&!eventsErrorV53&&taskHistoryV53.length===0?
          <div className="task-v7-empty">暂无操作记录</div>:null}

      </div>
    </aside>

  </div>

  <footer className="task-v7-footer">
    <span>审批在独立审批工作台完成；执行中的任务可经权限校验后人工完成。</span>
    <Space size={12}>
      <Button onClick={()=>setTaskId(null)} disabled={completingV53}>关闭</Button>
      {task.status==="running"&&!readOnly&&
        <Button type="primary" className="task-v7-complete-action" disabled={completingV53} onClick={()=>{setCompleteNoteV53("");setCompleteOpenV53(true);}}>
          完成清货
        </Button>}
    </Space>
  </footer>

</div>}
</Modal>
  <Modal
    title="确认完成清货"
    open={completeOpenV53&&task?.status==="running"}
    centered
    destroyOnHidden
    maskClosable={!completingV53}
    closable={!completingV53}
    onCancel={()=>{if(!completingV53){setCompleteOpenV53(false);setCompleteNoteV53("");}}}
    onOk={()=>{void confirmCompleteV53();}}
    okText="确认完成"
    okButtonProps={{loading:completingV53}}
    cancelButtonProps={{disabled:completingV53}}
  >
    <Form layout="vertical">
      <Form.Item label="完成说明（选填）" style={{marginBottom:0}}>
        <Input.TextArea
          value={completeNoteV53}
          onChange={event=>setCompleteNoteV53(event.target.value)}
          maxLength={4000}
          showCount
          rows={3}
          style={{resize:"none"}}
          placeholder="请输入完成说明"
        />
      </Form.Item>
    </Form>
  </Modal>
  <Modal title="更新累计清货执行进度" width={800} open={progressOpen} onCancel={()=>setProgressOpen(false)} onOk={()=>progressForm.submit()} okText="保存执行进度" destroyOnHidden>
   <Typography.Paragraph type="secondary">只记录 Mock 进度；各 SKU 的销售、移除、弃置总和不可超过目标，累计数值不得回退。</Typography.Paragraph>
   <Form form={progressForm} onFinish={taskProgressSave} layout="vertical">{task?.lines.map(l=><Card size="small" key={l.id} title={findProduct(l.id)?.sku+" · 目标 "+l.qty+"件"}><div className="clearance-progress-fields">{(["sold","removed","disposed"] as const).map((k,i)=><Form.Item key={k} label={["已销售","已移除","已弃置"][i]} name={["lines",l.id,k]}><InputNumber min={l[k]} max={l.qty} precision={0}/></Form.Item>)}</div></Card>)}</Form>
  </Modal>
  <Modal title="移出人工清货候选" open={Boolean(removeTarget)} onCancel={()=>{setRemoveTarget(null);setRemoveNote("");}} okText="确认移出" okButtonProps={{danger:true}} onOk={()=>{
    const x=removeTarget?findProduct(removeTarget):undefined;
    if(!x||!removeNote.trim()||x.owner!==role||activeTaskFor(data.tasks,x.id)){
      void message.error("原因必填，且只能移出本人无有效任务的 SKU");return;
    }
    change({manual:data.manual.filter(id=>id!==removeTarget)});
    setRemoveTarget(null);setRemoveNote("");void message.success("已移出人工候选（仅 Mock，不删除申请历史）");
  }}><Typography.Paragraph type="secondary">不会删除申请历史或改变库存；有有效清货任务的 SKU 不可移出。</Typography.Paragraph><Input.TextArea value={removeNote} onChange={e=>setRemoveNote(e.target.value)} placeholder="请填写移出原因" rows={3}/></Modal>
 </>;
}

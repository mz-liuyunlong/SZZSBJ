// CLEARANCE_APPROVAL_V34_STYLE_BRIDGE
/** Real clearance approval within the previously accepted full-width V3 visual shell.
 * Reuses DemoApprovalDrawer.css for presentation ONLY; never uses demo records
 * or demo decision state.  All decisions call the live clearance endpoint.
 */
import { Button, Drawer, Input, Modal, Spin, Table, Tag, message } from "antd";
import { useEffect, useState, type ReactNode } from "react";
import type { ApprovalItem } from "../approvalTypes";
import {
  getClearanceApplication, reviewClearanceApplication,
  type ApplicationDetail, type ClearanceListing, type ClearanceApplication,
} from "@/pages/products/clearance/clearanceApi";
import "./DemoApprovalDrawer.css";

type Action = "approved" | "rejected";
type Props = { selected?: ApprovalItem; onClose(): void; onUpdated(): void; directReviewAction?: Action };
type Metric = string | number | boolean | null | string[];
type CurrentDisplay = ClearanceListing & {
  strike_price_amount?: string | number | null;
  buybox_status?: string | null;
  unit_inventory_cost_usd?: string | number | null;
  capital_purchase_first_leg_usd?: string | number | null;
  unit_gross_margin_usd?: string | number | null;
};
type ApplicationDisplay = ClearanceApplication & {
  local_name?: string | null;
  product_name?: string | null;
  owner_name?: string | null;
  strike_price_amount?: string | number | null;
  buybox_status?: string | null;
  unit_inventory_cost_usd?: string | number | null;
};
type SubmissionSuggestion = NonNullable<ApplicationDetail["submission_suggestion"]>;
const numberOrNull = (v: unknown): number | null => {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string" && v.trim()) {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
};
const firstText = (...values: unknown[]): string | null => {
  for (const value of values) if (typeof value === "string" && value.trim()) return value.trim();
  return null;
};
const nonnegative = (v: unknown): number | null => {
  const n = numberOrNull(v);
  return n !== null && n >= 0 ? n : null;
};
const inventoryUnitCost = (row: CurrentDisplay, a: ApplicationDisplay): number | null => {
  const unit = nonnegative(row.unit_inventory_cost_usd) ??
    nonnegative(metric(row,"inventory_unit_cost_usd")) ??
    nonnegative(metric(row,"unit_inventory_cost_usd")) ??
    nonnegative(a.unit_inventory_cost_usd);
  if (unit !== null) return unit;
  const purchase = nonnegative(metric(row,"purchase_unit_cost_usd"));
  const firstLeg = nonnegative(metric(row,"first_leg_unit_cost_usd"));
  return purchase !== null && firstLeg !== null ? purchase + firstLeg : null;
};
const inventoryCapital = (row: CurrentDisplay, unit: number | null): number | null => {
  const saved = nonnegative(row.capital_purchase_first_leg_usd) ?? nonnegative(metric(row,"capital_purchase_first_leg_usd"));
  if (saved !== null) return saved;
  const available = nonnegative(row.available);
  return unit !== null && available !== null ? unit * available : null;
};
const unitMargin = (row: CurrentDisplay): number | null => {
  const margin = numberOrNull(row.unit_gross_margin_usd) ?? numberOrNull(metric(row,"unit_margin_usd"));
  if (margin !== null) return margin;
  const price = nonnegative(row.price_amount);
  const full = nonnegative(metric(row,"full_sale_unit_cost_usd")) ?? nonnegative(metric(row,"unit_full_sale_cost_usd"));
  return price !== null && full !== null ? price - full : null;
};
const businessName = (row: CurrentDisplay, a: ApplicationDisplay): string =>
  firstText(row.product_name, row.local_name, a.product_name, a.local_name, a.title) ?? a.item_id;
const businessOwner = (row: CurrentDisplay, a: ApplicationDisplay): string =>
  firstText(row.owner_name, a.owner_name, row.owner, a.owner_ref) ?? "—";
const buyboxDisplay = (value: unknown): string => {
  if (value === true) return "已获得";
  if (value === false) return "未获得";
  const raw = firstText(value);
  if (!raw) return "—";
  const key = raw.toLowerCase().replace(/[\s_-]/g, "");
  if (["yes", "true", "win", "winner", "won", "winning", "owned", "buyboxwinner"].includes(key)) return "已获得";
  if (["no", "false", "lose", "lost", "notwon", "notwinning", "notowned"].includes(key)) return "未获得";
  return raw;
};
const riskText: Record<string,string> = {high:"高风险",medium:"中风险",low:"低风险",none:"无风险",unknown:"待评估"};
const statusText: Record<string,string> = {pending:"待审批",running:"清货执行中",done:"已完成",rejected:"已驳回",cancelled:"已撤销",stock_closed:"库存已售罄"};
const display = (v: unknown): string => v == null || v === "" || (typeof v === "number" && !Number.isFinite(v)) ? "—" : String(v);
const quantity = (v: unknown) => v == null || v === "" || !Number.isFinite(Number(v)) ? "—" : `${Number(v).toLocaleString("zh-CN")} 件`;
const money = (v: unknown) => v == null || v === "" || !Number.isFinite(Number(v)) ? "—" : `$${Number(v).toFixed(2)}`;
const percentage = (v: unknown) => v == null || v === "" || !Number.isFinite(Number(v)) ? "—" : `${Number(v).toFixed(1)}%`;
const when = (v?: string | null) => {
  if (!v) return "—";
  const dateOnly = /^(\d{4})[-/](\d{2})[-/](\d{2})$/.exec(v);
  if (dateOnly) return `${dateOnly[1]}/${dateOnly[2]}/${dateOnly[3]}`;
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "—";
  const pieces = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(d);
  const get = (part: Intl.DateTimeFormatPartTypes) => pieces.find(p => p.type === part)?.value;
  return `${get("year")}/${get("month")}/${get("day")}`;
};
function Section({heading,note,children}:{heading:string;note?:string;children:ReactNode}) {
  return <section className="approval-demo__section">
    <header><strong>{heading}</strong>{note ? <span>{note}</span> : null}</header>{children}
  </section>;
}
function metric(row: ClearanceListing, key: string): Metric | undefined {
  return row.metrics?.[key];
}
function StockAndBusiness({row}:{row:ClearanceListing}) {
  const periods=[7,14,30] as const;
  const matrix=[
    ["销量（件）", "sales_", "d", quantity],
    ["销售额", "revenue_", "d_usd", money],
    ["广告费用", "ad_spend_", "d_usd", money],
    ["利润", "profit_", "d_usd", money],
    ["利润率", "margin_", "d_percent", percentage],
  ] as const;
  const rows=matrix.map(([label,pre,suf,fmt])=>({
    key:label,label,values:periods.map(n=>fmt(metric(row,`${pre}${n}${suf}`))),
  }));
  return <div className="approval-demo__sku-analysis-grid">
    <div className="approval-demo__mini-panel">
      <div className="approval-demo__mini-head"><b>经营数据对比</b><span>7 / 14 / 30 天</span></div>
      <div className="approval-demo__business-matrix">
        <Table className="approval-demo__business-matrix-table" size="small" pagination={false} rowKey="key"
          dataSource={rows} columns={[
            {key:"label",title:"经营指标",dataIndex:"label",width:160},
            ...periods.map((n,i)=>({key:String(n),title:`近${n}天`,render:(_v:unknown,r:typeof rows[number])=>r.values[i]})),
          ]}/>
      </div>
    </div>
    <div className="approval-demo__mini-panel">
      <div className="approval-demo__mini-head"><b>库存与风险依据</b><Tag>{riskText[row.risk] ?? "待评估"}</Tag></div>
      <div className="approval-demo__risk-reasons">
        <div><b>最新风险等级</b><p>{riskText[row.risk] ?? "待评估"}</p></div>
        <div><b>风险依据</b><p>{row.reasons?.join("；") || "目前没有可展示的风险依据"}</p></div>
        <div><b>缺失数据</b><p>{row.data_gaps?.join("；") || "—"}</p></div>
      </div>
    </div>
  </div>;
}
function LiveBody({detail}:{detail:ApplicationDetail}) {
  const a=detail.application as ApplicationDisplay;
  const row=detail.current as CurrentDisplay;
  const requested=nonnegative(a.requested_qty);
  const available=nonnegative(row.available);
  const remaining=available !== null && requested !== null ? Math.max(available-requested,0) : null;
  const due=a.planned_completion_date;
  const unitCost=inventoryUnitCost(row,a);
  const capital=inventoryCapital(row,unitCost);
  const margin=unitMargin(row);
  const suggested: SubmissionSuggestion | undefined = detail.submission_suggestion ?? undefined;
  const suggestedQty=nonnegative(suggested?.suggested_qty);
  const floor=nonnegative(suggested?.rule_floor_price_usd);
  const historicalMargin=numberOrNull(suggested?.snapshot_unit_margin_usd);
  const snapshotAvailable=nonnegative(suggested?.snapshot_available_qty);
  const suggestedRemaining = suggestedQty !== null && snapshotAvailable !== null
    ? Math.max(snapshotAvailable-suggestedQty,0) : null;
  const hasSuggestion = suggestedQty !== null || floor !== null || historicalMargin !== null;
  const fields: Array<[string,ReactNode]> = [
    ["店铺",a.store_name || row.store_name || a.store_id], ["负责人",businessOwner(row,a)],
    ["当前售价",money(row.price_amount)],
    ["划线价",money(row.strike_price_amount ?? a.strike_price_amount)],
    ["购物车",buyboxDisplay(row.buybox_status ?? a.buybox_status ?? metric(row,"has_buybox"))],
    ["单件库存成本",money(unitCost)],
    ["单件毛利空间",money(margin)], ["清货原因",a.reason],
    ["清货方式",a.methods_json?.join("、") || "—"], ["申请清货数量",quantity(a.requested_qty)],
    ["计划完成日期",when(due)], ["申请状态",<Tag key="status">{statusText[a.status]||a.status}</Tag>],
  ];
  const tiles: Array<[string,string,string]> = [
    ["WFS 可售库存",quantity(row.available),"实时可售"],
    ["预计售罄天数",metric(row,"sellout_is_infinite") === true ? "无限" : display(metric(row,"sellout_days")),"按现有规则计算"],
    ["可售库存成本",money(capital),"采购＋头程，不含销售费用"],
    ["上架天数",display(metric(row,"listing_days")),"Listing 上架时间"],
    ["Listing 评分",display(metric(row,"rating")),"最新可用评分"],
    ["退货率 · 30天",percentage(metric(row,"return_rate_30d_percent")),"最新有效观察值"],
  ];
  return <div className="approval-demo__clearance-main">
    <Section heading="01 申请基本信息" note="运营提交内容">
      <div className="approval-demo__clearance-product">
        <div className="approval-demo__clearance-thumb">SKU</div>
        <div className="approval-demo__clearance-product-info">
          <strong>{businessName(row,a)}</strong>
          <small>{a.item_id} · {a.local_sku || "—"} · {a.msku || "—"}</small>
        </div>
        <Tag color={a.risk_at_submission === "high" ? "error" : a.risk_at_submission === "medium" ? "warning" : "default"}>{riskText[a.risk_at_submission] || "待评估"}</Tag>
      </div>
      <div className="approval-demo__clearance-base-grid">{fields.map(([label,value])=><div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
      <div className="approval-demo__snapshot-note">商品经营数据展示最新可用值；缺失值显示“—”，不使用演示计算。</div>
    </Section>
    <Section heading="02 清货方案对比" note="系统建议 vs 运营申请">
      <div className="approval-demo__compare-grid">
        <div className="approval-demo__compare-card"><div className="approval-demo__compare-head"><b>系统建议</b><span>申请时建议快照</span></div>
          <div className="approval-demo__compare-body">
            <div className="approval-demo__compare-primary"><strong>{suggestedQty !== null ? suggestedQty : "—"}</strong><span>件 · {hasSuggestion ? "申请时规则建议（有数据项）" : "暂无可用建议快照"}</span></div>
            <div className="approval-demo__compare-kpis">
              <div><span>建议清货售价</span><b>—</b></div>
              <div><span>规则建议底价</span><b>{money(floor)}</b></div>
              <div><span>预计净回款</span><b>—</b></div>
              <div><span>预计清货盈亏</span><b>—</b></div>
              <div><span>建议清货后剩余库存</span><b>{quantity(suggestedRemaining)}</b></div>
              <div><span>当时单件毛利空间</span><b>{money(historicalMargin)}</b></div>
            </div>
          </div>
        </div>
        <div className="approval-demo__compare-card approval-demo__compare-card--applied">
          <div className="approval-demo__compare-head"><b>运营申请</b><Tag color="blue">实际提交方案</Tag></div>
          <div className="approval-demo__compare-body">
            <div className="approval-demo__compare-primary"><strong>{requested}</strong><span>件 · 申请清货量</span></div>
            <div className="approval-demo__compare-kpis">
              {(["申请清货售价","最低保本售价","预计净回款","预计清货盈亏"] as const).map(x=><div key={x}><span>{x}</span><b>—</b></div>)}
              <div><span>清货后剩余库存</span><b>{quantity(remaining)}</b></div>
              <div><span>当前单件毛利空间</span><b>{money(margin)}</b></div>
            </div>
          </div>
        </div>
      </div>
      <div className="approval-demo__delta-row">{hasSuggestion
        ? "仅展示申请时有依据的规则建议；规则底价不等于保本售价，历史与实时数据不可混算。"
        : "未保存可用的系统建议，无法比较申请方案与系统建议的差异。"} 未提交清货成交价或完整费用时，不估算净回款和盈亏。</div>
      <div className="approval-demo__compare-alert">审批决定基于已保存的申请、最新库存和授权校验；清货建议与真实售价调整分别执行。</div>
    </Section>
    <Section heading="03 SKU 经营与库存风险" note="当前最新数据">
      <div className="approval-demo__timestamp">真实业务只读来源；与申请保存时间可能不同</div>
      <div className="approval-demo__sku-metrics">
        {tiles.map(([label,value,hint])=><div key={label}><span>{label}</span><strong>{value}</strong><small>{hint}</small></div>)}
      </div>
      <StockAndBusiness row={row}/>
    </Section>
    <Section heading="04 申请说明" note="申请人补充信息">
      <p className="approval-demo__request-description">{a.note || "—"}</p>
    </Section>
    <Section heading="05 审批记录" note="真实业务事件">
      <div className="approval-demo__timeline">
        {detail.events?.length ? detail.events.map((ev,i)=><div className="approval-demo__timeline-item" key={`${ev.created_at}-${i}`}>
          <i className={`approval-demo__timeline-dot ${ev.event_type === "rejected" ? "approval-demo__timeline-dot--rejected" : "approval-demo__timeline-dot--done"}`}/>
          <div><b>{display(ev.actor_ref)} · {display(ev.event_type)}</b><p>{typeof ev.detail_json?.reason === "string" ? ev.detail_json.reason : "—"}</p></div>
          <time>{when(ev.created_at)}</time>
        </div>) : <div className="approval-demo__empty">尚无审批事件记录</div>}
      </div>
    </Section>
  </div>;
}
// CLEARANCE_REVIEW_STATE_FIX_V38: reset local modal/detail state per selected
// approval and entry path. Do not reset React state synchronously in an Effect.
export default function ClearanceApprovalDetailDrawer(props:Props) {
  const selectionKey = `${props.selected?.id ?? "closed"}:${props.directReviewAction ?? "detail"}`;
  return <ClearanceApprovalContent key={selectionKey} {...props} />;
}

function ClearanceApprovalContent({selected,onClose,onUpdated,directReviewAction}:Props) {
  const [detail,setDetail]=useState<ApplicationDetail>();
  const [loading,setLoading]=useState(Boolean(selected));
  const [action,setAction]=useState<Action | undefined>(directReviewAction);
  const [note,setNote]=useState("");
  const [saving,setSaving]=useState(false);
  const [messageApi,holder]=message.useMessage();
  const selectedId=selected?.id;
  useEffect(()=>{
    if(!selectedId)return;
    let active=true;
    void getClearanceApplication(selectedId).then(data=>{
      if(active){setDetail(data);setLoading(false);}
    }).catch(()=>{
      if(active){
        setLoading(false);
        void messageApi.error("清货申请详情加载失败，请刷新重试");
      }
    });
    return ()=>{active=false;};
  },[selectedId,messageApi]);
  const app=detail?.application;
  const canReview=Boolean(selected?.can_review && app?.status === "pending");
  const decide=async()=>{
    if(!app||!action||!canReview||saving)return;
    if(action==="rejected" && !note.trim()){void messageApi.warning("驳回原因必填");return;}
    setSaving(true);
    try{
      await reviewClearanceApplication(app.id,app.version,action,note.trim());
      // CLEARANCE_APPROVAL_REFRESH_V36: notify clearance center after confirmed server success
      window.dispatchEvent(new Event("szzsbj-clearance-application-updated"));
      void messageApi.success(action==="approved"?"审批通过，清货期状态已提交":"已驳回，Listing 生命周期保持不变");
      setAction(undefined);
      onClose();
      onUpdated();
    }catch{
      void messageApi.error("审批未成功，请刷新确认当前库存、审批权限与申请版本");
    }finally{setSaving(false);}
  };
  // CLEARANCE_REVIEW_MODAL_ONLY_V37: inline details and direct table actions have separate surfaces.
  return <>
  {holder}
  <Drawer title={null} closable={false} open={Boolean(selected) && !directReviewAction} width={1000}
    destroyOnHidden onClose={onClose} styles={{body:{padding:0}}}>
    {loading||!detail ? <div style={{padding:30}}><Spin /></div> : <div className="approval-demo approval-demo--clearance">
      <header className="approval-demo__clearance-header">
        <div className="approval-demo__clearance-header-top">
          <div className="approval-demo__clearance-title-wrap">
            <div className="approval-demo__clearance-eyebrow">CLEARANCE APPROVAL · DETAIL</div>
            <div className="approval-demo__clearance-title-line">
              <h2>{app ? businessName(detail.current as CurrentDisplay,app as ApplicationDisplay) : "—"}</h2>
              <Tag color="blue">真实申请</Tag>
              <Tag color="processing">{statusText[app?.status || ""] || app?.status}</Tag>
              <Tag>{riskText[app?.risk_at_submission || ""] || "待评估"}</Tag>
            </div>
            <div className="approval-demo__clearance-request-id">申请编号：{app?.id}</div>
          </div>
          <Button className="approval-demo__clearance-close" aria-label="关闭详情" onClick={onClose}>×</Button>
        </div>
        <div className="approval-demo__clearance-meta">
          <span>申请人<b>{app?.applicant_ref || "—"}</b></span>
          <span>提交时间<b>{when(app?.submitted_at)}</b></span>
          <span>当前审批人<b>授权审批人</b></span>
          <span>审批状态<b>{statusText[app?.status || ""] || "—"}</b></span>
        </div>
      </header>
      <main className="approval-demo__clearance-body"><LiveBody detail={detail}/></main>
      <footer className="approval-demo__clearance-footer">
        <span>{app?.status !== "pending" ? "该申请已审批或结束，不可重复审批" :
          !selected?.can_review ? "当前账号没有此申请的审批权限" :
          "审批结果写入本地清货测试库；只有审批通过才改变测试 Listing 生命周期状态。"}</span>
        <div>
          <Button disabled={!canReview} onClick={()=>{setAction("rejected");setNote("");}}>驳回</Button>
          <Button type="primary" disabled={!canReview} onClick={()=>{setAction("approved");setNote("");}}>审批通过</Button>
        </div>
      </footer>
    </div>}
  </Drawer>
  {/* CLEARANCE_APPROVAL_MODAL_STACK_V39: confirmation always above the clearance Drawer */}
  <Modal className="approval-demo__clearance-action-modal" open={Boolean(action && selected && detail && !loading)} centered zIndex={2200}
        title={action==="approved"?"审批通过":"驳回申请"} footer={null} width={410}
        destroyOnHidden onCancel={()=>{setAction(undefined);if(directReviewAction) onClose();}}>
        {directReviewAction && !canReview ? <div role="status" style={{padding:"12px 18px 0",fontSize:12,color:"#64748b"}}>
          {loading ? "正在核对申请状态与审批权限…" : app?.status !== "pending" ? "该申请已审批或结束，不允许重复审批" : "当前账号无审核权限，或审批列表需要刷新"}
        </div> : null}
        <div className="approval-demo__clearance-action-body">
          <label htmlFor="clearance-live-action-note">{action==="approved"?"审批意见（选填）":"驳回原因（必填）"}</label>
          <Input.TextArea id="clearance-live-action-note" rows={4} maxLength={4000}
            value={note} onChange={e=>setNote(e.target.value)} style={{resize:"none"}}
            placeholder={action==="approved"?"填写审批意见":"请填写驳回原因"}
            className="approval-demo__clearance-action-input" />
        </div>
        <div className="approval-demo__clearance-action-footer">
          <Button disabled={saving} onClick={()=>{setAction(undefined);if(directReviewAction) onClose();}}>取消</Button>
          <Button type="primary" loading={saving} disabled={!canReview || saving} onClick={()=>void decide()}>
            {action==="approved"?"确认通过":"确认驳回"}
          </Button>
        </div>
      </Modal>
  </>;
}

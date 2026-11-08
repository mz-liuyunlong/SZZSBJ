/** V3 demo-only drawers: four independent business layouts, no approval endpoints. */
import { Alert, Button, Descriptions, Drawer, Input, Modal, Table, Tag, Typography, message } from "antd";
import { useState, type ReactNode } from "react";
import type { ApprovalItem } from "../approvalTypes";
import { getDemoSeed, type DemoSeed } from "../approvalDemoData";
import { demoProfiles, type ClearanceSku, type DemoBusinessProfile } from "../approvalDemoPresentation";
import "./DemoApprovalDrawer.css";

interface Props { selected?: ApprovalItem; onClose(): void; initialAction?: "approve" | "reject"; }
const usd = (n: number | string | null | undefined) => n == null ? "—" : `$${Number(n).toFixed(2)}`;
const num = (n: number | undefined) => n == null ? "—" : n.toLocaleString("zh-CN");
const pct = (n: number | null | undefined) => n == null || !Number.isFinite(n) ? "—" : `${n.toFixed(1)}%`;
const status: Record<string,string> = {submitted:"待审批",approved:"已审批",rejected:"驳回记录",withdrawn:"已撤回",info_required:"待补资料",legacy_unverified:"历史待核验"};
const risk: Record<string,string> = {low:"低风险",medium:"中风险",high:"高风险",unknown:"待评估"};
const approvalType: Record<string,string> = {purchase:"采购审批",clearance:"清货审批",listing:"Listing归档",price:"价格调整"};
const info = (label: string, value: string | number | undefined) => ({key:label,label,children:value ?? "—"});

function StatTiles({items}:{items: Array<[string,string,string]>}) {
  return <div className="approval-demo__tiles">{items.map(([name,value,hint])=><div className="approval-demo__tile" key={name}>
    <span>{name}</span><strong>{value}</strong><small>{hint}</small>
  </div>)}</div>;
}
function Section({heading,note,children}:{heading:string;note?:string;children:ReactNode}) {
  return <section className="approval-demo__section">
    <header><strong>{heading}</strong>{note?<span>{note}</span>:null}</header>{children}
  </section>;
}
function Safety({children}:{children:ReactNode}) {
  return <Alert type="warning" showIcon message="审批与实际业务执行分离" description={children} />;
}
function PurchaseDetail({seed,p}:{seed:DemoSeed;p:DemoBusinessProfile}) {
  return <>
    <StatTiles items={[["采购申请金额",usd(seed.amount),"USD · 演示申请"],["采购件数",`${num(p.quantity)} 件`,"拟采购数量"],["要求交期",p.delivery ?? "—","供应商计划交付"]]} />
    <Section heading="01 / 采购业务信息"><Descriptions bordered size="small" column={2} items={[
      info("采购单号",seed.business_ref),info("供应商",p.supplier),info("店铺",seed.store),info("SKU",p.sku),
      info("产品负责人",p.owner),info("预计交期",p.delivery),info("采购金额",usd(seed.amount)),info("采购数量",`${num(p.quantity)} 件`),
    ]}/></Section>
    <Section heading="02 / 采购决策说明"><p className="approval-demo__copy">{seed.reason}</p>
      <Safety>请核对断货风险、采购数量、资金占用及供应商交期。通过审批不代表已经向供应商下单或付款。</Safety>
    </Section>
  </>;
}
function BusinessMatrix({sku}:{sku:ClearanceSku}) {
  const windows=[7,14,30] as const;
  const rows=[
    ["销量（件）",sku.sales.map(num)],
    ["日均销量（件）",sku.sales.map((n,i)=>(n/windows[i]).toFixed(2))],
    ["销售额",sku.revenue.map(usd)],
    ["广告费",sku.ad.map(usd)],
    ["广告占比",sku.ad.map((n,i)=>pct(sku.revenue[i]?100*n/sku.revenue[i]:null))],
    ["利润",sku.profit.map(usd)],
    ["利润率",sku.profit.map((n,i)=>pct(sku.revenue[i]?100*n/sku.revenue[i]:null))],
  ].map(([label,values])=>({key:label as string,label:label as string,values:values as string[]}));
  return <Table className="approval-demo__business-matrix-table" size="small" pagination={false} scroll={{x:560}}
    rowKey="key" dataSource={rows} columns={[
      {key:"label",title:"经营指标",dataIndex:"label",width:180},
      ...windows.map((n,i)=>({key:String(n),title:`近${n}天`,render:(_v:unknown,row:typeof rows[number])=>row.values[i]})),
    ]}/>;
}
function ClearanceDetail({
  seed,
  p,
  currentStatus,
  reviewedAt,
  reviewNote,
  isLive = false,
  liveRecord,
}: {
  seed: DemoSeed;
  p: DemoBusinessProfile;
  currentStatus: DemoSeed["status"];
  reviewedAt: string | null;
  reviewNote: string;
  isLive?: boolean;
  liveRecord?: ApprovalItem;
}) {
  const products = p.clearanceSkus ?? [];
  // 详情只展示当前申请记录指定的主 SKU
  const current = products.find((item) => item.sku === seed.sku);
  const totalAvailable = current?.available;
  const appliedQty = current?.target ?? p.targetQty;
  const remaining = totalAvailable == null || appliedQty == null ? undefined : Math.max(0, totalAvailable - appliedQty);
  const currentRisk = risk[seed.risk];
  const submittedAt = formatDemoTime(seed.submitted_at);
  const methods = p.methods?.join("、") ?? "—";

  return <div className="approval-demo__clearance-main">
    <Section heading="01 申请基本信息" note="运营提交内容">
      <div className="approval-demo__clearance-product">
        <div className="approval-demo__clearance-thumb">SKU</div>
        <div className="approval-demo__clearance-product-info">
          <strong>{current?.name ?? seed.title}</strong>
          <small>{current ? `${current.item} · ${current.sku} · ${current.msku}` : seed.sku}</small>
        </div>
        <Tag color={seed.risk === "high" ? "error" : seed.risk === "medium" ? "warning" : seed.risk === "low" ? "success" : "default"}>{currentRisk}</Tag>
      </div>
      <div className="approval-demo__clearance-base-grid">
        <div><span>店铺</span><strong>{seed.store}</strong></div>
        <div><span>负责人</span><strong>{p.owner ?? seed.applicant}</strong></div>
        <div><span>当前售价</span><strong>{current ? usd(current.price) : "—"}</strong></div>
        <div><span>划线价</span><strong>—</strong></div>
        <div><span>购物车</span><strong>—</strong></div>
        <div><span>单件库存成本</span><strong>{current ? usd(current.cost) : "—"}</strong></div>
        <div><span>单件毛利空间</span><strong>—</strong></div>
        <div><span>清货原因</span><strong>{seed.reason}</strong></div>
        <div><span>清货方式</span><strong>{methods}</strong></div>
        <div><span>申请清货数量</span><strong>{appliedQty == null ? "—" : `${num(appliedQty)} 件`}</strong></div>
        <div><span>计划完成日期</span><strong>{p.deadline ?? "—"}</strong></div>
        <div><span>申请状态</span><strong><Tag color={currentStatus === "approved" ? "success" : currentStatus === "rejected" ? "error" : "warning"}>{status[currentStatus]}</Tag></strong></div>
      </div>
      <div className="approval-demo__snapshot-note">{isLive ? "当前仅展示真实接口提供的资料；未取得的指标显示 —。" : "当前为清货审批 Mock 申请资料；划线价、购物车及完整毛利数据未提供时以 — 展示。"}</div>
    </Section>

    <Section heading="02 清货方案对比" note="系统建议 vs 运营申请">
      <div className="approval-demo__compare-grid">
        <div className="approval-demo__compare-card">
          <div className="approval-demo__compare-head"><b>系统建议</b><span>申请时建议快照</span></div>
          <div className="approval-demo__compare-body">
            <div className="approval-demo__compare-primary"><strong>—</strong><span>件 · 系统建议量未提供</span></div>
            <div className="approval-demo__compare-kpis">
              <div><span>建议清货售价</span><b>—</b></div>
              <div><span>最低保本售价</span><b>—</b></div>
              <div><span>预计净回款</span><b>—</b></div>
              <div><span>预计清货盈亏</span><b>—</b></div>
              <div><span>清货后剩余库存</span><b>—</b></div>
              <div><span>单件毛利空间</span><b>—</b></div>
            </div>
          </div>
        </div>
        <div className="approval-demo__compare-card approval-demo__compare-card--applied">
          <div className="approval-demo__compare-head"><b>运营申请</b><Tag color="blue">实际提交方案</Tag></div>
          <div className="approval-demo__compare-body">
            <div className="approval-demo__compare-primary"><strong>{num(appliedQty)}</strong><span>件 · 申请清货量</span></div>
            <div className="approval-demo__compare-kpis">
              <div><span>申请清货售价</span><b>—</b></div>
              <div><span>最低保本售价</span><b>—</b></div>
              <div><span>预计净回款</span><b>—</b></div>
              <div><span>预计清货盈亏</span><b>—</b></div>
              <div><span>清货后剩余库存</span><b>{remaining == null ? "—" : `${num(remaining)} 件`}</b></div>
              <div><span>单件毛利空间</span><b>—</b></div>
            </div>
          </div>
        </div>
      </div>
      <div className="approval-demo__delta-row">系统建议快照未提供，暂无法计算申请数量、售价及盈亏差异。</div>
      <div className="approval-demo__compare-alert">{isLive ? "未取得可核实的规则建议快照或完整费用口径，不展示模拟净回款、盈亏或保本价。" : "当前 Mock 资料未提供系统建议历史快照及完整清货费用口径，净回款、盈亏和保本价暂不展示，避免使用当前售价或库存成本代替清货测算。"}</div>
    </Section>

    <Section heading="03 SKU 经营与库存风险" note="当前最新数据">
      <div className="approval-demo__timestamp">{isLive ? "经营指标未取得时显示 —，不使用模拟数据" : "当前展示清货审批 Mock 经营数据"}</div>
      {current ? <>
        <div className="approval-demo__sku-metrics">
          <div><span>WFS 可售库存</span><strong>{num(current.available)} 件</strong><small>当前可售</small></div>
          <div><span>预计售罄天数</span><strong className="approval-demo__red">{current.sales[2] > 0 ? `${num(Math.ceil(current.available / current.sales[2] * 30))} 天` : "—"}</strong><small>按近30天销量估算</small></div>
          <div><span>可售库存成本</span><strong>{usd(current.available * current.cost)}</strong><small>可售库存 × 单件成本</small></div>
          <div><span>上架天数</span><strong>—</strong><small>Mock 数据未提供</small></div>
          <div><span>Listing 评分</span><strong className={current.rating < 4 ? "approval-demo__red" : ""}>{current.rating.toFixed(1)} / 5</strong><small>Mock 评价数据</small></div>
          <div><span>退货率 · 30天</span><strong>{pct(current.returnRate)}</strong><small>30天退货率</small></div>
        </div>
        <div className="approval-demo__sku-analysis-grid">
          <div className="approval-demo__mini-panel">
            <div className="approval-demo__mini-head"><b>经营数据对比</b><span>7 / 14 / 30 天</span></div>
            <div className="approval-demo__business-matrix"><BusinessMatrix sku={current}/></div>
          </div>
          <div className="approval-demo__mini-panel">
            <div className="approval-demo__mini-head"><b>库存与风险依据</b><Tag color={seed.risk === "high" ? "error" : seed.risk === "medium" ? "warning" : seed.risk === "low" ? "success" : "default"}>{currentRisk}</Tag></div>
            <div className="approval-demo__risk-reasons">
              <div><b>申请风险等级 · {currentRisk}</b><p>{seed.reason}</p></div>
              <div><b>申请佐证资料</b><p>{seed.evidence || "未提供补充佐证资料"}</p></div>
              <div><b>清货计划</b><p>{seed.plan || "未提供清货计划说明"}</p></div>
            </div>
          </div>
        </div>
      </> : <div className="approval-demo__empty">当前申请未关联 SKU 明细。</div>}
    </Section>

    <Section heading="04 申请说明" note="申请人补充信息">
      <p className="approval-demo__request-description">{seed.reason || "申请人未填写补充说明。"}</p>
    </Section>

    <Section heading="05 审批记录" note="完整保留申请与流转记录">
      <div className="approval-demo__timeline">
        <div className="approval-demo__timeline-item">
          <i className="approval-demo__timeline-dot approval-demo__timeline-dot--done"/>
          <div><b>{seed.applicant}提交清货申请</b><p>提交清货数量 {num(appliedQty)} 件，方式：{methods}。</p></div>
          <time>{submittedAt}</time>
        </div>
        {reviewedAt ? <div className="approval-demo__timeline-item">
          <i className={`approval-demo__timeline-dot ${currentStatus === "approved" ? "approval-demo__timeline-dot--done" : "approval-demo__timeline-dot--rejected"}`}/>
          <div><b>{isLive ? (liveRecord?.reviewed_by || "审批人") : "演示审批人"}{currentStatus === "approved" ? "审批通过" : "驳回申请"}</b><p>{reviewNote || (isLive ? "审批意见未提供" : "本地演示操作，未调用正式审批接口。")}</p></div>
          <time>{formatDemoTime(reviewedAt)}</time>
        </div> : currentStatus === "submitted" ? <div className="approval-demo__timeline-item">
          <i className="approval-demo__timeline-dot approval-demo__timeline-dot--pending"/>
          <div><b>流转至部门负责人</b><p>等待审批处理</p></div>
          <time>待处理</time>
        </div> : <div className="approval-demo__timeline-item">
          <i className={`approval-demo__timeline-dot ${currentStatus === "approved" ? "approval-demo__timeline-dot--done" : "approval-demo__timeline-dot--rejected"}`}/>
          <div><b>{isLive ? "审批记录" : "Mock 记录"}：{status[currentStatus] ?? "—"}</b><p>原始演示数据未提供审批意见和审批时间。</p></div>
          <time>—</time>
        </div>}
      </div>
    </Section>
  </div>;
}

function formatDemoTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  });
}

function ListingDetail({seed,p}:{seed:DemoSeed;p:DemoBusinessProfile}) {
  return <>
    <StatTiles items={[["归档业务对象",p.item??"—","商品 ID / Listing"],["当前 Listing 状态",p.listingStatus??"—","申请时快照"],["WFS 可售库存",`${num(p.stockAvailable)} 件`,"归档前核对"]]}/>
    <Section heading="01 / Listing 归档内容"><Descriptions bordered size="small" column={2} items={[
      info("商品 ID / Item ID",p.item),info("品名",p.product),info("SKU / MSKU",`${p.sku} / ${p.msku}`),
      info("店铺",seed.store),info("当前 Listing 状态",p.listingStatus),info("归档类型",p.archiveWay),
    ]}/></Section>
    <Section heading="02 / 归档前业务风险核对"><Descriptions bordered size="small" column={2} items={[
      info("WFS 可售库存",`${num(p.stockAvailable)} 件`),info("未完成订单",`${num(p.openOrders)} 单`),
      info("风险等级",risk[seed.risk]),info("归档申请原因",seed.reason),
    ]}/></Section>
    <Section heading="03 / 审批边界"><Safety>审批通过不代表立即归档 Listing。仍有可售库存或未完成订单时，业务侧必须二次核对并独立执行。</Safety></Section>
  </>;
}
function PriceDetail({seed,p}:{seed:DemoSeed;p:DemoBusinessProfile}) {
  const old=p.oldPrice??0, next=p.newPrice??0;
  const delta=old?(next-old)/old*100:0;
  return <>
    <StatTiles items={[["原售价",usd(old),"申请前售价"],["申请售价",usd(next),"待审批新售价"],["调整幅度",`${delta>0?"+":""}${pct(delta)}`,"与原售价比较"]]}/>
    <Section heading="01 / 价格调整决策依据"><Descriptions bordered size="small" column={2} items={[
      info("店铺",seed.store),info("品名",p.product),info("商品 ID",p.item),info("SKU / MSKU",`${p.sku} / ${p.msku}`),
      info("原售价",usd(old)),info("申请售价",usd(next)),info("最低保护售价",usd(p.minPrice)),info("申请调整幅度",pct(delta)),
    ]}/></Section>
    <Section heading="02 / 利润影响"><Descriptions bordered size="small" column={2} items={[
      info("原利润率",pct(p.oldMargin)),info("申请后预计利润率",pct(p.newMargin)),
      info("利润率变动",p.oldMargin==null||p.newMargin==null?"—":`${(p.newMargin-p.oldMargin).toFixed(1)} 个百分点`),
      info("示例月销量",`${num(p.monthlySales)} 件`),info("关联清货申请",p.linkedClearance),
    ]}/></Section>
    <Section heading="03 / 价格执行边界"><Safety>只有超出已批准的价格范围时才需要再次审批。审批通过不会自动修改平台售价；上述利润数据仅为演示测算。</Safety></Section>
  </>;
}

function Side({seed}:{seed:DemoSeed}) {
  return <aside className="approval-demo__side">
    <Section heading="申请基础信息"><Descriptions size="small" column={1} items={[
      info("业务类型",approvalType[demoProfiles[seed.id]?.kind??""]),info("申请人",seed.applicant),
      info("申请单号",seed.id),info("业务单号",seed.business_ref),
      info("申请时间",seed.submitted_at.replace("T"," ").replace("Z"," UTC")),
      info("审批状态",status[seed.status]),info("风险等级",risk[seed.risk]),
    ]}/></Section>
    <Section heading="申请说明 · 必填"><p className="approval-demo__copy">{seed.reason}</p></Section>
    <Section heading="审批与补充记录"><div className="approval-demo__timeline"><strong>演示申请已创建</strong><small>{seed.applicant} · {seed.submitted_at.slice(0,16).replace("T"," ")}</small><p>示例数据，无真实审批操作及审计记录。</p></div></Section>
    <Section heading="安全边界"><p className="approval-demo__copy">演示记录不调用审批 API。申请人不能审批自己的正式申请，真实业务须由后端校验授权和业务快照。</p></Section>
  </aside>;
}
function DemoApprovalDrawerContent({selected,onClose,initialAction}:Props) {
  const live = selected && selected.approval_type === "clearance_request" && !selected.id.startsWith("DEMO-") ? selected : undefined;
  const isLive = Boolean(live);
  const seed: DemoSeed | undefined = selected ? getDemoSeed(selected.id) ?? (live ? {
    id: live.id, approval_type: live.approval_type, title: live.title,
    business_ref: live.business_ref, applicant: live.applicant_id || "—",
    store: live.clearance_details?.store_name ?? live.source_account_ref ?? "—",
    status: live.status as DemoSeed["status"],
    risk: live.risk_level as DemoSeed["risk"], amount: null,
    submitted_at: live.submitted_at || "", reason: live.reason || "",
    evidence: "", sku: live.clearance_details?.sku || "—", plan: "",
  } : undefined) : undefined;
  const p: DemoBusinessProfile | undefined = seed ? demoProfiles[seed.id] ?? (live ? {
    kind: "clearance", owner: live.clearance_details?.owner_ref ?? live.applicant_id ?? "—",
    targetQty: live.clearance_details?.requested_qty,
    methods: live.clearance_details?.methods ?? [],
    clearanceSkus: [],
  } : undefined) : undefined;
  const isClearance = p?.kind === "clearance";
  const [clearanceStatus, setClearanceStatus] = useState<DemoSeed["status"]>(seed?.status ?? "submitted");
  const [actionType, setActionType] = useState<"approve" | "reject" | null>(initialAction ?? null);
  const [actionNote, setActionNote] = useState("");
  const [actionError, setActionError] = useState(false);
  const [reviewedAt, setReviewedAt] = useState<string | null>(null);
  const [reviewNote, setReviewNote] = useState("");

  const openAction = (type: "approve" | "reject") => {
    if (isLive) return; // Real clearance actions remain blocked in this UI-only phase.
    setActionType(type);
    setActionNote("");
    setActionError(false);
  };
  const closeAction = () => {
    setActionType(null);
    setActionError(false);
  };
  const confirmAction = () => {
    if (isLive) return;
    if (!actionType) return;
    const note = actionNote.trim();
    if (actionType === "reject" && !note) {
      setActionError(true);
      return;
    }
    setClearanceStatus(actionType === "approve" ? "approved" : "rejected");
    setReviewedAt(new Date().toISOString());
    setReviewNote(note);
    closeAction();
    message.success(`本地演示状态已更新为${actionType === "approve" ? "已审批" : "已驳回"}，未调用正式审批接口`);
  };

  return <Drawer
    title={null}
    closable={false}
    open={Boolean(seed)}
    width={isClearance ? 1000 : 1040}
    destroyOnHidden
    onClose={onClose}
    styles={{body:{padding:0}}}
  >
    {seed && p ? <div className={`approval-demo ${isClearance ? "approval-demo--clearance" : ""}`}>
      {isClearance ? <>
        <header className="approval-demo__clearance-header">
          <div className="approval-demo__clearance-header-top">
            <div className="approval-demo__clearance-title-wrap">
              <div className="approval-demo__clearance-eyebrow">CLEARANCE APPROVAL · DETAIL</div>
              <div className="approval-demo__clearance-title-line">
                <h2>{seed.title}</h2>
                <Tag color="blue">{isLive ? "真实申请" : "演示数据"}</Tag>
                <Tag color={clearanceStatus === "approved" ? "success" : clearanceStatus === "rejected" ? "error" : "warning"}>{status[clearanceStatus]}</Tag>
                <Tag color={seed.risk === "high" ? "error" : seed.risk === "medium" ? "warning" : seed.risk === "low" ? "success" : "default"}>{risk[seed.risk]}</Tag>
              </div>
              <div className="approval-demo__clearance-request-id">申请编号：{seed.id}</div>
            </div>
            <Button className="approval-demo__clearance-close" aria-label="关闭详情" onClick={onClose}>×</Button>
          </div>
          <div className="approval-demo__clearance-meta">
            <span>申请人<b>{seed.applicant}</b></span>
            <span>提交时间<b>{formatDemoTime(seed.submitted_at)}</b></span>
            <span>当前审批人<b>{clearanceStatus === "submitted" ? "部门负责人" : "—"}</b></span>
            <span>等待时长<b>—</b></span>
          </div>
        </header>
        <main className="approval-demo__clearance-body">
          <ClearanceDetail seed={seed} p={p} currentStatus={clearanceStatus} reviewedAt={live?.reviewed_at ?? reviewedAt} reviewNote={reviewNote} isLive={isLive} liveRecord={live}/>
        </main>
        <footer className="approval-demo__clearance-footer">
          <span>{isLive ? "当前真实清货审批仅展示资料；本阶段未开放提交、通过和驳回。" : "演示交互仅更新当前详情状态，不调用正式审批接口或执行平台操作。"}</span>
          <div>
            <Button danger disabled={isLive || clearanceStatus !== "submitted"} onClick={() => openAction("reject")}>驳回</Button>
            <Button type="primary" disabled={isLive || clearanceStatus !== "submitted"} onClick={() => openAction("approve")}>审批通过</Button>
          </div>
        </footer>
        <Modal
          className="approval-demo__clearance-action-modal"
          open={actionType !== null}
          centered
          width={410}
          title={actionType === "approve" ? "审批通过" : "驳回申请"}
          footer={null}
          onCancel={closeAction}
          destroyOnHidden
        >
          <div className="approval-demo__clearance-action-body">
            <label htmlFor="approval-clearance-action-note">{actionType === "approve" ? "审批意见（选填）" : "驳回原因 *"}</label>
            <Input.TextArea
              id="approval-clearance-action-note"
              rows={4}
              value={actionNote}
              onChange={event => { setActionNote(event.target.value); setActionError(false); }}
              placeholder={actionType === "approve" ? "填写审批意见（选填）" : "请填写驳回原因"}
              className="approval-demo__clearance-action-input"
            />
            {actionError ? <div className="approval-demo__clearance-action-error" role="alert">请填写驳回原因</div> : null}
          </div>
          <div className="approval-demo__clearance-action-footer">
            <Button onClick={closeAction}>取消</Button>
            {actionType === "approve"
              ? <Button type="primary" onClick={confirmAction}>确认通过</Button>
              : <Button danger onClick={confirmAction}>确认驳回</Button>}
          </div>
        </Modal>
      </> : <>
        <header className="approval-demo__header"><div>
          <small>数据中心 / 审批工作台 / {approvalType[p.kind]}</small>
          <h2>{seed.title}</h2>
          <Tag color="blue">演示数据</Tag><Tag color={seed.status==="approved"?"green":seed.status==="rejected"?"red":"orange"}>{status[seed.status]}</Tag><Tag>{risk[seed.risk]}</Tag>
          <span className="approval-demo__header-id">审批单 {seed.id}</span>
        </div><Button onClick={onClose}>关闭</Button></header>
        <div className="approval-demo__layout"><main className="approval-demo__main">
          {p.kind==="purchase"?<PurchaseDetail seed={seed} p={p}/>:null}
          {p.kind==="listing"?<ListingDetail seed={seed} p={p}/>:null}
          {p.kind==="price"?<PriceDetail seed={seed} p={p}/>:null}
        </main><Side seed={seed}/></div>
        <footer className="approval-demo__footer"><Typography.Text type="secondary">只读演示 · 不连接真实审批、采购、清货、Listing 或价格 API</Typography.Text><Button onClick={onClose}>关闭详情</Button></footer>
      </>}
    </div> : null}
  </Drawer>;
}

// Remount the demo detail when the selected approval changes. This resets local
// demo state without synchronously calling setState inside an effect.
export default function DemoApprovalDrawer(props: Props) {
  return <DemoApprovalDrawerContent key={props.selected?.id ?? "closed"} {...props} />;
}

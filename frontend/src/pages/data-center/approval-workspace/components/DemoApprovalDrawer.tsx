/** V3 demo-only drawers: four independent business layouts, no approval endpoints. */
import { Alert, Button, Descriptions, Drawer, Table, Tag, Typography } from "antd";
import { useState, type ReactNode } from "react";
import type { ApprovalItem } from "../approvalTypes";
import { getDemoSeed, type DemoSeed } from "../approvalDemoData";
import { demoProfiles, type ClearanceSku, type DemoBusinessProfile } from "../approvalDemoPresentation";
import "./DemoApprovalDrawer.css";

interface Props { selected?: ApprovalItem; onClose(): void; }
const usd = (n: number | string | null | undefined) => n == null ? "—" : `$${Number(n).toFixed(2)}`;
const num = (n: number | undefined) => n == null ? "—" : n.toLocaleString("zh-CN");
const pct = (n: number | null | undefined) => n == null || !Number.isFinite(n) ? "—" : `${n.toFixed(1)}%`;
const status: Record<string,string> = {submitted:"待审批",approved:"已审批",rejected:"驳回记录"};
const risk: Record<string,string> = {low:"低风险",medium:"中风险",high:"高风险"};
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
  return <Table size="small" pagination={false} scroll={{x:600}}
    rowKey="key" dataSource={rows} columns={[
      {key:"label",title:"经营指标",dataIndex:"label",width:180},
      ...windows.map((n,i)=>({key:String(n),title:`近${n}天`,render:(_v:unknown,row:typeof rows[number])=>row.values[i]})),
    ]}/>;
}
function ClearanceDetail({seed,p}:{seed:DemoSeed;p:DemoBusinessProfile}) {
  const products=p.clearanceSkus ?? [];
  const [index,setIndex]=useState(0);
  const current=products[index] ?? products[0];
  const stockCost=products.reduce((s,x)=>s+x.target*x.cost,0);
  return <>
    <StatTiles items={[["计划清货量",`${num(p.targetQty)} 件`,"整单申请目标"],["相关库存成本",usd(stockCost),"不等于清货亏损"],["SKU 数量",String(products.length),"单店铺申请"]]}/>
    <Section heading="01 / 清货申请决策依据"><Descriptions size="small" bordered column={2} items={[
      info("Walmart 店铺",seed.store),info("清货原因",seed.reason),info("计划完成日期",p.deadline),
      info("清货方式",p.methods?.join("、")),info("申请来源",p.source),info("预计库存成本",usd(stockCost)),
    ]}/></Section>
    <Section heading="02 / 清货 SKU 明细" note="逐 SKU 核对">
      <Table size="small" pagination={false} scroll={{x:740}} rowKey="sku" dataSource={products} columns={[
        {title:"SKU / MSKU",key:"sku",width:170,render:(_v,x:ClearanceSku)=><><strong>{x.sku}</strong><small className="approval-demo__subline">{x.msku}</small></>},
        {title:"商品 ID",dataIndex:"item",width:120},
        {title:"WFS 可售",key:"available",render:(_v,x:ClearanceSku)=>`${num(x.available)} 件`},
        {title:"库龄",key:"age",render:(_v,x:ClearanceSku)=>`${x.age} 天`},
        {title:"目标清货量",key:"target",render:(_v,x:ClearanceSku)=>`${num(x.target)} 件`},
        {title:"单件成本",key:"cost",render:(_v,x:ClearanceSku)=>usd(x.cost)},
      ]}/>
    </Section>
    {current?<Section heading="03 / 经营表现 · 7 / 14 / 30 天" note="与清货分析口径一致">
      <div className="approval-demo__sku-pills">{products.map((item,i)=><Button key={item.sku} size="small" type={i===index?"primary":"default"} onClick={()=>setIndex(i)}>{item.sku}</Button>)}</div>
      <div className="approval-demo__sku-summary">{current.name} ｜ {current.item} ｜ {current.sku} / {current.msku}<p>WFS 可售 {num(current.available)} 件 · 平均库龄 {current.age} 天 · 预计售罄 {current.sales[2]?Math.ceil(current.available/current.sales[2]*30):"无法估算"} 天</p></div>
      <BusinessMatrix sku={current}/>
      <Descriptions bordered size="small" column={2} className="approval-demo__bottom-facts" items={[
        info("30天退货率",pct(current.returnRate)),info("商品评分",`${current.rating.toFixed(1)} / 5.0`),
        info("当前售价",usd(current.price)),info("WFS 可售库存成本",usd(current.available*current.cost)),
      ]}/>
    </Section>:null}
    <Section heading="04 / 库存与经营风险说明"><Safety>申请人不得自批；清货数量不能超过可售库存。审批通过不会自动降价、创建广告或执行 WFS 移除/弃置。</Safety></Section>
  </>;
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
export default function DemoApprovalDrawer({selected,onClose}:Props) {
  const seed=selected ? getDemoSeed(selected.id) : undefined;
  const p=seed?demoProfiles[seed.id]:undefined;
  return <Drawer title={null} closable={false} open={Boolean(seed)} width={1040} destroyOnHidden onClose={onClose} styles={{body:{padding:0}}}>
    {seed&&p?<div className="approval-demo">
      <header className="approval-demo__header"><div>
        <small>数据中心 / 审批工作台 / {approvalType[p.kind]}</small>
        <h2>{seed.title}</h2>
        <Tag color="blue">演示数据</Tag><Tag color={seed.status==="approved"?"green":seed.status==="rejected"?"red":"orange"}>{status[seed.status]}</Tag><Tag>{risk[seed.risk]}</Tag>
        <span className="approval-demo__header-id">审批单 {seed.id}</span>
      </div><Button onClick={onClose}>关闭</Button></header>
      <div className="approval-demo__layout"><main className="approval-demo__main">
        {p.kind==="purchase"?<PurchaseDetail seed={seed} p={p}/>:null}
        {p.kind==="clearance"?<ClearanceDetail key={seed.id} seed={seed} p={p}/>:null}
        {p.kind==="listing"?<ListingDetail seed={seed} p={p}/>:null}
        {p.kind==="price"?<PriceDetail seed={seed} p={p}/>:null}
      </main><Side seed={seed}/></div>
      <footer className="approval-demo__footer"><Typography.Text type="secondary">只读演示 · 不连接真实审批、采购、清货、Listing 或价格 API</Typography.Text><Button onClick={onClose}>关闭详情</Button></footer>
    </div>:null}
  </Drawer>;
}


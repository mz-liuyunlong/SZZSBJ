/** Live clearance approval detail: current Listing figures plus immutable application facts. */
import { Descriptions, Empty, Image, Tabs, Tag, Typography } from "antd";
import type { ApprovalDetail } from "../approvalTypes";

type Data = Record<string, unknown>;
const dict = (value: unknown): Data =>
  value && typeof value === "object" && !Array.isArray(value) ? value as Data : {};
const display = (value: unknown): string =>
  value === undefined || value === null || value === "" ? "—" : String(value);
const qty = (value: unknown): string =>
  value === undefined || value === null ? "—" : `${display(value)} 件`;
const usd = (value: unknown): string =>
  value === undefined || value === null ? "—" : `$${Number(value).toFixed(2)}`;

export default function ClearanceApprovalDetail({ detail }: {detail: ApprovalDetail}) {
  const data = dict(detail.current_case);
  const request = dict(data.request);
  const current = dict(data.current);
  const listing = dict(current.listing);
  const evaluation = dict(current.evaluation);
  if (!Object.keys(request).length) return <Empty description="当前清货申请不存在或不可读取" />;

  const methods = Array.isArray(request.methods)
    ? request.methods.map(String).join("、") : "—";
  const reasons = Array.isArray(evaluation.risk_reasons)
    ? evaluation.risk_reasons.map(String).join("、") : "";
  const warnings = Array.isArray(evaluation.warnings)
    ? evaluation.warnings.map(String).join("、") : "";
  const businessName = display(listing.title || detail.title);
  const subject = <div style={{display:"flex",gap:16,alignItems:"center",padding:"8px 0 14px"}}>
    {typeof listing.picture_url==="string" && listing.picture_url ? <Image
      src={listing.picture_url} width={72} height={72} style={{objectFit:"contain",borderRadius:6}}
    /> : null}
    <div style={{minWidth:0}}>
      <Typography.Text strong>{businessName}</Typography.Text>
      <div style={{fontSize:12,color:"#64748b",marginTop:4}}>
        Item ID {display(listing.item_id)} · SKU {display(listing.local_sku)} · MSKU {display(listing.msku)}
      </div>
      <div style={{fontSize:12,color:"#64748b",marginTop:4}}>
        {display(listing.store_name || listing.store_id)} · 负责人 {display(listing.owner_ref)}
      </div>
    </div>
  </div>;
  const applicantFields = <Descriptions size="small" column={3} bordered>
    <Descriptions.Item label="当前售价">{usd(listing.sale_price_amount)}</Descriptions.Item>
    <Descriptions.Item label="目标清货量">{qty(request.target_qty)}</Descriptions.Item>
    <Descriptions.Item label="申请来源">{request.source==="manual"?"主动申请":"系统识别"}</Descriptions.Item>
    <Descriptions.Item label="清货原因" span={2}>{display(request.reason)}</Descriptions.Item>
    <Descriptions.Item label="清货方式">{methods}</Descriptions.Item>
    <Descriptions.Item label="申请说明" span={3}>
      <Typography.Text style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>
        {display(request.remark)}
      </Typography.Text>
    </Descriptions.Item>
  </Descriptions>;
  const tabs = [
    {key:"analysis",label:"经营分析",children:<Descriptions size="small" bordered column={3}>
      <Descriptions.Item label="30天销量">{qty(evaluation.sales_30d)}</Descriptions.Item>
      <Descriptions.Item label="预计售罄">{evaluation.coverage_days==null?"不可计算":`${evaluation.coverage_days} 天`}</Descriptions.Item>
      <Descriptions.Item label="30天利润率">{evaluation.margin_30d_percent==null?"待核实":`${evaluation.margin_30d_percent}%`}</Descriptions.Item>
      <Descriptions.Item label="30天期间退款率">{evaluation.refund_rate_percent==null?"待核实":`${evaluation.refund_rate_percent}%`}</Descriptions.Item>
      <Descriptions.Item label="风险等级">
        <Tag color={evaluation.risk_level==="high"?"red":evaluation.risk_level==="medium"?"orange":"default"}>
          {display(evaluation.risk_level)}
        </Tag>
      </Descriptions.Item>
      <Descriptions.Item label="建议清货量">{qty(evaluation.suggested_qty)}</Descriptions.Item>
    </Descriptions>},
    {key:"inventory",label:"库存与风险",children:<Descriptions size="small" bordered column={3}>
      <Descriptions.Item label="当前 WFS 可售">{qty(evaluation.current_wfs_available)}</Descriptions.Item>
      <Descriptions.Item label="30天有效库存快照">{display(evaluation.snapshot_coverage_days_30d)} 天</Descriptions.Item>
      <Descriptions.Item label="30天有货天数">{display(evaluation.positive_stock_days_30d)} 天</Descriptions.Item>
      <Descriptions.Item label="Listing评分">{display(listing.average_rating)}</Descriptions.Item>
      <Descriptions.Item label="评论数">{display(listing.review_count)}</Descriptions.Item>
      <Descriptions.Item label="库存资金占用">{usd(evaluation.stock_capital_usd)}</Descriptions.Item>
      <Descriptions.Item label="风险依据" span={3}>{reasons || "无自动风险依据"}</Descriptions.Item>
      {warnings?<Descriptions.Item label="待核实" span={3}>{warnings}</Descriptions.Item>:null}
    </Descriptions>},
  ];
  return <div style={{padding:"2px 18px 16px"}}>
    {subject}
    {applicantFields}
    <Tabs style={{marginTop:12}} size="small" defaultActiveKey="analysis" items={tabs}/>
    <Typography.Text type="secondary" style={{fontSize:12}}>
      以上经营和库存指标读取系统当前最新数据，申请单保存原始业务事实用于审计；审批通过不自动执行任何清货操作。
    </Typography.Text>
  </div>;
}

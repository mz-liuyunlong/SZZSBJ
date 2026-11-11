import { Button, Tag } from 'antd';
import { StarOutlined, BarChartOutlined, RiseOutlined, InboxOutlined, FileTextOutlined, ClockCircleOutlined, DatabaseOutlined } from '@ant-design/icons';
import { useLayoutEffect, useRef, type ReactNode } from 'react';
import type { ApprovalItem } from '../approvalTypes';
import type { DemoSeed } from '../approvalDemoData';
import type { DemoBusinessProfile } from '../approvalDemoPresentation';
import { finiteNumber } from '../purchaseApprovalDemoMetrics';
import './PurchaseApprovalDecisionDrawer.css';

type DecisionAction = 'approve' | 'reject';
type Props = {
  record: ApprovalItem;
  seed: DemoSeed;
  profile: DemoBusinessProfile;
  onClose(): void;
  onAction?: (item: ApprovalItem, action: DecisionAction) => void;
};

const dimensionSpec = [
  {key: 'market', title: '市场竞争', weight: 15},
  {key: 'speed', title: '出单速度', weight: 30},
  {key: 'ad', title: '广告有效性', weight: 20},
  {key: 'profit', title: '利润空间', weight: 25},
  {key: 'trust', title: '数据可信度', weight: 10},
] as const;

function numberText(value: number | null | undefined, decimals = 0): string {
  return value == null || !Number.isFinite(value) ? '—' : value.toLocaleString('zh-CN', {
    minimumFractionDigits: decimals, maximumFractionDigits: decimals,
  });
}
function money(value: number | null | undefined, currency = 'USD'): string {
  return value == null || !Number.isFinite(value) ? '—' : `${currency} ${numberText(value, 2)}`;
}
function percentage(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? '—' : `${numberText(value, 1)}%`;
}
function dateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('zh-CN', {hour12: false});
}
// PR337_PURCHASE_REFERENCE_V34: icons only; no business logic changes.
// PR337_PURCHASE_REFERENCE_V35: outlined layer icon as in the approved reference.
function PurchaseLayerMark() {
  return <svg className="purchase-decision__brand-icon" viewBox="0 0 32 32" width="32" height="32" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round">
    <path d="M16 3 29 10 16 17 3 10 16 3Z" />
    <path d="m3 16 13 7 13-7" />
    <path d="m3 22 13 7 13-7" />
  </svg>;
}
function metricIcon(label: string) {
  if (label.includes('评分')) return <StarOutlined />;
  if (label.includes('毛利')) return <BarChartOutlined />;
  if (label.includes('ACOS')) return <RiseOutlined />;
  return <InboxOutlined />;
}
function panelIcon(title: string) {
  if (title.includes('五维')) return <BarChartOutlined />;
  if (title.includes('利润') || title.includes('成本')) return <DatabaseOutlined />;
  if (title.includes('广告')) return <RiseOutlined />;
  if (title.includes('申请基础')) return <FileTextOutlined />;
  if (title.includes('审批历史')) return <ClockCircleOutlined />;
  return <InboxOutlined />;
}
function Metric({label,value,description,attention}: {
  label: string; value: string; description: string; attention?: boolean;
}) {
  return <div className={`purchase-decision__metric${attention ? ' is-attention' : ''}`}>
    <span className="purchase-decision__metric-label"><span className="purchase-decision__metric-icon">{metricIcon(label)}</span>{label}</span><strong>{value}</strong><small>{description}</small>
  </div>;
}
function Panel({title,aside,children}: {title: string; aside?: ReactNode; children: ReactNode}) {
  return <section className="purchase-decision__panel">
    <div className="purchase-decision__panel-head"><strong><span className="purchase-decision__panel-icon">{panelIcon(title)}</span>{title}</strong>{aside ? <span>{aside}</span> : null}</div>
    <div className="purchase-decision__panel-body">{children}</div>
  </section>;
}
function Fact({label,value,emphasize}: {label: string; value: ReactNode; emphasize?: boolean}) {
  return <div className="purchase-decision__fact">
    <span>{label}</span><b className={emphasize ? 'is-emphasized' : undefined}>{value}</b>
  </div>;
}

function FiveDimensions({profile}: {profile: DemoBusinessProfile}) {
  const scores = profile.purchaseAnalysis?.dimensions;
  return <Panel title="五维测评分析" aside="申请时评分 · 满分10分">
    <div className="purchase-decision__dimensions">
      {dimensionSpec.map(({key, title, weight}) => {
        const value = finiteNumber(scores?.[key]);
        return <div key={key} className="purchase-decision__dimension">
          <span>{title}</span>
          <div className="purchase-decision__track"><i style={{width: value == null ? '0%' : `${Math.min(100, Math.max(0, value * 10))}%`}} /></div>
          <b>{value == null ? '—' : value.toFixed(1)}</b><small>{weight}%</small>
        </div>;
      })}
    </div>
    {scores ? <div className="purchase-decision__hint">总分和各维度均为申请时测评快照，审批后不应被最新评分覆盖。</div>
      : <div className="purchase-decision__hint">尚未取得五维评分明细，不能用评级代替各维度数据。</div>}
  </Panel>;
}

function InitialAnalysis({profile}: {profile: DemoBusinessProfile}) {
  const p = profile.purchaseAnalysis;
  const hasAd = p?.adState === 'active';
  return <>
    <FiveDimensions profile={profile}/>
    <div className="purchase-decision__two-panels">
      <Panel title="利润与成本" aside="测评期预计口径">
        <Fact label="预计售价" value={money(p?.sellingPrice)}/>
        <Fact label="采购成本 / 件" value={money(p?.unitPurchaseCost)}/>
        <Fact label="头程及平台费用 / 件" value={money(p?.unitOtherCost)}/>
        <Fact label="单件预计毛利" value={money(p?.unitGrossProfit)} emphasize/>
        <Fact label="预计毛利率" value={percentage(p?.grossMarginPct)} emphasize/>
        <Fact label="ROI" value={numberText(p?.roi, 2)}/>
      </Panel>
      <Panel title="广告与出单" aside="测评观察期">
        {p?.adState === 'organic' ? <div className="purchase-decision__notice">无广告投放 · 自然成交；广告维度不计分，权重按规则重新分配。</div>
          : p?.adState === 'none' ? <div className="purchase-decision__notice">未获取广告表现，请核对是否有自然成交及广告样本。</div>
          : null}
        <Fact label="广告 ACOS" value={hasAd ? percentage(p?.acosPct) : '—'}/>
        <Fact label="CPC / CVR" value={hasAd ? `${money(p?.cpc)} / ${percentage(p?.cvrPct)}` : '—'}/>
        <Fact label="广告花费 / 销售额" value={hasAd ? `${money(p?.adSpend)} / ${money(p?.adSales)}` : '—'}/>
        <Fact label="点击 / 广告订单" value={hasAd ? `${numberText(p?.adClicks)} / ${numberText(p?.adOrders)}` : '—'}/>
        <Fact label="首单用时" value={p?.firstOrderDays == null ? '—' : `${numberText(p.firstOrderDays)} 天`}/>
        <Fact label="14天有效订单" value={p?.validOrders14 == null ? '—' : `${numberText(p.validOrders14)} 单`}/>
        {hasAd && p?.adClicks != null && p.adClicks < 20 ? <div className="purchase-decision__notice">广告点击不足20次，样本不足，仅供参考。</div> : null}
      </Panel>
    </div>
  </>;
}

function DailySalesChart({profile, seed}: {profile: DemoBusinessProfile; seed: DemoSeed}) {
  const daily = profile.purchaseAnalysis?.dailySales90;
  const valid = Array.isArray(daily) && daily.length === 90 && daily.every((n) => Number.isFinite(n) && n >= 0);
  const points = valid ? daily : [];
  const max = Math.max(1, ...points);
  const ending = new Date(seed.submitted_at);
  const dateForIndex = (i: number) => {
    if (Number.isNaN(ending.getTime())) return `第 ${i + 1} 天`;
    const d = new Date(ending);
    d.setUTCDate(d.getUTCDate() - (89 - i));
    return d.toISOString().slice(0, 10);
  };
  return <Panel title="申请时近90天每日销量" aside="每日一柱 · 历史销量快照">
    {valid ? <>
      <div className="purchase-decision__sales-bars" role="img" aria-label="申请时近90天每日销量柱状图">
        {points.map((value, i) => <div className="purchase-decision__sales-column" key={i}
          title={`${dateForIndex(i)}：${value} 件`}>
          <span style={{height: value === 0 ? 2 : `${Math.max(4, value / max * 100)}%`}} />
        </div>)}
      </div>
      <div className="purchase-decision__axis"><span>{dateForIndex(0)}</span><span>{dateForIndex(44)}</span><span>{dateForIndex(89)}</span></div>
      <div className="purchase-decision__hint">蓝色柱子代表每日销量；鼠标悬停可查看日期和数量。只呈现申请时的记录，不把审批后的销量倒灌进原审批依据。</div>
    </> : <div className="purchase-decision__empty">暂未提供90天每日销量数据，不能依据近30天总销量伪造每日曲线。</div>}
  </Panel>;
}

function ReplenishmentAnalysis({profile, seed}: {profile: DemoBusinessProfile; seed: DemoSeed}) {
  const p = profile.purchaseAnalysis;
  return <>
    <DailySalesChart profile={profile} seed={seed}/>
    <div className="purchase-decision__two-panels">
      <Panel title="库存与补货" aside="提交申请时库存快照">
        <Fact label="当前可售库存" value={p?.stockAvailable == null ? '—' : `${numberText(p.stockAvailable)} 件`}/>
        <Fact label="在途库存" value={p?.stockInbound == null ? '—' : `${numberText(p.stockInbound)} 件`}/>
        <Fact label="预计可售天数" value={profile.estimatedSellableDays == null ? '—' : `${numberText(profile.estimatedSellableDays)} 天`} emphasize/>
        <Fact label="近30天销量" value={profile.sales30Qty == null ? '—' : `${numberText(profile.sales30Qty)} 件`}/>
        <Fact label="日均销量" value={profile.sales30Qty == null ? '—' : `${numberText(profile.sales30Qty / 30, 1)} 件`}/>
        <Fact label="预计补货到货" value={profile.delivery ?? '—'}/>
      </Panel>
      <Panel title="经营利润与广告" aside="近30天实际经营">
        <Fact label="近30天利润" value={money(p?.profit30)}/>
        <Fact label="近30天利润率" value={percentage(p?.profitMargin30Pct)} emphasize/>
        <Fact label="广告花费" value={money(p?.adSpend30)}/>
        <Fact label="广告销售额" value={money(p?.adSales30)}/>
        <Fact label="ACOS" value={percentage(p?.acos30Pct)}/>
        <Fact label="观察说明" value={p?.businessNote ?? '—'}/>
      </Panel>
    </div>
  </>;
}

export default function PurchaseApprovalDecisionDrawer({record, seed, profile, onClose, onAction}: Props) {
  const purchaseScrollRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    // Never reopen an approval half-scrolled under the fixed header.
    if (purchaseScrollRef.current) purchaseScrollRef.current.scrollTop = 0;
  }, [record.id]);
  const kind = profile.purchaseKind;
  const isInitial = kind === 'initial';
  const isReplenishment = kind === 'replenishment';
  const p = profile.purchaseAnalysis;
  const canDecide = record.status === 'submitted' && Boolean(onAction);
  const statusNames: Record<string, string> = {submitted: '待审批', approved: '已审批', rejected: '已驳回', info_required: '待补资料'};
  const requestQty = profile.quantity;
  const suggestQty = profile.suggestedQty;
  const deviation = requestQty != null && suggestQty != null ? requestQty - suggestQty : null;
  const purchaseAmount = seed.amount == null ? '—' : `${seed.amount === '' ? '' : 'USD '}${numberText(Number(seed.amount), 2)}`;
  const source = profile.applicationSource === 'system' ? '系统自动申请' : profile.applicationSource === 'operator' ? '运营主动申请' : '来源待确认';
  return <div className="purchase-decision">
    <header className="purchase-decision__header">
      <div className="purchase-decision__header-title">
        <h2><PurchaseLayerMark />{profile.product || seed.title}</h2>
        <div className="purchase-decision__header-tags">
          <Tag color="blue">{isInitial ? '新品首采' : isReplenishment ? '后续补货' : '采购类型待确认'}</Tag>
          <Tag>{source}</Tag>
          <Tag color={record.status === 'approved' ? 'success' : record.status === 'rejected' ? 'error' : 'warning'}>{statusNames[record.status] ?? record.status}</Tag>
          <span>{profile.sku || 'SKU 待关联'} · {profile.owner || '负责人待确认'}</span>
        </div>
      </div>
    </header>

    <div ref={purchaseScrollRef} className="purchase-decision__scroll">
      <div className="purchase-decision__metrics">
        {isInitial ? <>
          <Metric label="综合测评分数" value={profile.scoreTotal == null ? '—' : numberText(profile.scoreTotal, 2)} description={profile.initialGrade ? `${profile.initialGrade} 级 · 申请时评级` : '评级待确认'} />
          <Metric label="预计毛利率" value={percentage(p?.grossMarginPct)} description={`ROI ${numberText(p?.roi, 2)}`} />
          <Metric label="广告 ACOS" value={p?.adState === 'active' ? percentage(p?.acosPct) : '—'} description={p?.adState === 'organic' ? '自然成交 · 未投广告' : `CVR ${percentage(p?.cvrPct)}`} />
          <Metric label="申请采购数量" value={requestQty == null ? '—' : `${numberText(requestQty)} 件`} description={`系统建议 ${suggestQty == null ? '—' : `${numberText(suggestQty)} 件`}`} />
        </> : <>
          <Metric label="预计可售天数" value={profile.estimatedSellableDays == null ? '—' : `${numberText(profile.estimatedSellableDays)} 天`} description="申请时库存覆盖" attention={profile.estimatedSellableDays != null && profile.estimatedSellableDays <= 7}/>
          <Metric label="近30天销量" value={profile.sales30Qty == null ? '—' : `${numberText(profile.sales30Qty)} 件`} description={profile.sales30Qty == null ? '待评估' : `日均 ${numberText(profile.sales30Qty / 30, 1)} 件`}/>
          <Metric label="近30天利润率" value={percentage(p?.profitMargin30Pct)} description={`利润 ${money(p?.profit30)}`}/>
          <Metric label="申请补货数量" value={requestQty == null ? '—' : `${numberText(requestQty)} 件`} description={`系统建议 ${suggestQty == null ? '—' : `${numberText(suggestQty)} 件`}`}/>
        </>}
      </div>
      <div className="purchase-decision__layout">
        {/* PR337_PURCHASE_DETAIL_GRID_V32: layout classes only */}
        <main className={`purchase-decision__main purchase-decision__main--${isInitial ? 'initial' : isReplenishment ? 'replenishment' : 'unknown'}`}>
          <Panel title="采购决策依据" aside="系统建议与实际申请对照">
            <div className="purchase-decision__decision-grid">
              <Fact label="系统建议量" value={suggestQty == null ? '—' : `${numberText(suggestQty)} 件`}/>
              <Fact label="实际申请量" value={requestQty == null ? '—' : `${numberText(requestQty)} 件`} emphasize/>
              <Fact label="申请与建议差异" value={deviation == null ? '—' : `${deviation > 0 ? '+' : ''}${numberText(deviation)} 件`}/>
              <Fact label="预计采购金额" value={purchaseAmount} emphasize/>
            </div>
            <div className="purchase-decision__reason"><strong>申请说明</strong><p>{seed.reason || '—'}</p></div>
            {isInitial && p?.roi != null && p.roi < .5 ? <div className="purchase-decision__notice is-warning">ROI 低于 0.5，按新品评分规则触发采购否决，请重点核对。</div> : null}
          </Panel>
          {isInitial ? <InitialAnalysis profile={profile}/> : isReplenishment ? <ReplenishmentAnalysis profile={profile} seed={seed}/> : <Panel title="经营分析"><div className="purchase-decision__empty">采购类型尚未确认，无法确定对应的审批评估指标。</div></Panel>}
        </main>
        <aside className="purchase-decision__aside">
          <Panel title="申请基础信息">
            <Fact label="申请人" value={profile.applicationSource === 'system' ? '系统自动发起' : seed.applicant}/>
            <Fact label="业务负责人" value={profile.owner || '—'}/>
            <Fact label="所属店铺" value={seed.store || '—'}/>
          </Panel>
          <Panel title="审批历史">
            <div className="purchase-decision__timeline"><b>申请已提交</b><small>{dateTime(seed.submitted_at)}</small><span>{source} · {seed.id}</span></div>
            {record.status === 'approved' || record.status === 'rejected' ? <div className="purchase-decision__timeline"><b>{statusNames[record.status]}</b><small>{dateTime(record.reviewed_at)}</small><span>{record.reviewed_by || '审批人员'}</span></div> : null}
          </Panel>
        </aside>
      </div>
    </div>
    <footer className="purchase-decision__footer">
      <span>申请时分析快照 · 模拟审批，不写入生产业务数据</span>
      <div className="purchase-decision__footer-actions">
        {/* PR337_PURCHASE_DETAIL_SYSTEM_UI_V33: use standard Ant Design actions and retained guard. */}
        <Button size="middle" onClick={onClose}>关闭</Button>
        <Button size="middle" type="default" danger disabled={!canDecide} onClick={() => onAction?.(record, 'reject')}>驳回</Button>
        <Button size="middle" type="primary" disabled={!canDecide} onClick={() => onAction?.(record, 'approve')}>审批通过</Button>
      </div>
    </footer>
  </div>;
}

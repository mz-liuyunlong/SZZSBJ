import { Alert, Button, Tag } from 'antd';
import { StarOutlined, BarChartOutlined, RiseOutlined, InboxOutlined, FileTextOutlined, ClockCircleOutlined, DatabaseOutlined } from '@ant-design/icons';
import { useLayoutEffect, useRef, type ReactNode } from 'react';
import type { ApprovalItem, PurchasePageRead } from '../approvalTypes';
import type { DemoSeed } from '../approvalDemoData';
import type { DemoBusinessProfile } from '../approvalDemoPresentation';
import NewProductEvaluationData from '@/pages/products/new-product/NewProductEvaluationData';
import type { Identity } from '@/pages/products/new-product/newProductBusinessApi';
import { usePurchaseApprovalReadModel } from '../purchaseApprovalReadModel';
import type { Product } from '@/pages/products/new-product/newProductModel';
import PurchaseApprovalEvidence, { approvalScoreDisplay } from './PurchaseApprovalEvidence';
import './PurchaseApprovalDecisionDrawer.css';

type DecisionAction = 'approve' | 'reject';
type Props = {
  record: ApprovalItem;
  seed: DemoSeed;
  profile: DemoBusinessProfile;
  evaluationIdentity?: Identity;
  detailState?: 'loading' | 'ready' | 'error';
  preloadedRead?: PurchasePageRead;
  onClose(): void;
  onAction?: (item: ApprovalItem, action: DecisionAction) => void;
};

function numberText(value: number | null | undefined, decimals = 0): string {
  return value == null || !Number.isFinite(value) ? '—' : value.toLocaleString('zh-CN', {
    minimumFractionDigits: decimals, maximumFractionDigits: decimals,
  });
}
function money(value: number | null | undefined, currency = 'USD'): string {
  return value == null || !Number.isFinite(value) ? '—' : `${currency} ${numberText(value, 2)}`;
}
function finiteAmount(value: unknown): number | null {
  if (value === null || value === undefined || value === '' || typeof value === 'boolean') return null;
  if (typeof value !== 'number' && typeof value !== 'string') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
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
function Metric({label,value,description,attention,extra,previousValue}: {
  label: string; value: string; description: ReactNode; attention?: boolean; extra?: ReactNode; previousValue?: string|null;
}) {
  return <div className={`purchase-decision__metric${attention ? ' is-attention' : ''}${previousValue ? ' purchase-decision__metric--score-transition' : ''}`}>
    <span className="purchase-decision__metric-label"><span className="purchase-decision__metric-icon">{metricIcon(label)}</span>{label}</span><strong>{previousValue && <><span className="purchase-decision__score-before">{previousValue}</span><span className="purchase-decision__score-arrow">→</span></>}{value.startsWith("CNY ") ? `\u00a5 ${value.slice(4)}` : value}</strong>{description ? <small>{description}</small> : null}{extra ? <div className="purchase-decision__metric-extra">{extra}</div> : null}
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

function InitialAnalysis({product, loading, hasIdentity, preloadedDaily}: {
  profile: DemoBusinessProfile;
  product: Product | null;
  loading: boolean;
  hasIdentity: boolean;
  preloadedDaily?: unknown;
}) {
  return <>
    {product ? <NewProductEvaluationData product={product} initialOperatingDaily={preloadedDaily}/> :
      <div className="purchase-decision__empty">
        {loading ? '正在读取同一商品的测评数据…' :
          hasIdentity ? '暂未取得匹配账号、店铺和 Item ID 的真实测评数据。' :
          '采购记录缺少可验证的商品身份，无法展示真实测评数据。'}
      </div>}
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

export default function PurchaseApprovalDecisionDrawer({record, seed, profile, evaluationIdentity, detailState = 'ready', preloadedRead, onClose, onAction}: Props) {
  const purchaseScrollRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    // Never reopen an approval half-scrolled under the fixed header.
    if (purchaseScrollRef.current) purchaseScrollRef.current.scrollTop = 0;
  }, [record.id]);
  const kind = profile.purchaseKind;
  const isInitial = kind === 'initial';
  const isReplenishment = kind === 'replenishment';
  const p = profile.purchaseAnalysis;
  const identityKey = evaluationIdentity ? JSON.stringify([
    evaluationIdentity.source_account_ref, evaluationIdentity.store_id, evaluationIdentity.item_id,
  ]) : null;
  const requestIdentity = isInitial && detailState === 'ready' ? evaluationIdentity : undefined;
  const readModel = usePurchaseApprovalReadModel(requestIdentity, profile.sku, preloadedRead);
  const evaluationProduct = readModel.product;
  const evaluationLoading = detailState === 'loading' || readModel.loading;
  const canDecide = detailState === 'ready' && record.status === 'submitted' && !readModel.loading && Boolean(onAction) && (record.id.startsWith('DEMO-') || record.can_review);
  const statusNames: Record<string, string> = {submitted: '待审批', approved: '已审批', rejected: '已驳回', info_required: '待补资料'};
  const requestQty = profile.quantity;
  const suggestQty = profile.suggestedQty;
  const purchaseValue = finiteAmount(record.purchase_details?.amount ?? seed.amount);
  const purchaseCurrency = record.purchase_details?.currency_code ??
    record.currency_code ?? (record.id.startsWith('DEMO-') ? 'USD' : null);
  const currentUnitCost = readModel.unitPurchaseCostCny;
  const estimatedPurchaseCny = currentUnitCost !== null && currentUnitCost >= 0 &&
    requestQty != null && Number.isInteger(requestQty) && requestQty > 0
    ? currentUnitCost * requestQty : null;
  const purchaseAmount = purchaseValue !== null && purchaseCurrency
    ? `${purchaseCurrency} ${numberText(purchaseValue, 2)}`
    : estimatedPurchaseCny !== null ? `CNY ${numberText(estimatedPurchaseCny, 2)}` : '—';
  // Estimate using verified historical net profit per paid unit; it is a forecast,
  // not an approved purchase quote nor the frozen approval scoring snapshot.
  const estimatedTotalProfit = readModel.unitProfitUsd != null &&
    requestQty != null && Number.isInteger(requestQty) && requestQty > 0
    ? readModel.unitProfitUsd * requestQty : null;
  // The exact-SKU cost is read once from product management. A current Listing
  // identity comes from the already-needed new-product list (same MART).
  const resolvedPurchaseAmount = purchaseAmount === '—' &&
    (detailState === 'loading' || readModel.costLoading) ? '加载中…' : purchaseAmount;

  const source = profile.applicationSource === 'system' ? '系统自动申请' : profile.applicationSource === 'operator' ? '运营主动申请' : '来源待确认';
  // PURCHASE_PROFIT_SYSTEM_FX_V1
  // Display conversion only. The original USD profit is unchanged.
  const profitFxText = record.purchase_details?.profit_fx_rate;
  const profitFxMonth = record.purchase_details?.profit_fx_month;
  const profitFxSource = record.purchase_details?.profit_fx_source;

  const profitFxRate =
    profitFxSource === 'lingxing_my_rate' &&
    typeof profitFxText === 'string' &&
    /^\d+(?:\.\d+)?$/.test(profitFxText)
      ? Number(profitFxText) : null;

  const estimatedTotalProfitCny =
    estimatedTotalProfit != null &&
    Number.isFinite(estimatedTotalProfit) &&
    profitFxRate != null &&
    Number.isFinite(profitFxRate) &&
    profitFxRate > 0 &&
    typeof profitFxMonth === 'string' &&
    /^\d{4}-\d{2}$/.test(profitFxMonth)
      ? estimatedTotalProfit * profitFxRate
      : null;

  // PURCHASE_APPROVAL_REFERENCE_V2: read-only frozen status for the top score card.
  const referenceEvidence = record.purchase_details?.approval_evidence;
  // NP_PURCHASE_SCORE_HOVER_HEADER_V2
  const scoreDisplay = approvalScoreDisplay(referenceEvidence);
  // NP_PURCHASE_GRADE_INLINE_V4: show the frozen original grade beside the final badge.
  const previousGrade = scoreDisplay.gradeChange && referenceEvidence?.system_grade
    && referenceEvidence.effective_grade === profile.initialGrade
    ? referenceEvidence.system_grade : null;
  const scoreDescription = previousGrade
    ? ''
    : scoreDisplay.revised && !referenceEvidence?.system_grade && profile.initialGrade
      ? `${profile.initialGrade} 级 · 原始等级未核实`
      : profile.initialGrade ? `${profile.initialGrade} 级 · 申请时评级` : '评级待确认';
  return <div className="purchase-decision">
    {record.approval_type === 'new_product_purchase' && <div className="purchase-decision__modal-bar">
      <span className="purchase-decision__modal-icon" aria-hidden="true"><svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinejoin="round"><rect x="7" y="6" width="19" height="23" rx="3"/><path d="M12 4h9v5h-9zM12 15h10M12 20h10"/></svg></span>
      <strong>{"\u91c7\u8d2d\u7533\u8bf7\u5ba1\u6279"}</strong>
      <button type="button" className="purchase-decision__modal-close" aria-label={"\u5173\u95ed\u91c7\u8d2d\u5ba1\u6279\u5f39\u6846"} onClick={onClose}>{"\u00d7"}</button>
    </div>}
    <header className="purchase-decision__header">
      <div className="purchase-decision__header-title">
        <h2><PurchaseLayerMark />{profile.product || seed.title}</h2>
        <div className="purchase-decision__header-tags">
          <Tag color="blue">{isInitial ? '新品首采' : isReplenishment ? '后续补货' : '采购类型待确认'}</Tag>
          <Tag>{source}</Tag>
          <Tag color={record.status === 'approved' ? 'success' : record.status === 'rejected' ? 'error' : 'warning'}>{statusNames[record.status] ?? record.status}</Tag>
          <span>{profile.sku || 'SKU 待关联'} · {seed.store && seed.store !== '—' ? seed.store : '店铺待关联'} · {profile.owner || '负责人待确认'}</span>
        </div>
      </div>
    </header>

    <div ref={purchaseScrollRef} className="purchase-decision__scroll">
      {detailState === 'error' && <Alert type="error" showIcon message="采购审批详情加载失败，请关闭后重新打开。当前不可审批。"/>}
      <div className="purchase-decision__metrics">
        {isInitial ? <>
          <Metric label="综合测评分数" value={profile.scoreTotal == null ? '—' : numberText(profile.scoreTotal, 2)} description={scoreDescription} previousValue={scoreDisplay.previous} extra={<>
      {profile.initialGrade && (previousGrade ? <div className="purchase-decision__score-grade-pair">
        <span className="purchase-decision__score-before">{previousGrade}级</span>
        <span className="purchase-decision__score-arrow" aria-hidden="true">→</span>
        <span className="purchase-decision__score-grade">{profile.initialGrade}级</span>
      </div> : <span className="purchase-decision__score-grade">{profile.initialGrade}级</span>)}
      {referenceEvidence?.frozen && <span className={scoreDisplay.revised ? 'purchase-decision__score-revised' : 'purchase-decision__score-untouched'}>{scoreDisplay.revised ? '已修正' : scoreDisplay.verifiedUnchanged ? '未修改' : '未核实'}</span>}
    </>} />
          <Metric label="申请采购数量" value={requestQty == null ? '—' : `${numberText(requestQty)} 件`} description={`系统建议 ${suggestQty == null ? '—' : `${numberText(suggestQty)} 件`}`} />
          <Metric label="预计采购金额" value={resolvedPurchaseAmount} description="" />
          <Metric label="预计总利润" value={estimatedTotalProfitCny === null && (detailState === 'loading' || readModel.profitLoading) ? '加载中…' : money(estimatedTotalProfitCny, 'CNY')} description="" />
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
          {isInitial ? <>{/* PURCHASE_APPROVAL_REFERENCE_V1 */}<InitialAnalysis profile={profile} product={evaluationProduct} loading={evaluationLoading} hasIdentity={Boolean(identityKey)} preloadedDaily={readModel.daily}/>{detailState !== 'error' && <PurchaseApprovalEvidence record={record}/>}</> : isReplenishment ? <ReplenishmentAnalysis profile={profile} seed={seed}/> : <Panel title="经营分析"><div className="purchase-decision__empty">采购类型尚未确认，无法确定对应的审批评估指标。</div></Panel>}
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
      <span>{record.approval_type === "new_product_purchase" ? "申请时真实评分快照 · 审批结果写入原采购申请" : "申请时分析快照 · 模拟审批，不写入生产业务数据"}</span>
      <div className="purchase-decision__footer-actions">
        {/* PR337_PURCHASE_DETAIL_SYSTEM_UI_V33: use standard Ant Design actions and retained guard. */}
        <Button size="middle" onClick={onClose}>关闭</Button>
        <Button size="middle" type="default" danger disabled={!canDecide} onClick={() => onAction?.(record, 'reject')}>驳回</Button>
        <Button size="middle" type="primary" disabled={!canDecide} onClick={() => onAction?.(record, 'approve')}>{record.approval_type === "new_product_purchase" ? "\u6279\u51c6\u91c7\u8d2d" : "\u5ba1\u6279\u901a\u8fc7"}</Button>
      </div>
    </footer>
  </div>;
}

// PURCHASE_DETAIL_SYNCHRONIZED_V1

// NP_APPROVAL_IDENTITY_REGISTRY_V2_20261122

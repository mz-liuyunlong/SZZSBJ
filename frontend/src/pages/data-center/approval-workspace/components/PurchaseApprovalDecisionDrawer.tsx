import { Button, Tag } from 'antd';
import { StarOutlined, BarChartOutlined, RiseOutlined, InboxOutlined, FileTextOutlined, ClockCircleOutlined, DatabaseOutlined } from '@ant-design/icons';
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import type { ApprovalItem } from '../approvalTypes';
import type { DemoSeed } from '../approvalDemoData';
import type { DemoBusinessProfile } from '../approvalDemoPresentation';
import { backendRequest } from '@/api/backendApi';
import NewProductEvaluationData from '@/pages/products/new-product/NewProductEvaluationData';
import { getCachedNewProductDetail, listNewProducts, type Identity } from '@/pages/products/new-product/newProductBusinessApi';
import { toPersistedProduct } from '@/pages/products/new-product/newProductRealAdapter';
import type { Product } from '@/pages/products/new-product/nativeData';
import { fetchListingManagementRows } from '@/pages/products/listingManagementApi';
import { listProductManagementSkus } from '@/pages/products/productManagementApi';
import PurchaseApprovalEvidence from './PurchaseApprovalEvidence';
import './PurchaseApprovalDecisionDrawer.css';

type DecisionAction = 'approve' | 'reject';
type Props = {
  record: ApprovalItem;
  seed: DemoSeed;
  profile: DemoBusinessProfile;
  evaluationIdentity?: Identity;
  preloadedEvaluation?: {id: string; product: Product; daily: unknown};
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
function Metric({label,value,description,attention,extra}: {
  label: string; value: string; description: string; attention?: boolean; extra?: ReactNode;
}) {
  return <div className={`purchase-decision__metric${attention ? ' is-attention' : ''}`}>
    <span className="purchase-decision__metric-label"><span className="purchase-decision__metric-icon">{metricIcon(label)}</span>{label}</span><strong>{value.startsWith("CNY ") ? `\u00a5 ${value.slice(4)}` : value}</strong>{description ? <small>{description}</small> : null}{extra ? <div className="purchase-decision__metric-extra">{extra}</div> : null}
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

export default function PurchaseApprovalDecisionDrawer({record, seed, profile, evaluationIdentity, preloadedEvaluation, onClose, onAction}: Props) {
  const purchaseScrollRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    // Never reopen an approval half-scrolled under the fixed header.
    if (purchaseScrollRef.current) purchaseScrollRef.current.scrollTop = 0;
  }, [record.id]);
  const kind = profile.purchaseKind;
  const isInitial = kind === 'initial';
  const isReplenishment = kind === 'replenishment';
  const p = profile.purchaseAnalysis;
  const account = evaluationIdentity?.source_account_ref;
  const store = evaluationIdentity?.store_id;
  const item = evaluationIdentity?.item_id;
  const sku = profile.sku?.trim();
  const identityKey = account && store && item ? JSON.stringify([account,store,item]) : null;
  // PURCHASE_DETAIL_SYNCHRONIZED_V1: the parent validates the saved identity.
  const warmed = preloadedEvaluation?.id === record.id ? preloadedEvaluation : undefined;
  const [evaluationState, setEvaluationState] = useState<{
    identityKey: string;
    product: Product | null;
    unitProfitUsd: number | null;
    unitPurchaseCostCny: number | null;
  } | null>(null);
  useEffect(() => {
    if (!isInitial || !account || !store || !item || !identityKey) return;
    let active = true;
    const identity = {source_account_ref:account, store_id:store, item_id:item};
    // Both existing endpoints are read-only; no new source, rescore, or purchase writes.
    void Promise.allSettled([
      warmed ? Promise.resolve({items: []}) : listNewProducts({page:1,pageSize:200,storeId:store,keyword:item,searchField:'item_id'}),
      warmed ? Promise.resolve({evaluation_operating_daily:warmed.daily}) : getCachedNewProductDetail(identity),
      // Exact-SKU read via the existing product-management endpoint; backend
      // redacts purchase costs unless this reviewer has field-level access.
      sku ? backendRequest<{items:Array<{sku:string|null;purchase_cost_cny:string|null}>}>(
        `/api/product-management/skus?sku_batch=${encodeURIComponent(sku)}&page=1&page_size=100`
      ) : Promise.resolve(null),
    ]).then(([listResult,detailResult,costResult]) => {
      if (!active) return;
      const candidates = listResult.status === 'fulfilled'
        ? listResult.value.items.filter(row =>
          row.listing.source_account_ref === account &&
          row.listing.store_id === store && row.listing.item_id === item) : [];
      // Ambiguous matches must not silently display another account's data.
      const product = warmed?.product ?? (candidates.length === 1 ? toPersistedProduct(candidates[0]) : null);
      const detail = detailResult.status === 'fulfilled'
        ? detailResult.value.evaluation_operating_daily : null;
      const daily = detail && typeof detail === 'object'
        ? detail as Record<string,unknown> : null;
      const totals = daily?.totals && typeof daily.totals === 'object'
        ? daily.totals as Record<string,unknown> : null;
      const units = finiteAmount(totals?.sales_units);
      const profit = finiteAmount(totals?.profit_usd);
      // Use the original refund/sample-aware testing-profit source. Never
      // infer profit from selling price, ROI, ACOS or an incomplete evidence set.
      const unitProfitUsd = daily?.status === 'scored' &&
        daily.source === 'new_products_testing_profit_full_history_v2' &&
        daily.policy === 'returns_ignored_samples_excluded_sample_ads_included' &&
        units !== null && units > 0 && profit !== null ? profit / units : null;
      const costRows = costResult.status === 'fulfilled'
        ? costResult.value?.data.items.filter(row => row.sku === sku) ?? [] : [];
      const unitPurchaseCostCny = costRows.length === 1
        ? finiteAmount(costRows[0].purchase_cost_cny) : null;
      setEvaluationState({identityKey, product, unitProfitUsd, unitPurchaseCostCny});
    });
    return () => {active = false;};
  }, [isInitial, account, store, item, identityKey, sku, warmed]);
  const evaluationReady = evaluationState?.identityKey === identityKey;
  const evaluationProduct = warmed?.product ?? (evaluationReady ? evaluationState?.product ?? null : null);
  const evaluationLoading = Boolean(identityKey) && !evaluationReady && !warmed;
  const canDecide = record.status === 'submitted' && Boolean(onAction) && (record.id.startsWith('DEMO-') || record.can_review);
  const statusNames: Record<string, string> = {submitted: '待审批', approved: '已审批', rejected: '已驳回', info_required: '待补资料'};
  const requestQty = profile.quantity;
  const suggestQty = profile.suggestedQty;
  const purchaseValue = finiteAmount(record.purchase_details?.amount ?? seed.amount);
  const purchaseCurrency = record.purchase_details?.currency_code ??
    record.currency_code ?? (record.id.startsWith('DEMO-') ? 'USD' : null);
  const currentUnitCost = evaluationReady ? evaluationState?.unitPurchaseCostCny ?? null : null;
  const estimatedPurchaseCny = currentUnitCost !== null && currentUnitCost >= 0 &&
    requestQty != null && Number.isInteger(requestQty) && requestQty > 0
    ? currentUnitCost * requestQty : null;
  const purchaseAmount = purchaseValue !== null && purchaseCurrency
    ? `${purchaseCurrency} ${numberText(purchaseValue, 2)}`
    : estimatedPurchaseCny !== null ? `CNY ${numberText(estimatedPurchaseCny, 2)}` : '—';
  // Estimate using verified historical net profit per paid unit; it is a forecast,
  // not an approved purchase quote nor the frozen approval scoring snapshot.
  const estimatedTotalProfit = evaluationReady && evaluationState?.unitProfitUsd != null &&
    requestQty != null && Number.isInteger(requestQty) && requestQty > 0
    ? evaluationState.unitProfitUsd * requestQty : null;
  // PURCHASE_AMOUNT_COST_LOOKUP_V4
  // Read-only: account + store + Item ID -> SKU -> CNY purchase cost.
  const costQty = typeof requestQty === 'number' &&
    Number.isSafeInteger(requestQty) && requestQty > 0
      ? requestQty : null;

  const costKey = isInitial && account && store && item && costQty !== null
    ? JSON.stringify([record.id, account, store, item, costQty, profile.sku])
    : null;

  const [costResult, setCostResult] = useState<{
    key: string; amount: number | null; reason: string;
  } | null>(null);

  useEffect(() => {
    if (!costKey || !account || !store || !item || costQty === null) return;
    let active = true;
    const qty = costQty;

    const finish = (amount: number | null, reason: string) => {
      if (active) setCostResult({key: costKey, amount, reason});
    };

    void (async () => {
      try {
        const listings = await fetchListingManagementRows({
          stores: [store], searchType: 'productId',
          keyword: item, page: 1, pageSize: 100,
        });
        if (listings.meta.total > listings.rows.length) {
          finish(null, '商品查询结果不完整'); return;
        }

        const matches = listings.rows.filter(row =>
          row.sourceAccountRef === account &&
          row.storeId === store &&
          row.productId === item
        );
        if (matches.length !== 1) {
          finish(null, '商品身份未匹配或不唯一'); return;
        }

        const sku = matches[0].sku?.trim();
        if (!sku || sku === '-') {
          finish(null, '商品未关联采购SKU'); return;
        }
        if (profile.sku && profile.sku !== '—' &&
            profile.sku.trim() !== sku) {
          finish(null, '申请快照与Listing的SKU不一致'); return;
        }

        const products = await listProductManagementSkus({
          searchType: 'sku', keyword: sku,
        }, 1, 100);

        if (products.total > products.rows.length) {
          finish(null, '采购价查询结果不完整'); return;
        }

        const exact = products.rows.filter(row => row.sku?.trim() === sku);
        if (exact.length !== 1) {
          finish(null, '产品管理SKU未匹配或不唯一'); return;
        }

        const price = exact[0].purchasePrice?.trim() ?? '';
        const match = /^¥\s*([\d,]+(?:\.\d+)?)$/.exec(price);
        const unit = match ? Number(match[1].replace(/,/g, '')) : null;

        if (unit === null || !Number.isFinite(unit) || unit <= 0) {
          finish(null, '采购价缺失或无成本查看权限'); return;
        }

        const amount = unit * qty;
        if (!Number.isFinite(amount) ||
            amount > Number.MAX_SAFE_INTEGER) {
          finish(null, '采购金额无效'); return;
        }

        finish(amount, '产品管理当前采购价 × 申请数量 · CNY');
      } catch {
        finish(null, '采购价读取失败或无查看权限');
      }
    })();

    return () => {active = false;};
  }, [costKey, account, store, item, costQty, profile.sku]);

  const matchedCost = costResult?.key === costKey ? costResult : null;

  const resolvedPurchaseAmount = purchaseAmount !== '—'
    ? purchaseAmount
    : matchedCost?.amount != null
      ? `CNY ${numberText(matchedCost.amount, 2)}`
      : '—';

  const resolvedPurchaseNote = purchaseAmount !== '—'
    ? '采购申请已记录金额'
    : matchedCost?.reason ??
      (costKey ? '正在读取采购价…' : '商品身份或数量未核实');

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
  const referenceHasCorrection = Boolean(referenceEvidence?.frozen &&
    (['speed','ad','profit','trust'] as const).some(key => {
      const from = referenceEvidence.system_dimensions[key];
      const to = referenceEvidence.effective_dimensions[key];
      return from != null && to != null && Number.isFinite(Number(from)) &&
        Number.isFinite(Number(to)) && Number(from) !== Number(to);
    }));
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
      <div className="purchase-decision__metrics">
        {isInitial ? <>
          <Metric label="综合测评分数" value={profile.scoreTotal == null ? '—' : numberText(profile.scoreTotal, 2)} description={profile.initialGrade ? `${profile.initialGrade} 级 · 申请时评级` : '评级待确认'} extra={<>
      {profile.initialGrade && <span className="purchase-decision__score-grade">{profile.initialGrade}{"\u7ea7"}</span>}
      {referenceEvidence?.frozen && <span className={referenceHasCorrection ? "purchase-decision__score-revised" : "purchase-decision__score-untouched"}>{referenceHasCorrection ? "\u5df2\u4fee\u6b63" : "\u672a\u4fee\u6539"}</span>}
    </>} />
          <Metric label="申请采购数量" value={requestQty == null ? '—' : `${numberText(requestQty)} 件`} description={`系统建议 ${suggestQty == null ? '—' : `${numberText(suggestQty)} 件`}`} />
          <Metric label="预计采购金额" value={resolvedPurchaseAmount} description="" />
          <Metric label="预计总利润" value={money(estimatedTotalProfitCny, 'CNY')} description="" />
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
          {isInitial ? <>{/* PURCHASE_APPROVAL_REFERENCE_V1 */}<InitialAnalysis profile={profile} product={evaluationProduct} loading={evaluationLoading} hasIdentity={Boolean(identityKey)} preloadedDaily={warmed?.daily}/><PurchaseApprovalEvidence record={record}/></> : isReplenishment ? <ReplenishmentAnalysis profile={profile} seed={seed}/> : <Panel title="经营分析"><div className="purchase-decision__empty">采购类型尚未确认，无法确定对应的审批评估指标。</div></Panel>}
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

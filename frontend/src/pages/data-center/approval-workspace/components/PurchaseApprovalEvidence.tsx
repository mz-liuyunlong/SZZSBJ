/** Read-only as-submitted evidence for initial-purchase approval. Never rescore. */
import { useState } from 'react';
import { SafetyCertificateOutlined, BarChartOutlined, CheckSquareOutlined, InboxOutlined, UnorderedListOutlined, FileTextOutlined } from '@ant-design/icons';
import type { ApprovalItem, PurchaseApprovalEvidenceView } from '../approvalTypes';
import { Modal } from 'antd';
import './PurchaseApprovalEvidence.css';

type Dimension = 'speed' | 'ad' | 'profit' | 'trust' | 'market';
const dimensions: Array<{key: Dimension; label: string}> = [
  {key:'speed', label:'出单速度'},
  {key:'ad', label:'广告有效性'},
  {key:'profit', label:'利润空间'},
  {key:'trust', label:'数据可信度'},
  {key:'market', label:'市场竞争评分'},
];
const asScore = (value: string | null | undefined): number | null => {
  if (value == null || value.trim() === '') return null;
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 && n <= 10 ? n : null;
};
const shown = (value: number | null) => value == null ? '—' : value.toFixed(2);
const isRecorded = (value: string | null | undefined) => Boolean(value?.trim());

/** Exported for component tests; counts describe actual net edits, not historical edit events. */
export function evidenceDimensionStatus(evidence: PurchaseApprovalEvidenceView, key: Dimension) {
  const current = asScore(evidence.effective_dimensions?.[key]);
  const original = key === 'market' ? null : asScore(evidence.system_dimensions?.[key]);
  return {
    current, original,
    status: key === 'market' ? (current == null ? 'missing' : 'manual') :
      current == null || original == null ? 'missing' :
      Math.abs(current - original) > 0.000001 ? 'changed' : 'unchanged',
  } as const;
}

export function shouldShowPurchaseReason(requested: number | null | undefined, suggested: number | null | undefined): boolean {
  return Number.isSafeInteger(requested) && Number.isSafeInteger(suggested) && requested !== suggested;
}

function Badges({values, tone}: {values: string[]; tone: 'red'|'blue'}) {
  return <div className="purchase-evidence__pills">{values.map((value, index) =>
    <span className={`purchase-evidence__pill purchase-evidence__pill--${tone}`} key={`${value}-${index}`}>{value}</span>)}</div>;
}

function RiskRow({evidence}: {evidence: PurchaseApprovalEvidenceView}) {
  const manual = evidence.manual_risks;
  const system = evidence.system_risks ?? [];
  const recordedNone = Array.isArray(manual) && manual.length === 1 && manual[0] === '无';
  const actual = [...new Set([...(manual ?? []).filter(value => value !== '无'), ...system])];
  const isNone = recordedNone && actual.length === 0;
  return <div className="purchase-evidence__entry">
    <div className="purchase-evidence__entry-label"><span className="purchase-evidence__entry-icon" aria-hidden="true"><SafetyCertificateOutlined/></span>风险条件</div>
    <div className="purchase-evidence__entry-body purchase-evidence__entry-body--risk">
      <div className="purchase-evidence__risk-status">
        <strong>风险条件：</strong>{actual.length > 0 ? <><span className="purchase-evidence__pill purchase-evidence__pill--red">有（{actual.length} 项）</span></> :
        isNone ? <span className="purchase-evidence__pill purchase-evidence__pill--green">无</span> :
        <span className="purchase-evidence__pill purchase-evidence__pill--muted">未核实</span>}
      </div>
      {actual.length > 0 && <div className="purchase-evidence__risk-tags">
        <strong>风险标签：</strong><Badges values={actual} tone="red"/>
      </div>}
    </div>
  </div>;
}

function MarketRow({evidence}: {evidence: PurchaseApprovalEvidenceView}) {
  const none = evidence.no_competitors === true;
  const ids = !none && evidence.no_competitors === false ? evidence.competitor_ids ?? [] : [];
  const status = none ? <span className="purchase-evidence__pill purchase-evidence__pill--red">无</span> :
    ids.length ? <span className="purchase-evidence__pill purchase-evidence__pill--green">已填写（{ids.length} 个）</span> :
    <span className="purchase-evidence__pill purchase-evidence__pill--muted">未核实</span>;
  return <div className="purchase-evidence__entry">
    <div className="purchase-evidence__entry-label"><span className="purchase-evidence__entry-icon" aria-hidden="true"><BarChartOutlined/></span>市场竞争判断</div>
    <div className="purchase-evidence__entry-body purchase-evidence__entry-body--market">
      <div className="purchase-evidence__market-reason">
        <strong>市场评分依据：</strong><span>{evidence.market_reason || '未记录'}</span>
      </div>
      <div className="purchase-evidence__competitors">
        <strong>竞品 ID：</strong>{status}
        {ids.length > 0 && <Badges values={ids} tone="blue"/>}
      </div>
    </div>
  </div>;
}

function ConclusionRow({evidence, record}: {evidence:PurchaseApprovalEvidenceView; record:ApprovalItem}) {
  const manual = evidence.manual_conclusion;
  const decision = manual?.decision?.trim();
  const isPassed = decision != null && /^(passed|pass|approved|测评通过|通过)$/i.test(decision);
  const isFailed = decision != null && /^(failed|fail|rejected|测评未通过|不通过)$/i.test(decision);
  const grade = record.purchase_details?.initial_grade;
  return <div className="purchase-evidence__entry">
    <div className="purchase-evidence__entry-label"><span className="purchase-evidence__entry-icon" aria-hidden="true"><CheckSquareOutlined/></span>人工测评结论</div>
    <div className="purchase-evidence__entry-body">
      <div className="purchase-evidence__conclusion"><strong>测评结论：</strong>{decision ?
        <span className={`purchase-evidence__pill purchase-evidence__pill--${isPassed?'green':isFailed?'red':'blue'}`}>
          {isPassed?'测评通过':isFailed?'测评未通过':decision}</span> :
        <span className="purchase-evidence__pill purchase-evidence__pill--muted">人工结论未记录</span>}
        {!decision && grade && <span className="purchase-evidence__caption">申请时评级 {grade}，不能代替人工结论</span>}
      </div>
      {isRecorded(manual?.reason) && <p><strong>人工测评原因：</strong>{manual?.reason}</p>}
    </div>
  </div>;
}

function ReasonRow({record}: {record:ApprovalItem}) {
  const requested = record.purchase_details?.requested_qty;
  const suggested = record.purchase_details?.suggested_qty;
  if (!shouldShowPurchaseReason(requested, suggested)) return null;
  return <div className="purchase-evidence__entry">
    <div className="purchase-evidence__entry-label"><span className="purchase-evidence__entry-icon" aria-hidden="true"><InboxOutlined/></span>采购申请说明</div>
    <div className="purchase-evidence__entry-body">
      <div className="purchase-evidence__qty">
        <strong>申请采购数量：{requested} 件</strong><span aria-hidden="true">｜</span>
        <strong>系统建议采购量：{suggested} 件</strong>
      </div>
      {record.reason?.trim() ? <p><strong>采购数量调整原因：</strong>{record.reason}</p> :
        <p className="purchase-evidence__missing">采购数量不同于系统建议，但申请说明未记录</p>}
    </div>
  </div>;
}

export default function PurchaseApprovalEvidence({record}: {record: ApprovalItem}) {
  const evidence = record.purchase_details?.approval_evidence;
  const [expanded, setExpanded] = useState<Dimension|null>(null);
  // PURCHASE_APPROVAL_REFERENCE_V2: preserve frozen proof.
  // The list response intentionally lacks as-of audit details; do not show current data as a substitute.
  if (!evidence?.frozen) return <section className="purchase-evidence purchase-evidence--pending">
    <h3>审批依据摘要</h3><p>正在读取采购申请时的评分及审计记录；未核实的信息不展示。</p>
  </section>;
  const states = dimensions.map(({key,label}) => ({key,label,...evidenceDimensionStatus(evidence,key)}));
  const changed = states.filter(s=>s.status==='changed').length;
  const unchanged = states.filter(s=>s.status==='unchanged').length;
  const manual = states.filter(s=>s.status==='manual').length;
  const missing = states.filter(s=>s.status==='missing').length;
  return <div className="purchase-evidence">
    <section className="purchase-evidence__scores" aria-label="五维测评分数（含人工修正记录）">
      <header className="purchase-evidence__heading">
        <h3><span className="purchase-evidence__heading-icon" aria-hidden="true"><UnorderedListOutlined/></span>五维测评分数（含人工修正记录）</h3>
        <div className="purchase-evidence__stats">
          <span>已修改：{changed} 项</span><span>未修改：{unchanged} 项</span>
          <span>人工填写：{manual} 项</span>{missing>0&&<span>未核实：{missing} 项</span>}
        </div>
      </header>
      <div className="purchase-evidence__cards">
        {states.map(({key,label,original,current,status}) => {
          const history = evidence.correction_history.filter(item=>item.dimension===key);
          const last = history.length ? history[history.length-1] : undefined;
          const hasHistory = history.length>0;
          return <div key={key} className={`purchase-evidence__score-card ${key==='market'?'is-market':''}`}>
            <div className="purchase-evidence__score-head"><strong>{label}</strong><span>权重 {evidence.weights?.[key] == null ? '—' : `${evidence.weights[key]}%`}</span></div>
            <div className={`purchase-evidence__state purchase-evidence__state--${status}`}>
              {status==='manual'?'人工填写':status==='changed'?'已修改':status==='unchanged'?'未修改':'未核实'}</div>
            <div className="purchase-evidence__score-numbers">
              {status==='changed'&&<><b>{shown(original)}</b><span className="purchase-evidence__arrow">→</span></>}
              <strong>{shown(current)}</strong><span>/10</span>
            </div>
            {status==='changed' ? <>
              <div className="purchase-evidence__correction-preview"><strong>修正原因</strong><p>{last?.reason || '修正记录缺少原因'}</p></div>
              {hasHistory && <button type="button" className="purchase-evidence__history-toggle"
                aria-expanded={expanded===key} onClick={()=>setExpanded(expanded===key?null:key)}>
                  {expanded===key?'收起':'查看'}修正记录（{history.length}）</button>}
            </> : <div className="purchase-evidence__unchanged-caption">
              {status==='manual'?'申请前人工填写的市场评分':status==='missing'?'评分证据未核实':hasHistory?'已恢复系统原始评分':'系统自动评分'}</div>}

          </div>;
        })}
      </div>
      {/* Render in Ant Design portal: never clip audit history under scrolling cards. */}
      <Modal
        rootClassName="purchase-evidence__history-modal"
        open={expanded !== null}
        title={`评分修正记录 · ${dimensions.find(d => d.key === expanded)?.label ?? ''}`}
        footer={null}
        width={620}
        onCancel={() => setExpanded(null)}
      >
        <div className="purchase-evidence__history-list">
          {evidence.correction_history.filter(item => item.dimension === expanded)
            .map((event, index) => <div key={`${event.dimension}-${event.revision ?? index}`}>
              <b>{shown(asScore(event.before))} → {shown(asScore(event.after))}</b>
              <p>{event.reason || '未记录修正说明'}</p>
              <small>{event.actor_id || '操作人待核实'} · {event.at || '时间待核实'}</small>
            </div>)}
        </div>
      </Modal>
    </section>
    <section className="purchase-evidence__summary" aria-label="审批依据摘要">
      <header className="purchase-evidence__heading"><h3><span className="purchase-evidence__heading-icon" aria-hidden="true"><FileTextOutlined/></span>审批依据摘要</h3><span className="purchase-evidence__caption">申请时留存 · 只读</span></header>
      <div className="purchase-evidence__entries">
        <RiskRow evidence={evidence}/>
        <MarketRow evidence={evidence}/>
        <ConclusionRow evidence={evidence} record={record}/>
        <ReasonRow record={record}/>
      </div>
    </section>
  </div>;
}

// PURCHASE_APPROVAL_LAYOUT_ALIGNMENT_V1

// PURCHASE_RISK_MARKET_DETAIL_ALIGNMENT_V2

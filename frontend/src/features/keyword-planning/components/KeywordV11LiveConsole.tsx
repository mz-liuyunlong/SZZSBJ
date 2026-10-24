/**
 * Real-data V1.1 extension for the existing keyword analysis page.
 * No mock scores and no official upload flow. Mounted as the default launch
 * experience; the old browser-only draft is explicitly separated.
 */
import { useCallback, useEffect, useState, type ChangeEvent } from 'react';
import {
  Alert, Button, Card, Descriptions, Input, InputNumber, Space, Table, Tabs,
  Tag, Typography, Upload, Select, message,
} from 'antd';
import { CloudUploadOutlined, DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import { searchListingsForSku, searchProductsBySku,
  type ListingCandidate } from '@/features/keyword-planning/keywordProductLookup';
import type { ProductManagementRow } from '@/pages/products/productManagementTypes';
import {
  createKeywordAnalysis, createKeywordRuleDraft, DEFAULT_DRAFT_LIMITS,
  downloadKeywordInternalWorkbook, getKeywordRun, listKeywordRuleSets,
  listKeywordRuleVersions, listRunKeywords, listKeywordRuns,
  preflightKeywordAnalysis, uploadKeywordSourceXlsx,
  confirmStoredKeywordFacts, getKeywordSourceState, importStoredAsin,
  type CreateKeywordAnalysisRequest, type KeywordDraftLimits,
  type KeywordPreflight, type KeywordResult, type KeywordRuleSet,
  type KeywordRuleVersion, type KeywordRun, type KeywordSourceState,
  type ConfirmedKeywordField,
} from '@/api/keywordPlanningV11Api';

type SourceForm = Omit<CreateKeywordAnalysisRequest, 'request_key'>;
type ErrorLike = { code?: string; message?: string };

const defaultForm: SourceForm = {
  source_account_ref: '', product_id: '', item_id: '', product_fact_snapshot_id: '',
  rule_version_id: '', upload_file_id: '',
};
const initialForm = (): SourceForm => {
  try {
    const saved = JSON.parse(sessionStorage.getItem('kw-v11-selected-product') || '{}') as Partial<SourceForm>;
    return {...defaultForm,source_account_ref:saved.source_account_ref || '',product_id:saved.product_id || ''};
  } catch { return defaultForm; }
};

/** This panel is a real backend client, not a parallel browser-side scoring engine. */
export function KeywordV11LiveConsole() {
  const [form, setForm] = useState<SourceForm>(initialForm);
  const [working, setWorking] = useState(false);
  const [preflight, setPreflight] = useState<KeywordPreflight | null>(null);
  const [runs, setRuns] = useState<KeywordRun[]>([]);
  const [runPage, setRunPage] = useState(1);
  const [runTotal, setRunTotal] = useState(0);
  const [active, setActive] = useState<KeywordRun | null>(null);
  const [keywords, setKeywords] = useState<KeywordResult[]>([]);
  const [keywordPage, setKeywordPage] = useState(1);
  const [keywordTotal, setKeywordTotal] = useState(0);
  const [rulesets, setRulesets] = useState<KeywordRuleSet[]>([]);
  const [versions, setVersions] = useState<KeywordRuleVersion[]>([]);
  const [ruleSetId, setRuleSetId] = useState('');
  const [limits, setLimits] = useState<KeywordDraftLimits>(DEFAULT_DRAFT_LIMITS);
  const [sourceState, setSourceState] = useState<KeywordSourceState | null>(null);
  const [decodoSnapshotId, setDecodoSnapshotId] = useState('');
  const [asinSnapshotId, setAsinSnapshotId] = useState('');
  const [asin, setAsin] = useState('');
  const [riskAcknowledged, setRiskAcknowledged] = useState(false);
  const [facts, setFacts] = useState<Record<string, string>>({});
  const [reviewPhrase,setReviewPhrase]=useState('');
  const [reviewType,setReviewType]=useState('人工确认词');
  const [reviewRef,setReviewRef]=useState('');
  const [reviewPagePhrase,setReviewPagePhrase]=useState('');
  const [reviewHardRisk,setReviewHardRisk]=useState(false);
  const [reviewedPhrases,setReviewedPhrases]=useState<Array<{
    phrase:string;keyword_type:string;evidence_ref:string;hard_risk_proven:boolean;page_phrase?:string;
  }>>([]);
  const [notification, holder] = message.useMessage();
  const [skuQuery, setSkuQuery] = useState('');
  const [productOptions, setProductOptions] = useState<ProductManagementRow[]>([]);
  const [listingOptions, setListingOptions] = useState<ListingCandidate[]>([]);

  const setField = (field: keyof SourceForm, value: string) => {
    setForm(previous => ({ ...previous, [field]: value.trim() }));
    setPreflight(null);
    if(field==='source_account_ref'||field==='product_id'){
      setRuns([]);setRunPage(1);setRunTotal(0);
      setActive(null);setKeywords([]);setKeywordPage(1);setKeywordTotal(0);setSourceState(null);
    }
  };

  useEffect(() => {
    sessionStorage.setItem('kw-v11-selected-product',JSON.stringify({
      source_account_ref:form.source_account_ref,product_id:form.product_id,
    }));
  },[form.source_account_ref,form.product_id]);

  const handleError = useCallback((error: unknown) => {
    const known = error as ErrorLike | null;
    notification.error(known?.code || known?.message || '请求失败，请检查权限和数据来源');
  }, [notification]);

  const perform = useCallback(async (task: () => Promise<void>) => {
    if (working) return;
    setWorking(true);
    try { await task(); } catch (error) { handleError(error); }
    finally { setWorking(false); }
  }, [working, handleError]);

  const refreshRuns = async (page = 1) => {
    const result = await listKeywordRuns(form.product_id, form.source_account_ref, 20, (page - 1) * 20);
    setRuns(result.items);
    setRunPage(page);
    setRunTotal(result.total);
  };

  // Reload persisted history when the selected product/account changes. An old
  // browser session is never the source of truth for analysis or approvals.
  useEffect(() => {
    if (!form.product_id || !form.source_account_ref) {
      return;
    }
    let cancelled = false;
    Promise.all([
      listKeywordRuns(form.product_id, form.source_account_ref),
      getKeywordSourceState(form.product_id, form.source_account_ref),
    ]).then(([history, state]) => {
      if (cancelled) return;
      setRuns(history.items); setRunPage(1); setRunTotal(history.total); setSourceState(state);
      if (state.latest_confirmed_fact_id) {
        setForm(previous => ({...previous,
          product_fact_snapshot_id: state.latest_confirmed_fact_id ?? previous.product_fact_snapshot_id,
          item_id: state.item_id ?? previous.item_id,
          upload_file_id: state.latest_upload_id ?? previous.upload_file_id,
        }));
      }
    }).catch(() => {
      if (!cancelled) { setRuns([]); setRunTotal(0); setSourceState(null); }
    });
    return () => { cancelled = true; };
  }, [form.product_id, form.source_account_ref]);

  const refreshRules = async () => {
    const result = await listKeywordRuleSets(form.source_account_ref);
    setRulesets(result);
  };

  const selectRun = (run: KeywordRun) => perform(async () => {
    const [detail, result] = await Promise.all([
      getKeywordRun(run.run_id, form.source_account_ref),
      listRunKeywords(run.run_id, form.source_account_ref, 50, 0),
    ]);
    setActive(detail);
    setKeywords(result.items);
    setKeywordPage(1);
    setKeywordTotal(result.total);
  });

  const importFile = (file: File) => {
    void perform(async () => {
      const result = await uploadKeywordSourceXlsx(
        file, form.source_account_ref, form.product_id, form.product_fact_snapshot_id,
      );
      setField('upload_file_id', result.upload_id);
      notification.success(`原始数据已保存：${result.source_rows} 行，状态 ${result.status}`);
    });
    return false;
  };

  const createRun = () => perform(async () => {
    // Each deliberate click gets a distinct idempotency key; retries should
    // reuse the same request_key from the original network attempt if needed.
    const requestKey = crypto.randomUUID();
    const result = await createKeywordAnalysis({ ...form, request_key: requestKey });
    notification.success(`分析批次 ${result.status}，共 ${result.keyword_count} 个关键词`);
    await refreshRuns();
    const detail = await getKeywordRun(result.run_id, form.source_account_ref);
    setActive(detail);
    const list = await listRunKeywords(result.run_id, form.source_account_ref, 50, 0);
    setKeywords(list.items);
    setKeywordPage(1);
    setKeywordTotal(list.total);
  });

  const header = [
    ['source_account_ref', '账户范围'], ['product_id', '产品 UUID'],
    ['item_id', 'Walmart Item ID'], ['product_fact_snapshot_id', '已确认商品快照 UUID'],
    ['rule_version_id', '规则版本 UUID'], ['upload_file_id', '关键词原文件 UUID'],
  ] as const;

  const factFields = [
    'title', 'item_type', 'brand', 'material', 'color', 'pack',
    'size', 'structure', 'use', 'owner',
  ];
  const keywordTypes = [
    '核心本体词','核心材质长尾词','核心场景长尾词','核心规格/数量词','精准长尾词',
    '同义表达词','复数变体词','拼写变体词','相邻结构词','相邻用途词','次级场景词',
    '泛流量词','品牌/竞品词','配件/替换词','错货架词','结构冲突词','材质不符词',
    '规格/尺寸不符词','Pack/数量不符词','颜色/款式不符词','合规/认证风险词',
    '机器设备词','食材本身词','低价值重复词','人工确认词',
  ];

  const confirmFacts = () => perform(async () => {
    const fields: Record<string, ConfirmedKeywordField> = {};
    for (const key of factFields) {
      const value = facts[key]?.trim();
      if (!value) throw new Error(`缺少已核对商品字段：${key}`);
      fields[key] = { value, source: 'operator' };
    }
    const receipt = await confirmStoredKeywordFacts({
      source_account_ref: form.source_account_ref, product_id: form.product_id,
      item_id: form.item_id, decodo_snapshot_id: decodoSnapshotId,
      fields, risk_boundary_mode: 'none',
      risk_boundary_acknowledged: riskAcknowledged, semantic_phrases: reviewedPhrases,
    });
    setField('product_fact_snapshot_id', receipt.product_fact_snapshot_id);
    setSourceState(await getKeywordSourceState(form.product_id, form.source_account_ref));
    notification.success('已确认并保存商品来源快照；未调用外部采集 API');
  });

  const sourceTab = <Space direction="vertical" size="middle" style={{ width: '100%' }}>
    <Alert type="info" showIcon message="只使用真实且已确认的数据。上传 Excel 前必须已确认商品事实，且后台已显式开放安全写入。" />
    <Card size="small" title="从现有商品 / Listing API 选择真实身份">
      <Space wrap>
        <Input aria-label="搜索 SKU" placeholder="输入 SKU（至少 2 字符）" value={skuQuery}
          onChange={event=>setSkuQuery(event.target.value)}/>
        <Button loading={working} onClick={()=>void perform(async()=>{
          setProductOptions(await searchProductsBySku(skuQuery));setListingOptions([]);
        })}>搜索商品</Button>
      </Space>
      <Table size="small" rowKey="id" pagination={false} dataSource={productOptions}
        columns={[{title:'SKU',dataIndex:'sku'},{title:'商品名称',dataIndex:'productName'},
          {title:'选择',render:(_:unknown,row:ProductManagementRow)=><Button type="link" onClick={()=>void perform(async()=>{
            setField('product_id',row.id);
            const matches=await searchListingsForSku(row.sku||'');
            setListingOptions(matches.candidates);
            matches.warnings.forEach(warning=>notification.warning(warning));
          })}>选择并查找 Listing</Button>}]}/>
      <Table size="small" rowKey={row=>`${row.listing.id}-${row.listing.productId}`}
        pagination={false} dataSource={listingOptions}
        columns={[{title:'店铺',render:(_:unknown,row:ListingCandidate)=>row.listing.store},
          {title:'Item ID',render:(_:unknown,row:ListingCandidate)=>row.listing.productId},
          {title:'匹配依据',dataIndex:'label'},
          {title:'选择',render:(_:unknown,row:ListingCandidate)=><Button type="link" onClick={()=>{
            if(row.listing.isArchived){notification.warning('归档 Listing 不作为当前分析来源');return;}
            setField('item_id',row.listing.productId);
          }}>确认 Item ID</Button>}]}/>
      <Alert type="warning" showIcon message="商品、Listing 候选均来自现有后端；账户归属与 Item ID 最终由后端强校验。模糊 MSKU 候选必须人工核对。"/>
    </Card>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(260px,1fr))', gap: 12 }}>
      {header.map(([key, title]) => (
        <label key={key} style={{ display: 'block' }}>
          <Typography.Text type="secondary">{title}</Typography.Text>
          <Input style={{ marginTop: 5 }} value={form[key]} placeholder={`请输入${title}`}
            onChange={(event: ChangeEvent<HTMLInputElement>) => setField(key, event.target.value)} />
        </label>
      ))}
    </div>
    <Card size="small" title="已留存的商品来源（刷新页面后自动读取）">
      <Descriptions size="small" column={2}>
        <Descriptions.Item label="商品事实">{sourceState?.latest_confirmed_fact_id || '未确认'}</Descriptions.Item>
        <Descriptions.Item label="关键词文件">{sourceState?.latest_upload_id || '未上传'}</Descriptions.Item>
        <Descriptions.Item label="已保存 ASIN">{sourceState?.asin_reference_count ?? 0}</Descriptions.Item>
        <Descriptions.Item label="来源状态">{sourceState?.source_status || '待查询'}</Descriptions.Item>
      </Descriptions>
      <Alert type="warning" showIcon message="商品事实只可由已保存且验证通过的 Decodo 快照与人工核对共同确认；当前无法从本页自动抓取。" />
      <Input style={{marginTop:12}} aria-label="已验证 Decodo 快照 UUID" placeholder="已验证 Decodo 快照 UUID"
        value={decodoSnapshotId} onChange={event=>setDecodoSnapshotId(event.target.value.trim())} />
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(240px,1fr))', gap:8, marginTop:12 }}>
        {factFields.map(key => <Input key={key} aria-label={`已核对 ${key}`} placeholder={`已核对 ${key}`}
          value={facts[key] || ''} onChange={event=>setFacts(current=>({...current,[key]:event.target.value}))} />)}
      </div>
      <label style={{display:'block',marginTop:12}}><input type="checkbox" checked={riskAcknowledged}
        onChange={event=>setRiskAcknowledged(event.target.checked)} /> 我确认尚未提供完整禁用词边界；结果只用于内部复核</label>
      <Card size="small" title="逐词证据复核 · 25 类候选" style={{marginTop:12}}>
        <Alert type="info" showIcon message="只记录人工核对的短语与证据。未证明的类别仍为人工确认词；自有品牌须另由批准品牌清单证明。保存新商品事实后，请创建新的分析批次，历史批次不变。" />
        <Space wrap style={{marginTop:12}}>
          <Input aria-label="复核关键词短语" placeholder="复核短语" value={reviewPhrase} onChange={e=>setReviewPhrase(e.target.value)}/>
          <Select aria-label="复核关键词类型" value={reviewType} style={{width:190}}
            options={keywordTypes.map(value=>({label:value,value}))} onChange={setReviewType}/>
          <Input aria-label="复核证据编号" placeholder="证据编号" value={reviewRef} onChange={e=>setReviewRef(e.target.value)}/>
          <Input aria-label="页面匹配短语" placeholder="页面标题真实短语（可空）" value={reviewPagePhrase}
            onChange={e=>setReviewPagePhrase(e.target.value)}/>
          <label><input type="checkbox" checked={reviewHardRisk} onChange={e=>setReviewHardRisk(e.target.checked)}/> 已证明硬风险</label>
          <Button onClick={()=>{
            if(!reviewPhrase.trim()||!reviewRef.trim())return notification.warning('短语和证据编号必填');
            if(reviewType==='品牌/竞品词')return notification.warning('品牌必须通过独立批准品牌清单核验');
            if(reviewedPhrases.some(item=>item.phrase===reviewPhrase.trim()&&
              item.keyword_type===reviewType&&item.evidence_ref===reviewRef.trim())){
              return notification.warning('相同短语、类型和证据已经加入');
            }
            setReviewedPhrases(current=>[...current,{phrase:reviewPhrase.trim(),keyword_type:reviewType,
              evidence_ref:reviewRef.trim(),hard_risk_proven:reviewHardRisk,
              ...(reviewPagePhrase.trim()?{page_phrase:reviewPagePhrase.trim()}:{})}]);
            setReviewPhrase('');setReviewRef('');setReviewPagePhrase('');setReviewHardRisk(false);
          }}>加入本次复核</Button>
        </Space>
        <Table size="small" rowKey={row=>`${row.phrase}:${row.keyword_type}:${row.evidence_ref}`}
          pagination={{pageSize:8}} dataSource={reviewedPhrases}
          columns={[{title:'短语',dataIndex:'phrase'},{title:'类型',dataIndex:'keyword_type'},
            {title:'证据',dataIndex:'evidence_ref'},{title:'页面短语',dataIndex:'page_phrase'},
            {title:'操作',render:(_:unknown,row:typeof reviewedPhrases[number])=><Button type="link"
              onClick={()=>setReviewedPhrases(current=>current.filter(item=>item!==row))}>移除</Button>}]}/>
      </Card>
      <Button style={{marginTop:8}} disabled={!riskAcknowledged || !decodoSnapshotId || working}
        onClick={()=>void confirmFacts()}>确认并保存商品事实</Button>
      <Space.Compact style={{display:'flex',marginTop:12}}>
        <Input aria-label="ASIN" placeholder="ASIN" value={asin} onChange={event=>setAsin(event.target.value.trim())}/>
        <Input aria-label="Amazon 来源快照 UUID" placeholder="已保存 Amazon 来源快照 UUID" value={asinSnapshotId}
          onChange={event=>setAsinSnapshotId(event.target.value.trim())}/>
        <Button disabled={!asin || !asinSnapshotId || working} onClick={()=>void perform(async()=>{
          const result=await importStoredAsin({source_account_ref:form.source_account_ref,
            product_id:form.product_id,asin,decodo_snapshot_id:asinSnapshotId});
          notification.success(`已保存 ${result.image_count} 张来源图片，不代表 ASIN 授权通过`);
          setSourceState(await getKeywordSourceState(form.product_id,form.source_account_ref));
        })}>导入已保存 ASIN</Button>
      </Space.Compact>
    </Card>
    <Space wrap>
      <Upload showUploadList={false} accept=".xlsx" beforeUpload={importFile}>
        <Button icon={<CloudUploadOutlined />} loading={working}>上传并留存原始 Excel</Button>
      </Upload>
      <Button loading={working} onClick={() => void perform(async () => {
        setPreflight(await preflightKeywordAnalysis(form));
      })}>检查分析条件</Button>
    </Space>
    {preflight && <Card size="small" title="分析前置核验">
      <Descriptions size="small" column={2}>
        <Descriptions.Item label="唯一候选词数">{preflight.candidate_count}</Descriptions.Item>
        <Descriptions.Item label="已确认事实自动归类">{preflight.automatic_evidence_count}</Descriptions.Item>
        <Descriptions.Item label="人工证据归类">{preflight.reviewed_evidence_count}</Descriptions.Item>
        <Descriptions.Item label="未归类待人工确认">{preflight.manual_review_count}</Descriptions.Item>
        <Descriptions.Item label="Top40 待复核">{preflight.top40_review_required}</Descriptions.Item>
        <Descriptions.Item label="可创建复核批次">{preflight.can_create_review_run ? '是' : '否'}</Descriptions.Item>
        <Descriptions.Item label="可输出正式文件">否（待审批）</Descriptions.Item>
      </Descriptions>
      <Space wrap>{preflight.review_reason_codes.map(code => <Tag key={code}>{code}</Tag>)}</Space>
    </Card>}
  </Space>;

  const runTab = <Space direction="vertical" size="middle" style={{ width: '100%' }}>
    <Space wrap>
      <Button icon={<ReloadOutlined />} onClick={() => void perform(() => refreshRuns(runPage))} loading={working}>读取历史批次</Button>
      <Button type="primary" disabled={!preflight?.can_create_review_run} loading={working}
        onClick={createRun}>创建复核分析批次</Button>
      <Button icon={<DownloadOutlined />} disabled={!active || active.status === 'queued' || active.status === 'running'}
        onClick={() => void perform(() => downloadKeywordInternalWorkbook(active!.run_id, form.source_account_ref))}>
        下载内部五表（非官方模板）
      </Button>
    </Space>
    <Table size="small" rowKey="run_id" dataSource={runs}
      pagination={{current:runPage,pageSize:20,total:runTotal,showSizeChanger:false}}
      onChange={page=>void perform(()=>refreshRuns(page.current || 1))}
      columns={[
        { title: '批次时间', dataIndex: 'created_at', render: (v: string) => v?.slice(0, 19) },
        { title: 'Item ID', dataIndex: 'item_id' },
        { title: '关键词', dataIndex: 'keyword_count' },
        { title: '状态', dataIndex: 'status', render: (v: string) => <Tag>{v}</Tag> },
        { title: '操作', render: (_: unknown, row: KeywordRun) =>
          <Button type="link" onClick={() => selectRun(row)}>查看结果</Button> },
      ]} />
    {active && <Card size="small" title={`批次 ${active.run_id}`}>
      <Alert type="warning" showIcon message="未获审批的语义分数保持为空；本页结果不代表可正式投放。" />
      <Table style={{ marginTop: 12 }} size="small" rowKey="term_id" dataSource={keywords}
        scroll={{ x: 950 }}
        pagination={{current:keywordPage,pageSize:50,total:keywordTotal,showSizeChanger:false}}
        onChange={page=>void perform(async()=>{
          const result=await listRunKeywords(active.run_id,form.source_account_ref,50,((page.current||1)-1)*50);
          setKeywords(result.items);setKeywordPage(page.current||1);setKeywordTotal(result.total);
        })}
        columns={[
          { title: '关键词', dataIndex: 'keyword', width: 220 },
          { title: '类型', dataIndex: 'primary_type', render: (v: string | null) => v || '待复核' },
          { title: '页面承接', dataIndex: 'page_coverage', render: (v: string | null) => v || '证据缺失' },
          { title: '评分', dataIndex: 'score', render: (v: number | null) => v == null ? '—' : v },
          { title: '等级', dataIndex: 'allocation_grade' },
          { title: 'Exact', dataIndex: 'exact_selected', render: (v: boolean) => v ? '是' : '否' },
          { title: 'Broad', dataIndex: 'broad_selected', render: (v: boolean) => v ? '是' : '否' },
          { title: '原因', dataIndex: 'quality_note', ellipsis: true },
        ]} />
    </Card>}
  </Space>;

  const ruleTab = <Space direction="vertical" size="middle" style={{ width: '100%' }}>
    <Alert type="warning" showIcon message="D01–D08 业务规则未独立审批前，规则只能创建草稿，不能通过本页面发布。" />
    <Button onClick={() => void perform(refreshRules)} loading={working}>读取规则集</Button>
    <Table rowKey="rule_set_id" size="small" dataSource={rulesets} pagination={false}
      columns={[
        { title: '规则', dataIndex: 'display_name' },
        { title: '范围', dataIndex: 'scope_key' },
        { title: '启用', dataIndex: 'is_enabled', render: (v: boolean) => v ? '是' : '否' },
        { title: '版本', render: (_: unknown, row: KeywordRuleSet) =>
          <Button type="link" onClick={() => void perform(async () => {
            setRuleSetId(row.rule_set_id);
            setVersions(await listKeywordRuleVersions(form.source_account_ref, row.rule_set_id));
          })}>查看版本</Button> },
      ]} />
    {ruleSetId && <>
      <Typography.Text strong>草稿配额（仅高级管理员、开发安全开关允许时可创建）</Typography.Text>
      <Space wrap>{(Object.keys(limits) as (keyof KeywordDraftLimits)[]).map(key => (
        <label key={key}>
          <Typography.Text type="secondary">{key}</Typography.Text>
          <InputNumber style={{ display: 'block' }} min={0} max={500} value={limits[key]}
            onChange={value => setLimits(current => ({...current, [key]: value ?? 0}))} />
        </label>
      ))}</Space>
      <Button disabled={working} onClick={() => void perform(async () => {
        const result = await createKeywordRuleDraft(form.source_account_ref, ruleSetId, limits);
        notification.success(`规则草稿 V${result.version_number} 已创建（未发布）`);
        setVersions(await listKeywordRuleVersions(form.source_account_ref, ruleSetId));
      })}>创建规则草稿</Button>
      <Table rowKey="version_id" size="small" dataSource={versions} pagination={false}
        columns={[
          { title: '版本', dataIndex: 'version_number' },
          { title: '状态', dataIndex: 'status', render: (v: string) => <Tag>{v}</Tag> },
          { title: '配置 SHA256', dataIndex: 'config_sha256', ellipsis: true },
          { title: '正式发布', render: () => <Button disabled>待 D01–D08 审批</Button> },
        ]} />
    </>}
  </Space>;

  return <Card title="Walmart 关键词 V1.1 · 真实数据工作台" variant="borderless">
    {holder}
    <Tabs items={[
      { key: 'sources', label: '商品与来源', children: sourceTab },
      { key: 'runs', label: '分析批次', children: runTab },
      { key: 'rules', label: '规则版本', children: ruleTab },
    ]} />
  </Card>;
}

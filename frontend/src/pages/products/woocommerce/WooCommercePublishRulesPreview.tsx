import { useEffect, useState } from "react";
import { Alert, Button, Drawer, Input, InputNumber, Spin, Switch, Typography } from "antd";
import { PlusOutlined, DeleteOutlined } from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ReportFacetSelect from "@/shared/report-filters";
import ResetButton from "@/components/report-table/ResetButton";
import { BackendRequestError } from "@/api/backendApi";
import { fetchWooRules, saveWooRules, type Rules, type RulesData, type WooOption, type BrandRule, type SubmissionRule } from "./wooCommerceProductsApi";
import "./WooCommercePublishRulesPreview.css";

const { Text } = Typography;
const options = (items: [string, string][]): WooOption[] => items.map(([value, label]) => ({ value, label }));
const listingOptions = options([["active", "正常在售"], ["review", "人工确认后刊登"]]);
const priceOptions = options([["original", "Listing售价"], ["fixed", "Listing售价 + 固定金额"], ["percent", "Listing售价 + 百分比"]]);
const errorText = (error: unknown) => error instanceof BackendRequestError ? String(error.code || "BACKEND_ERROR") : "NETWORK_ERROR";
const identity = (account: string, store: string) => JSON.stringify([account, store]);
let keyCounter = 0;
const rowKey = () => `woo-rule-${++keyCounter}`;
type Mapping = BrandRule & { key: string };
type Submission = SubmissionRule & { key: string };
type Draft = Omit<Rules, "mappings" | "submission_stores"> & { mappings: Mapping[]; submission_stores: Submission[] };
const makeDraft = (rules: Rules): Draft => ({ ...rules, mappings: rules.mappings.map(row => ({ ...row, key: rowKey() })), submission_stores: rules.submission_stores.map(row => ({ ...row, key: rowKey() })) });
const payloadOf = (draft: Draft): Rules => ({
  ...draft,
  mappings: draft.mappings.map(({ source_brand, target_store_id, target_brand_id, target_category_id, enabled }) => ({ source_brand, target_store_id, target_brand_id, target_category_id, enabled })),
  submission_stores: draft.submission_stores.map(({ source_account_ref, source_store_id, submission_store_id }) => ({ source_account_ref, source_store_id, submission_store_id })),
});

export default function WooCommercePublishRulesPreview({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [saved, setSaved] = useState<Draft | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [data, setData] = useState<RulesData | null>(null);
  const [loading, setLoading] = useState(open);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);
  const [previousRequest, setPreviousRequest] = useState({ open, reload });
  // Reset the draft before rendering a new open/retry session, not inside the effect.
  if (previousRequest.open !== open || previousRequest.reload !== reload) {
    setPreviousRequest({ open, reload });
    if (open) {
      setLoading(true); setError(""); setNotice(""); setDraft(null); setSaved(null); setData(null);
    }
  }
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    void fetchWooRules(controller.signal).then(value => {
      if (controller.signal.aborted) return;
      const next = makeDraft(value.rules);
      setSaved(next); setDraft(next); setData(value);
    }).catch(err => { if (!controller.signal.aborted) setError(`读取规则失败：${errorText(err)}`); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [open, reload]);
  const update = (patch: Partial<Draft>) => { setDraft(old => old ? { ...old, ...patch } : old); setNotice(""); };
  const editMapping = (key: string, patch: Partial<Mapping>) => setDraft(old => old ? { ...old, mappings: old.mappings.map(row => row.key === key ? { ...row, ...patch } : row) } : old);
  const editSubmission = (key: string, patch: Partial<Submission>) => setDraft(old => old ? { ...old, submission_stores: old.submission_stores.map(row => row.key === key ? { ...row, ...patch } : row) } : old);
  const select = (label: string, value: string, choices: WooOption[], onChange: (value: string) => void, allowClear = true) => (
    <ReportFacetSelect ariaLabel={label} placeholder={label} value={value || undefined} options={choices} triggerWidth="100%" allowClear={allowClear} onChange={v => onChange(typeof v === "string" ? v : "")} />
  );
  const mappings = draft?.mappings ?? [];
  const submissions = draft?.submission_stores ?? [];
  const brands = mappings.map(row => row.source_brand.trim().toLowerCase()).filter(Boolean);
  const pairs = submissions.filter(row => row.source_account_ref && row.source_store_id).map(row => identity(row.source_account_ref, row.source_store_id));
  const duplicate = new Set(brands).size !== brands.length || new Set(pairs).size !== pairs.length;
  const invalid = !draft || !data || duplicate || mappings.some(row => !row.source_brand.trim() || !row.target_store_id || !row.target_brand_id || !row.target_category_id) || submissions.some(row => !row.source_account_ref || !row.source_store_id || !row.submission_store_id.trim()) || (draft.auto_publish_enabled && (!mappings.some(row => row.enabled) || draft.stock_quantity === null));
  const dirty = Boolean(draft && saved && JSON.stringify(payloadOf(draft)) !== JSON.stringify(payloadOf(saved)));
  const submit = async () => {
    if (!draft || invalid || !dirty || saving) return;
    setSaving(true); setError(""); setNotice("");
    try {
      const result = await saveWooRules(payloadOf(draft));
      const next = makeDraft(result.rules);
      setSaved(next); setDraft(next); setData(result); setNotice("规则已保存到数据库");
    } catch (err) { setError(`保存失败：${errorText(err)}`); }
    finally { setSaving(false); }
  };
  const mappingColumns: ProColumns<Mapping>[] = [
    { title: "Listing品牌", key: "sourceBrand", width: 180, render: (_, row) => <Input value={row.source_brand} maxLength={255} placeholder="商品ID实际品牌" onChange={e => editMapping(row.key, { source_brand: e.target.value })} /> },
    { title: "目标独立站", key: "store", width: 230, render: (_, row) => select("目标独立站", row.target_store_id, data?.stores ?? [], v => editMapping(row.key, { target_store_id: v, target_brand_id: "", target_category_id: "" })) },
    { title: "目标品牌", key: "brand", width: 150, render: (_, row) => select("目标品牌", row.target_brand_id, data?.stores.find(s => s.value === row.target_store_id)?.brands ?? [], v => editMapping(row.key, { target_brand_id: v })) },
    { title: "目标分类", key: "category", width: 150, render: (_, row) => select("目标分类", row.target_category_id, data?.stores.find(s => s.value === row.target_store_id)?.categories ?? [], v => editMapping(row.key, { target_category_id: v })) },
    { title: "启用", key: "enabled", width: 72, render: (_, row) => <Switch size="small" checked={row.enabled} onChange={v => editMapping(row.key, { enabled: v })} /> },
    { title: "操作", key: "actions", width: 70, render: (_, row) => <Button type="text" danger icon={<DeleteOutlined />} aria-label="删除品牌规则" onClick={() => update({ mappings: mappings.filter(r => r.key !== row.key) })} /> },
  ];
  const submissionColumns: ProColumns<Submission>[] = [
    { title: "Walmart店铺", key: "store", width: 300, render: (_, row) => select("Walmart店铺", row.source_account_ref && row.source_store_id ? identity(row.source_account_ref, row.source_store_id) : "", (data?.walmart_stores ?? []).map(s => ({ value: identity(s.account, s.storeId), label: s.label })), v => { const selected = data?.walmart_stores.find(s => identity(s.account, s.storeId) === v); editSubmission(row.key, { source_account_ref: selected?.account ?? "", source_store_id: selected?.storeId ?? "" }); }) },
    { title: "提报店铺ID", key: "submissionStoreId", width: 350, render: (_, row) => <Input value={row.submission_store_id} placeholder="输入经理要求的店铺ID" maxLength={128} onChange={e => editSubmission(row.key, { submission_store_id: e.target.value })} /> },
    { title: "操作", key: "actions", width: 76, render: (_, row) => <Button type="text" danger icon={<DeleteOutlined />} aria-label="删除店铺配置" onClick={() => update({ submission_stores: submissions.filter(r => r.key !== row.key) })} /> },
  ];
  return <Drawer title="自动刊登规则" placement="right" width="min(1120px, 100vw)" open={open} onClose={() => !saving && onClose()} maskClosable={false} closable={!saving} keyboard={!saving}
    footer={<div className="woo-rules__footer"><Text type="secondary">{notice || (dirty ? "有未保存的修改" : "规则配置 · 自动任务未接入")}</Text><div className="woo-rules__actions"><Button disabled={saving} onClick={onClose}>关闭</Button><ResetButton disabled={!dirty || saving} onClick={() => { setDraft(saved); setError(""); setNotice(""); }} /><Button type="primary" loading={saving} disabled={!dirty || invalid || loading} onClick={() => void submit()}>保存规则</Button></div></div>}>
    {error && <Alert type="error" showIcon message={error} action={!saving && <Button onClick={() => setReload(n => n + 1)}>重新读取</Button>} />}
    <Spin spinning={loading || saving}>
    {draft && data && <div className="woo-rules">
      <div className="woo-rules__section-title woo-rules__master"><h2>自动刊登配置</h2><Switch checked={draft.auto_publish_enabled} checkedChildren="开启" unCheckedChildren="关闭" onChange={v => update({ auto_publish_enabled: v })} /></div>
      <section className="woo-rules__section">
        <div className="woo-rules__section-title"><h2>品牌对应规则</h2><Button icon={<PlusOutlined />} onClick={() => update({ mappings: [...mappings, { key: rowKey(), source_brand: "", target_store_id: "", target_brand_id: "", target_category_id: "", enabled: false }] })}>新增规则</Button></div>
        <ReportTableShell label="品牌对应规则" className="woo-rules__table"><ProTable<Mapping> rowKey="key" search={false} options={false} toolBarRender={false} tableAlertRender={false} pagination={false} bordered size="small" tableLayout="fixed" columns={mappingColumns} dataSource={mappings} scroll={{x: 852}} /></ReportTableShell>
        {!data.stores.some(s => s.brands.length && s.categories.length) && <Text type="secondary">先同步独立站商品，品牌及分类选项来自已同步数据。</Text>}
      </section>
      <section className="woo-rules__section">
        <div className="woo-rules__section-title"><h2>店铺提报配置</h2><Button icon={<PlusOutlined />} onClick={() => update({ submission_stores: [...submissions, { key: rowKey(), source_account_ref: "", source_store_id: "", submission_store_id: "" }] })}>新增配置</Button></div>
        <ReportTableShell label="店铺提报配置" className="woo-rules__table"><ProTable<Submission> rowKey="key" search={false} options={false} toolBarRender={false} tableAlertRender={false} pagination={false} bordered size="small" tableLayout="fixed" columns={submissionColumns} dataSource={submissions} scroll={{x: 726}} /></ReportTableShell>
        {duplicate && <Text type="danger">同一品牌或来源账号及店铺不能重复配置。</Text>}
      </section>
      <div className="woo-rules__grid">
        <section className="woo-rules__section"><h2>刊登条件</h2><div className="woo-rules__field"><Text>Listing状态</Text><div className="woo-rules__control">{select("Listing状态", draft.listing_status, listingOptions, v => { if (v === "active" || v === "review") update({ listing_status: v }); }, false)}</div></div></section>
        <section className="woo-rules__section"><h2>售价设置</h2><div className="woo-rules__field"><Text>定价方式</Text><div className="woo-rules__control">{select("定价方式", draft.price_mode, priceOptions, v => { if (v === "original" || v === "fixed" || v === "percent") update({ price_mode: v }); }, false)}</div></div>{draft.price_mode !== "original" && <div className="woo-rules__field"><Text>加价参数</Text><div className="woo-rules__inline"><InputNumber stringMode min="0" max="99999" precision={2} value={draft.price_markup} onChange={v => { if (v !== null) update({ price_markup: String(v) }); }} /><Text>{draft.price_mode === "percent" ? "%" : "USD"}</Text></div></div>}</section>
        <section className="woo-rules__section"><h2>库存设置</h2><div className="woo-rules__field"><Text>实际可售数量</Text><div className="woo-rules__inline"><InputNumber min={0} max={2147483647} precision={0} value={draft.stock_quantity} placeholder="待配置" onChange={v => update({ stock_quantity: v })} /><Text>件</Text></div></div></section>
        <section className="woo-rules__section"><h2>提报周期</h2><div className="woo-rules__field"><Text>间隔天数</Text><div className="woo-rules__inline"><InputNumber min={1} max={3650} precision={0} value={draft.submission_interval_days} onChange={v => { if (v !== null) update({ submission_interval_days: v }); }} /><Text>天</Text></div></div><Text type="secondary">仅保存周期参数，暂未接入通知或提报任务。</Text></section>
      </div>
      <section className="woo-rules__section"><div className="woo-rules__section-title"><h2>失败重试</h2><Switch checked={draft.retry_enabled} onChange={v => update({ retry_enabled: v })} /></div><div className="woo-rules__field"><Text>最大重试次数</Text><InputNumber min={0} max={20} precision={0} disabled={!draft.retry_enabled} value={draft.retry_limit} onChange={v => { if (v !== null) update({ retry_limit: v }); }} /></div></section>
      {invalid && dirty && <Text type="danger">请补齐必填规则、检查重复项及库存设置。</Text>}
    </div>}
    </Spin>
  </Drawer>;
}

import { useEffect, useState } from "react";
import ReportFacetSelect, { type ReportFilterOption } from "@/shared/report-filters";
import { fetchListingExactFacetOptions, type ListingManagementParams } from "@/pages/products/listingManagementApi";
import type { MoreFacetState } from "@/pages/products/listingExactFacetLogic";

interface Props {
  preloaded?: MoreFacetState;
  fullWidth?: boolean;
  field: string;
  label: string;
  query: ListingManagementParams;
  revision: number;
  value: string[];
  onChange: (values: string[]) => void;
  onError: (message: string) => void;
}

function selectedLabel(field: string, value: string) {
  if (value === "n:") return ({rating:"无评分", listedAt:"未上架", checkedAt:"未检测"} as Record<string,string>)[field] ?? "无数据";
  try { return String(JSON.parse(value.slice(2))); } catch { return value; }
}

export default function ListingExactFacetSelect({ field, label, query, revision, value, onChange, onError, fullWidth = false, preloaded }: Props) {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<ReportFilterOption[]>([]);
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  // Keep unrelated page renders and own selections from restarting a request.
  const scope = JSON.stringify({ ...query, exactFilters: Object.fromEntries(
    Object.entries(query.exactFilters ?? {}).filter(([key]) => key !== field),
  ) });
  const managedByParent = preloaded !== undefined;
  useEffect(() => {
    if (!open || managedByParent) return;
    let active = true;
    const run = async () => {
      const collected: ReportFilterOption[] = [];
      let offset = 0;
      for (;;) {
        const page = await fetchListingExactFacetOptions(field, JSON.parse(scope) as ListingManagementParams, offset);
        if (!active) return;
        collected.push(...page.options);
        if (!page.has_more) break;
        if (!page.options.length) throw new Error("invalid facet page");
        offset += page.options.length;
      }
      if (!active) return;
      setOptions(collected);
      setReady(true);
    };
    const timer = window.setTimeout(() => {
      setLoading(true);
      setReady(false);
      setOptions([]);
      void run().catch(() => {
        if (!active) return;
        setOptions([]);
        setReady(false);
        onError(`${label}选项加载失败，请关闭后重试`);
      }).finally(() => { if (active) setLoading(false); });
    }, 0);
    return () => { active = false; window.clearTimeout(timer); };
    // onError is a page callback; scope/revision represent all query inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [field, label, open, revision, scope, managedByParent]);

  const activeOptions = preloaded?.options ?? options;
  const activeReady = preloaded?.ready ?? ready;
  const activeLoading = preloaded?.loading ?? loading;
  const known = new Set(activeOptions.map(item => item.value));
  const merged = [...activeOptions, ...value.filter(item => !known.has(item)).map(item => ({
    value: item, label: selectedLabel(field, item), ...(activeReady ? { count: 0 } : {}),
  }))];
  return <ReportFacetSelect
    mode="multiple" immediateMultiple={managedByParent} ariaLabel={label} placeholder={fullWidth ? "" : label} unit="项"
    triggerWidth={fullWidth ? "100%" : Math.max(100, Math.min(154, Array.from(label).length * 12 + 42))}
    popupWidth={field === "title" || field === "keyFeatures" ? 560 : 360}
    value={value} options={merged} loading={!managedByParent && activeLoading} optionsReady={activeReady}
    onOpenChange={next => { if (!managedByParent && next) setReady(false); setOpen(next); }}
    onChange={next => {
      const values = Array.isArray(next) ? next : [];
      // Selecting every currently available exact value is equivalent to no restriction.
      if (!managedByParent && ready && options.length && options.every(option => values.includes(option.value))) {
        onChange([]);
      } else {
        onChange(values);
      }
    }}
  />;
}

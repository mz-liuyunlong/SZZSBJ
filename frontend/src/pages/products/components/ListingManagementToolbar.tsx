import {
  CloudDownloadOutlined,
  SettingOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { Button, Popover, Space, Typography, Input } from "antd";
import { useState } from "react";
import ConnectedSearch from "@/components/report-table/ConnectedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import ListingExactFacetSelect from "@/pages/products/components/ListingExactFacetSelect";
import { listingMainFacets, listingMoreFacetGroups, visibleListingExactFilters, listingMoreDraft, mergeListingMoreDraft, useListingMoreFacetOptions } from "@/pages/products/listingExactFacetLogic";
import type { ListingManagementParams } from "@/pages/products/listingManagementApi";
import type { ReportFilterOption } from "@/shared/report-filters";

export interface ListingManagementFilters {
  stores: string[];
  exactFilters?: Record<string, string[]>;
  owners?: string[];
  productTypes?: string[];
  productStatuses?: string[];
  tagValues?: string[];
  productTagValues?: string[];
  customTagValues?: string[];
  lifecycleValues?: string[];
  gradeValues?: string[];
  archiveStatuses?: string[];

  /** Legacy cached single-value filters. Kept only to migrate older page-state cache safely. */
  owner?: string;
  productType?: string;
  productStatus?: string;

  searchType: "sku" | "msku" | "productId" | "productName";
  keyword: string;
  batchValues?: string[];
}

interface ListingManagementToolbarProps {
  filters: ListingManagementFilters;
  stores?: ReportFilterOption[];
  owners?: ReportFilterOption[];
  productTags?: ReportFilterOption[];
  customTags?: ReportFilterOption[];
  lifecycles?: ReportFilterOption[];
  grades?: ReportFilterOption[];
  archiveStatuses?: ReportFilterOption[];
  facetQuery?: ListingManagementParams;
  facetRevision?: number;
  facetPrefetchReady?: boolean;
  statisticsVisible: boolean;
  onChange: (filters: ListingManagementFilters) => void;
  onReset: () => void;
  onBatchSearch: (values: string[]) => void;
  onMessage: (content: string) => void;
  onToggleStatistics: () => void;
  onOpenTagManager?: () => void;
  onOpenRuleConfig: () => void;
  onOpenColumnConfig: () => void;
  onDownload: () => void;
  downloadDisabled?: boolean;
  downloadLoading?: boolean;
}

function ListingManagementToolbar({
  filters,
  facetQuery = {},
  facetRevision = 0,
  facetPrefetchReady = true,
  statisticsVisible,
  onChange,
  onReset,
  onMessage,
  onToggleStatistics,
  onOpenTagManager,
  onOpenRuleConfig,
  onOpenColumnConfig,
  onDownload,
  downloadDisabled = false,
  downloadLoading = false,
}: ListingManagementToolbarProps) {
  const [moreOpen, setMoreOpen] = useState(false);
  const [batchOpen, setBatchOpen] = useState(false);
  const exact = visibleListingExactFilters(filters.exactFilters);
  const moreFields = listingMoreFacetGroups.flatMap<string>(group => group.fields.map(([field]) => field));
  const moreCount = moreFields.filter(field => exact[field]?.length).length;
  const [moreDraft, setMoreDraft] = useState<Record<string, string[]>>({});
  const moreDraftCount = moreFields.filter(field => moreDraft[field]?.length).length;
  const draftQuery = {
    ...facetQuery,
    exactFilters: moreOpen ? mergeListingMoreDraft(exact, moreDraft) : exact,
  };
  const moreOptions = useListingMoreFacetOptions(draftQuery, facetRevision, onMessage, facetPrefetchReady || moreOpen);
  const moreLoading = moreOpen && (
    Object.keys(moreOptions).length === 0 || Object.values(moreOptions).some(item => item.loading)
  );
  const changeMoreOpen = (next: boolean) => {
    if (next) setMoreDraft(listingMoreDraft(exact));
    setMoreOpen(next);
  };
  const changeMoreDraft = (field: string, values: string[]) => {
    setMoreDraft(previous => {
      const next = { ...previous };
      if (values.length) next[field] = values;
      else delete next[field];
      return next;
    });
  };
  const applyMoreSearch = () => {
    onChange({ ...filters, exactFilters: mergeListingMoreDraft(exact, moreDraft) });
    setMoreOpen(false);
  };
  const setExact = (field: string, values: string[]) => {
    const next = { ...exact };
    if (values.length) next[field] = values;
    else delete next[field];
    onChange({ ...filters, exactFilters: next });
  };
  const renderFacet = (field: string, label: string, fullWidth = false) => <ListingExactFacetSelect
    key={field} field={field} label={label} query={facetQuery} revision={facetRevision} fullWidth={fullWidth}
    value={exact[field] ?? []} onChange={values => setExact(field, values)} onError={onMessage}
  />;
  const [batchText, setBatchText] = useState("");
  const [searchTypeDraft, setSearchTypeDraft] = useState<ListingManagementFilters["searchType"]>(filters.searchType);
  const [keywordDraft, setKeywordDraft] = useState(filters.keyword);

  const applyBatchSearch = () => {
    const values = batchText
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);

    if (values.length === 0) {
      onMessage("请输入 SKU / MSKU / 商品ID");
      return;
    }
    if (values.length > 1000) {
      onMessage("最多支持 1000 行");
      return;
    }

    onChange({
      ...filters,
      searchType: searchTypeDraft,
      keyword: "",
      batchValues: values,
    });
    setBatchOpen(false);
  };

  const batchControl = (
    <Popover
      trigger="click"
      open={batchOpen}
      placement="bottomRight"
      onOpenChange={setBatchOpen}
      content={(
        <div className="listing-management__batch-popover">
          <Typography.Text strong>精确搜索，一行一项，最多支持1000行</Typography.Text>
          <Input.TextArea
            value={batchText}
            placeholder="请输入 SKU / MSKU / 商品ID，一行一个"
            rows={8}
            onChange={(event) => setBatchText(event.target.value)}
          />
          <div className="listing-management__batch-actions">
            <Button onClick={() => setBatchText("")}>清空</Button>
            <Button onClick={() => setBatchOpen(false)}>关闭</Button>
            <Button type="primary" onClick={applyBatchSearch}>搜索</Button>
          </div>
        </div>
      )}
    >
      <Button
        className="report-table-connected-search__filter"
        aria-label="批量搜索 Listing"
        icon={<UnorderedListOutlined aria-hidden="true" />}
      />
    </Popover>
  );

  return (
    <>
    <div className="listing-management__toolbar" role="search" aria-label="Listing 管理筛选">
      {listingMainFacets.map(([field, label]) => renderFacet(field, label))}
      <ConnectedSearch
        className="listing-management__search"
        typeAriaLabel="搜索类型"
        typeOptions={[
          { value: "sku", label: "SKU" },
          { value: "msku", label: "MSKU" },
          { value: "productId", label: "商品ID" },
          { value: "productName", label: "品名" },
        ]}
        typeValue={searchTypeDraft}
        inputAriaLabel="搜索商品"
        inputPlaceholder="搜索商品"
        inputValue={keywordDraft}
        batchControl={batchControl}
        onTypeChange={(searchType) => setSearchTypeDraft(searchType as ListingManagementFilters["searchType"])}
        onInputChange={setKeywordDraft}
        onSearch={() => {
          onChange({
            ...filters,
            searchType: searchTypeDraft,
            keyword: keywordDraft.trim(),
            batchValues: undefined,
          });
          onMessage("已应用搜索条件");
        }}
      />
      <Popover
        trigger="click"
        placement="bottomRight"
        open={moreOpen}
        onOpenChange={next => { if (!next) changeMoreOpen(false); }}
        destroyOnHidden
        content={(
          <section className="listing-management__more-filters" aria-label="更多筛选">
      <div className="listing-management__more-filter-grid">
        {listingMoreFacetGroups.map(group =>
          group.fields.map(([field, label]) => (
            <div className="listing-management__more-filter-item" key={field}>
              <span className="listing-management__more-filter-title">
                {label}
              </span>
              {<ListingExactFacetSelect
                field={field} label={label} query={draftQuery} revision={facetRevision} fullWidth
                preloaded={moreOptions[field] ?? { options: [], ready: false, loading: false }}
                value={moreDraft[field] ?? []}
                onChange={values => changeMoreDraft(field, values)} onError={onMessage}
              />}
            </div>
          ))
        )}
      </div>
      <div className="listing-management__more-filter-actions">
        {moreLoading && <Typography.Text type="secondary" style={{ marginRight: "auto", fontSize: 12 }} role="status">正在加载筛选选项…</Typography.Text>}
        <Button size="small" disabled={!moreDraftCount} onClick={() => setMoreDraft({})}>清空更多筛选</Button>
        <Button size="small" onClick={() => setMoreOpen(false)}>关闭</Button>
        <Button size="small" type="primary" onClick={applyMoreSearch}>搜索</Button>
      </div>
    </section>
        )}
      >
        <Button aria-expanded={moreOpen} onClick={() => changeMoreOpen(!moreOpen)}>
          更多筛选{moreCount > 0 ? ` (${moreCount})` : ""}
        </Button>
      </Popover>
      <ResetButton
        onClick={() => {
          setSearchTypeDraft("sku");
          setKeywordDraft("");
          setBatchText("");
          onReset();
        }}
      />
      {onOpenTagManager ? (
        <Button
          className="listing-management__tag-manager-button"
          onClick={onOpenTagManager}
        >
          标签管理
        </Button>
      ) : null}
      <Button onClick={onToggleStatistics}>
        {statisticsVisible ? "隐藏统计" : "显示统计"}
      </Button>
      <Space className="listing-management__toolbar-actions" size={8}>
        <Button aria-label="Listing规则配置" icon={<SettingOutlined aria-hidden="true" />} onClick={onOpenRuleConfig}>规则配置</Button>
        <Button
          aria-label="列配置"
          icon={<SettingOutlined aria-hidden="true" />}
          onClick={onOpenColumnConfig}
        />
        <Button
          aria-label="下载"
          disabled={downloadDisabled}
          loading={downloadLoading}
          icon={<CloudDownloadOutlined aria-hidden="true" />}
          onClick={onDownload}
        />
      </Space>
    </div>

    </>
  );
}

export default ListingManagementToolbar;

/** Shared filter and empty-table frame for the WFS list pages. */
import { QuestionCircleOutlined } from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Empty } from "antd";
import { useEffect, useRef, useState, type ReactNode } from "react";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ResetButton from "@/components/report-table/ResetButton";
import PageShell from "@/components/page/PageShell";
import RequestLoadingOverlay from "@/components/page/RequestLoadingOverlay";
import type { NavigationPage } from "@/config/navigation";
import "./PendingPackingPage.css";

export interface WfsQueryPageProps<Row extends { id: string } = { id: string }> {
  page: NavigationPage;
  title: string;
  tableLabel: string;
  emptyText: string;
  searchAriaLabel: string;
  inputAriaLabel: string;
  inputPlaceholder: string;
  typeAriaLabel: string;
  typeOptions: { value: string; label: string }[];
  searchType?: string;
  columns: ProColumns<Row>[];
  scrollX: number;
  keyword: string;
  onSearch: (keyword: string, searchType: string) => void;
  onReset: () => void;
  filters?: ReactNode;
  headExtra?: ReactNode;
  loading?: boolean;
  loadingLabel?: string;
  rows?: Row[];
  total?: number;
  current?: number;
  pageSize?: number;
  onPageChange?: (page: number, pageSize: number) => void;
  onRowClick?: (row: Row) => void;
  aboveToolbar?: ReactNode;
}

export default function WfsQueryPage<Row extends { id: string } = { id: string }>({
  page, title, tableLabel, emptyText, searchAriaLabel, inputAriaLabel, inputPlaceholder,
  typeAriaLabel, typeOptions, searchType, columns, scrollX, keyword, onSearch, onReset, filters, headExtra,
  loading = false, loadingLabel = "正在加载数据，请稍候",
  rows = [], total = 0, current = 1, pageSize = 20, onPageChange, onRowClick, aboveToolbar,
}: WfsQueryPageProps<Row>) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [scrollY, setScrollY] = useState(360);
  useEffect(() => {
    const node = bodyRef.current;
    if (!node) return undefined;
    const measure = () => setScrollY(Math.max(220, node.clientHeight - 96));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return (
    <PageShell page={page} headerActions={<Button href="/help/pmc-wfs.html" target="_blank" rel="noreferrer" icon={<QuestionCircleOutlined />}>帮助</Button>}>
      <div className="wfs-pending">
        <RequestLoadingOverlay spinning={loading} label={loadingLabel} />
        {aboveToolbar}
        <div className="wfs-pending__toolbar" role="search" aria-label={`${page.title}筛选`}>
          {filters}
          <CommittedSearch
            key={keyword}
            className="wfs-pending__search"
            typeAriaLabel={typeAriaLabel}
            typeValue={searchType ?? typeOptions[0]?.value ?? "all"}
            typeOptions={typeOptions}
            inputAriaLabel={inputAriaLabel}
            inputValue={keyword}
            inputPlaceholder={inputPlaceholder}
            searchAriaLabel={searchAriaLabel}
            onCommit={({ keyword: next, searchField }) => onSearch(next, searchField)}
          />
          <ResetButton aria-label={`重置${page.title}筛选`} onClick={onReset} />
        </div>
        <section className="wfs-pending__table" aria-label={tableLabel}>
          <div className="wfs-pending__head">
            <div className="wfs-pending__title"><b>{title}</b></div>
            {headExtra}
          </div>
          <div className="wfs-pending__body" ref={bodyRef}>
            <ProTable<Row>
              rowKey="id"
              search={false}
              options={false}
              toolBarRender={false}
              tableAlertRender={false}
              size="small"
              bordered
              columns={columns}
              dataSource={rows}
              onRow={onRowClick ? (record) => ({ onClick: () => onRowClick(record) }) : undefined}
              scroll={{ x: scrollX, y: scrollY }}
              pagination={{
                current,
                pageSize,
                total,
                showSizeChanger: true,
                showTotal: (n) => `共 ${n} 条`,
                onChange: (p, size) => onPageChange?.(p, size),
              }}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} /> }}
            />
          </div>
        </section>
      </div>
    </PageShell>
  );
}

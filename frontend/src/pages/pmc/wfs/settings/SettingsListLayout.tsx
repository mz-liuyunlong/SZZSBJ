/**
 * List frame for the PMC 设置 table pages, composed from the shared report components the PMC
 * domestic pages use: PageShell → page card (title + source) → toolbar card (filters,
 * CommittedSearch, ResetButton) → alerts → summary row (count + actions) → ReportTableShell
 * (ProTable, fixed header, internal scroll) + fixed pagination.
 */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Card, Empty, Pagination, Typography, theme } from "antd";
import type { CSSProperties, ReactNode } from "react";
import PageShell from "@/components/page/PageShell";
import RequestLoadingOverlay from "@/components/page/RequestLoadingOverlay";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResetButton from "@/components/report-table/ResetButton";
import { REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import type { NavigationPage } from "@/config/navigation";
import "../WfsSettingsPage.css";

export interface SettingsSearch {
  keyword: string;
  field: string;
}

interface Props<Row> {
  page: NavigationPage;
  source: string;
  loading: boolean;
  filters?: ReactNode;
  search: SettingsSearch;
  searchOptions: { value: string; label: string }[];
  searchPlaceholder: string;
  onSearch: (search: SettingsSearch) => void;
  onReset: () => void;
  alerts?: ReactNode;
  summary: ReactNode;
  actions?: ReactNode;
  tableLabel: string;
  rowKey: keyof Row & string;
  columns: ProColumns<Row>[];
  rows: Row[];
  scrollX: number;
  emptyText: string;
  total: number;
  pagination?: { page: number; pageSize: number };
  onPagination?: (page: number, pageSize: number) => void;
  extra?: ReactNode;
  onSortChange?: (sorter: unknown) => void;
}

export default function SettingsListLayout<Row extends Record<string, unknown>>(p: Props<Row>) {
  const { token } = theme.useToken();
  const vars = {
    "--ant-color-border-secondary": token.colorBorderSecondary,
    "--ant-border-radius-lg": `${token.borderRadiusLG}px`,
    "--ant-color-fill-quaternary": token.colorFillQuaternary,
  } as CSSProperties;
  return (
    <PageShell page={p.page}>
      <div className="pmc-settings" style={vars}>
        <Card size="small" className="pmc-settings__page-card">
          <RequestLoadingOverlay spinning={p.loading} label={`正在加载${p.page.title}，请稍候`} />
          <div className="pmc-settings__title-row">
            <Typography.Title level={3}>{p.page.title}</Typography.Title>
            <Typography.Text type="secondary">{p.source}</Typography.Text>
          </div>
          <Card size="small" className="pmc-settings__toolbar-card">
            <div className="pmc-settings__toolbar" role="search" aria-label={`${p.page.title}筛选`}>
              {p.filters}
              <CommittedSearch
                key={`${p.search.field}:${p.search.keyword}`}
                className="pmc-settings__search"
                typeAriaLabel={`${p.page.title}搜索类型`}
                typeValue={p.search.field}
                typeOptions={p.searchOptions}
                inputAriaLabel={`搜索${p.page.title}关键字`}
                inputValue={p.search.keyword}
                inputPlaceholder={p.searchPlaceholder}
                searchAriaLabel={`搜索${p.page.title}`}
                onCommit={({ keyword, searchField }) => p.onSearch({ keyword: keyword.trim(), field: searchField })}
              />
              <ResetButton aria-label={`重置${p.page.title}筛选`} onClick={p.onReset} />
            </div>
          </Card>
          {p.alerts}
          <div className="pmc-settings__summary-row">
            <Typography.Text>{p.summary}</Typography.Text>
            {p.actions}
          </div>
          <div className="pmc-settings__table-wrap">
            <ReportTableShell label={p.tableLabel}>
              <ProTable<Row>
                rowKey={p.rowKey}
                search={false}
                options={false}
                toolBarRender={false}
                tableAlertRender={false}
                size="small"
                bordered
                columns={p.columns}
                dataSource={p.rows}
                loading={false}
                scroll={{ x: p.scrollX, y: "100%" }}
                pagination={false}
                onChange={(_, __, sorter, extra) => { if (extra.action === "sort") p.onSortChange?.(sorter); }}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={p.emptyText} /> }}
              />
              {p.pagination && p.onPagination && (
                <Pagination
                  className="ant-table-pagination"
                  size="small"
                  current={p.pagination.page}
                  pageSize={p.pagination.pageSize}
                  total={p.total}
                  showSizeChanger
                  showQuickJumper
                  pageSizeOptions={REPORT_TABLE_PAGE_SIZE_OPTIONS}
                  showTotal={(n) => `共 ${n} 条`}
                  onChange={(page, size) => p.onPagination?.(size !== p.pagination?.pageSize ? 1 : page, size)}
                />
              )}
            </ReportTableShell>
          </div>
        </Card>
        {p.extra}
      </div>
    </PageShell>
  );
}

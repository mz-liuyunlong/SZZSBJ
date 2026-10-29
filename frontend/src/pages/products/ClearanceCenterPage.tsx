/** Shared React tables and search bridge. Business state and dialogs remain in V4. */
import { ConfigProvider, Tabs } from "antd";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { StyleProvider } from "@ant-design/cssinjs";
import { createElement, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import PageShell from "@/components/page/PageShell";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import { REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import ConnectedSearch from "@/components/report-table/ConnectedSearch";
import ManagementStatCards, {
  type ManagementStatCardItem,
} from "@/components/report-table/ManagementStatCards";
import {
  ClockCircleOutlined,
  FileTextOutlined,
  LineChartOutlined,
  CheckCircleOutlined,
  InboxOutlined,
  WarningOutlined,
  DollarCircleOutlined,
} from "@ant-design/icons";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import type { NavigationPage } from "@/config/navigation";
import "./ClearanceCenterPage.css";

type ClearanceColumn = [key: string, title: string, width: number];
interface ClearanceRow {
  id: string;
  cells: Record<string, string>;
}
interface ClearanceMetric {
  key: string;
  title: string;
  value: string | number;
  subtitle: string;
  icon: string;
}
interface ClearanceSnapshot {
  tabCounts: { analysis: number; management: number };
  statsVisible: boolean;
  activeMetric: string;
  metrics: ClearanceMetric[];
  tab: "analysis" | "management" | "rules";
  page: number;
  pageSize: number;
  query: string;
  total: number;
  columns: ClearanceColumn[];
  rows: ClearanceRow[];
}
interface ClearanceBridge {
  setTab(key: "analysis" | "management"): void;
  clickMetric(key: string): void;
  setReactReady(ready: boolean): void;
  snapshot(): ClearanceSnapshot;
  setSearch(value: string): void;
  setPagination(page: number, pageSize: number): void;
}
type ClearanceWindow = Window & {
  __SZZSBJ_CLEARANCE_BRIDGE__?: ClearanceBridge;
};

/** Allowlisted HTML-to-React adapter: preserves old cell layout without unsafe HTML insertion. */
const allowedTags = new Set([
  "a", "b", "br", "button", "circle", "div", "em", "i", "label",
  "line", "path", "polyline", "rect", "small", "span", "strong", "svg",
]);
const allowedAttributes = new Set([
  "title", "class", "data-act", "data-id", "data-val", "viewBox",
  "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "fill",
  "d", "cx", "cy", "r", "x", "y", "x1", "y1", "x2", "y2",
  "points", "width", "height", "xmlns", "aria-label", "role",
]);
const reactAttributeNames: Record<string, string> = {
  class: "className",
  "stroke-width": "strokeWidth",
  "stroke-linecap": "strokeLinecap",
  "stroke-linejoin": "strokeLinejoin",
};
function renderLegacyCell(html: string | undefined, doc: Document): ReactNode {
  if (!html) return "-";
  const template = doc.createElement("template");
  template.innerHTML = html;
  const parse = (node: Node, key: number): ReactNode => {
    if (node.nodeType === 3) return node.textContent;
    if (node.nodeType !== 1) return null;
    const el = node as Element;
    const tag = el.tagName.toLowerCase();
    const children = Array.from(el.childNodes).map(parse);
    if (!allowedTags.has(tag)) return children;
    const props: Record<string, string | number | undefined> = { key };
    for (const attr of Array.from(el.attributes)) {
      if (!allowedAttributes.has(attr.name)) continue;
      const propName = reactAttributeNames[attr.name] ?? attr.name;
      props[propName] = attr.value;
    }
    if (tag === "a") props.href = undefined;
    if (tag === "button") props.type = "button";
    return createElement(tag, props, ...children);
  };
  return Array.from(template.content.childNodes).map(parse);
}

/* SZZSBJ_CLEARANCE_SHARED_STATS_V1 */
const clearanceStatIcons: Record<string, ReactNode> = {
  clock: <ClockCircleOutlined />,
  file: <FileTextOutlined />,
  chart: <LineChartOutlined />,
  check: <CheckCircleOutlined />,
  package: <InboxOutlined />,
  alert: <WarningOutlined />,
  money: <DollarCircleOutlined />,
};

function ClearanceSharedStats({
  snapshot, bridge,
}: {
  snapshot: ClearanceSnapshot;
  bridge: ClearanceBridge;
}) {
  const cards: ManagementStatCardItem<string>[] = snapshot.metrics.map((metric) => ({
    key: metric.key,
    title: metric.title,
    value: metric.value,
    subtitle: metric.subtitle,
    tone: metric.key === "high" ? "danger" : metric.key === "pending" ? "warning" : "normal",
    icon: clearanceStatIcons[metric.icon] ?? <InboxOutlined />,
  }));

  return (
    <ManagementStatCards
      ariaLabel={snapshot.tab === "analysis" ? "清货分析统计" : "清货管理统计"}
      cards={cards}
      activeKey={snapshot.activeMetric}
      onCardClick={(key) => bridge.clickMetric(key)}
    />
  );
}

function SharedClearanceTable({
  snapshot, doc, bridge,
}: {
  snapshot: ClearanceSnapshot;
  doc: Document;
  bridge: ClearanceBridge;
}) {
  const [widths, setWidths] = useState<Record<string, number>>({});
  const columns: ProColumns<ClearanceRow>[] = snapshot.columns.map(([key, label, width]) => {
    const effectiveWidth = widths[`${snapshot.tab}:${key}`] ?? width;
    return {
      key,
      dataIndex: ["cells", key],
      title: (
        <ResizableColumnTitle
          label={label}
          width={effectiveWidth}
          minWidth={Math.max(60, Math.min(width, 110))}
          onWidthChange={(value) => setWidths((old) => ({
            ...old, [`${snapshot.tab}:${key}`]: value,
          }))}
        />
      ),
      width: effectiveWidth,
      ellipsis: false,
      fixed: (key === "identity" || key === "id" ? "left" : key === "action" ? "right" : undefined) as "left" | "right" | undefined,
      onHeaderCell: () => ({ className: "report-table-resizable-header-cell" }),
      render: (_, row) => renderLegacyCell(row.cells[key], doc),
    };
  });
  const xWidth = snapshot.columns.reduce((sum, [key, , width]) => (
    sum + (widths[`${snapshot.tab}:${key}`] ?? width)
  ), snapshot.tab === "analysis" ? 44 : 0);
  return (
    <ReportTableShell label={snapshot.tab === "analysis" ? "清货分析表格" : "清货管理表格"}>
      <ProTable<ClearanceRow>
        rowKey="id"
        dataSource={snapshot.rows}
        columns={columns}
        search={false}
        options={false}
        toolBarRender={false}
        scroll={{ x: xWidth }}
        pagination={{
          current: snapshot.page,
          pageSize: snapshot.pageSize,
          total: snapshot.total,
          size: "small",
          showSizeChanger: true,
          showQuickJumper: true,
          pageSizeOptions: REPORT_TABLE_PAGE_SIZE_OPTIONS,
          onChange: (page, pageSize) => bridge.setPagination(page, pageSize),
        }}
        locale={{ emptyText: "暂无符合条件的清货记录" }}
      />
    </ReportTableShell>
  );
}

/** Copies app-global CSS into the same-origin demo document. CSS-in-JS uses StyleProvider. */
function copySharedStyles(doc: Document) {
  doc.head.querySelectorAll('[data-clearance-shared-style="true"]').forEach((node) => node.remove());
  document.head.querySelectorAll('link[rel="stylesheet"], style[data-vite-dev-id]').forEach((node) => {
    const cloned = node.cloneNode(true) as Element;
    cloned.setAttribute("data-clearance-shared-style", "true");
    doc.head.appendChild(cloned);
  });
}

export default function ClearanceCenterPage({ page }: { page: NavigationPage }) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const frameWindowRef = useRef<ClearanceWindow | null>(null);
  const frameHandlerRef = useRef<(() => void) | null>(null);
  const [frameDocument, setFrameDocument] = useState<Document | null>(null);
  const [snapshot, setSnapshot] = useState<ClearanceSnapshot | null>(null);
  const [activeBridge, setActiveBridge] = useState<ClearanceBridge | null>(null);
  const [searchText, setSearchText] = useState("");

  const onFrameLoad = useCallback(() => {
    const frame = frameRef.current;
    const win = frame?.contentWindow as ClearanceWindow | null;
    const doc = frame?.contentDocument;
    if (!win || !doc || !win.__SZZSBJ_CLEARANCE_BRIDGE__) return;
    if (frameWindowRef.current && frameHandlerRef.current) {
      frameWindowRef.current.removeEventListener("szzsbj-clearance-view-update", frameHandlerRef.current);
    }
    const bridge = win.__SZZSBJ_CLEARANCE_BRIDGE__;
    const refresh = () => {
      const next = bridge.snapshot();
      setSnapshot(next);
      setSearchText(next.query);
    };
    frameWindowRef.current = win;
    frameHandlerRef.current = refresh;
    setActiveBridge(bridge);
    copySharedStyles(doc);
    win.addEventListener("szzsbj-clearance-view-update", refresh);
    setFrameDocument(doc);
    bridge.setReactReady(true);
    refresh();
  }, []);
  useEffect(() => () => {
    if (frameWindowRef.current && frameHandlerRef.current) {
      frameWindowRef.current.removeEventListener("szzsbj-clearance-view-update", frameHandlerRef.current);
    }
  }, []);

  const bridge = activeBridge;
  const tabRoot = frameDocument?.getElementById("clearance-react-tabs-root");
  const statsRoot = frameDocument?.getElementById("clearance-react-stats-root");
  const searchRoot = frameDocument?.getElementById("clearance-react-search-root");
  const tableRoot = frameDocument?.getElementById("clearance-protable-root");

  return (
    <PageShell page={page}>
      <div className="clearance-center-preview">
        <iframe
          ref={frameRef}
          title="WFS 清货中心"
          className="clearance-center-preview__frame"
          src="/demos/wfs-clearance-center-v4.html"
          onLoad={onFrameLoad}
          sandbox="allow-scripts allow-same-origin allow-modals allow-downloads"
          referrerPolicy="no-referrer"
        />
        {frameDocument && snapshot && bridge && (
          <StyleProvider container={frameDocument.head}>
            <ConfigProvider getPopupContainer={(trigger) => trigger?.parentElement ?? frameDocument.body}>
              {/* SZZSBJ_CLEARANCE_NATIVE_SMOOTH_TABS_V1: actual Ant Design Tabs */}
              {tabRoot && createPortal(
                <Tabs
                  className="clearance-native-tabs"
                  activeKey={snapshot.tab === "rules" ? "" : snapshot.tab}
                  animated={{ inkBar: true, tabPane: false }}
                  onChange={(key) => bridge.setTab(key as "analysis" | "management")}
                  items={[
                    {
                      key: "analysis",
                      label: <span className="clearance-react-tab-label">清货分析 <span className="clearance-react-tab-count">{snapshot.tabCounts.analysis}</span></span>,
                    },
                    {
                      key: "management",
                      label: <span className="clearance-react-tab-label">清货管理 <span className="clearance-react-tab-count">{snapshot.tabCounts.management}</span></span>,
                    },
                  ]}
                />,
                tabRoot,
              )}
              {statsRoot && snapshot.statsVisible && createPortal(
                <ClearanceSharedStats snapshot={snapshot} bridge={bridge} />,
                statsRoot,
              )}
              {searchRoot && createPortal(
                <ConnectedSearch
                  typeAriaLabel="清货搜索范围"
                  typeOptions={[{ label: "全部", value: "all" }]}
                  typeValue="all"
                  inputAriaLabel="搜索清货记录"
                  inputPlaceholder={snapshot.tab === "analysis"
                    ? "搜索 SKU / MSKU / 商品ID / 品名"
                    : "搜索清货单号 / SKU / 申请说明"}
                  inputValue={searchText}
                  onTypeChange={() => {}}
                  onInputChange={(value) => {
                    setSearchText(value);
                    bridge.setSearch(value);
                  }}
                  onSearch={() => bridge.setSearch(searchText)}
                />,
                searchRoot,
              )}
              {tableRoot && snapshot.tab !== "rules" && createPortal(
                <SharedClearanceTable snapshot={snapshot} doc={frameDocument} bridge={bridge} />,
                tableRoot,
              )}
            </ConfigProvider>
          </StyleProvider>
        )}
      </div>
    </PageShell>
  );
}

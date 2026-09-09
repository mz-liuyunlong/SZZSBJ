// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import dayjs from "dayjs";
import { useState, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { navigation } from "../../config/navigation";
import DailySalesPage from "./DailySalesPage";
import { dailySalesMockData } from "./dailySalesMockData";
import { dailySalesColumnFields } from "./dailySalesTypes";

const messageInfo = vi.fn();
const messageSuccess = vi.fn();
const messageError = vi.fn();

vi.mock("echarts-for-react", () => ({
  default: ({ option }: { option: { yAxis: { name: string } } }) => (
    <div role="img" aria-label={`${option.yAxis.name}图表`} />
  ),
}));

vi.mock("antd", async (importOriginal) => {
  const actual = await importOriginal<typeof import("antd")>();

  const Select = ({
    allowClear,
    maxTagCount,
    maxTagPlaceholder,
    mode,
    onChange,
    optionRender,
    options = [],
    placeholder,
    value,
    ...props
  }: {
    mode?: "multiple";
    onChange?: (value?: string | string[]) => void;
    options?: { label: ReactNode; value: string }[];
    optionRender?: (
      option: { label: ReactNode; value: string },
      info: { index: number },
    ) => ReactNode;
    placeholder?: string;
    value?: string | string[];
    [key: string]: unknown;
  }) => {
    void allowClear;
    void maxTagCount;
    void maxTagPlaceholder;
    const multiple = mode === "multiple";
    return (
      <>
        <select
          multiple={multiple}
          value={value ?? (multiple ? [] : "")}
          onChange={(event) => onChange?.(multiple
            ? Array.from(event.target.selectedOptions, (option) => option.value)
            : event.target.value || undefined)}
          {...props}
        >
          <option value="">{placeholder}</option>
          {options.map((option) => <option key={option.value} value={option.value}>{String(option.label)}</option>)}
        </select>
        {multiple && optionRender && (
          <div data-testid={`${String(props["aria-label"])}-checkbox-options`}>
            {options.map((option, index) => (
              <span key={option.value}>{optionRender(option, { index })}</span>
            ))}
          </div>
        )}
      </>
    );
  };

  const RangePicker = ({
    format,
    locale,
    onChange,
    presets,
    separator,
    value,
    ...props
  }: {
    onChange: (dates?: [dayjs.Dayjs, dayjs.Dayjs]) => void;
    presets?: unknown;
    separator?: ReactNode;
    value?: [dayjs.Dayjs, dayjs.Dayjs];
    [key: string]: unknown;
  }) => {
    void format;
    void locale;
    void presets;
    void separator;
    return (
      <div {...props}>
        <output aria-label="日期范围值">
          {value ? `${value[0].format("YYYY-MM-DD")}~${value[1].format("YYYY-MM-DD")}` : ""}
        </output>
        <button
          type="button"
          aria-label="设置自定义日期范围"
          onClick={() => onChange([dayjs().subtract(2, "day"), dayjs().subtract(1, "day")])}
        >
          自定义日期
        </button>
      </div>
    );
  };
  const RadioGroup = ({
    buttonStyle,
    onChange,
    optionType,
    options = [],
    size,
    value,
    ...props
  }: {
    onChange: (event: { target: { value: string } }) => void;
    options?: { label: ReactNode; value: string }[];
    value: string;
    [key: string]: unknown;
  }) => {
    void buttonStyle;
    void optionType;
    void size;
    return (
      <div {...props}>
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            aria-pressed={value === option.value}
            onClick={() => onChange({ target: { value: option.value } })}
          >
            {option.label}
          </button>
        ))}
      </div>
    );
  };

  const Drawer = ({
    children,
    footer,
    open,
    title,
  }: {
    children: ReactNode;
    footer?: ReactNode;
    open: boolean;
    title: ReactNode;
  }) => open ? (
    <aside role="dialog" aria-label={String(title)}>
      <h2>{title}</h2>
      {children}
      {footer}
    </aside>
  ) : null;

  const Empty = Object.assign(
    ({ description }: { description?: ReactNode }) => <div role="status">{description}</div>,
    { PRESENTED_IMAGE_SIMPLE: "simple" },
  );
  const Summary = Object.assign(
    ({ children, fixed }: { children: ReactNode; fixed?: boolean | "top" | "bottom" }) => (
      <tfoot data-fixed={String(fixed)}>{children}</tfoot>
    ),
    {
      Row: ({ children, ...props }: { children: ReactNode; [key: string]: unknown }) => (
        <tr {...props}>{children}</tr>
      ),
      Cell: ({ children, index, ...props }: {
        children?: ReactNode;
        index: number;
        [key: string]: unknown;
      }) => <td data-index={index} {...props}>{children}</td>,
    },
  );

  return {
    ...actual,
    DatePicker: { ...actual.DatePicker, RangePicker },
    Drawer,
    Empty,
    Popover: ({
      children,
      content,
      onOpenChange,
      open,
      title,
      trigger,
    }: {
      children: ReactNode;
      content: ReactNode;
      onOpenChange?: (open: boolean) => void;
      open?: boolean;
      title?: ReactNode;
      trigger?: string | string[];
    }) => {
      const [internalOpen, setInternalOpen] = useState(false);
      const shown = open ?? internalOpen;
      const supportsHover = trigger === "hover" || trigger?.includes("hover");
      const setOpen = (next: boolean) => onOpenChange?.(next) ?? setInternalOpen(next);
      return (
        <span>
          <span
            onClick={() => setOpen(!shown)}
            onMouseEnter={() => supportsHover && setOpen(true)}
            onMouseLeave={() => supportsHover && setOpen(false)}
          >
            {children}
          </span>
          {shown && <span role="dialog">{title}{content}</span>}
        </span>
      );
    },
    Radio: { ...actual.Radio, Group: RadioGroup },
    Select,
    Table: { Summary },
    Tooltip: ({ children, title }: { children: ReactNode; title?: ReactNode }) => (
      <span data-tooltip={String(title ?? "")}>{children}</span>
    ),
    message: {
      ...actual.message,
      useMessage: () => [{ info: messageInfo, success: messageSuccess, error: messageError }, null],
    },
  };
});

interface MockColumn<Row> {
  key?: string;
  title?: ReactNode;
  render?: (value: unknown, row: Row, index: number) => ReactNode;
}

interface MockTableProps<Row extends { id: string }> {
  columns: MockColumn<Row>[];
  dataSource: Row[];
  footer?: () => ReactNode;
  locale?: { emptyText?: ReactNode };
  pagination: {
    current: number;
    onChange: (page: number, pageSize: number) => void;
    pageSize: number;
  };
  rowSelection: {
    onChange: (keys: string[]) => void;
    selectedRowKeys: React.Key[];
  };
  summary?: () => ReactNode;
}

vi.mock("@ant-design/pro-components", () => ({
  ProTable: <Row extends { id: string }>({
    columns,
    dataSource,
    footer,
    locale,
    pagination,
    rowSelection,
    summary,
  }: MockTableProps<Row>) => {
    const displayed = Math.min(pagination.pageSize, dataSource.length);
    const first = dataSource[0];
    return (
      <div data-testid="pro-table" data-total={dataSource.length}>
        <table>
          <thead data-testid="table-header"><tr><th>选择</th>{columns.map((column) => <th key={column.key}>{column.title}</th>)}</tr></thead>
          <tbody data-testid="table-body">
            {first && (
              <tr>
                <td>
                  <input
                    aria-label={`选择行：${first.id}`}
                    type="checkbox"
                    checked={rowSelection.selectedRowKeys.includes(first.id)}
                    onChange={(event) => rowSelection.onChange(event.target.checked ? [first.id] : [])}
                  />
                </td>
                {columns.map((column, index) => (
                  <td key={column.key}>{column.render?.(undefined, first, index) ?? String(first[column.key as keyof Row] ?? "")}</td>
                ))}
              </tr>
            )}
          </tbody>
          {summary?.()}
        </table>
        {!first && locale?.emptyText}
        {footer?.()}
        <footer data-testid="pagination-footer">
          <output aria-label="当前页">{pagination.current}</output>
          <output aria-label="当前显示条数">{displayed}</output>
          <button type="button" onClick={() => pagination.onChange(2, pagination.pageSize)}>下一页</button>
          <select
            aria-label="每页条数"
            value={pagination.pageSize}
            onChange={(event) => pagination.onChange(2, Number(event.target.value))}
          >
            {[10, 20, 50, 100].map((size) => <option key={size} value={size}>{size}</option>)}
          </select>
        </footer>
      </div>
    );
  },
}));

const dailySalesPage = navigation
  .find((group) => group.key === "sales")
  ?.children.find((page) => page.key === "sales_daily_sales");

beforeEach(() => {
  if (!dailySalesPage) throw new Error("daily-sales navigation metadata is required");
  messageInfo.mockReset();
  messageSuccess.mockReset();
  messageError.mockReset();
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});

const renderPage = () => render(<DailySalesPage page={dailySalesPage!} />);
const today = dayjs().format("YYYY-MM-DD");
const todayRows = dailySalesMockData.filter((row) => row.date === today);
const usdHeaders = dailySalesColumnFields.map((field) => ({
  wfsDeliveryUnitPrice: "WFS配送单价($)",
  purchaseUnitPriceCny: "采购单价($)",
  firstLegUnitPriceCny: "头程单价($)",
  storageUnitPrice: "仓储单价($)",
}[field.key] ?? field.title));

describe("DailySalesPage", () => {
  it("uses PageShell metadata, hides the implementation status, and keeps all 35 columns in order", () => {
    const view = renderPage();

    expect(screen.getByRole("heading", { name: "当前页面" })).toHaveTextContent("每日销售");
    expect(view.container.querySelector(
      ".page-shell:has(> .page-shell__content .daily-sales) > .page-shell__header > .page-shell__heading",
    )).not.toBeNull();
    expect(screen.getByLabelText("页面状态：planned").closest(".page-shell"))
      .toContainElement(screen.getByLabelText("每日销售筛选"));
    expect(screen.getByRole("link", { name: /在新标签页打开/ })).toBeVisible();
    expect(dailySalesMockData).toHaveLength(50);
    expect(screen.getByTestId("pro-table")).toHaveAttribute("data-total", String(todayRows.length));

    const headers = within(screen.getByTestId("table-header"))
      .getAllByRole("columnheader")
      .slice(1)
      .map((header) => header.textContent);
    expect(headers).toEqual(usdHeaders);
    expect(screen.getAllByRole("separator", { name: /调整列宽/ })).toHaveLength(35);
    expect(screen.queryByText("商品 ID")).not.toBeInTheDocument();
    expect(screen.queryByText("父体")).not.toBeInTheDocument();
  });

  it("keeps only sync, refresh, and help in the global header", () => {
    renderPage();

    const actions = screen.getByText("同步时间：待接入")
      .closest<HTMLElement>(".page-shell__header-actions");
    expect(actions).not.toBeNull();
    expect(within(actions!).getByRole("button", { name: "刷新每日销售" })).toBeVisible();
    expect(within(actions!).getByRole("link", { name: /在新标签页打开/ })).toBeVisible();
    expect(within(actions!).queryByRole("button", { name: "下载" })).not.toBeInTheDocument();
    expect(within(actions!).queryByRole("button", { name: "列配置" })).not.toBeInTheDocument();
    expect(within(actions!).queryByRole("button", { name: /统计|图表/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "刷新每日销售" }));
    expect(messageInfo).toHaveBeenCalledWith("同步接口待接入");
  });

  it("moves page actions into the toolbar and reuses the runtime column drawer", () => {
    renderPage();

    const toolbar = screen.getByRole("search", { name: "每日销售筛选" });
    const downloadButton = within(toolbar).getByRole("button", { name: "下载" });
    const columnButton = within(toolbar).getByRole("button", { name: "列配置" });
    expect(within(toolbar).getByRole("button", { name: /隐藏统计$/ })).toBeVisible();
    expect(within(toolbar).getByRole("button", { name: /显示图表$/ })).toBeVisible();

    fireEvent.click(downloadButton);
    expect(messageInfo).toHaveBeenCalledWith("导出接口待接入");

    fireEvent.click(columnButton);
    const drawer = screen.getByRole("dialog", { name: "列配置" });
    expect(drawer).toBeVisible();
    expect(within(drawer).getAllByRole("checkbox")).toHaveLength(35);
    for (const title of ["图片", "分析", "日期"]) {
      expect(within(drawer).getByRole("checkbox", { name: `显示列：${title}` })).toBeChecked();
      expect(within(drawer).getByRole("checkbox", { name: `显示列：${title}` })).toBeDisabled();
    }
  });

  it("defaults dates to today, links shortcuts, and exposes the three multi-select filters", () => {
    renderPage();

    expect(screen.getByRole("button", { name: "今日" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("日期范围值")).toHaveTextContent(`${today}~${today}`);
    for (const label of ["平台", "负责人", "店铺"]) {
      expect(screen.getByLabelText(label)).toHaveAttribute("multiple");
      expect(screen.getByTestId(`${label}-checkbox-options`).querySelectorAll('input[type="checkbox"]'))
        .not.toHaveLength(0);
    }

    fireEvent.click(screen.getByRole("button", { name: "本周" }));
    expect(screen.getByLabelText("日期范围值")).toHaveTextContent(
      `${dayjs().startOf("week").format("YYYY-MM-DD")}~${today}`,
    );
    fireEvent.click(screen.getByRole("button", { name: "设置自定义日期范围" }));
    expect(screen.getByRole("button", { name: "本周" })).toHaveAttribute("aria-pressed", "false");
  });

  it("filters locally, switches display currency without clearing rows, and resets cleanly", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const localStorageSpy = vi.spyOn(Storage.prototype, "setItem");
    const sessionStorageSpy = vi.spyOn(window.sessionStorage, "setItem");
    renderPage();

    fireEvent.change(screen.getByLabelText("平台"), { target: { value: "Walmart" } });
    expect(Number(screen.getByTestId("pro-table").getAttribute("data-total"))).toBeLessThan(todayRows.length);

    fireEvent.change(screen.getByLabelText("币种"), { target: { value: "CNY" } });
    const filteredTotal = screen.getByTestId("pro-table").getAttribute("data-total");
    expect(screen.getAllByText(/^¥\d/).length).toBeGreaterThan(0);
    expect(screen.getByTestId("pro-table")).toHaveAttribute("data-total", filteredTotal);

    fireEvent.change(screen.getByLabelText("搜索内容"), { target: { value: "does-not-exist" } });
    expect(screen.getByText("暂无匹配销售数据")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: /重.*置/ }));
    expect(screen.getByTestId("pro-table")).toHaveAttribute("data-total", String(todayRows.length));
    expect(screen.getByLabelText("币种")).toHaveValue("USD");
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(localStorageSpy).not.toHaveBeenCalled();
    expect(sessionStorageSpy).not.toHaveBeenCalled();
  });

  it("opens batch search as a popover and performs case-sensitive exact matching", () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "批量搜索" }));
    const popover = screen.getByRole("dialog");
    expect(within(popover).getByText("精确搜索，一行一项，最多支持1000行")).toBeVisible();
    fireEvent.change(within(popover).getByLabelText("批量搜索内容"), {
      target: { value: `${todayRows[0].sku}\n\n${todayRows[0].sku}` },
    });
    fireEvent.click(within(popover).getByRole("button", { name: /搜.*索/ }));
    expect(screen.getByTestId("pro-table")).toHaveAttribute("data-total", "1");

    fireEvent.click(screen.getByRole("button", { name: "批量搜索" }));
    fireEvent.change(screen.getByLabelText("批量搜索内容"), {
      target: { value: todayRows[0].sku.toLocaleLowerCase() },
    });
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /搜.*索/ }));
    expect(screen.getByText("暂无匹配销售数据")).toBeVisible();
  });

  it("resets to page one and clears selection for every supported page size", () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    fireEvent.click(screen.getByRole("checkbox", { name: /选择行/ }));
    expect(screen.getByLabelText("当前页")).toHaveTextContent("2");
    expect(screen.getByText("已选择 1 项")).toBeVisible();

    for (const size of [10, 20, 50, 100, 10]) {
      fireEvent.change(screen.getByLabelText("每页条数"), { target: { value: String(size) } });
      expect(screen.getByLabelText("当前页")).toHaveTextContent("1");
      expect(screen.queryByText("已选择 1 项")).not.toBeInTheDocument();
      expect(screen.getByLabelText("当前显示条数")).toHaveTextContent(String(Math.min(size, todayRows.length)));
    }
    expect(screen.getByTestId("table-header")).toBeInTheDocument();
    expect(screen.getByTestId("table-body")).toBeInTheDocument();
    expect(screen.getByTestId("pagination-footer")).toBeInTheDocument();
  });

  it("defaults to visible statistics and hidden charts, then toggles both", () => {
    renderPage();

    const summary = screen.getByLabelText("销售统计");
    expect(summary).toBeVisible();
    for (const metric of ["销量", "销售额", "订单利润", "利润率", "广告费", "广告占比"]) {
      expect(within(summary).getByText(metric)).toBeVisible();
    }
    expect(within(summary).getAllByText("较上期")).toHaveLength(6);
    for (const trend of ["12.5%", "8.2%", "15.3%", "2.1%", "6.8%", "1.2%"]) {
      expect(within(summary).getByText(trend)).toBeVisible();
    }
    expect(within(summary).queryByText("所选日期范围")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("销售趋势图")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /隐藏统计$/ }));
    fireEvent.click(screen.getByRole("button", { name: /显示图表$/ }));
    expect(screen.queryByLabelText("销售统计")).not.toBeInTheDocument();
    expect(screen.getByLabelText("销售趋势图")).toBeVisible();
    const metricSelector = screen.getByLabelText("图表指标");
    for (const metric of ["销量", "销售额", "订单利润", "利润率", "广告费", "广告占比"]) {
      expect(within(metricSelector).getByRole("button", { name: metric })).toBeVisible();
    }
    fireEvent.click(within(metricSelector).getByRole("button", { name: "广告费" }));
    expect(screen.getByLabelText("广告费趋势")).toBeVisible();
    expect(screen.getByRole("button", { name: /显示统计$/ })).toBeVisible();
    expect(screen.getByRole("button", { name: /隐藏图表$/ })).toBeVisible();
  });

  it("keeps a fixed total row for all filtered rows and converts it with the display currency", () => {
    renderPage();

    const totalRow = screen.getByTestId("daily-sales-total-row");
    expect(totalRow).toHaveTextContent("总计");
    expect(totalRow).toHaveTextContent(
      todayRows.reduce((total, row) => total + row.salesVolume, 0).toLocaleString("zh-CN"),
    );
    expect(totalRow.querySelector(".daily-sales__total-cell--salesAmount")).toHaveTextContent("$");

    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    expect(screen.getByTestId("daily-sales-total-row")).toHaveTextContent("总计");
    fireEvent.change(screen.getByLabelText("平台"), { target: { value: "Walmart" } });
    expect(screen.getByTestId("daily-sales-total-row")).toHaveTextContent(
      todayRows
        .filter((row) => row.platform === "Walmart")
        .reduce((total, row) => total + row.salesVolume, 0)
        .toLocaleString("zh-CN"),
    );
    fireEvent.change(screen.getByLabelText("币种"), { target: { value: "CNY" } });
    expect(screen.getByTestId("daily-sales-total-row")).toHaveTextContent("¥");
  });

  it("renders shared hover previews and opens the static sales detail", () => {
    renderPage();

    fireEvent.mouseEnter(screen.getByLabelText("每日销售商品图片占位"));
    expect(document.querySelector(".report-table-image-preview")).toBeInTheDocument();
    fireEvent.mouseEnter(screen.getByRole("img", { name: "前7天销量趋势图" }));
    expect(screen.getByRole("img", { name: "销量图表" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: /查看销售详情/ }));
    expect(screen.getByRole("dialog", { name: "销售详情" })).toBeInTheDocument();
  });
});

// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import dayjs from "dayjs";
import { useState, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.setConfig({ testTimeout: 30_000 });
import { navigation } from "@/config/navigation";
import OrderProfitPage from "@/pages/sales/OrderProfitPage";
import { aggregateOrderProfitRows } from "@/pages/sales/orderProfitTypes";
import { orderProfitSourceRecords } from "@/pages/sales/orderProfitMockData";
import { orderProfitColumnFields } from "@/pages/sales/orderProfitTypes";

const messageInfo = vi.fn();
const messageSuccess = vi.fn();
const messageError = vi.fn();


vi.mock("@/pages/sales/orderProfitApi", async () => {
  const { orderProfitSourceRecords } = await import("@/pages/sales/orderProfitMockData");

  type OrderProfitMockRecord = (typeof orderProfitSourceRecords)[number];

  const inDateRange = (
    row: OrderProfitMockRecord,
    params: { startDate?: string; endDate?: string },
  ) => (!params.startDate || row.date >= params.startDate)
    && (!params.endDate || row.date <= params.endDate);

  const sum = (rows: OrderProfitMockRecord[], key: keyof OrderProfitMockRecord) => (
    rows.reduce((total, row) => total + Number(row[key] ?? 0), 0)
  );

  const sumOrderProfit = (rows: OrderProfitMockRecord[]) => rows.reduce((total, row) => (
    total
    + Number(row.salesAmount ?? 0)
    - Number(row.refundAmount ?? 0)
    - Number(row.adSpend ?? 0)
    - Number(row.wfsDeliveryFee ?? 0)
    - Number(row.commission ?? 0)
    - Number(row.purchaseCost ?? 0)
    - Number(row.firstLegCost ?? 0)
    - Number(row.storageFee ?? 0)
  ), 0);

  const fetchOrderProfitSourceRecords = vi.fn(async (
    params: {
      startDate?: string;
      endDate?: string;
      page?: number;
      pageSize?: number;
      platforms?: string[];
      owners?: string[];
      stores?: string[];
      searchField?: keyof OrderProfitMockRecord;
      keyword?: string;
      signal?: AbortSignal;
    } = {},
  ) => {
    const search = new URLSearchParams();
    if (params.startDate) search.set("start_date", params.startDate);
    if (params.endDate) search.set("end_date", params.endDate);
    search.set("page", String(params.page ?? 1));
    search.set("page_size", String(params.pageSize ?? 50));

    await fetch(`/api/sales/order-profit?${search.toString()}`, {
      credentials: "same-origin",
      ...(params.signal ? { signal: params.signal } : {}),
    });

    const keyword = params.keyword?.trim().toLocaleLowerCase() ?? "";
    const searchField = params.searchField ?? "productId";
    const records = orderProfitSourceRecords.filter((row) => {
      const target = String(row[searchField] ?? "");
      return inDateRange(row, params)
        && (!params.platforms?.length || params.platforms.includes(row.platform))
        && (!params.owners?.length || params.owners.includes(row.owner))
        && (!params.stores?.length || params.stores.includes(row.store))
        && (!keyword || target.toLocaleLowerCase().includes(keyword));
    });

    return {
      records,
      summary: {
        salesQuantity: sum(records, "salesVolume"),
        orderCount: sum(records, "orderCount"),
        salesAmount: sum(records, "salesAmount"),
        salesCurrency: "USD",
        refundAmount: sum(records, "refundAmount"),
        refundCurrency: "USD",
        orderProfitAmount: sumOrderProfit(records),
        orderProfitCurrency: "USD",
        adSpendAmount: sum(records, "adSpend"),
        adSpendCurrency: "USD",
      },
      meta: {
        latest_calculated_at: null,
        page: params.page ?? 1,
        page_size: params.pageSize ?? 50,
        total: records.length,
        partial: false,
        input_missing: false,
      },
    };
  });

  return {
    fetchOrderProfitSourceRecords,
    preloadOrderProfitSourceRecords: vi.fn(),
  };
});

vi.mock("@/pages/sales/salesFilterOptionsApi", async () => {
  const { orderProfitSourceRecords } = await import("@/pages/sales/orderProfitMockData");

  type OrderProfitMockRecord = (typeof orderProfitSourceRecords)[number];

  const inDateRange = (
    row: OrderProfitMockRecord,
    params: { startDate?: string; endDate?: string },
  ) => (!params.startDate || row.date >= params.startDate)
    && (!params.endDate || row.date <= params.endDate);

  const toOptions = (values: string[]) => Array.from(new Set(values.filter(Boolean)))
    .map((value) => ({ value, label: value, count: values.filter((item) => item === value).length }));

  return {
    emptySalesFilterOptions: { platforms: [], owners: [], stores: [] },
    mergeSelectedFilterValues: (
      selected: string[],
      options: { value: string }[],
    ) => Array.from(new Set([
      ...selected,
      ...options.map((option) => option.value),
    ])).filter(Boolean),
    fetchSalesFilterOptions: vi.fn(async (
      params: { startDate?: string; endDate?: string } = {},
    ) => {
      const rows = orderProfitSourceRecords.filter((row) => inDateRange(row, params));
      return {
        platforms: toOptions(rows.map((row) => row.platform)),
        owners: toOptions(rows.map((row) => row.owner)),
        stores: toOptions(rows.map((row) => row.store)),
      };
    }),
  };
});

vi.mock("echarts-for-react", () => ({
  default: ({ option }: { option: { yAxis: { name: string } } }) => (
    <div role="img" aria-label={`${option.yAxis.name}图表`} />
  ),
}));

vi.mock("antd", async (importOriginal) => {
  const actual = await importOriginal<typeof import("antd")>();

  const Select = ({
    allowClear,
    classNames,
    maxTagCount,
    maxTagPlaceholder,
    mode,
    onChange,
    onClear,
    onOpenChange,
    open,
    menuItemSelectedIcon,
    optionFilterProp,
    optionRender,
    options = [],
    popupRender,
    placeholder,
    popupMatchSelectWidth,
    showSearch,
    styles,
    value,
    ...props
  }: {
    mode?: "multiple";
    onChange?: (value?: string | string[]) => void;
    options?: { label: ReactNode; value: string }[];
    onClear?: () => void;
    onOpenChange?: (open: boolean) => void;
    open?: boolean;
    optionRender?: (
      option: { label: ReactNode; value: string },
      info: { index: number },
    ) => ReactNode;
    placeholder?: string;
    popupRender?: (menu: ReactNode) => ReactNode;
    value?: string | string[];
    [key: string]: unknown;
  }) => {
    void allowClear;
    void classNames;
    void maxTagCount;
    void maxTagPlaceholder;
    void onOpenChange;
    void open;
    void menuItemSelectedIcon;
    void optionFilterProp;
    void popupMatchSelectWidth;
    void showSearch;
    void styles;
    const multiple = mode === "multiple";
    const ariaLabel = String(props["aria-label"]);
    const hasValue = multiple
      ? Array.isArray(value) && value.length > 0
      : Boolean(value);
    const menu = <div data-testid={`${ariaLabel}-menu`} />;

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
        {allowClear && hasValue && (
          <button
            type="button"
            aria-label={`清除${ariaLabel}`}
            onClick={() => {
              onClear?.();
              onChange?.(multiple ? [] : undefined);
            }}
          >
            清除
          </button>
        )}
        {multiple && optionRender && (
          <div data-testid={`${ariaLabel}-checkbox-options`}>
            {options.map((option, index) => (
              <span key={option.value}>{optionRender(option, { index })}</span>
            ))}
          </div>
        )}
        {popupRender && (
          <div data-testid={`${ariaLabel}-dropdown`}>
            {popupRender(menu)}
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
    value?: string;
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
    pageSizeOptions: string[];
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
            {pagination.pageSizeOptions.map((size) => (
              <option key={size} value={size}>{size}</option>
            ))}
          </select>
        </footer>
      </div>
    );
  },
}));

const orderProfitPage = navigation
  .find((group) => group.key === "sales")
  ?.children.find((page) => page.key === "sales_order_profit");

beforeEach(() => {
  if (!orderProfitPage) throw new Error("order-profit navigation metadata is required");
  messageInfo.mockReset();
  messageSuccess.mockReset();
  messageError.mockReset();
  vi.stubGlobal("fetch", vi.fn(async () => ({})));
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
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});

const renderPage = async () => {
  const view = render(<OrderProfitPage page={orderProfitPage!} />);
  await waitFor(() => expect(screen.getByTestId("pro-table")).not.toHaveAttribute("data-total", "0"));
  return view;
};
const referenceDay = dayjs().subtract(1, "day").format("YYYY-MM-DD");
const referenceRows = aggregateOrderProfitRows(
  orderProfitSourceRecords.filter((row) => row.date === referenceDay),
);

describe("OrderProfitPage", () => {
  it("renders the order-profit shell with product-ID aggregation and no log columns", async () => {
    await renderPage();

    expect(screen.getByRole("region", { name: "订单利润" }))
      .toContainElement(screen.getByLabelText("订单利润筛选"));
    expect(orderProfitSourceRecords).toHaveLength(800);
    expect(referenceRows).toHaveLength(100);
    expect(screen.getByTestId("pro-table")).toHaveAttribute("data-total", String(referenceRows.length));
    expect(screen.getByText("商品ID/品名")).toBeVisible();
    expect(screen.getByText("SKU/MSKU")).toBeVisible();
    expect(screen.queryByText("系统运营日志")).not.toBeInTheDocument();
    expect(screen.queryByText("运营日志")).not.toBeInTheDocument();
    expect(screen.getAllByRole("separator", { name: /调整列宽/ })).toHaveLength(orderProfitColumnFields.length);
  });

  it("leaves global sync and help to MainLayout while keeping page actions in the toolbar", async () => {
    await renderPage();

    expect(screen.queryByText("同步时间：待接入")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "刷新订单利润" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /帮助/ })).not.toBeInTheDocument();

    const toolbar = screen.getByRole("search", { name: "订单利润筛选" });
    expect(within(toolbar).getByRole("button", { name: /隐藏统计$/ })).toBeVisible();
    expect(within(toolbar).getByRole("button", { name: /显示图表$/ })).toBeVisible();
    expect(within(toolbar).getByRole("button", { name: "列配置" })).toBeVisible();
    expect(within(toolbar).getByRole("button", { name: "下载" })).toBeVisible();
  });

  it("defaults to the previous completed day, product ID search, visible statistics and hidden charts", async () => {
    await renderPage();

    expect(screen.getByRole("button", { name: "今日" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByLabelText("日期范围值")).toHaveTextContent(`${referenceDay}~${referenceDay}`);
    expect(screen.getByLabelText("搜索类型")).toHaveValue("productId");
    expect(screen.queryByLabelText("订单利润趋势图")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /显示图表$/ }));
    expect(screen.getByLabelText("订单利润趋势图")).toBeVisible();
    const metricSelector = screen.getByLabelText("图表指标");
    for (const metric of ["销量", "销售额", "订单利润", "利润率", "广告费", "广告占比"]) {
      expect(within(metricSelector).getByRole("button", { name: metric })).toBeVisible();
    }
  });

  it("applies multi-select filters only after confirmation", async () => {
    await renderPage();

    fireEvent.change(screen.getByLabelText("平台"), { target: { value: "Walmart" } });
    expect(screen.getByTestId("pro-table")).toHaveAttribute("data-total", String(referenceRows.length));

    fireEvent.click(within(screen.getByTestId("平台-dropdown")).getByRole("button", { name: /确\s*定/ }));
    await waitFor(() => expect(Number(screen.getByTestId("pro-table").getAttribute("data-total"))).toBeLessThan(referenceRows.length));

    fireEvent.click(screen.getByRole("button", { name: "清除平台" }));
    await waitFor(() => expect(screen.getByTestId("pro-table")).toHaveAttribute("data-total", String(referenceRows.length)));
  });

  it("filters locally by product ID and opens the product-ID detail modal", async () => {
    const localStorageSpy = vi.spyOn(Storage.prototype, "setItem");
    const sessionStorageSpy = vi.spyOn(window.sessionStorage, "setItem");
    await renderPage();

    fireEvent.change(screen.getByLabelText("搜索内容"), { target: { value: referenceRows[0].productId } });
    fireEvent.click(screen.getByLabelText("搜索"));
    await waitFor(() => expect(screen.getByTestId("pro-table")).toHaveAttribute("data-total", "1"));
    fireEvent.click(screen.getByRole("button", { name: /查看订单利润详情/ }));
    expect(screen.getByRole("dialog", { name: "订单利润详情" })).toBeInTheDocument();
    expect(screen.getByText(/商品ID \/ 品名/)).toBeInTheDocument();
    expect(localStorageSpy).not.toHaveBeenCalled();
    expect(sessionStorageSpy).not.toHaveBeenCalled();
  });

  it("keeps a fixed total row and uses the selected display currency", async () => {
    await renderPage();

    const totalRow = screen.getByTestId("order-profit-total-row");
    expect(totalRow).toHaveTextContent("总计");
    expect(totalRow).toHaveTextContent(
      referenceRows.reduce((total, row) => total + row.salesVolume, 0).toLocaleString("zh-CN"),
    );
    expect(totalRow.querySelector(".order-profit__total-cell--salesAmount")).toHaveTextContent("$");

    fireEvent.change(screen.getByLabelText("币种"), { target: { value: "CNY" } });
    expect(screen.getByTestId("order-profit-total-row")).toHaveTextContent("¥");
  });
});

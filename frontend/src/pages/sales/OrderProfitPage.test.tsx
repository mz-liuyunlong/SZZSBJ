// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import dayjs from "dayjs";
import { useState, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { navigation } from "@/config/navigation";
import OrderProfitPage from "@/pages/sales/OrderProfitPage";
import { aggregateOrderProfitRows } from "@/pages/sales/orderProfitTypes";
import { orderProfitSourceRecords } from "@/pages/sales/orderProfitMockData";
import { orderProfitColumnFields } from "@/pages/sales/orderProfitTypes";

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
    classNames,
    maxTagCount,
    maxTagPlaceholder,
    mode,
    onChange,
    optionRender,
    options = [],
    placeholder,
    showSearch,
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
    void classNames;
    void maxTagCount;
    void maxTagPlaceholder;
    void showSearch;
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

const renderPage = () => render(<OrderProfitPage page={orderProfitPage!} />);
const today = dayjs().format("YYYY-MM-DD");
const todayRows = aggregateOrderProfitRows(orderProfitSourceRecords.filter((row) => row.date === today));

describe("OrderProfitPage", () => {
  it("renders the order-profit shell with product-ID aggregation and no log columns", () => {
    renderPage();

    expect(screen.getByRole("region", { name: "订单利润" }))
      .toContainElement(screen.getByLabelText("订单利润筛选"));
    expect(orderProfitSourceRecords).toHaveLength(800);
    expect(todayRows).toHaveLength(100);
    expect(screen.getByTestId("pro-table")).toHaveAttribute("data-total", String(todayRows.length));
    expect(screen.getByText("商品ID/品名")).toBeVisible();
    expect(screen.getByText("SKU/MSKU")).toBeVisible();
    expect(screen.queryByText("系统运营日志")).not.toBeInTheDocument();
    expect(screen.queryByText("运营日志")).not.toBeInTheDocument();
    expect(screen.getAllByRole("separator", { name: /调整列宽/ })).toHaveLength(orderProfitColumnFields.length);
  });

  it("leaves global sync and help to MainLayout while keeping page actions in the toolbar", () => {
    renderPage();

    expect(screen.queryByText("同步时间：待接入")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "刷新订单利润" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /帮助/ })).not.toBeInTheDocument();

    const toolbar = screen.getByRole("search", { name: "订单利润筛选" });
    expect(within(toolbar).getByRole("button", { name: /隐藏统计$/ })).toBeVisible();
    expect(within(toolbar).getByRole("button", { name: /显示图表$/ })).toBeVisible();
    expect(within(toolbar).getByRole("button", { name: "列配置" })).toBeVisible();
    expect(within(toolbar).getByRole("button", { name: "下载" })).toBeVisible();

  });

  it("defaults to today, product ID search, visible statistics and hidden charts", () => {
    renderPage();

    expect(screen.getByRole("button", { name: "今日" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("日期范围值")).toHaveTextContent(`${today}~${today}`);
    expect(screen.getByLabelText("搜索类型")).toHaveValue("productId");
    expect(screen.queryByLabelText("订单利润趋势图")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /显示图表$/ }));
    expect(screen.getByLabelText("订单利润趋势图")).toBeVisible();
    const metricSelector = screen.getByLabelText("图表指标");
    for (const metric of ["销量", "销售额", "订单利润", "利润率", "广告费", "广告占比"]) {
      expect(within(metricSelector).getByRole("button", { name: metric })).toBeVisible();
    }
  });

  it("filters locally by product ID and opens the product-ID detail modal", () => {
    const localStorageSpy = vi.spyOn(Storage.prototype, "setItem");
    const sessionStorageSpy = vi.spyOn(window.sessionStorage, "setItem");
    renderPage();

    fireEvent.change(screen.getByLabelText("搜索内容"), { target: { value: todayRows[0].productId } });
    expect(screen.getByTestId("pro-table")).toHaveAttribute("data-total", "1");
    fireEvent.click(screen.getByRole("button", { name: /查看订单利润详情/ }));
    expect(screen.getByRole("dialog", { name: "订单利润详情" })).toBeInTheDocument();
    expect(screen.getByText(/商品ID \/ 品名/)).toBeInTheDocument();
    expect(localStorageSpy).not.toHaveBeenCalled();
    expect(sessionStorageSpy).not.toHaveBeenCalled();
  });

  it("keeps a fixed total row and uses the selected display currency", () => {
    renderPage();

    const totalRow = screen.getByTestId("order-profit-total-row");
    expect(totalRow).toHaveTextContent("总计");
    expect(totalRow).toHaveTextContent(
      todayRows.reduce((total, row) => total + row.salesVolume, 0).toLocaleString("zh-CN"),
    );
    expect(totalRow.querySelector(".order-profit__total-cell--salesAmount")).toHaveTextContent("$");

    fireEvent.change(screen.getByLabelText("币种"), { target: { value: "CNY" } });
    expect(screen.getByTestId("order-profit-total-row")).toHaveTextContent("¥");
  });
});

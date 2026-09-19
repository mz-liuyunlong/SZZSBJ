// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactElement,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.setConfig({ testTimeout: 30_000 });
import type { NavigationPage } from "@/config/navigation";

vi.mock("@ant-design/icons", () => {
  const Icon = () => <span aria-hidden="true">icon</span>;
  return {
    ArrowDownOutlined: Icon,
    ArrowUpOutlined: Icon,
    AppstoreOutlined: Icon,
    CheckOutlined: Icon,
    CopyOutlined: Icon,
    CloudDownloadOutlined: Icon,
    DatabaseOutlined: Icon,
    DownOutlined: Icon,
    GoldenFilled: Icon,
    PartitionOutlined: Icon,
    PictureOutlined: Icon,
    PlayCircleFilled: Icon,
    SearchOutlined: Icon,
    SettingOutlined: Icon,
    SyncOutlined: Icon,
    UnorderedListOutlined: Icon,
  };
});

vi.mock("@/components/page/PageShell", () => ({
  default: ({
    page,
    children,
  }: {
    page: NavigationPage;
    children: ReactNode;
  }) => (
    <section className="page-shell" aria-label={page.title}>
      <div className="page-shell__content">{children}</div>
    </section>
  ),
}));

vi.mock("antd", async () => {
  const React = await import("react");

  interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type"> {
    danger?: boolean;
    htmlType?: "button" | "submit" | "reset";
    icon?: ReactNode;
    shape?: string;
    size?: string;
    type?: string;
  }

  const Button = ({
    children,
    danger,
    htmlType = "button",
    icon,
    shape,
    size,
    type: visualType,
    ...props
  }: ButtonProps) => (
    <button
      type={htmlType}
      data-danger={danger || undefined}
      data-shape={shape}
      data-size={size}
      data-variant={visualType}
      {...props}
    >
      {icon}
      {children}
    </button>
  );

  interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "prefix"> {
    allowClear?: boolean;
    onPressEnter?: () => void;
    prefix?: ReactNode;
  }

  interface TextAreaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
    rows?: number;
  }

  const Input = Object.assign(
    ({ allowClear, onPressEnter, onKeyDown, prefix, ...props }: InputProps) => (
      <input
        data-allow-clear={allowClear || undefined}
        data-has-prefix={Boolean(prefix) || undefined}
        {...props}
        onKeyDown={(event) => {
          onKeyDown?.(event);
          if (event.key === "Enter") onPressEnter?.();
        }}
      />
    ),
    { TextArea: (props: TextAreaProps) => <textarea {...props} /> },
  );

  interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "onChange"> {
    allowClear?: boolean;
    classNames?: unknown;
    maxTagCount?: number;
    maxTagPlaceholder?: ReactNode | (() => ReactNode);
    mode?: "multiple";
    onChange?: (value: string | string[] | undefined) => void;
    onClear?: () => void;
    onOpenChange?: (open: boolean) => void;
    open?: boolean;
    menuItemSelectedIcon?: ReactNode;
    optionFilterProp?: string;
    optionRender?: (option: { label: ReactNode; value: string }, info: { index: number }) => ReactNode;
    options?: { label: ReactNode; value: string }[];
    placeholder?: ReactNode;
    popupMatchSelectWidth?: boolean | number;
    popupRender?: (menu: ReactNode) => ReactNode;
    showSearch?: boolean;
    styles?: unknown;
    value?: string | string[];
  }

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
    placeholder,
    popupMatchSelectWidth,
    popupRender,
    showSearch,
    styles,
    value,
    ...props
  }: SelectProps) => {
    void classNames;
    void maxTagCount;
    void maxTagPlaceholder;
    void onOpenChange;
    void open;
    void menuItemSelectedIcon;
    void optionFilterProp;
    void optionRender;
    void popupMatchSelectWidth;
    void popupRender;
    void showSearch;
    void styles;
    return (
      <>
      <select
        data-allow-clear={allowClear || undefined}
        multiple={mode === "multiple"}
        value={value ?? (mode === "multiple" ? [] : "")}
        onChange={(event) => onChange?.(
          mode === "multiple"
            ? Array.from(event.target.selectedOptions, (option) => option.value)
            : event.target.value || undefined,
        )}
        {...props}
      >
        {mode !== "multiple" && <option value="">{placeholder}</option>}
        {options.map((option) => (
          <option key={option.value} value={option.value}>{option.value}</option>
        ))}
      </select>
      {allowClear && Boolean(Array.isArray(value) ? value.length : value) && (
        <button
          type="button"
          aria-label={`清除${String(props["aria-label"] ?? "")}`}
          onClick={() => {
            onClear?.();
            onChange?.(mode === "multiple" ? [] : undefined);
          }}
        >
          清除
        </button>
      )}
      {mode === "multiple" && (
        <span hidden>{options.map((option) => <span key={option.value}>{option.label}</span>)}</span>
      )}
      </>
    );
  };

  interface DialogProps {
    children: ReactNode;
    className?: string;
    footer?: ReactNode;
    onCancel?: () => void;
    onClose?: () => void;
    open: boolean;
    placement?: string;
    size?: string;
    title: ReactNode;
    width?: number;
  }

  const Modal = ({ children, className, footer, open, title, width }: DialogProps) =>
    open ? (
      <div role="dialog" aria-label={String(title)} className={className} data-width={width}>
        <h2>{title}</h2>
        {children}
        {footer}
      </div>
    ) : null;

  const Drawer = ({ children, footer, open, placement, size, title }: DialogProps) =>
    open ? (
      <aside
        role="dialog"
        aria-label={String(title)}
        data-placement={placement}
        data-size={size}
      >
        <h2>{title}</h2>
        {children}
        {footer}
      </aside>
    ) : null;

  const Popover = ({
    children,
    content,
    onOpenChange,
    open,
  }: {
    children: ReactElement;
    content: ReactNode;
    onOpenChange: (open: boolean) => void;
    open: boolean;
  }) => (
    <span data-overlay-kind="popover">
      <span onClick={() => onOpenChange(!open)}>{children}</span>
      {open && content}
    </span>
  );

  const Checkbox = ({
    checked,
    children,
    onChange,
    ...props
  }: {
    checked: boolean;
    children: ReactNode;
    onChange: (event: { target: { checked: boolean } }) => void;
    [key: string]: unknown;
  }) => (
    <label>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange({ target: { checked: event.target.checked } })}
        {...props}
      />
      {children}
    </label>
  );

  const Dropdown = ({
    children,
    menu,
    placement,
  }: {
    children: ReactElement;
    placement?: string;
    menu: {
      items: { danger?: boolean; disabled?: boolean; key: string; label: ReactNode }[];
      onClick: (info: { key: string }) => void;
    };
  }) => {
    const [open, setOpen] = React.useState(false);
    return (
      <span data-placement={placement}>
        <span onClick={() => setOpen((current) => !current)}>{children}</span>
        {open && (
          <div role="menu">
            {menu.items.map((item) => (
              <button
                key={item.key}
                type="button"
                role="menuitem"
                data-danger={item.danger || undefined}
                disabled={item.disabled}
                onClick={() => {
                  menu.onClick({ key: item.key });
                  setOpen(false);
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
        )}
      </span>
    );
  };

  const Menu = ({
    items,
    onClick,
    selectedKeys,
  }: {
    items: { key: string; label: ReactNode }[];
    onClick: (info: { key: string }) => void;
    selectedKeys: string[];
  }) => (
    <nav aria-label="详情菜单">
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          aria-current={selectedKeys.includes(item.key) ? "page" : undefined}
          onClick={() => onClick({ key: item.key })}
        >
          {item.label}
        </button>
      ))}
    </nav>
  );

  const Descriptions = ({
    items,
  }: {
    items: { children: ReactNode; key: string; label: ReactNode }[];
  }) => (
    <dl>
      {items.map((item) => (
        <div key={item.key}>
          <dt>{item.label}</dt>
          <dd>{item.children}</dd>
        </div>
      ))}
    </dl>
  );

  const Empty = Object.assign(
    ({ description }: { description: ReactNode }) => <div>{description}</div>,
    { PRESENTED_IMAGE_SIMPLE: "simple" },
  );

  const Typography = {
    Link: ({ children, onClick, strong }: {
      children: ReactNode;
      onClick?: () => void;
      strong?: boolean;
    }) => (
      <button type="button" onClick={onClick}>
        {strong ? <strong>{children}</strong> : children}
      </button>
    ),
    Paragraph: ({ children }: { children: ReactNode }) => <p>{children}</p>,
    Text: ({ children, strong }: { children: ReactNode; strong?: boolean }) =>
      strong ? <strong>{children}</strong> : <span>{children}</span>,
    Title: ({ children, id, level }: { children: ReactNode; id?: string; level: number }) =>
      level === 4 ? <h4 id={id}>{children}</h4> : <h5 id={id}>{children}</h5>,
  };

  return {
    Alert: ({ description, message }: { description: ReactNode; message: ReactNode }) => (
      <div>{message}{description}</div>
    ),
    Button,
    Card: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    Checkbox,
    Descriptions,
    Drawer,
    Dropdown,
    Empty,
    Input,
    Menu,
    Modal,
    Popover,
    Progress: ({ percent }: { percent: number }) => <div role="progressbar" aria-valuenow={percent} />,
    Select,
    Spin: ({ tip }: { tip: ReactNode }) => <div>{tip}</div>,
    Space: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    Tag: ({ children }: { children: ReactNode }) => <span>{children}</span>,
    Tooltip: ({ children, title }: { children: ReactNode; title: string }) => (
      <span data-tooltip={title}>{children}</span>
    ),
    Typography,
    message: {
      useMessage: () => {
        const [text, setText] = React.useState("");
        return [
          {
            error: (value: string) => setText(value),
            info: (value: string) => setText(value),
            success: (value: string) => setText(value),
          },
          text ? <output key="message">{text}</output> : null,
        ];
      },
    },
  };
});

interface MockColumn {
  title: ReactNode;
  dataIndex?: string;
  fixed?: string;
  key?: string;
  render?: (value: unknown, record: Record<string, unknown>) => ReactNode;
  sorter?: (left: Record<string, unknown>, right: Record<string, unknown>) => number;
  onHeaderCell?: () => { className?: string };
  width?: number;
}

interface MockTableProps {
  columns: MockColumn[];
  dataSource: Record<string, unknown>[];
  footer?: () => ReactNode;
  rowKey: string;
  request?: unknown;
  rowSelection?: {
    fixed?: boolean;
    onChange: (keys: string[]) => void;
    selectedRowKeys: (string | number)[];
  };
  scroll?: { x?: number | string; y?: number | string };
  tableAlertOptionRender?: boolean;
  tableAlertRender?: boolean;
  pagination: {
    current: number;
    onChange: (page: number, pageSize: number) => void;
    pageSize: number;
    pageSizeOptions: string[];
    showQuickJumper: boolean;
    showSizeChanger: boolean;
    total: number;
    showTotal: (total: number) => ReactNode;
  };
  locale?: { emptyText: ReactNode };
}

vi.mock("@ant-design/pro-components", () => ({
  ProTable: ({
    columns,
    dataSource,
    footer,
    rowKey,
    request,
    rowSelection,
    scroll,
    tableAlertOptionRender,
    tableAlertRender,
    pagination,
    locale,
  }: MockTableProps) => {
    const [sortState, setSortState] = useState<{ key: string; order: "ascend" | "descend" }>();
    const sortedData = [...dataSource];
    if (sortState) {
      const sortColumn = columns.find((column) => String(column.key) === sortState.key);
      if (sortColumn?.sorter) {
        sortedData.sort((left, right) => (
          sortState.order === "ascend" ? sortColumn.sorter!(left, right) : sortColumn.sorter!(right, left)
        ));
      }
    }
    const start = (pagination.current - 1) * pagination.pageSize;
    const pageData = pagination.total > sortedData.length
      ? sortedData
      : sortedData.slice(start, start + pagination.pageSize);
    const pageKeys = pageData.map((record) => String(record[rowKey]));
    const selectedPageKeys = rowSelection?.selectedRowKeys.map(String)
      .filter((key) => pageKeys.includes(key)) ?? [];
    const pageCount = Math.max(1, Math.ceil(pagination.total / pagination.pageSize));

    return (
      <div
        data-testid="pro-table"
        data-row-key={rowKey}
        data-has-request={String(Boolean(request))}
        data-scroll-x={scroll?.x}
        data-scroll-y={scroll?.y}
        data-source-count={dataSource.length}
        data-table-alert-option={String(tableAlertOptionRender)}
        data-table-alert={String(tableAlertRender)}
      >
      <div className="ant-table-container">
        <div className="ant-table-header">
          <table>
            <thead>
              <tr>
                {rowSelection && (
                  <th data-fixed={String(rowSelection.fixed)}>
                    <input
                      type="checkbox"
                      aria-label="选择当前页"
                      checked={pageData.length > 0 && selectedPageKeys.length === pageData.length}
                      ref={(input) => {
                        if (input) {
                          input.indeterminate = selectedPageKeys.length > 0
                            && selectedPageKeys.length < pageData.length;
                        }
                      }}
                      onChange={(event) => rowSelection.onChange(
                        event.target.checked
                          ? [...new Set([...rowSelection.selectedRowKeys.map(String), ...pageKeys])]
                          : rowSelection.selectedRowKeys.map(String).filter((key) => !pageKeys.includes(key)),
                      )}
                    />
                  </th>
                )}
                {columns.map((column, index) => {
                  const headerCellProps = column.onHeaderCell?.();
                  return (
                    <th
                      key={column.key ?? column.dataIndex ?? index}
                      {...headerCellProps}
                      data-sortable={String(Boolean(column.sorter))}
                      data-fixed={column.fixed}
                      data-width={column.width}
                      onClick={() => {
                        if (!column.sorter) return;
                        const key = String(column.key);
                        setSortState((current) => ({
                          key,
                          order: current?.key === key && current.order === "ascend" ? "descend" : "ascend",
                        }));
                      }}
                    >
                      {column.title}
                    </th>
                  );
                })}
              </tr>
            </thead>
          </table>
        </div>
        <div className="ant-table-body" data-scroll-y={scroll?.y}>
          <table>
            <tbody>
              {pageData.map((record, rowIndex) => (
                <tr key={String(record[rowKey] ?? rowIndex)}>
                  {rowSelection && (
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`选择 ${String(record[rowKey])}`}
                        checked={rowSelection.selectedRowKeys.includes(String(record[rowKey]))}
                        onChange={(event) => rowSelection.onChange(
                          event.target.checked
                            ? [...rowSelection.selectedRowKeys.map(String), String(record[rowKey])]
                            : rowSelection.selectedRowKeys.map(String).filter((key) => key !== String(record[rowKey])),
                        )}
                      />
                    </td>
                  )}
                  {columns.map((column, columnIndex) => {
                    const value = column.dataIndex ? record[column.dataIndex] : undefined;
                    return (
                      <td key={column.key ?? column.dataIndex ?? columnIndex}>
                        {column.render?.(value, record) ?? String(value ?? "")}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {dataSource.length === 0 && locale?.emptyText}
      {footer && <div className="ant-table-footer">{footer()}</div>}
      <nav className="ant-pagination" aria-label="分页">
        {pagination.showTotal(pagination.total)}
        <button
          type="button"
          aria-label="上一页"
          disabled={pagination.current === 1}
          onClick={() => pagination.onChange(pagination.current - 1, pagination.pageSize)}
        >
          上一页
        </button>
        {Array.from({ length: pageCount }, (_, index) => index + 1).map((page) => (
          <button
            key={page}
            type="button"
            aria-label={`第 ${page} 页`}
            aria-current={pagination.current === page ? "page" : undefined}
            onClick={() => pagination.onChange(page, pagination.pageSize)}
          >
            {page}
          </button>
        ))}
        <button
          type="button"
          aria-label="下一页"
          disabled={pagination.current === pageCount}
          onClick={() => pagination.onChange(pagination.current + 1, pagination.pageSize)}
        >
          下一页
        </button>
        <select
          aria-label="每页条数"
          value={pagination.pageSize}
          onChange={(event) => pagination.onChange(1, Number(event.target.value))}
        >
          {pagination.pageSizeOptions.map((option) => (
            <option key={option} value={option}>{option}条/页</option>
          ))}
        </select>
        <label>
          跳至
          <input
            aria-label="跳至页码"
            onKeyDown={(event) => {
              if (event.key !== "Enter") return;
              const page = Number(event.currentTarget.value);
              if (page >= 1 && page <= pageCount) pagination.onChange(page, pagination.pageSize);
            }}
          />
          页
        </label>
      </nav>
      </div>
    );
  },
}));

vi.mock("@/pages/products/productManagementApi", () => ({
  getProductManagementOptions: vi.fn(),
  getProductManagementSku: vi.fn(),
  getProductManagementSummary: vi.fn(),
  getProductManagementTableView: vi.fn(),
  listProductManagementSkus: vi.fn(),
  requestProductManagementExport: vi.fn(),
  saveProductManagementTableView: vi.fn(),
}));

import ProductManagementPage from "@/pages/products/ProductManagementPage";
import { clearPageStateCache } from "@/shared/page-state/pageStateCache";
import {
  getProductManagementOptions,
  getProductManagementSku,
  getProductManagementSummary,
  getProductManagementTableView,
  listProductManagementSkus,
  saveProductManagementTableView,
} from "@/pages/products/productManagementApi";
import type { ProductManagementRow } from "@/pages/products/productManagementTypes";

const productPage = {
  key: "products_product_management",
  title: "产品管理",
  path: "/products/management",
  phase: 1,
  status: "planned",
  source: "pending",
  sourceTables: [],
  readOnly: false,
  migrationMode: "pending",
  permissionKey: "products.product_management.view",
  help: {
    enabled: false,
    title: "产品管理帮助",
    helpUrl: "/help/products/product_management",
    openInNewTab: true,
  },
} as NavigationPage;

const row: ProductManagementRow = {
  id: "synthetic-id",
  image: null,
  images: [],
  imageCount: 0,
  sku: "SYNTHETIC-SKU",
  productName: "Synthetic Product",
  tags: [],
  sourceTags: ["Synthetic Source Tag"],
  ownerUid: null,
  ownerName: null,
  developerUid: null,
  developerName: null,
  productGrade: null,
  category: null,
  purchasePrice: null,
  firstLegFreight: null,
  wfsDeliveryFee: null,
  purchaseLeadTime: null,
  storageFee: null,
  wfsFee: null,
  suggestedPrice: null,
  minimumPrice: null,
  clearancePrice: null,
  calculationStatus: "pricing_unavailable",
  rootMissingCodes: ["missing_purchase_cost"],
  pricingAvailable: false,
  billingRootComplete: false,
  wfsCalculationStatus: "unavailable",
  wfsCalculationReason: "missing_weight_or_dimensions",
  storageCalculationStatus: "unavailable",
  firstLegCalculationStatus: "unavailable",
  formulaVersion: "sku_pricing_formula_v1",
  pricingBreakdown: null,
  materialCn: null,
  materialEn: null,
  usageCn: null,
  usageEn: null,
  customsNameCn: null,
  customsNameEn: null,
  packageSpec: null,
  cartonSpec: null,
  productSpec: null,
  grossWeightKg: null,
  netWeightKg: null,
  dataCompleteness: 0,
  linkedPlatformSkuCount: 0,
  updatedAt: null,
};

beforeEach(() => {
  clearPageStateCache();
  vi.mocked(listProductManagementSkus).mockResolvedValue({ rows: [row], total: 1 });
  vi.mocked(getProductManagementOptions).mockResolvedValue({
    grades: [],
    gradeOptions: [],
    owners: [],
    developers: [],
    tags: [],
  });
  vi.mocked(getProductManagementSummary).mockResolvedValue({
    total: 1,
    syncedDetailCount: 1,
    dataCompletenessRate: 80,
    withImageCount: 1,
    withSourceTagCount: 1,
    incompleteCount: 1,
    missingPurchaseCostCount: 1,
    missingPurchaseDeliveryCount: 1,
    missingGrossWeightCount: 1,
    missingPackageDimensionsCount: 1,
    missingImageCount: 1,
    missingDimensionImageCount: 1,
    invalidPricingRuleCount: 0,
    pricingOkCount: 0,
  });
  vi.mocked(getProductManagementTableView).mockResolvedValue({
    applied_column_keys: ["sku", "productName"],
    column_widths: {},
    schema_version: 1,
    view_key: "default",
    updated_at: null,
  });
  vi.mocked(saveProductManagementTableView).mockResolvedValue({
    applied_column_keys: ["image", "sku", "productName"],
    column_widths: {},
    schema_version: 1,
    view_key: "default",
    updated_at: null,
  });
  vi.mocked(getProductManagementSku).mockResolvedValue({ ...row, image: "synthetic-image" });
});

afterEach(() => {
  clearPageStateCache();
  cleanup();
  vi.clearAllMocks();
  window.localStorage.clear();
});

const renderProductPage = () => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <ProductManagementPage page={productPage} preferenceScope="synthetic-user" />
    </QueryClientProvider>,
  );
};

describe("ProductManagementPage", () => {
  it("hides statistics by default and uses backend totals when shown", async () => {
    vi.mocked(listProductManagementSkus).mockResolvedValue({
      rows: Array.from({ length: 50 }, (_, index) => ({
        ...row,
        id: `synthetic-id-${index}`,
        sku: `SYNTHETIC-${index}`,
      })),
      total: 1188,
    });
    vi.mocked(getProductManagementSummary).mockResolvedValueOnce({
      total: 1188,
      syncedDetailCount: 1188,
      dataCompletenessRate: 80,
      withImageCount: 1000,
      withSourceTagCount: 1188,
      incompleteCount: 188,
      missingPurchaseCostCount: 17,
      missingPurchaseDeliveryCount: 21,
      missingGrossWeightCount: 31,
      missingPackageDimensionsCount: 27,
      missingImageCount: 11,
      missingDimensionImageCount: 15,
      invalidPricingRuleCount: 0,
      pricingOkCount: 1100,
    });

    renderProductPage();

    expect(await screen.findByText("共 1,188 条数据")).toBeVisible();
    expect(screen.queryByLabelText("产品管理统计")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "显示统计" }));
    expect(await screen.findByLabelText("产品管理统计")).toHaveTextContent("1,188");
    expect(await screen.findByRole("button", { name: "缺采购价：17" })).toBeVisible();
    expect(await screen.findByRole("button", { name: "缺图片：11" })).toBeVisible();
    expect(getProductManagementSummary).toHaveBeenCalledWith(
      expect.objectContaining({ keyword: "" }),
    );
  });

  it("uses real-data default columns and keeps fee and price columns optional", async () => {
    vi.mocked(getProductManagementTableView).mockRejectedValueOnce(new Error("no saved view"));

    renderProductPage();
    await screen.findByRole("button", { name: "SYNTHETIC-SKU" });

    expect(screen.queryByRole("columnheader", { name: /类目/ })).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /产品采购价/ })).toBeVisible();
    expect(screen.getByRole("columnheader", { name: /负责人/ })).toBeVisible();
    expect(screen.getByRole("columnheader", { name: /开发人/ })).toBeVisible();
    expect(screen.queryByRole("columnheader", { name: /资料完整度/ })).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /每日仓储费/ })).toBeVisible();
    expect(screen.queryByRole("columnheader", { name: /建议售价/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: /最低售价/ })).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /清仓售价/ })).toBeVisible();
  });

  it("can restore real-data defaults over an older saved column view", async () => {
    vi.mocked(getProductManagementTableView).mockResolvedValueOnce({
      applied_column_keys: ["sku", "productName", "wfsFee", "suggestedPrice"],
      column_widths: {},
      schema_version: 1,
      view_key: "default",
      updated_at: null,
    });

    renderProductPage();
    expect(await screen.findByRole("columnheader", { name: /每日仓储费/ })).toBeVisible();
    expect((await screen.findAllByText("缺基础数据")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "列配置" }));
    fireEvent.click(screen.getByRole("button", { name: "恢复默认" }));
    fireEvent.click(screen.getByRole("button", { name: "保存并应用" }));

    expect(screen.queryByRole("columnheader", { name: /类目/ })).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /每日仓储费/ })).toBeVisible();
    expect(screen.queryByRole("columnheader", { name: /建议售价/ })).not.toBeInTheDocument();
  });

  it("loads rows from the backend and opens backend detail data", async () => {
    renderProductPage();

    expect(await screen.findByRole("button", { name: "SYNTHETIC-SKU" })).toBeVisible();
    expect(screen.getByText("共 1 条数据")).toBeVisible();
    expect(listProductManagementSkus).toHaveBeenCalledWith(
      expect.objectContaining({ keyword: "" }),
      1,
      50,
    );

    fireEvent.click(screen.getByRole("button", { name: "SYNTHETIC-SKU" }));
    await waitFor(() => expect(getProductManagementSku).toHaveBeenCalledWith(row));
    expect(await screen.findByRole("dialog", { name: "产品详情" })).toBeVisible();
  });

  it("sends changed filters to the backend and renders safe failures", async () => {
    renderProductPage();
    await screen.findByRole("button", { name: "SYNTHETIC-SKU" });
    const requestsBeforeTyping = vi.mocked(listProductManagementSkus).mock.calls.length;
    fireEvent.change(screen.getByLabelText("搜索产品"), { target: { value: "filtered" } });
    fireEvent.click(screen.getByLabelText("搜索"));
    expect(vi.mocked(listProductManagementSkus).mock.calls.length).toBe(requestsBeforeTyping);
    fireEvent.click(screen.getByRole("button", { name: "搜索" }));
    await waitFor(() => expect(listProductManagementSkus).toHaveBeenLastCalledWith(
      expect.objectContaining({ keyword: "filtered" }),
      1,
      50,
    ));
    expect(screen.getByRole("button", { name: "SYNTHETIC-SKU" })).toBeVisible();

    vi.mocked(listProductManagementSkus).mockRejectedValueOnce(new Error("SAFE_BACKEND_ERROR"));
    fireEvent.change(screen.getByLabelText("搜索产品"), { target: { value: "failed" } });
    fireEvent.click(screen.getByLabelText("搜索"));
    fireEvent.click(screen.getByRole("button", { name: "搜索" }));
    expect(await screen.findByText(/SAFE_BACKEND_ERROR/)).toBeVisible();
  });

  it("renders each server-provided page without applying client-side business filters", async () => {
    vi.mocked(listProductManagementSkus).mockResolvedValue({ rows: [row], total: 100 });
    renderProductPage();
    await screen.findByRole("button", { name: "SYNTHETIC-SKU" });

    fireEvent.click(screen.getByRole("button", { name: "第 2 页" }));
    await waitFor(() => expect(listProductManagementSkus).toHaveBeenLastCalledWith(
      expect.objectContaining({ keyword: "" }),
      2,
      50,
    ));
    expect(screen.getByRole("button", { name: "SYNTHETIC-SKU" })).toBeVisible();
  });
});

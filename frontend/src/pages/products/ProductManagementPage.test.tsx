// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import {
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactElement,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { NavigationPage } from "../../config/navigation";

const SYNC_PENDING = "同步接口待接入";
const TAG_PENDING = "标签接口待接入";

vi.mock("@ant-design/icons", () => {
  const Icon = () => <span aria-hidden="true">icon</span>;
  return {
    ArrowDownOutlined: Icon,
    ArrowUpOutlined: Icon,
    CopyOutlined: Icon,
    DownOutlined: Icon,
    PictureOutlined: Icon,
    SearchOutlined: Icon,
    SettingOutlined: Icon,
    SyncOutlined: Icon,
    UnorderedListOutlined: Icon,
  };
});

vi.mock("../../components/page/PageShell", () => ({
  default: ({
    page,
    description,
    headerActions,
    children,
  }: {
    page: NavigationPage;
    description?: string;
    headerActions?: ReactNode;
    children: ReactNode;
  }) => (
    <>
      <div role="group" aria-label="页面级操作">
        {headerActions}
        {page.help.enabled && (
          <a aria-label={`在新标签页打开${page.help.title}`} href={page.help.helpUrl}>帮助</a>
        )}
      </div>
      <section className="page-shell" aria-label="当前页面">
        <header className="page-shell__header">
          <div className="page-shell__heading">
            <h1 aria-label="当前页面">{page.title}</h1>
            <span aria-label={`页面状态：${page.status}`}>规划中</span>
            {description && <p>{description}</p>}
          </div>
        </header>
        <div className="page-shell__content">{children}</div>
      </section>
    </>
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

  interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
    allowClear?: boolean;
    onPressEnter?: () => void;
  }

  interface TextAreaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
    rows?: number;
  }

  const Input = Object.assign(
    ({ allowClear, onPressEnter, onKeyDown, ...props }: InputProps) => (
      <input
        data-allow-clear={allowClear || undefined}
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
    mode?: "multiple";
    onChange?: (value: string | string[] | undefined) => void;
    options?: { label: ReactNode; value: string }[];
    placeholder?: ReactNode;
    value?: string | string[];
  }

  const Select = ({
    allowClear,
    mode,
    onChange,
    options = [],
    placeholder,
    value,
    ...props
  }: SelectProps) => (
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
      {mode === "multiple" && (
        <span hidden>{options.map((option) => <span key={option.value}>{option.label}</span>)}</span>
      )}
    </>
  );

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
  }: {
    children: ReactElement;
    menu: {
      items: { danger?: boolean; key: string; label: ReactNode }[];
      onClick: (info: { key: string }) => void;
    };
  }) => {
    const [open, setOpen] = React.useState(false);
    return (
      <span>
        <span onClick={() => setOpen((current) => !current)}>{children}</span>
        {open && (
          <div role="menu">
            {menu.items.map((item) => (
              <button
                key={item.key}
                type="button"
                role="menuitem"
                data-danger={item.danger || undefined}
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
    Paragraph: ({ children }: { children: ReactNode }) => <p>{children}</p>,
    Text: ({ children, strong }: { children: ReactNode; strong?: boolean }) =>
      strong ? <strong>{children}</strong> : <span>{children}</span>,
    Title: ({ children, id, level }: { children: ReactNode; id?: string; level: number }) =>
      level === 4 ? <h4 id={id}>{children}</h4> : <h5 id={id}>{children}</h5>,
  };

  return {
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
    Select,
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
  locale: { emptyText: ReactNode };
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
    const pageData = sortedData.slice(start, start + pagination.pageSize);
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
      {dataSource.length === 0 && locale.emptyText}
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

import ProductManagementPage from "./ProductManagementPage";

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

const productPage: NavigationPage = {
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
    enabled: true,
    title: "产品管理帮助",
    helpUrl: "/help/products/product_management",
    openInNewTab: true,
  },
};

const renderPage = () => render(<ProductManagementPage page={productPage} />);

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  vi.stubGlobal("fetch", vi.fn());
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

describe("ProductManagementPage", () => {
  it("renders the final toolbar, selectable table columns, sorting, and pagination shell", () => {
    const view = renderPage();

    expect(screen.getByRole("heading", { name: "当前页面" })).toHaveTextContent(productPage.title);
    expect(view.container.querySelector(
      ".page-shell:has(> .page-shell__content .product-management) > .page-shell__header > .page-shell__heading",
    )).not.toBeNull();
    expect(screen.queryByText(productPage.permissionKey)).not.toBeInTheDocument();
    expect(screen.queryByText(/前端静态验收示例数据/)).not.toBeInTheDocument();
    expect(screen.queryByText(/不来自 API/)).not.toBeInTheDocument();
    expect(screen.queryByText(/当前排序仅作用于前端验收示例数据/)).not.toBeInTheDocument();

    const toolbar = screen.getByRole("search", { name: "产品筛选与页面工具" });
    expect(toolbar).toHaveClass("product-management__toolbar");
    expect(within(toolbar).getByRole("combobox", { name: "产品等级" })).toBeVisible();
    expect(within(toolbar).getByRole("combobox", { name: "标签" })).toBeVisible();
    expect(within(toolbar).getByRole("combobox", { name: "搜索类型" })).toHaveValue("sku");
    expect(within(toolbar).getByRole("button", { name: "批量搜索 SKU" })).toBeVisible();
    const moreButton = within(toolbar).getByRole("button", { name: /更多/ });
    expect(moreButton).toBeVisible();
    expect(moreButton.querySelectorAll('[aria-hidden="true"]')).toHaveLength(1);
    expect(within(toolbar).getByRole("button", { name: "重置" })).toBeVisible();
    expect(within(toolbar).queryByRole("combobox", { name: "WFS费用" })).not.toBeInTheDocument();
    expect(within(toolbar).queryByText("最后同步时间：待接入")).not.toBeInTheDocument();
    expect(within(toolbar).queryByText("更多筛选")).not.toBeInTheDocument();
    expect(within(toolbar).queryByText("预览产品详情结构")).not.toBeInTheDocument();

    const pageActions = screen.getByRole("group", { name: "页面级操作" });
    const syncState = within(pageActions).getByText("最后同步时间：待接入").closest("div");
    expect(syncState).toHaveClass("product-management__sync-state");
    expect(within(pageActions).getByRole("button", { name: "同步数据" })).toHaveAttribute(
      "data-shape",
      "circle",
    );
    expect(within(pageActions).getByRole("link", { name: "在新标签页打开产品管理帮助" }))
      .toHaveTextContent("帮助");
    expect(screen.getAllByText("最后同步时间：待接入")).toHaveLength(1);
    expect(screen.getAllByText("帮助")).toHaveLength(1);
    const productContent = view.container.querySelector(".product-management");
    expect(productContent).not.toBeNull();
    expect(productContent?.parentElement).toHaveClass("page-shell__content");
    expect(productContent?.closest(".page-shell")).toBeInTheDocument();
    expect(within(productContent as HTMLElement).queryByText("最后同步时间：待接入"))
      .not.toBeInTheDocument();
    expect(within(productContent as HTMLElement).queryByText("帮助")).not.toBeInTheDocument();
    expect(toolbar.querySelector(".product-management__search-box")).toContainElement(
      within(toolbar).getByRole("combobox", { name: "搜索类型" }),
    );

    const table = screen.getByRole("region", { name: "产品管理主表" });
    expect(within(table).getAllByText(/验收示例产品/)).toHaveLength(10);
    expect(within(table).getByText("共 50 条")).toBeVisible();
    expect(screen.getByTestId("pro-table")).toHaveAttribute("data-row-key", "id");
    expect(screen.getByTestId("pro-table")).toHaveAttribute("data-has-request", "false");
    expect(screen.getByTestId("pro-table")).toHaveAttribute("data-scroll-x", "max-content");
    expect(screen.getByTestId("pro-table")).toHaveAttribute(
      "data-scroll-y",
      "max(240px, calc(100dvh - 390px))",
    );
    expect(screen.getByTestId("pro-table")).toHaveAttribute("data-source-count", "50");
    expect(screen.getByTestId("pro-table")).toHaveAttribute("data-table-alert", "false");
    expect(screen.getByTestId("pro-table")).toHaveAttribute("data-table-alert-option", "false");
    const tableBody = view.container.querySelector(".ant-table-body");
    expect(tableBody).toHaveAttribute("data-scroll-y", "max(240px, calc(100dvh - 390px))");
    expect(tableBody).not.toContainElement(view.container.querySelector(".ant-pagination"));
    expect(within(table).getByRole("checkbox", { name: "选择当前页" })).toBeVisible();

    const headerNames = within(table).getAllByRole("columnheader").map((header) => header.textContent?.trim());
    expect(headerNames).toEqual([
      "",
      "图片",
      "SKU",
      "产品名称",
      "标签",
      "产品等级",
      "WFS费用",
      "建议售价",
      "最低售价",
      "清仓售价",
      "操作",
    ]);
    const sortableTitles = within(table)
      .getAllByRole("columnheader")
      .filter((header) => header.dataset.sortable === "true")
      .map((header) => header.textContent?.trim());
    expect(sortableTitles).toEqual(["SKU", "产品等级", "WFS费用", "建议售价", "最低售价", "清仓售价"]);
    expect(within(table).queryByRole("columnheader", { name: "详情" })).not.toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "操作" })).toHaveAttribute("data-fixed", "right");
    expect(within(table).getAllByRole("separator", { name: /调整列宽/ })).toHaveLength(9);
    expect(within(table).getByRole("combobox", { name: "每页条数" })).toHaveValue("10");
    expect(within(table).getByLabelText("跳至页码")).toBeVisible();
    expect(view.container.querySelector(".ant-pagination")).toBeInTheDocument();

    const productNameCell = within(table).getByText("验收示例产品 001").closest("td");
    expect(productNameCell).not.toHaveTextContent("测品");
    fireEvent.click(within(table).getByRole("button", { name: "第 2 页" }));
    expect(within(table).queryByText("验收示例产品 001")).not.toBeInTheDocument();
    expect(within(table).getByText("验收示例产品 011")).toBeVisible();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("applies local SKU search and reset while preserving existing storage", () => {
    localStorage.setItem("existing_local", "keep");
    sessionStorage.setItem("tab_workspace", "keep");
    renderPage();

    fireEvent.click(screen.getByRole("checkbox", { name: "选择 acceptance-product-1" }));
    expect(screen.getByText("已选择 1 项")).toBeVisible();
    fireEvent.change(screen.getByLabelText("搜索内容"), { target: { value: "ui-sample-025" } });
    fireEvent.click(screen.getByRole("button", { name: "搜索产品" }));
    expect(screen.getByText("共 1 条")).toBeVisible();
    expect(screen.getByRole("button", { name: "UI-SAMPLE-025" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "UI-SAMPLE-001" })).not.toBeInTheDocument();
    expect(screen.queryByText("已选择 1 项")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "同步数据" }));
    expect(screen.getByText(SYNC_PENDING)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "重置" }));
    expect(screen.getByLabelText("搜索内容")).toHaveValue("");
    expect(screen.getByText("共 50 条")).toBeVisible();
    expect(screen.getByRole("button", { name: "UI-SAMPLE-001" })).toBeVisible();

    expect(localStorage.getItem("existing_local")).toBe("keep");
    expect(sessionStorage.getItem("tab_workspace")).toBe("keep");
    expect(localStorage).toHaveLength(1);
    expect(sessionStorage).toHaveLength(1);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("filters locally by grade and tag, resets pagination and selection, and sorts filtered rows", () => {
    renderPage();
    const table = screen.getByRole("region", { name: "产品管理主表" });
    fireEvent.click(within(table).getByRole("button", { name: "第 2 页" }));
    fireEvent.click(within(table).getByRole("checkbox", { name: "选择 acceptance-product-11" }));
    fireEvent.change(screen.getByRole("combobox", { name: "产品等级" }), { target: { value: "B级" } });

    expect(within(table).getByText("共 17 条")).toBeVisible();
    expect(within(table).getByRole("button", { name: "第 1 页" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByText("已选择 1 项")).not.toBeInTheDocument();
    for (const row of within(table).getAllByRole("row").slice(1)) {
      expect(row).toHaveTextContent("B级");
    }

    const skuHeader = within(table).getAllByRole("columnheader")
      .find((header) => header.textContent?.trim() === "SKU");
    expect(skuHeader).toBeDefined();
    fireEvent.click(skuHeader!);
    fireEvent.click(skuHeader!);
    expect(within(table).getAllByRole("button", { name: /^UI-SAMPLE-/ })[0]).toHaveTextContent("UI-SAMPLE-050");

    fireEvent.click(screen.getByRole("button", { name: "重置" }));
    expect(within(table).getAllByRole("button", { name: /^UI-SAMPLE-/ })[0]).toHaveTextContent("UI-SAMPLE-001");
    fireEvent.change(screen.getByRole("combobox", { name: "标签" }), { target: { value: "测品" } });
    expect(within(table).getByText("共 20 条")).toBeVisible();
    for (const row of within(table).getAllByRole("row").slice(1)) {
      expect(row).toHaveTextContent("测品");
    }
  });

  it("keeps the table header and pagination fixed when page size changes", () => {
    const view = renderPage();
    const table = screen.getByRole("region", { name: "产品管理主表" });
    fireEvent.change(screen.getByLabelText("搜索内容"), { target: { value: "UI-SAMPLE-" } });
    fireEvent.click(screen.getByRole("button", { name: "搜索产品" }));
    fireEvent.change(screen.getByRole("combobox", { name: "产品等级" }), { target: { value: "B级" } });
    const skuHeader = within(table).getAllByRole("columnheader")
      .find((header) => header.textContent?.trim() === "SKU");
    fireEvent.click(skuHeader!);
    fireEvent.click(skuHeader!);
    fireEvent.click(within(table).getByRole("button", { name: "第 2 页" }));
    fireEvent.click(within(table).getAllByRole("checkbox", { name: /选择 acceptance-product-/ })[0]);
    expect(screen.getByText("已选择 1 项")).toBeVisible();

    fireEvent.change(within(table).getByRole("combobox", { name: "每页条数" }), {
      target: { value: "20" },
    });

    expect(within(table).getByRole("button", { name: "第 1 页" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.queryByText("已选择 1 项")).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "产品等级" })).toHaveValue("B级");
    expect(screen.getByLabelText("搜索内容")).toHaveValue("UI-SAMPLE-");
    expect(within(table).getAllByText(/验收示例产品/)).toHaveLength(17);
    expect(within(table).getAllByRole("button", { name: /^UI-SAMPLE-/ })[0])
      .toHaveTextContent("UI-SAMPLE-050");

    const tableHeader = view.container.querySelector<HTMLElement>(".ant-table-header");
    const tableBody = view.container.querySelector<HTMLElement>(".ant-table-body");
    const pagination = view.container.querySelector<HTMLElement>(".ant-pagination");
    expect(tableHeader).toBeInTheDocument();
    expect(tableBody).not.toContainElement(tableHeader);
    expect(pagination).not.toBeNull();
    expect(tableBody).not.toContainElement(pagination);
    expect(localStorage).toHaveLength(0);
    expect(sessionStorage).toHaveLength(0);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("uses the batch-search popover for exact local matches and rejects more than 1000 lines", () => {
    renderPage();
    fireEvent.click(screen.getByRole("checkbox", { name: "选择 acceptance-product-1" }));
    expect(screen.getByText("已选择 1 项")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "批量搜索 SKU" }));

    let dialog = screen.getByRole("dialog", { name: "批量搜索 SKU" });
    expect(dialog.closest('[data-overlay-kind="popover"]')).toBeInTheDocument();
    expect(within(dialog).getByText("精确搜索，一行一项，最多支持1000行")).toBeVisible();
    const input = within(dialog).getByLabelText("批量 SKU 输入");
    fireEvent.change(input, {
      target: { value: " UI-SAMPLE-003\n\nUI-SAMPLE-011\nUI-SAMPLE-004,UI-SAMPLE-005 " },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "搜索" }));
    expect(input).toHaveValue("UI-SAMPLE-003\nUI-SAMPLE-011\nUI-SAMPLE-004,UI-SAMPLE-005");
    expect(screen.getByText("共 2 条")).toBeVisible();
    expect(screen.getByRole("button", { name: "UI-SAMPLE-003" })).toBeVisible();
    expect(screen.getByRole("button", { name: "UI-SAMPLE-011" })).toBeVisible();
    expect(screen.queryByText("已选择 1 项")).not.toBeInTheDocument();
    fireEvent.change(input, {
      target: { value: Array.from({ length: 1_001 }, (_, index) => `SKU-${index}`).join("\n") },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "搜索" }));
    expect(screen.getByText("最多支持1000行")).toBeVisible();
    fireEvent.click(within(dialog).getByRole("button", { name: "清空" }));
    expect(input).toHaveValue("");
    expect(screen.getByText("共 50 条")).toBeVisible();
    fireEvent.change(input, { target: { value: "NOT-SAVED" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "搜索" }));
    expect(screen.getByText("暂无匹配产品")).toBeVisible();
    fireEvent.click(within(dialog).getByRole("button", { name: "关闭" }));
    expect(screen.queryByRole("dialog", { name: "批量搜索 SKU" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "批量搜索 SKU" }));
    dialog = screen.getByRole("dialog", { name: "批量搜索 SKU" });
    expect(within(dialog).getByLabelText("批量 SKU 输入")).toHaveValue("");
  });

  it("selects only the current page and gates the top more-menu mark action", () => {
    sessionStorage.setItem("tab_workspace", "keep");
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /更多/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: "标记" }));
    expect(screen.getByText("请先选择产品")).toBeVisible();

    fireEvent.click(screen.getByRole("checkbox", { name: "选择当前页" }));
    expect(screen.getByText("已选择 10 项")).toBeVisible();
    const selectionFooter = screen.getByText("已选择 10 项").closest(".ant-table-footer");
    const pagination = screen.getByRole("navigation", { name: "分页" });
    expect(selectionFooter?.parentElement).toBe(pagination.parentElement);
    expect(screen.queryByRole("button", { name: "批量标记标签" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "清空选择" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "第 2 页" }));
    expect(screen.getByRole("checkbox", { name: "选择当前页" })).not.toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: /更多/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: "标记" }));
    const dialog = screen.getByRole("dialog", { name: "标记标签" });
    const tagSelect = within(dialog).getByRole("listbox", { name: "标记标签选择" });
    expect(tagSelect).toBeVisible();
    expect(tagSelect).toHaveValue([]);
    const tagDots = dialog.querySelectorAll(".product-management__tag-option-dot");
    expect(tagDots).toHaveLength(3);
    expect(Array.from(tagDots).map((dot) => (dot as HTMLElement).style.backgroundColor)).toEqual([
      "rgb(77, 141, 247)",
      "rgb(245, 158, 11)",
      "rgb(239, 83, 80)",
    ]);
    expect(dialog).toHaveAttribute("data-width", "560");
    expect(within(dialog).queryByRole("button", { name: "新建标签" })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "添加产品标签" })).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
    expect(sessionStorage.getItem("tab_workspace")).toBe("keep");
    expect(localStorage).toHaveLength(0);
  });

  it("uses a right drawer and applies checked and dragged column order only at runtime", () => {
    sessionStorage.setItem("tab_workspace", "keep");
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "列配置" }));

    const drawer = screen.getByRole("dialog", { name: "列配置" });
    expect(drawer).toHaveAttribute("data-placement", "right");
    expect(within(drawer).getByRole("combobox", { name: "选择模板" })).toBeDisabled();
    for (const group of ["默认主表字段", "可选基本信息字段"]) {
      expect(within(drawer).getByText(group)).toBeVisible();
    }
    for (const excluded of [
      "物流报关清关",
      "图片信息",
      "商品分析资料",
      "包装规格",
      "单箱重量",
      "操作",
    ]) {
      expect(within(drawer).queryByText(excluded)).not.toBeInTheDocument();
    }

    const imageCheckbox = within(drawer).getByRole("checkbox", { name: "显示列：图片" });
    const skuCheckbox = within(drawer).getByRole("checkbox", { name: "显示列：SKU" });
    expect(imageCheckbox).toBeChecked();
    expect(imageCheckbox).toBeDisabled();
    expect(skuCheckbox).toBeChecked();
    expect(skuCheckbox).toBeDisabled();
    expect(within(drawer).getByLabelText("固定字段：图片")).toHaveAttribute("draggable", "false");
    expect(within(drawer).getByLabelText("固定字段：SKU")).toHaveAttribute("draggable", "false");

    fireEvent.click(within(drawer).getByRole("button", { name: "取消全选" }));
    expect(imageCheckbox).toBeChecked();
    expect(skuCheckbox).toBeChecked();
    expect(within(drawer).getByRole("checkbox", { name: "显示列：产品名称" })).not.toBeChecked();
    fireEvent.click(within(drawer).getByRole("button", { name: "全选" }));

    const tags = within(drawer).getByLabelText("拖动字段：标签");
    const productName = within(drawer).getByLabelText("拖动字段：产品名称");
    fireEvent.dragStart(tags);
    fireEvent.dragOver(productName);
    fireEvent.drop(productName);
    fireEvent.click(within(drawer).getByRole("button", { name: "保存并应用" }));

    const headers = screen.getAllByRole("columnheader").map((item) => item.textContent?.trim());
    expect(headers.slice(1, 4)).toEqual(["图片", "SKU", "标签"]);
    expect(headers).toContain("类目");
    expect(headers.at(-1)).toBe("操作");
    expect(sessionStorage.getItem("tab_workspace")).toBe("keep");
    expect(localStorage).toHaveLength(0);
  });

  it("resizes business columns with native handles but not system columns", () => {
    renderPage();
    const table = screen.getByRole("region", { name: "产品管理主表" });
    const handles = within(table).getAllByRole("separator", { name: /调整列宽/ });
    expect(handles).toHaveLength(9);
    expect(within(table).queryByRole("separator", { name: /操作/ })).not.toBeInTheDocument();

    const skuHandle = within(table).getByRole("separator", { name: "调整列宽：SKU" });
    const skuHeader = skuHandle.closest("th");
    expect(skuHeader).toHaveClass("product-management__resizable-header-cell");
    expect(skuHeader).toHaveAttribute("data-width", "176");
    fireEvent.pointerDown(skuHandle, { clientX: 100, pointerId: 1 });
    fireEvent.pointerMove(skuHandle, { clientX: 148, pointerId: 1 });
    expect(skuHeader).toHaveAttribute("data-width", "176");
    expect(skuHandle.querySelector(".report-table-resize-guide")).toHaveStyle({
      visibility: "visible",
      transform: "translateX(48px)",
    });
    fireEvent.pointerUp(skuHandle, { clientX: 148, pointerId: 1 });
    expect(skuHeader).toHaveAttribute("data-width", "224");
    expect(skuHandle.querySelector(".report-table-resize-guide")).toHaveStyle({ visibility: "hidden" });
    fireEvent.click(skuHandle);
    expect(within(table).getAllByRole("button", { name: /^UI-SAMPLE-/ })[0])
      .toHaveTextContent("UI-SAMPLE-001");
  });

  it("renders formal tag management while keeping all actions as no-API placeholders", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "标签管理" }));
    const dialog = screen.getByRole("dialog", { name: "标签管理" });
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    const tagNameInput = within(dialog).getByLabelText("新增标签名");
    expect(tagNameInput).toHaveAttribute("placeholder", "请输入标签名称");
    expect(within(dialog).getAllByRole("button", { name: /选择标签颜色/ })).toHaveLength(7);
    expect(tagNameInput.closest(".product-management__new-tag-row")).not.toBeNull();
    const colorRow = within(dialog).getByText("标签颜色：").closest(
      ".product-management__tag-color-row",
    );
    expect(colorRow).not.toBeNull();
    expect(colorRow).not.toContainElement(tagNameInput);

    for (const tag of ["测品", "清货", "停售"]) {
      expect(within(dialog).getByText(tag)).toBeVisible();
    }
    for (const heading of ["标签名", "操作"]) {
      expect(within(dialog).getByRole("columnheader", { name: heading })).toBeVisible();
    }
    expect(within(dialog).queryByRole("columnheader", { name: "颜色" })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("columnheader", { name: "使用数量" })).not.toBeInTheDocument();
    expect(within(dialog).getAllByLabelText("标签颜色")).toHaveLength(3);
    fireEvent.click(within(dialog).getByRole("button", { name: "新增标签" }));
    expect(screen.getByText("请输入标签名称")).toBeVisible();
    fireEvent.change(tagNameInput, { target: { value: "临时标签" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "新增标签" }));
    expect(screen.getByText(TAG_PENDING)).toBeVisible();
    fireEvent.click(within(dialog).getAllByRole("button", { name: "编辑" })[0]);
    expect(tagNameInput).toHaveValue("测品");
    expect(within(dialog).getByRole("button", { name: "选择标签颜色：蓝色" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(within(dialog).getByRole("button", { name: "保存修改" })).toBeVisible();
    fireEvent.click(within(dialog).getByRole("button", { name: "保存修改" }));
    expect(screen.getByText(TAG_PENDING)).toBeVisible();
    fireEvent.click(within(dialog).getAllByRole("button", { name: "删除" })[0]);
    expect(within(dialog).getByText("测品")).toBeVisible();
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
  });

  it("opens a product card and switches among only the four approved detail sections", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "UI-SAMPLE-001" }));
    const dialog = screen.getByRole("dialog", { name: "产品详情" });

    expect(within(dialog).getByText("验收示例产品 001")).toBeVisible();
    const menu = within(dialog).getByRole("navigation", { name: "详情菜单" });
    expect(within(menu).getAllByRole("button").map((item) => item.textContent)).toEqual([
      "基本信息",
      "物流报关清关",
      "图片信息",
      "商品分析资料",
    ]);
    expect(within(menu).getByRole("button", { name: "基本信息" })).toHaveAttribute("aria-current", "page");
    for (const field of ["SKU", "类目", "产品等级", "WFS配送费"]) {
      expect(within(dialog).getByText(field)).toBeVisible();
    }
    for (const field of ["包装规格", "单箱重量", "单品净重"]) {
      expect(within(dialog).queryByText(field)).not.toBeInTheDocument();
    }
    expect(within(dialog).queryByText("WFS费用")).not.toBeInTheDocument();

    fireEvent.click(within(menu).getByRole("button", { name: "物流报关清关" }));
    for (const field of ["中文报关名", "英文用途", "报关单价", "海关编码", "包装规格", "单品净重"]) {
      expect(within(dialog).getByText(field)).toBeVisible();
    }
    fireEvent.click(within(menu).getByRole("button", { name: "商品分析资料" }));
    for (const field of ["竞品文案信息表", "卖家精灵关键词表", "图片分析表", "沃尔玛竞争ID"]) {
      expect(within(dialog).getByText(field)).toBeVisible();
    }
    for (const excluded of ["采购信息", "供应商报价", "关联资料", "质检信息", "操作日志", "竞品链接"]) {
      expect(within(dialog).queryByText(excluded)).not.toBeInTheDocument();
    }
  });

  it("copies SKU and product names without opening detail from the copy control", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "复制SKU：UI-SAMPLE-001" }));
    expect(await screen.findByText("已复制")).toBeVisible();
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("UI-SAMPLE-001");
    expect(screen.queryByRole("dialog", { name: "产品详情" })).not.toBeInTheDocument();

    vi.mocked(navigator.clipboard.writeText).mockRejectedValueOnce(new Error("denied"));
    fireEvent.click(screen.getByRole("button", { name: "复制产品名称：验收示例产品 001" }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("验收示例产品 001");
    expect(await screen.findByText("复制失败，请手动复制")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "UI-SAMPLE-001" }));
    expect(screen.getByRole("dialog", { name: "产品详情" })).toBeVisible();
  });

  it("shows only edit and delete in each row operation menu", () => {
    renderPage();
    fireEvent.click(screen.getAllByRole("button", { name: /操作/ })[0]);
    const menu = screen.getByRole("menu");

    expect(within(menu).getByRole("menuitem", { name: "删除" })).toHaveAttribute("data-danger", "true");
    const cases = [
      ["编辑", "产品编辑接口待接入"],
      ["删除", "产品删除接口待接入"],
    ];
    for (const [action, expected] of cases) {
      if (!screen.queryByRole("menu")) {
        fireEvent.click(screen.getAllByRole("button", { name: /操作/ })[0]);
      }
      const currentMenu = screen.getByRole("menu");
      fireEvent.click(within(currentMenu).getByRole("menuitem", { name: action }));
      expect(screen.getByText(expected)).toBeVisible();
    }
    for (const excluded of ["停用", "复制", "打印产品条码"]) {
      expect(screen.queryByRole("menuitem", { name: excluded })).not.toBeInTheDocument();
    }
    expect(fetch).not.toHaveBeenCalled();
  });
});

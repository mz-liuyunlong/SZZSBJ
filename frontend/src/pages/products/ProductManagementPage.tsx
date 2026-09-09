import {
  DownOutlined,
  PictureOutlined,
  SettingOutlined,
  SyncOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import {
  Button,
  Card,
  Descriptions,
  Dropdown,
  Empty,
  Input,
  Menu,
  Modal,
  Popover,
  Select,
  Space,
  Tag,
  Tooltip,
  Typography,
  message,
  type MenuProps,
} from "antd";
import {
  useMemo,
  useState,
  type Key,
} from "react";
import PageShell from "@/components/page/PageShell";
import ConnectedSearch from "@/components/report-table/ConnectedSearch";
import ReportTableShell, {
  ReportTableSelectionBar,
} from "@/components/report-table/ReportTableShell";
import {
  REPORT_TABLE_DEFAULT_PAGE_SIZE,
  REPORT_TABLE_PAGE_SIZE_OPTIONS,
  normalizeReportTablePageSize,
} from "@/components/report-table/pagination";
import ResetButton from "@/components/report-table/ResetButton";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import RuntimeColumnConfigDrawer, {
  type RuntimeColumnGroup,
} from "@/components/report-table/RuntimeColumnConfigDrawer";
import { CopyableTextCell, ImageCell } from "@/components/report-table/cells";
import type { NavigationPage } from "@/config/navigation";
import "@/pages/products/ProductManagementPage.css";

const SYNC_PENDING = "同步接口待接入";
const TAG_PENDING = "标签接口待接入";
const TEMPLATE_PENDING = "列模板接口待接入";
const LABEL_NAME_REQUIRED = "请输入标签名称";
const MAX_BATCH_SKUS = 1_000;
const fixedColumnKeys = ["image", "sku"];

const tagDefinitions = [
  { name: "测品", color: "#4D8DF7" },
  { name: "清货", color: "#F59E0B" },
  { name: "停售", color: "#EF5350" },
] as const;
const defaultTags = tagDefinitions.map((item) => item.name);
const tagSelectOptions = tagDefinitions.map((item) => ({
  value: item.name,
  label: (
    <span className="product-management__tag-option">
      <span
        className="product-management__tag-option-dot"
        style={{ backgroundColor: item.color }}
        aria-hidden="true"
      />
      {item.name}
    </span>
  ),
}));

const tagColorOptions = [
  { name: "绿色", value: "#34C759" },
  { name: "蓝色", value: "#4D8DF7" },
  { name: "橙色", value: "#F59E0B" },
  { name: "红色", value: "#EF5350" },
  { name: "灰色", value: "#8B95A5" },
  { name: "青色", value: "#35C4C7" },
  { name: "紫色", value: "#C65AD8" },
] as const;

const columnGroups: RuntimeColumnGroup[] = [
  {
    title: "默认主表字段",
    fields: [
      { key: "image", title: "图片" },
      { key: "sku", title: "SKU" },
      { key: "productName", title: "产品名称" },
      { key: "tags", title: "标签" },
      { key: "productGrade", title: "产品等级" },
      { key: "wfsFee", title: "WFS费用" },
      { key: "suggestedPrice", title: "建议售价" },
      { key: "minimumPrice", title: "最低售价" },
      { key: "clearancePrice", title: "清仓售价" },
    ],
  },
  {
    title: "可选基本信息字段",
    fields: [
      { key: "category", title: "类目" },
      { key: "purchasePrice", title: "产品采购价" },
      { key: "firstLegFreight", title: "头程运费" },
      { key: "wfsDeliveryFee", title: "WFS配送费" },
      { key: "purchaseLeadTime", title: "采购交期" },
      { key: "storageFee", title: "仓储费" },
    ],
  },
];

const defaultColumnKeys = columnGroups[0].fields.map((field) => field.key);
const allColumnFields = columnGroups.flatMap((group) => group.fields);

const defaultColumnWidths: Record<string, number> = {
  image: 72,
  sku: 176,
  productName: 220,
  tags: 150,
  productGrade: 112,
  wfsFee: 112,
  suggestedPrice: 112,
  minimumPrice: 112,
  clearancePrice: 112,
};

const detailGroups = {
  basic: [
    "SKU",
    "类目",
    "产品等级",
    "产品采购价",
    "头程运费",
    "WFS配送费",
    "采购交期",
    "仓储费",
  ],
  logisticsBasic: [
    "中文报关名",
    "英文报关名",
    "中文材质",
    "英文材质",
    "中文用途",
    "英文用途",
  ],
  customs: ["报关单价", "海关编码"],
  specifications: [
    "包装规格",
    "单箱重量",
    "单箱数量",
    "外箱规格",
    "单品规格",
    "单品毛重",
    "单品净重",
  ],
  images: ["产品图片"],
  analysis: ["竞品文案信息表", "卖家精灵关键词表", "图片分析表", "沃尔玛竞争ID"],
} as const;

interface ProductTableRow {
  id: string;
  sku: string;
  productName: string;
  productGrade: string;
  tags: string[];
  wfsFee: string;
  suggestedPrice: string;
  minimumPrice: string;
  clearancePrice: string;
}

const productGrades = ["A级", "B级", "C级"];
const productTagPatterns = [["测品"], ["清货"], ["停售"], ["测品", "清货"], []];

const acceptanceProducts: ProductTableRow[] = Array.from({ length: 50 }, (_, index) => {
  const number = index + 1;
  const serial = String(number).padStart(3, "0");
  return {
    id: `acceptance-product-${number}`,
    sku: `UI-SAMPLE-${serial}`,
    productName: `验收示例产品 ${serial}`,
    productGrade: productGrades[index % productGrades.length],
    tags: productTagPatterns[index % productTagPatterns.length],
    wfsFee: "待接入",
    suggestedPrice: "待接入",
    minimumPrice: "待接入",
    clearancePrice: "待接入",
  };
});

const operationItems: MenuProps["items"] = [
  { key: "edit", label: "编辑" },
  { key: "delete", label: "删除", danger: true },
];

const operationMessages: Record<string, string> = {
  edit: "产品编辑接口待接入",
  delete: "产品删除接口待接入",
};

const compareText = (left: string, right: string) => left.localeCompare(right, "zh-CN");

const renderTags = (tags: string[]) => {
  if (tags.length === 0) return "-";
  const visibleTags = tags.slice(0, 2);
  return (
    <Space size={4} className="product-management__tags">
      {visibleTags.map((tag) => {
        const definition = tagDefinitions.find((item) => item.name === tag);
        return <Tag key={tag} color={definition?.color}>{tag}</Tag>;
      })}
      {tags.length > visibleTags.length && <Tag>+{tags.length - visibleTags.length}</Tag>}
    </Space>
  );
};

function createDefaultColumns(
  openDetail: (product: ProductTableRow) => void,
  showOperationPending: (key: string) => void,
  copyText: (text: string) => void,
): ProColumns<ProductTableRow>[] {
  return [
    {
      title: "图片",
      key: "image",
      width: 72,
      render: () => <ImageCell label="图片占位" />,
    },
    {
      title: "SKU",
      dataIndex: "sku",
      key: "sku",
      width: 176,
      sorter: (left, right) => compareText(left.sku, right.sku),
      render: (_, record) => (
        <CopyableTextCell
          text={record.sku}
          label="SKU"
          link
          onCopy={copyText}
          onOpen={() => openDetail(record)}
        />
      ),
    },
    {
      title: "产品名称",
      dataIndex: "productName",
      key: "productName",
      width: 220,
      render: (_, record) => (
        <CopyableTextCell text={record.productName} label="产品名称" onCopy={copyText} />
      ),
    },
    {
      title: "标签",
      dataIndex: "tags",
      key: "tags",
      width: 150,
      render: (_, record) => renderTags(record.tags),
    },
    {
      title: "产品等级",
      dataIndex: "productGrade",
      key: "productGrade",
      width: 112,
      sorter: (left, right) => compareText(left.productGrade, right.productGrade),
    },
    {
      title: "WFS费用",
      dataIndex: "wfsFee",
      key: "wfsFee",
      width: 112,
      sorter: (left, right) => compareText(left.wfsFee, right.wfsFee),
    },
    {
      title: "建议售价",
      dataIndex: "suggestedPrice",
      key: "suggestedPrice",
      width: 112,
      sorter: (left, right) => compareText(left.suggestedPrice, right.suggestedPrice),
    },
    {
      title: "最低售价",
      dataIndex: "minimumPrice",
      key: "minimumPrice",
      width: 112,
      sorter: (left, right) => compareText(left.minimumPrice, right.minimumPrice),
    },
    {
      title: "清仓售价",
      dataIndex: "clearancePrice",
      key: "clearancePrice",
      width: 112,
      sorter: (left, right) => compareText(left.clearancePrice, right.clearancePrice),
    },
    {
      title: "操作",
      key: "actions",
      width: 150,
      fixed: "right",
      render: (_, record) => (
        <Space size={4}>
          <Button type="link" onClick={() => openDetail(record)}>详情</Button>
          <Dropdown
            trigger={["click"]}
            menu={{ items: operationItems, onClick: ({ key }) => showOperationPending(key) }}
          >
            <Button type="link">操作 <DownOutlined aria-hidden="true" /></Button>
          </Dropdown>
        </Space>
      ),
    },
  ];
}

const normalizeBatchSkuInput = (value: string) =>
  value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

const pendingDescriptionItems = (fields: readonly string[], product?: ProductTableRow) =>
  fields.map((field) => ({
    key: field,
    label: field,
    children: field === "SKU"
      ? product?.sku
      : field === "产品等级"
        ? product?.productGrade
        : <Typography.Text type="secondary">待接入</Typography.Text>,
  }));

type DetailSection = "basic" | "logistics" | "images" | "analysis";

const detailMenuItems = [
  { key: "basic", label: "基本信息" },
  { key: "logistics", label: "物流报关清关" },
  { key: "images", label: "图片信息" },
  { key: "analysis", label: "商品分析资料" },
];

interface ProductDetailModalProps {
  open: boolean;
  product: ProductTableRow;
  section: DetailSection;
  onClose: () => void;
  onSectionChange: (section: DetailSection) => void;
}

function ProductDetailModal({
  open,
  product,
  section,
  onClose,
  onSectionChange,
}: ProductDetailModalProps) {
  let content;

  if (section === "logistics") {
    content = (
      <section aria-labelledby="detail-logistics">
        <Typography.Title id="detail-logistics" level={4}>物流报关清关</Typography.Title>
        <Typography.Title level={5}>基本信息</Typography.Title>
        <Descriptions
          size="small"
          column={{ xs: 1, sm: 2, md: 3 }}
          items={pendingDescriptionItems(detailGroups.logisticsBasic)}
        />
        <Typography.Title level={5}>报关信息</Typography.Title>
        <Descriptions
          size="small"
          column={{ xs: 1, sm: 2 }}
          items={pendingDescriptionItems(detailGroups.customs)}
        />
        <Typography.Title level={5}>规格信息</Typography.Title>
        <div className="product-management__detail-spec-scroll">
          <table className="product-management__detail-spec-table">
            <thead>
              <tr>
                {detailGroups.specifications.map((field) => <th key={field}>{field}</th>)}
              </tr>
            </thead>
            <tbody>
              <tr>
                {detailGroups.specifications.map((field) => <td key={field}>待接入</td>)}
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    );
  } else if (section === "images") {
    content = (
      <section aria-labelledby="detail-images">
        <Typography.Title id="detail-images" level={4}>图片信息</Typography.Title>
        <Descriptions column={1} items={pendingDescriptionItems(detailGroups.images)} />
      </section>
    );
  } else if (section === "analysis") {
    content = (
      <section aria-labelledby="detail-analysis">
        <Typography.Title id="detail-analysis" level={4}>商品分析资料</Typography.Title>
        <Descriptions
          size="small"
          column={{ xs: 1, sm: 2 }}
          items={pendingDescriptionItems(detailGroups.analysis)}
        />
      </section>
    );
  } else {
    content = (
      <section aria-labelledby="detail-basic">
        <Typography.Title id="detail-basic" level={4}>基本信息</Typography.Title>
        <Descriptions
          size="small"
          column={{ xs: 1, sm: 2, md: 3 }}
          items={pendingDescriptionItems(detailGroups.basic, product)}
        />
      </section>
    );
  }

  return (
    <Modal
      className="product-management__detail-modal"
      title="产品详情"
      open={open}
      centered
      destroyOnHidden
      width="min(1100px, calc(100vw - 32px))"
      footer={<Button type="primary" aria-label="关闭产品详情" onClick={onClose}>关闭</Button>}
      onCancel={onClose}
    >
      <div className="product-management__detail-layout">
        <aside className="product-management__detail-sidebar" aria-label="产品详情分区">
          <Card size="small" className="product-management__product-card">
            <div className="product-management__detail-image" aria-label="产品图片占位">
              <PictureOutlined aria-hidden="true" />
            </div>
            <Typography.Text strong>{product.productName}</Typography.Text>
            <Typography.Text type="secondary">{product.sku}</Typography.Text>
          </Card>
          <Menu
            mode="inline"
            selectedKeys={[section]}
            items={detailMenuItems}
            onClick={({ key }) => onSectionChange(key as DetailSection)}
          />
        </aside>
        <div className="product-management__detail-content">{content}</div>
      </div>
    </Modal>
  );
}

interface ProductManagementPageProps {
  page: NavigationPage;
}

function ProductManagementPage({ page }: ProductManagementPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [productGrade, setProductGrade] = useState<string>();
  const [tag, setTag] = useState<string>();
  const [searchType, setSearchType] = useState("sku");
  const [keyword, setKeyword] = useState("");
  const [activeKeyword, setActiveKeyword] = useState("");
  const [batchSearchOpen, setBatchSearchOpen] = useState(false);
  const [batchSkuInput, setBatchSkuInput] = useState("");
  const [batchSearchSkus, setBatchSearchSkus] = useState<string[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [markTagsOpen, setMarkTagsOpen] = useState(false);
  const [draftMarkTags, setDraftMarkTags] = useState<string[]>([]);
  const [columnConfigOpen, setColumnConfigOpen] = useState(false);
  const [appliedColumnKeys, setAppliedColumnKeys] = useState(defaultColumnKeys);
  const [columnWidths, setColumnWidths] = useState(defaultColumnWidths);
  const [tagManagementOpen, setTagManagementOpen] = useState(false);
  const [newTagName, setNewTagName] = useState("");
  const [newTagColor, setNewTagColor] = useState<string>(tagColorOptions[0].value);
  const [editingTag, setEditingTag] = useState<string>();
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailSection, setDetailSection] = useState<DetailSection>("basic");
  const [selectedProduct, setSelectedProduct] = useState(acceptanceProducts[0]);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(REPORT_TABLE_DEFAULT_PAGE_SIZE);
  const [tableResetKey, setTableResetKey] = useState(0);

  const copyText = async (text: string) => {
    try {
      if (!navigator.clipboard) throw new Error("Clipboard API unavailable");
      await navigator.clipboard.writeText(text);
      void messageApi.success("已复制");
    } catch {
      void messageApi.error("复制失败，请手动复制");
    }
  };

  const openDetail = (product: ProductTableRow) => {
    setSelectedProduct(product);
    setDetailSection("basic");
    setDetailOpen(true);
  };

  const closeBatchSearch = () => {
    setBatchSearchOpen(false);
    setBatchSkuInput("");
  };

  const resetPageAndSelection = () => {
    setCurrentPage(1);
    setSelectedRowKeys([]);
  };

  const searchSku = () => {
    setActiveKeyword(keyword.trim());
    setBatchSearchSkus([]);
    setBatchSkuInput("");
    resetPageAndSelection();
  };

  const searchBatchSku = () => {
    const normalized = normalizeBatchSkuInput(batchSkuInput);
    if (normalized.length > MAX_BATCH_SKUS) {
      void messageApi.info("最多支持1000行");
      return;
    }
    setBatchSkuInput(normalized.join("\n"));
    setBatchSearchSkus(normalized);
    setActiveKeyword("");
    setKeyword("");
    resetPageAndSelection();
  };

  const clearBatchSearch = () => {
    setBatchSkuInput("");
    setBatchSearchSkus([]);
    resetPageAndSelection();
  };

  const openMarkTags = () => {
    setDraftMarkTags([]);
    setMarkTagsOpen(true);
  };

  const openTagManagement = () => {
    setNewTagName("");
    setNewTagColor(tagColorOptions[0].value);
    setEditingTag(undefined);
    setTagManagementOpen(true);
  };

  const saveManagedTag = () => {
    if (!newTagName.trim()) {
      void messageApi.info(LABEL_NAME_REQUIRED);
      return;
    }
    void messageApi.info(TAG_PENDING);
  };

  const editManagedTag = (name: string, color: string) => {
    setNewTagName(name);
    setNewTagColor(color);
    setEditingTag(name);
  };

  const openColumnConfig = () => {
    setColumnConfigOpen(true);
  };

  const defaultColumns = createDefaultColumns(
    openDetail,
    (key) => void messageApi.info(operationMessages[key]),
    (text) => void copyText(text),
  );
  const resizableDefaultColumns = defaultColumns.map((column) => {
    const key = String(column.key);
    const width = columnWidths[key];
    if (!width || !defaultColumnWidths[key]) return column;
    const fieldTitle = allColumnFields.find((field) => field.key === key)?.title ?? key;
    return {
      ...column,
      width,
      onHeaderCell: () => ({
        className: "report-table-resizable-header-cell product-management__resizable-header-cell",
      }),
      title: (
        <ResizableColumnTitle
          label={fieldTitle}
          minWidth={key === "image" ? 64 : 96}
          width={width}
          onWidthChange={(nextWidth) => setColumnWidths((current) => ({
            ...current,
            [key]: nextWidth,
          }))}
        />
      ),
    };
  });
  const optionalColumns: ProColumns<ProductTableRow>[] = allColumnFields
    .filter((field) => !defaultColumnKeys.includes(field.key))
    .map((field) => ({
      title: field.title,
      key: field.key,
      width: 128,
      render: () => <Typography.Text type="secondary">待接入</Typography.Text>,
    }));
  const actionColumn = resizableDefaultColumns.find((column) => column.key === "actions");
  const columnMap = new Map(
    [...resizableDefaultColumns, ...optionalColumns]
      .filter((column) => column.key !== "actions")
      .map((column) => [String(column.key), column]),
  );
  const columns = [
    ...appliedColumnKeys.flatMap((key) => {
      const column = columnMap.get(key);
      return column ? [column] : [];
    }),
    ...(actionColumn ? [actionColumn] : []),
  ];
  const batchSkuSet = useMemo(() => new Set(batchSearchSkus), [batchSearchSkus]);
  const filteredProducts = useMemo(() => {
    const normalizedKeyword = activeKeyword.toLocaleLowerCase();
    return acceptanceProducts.filter((product) => (
      (!productGrade || product.productGrade === productGrade)
      && (!tag || product.tags.includes(tag))
      && (!normalizedKeyword || product.sku.toLocaleLowerCase().includes(normalizedKeyword))
      && (batchSkuSet.size === 0 || batchSkuSet.has(product.sku))
    ));
  }, [activeKeyword, batchSkuSet, productGrade, tag]);

  const resetFilters = () => {
    setProductGrade(undefined);
    setTag(undefined);
    setSearchType("sku");
    setKeyword("");
    setActiveKeyword("");
    setBatchSkuInput("");
    setBatchSearchSkus([]);
    setBatchSearchOpen(false);
    setCurrentPage(1);
    setSelectedRowKeys([]);
    setTableResetKey((current) => current + 1);
  };

  const batchSearchContent = (
    <div className="product-management__batch-popover" role="dialog" aria-label="批量搜索 SKU">
      <Typography.Paragraph>精确搜索，一行一项，最多支持1000行</Typography.Paragraph>
      <Input.TextArea
        aria-label="批量 SKU 输入"
        placeholder="请输入 SKU，一行一个"
        rows={8}
        value={batchSkuInput}
        onChange={(event) => setBatchSkuInput(event.target.value)}
      />
      <div className="product-management__batch-actions">
        <Button onClick={clearBatchSearch}>清空</Button>
        <Button onClick={closeBatchSearch}>关闭</Button>
        <Button type="primary" onClick={searchBatchSku}>搜索</Button>
      </div>
    </div>
  );

  return (
    <PageShell
      page={page}
      headerActions={(
        <div className="product-management__sync-state">
          <Typography.Text type="secondary">最后同步时间：待接入</Typography.Text>
          <Tooltip title={SYNC_PENDING}>
            <Button
              className="product-management__sync-button"
              shape="circle"
              size="small"
              aria-label="同步数据"
              icon={<SyncOutlined aria-hidden="true" />}
              onClick={() => void messageApi.info(SYNC_PENDING)}
            />
          </Tooltip>
        </div>
      )}
    >
      {messageContextHolder}
      <div className="product-management">
        <Card size="small" className="product-management__toolbar-card">
          <div className="product-management__toolbar" role="search" aria-label="产品筛选与页面工具">
            <Select
              allowClear
              className="report-filter-select"
              classNames={{ popup: { root: "report-filter-select-dropdown" } }}
              aria-label="产品等级"
              placeholder="产品等级"
              value={productGrade}
              options={["A级", "B级", "C级"].map((value) => ({ label: value, value }))}
              onChange={(value) => {
                setProductGrade(value);
                resetPageAndSelection();
              }}
            />
            <Select
              allowClear
              className="report-filter-select"
              classNames={{ popup: { root: "report-filter-select-dropdown" } }}
              aria-label="标签"
              placeholder="标签"
              value={tag}
              options={defaultTags.map((value) => ({ label: value, value }))}
              onChange={(value) => {
                setTag(value);
                resetPageAndSelection();
              }}
            />
            <ConnectedSearch
              className="product-management__search-box"
              typeAriaLabel="搜索类型"
              typeOptions={[{ label: "SKU", value: "sku" }]}
              typeValue={searchType}
              inputAriaLabel="搜索内容"
              inputPlaceholder="请输入搜索内容"
              inputValue={keyword}
              searchAriaLabel="搜索产品"
              onTypeChange={setSearchType}
              onInputChange={setKeyword}
              onSearch={searchSku}
              batchControl={(
                <Popover
                  content={batchSearchContent}
                  trigger="click"
                  placement="bottomRight"
                  open={batchSearchOpen}
                  onOpenChange={(open) => open ? setBatchSearchOpen(true) : closeBatchSearch()}
                >
                  <Tooltip title="批量搜索 SKU">
                    <Button
                      className="report-table-connected-search__batch product-management__batch-trigger"
                      aria-label="批量搜索 SKU"
                      aria-expanded={batchSearchOpen}
                      icon={<UnorderedListOutlined aria-hidden="true" />}
                    />
                  </Tooltip>
                </Popover>
              )}
            />
            <ResetButton onClick={resetFilters} />
            <Button onClick={openTagManagement}>标签管理</Button>
            <span className="product-management__toolbar-spacer" aria-hidden="true" />
            <div className="product-management__toolbar-actions">
              <Button icon={<SettingOutlined aria-hidden="true" />} onClick={openColumnConfig}>列配置</Button>
            </div>
          </div>
        </Card>

        <ReportTableShell className="product-management__table" label="产品管理主表">
          <ProTable<ProductTableRow>
            key={tableResetKey}
            columns={columns}
            dataSource={filteredProducts}
            rowKey="id"
            rowSelection={{
              fixed: true,
              selectedRowKeys,
              onChange: setSelectedRowKeys,
            }}
            search={false}
            options={false}
            toolBarRender={false}
            tableAlertRender={false}
            tableAlertOptionRender={false}
            showSorterTooltip={{ target: "sorter-icon" }}
            scroll={{ x: "max-content", y: "max(240px, calc(100dvh - 390px))" }}
            footer={() => (
              <ReportTableSelectionBar
                selectedCount={selectedRowKeys.length}
                actions={[{ key: "mark", label: "批量标记", onClick: openMarkTags }]}
              />
            )}
            pagination={{
              current: currentPage,
              pageSize,
              total: filteredProducts.length,
              showSizeChanger: true,
              showQuickJumper: true,
              pageSizeOptions: REPORT_TABLE_PAGE_SIZE_OPTIONS,
              showTotal: (total) => `共 ${total} 条`,
              onChange: (nextPage, nextPageSize) => {
                const pageSizeChanged = nextPageSize !== pageSize;
                setCurrentPage(pageSizeChanged ? 1 : nextPage);
                setPageSize(normalizeReportTablePageSize(nextPageSize));
                if (pageSizeChanged) setSelectedRowKeys([]);
              },
            }}
            locale={{
              emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配产品" />,
            }}
          />
        </ReportTableShell>
      </div>

      <RuntimeColumnConfigDrawer
        open={columnConfigOpen}
        groups={columnGroups}
        fixedKeys={fixedColumnKeys}
        defaultKeys={defaultColumnKeys}
        appliedKeys={appliedColumnKeys}
        onApply={setAppliedColumnKeys}
        onClose={() => setColumnConfigOpen(false)}
        onSaveTemplate={() => void messageApi.info(TEMPLATE_PENDING)}
      />

      <Modal
        className="product-management__mark-modal"
        title="标记标签"
        open={markTagsOpen}
        centered
        width={560}
        destroyOnHidden
        footer={
          <div className="product-management__mark-footer">
            <Space>
              <Button onClick={() => setMarkTagsOpen(false)}>取消</Button>
              <Button type="primary" onClick={() => void messageApi.info(TAG_PENDING)}>保存</Button>
            </Space>
          </div>
        }
        onCancel={() => setMarkTagsOpen(false)}
      >
        <label className="product-management__mark-label">
          <span>标签：</span>
          <Select
            mode="multiple"
            showSearch
            className="report-filter-select"
            classNames={{ popup: { root: "report-filter-select-dropdown report-filter-select-dropdown--multiple" } }}
            aria-label="标记标签选择"
            value={draftMarkTags}
            options={tagSelectOptions}
            onChange={setDraftMarkTags}
          />
        </label>
      </Modal>

      <Modal
        className="product-management__tag-management-modal"
        title="标签管理"
        open={tagManagementOpen}
        centered
        width={720}
        footer={<Button aria-label="关闭标签管理" onClick={() => setTagManagementOpen(false)}>关闭</Button>}
        onCancel={() => setTagManagementOpen(false)}
      >
        <div className="product-management__new-tag">
          <div className="product-management__new-tag-row">
            <Input
              aria-label="新增标签名"
              placeholder="请输入标签名称"
              value={newTagName}
              onChange={(event) => setNewTagName(event.target.value)}
            />
            <Button type="primary" onClick={saveManagedTag}>
              {editingTag ? "保存修改" : "新增标签"}
            </Button>
          </div>
          <div className="product-management__tag-color-row">
            <Typography.Text>标签颜色：</Typography.Text>
            <div className="product-management__tag-colors" aria-label="标签颜色选择">
              {tagColorOptions.map((option) => (
                <Button
                  key={option.value}
                  className="product-management__tag-color-option"
                  shape="circle"
                  aria-label={`选择标签颜色：${option.name}`}
                  aria-pressed={newTagColor === option.value}
                  style={{ backgroundColor: option.value }}
                  onClick={() => setNewTagColor(option.value)}
                />
              ))}
            </div>
          </div>
        </div>
        <div className="product-management__tag-table-scroll">
          <table className="product-management__tag-table">
            <thead>
              <tr>
                <th>标签名</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {tagDefinitions.map((item) => (
                <tr key={item.name}>
                  <td>
                    <span
                      className="product-management__tag-color"
                      style={{ backgroundColor: item.color }}
                      role="img"
                      aria-label="标签颜色"
                    />
                    {item.name}
                  </td>
                  <td>
                    <Space size={4}>
                      <Button type="link" onClick={() => editManagedTag(item.name, item.color)}>编辑</Button>
                      <Button danger type="link" onClick={() => void messageApi.info(TAG_PENDING)}>删除</Button>
                    </Space>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Modal>

      <ProductDetailModal
        open={detailOpen}
        product={selectedProduct}
        section={detailSection}
        onClose={() => setDetailOpen(false)}
        onSectionChange={setDetailSection}
      />
    </PageShell>
  );
}

export default ProductManagementPage;

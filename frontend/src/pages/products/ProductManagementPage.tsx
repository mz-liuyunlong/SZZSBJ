import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  CopyOutlined,
  DownOutlined,
  PictureOutlined,
  SearchOutlined,
  SettingOutlined,
  SyncOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import {
  Button,
  Card,
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
  Space,
  Tag,
  Tooltip,
  Typography,
  message,
  type MenuProps,
} from "antd";
import {
  useMemo,
  useRef,
  useState,
  type DragEvent,
  type Key,
  type KeyboardEvent,
  type MouseEvent,
  type PointerEvent,
} from "react";
import PageShell from "../../components/page/PageShell";
import type { NavigationPage } from "../../config/navigation";
import "./ProductManagementPage.css";

const SYNC_PENDING = "同步接口待接入";
const TAG_PENDING = "标签接口待接入";
const TEMPLATE_PENDING = "列模板接口待接入";
const PLEASE_SELECT_PRODUCT = "请先选择产品";
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

interface ColumnField {
  key: string;
  title: string;
}

const columnGroups: { fields: ColumnField[]; title: string }[] = [
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
const allColumnKeys = allColumnFields.map((field) => field.key);
const isFixedColumn = (key: string) => fixedColumnKeys.includes(key);
const keepFixedColumns = (keys: string[]) => [
  ...fixedColumnKeys,
  ...keys.filter((key) => !isFixedColumn(key)),
];

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

const moreItems: MenuProps["items"] = [{ key: "mark", label: "标记" }];

const compareText = (left: string, right: string) => left.localeCompare(right, "zh-CN");

interface CopyableTextProps {
  text: string;
  label: string;
  link?: boolean;
  onCopy: (text: string) => void;
  onOpen?: () => void;
}

function CopyableText({ text, label, link, onCopy, onOpen }: CopyableTextProps) {
  const handleCopy = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    onCopy(text);
  };

  return (
    <span className="product-management__copyable">
      {link ? (
        <Button className="product-management__sku-link" type="link" onClick={onOpen}>{text}</Button>
      ) : (
        <span className="product-management__copy-text">{text}</span>
      )}
      <Button
        className="product-management__copy-button"
        type="text"
        size="small"
        aria-label={`复制${label}：${text}`}
        icon={<CopyOutlined aria-hidden="true" />}
        onClick={handleCopy}
      />
    </span>
  );
}

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
      render: () => (
        <span className="product-management__image-placeholder" aria-label="图片占位">
          <PictureOutlined aria-hidden="true" />
        </span>
      ),
    },
    {
      title: "SKU",
      dataIndex: "sku",
      key: "sku",
      width: 176,
      sorter: (left, right) => compareText(left.sku, right.sku),
      render: (_, record) => (
        <CopyableText
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
        <CopyableText text={record.productName} label="产品名称" onCopy={copyText} />
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
  const [columnSearch, setColumnSearch] = useState("");
  const [appliedColumnKeys, setAppliedColumnKeys] = useState(defaultColumnKeys);
  const [draftColumnKeys, setDraftColumnKeys] = useState(defaultColumnKeys);
  const [draggedColumnKey, setDraggedColumnKey] = useState<string>();
  const [columnWidths, setColumnWidths] = useState(defaultColumnWidths);
  const [resizingColumnKey, setResizingColumnKey] = useState<string>();
  const resizeSession = useRef<{ key: string; startWidth: number; startX: number } | undefined>(undefined);
  const [tagManagementOpen, setTagManagementOpen] = useState(false);
  const [newTagName, setNewTagName] = useState("");
  const [newTagColor, setNewTagColor] = useState<string>(tagColorOptions[0].value);
  const [editingTag, setEditingTag] = useState<string>();
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailSection, setDetailSection] = useState<DetailSection>("basic");
  const [selectedProduct, setSelectedProduct] = useState(acceptanceProducts[0]);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
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

  const handleMoreAction = () => {
    if (selectedRowKeys.length === 0) {
      void messageApi.info(PLEASE_SELECT_PRODUCT);
      return;
    }
    openMarkTags();
  };

  const openColumnConfig = () => {
    setDraftColumnKeys(appliedColumnKeys);
    setColumnSearch("");
    setColumnConfigOpen(true);
  };

  const closeColumnConfig = () => {
    setDraftColumnKeys(appliedColumnKeys);
    setColumnConfigOpen(false);
  };

  const toggleColumn = (key: string, checked: boolean) => {
    if (isFixedColumn(key)) return;
    setDraftColumnKeys((current) => keepFixedColumns(checked
      ? [...current, key]
      : current.filter((item) => item !== key)));
  };

  const moveColumn = (key: string, offset: -1 | 1) => {
    if (isFixedColumn(key)) return;
    setDraftColumnKeys((current) => {
      const from = current.indexOf(key);
      const to = from + offset;
      if (from < 0 || to < fixedColumnKeys.length || to >= current.length) return current;
      const next = [...current];
      [next[from], next[to]] = [next[to], next[from]];
      return next;
    });
  };

  const dropColumn = (targetKey: string, event: DragEvent<HTMLLIElement>) => {
    event.preventDefault();
    if (!draggedColumnKey || draggedColumnKey === targetKey || isFixedColumn(targetKey)) return;
    setDraftColumnKeys((current) => {
      const next = current.filter((key) => key !== draggedColumnKey);
      const targetIndex = next.indexOf(targetKey);
      next.splice(targetIndex, 0, draggedColumnKey);
      return next;
    });
    setDraggedColumnKey(undefined);
  };

  const startColumnResize = (key: string, event: PointerEvent<HTMLSpanElement>) => {
    event.preventDefault();
    event.stopPropagation();
    resizeSession.current = {
      key,
      startWidth: columnWidths[key],
      startX: event.clientX,
    };
    setResizingColumnKey(key);
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };

  const resizeColumn = (key: string, event: PointerEvent<HTMLSpanElement>) => {
    const session = resizeSession.current;
    if (!session || session.key !== key) return;
    event.stopPropagation();
    setColumnWidths((current) => ({
      ...current,
      [key]: Math.max(key === "image" ? 64 : 96, session.startWidth + event.clientX - session.startX),
    }));
  };

  const finishColumnResize = (event: PointerEvent<HTMLSpanElement>) => {
    event.stopPropagation();
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    resizeSession.current = undefined;
    setResizingColumnKey(undefined);
  };

  const resizeColumnWithKeyboard = (key: string, event: KeyboardEvent<HTMLSpanElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    event.stopPropagation();
    const offset = event.key === "ArrowLeft" ? -8 : 8;
    setColumnWidths((current) => ({
      ...current,
      [key]: Math.max(key === "image" ? 64 : 96, current[key] + offset),
    }));
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
      onHeaderCell: () => ({ className: "product-management__resizable-header-cell" }),
      title: (
        <span className="product-management__resizable-title">
          <span>{fieldTitle}</span>
          <span
            className="product-management__resize-handle"
            role="separator"
            tabIndex={0}
            aria-label={`调整列宽：${fieldTitle}`}
            aria-orientation="vertical"
            aria-valuemin={key === "image" ? 64 : 96}
            aria-valuenow={width}
            data-resizing={resizingColumnKey === key || undefined}
            onPointerDown={(event) => startColumnResize(key, event)}
            onPointerMove={(event) => resizeColumn(key, event)}
            onPointerUp={finishColumnResize}
            onPointerCancel={finishColumnResize}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
            }}
            onKeyDown={(event) => resizeColumnWithKeyboard(key, event)}
          />
        </span>
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
  const selectedColumnFields = draftColumnKeys.flatMap((key) => {
    const field = allColumnFields.find((item) => item.key === key);
    return field ? [field] : [];
  });
  const visibleColumnGroups = columnGroups
    .map((group) => ({
      ...group,
      fields: group.fields.filter((field) => field.title.includes(columnSearch.trim())),
    }))
    .filter((group) => group.fields.length > 0);
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
              aria-label="标签"
              placeholder="标签"
              value={tag}
              options={defaultTags.map((value) => ({ label: value, value }))}
              onChange={(value) => {
                setTag(value);
                resetPageAndSelection();
              }}
            />
            <div className="product-management__search-box">
              <Select
                aria-label="搜索类型"
                value={searchType}
                options={[{ label: "SKU", value: "sku" }]}
                onChange={setSearchType}
              />
              <Input
                allowClear
                aria-label="搜索内容"
                placeholder="请输入搜索内容"
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                onPressEnter={searchSku}
              />
              <Tooltip title="搜索">
                <Button
                  aria-label="搜索产品"
                  icon={<SearchOutlined aria-hidden="true" />}
                  onClick={searchSku}
                />
              </Tooltip>
              <Popover
                content={batchSearchContent}
                trigger="click"
                placement="bottomRight"
                open={batchSearchOpen}
                onOpenChange={(open) => open ? setBatchSearchOpen(true) : closeBatchSearch()}
              >
                <Tooltip title="批量搜索 SKU">
                  <Button
                    className="product-management__batch-trigger"
                    aria-label="批量搜索 SKU"
                    aria-expanded={batchSearchOpen}
                    icon={<UnorderedListOutlined aria-hidden="true" />}
                  />
                </Tooltip>
              </Popover>
            </div>
            <Button icon={<SettingOutlined aria-hidden="true" />} onClick={openColumnConfig}>列配置</Button>
            <Button onClick={openTagManagement}>标签管理</Button>
            <Dropdown trigger={["click"]} menu={{ items: moreItems, onClick: handleMoreAction }}>
              <Button>更多 <DownOutlined aria-hidden="true" /></Button>
            </Dropdown>
            <Button onClick={resetFilters}>重置</Button>
          </div>
        </Card>

        <section className="product-management__table" aria-label="产品管理主表">
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
            footer={() => selectedRowKeys.length > 0 ? (
              <Typography.Text strong>已选择 {selectedRowKeys.length} 项</Typography.Text>
            ) : null}
            pagination={{
              current: currentPage,
              pageSize,
              total: filteredProducts.length,
              showSizeChanger: true,
              showQuickJumper: true,
              pageSizeOptions: ["10", "20", "50", "100"],
              showTotal: (total) => `共 ${total} 条`,
              onChange: (nextPage, nextPageSize) => {
                const pageSizeChanged = nextPageSize !== pageSize;
                setCurrentPage(pageSizeChanged ? 1 : nextPage);
                setPageSize(nextPageSize);
                if (pageSizeChanged) setSelectedRowKeys([]);
              },
            }}
            locale={{
              emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配产品" />,
            }}
          />
        </section>
      </div>

      <Drawer
        rootClassName="product-management__column-drawer"
        title="列配置"
        placement="right"
        size="large"
        open={columnConfigOpen}
        destroyOnHidden
        footer={
          <div className="product-management__drawer-footer">
            <Button onClick={() => setDraftColumnKeys(defaultColumnKeys)}>恢复默认</Button>
            <Space>
              <Button onClick={closeColumnConfig}>取消</Button>
              <Button
                type="primary"
                onClick={() => {
                  setAppliedColumnKeys(keepFixedColumns(draftColumnKeys));
                  setColumnConfigOpen(false);
                }}
              >
                保存并应用
              </Button>
            </Space>
          </div>
        }
        onClose={closeColumnConfig}
      >
        <div className="product-management__drawer-tools">
          <Select aria-label="选择模板" disabled placeholder="选择模板" options={[]} />
          <Button onClick={() => void messageApi.info(TEMPLATE_PENDING)}>保存为新模板</Button>
        </div>
        <div className="product-management__column-editor">
          <section className="product-management__available-columns" aria-label="可选字段">
            <Input
              allowClear
              aria-label="搜索字段"
              placeholder="搜索字段"
              value={columnSearch}
              onChange={(event) => setColumnSearch(event.target.value)}
            />
            <Space size={4}>
              <Button size="small" onClick={() => setDraftColumnKeys(allColumnKeys)}>全选</Button>
              <Button size="small" onClick={() => setDraftColumnKeys(fixedColumnKeys)}>取消全选</Button>
            </Space>
            {visibleColumnGroups.map((group) => (
              <div key={group.title} className="product-management__column-group">
                <Typography.Text strong>{group.title}</Typography.Text>
                <div className="product-management__column-checks">
                  {group.fields.map((field) => (
                    <Checkbox
                      key={field.key}
                      aria-label={`显示列：${field.title}`}
                      checked={draftColumnKeys.includes(field.key)}
                      disabled={isFixedColumn(field.key)}
                      onChange={(event) => toggleColumn(field.key, event.target.checked)}
                    >
                      {field.title}
                    </Checkbox>
                  ))}
                </div>
              </div>
            ))}
          </section>
          <section aria-labelledby="selected-columns-title">
            <Typography.Title id="selected-columns-title" level={5}>已选字段</Typography.Title>
            <ol className="product-management__selected-columns">
              {selectedColumnFields.map((field, index) => (
                <li
                  key={field.key}
                  draggable={!isFixedColumn(field.key)}
                  aria-label={isFixedColumn(field.key) ? `固定字段：${field.title}` : `拖动字段：${field.title}`}
                  onDragStart={() => setDraggedColumnKey(field.key)}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={(event) => dropColumn(field.key, event)}
                  onDragEnd={() => setDraggedColumnKey(undefined)}
                >
                  <span>{field.title}</span>
                  {isFixedColumn(field.key) ? (
                    <Tag>固定</Tag>
                  ) : (
                    <Space size={0}>
                      <Button
                        type="text"
                        size="small"
                        disabled={index === fixedColumnKeys.length}
                        aria-label={`上移字段：${field.title}`}
                        icon={<ArrowUpOutlined aria-hidden="true" />}
                        onClick={() => moveColumn(field.key, -1)}
                      />
                      <Button
                        type="text"
                        size="small"
                        disabled={index === selectedColumnFields.length - 1}
                        aria-label={`下移字段：${field.title}`}
                        icon={<ArrowDownOutlined aria-hidden="true" />}
                        onClick={() => moveColumn(field.key, 1)}
                      />
                    </Space>
                  )}
                </li>
              ))}
            </ol>
          </section>
        </div>
      </Drawer>

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
            aria-label="标记标签选择"
            value={draftMarkTags}
            options={tagSelectOptions}
            onChange={setDraftMarkTags}
          />
        </label>
      </Modal>

      <Modal
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

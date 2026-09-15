import { Button, Modal, Progress, Tag, Typography } from "antd";
import { useState, type CSSProperties, type ReactNode } from "react";
import type { ProductManagementRow } from "@/pages/products/productManagementTypes";

const isDisplayableImageUrl = (value: string | null | undefined): value is string => (
  typeof value === "string"
  && /^(https?:\/\/|data:image\/|blob:|\/)/i.test(value)
);

const getDetailImageUrl = (row: ProductManagementRow) => {
  const record = row as ProductManagementRow & {
    imageUrl?: string | null;
    mainImageUrl?: string | null;
    images?: string[] | null;
  };

  const candidate = (
    row.previewImage ??
    record.imageUrl ??
    record.image ??
    record.mainImageUrl ??
    record.images?.[0] ??
    null
  );

  return isDisplayableImageUrl(candidate) ? candidate : null;
};

const renderDetailProductImage = (row: ProductManagementRow) => {
  const imageUrl = getDetailImageUrl(row);

  return (
    <div className="product-detail-modal__cover-media">
      {imageUrl ? (
        <img
          className="product-detail-modal__cover-img"
          src={imageUrl}
          alt={row.productName ?? row.sku ?? "产品图片"}
          referrerPolicy="no-referrer"
          loading="lazy"
          onError={(event) => {
            event.currentTarget.style.display = "none";
            const emptyNode = event.currentTarget.nextElementSibling;
            if (emptyNode instanceof HTMLElement) {
              emptyNode.style.display = "flex";
            }
          }}
        />
      ) : null}
      <span
        className="product-detail-modal__image-empty"
        style={imageUrl ? { display: "none" } : undefined}
      >
        暂无图片
      </span>
    </div>
  );
};

interface ProductDetailModalProps {
  row?: ProductManagementRow;
  onClose: () => void;
}

type ProductDetailSection = "basic" | "logistics" | "images" | "analysis";

const productSections: { key: ProductDetailSection; label: string }[] = [
  { key: "basic", label: "基本信息" },
  { key: "logistics", label: "物流报关清关" },
  { key: "images", label: "图片信息" },
  { key: "analysis", label: "商品分析资料" },
];


interface DetailFieldItem {
  label: string;
  value: ReactNode;
  extra?: string;
}

const productTagFallbackColor = "#1677ff";

const productTagStyle = (color: string | null | undefined): CSSProperties => ({
  "--product-tag-color": color || productTagFallbackColor,
}) as CSSProperties;

const renderProductSourceTag = (
  label: string | null | undefined,
  color: string | null | undefined,
) => (
  label ? (
    <span
      className="product-management__source-tag-pill"
      style={productTagStyle(color)}
    >
      {label}
    </span>
  ) : null
);

function DetailFieldGrid({ items }: { items: DetailFieldItem[] }) {
  return (
    <div className="product-management__detail-field-grid">
      {items.map((item) => (
        <div key={item.label} className="product-management__detail-field">
          <div className="product-management__detail-field-label">{item.label}</div>
          <div className="product-management__detail-field-value">{item.value ?? "暂无数据"}</div>
          {item.extra && <div className="product-management__detail-field-extra">{item.extra}</div>}
        </div>
      ))}
    </div>
  );
}

function calculationFallback(row: ProductManagementRow) {
  if (row.rootMissingCodes.some((code) => [
    "missing_purchase_cost",
    "missing_gross_weight",
    "missing_package_dimensions",
  ].includes(code))) return "缺基础数据";
  return row.calculationStatus === "invalid_denominator" ? "规则异常" : "无法计算";
}

const withUnit = (value: string | null | undefined, unit: string) => (
  value == null ? null : `${value} ${unit}`
);



const normalizeDetailPercent = (value: unknown) => {
  if (typeof value === "number") {
    return Math.min(100, Math.max(0, value));
  }

  if (typeof value === "string") {
    const matched = value.match(/-?\d+(?:\.\d+)?/);
    if (!matched) return 0;

    const parsed = Number(matched[0]);
    if (!Number.isFinite(parsed)) return 0;

    return Math.min(100, Math.max(0, parsed));
  }

  return 0;
};


function ProductDetailModal({ row, onClose }: ProductDetailModalProps) {
  const [sectionOverride, setSectionOverride] = useState<{
    rowId: string;
    section: ProductDetailSection;
  }>();
  const activeSection = sectionOverride && sectionOverride.rowId === row?.id
    ? sectionOverride.section
    : "basic";

  const closeModal = () => {
    setSectionOverride(undefined);
    onClose();
  };

  const renderContent = () => {
    if (!row) return null;

    if (activeSection === "images") {
      return (
        <section className="product-management__detail-main">
          <div className="product-management__image-gallery">
            {row.images.map((url, index) => (
              <div key={`${row.id}-${index}`} className="product-management__image-card">
                <div className="product-management__image-thumb">
                  <img src={url} alt={`产品图片 ${index + 1}`} />
                </div>
                <Typography.Text strong>{index === 0 ? "主图" : `图片 ${index + 1}`}</Typography.Text>
              </div>
            ))}
            {row.images.length === 0 && <Typography.Text type="secondary">暂无图片</Typography.Text>}
          </div>
        </section>
      );
    }

    if (activeSection === "logistics") {
      return (
        <section className="product-management__detail-main">
          <div className="product-management__detail-card">
            <div className="product-management__detail-card-title">报关基础信息</div>
            <DetailFieldGrid
              items={[
                { label: "中文报关名", value: row.customsNameCn },
                { label: "英文报关名", value: row.customsNameEn },
                { label: "中文材质", value: row.materialCn },
                { label: "英文材质", value: row.materialEn },
                { label: "中文用途", value: row.usageCn },
                { label: "英文用途", value: row.usageEn },
              ]}
            />
          </div>
          <div className="product-management__detail-card">
            <div className="product-management__detail-card-title">规格信息</div>
            <DetailFieldGrid
              items={[
                { label: "包装规格", value: row.packageSpec },
                { label: "外箱规格", value: row.cartonSpec },
                { label: "单品规格", value: row.productSpec },
                { label: "毛重", value: row.grossWeightKg },
                { label: "净重", value: row.netWeightKg },
                { label: "采购交期", value: row.purchaseLeadTime },
              ]}
            />
          </div>
        </section>
      );
    }

    if (activeSection === "analysis") {
      return (
        <section className="product-management__detail-main">
          <div className="product-management__file-grid">
            {[
              ["竞品文案信息表", "记录竞品标题、卖点、描述等文案结构"],
              ["关键词分析表", "记录关键词、搜索量、竞争度等分析数据"],
              ["图片分析表", "记录主图、场景图、尺寸图与卖点图分析"],
              ["平台竞争ID", "记录 Walmart / Amazon / Temu 竞品 ID"],
            ].map(([title, desc]) => (
              <div key={title} className="product-management__file-card">
                <div className="product-management__file-icon">表</div>
                <div>
                  <Typography.Text strong>{title}</Typography.Text>
                  <Typography.Text type="secondary">{desc}</Typography.Text>
                </div>
                <Tag>待接入</Tag>
              </div>
            ))}
          </div>
        </section>
      );
    }

    return (
      <section className="product-management__detail-main">
        <div className="product-management__detail-card">
          <div className="product-management__detail-card-title">基础档案</div>
          <DetailFieldGrid
            items={[
              { label: "产品名称", value: row.productName },
              { label: "SKU", value: row.sku },
              {
                label: "标签",
                value: renderProductSourceTag(
                  row.sourceTags[0],
                  row.sourceTags[0] ? row.sourceTagColors?.[row.sourceTags[0]] : null,
                ),
              },
              { label: "负责人", value: row.ownerName },
              { label: "开发人", value: row.developerName },
            ]}
          />
        </div>
        <div className="product-management__detail-card">
          <div className="product-management__detail-card-title">成本与费用</div>
          <DetailFieldGrid
            items={[
              { label: "产品采购价", value: row.purchasePrice },
              { label: "头程运费", value: row.firstLegFreight ?? calculationFallback(row) },
              {
                label: "头程计费重",
                value: withUnit(row.pricingBreakdown?.firstLegChargeableWeightKg, "kg"),
              },
              {
                label: "每日仓储费",
                value: row.pricingBreakdown?.dailyStorageFeeUsd
                  ? `USD ${row.pricingBreakdown.dailyStorageFeeUsd}`
                  : calculationFallback(row),
              },
              { label: "WFS费用", value: row.wfsFee ?? calculationFallback(row) },
              { label: "清仓售价", value: row.clearancePrice ?? calculationFallback(row) },
            ]}
          />
        </div>
      </section>
    );
  };

  return (
    <Modal
      className="product-management__detail-modal"
      title="产品详情"
      open={Boolean(row)}
      width={1050}
      centered
      destroyOnHidden
      footer={row ? (
        <div className="product-management__detail-footer">
          <Button type="primary" onClick={closeModal}>关闭</Button>
        </div>
      ) : null}
      onCancel={closeModal}
    >
      {row && (
        <div className="product-management__detail-modern">
          <div className="product-management__detail-layout">
            <aside className="product-management__detail-aside">
              <div className="product-management__detail-product-card">
                <div className="product-management__detail-image-modern">{renderDetailProductImage(row)}</div>
                <div className="product-management__detail-progress-box">
                  <div><span>基础资料完整度</span><b>{row.dataCompleteness ?? "-"}{row.dataCompleteness === null ? "" : "%"}</b></div>
                  <Progress percent={normalizeDetailPercent(row.dataCompleteness)} showInfo={false} size="small" />
                </div>
              </div>
              <div className="product-management__detail-nav-card">
                {productSections.map((section) => (
                  <button
                    key={section.key}
                    className={activeSection === section.key ? "active" : undefined}
                    type="button"
                    onClick={() => setSectionOverride({ rowId: row.id, section: section.key })}
                  >
                    {section.label}<span>›</span>
                  </button>
                ))}
              </div>
            </aside>
            {renderContent()}
          </div>
        </div>
      )}
    </Modal>
  );
}

export default ProductDetailModal;

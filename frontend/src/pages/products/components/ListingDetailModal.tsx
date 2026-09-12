import { Button, Modal, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import type { ListingManagementRow } from "@/pages/products/listingManagementData";

interface ListingDetailModalProps {
  row?: ListingManagementRow;
  onClose: () => void;
}

type ListingDetailSection = "basic" | "status" | "inventory" | "governance";

const listingSections: { key: ListingDetailSection; label: string }[] = [
  { key: "basic", label: "基础档案" },
  { key: "status", label: "平台状态" },
  { key: "inventory", label: "销售库存" },
  { key: "governance", label: "治理记录" },
];

const statusColorMap: Record<string, string> = {
  启用: "green",
  停用: "red",
  在线: "green",
  离线: "red",
  拥有: "green",
  未拥有: "orange",
  是: "orange",
  否: "default",
};

interface ListingFieldItem {
  label: string;
  value: string | number;
}

function ListingFieldGrid({ items }: { items: ListingFieldItem[] }) {
  return (
    <div className="listing-management__detail-field-grid">
      {items.map((item) => (
        <div key={item.label} className="listing-management__detail-field">
          <div className="listing-management__detail-field-label">{item.label}</div>
          <div className="listing-management__detail-field-value">{item.value || "-"}</div>
        </div>
      ))}
    </div>
  );
}

function ListingDetailModal({ row, onClose }: ListingDetailModalProps) {
  const [activeSection, setActiveSection] = useState<ListingDetailSection>("basic");

  useEffect(() => {
    if (row) setActiveSection("basic");
  }, [row?.id]);

  const renderContent = () => {
    if (!row) return null;

    if (activeSection === "status") {
      return (
        <section className="listing-management__detail-main-card">
          <Typography.Title level={4}>平台状态</Typography.Title>
          <ListingFieldGrid
            items={[
              { label: "产品状态", value: row.productStatus },
              { label: "Listing状态", value: row.listingStatus },
              { label: "购物车状态", value: row.buyBoxStatus },
              { label: "是否被跟卖", value: row.resold },
              { label: "Walmart卖家", value: row.walmartSeller },
              { label: "停用原因", value: row.disabledReason || "-" },
            ]}
          />
        </section>
      );
    }

    if (activeSection === "inventory") {
      return (
        <section className="listing-management__detail-main-card">
          <Typography.Title level={4}>销售库存</Typography.Title>
          <ListingFieldGrid
            items={[
              { label: "划线价", value: `$${row.listPrice.toFixed(2)}` },
              { label: "在售价", value: `$${row.salePrice.toFixed(2)}` },
              { label: "WFS可售库存", value: row.wfsAvailableInventory },
              { label: "在途库存", value: row.inboundInventory },
              { label: "近90天销量", value: row.sales90Days },
              { label: "近30天广告费", value: `$${row.adSpend30Days.toFixed(2)}` },
              { label: "评分", value: row.rating },
              { label: "评论数", value: row.reviewCount },
            ]}
          />
        </section>
      );
    }

    if (activeSection === "governance") {
      return (
        <section className="listing-management__detail-main-card">
          <Typography.Title level={4}>治理记录</Typography.Title>
          <div className="listing-management__governance-list">
            <div>
              <Typography.Text strong>最近检查时间</Typography.Text>
              <Typography.Text>{row.checkedAt}</Typography.Text>
            </div>
            <div>
              <Typography.Text strong>购物车监控</Typography.Text>
              <Typography.Text>{row.buyBoxStatus === "未拥有" ? "需要跟进 Buy Box 风险" : "当前正常"}</Typography.Text>
            </div>
            <div>
              <Typography.Text strong>跟卖监控</Typography.Text>
              <Typography.Text>{row.resold === "是" ? "发现跟卖，建议复核价格与卖家" : "暂无跟卖"}</Typography.Text>
            </div>
            <div>
              <Typography.Text strong>治理状态</Typography.Text>
              <Typography.Text>{row.listingStatus === "离线" ? "需处理离线原因" : "持续监控"}</Typography.Text>
            </div>
          </div>
        </section>
      );
    }

    return (
      <section className="listing-management__detail-main-card">
        <Typography.Title level={4}>基础档案</Typography.Title>
        <ListingFieldGrid
          items={[
            { label: "店铺", value: row.store },
            { label: "负责人", value: row.owner },
            { label: "SKU", value: row.sku },
            { label: "产品类型", value: row.productType },
            { label: "生命周期", value: row.lifecycle },
            { label: "上架时间", value: row.listedAt },
            { label: "类目", value: row.category },
            { label: "品牌", value: row.brand },
            { label: "GTIN", value: row.gtin },
            { label: "产品等级", value: row.productGrade },
            { label: "标签", value: row.tags.join(" / ") },
            { label: "检查时间", value: row.checkedAt },
          ]}
        />
      </section>
    );
  };

  return (
    <Modal
      className="listing-management__detail-modal"
      title="Listing 详情"
      open={Boolean(row)}
      width="min(1080px, calc(100vw - 64px))"
      centered
      destroyOnHidden
      footer={(
        <div className="listing-management__detail-footer">
          <Button onClick={onClose}>关闭</Button>
        </div>
      )}
      onCancel={onClose}
    >
      {row && (
        <div className="listing-management__detail-modern">
          <section className="listing-management__detail-hero-modern">
            <div className="listing-management__detail-image-large">{row.image}</div>
            <div className="listing-management__detail-title-block">
              <Typography.Title level={3}>{row.productName}</Typography.Title>
              <Typography.Text type="secondary">{row.title}</Typography.Text>
              <div className="listing-management__detail-tags">
                <Tag color={statusColorMap[row.listingStatus]}>{row.listingStatus}</Tag>
                <Tag color={statusColorMap[row.buyBoxStatus]}>{row.buyBoxStatus}</Tag>
                {row.tags.map((tag) => <Tag key={tag} color="blue">{tag}</Tag>)}
              </div>
            </div>
            <div className="listing-management__detail-stat-pills">
              <div><strong>{row.msku}</strong><span>MSKU</span></div>
              <div><strong>{row.productId}</strong><span>商品ID</span></div>
              <div><strong>{row.rating}</strong><span>评分</span></div>
            </div>
          </section>
          <div className="listing-management__detail-layout">
            <aside className="listing-management__detail-menu">
              {listingSections.map((section) => (
                <button
                  key={section.key}
                  className={activeSection === section.key ? "active" : undefined}
                  type="button"
                  onClick={() => setActiveSection(section.key)}
                >
                  {section.label}
                </button>
              ))}
            </aside>
            {renderContent()}
          </div>
        </div>
      )}
    </Modal>
  );
}

export default ListingDetailModal;

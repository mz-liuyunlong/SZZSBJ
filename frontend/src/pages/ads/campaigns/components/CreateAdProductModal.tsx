import { DeleteOutlined, SearchOutlined } from "@ant-design/icons";
import {
  Button,
  Card,
  Empty,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMemo, useState } from "react";

import type { AdsCampaign, CampaignDetailRow } from "../adsCampaignTypes";

import "./CreateAdProductModal.css";

interface ProductCandidate {
  id: string;
  name: string;
  availableQuantity: number;
}

interface SelectedAdProduct extends ProductCandidate {
  bid: number;
}

export interface CreateAdProductValues {
  campaignId: string;
  adGroupId: string;
  products: SelectedAdProduct[];
}

interface CreateAdProductModalProps {
  open: boolean;
  currentCampaign: AdsCampaign | null;
  campaigns: AdsCampaign[];
  adGroups: CampaignDetailRow[];
  onCancel: () => void;
  onSubmit: (values: CreateAdProductValues) => void;
}

const maxSelectedProducts = 2000;

const productPool: ProductCandidate[] = [
  {
    id: "20226216904",
    name: "Trash Bag Holder with Bamboo Lid",
    availableQuantity: 261,
  },
  {
    id: "20250072767",
    name: "50PC Toilet Bowl Wand Refill Set",
    availableQuantity: 46,
  },
  {
    id: "20259123190",
    name: "4PCS Handwoven Wicker Laundry Basket",
    availableQuantity: 36,
  },
  {
    id: "20266522460",
    name: "2 Tier Metal Side Table with Storage",
    availableQuantity: 0,
  },
  {
    id: "20277220088",
    name: "2-Pack 8-Inch Non-Stick Square Pan",
    availableQuantity: 0,
  },
  {
    id: "20298803702",
    name: "2.2lb Pullman Loaf Pan with Cover",
    availableQuantity: 0,
  },
  {
    id: "20315102386",
    name: "3 Tier Fruit Basket for Kitchen",
    availableQuantity: 1,
  },
];

const truncateProductName = (name: string) =>
  name.length > 30 ? `${name.slice(0, 30)}...` : name;

function CreateAdProductModal({
  open,
  currentCampaign,
  campaigns,
  adGroups,
  onCancel,
  onSubmit,
}: CreateAdProductModalProps) {
  const [campaignId, setCampaignId] = useState<string>();
  const [adGroupId, setAdGroupId] = useState<string>();
  const [keyword, setKeyword] = useState("");
  const [selectedProducts, setSelectedProducts] = useState<SelectedAdProduct[]>(
    [],
  );

  const selectedProductIds = useMemo(
    () => new Set(selectedProducts.map((product) => product.id)),
    [selectedProducts],
  );

  const canLoadProducts = Boolean(campaignId && adGroupId);

  const filteredProducts = useMemo(() => {
    if (!canLoadProducts) return [];

    const normalizedKeyword = keyword.trim().toLowerCase();

    return productPool.filter((product) => {
      if (selectedProductIds.has(product.id)) return false;
      if (!normalizedKeyword) return true;

      return (
        product.name.toLowerCase().includes(normalizedKeyword) ||
        product.id.includes(normalizedKeyword)
      );
    });
  }, [canLoadProducts, keyword, selectedProductIds]);

  const resetModal = () => {
    setCampaignId(undefined);
    setAdGroupId(undefined);
    setKeyword("");
    setSelectedProducts([]);
  };

  const handleCancel = () => {
    resetModal();
    onCancel();
  };

  const handleCampaignChange = (nextCampaignId: string) => {
    setCampaignId(nextCampaignId);
    setAdGroupId(undefined);
    setKeyword("");
    setSelectedProducts([]);
  };

  const addProduct = (product: ProductCandidate) => {
    setSelectedProducts((current) => {
      if (
        current.length >= maxSelectedProducts ||
        current.some((item) => item.id === product.id)
      ) {
        return current;
      }

      return [
        ...current,
        {
          ...product,
          bid: 0.45,
        },
      ];
    });
  };

  const addAllVisibleProducts = () => {
    setSelectedProducts((current) => {
      const currentIds = new Set(current.map((item) => item.id));
      const nextProducts = filteredProducts
        .filter((product) => !currentIds.has(product.id))
        .slice(0, Math.max(maxSelectedProducts - current.length, 0))
        .map((product) => ({
          ...product,
          bid: 0.45,
        }));

      return [...current, ...nextProducts];
    });
  };

  const removeProduct = (productId: string) => {
    setSelectedProducts((current) =>
      current.filter((product) => product.id !== productId),
    );
  };

  const updateBid = (productId: string, bid: number | null) => {
    setSelectedProducts((current) =>
      current.map((product) =>
        product.id === productId
          ? {
              ...product,
              bid: bid ?? 0,
            }
          : product,
      ),
    );
  };

  const handleSubmit = () => {
    if (!campaignId || !adGroupId) return;

    onSubmit({
      campaignId,
      adGroupId,
      products: selectedProducts,
    });

    resetModal();
  };

  const availableColumns: ColumnsType<ProductCandidate> = [
    {
      title: "商品名称",
      dataIndex: "name",
      width: 280,
      render: (value: string) => (
        <span title={value}>{truncateProductName(value)}</span>
      ),
    },
    {
      title: "商品ID",
      dataIndex: "id",
      width: 150,
    },
    {
      title: "可售库存",
      dataIndex: "availableQuantity",
      width: 110,
    },
    {
      title: "操作",
      key: "action",
      width: 90,
      render: (_, record) => (
        <Button type="link" onClick={() => addProduct(record)}>
          添加
        </Button>
      ),
    },
  ];

  const selectedColumns: ColumnsType<SelectedAdProduct> = [
    {
      title: "商品名称",
      dataIndex: "name",
      width: 260,
      render: (value: string) => (
        <span title={value}>{truncateProductName(value)}</span>
      ),
    },
    {
      title: "商品ID",
      dataIndex: "id",
      width: 150,
    },
    {
      title: (
        <Space size={4}>
          <span>竞价</span>
          <Button type="link" size="small">
            批量
          </Button>
        </Space>
      ),
      dataIndex: "bid",
      width: 140,
      render: (_, record) => (
        <Space.Compact className="create-ad-product-modal__bid">
          <Button disabled>$</Button>
          <InputNumber
            min={0.01}
            step={0.01}
            controls={false}
            value={record.bid}
            onChange={(value) => updateBid(record.id, value)}
          />
        </Space.Compact>
      ),
    },
    {
      title: "操作",
      key: "action",
      width: 90,
      render: (_, record) => (
        <Button
          type="link"
          danger
          icon={<DeleteOutlined />}
          onClick={() => removeProduct(record.id)}
        >
          移除
        </Button>
      ),
    },
  ];

  return (
    <Modal
      open={open}
      title="创建广告商品"
      width={1320}
      centered
      destroyOnClose
      onCancel={handleCancel}
      footer={[
        <Button key="cancel" onClick={handleCancel}>
          取消
        </Button>,
        <Button
          key="submit"
          type="primary"
          disabled={!campaignId || !adGroupId || selectedProducts.length === 0}
          onClick={handleSubmit}
        >
          保存
        </Button>,
      ]}
    >
      <div className="create-ad-product-modal">
        <Card size="small" className="create-ad-product-modal__section">
          <Typography.Title
            level={5}
            className="create-ad-product-modal__section-title"
          >
            设置
          </Typography.Title>

          <div className="create-ad-product-modal__settings-grid">
            <div className="create-ad-product-modal__field-row">
              <span className="create-ad-product-modal__required">*</span>
              <span className="create-ad-product-modal__field-label">
                店铺：
              </span>
              <Input value={currentCampaign?.account ?? "--"} readOnly />
            </div>

            <div className="create-ad-product-modal__field-row">
              <span className="create-ad-product-modal__required">*</span>
              <span className="create-ad-product-modal__field-label">
                广告活动：
              </span>
              <Select
                allowClear
                placeholder="请选择广告活动"
                value={campaignId}
                options={campaigns.map((campaign) => ({
                  label: campaign.name,
                  value: campaign.id,
                }))}
                onChange={handleCampaignChange}
              />
            </div>

            <div className="create-ad-product-modal__field-row">
              <span className="create-ad-product-modal__required">*</span>
              <span className="create-ad-product-modal__field-label">
                广告组：
              </span>
              <Select
                allowClear
                placeholder="请选择广告组"
                disabled={!campaignId}
                value={adGroupId}
                options={adGroups.map((adGroup) => ({
                  label: adGroup.name,
                  value: adGroup.id,
                }))}
                onChange={(value) => {
                  setAdGroupId(value);
                  setKeyword("");
                  setSelectedProducts([]);
                }}
              />
            </div>
          </div>
        </Card>

        <Card
          size="small"
          className="create-ad-product-modal__section create-ad-product-modal__product-section"
          title="添加广告商品"
        >
          <div className="create-ad-product-modal__product-layout">
            <div className="create-ad-product-modal__product-pane">
              <div className="create-ad-product-modal__pane-toolbar">
                <Input
                  allowClear
                  className="create-ad-product-modal__search"
                  prefix={<SearchOutlined />}
                  placeholder="请输入商品名称、商品ID查询"
                  disabled={!canLoadProducts}
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                />
                <Button
                  type="link"
                  disabled={!canLoadProducts}
                  onClick={addAllVisibleProducts}
                >
                  添加全部
                </Button>
              </div>

              <Table<ProductCandidate>
                rowKey="id"
                size="small"
                columns={availableColumns}
                dataSource={filteredProducts}
                locale={{
                  emptyText: canLoadProducts ? (
                    <Empty description="暂无数据" />
                  ) : (
                    <Empty description="请选择广告活动和广告组后加载商品" />
                  ),
                }}
                pagination={
                  canLoadProducts
                    ? {
                        pageSize: 10,
                        showSizeChanger: false,
                        showTotal: (total) => `共 ${total} 条`,
                      }
                    : false
                }
                scroll={{ x: 620, y: 360 }}
              />
            </div>

            <div className="create-ad-product-modal__product-pane create-ad-product-modal__product-pane--selected">
              <div className="create-ad-product-modal__pane-toolbar">
                <Typography.Text>
                  已选择 <strong>{selectedProducts.length}</strong> 个商品
                  <Typography.Text type="secondary">
                    （最多可添加{maxSelectedProducts}个）
                  </Typography.Text>
                </Typography.Text>
                <Button type="link" onClick={() => setSelectedProducts([])}>
                  移除全部
                </Button>
              </div>

              <Table<SelectedAdProduct>
                rowKey="id"
                size="small"
                columns={selectedColumns}
                dataSource={selectedProducts}
                locale={{ emptyText: <Empty description="暂无数据" /> }}
                pagination={false}
                scroll={{ x: 650, y: 420 }}
              />
            </div>
          </div>
        </Card>
      </div>
    </Modal>
  );
}

export default CreateAdProductModal;

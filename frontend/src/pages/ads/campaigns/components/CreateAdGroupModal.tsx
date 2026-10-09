import { DeleteOutlined, SearchOutlined } from "@ant-design/icons";
import {
  Button,
  Card,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Space,
  Table,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMemo, useState } from "react";

import type { AdsCampaign } from "../adsCampaignTypes";

import "./CreateAdGroupModal.css";

interface ProductCandidate {
  id: string;
  name: string;
  availableQuantity: number;
}

interface SelectedProduct extends ProductCandidate {
  bid: number;
}

export interface CreateAdGroupValues {
  name: string;
  products: SelectedProduct[];
}

interface CreateAdGroupModalProps {
  open: boolean;
  campaign: AdsCampaign | null;
  onCancel: () => void;
  onSubmit: (values: CreateAdGroupValues) => void;
}

const maxSelectedProducts = 2000;

const productCandidates: ProductCandidate[] = [
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

function CreateAdGroupModal({
  open,
  campaign,
  onCancel,
  onSubmit,
}: CreateAdGroupModalProps) {
  const [form] = Form.useForm<{ name: string }>();
  const [keyword, setKeyword] = useState("");
  const [selectedProducts, setSelectedProducts] = useState<SelectedProduct[]>(
    [],
  );

  const selectedProductIds = useMemo(
    () => new Set(selectedProducts.map((product) => product.id)),
    [selectedProducts],
  );

  const filteredProducts = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase();

    return productCandidates.filter((product) => {
      if (selectedProductIds.has(product.id)) return false;
      if (!normalizedKeyword) return true;

      return (
        product.name.toLowerCase().includes(normalizedKeyword) ||
        product.id.includes(normalizedKeyword)
      );
    });
  }, [keyword, selectedProductIds]);

  const resetModal = () => {
    form.resetFields();
    setKeyword("");
    setSelectedProducts([]);
  };

  const handleCancel = () => {
    resetModal();
    onCancel();
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

  const handleSubmit = async () => {
    const values = await form.validateFields();

    onSubmit({
      name: values.name,
      products: selectedProducts,
    });

    resetModal();
  };

  const availableColumns: ColumnsType<ProductCandidate> = [
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

  const selectedColumns: ColumnsType<SelectedProduct> = [
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
        <Space.Compact className="create-ad-group-modal__bid">
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
      title="创建广告组"
      width={1320}
      centered
      destroyOnClose
      onCancel={handleCancel}
      footer={[
        <Button key="cancel" onClick={handleCancel}>
          取消
        </Button>,
        <Button key="submit" type="primary" onClick={() => void handleSubmit()}>
          保存
        </Button>,
      ]}
    >
      <div className="create-ad-group-modal">
        <Card size="small" className="create-ad-group-modal__section">
          <Typography.Title
            level={5}
            className="create-ad-group-modal__section-title"
          >
            设置
          </Typography.Title>
          <div className="create-ad-group-modal__settings-grid">
            <div className="create-ad-group-modal__readonly-field">
              <span className="create-ad-group-modal__required">*</span>
              <span className="create-ad-group-modal__field-label">店铺：</span>
              <Input value={campaign?.account ?? "--"} readOnly />
            </div>
            <div className="create-ad-group-modal__readonly-field">
              <span className="create-ad-group-modal__required">*</span>
              <span className="create-ad-group-modal__field-label">
                广告活动：
              </span>
              <Input value={campaign?.name ?? "--"} readOnly />
            </div>
          </div>
        </Card>

        <Typography.Title
          level={5}
          className="create-ad-group-modal__page-title"
        >
          创建广告组
        </Typography.Title>

        <Card size="small" className="create-ad-group-modal__section">
          <Typography.Title
            level={5}
            className="create-ad-group-modal__section-title"
          >
            广告组设置
          </Typography.Title>
          <Form
            form={form}
            layout="vertical"
            className="create-ad-group-modal__form"
          >
            <Form.Item
              label="广告组名称"
              name="name"
              rules={[{ required: true, message: "请输入广告组名称" }]}
            >
              <Input maxLength={255} showCount />
            </Form.Item>
          </Form>
        </Card>

        <Card
          size="small"
          className="create-ad-group-modal__section create-ad-group-modal__product-section"
          title="添加广告商品"
        >
          <div className="create-ad-group-modal__product-layout">
            <div className="create-ad-group-modal__product-pane">
              <div className="create-ad-group-modal__pane-toolbar">
                <Input
                  allowClear
                  className="create-ad-group-modal__search"
                  prefix={<SearchOutlined />}
                  placeholder="请输入商品名称、商品ID查询"
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                />
                <Button type="link" onClick={addAllVisibleProducts}>
                  添加全部
                </Button>
              </div>

              <Table<ProductCandidate>
                rowKey="id"
                size="small"
                columns={availableColumns}
                dataSource={filteredProducts}
                pagination={{
                  pageSize: 10,
                  showSizeChanger: false,
                  showTotal: (total) => `共 ${total} 条`,
                }}
                scroll={{ x: 620, y: 360 }}
              />
            </div>

            <div className="create-ad-group-modal__product-pane create-ad-group-modal__product-pane--selected">
              <div className="create-ad-group-modal__pane-toolbar">
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

              <Table<SelectedProduct>
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

export default CreateAdGroupModal;

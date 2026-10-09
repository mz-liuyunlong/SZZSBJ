import { DeleteOutlined } from "@ant-design/icons";
import {
  Button,
  Card,
  Checkbox,
  Empty,
  Input,
  Modal,
  Radio,
  Select,
  Table,
  Tabs,
  Typography,
} from "antd";
import type { CheckboxChangeEvent } from "antd/es/checkbox";
import type { ColumnsType } from "antd/es/table";
import { useMemo, useState } from "react";

import type { AdsCampaign, CampaignDetailRow } from "../adsCampaignTypes";

import "./CreateNegativeKeywordModal.css";

type NegativeMatchType = "exact" | "phrase";
type DeliveryType = "auto" | "manual";

interface SelectedNegativeKeyword {
  id: string;
  keyword: string;
  matchType: NegativeMatchType;
}

export interface CreateNegativeKeywordValues {
  campaignId: string;
  adGroupId?: string;
  deliveryType: DeliveryType;
  negativeKeywords: SelectedNegativeKeyword[];
}

interface CreateNegativeKeywordModalProps {
  open: boolean;
  currentCampaign: AdsCampaign | null;
  campaigns: AdsCampaign[];
  adGroups: CampaignDetailRow[];
  onCancel: () => void;
  onSubmit: (values: CreateNegativeKeywordValues) => void;
}

const maxSelectedNegativeKeywords = 500;

const negativeMatchTypeLabel: Record<NegativeMatchType, string> = {
  exact: "精准",
  phrase: "词组",
};

function CreateNegativeKeywordModal({
  open,
  currentCampaign,
  campaigns,
  adGroups,
  onCancel,
  onSubmit,
}: CreateNegativeKeywordModalProps) {
  const [deliveryType, setDeliveryType] = useState<DeliveryType>("manual");
  const [campaignId, setCampaignId] = useState<string>();
  const [adGroupId, setAdGroupId] = useState<string>();
  const [negativeTypes, setNegativeTypes] = useState<NegativeMatchType[]>([
    "exact",
  ]);
  const [manualText, setManualText] = useState("");
  const [selectedKeywords, setSelectedKeywords] = useState<
    SelectedNegativeKeyword[]
  >([]);

  const canAddKeywords = Boolean(
    campaignId && (deliveryType === "auto" || adGroupId),
  );

  const selectedKeywordNames = useMemo(
    () =>
      new Set(
        selectedKeywords.map(
          (item) => `${item.keyword.toLowerCase()}::${item.matchType}`,
        ),
      ),
    [selectedKeywords],
  );

  const resetModal = () => {
    setDeliveryType("manual");
    setCampaignId(undefined);
    setAdGroupId(undefined);
    setNegativeTypes(["exact"]);
    setManualText("");
    setSelectedKeywords([]);
  };

  const handleCancel = () => {
    resetModal();
    onCancel();
  };

  const handleCampaignChange = (value: string) => {
    setCampaignId(value);
    setAdGroupId(undefined);
    setManualText("");
    setSelectedKeywords([]);
  };

  const handleNegativeTypeChange =
    (type: NegativeMatchType) => (event: CheckboxChangeEvent) => {
      setNegativeTypes((current) => {
        if (event.target.checked) {
          return Array.from(new Set([...current, type]));
        }

        const next = current.filter((item) => item !== type);
        return next.length > 0 ? next : current;
      });
    };

  const addManualNegativeKeywords = () => {
    if (!canAddKeywords || negativeTypes.length === 0) return;

    const keywords = manualText
      .split(/\n+/)
      .map((item) => item.trim())
      .filter(Boolean);

    if (keywords.length === 0) return;

    setSelectedKeywords((current) => {
      const currentKeys = new Set(
        current.map(
          (item) => `${item.keyword.toLowerCase()}::${item.matchType}`,
        ),
      );
      const nextItems: SelectedNegativeKeyword[] = [];

      for (const keyword of keywords) {
        for (const matchType of negativeTypes) {
          const uniqueKey = `${keyword.toLowerCase()}::${matchType}`;
          if (currentKeys.has(uniqueKey) || selectedKeywordNames.has(uniqueKey))
            continue;

          nextItems.push({
            id: `NEG-${Date.now()}-${nextItems.length}`,
            keyword,
            matchType,
          });

          currentKeys.add(uniqueKey);

          if (
            current.length + nextItems.length >=
            maxSelectedNegativeKeywords
          ) {
            break;
          }
        }

        if (current.length + nextItems.length >= maxSelectedNegativeKeywords) {
          break;
        }
      }

      return [...current, ...nextItems];
    });

    setManualText("");
  };

  const removeKeyword = (id: string) => {
    setSelectedKeywords((current) => current.filter((item) => item.id !== id));
  };

  const handleSubmit = () => {
    if (!campaignId || selectedKeywords.length === 0) return;
    if (deliveryType === "manual" && !adGroupId) return;

    onSubmit({
      campaignId,
      adGroupId,
      deliveryType,
      negativeKeywords: selectedKeywords,
    });

    resetModal();
  };

  const selectedColumns: ColumnsType<SelectedNegativeKeyword> = [
    {
      title: "否定关键词",
      dataIndex: "keyword",
      width: 260,
    },
    {
      title: "否定类型",
      dataIndex: "matchType",
      width: 150,
      render: (value: NegativeMatchType) => negativeMatchTypeLabel[value],
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
          onClick={() => removeKeyword(record.id)}
        >
          移除
        </Button>
      ),
    },
  ];

  return (
    <Modal
      open={open}
      title="添加否定关键词"
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
          disabled={
            !campaignId ||
            selectedKeywords.length === 0 ||
            (deliveryType === "manual" && !adGroupId)
          }
          onClick={handleSubmit}
        >
          保存
        </Button>,
      ]}
    >
      <div className="create-negative-keyword-modal">
        <Card size="small" className="create-negative-keyword-modal__section">
          <Typography.Title
            level={5}
            className="create-negative-keyword-modal__section-title"
          >
            设置
          </Typography.Title>

          <div className="create-negative-keyword-modal__settings-grid">
            <div className="create-negative-keyword-modal__field-row">
              <span className="create-negative-keyword-modal__required">*</span>
              <span className="create-negative-keyword-modal__field-label">
                店铺：
              </span>
              <Select
                value={
                  currentCampaign?.account ?? "CN2602-添洋商贸(邓添祥)-574861"
                }
                options={[
                  {
                    label:
                      currentCampaign?.account ??
                      "CN2602-添洋商贸(邓添祥)-574861",
                    value:
                      currentCampaign?.account ??
                      "CN2602-添洋商贸(邓添祥)-574861",
                  },
                ]}
              />
            </div>

            <div className="create-negative-keyword-modal__field-row">
              <span className="create-negative-keyword-modal__required">*</span>
              <span className="create-negative-keyword-modal__field-label">
                投放类型：
              </span>
              <Radio.Group
                value={deliveryType}
                onChange={(event) => {
                  setDeliveryType(event.target.value as DeliveryType);
                  setAdGroupId(undefined);
                  setSelectedKeywords([]);
                }}
              >
                <Radio value="auto">自动投放</Radio>
                <Radio value="manual">手动投放</Radio>
              </Radio.Group>
            </div>

            <div className="create-negative-keyword-modal__field-row">
              <span className="create-negative-keyword-modal__required">*</span>
              <span className="create-negative-keyword-modal__field-label">
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

            <div className="create-negative-keyword-modal__field-row">
              <span className="create-negative-keyword-modal__required">*</span>
              <span className="create-negative-keyword-modal__field-label">
                广告组：
              </span>
              <Select
                allowClear
                placeholder="请选择广告组"
                disabled={!campaignId || deliveryType === "auto"}
                value={adGroupId}
                options={adGroups.map((adGroup) => ({
                  label: adGroup.name,
                  value: adGroup.id,
                }))}
                onChange={(value) => {
                  setAdGroupId(value);
                  setManualText("");
                  setSelectedKeywords([]);
                }}
              />
            </div>
          </div>
        </Card>

        <Card
          size="small"
          className="create-negative-keyword-modal__section create-negative-keyword-modal__keyword-section"
          title="添加否定关键词"
        >
          <div className="create-negative-keyword-modal__layout">
            <div className="create-negative-keyword-modal__pane">
              <Tabs
                activeKey="manual"
                items={[
                  {
                    key: "manual",
                    label: "手动输入",
                  },
                ]}
              />

              <div className="create-negative-keyword-modal__type-row">
                <span className="create-negative-keyword-modal__field-label">
                  否定类型：
                </span>
                <Checkbox
                  checked={negativeTypes.includes("exact")}
                  onChange={handleNegativeTypeChange("exact")}
                >
                  精准
                </Checkbox>
                <Checkbox
                  checked={negativeTypes.includes("phrase")}
                  onChange={handleNegativeTypeChange("phrase")}
                >
                  词组
                </Checkbox>
              </div>

              <Input.TextArea
                className="create-negative-keyword-modal__textarea"
                rows={12}
                disabled={!canAddKeywords}
                placeholder="请输入否定关键词"
                value={manualText}
                onChange={(event) => setManualText(event.target.value)}
              />

              <Button
                type="primary"
                disabled={!canAddKeywords || !manualText.trim()}
                onClick={addManualNegativeKeywords}
              >
                添加否定关键词
              </Button>
            </div>

            <div className="create-negative-keyword-modal__pane create-negative-keyword-modal__pane--selected">
              <div className="create-negative-keyword-modal__pane-toolbar">
                <Typography.Text>
                  已选择 <strong>{selectedKeywords.length}</strong> 个否定关键词
                  <Typography.Text type="secondary">
                    （最多可添加{maxSelectedNegativeKeywords}）
                  </Typography.Text>
                </Typography.Text>
                <Button type="link" onClick={() => setSelectedKeywords([])}>
                  全部移除
                </Button>
              </div>

              <Table<SelectedNegativeKeyword>
                rowKey="id"
                size="small"
                columns={selectedColumns}
                dataSource={selectedKeywords}
                locale={{ emptyText: <Empty description="暂无数据" /> }}
                pagination={false}
                scroll={{ x: 560, y: 430 }}
              />
            </div>
          </div>
        </Card>
      </div>
    </Modal>
  );
}

export default CreateNegativeKeywordModal;

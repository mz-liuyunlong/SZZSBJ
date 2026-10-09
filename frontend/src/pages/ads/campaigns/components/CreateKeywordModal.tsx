import { DeleteOutlined, SearchOutlined } from "@ant-design/icons";
import {
  Button,
  Card,
  Checkbox,
  Empty,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Tabs,
  Typography,
} from "antd";
import type { CheckboxChangeEvent } from "antd/es/checkbox";
import type { ColumnsType } from "antd/es/table";
import { useMemo, useState } from "react";

import type { AdsCampaign, CampaignDetailRow } from "../adsCampaignTypes";

import "./CreateKeywordModal.css";

type MatchType = "broad" | "phrase" | "exact";

interface KeywordCandidate {
  id: string;
  keyword: string;
  matchType: MatchType;
  suggestedBid: number;
}

interface SelectedKeyword extends KeywordCandidate {
  bid: number;
}

export interface CreateKeywordValues {
  campaignId: string;
  adGroupId: string;
  keywords: SelectedKeyword[];
}

interface CreateKeywordModalProps {
  open: boolean;
  currentCampaign: AdsCampaign | null;
  campaigns: AdsCampaign[];
  adGroups: CampaignDetailRow[];
  onCancel: () => void;
  onSubmit: (values: CreateKeywordValues) => void;
}

const maxSelectedKeywords = 1000;

const matchTypeLabel: Record<MatchType, string> = {
  broad: "广泛",
  phrase: "词组",
  exact: "精准",
};

const keywordPool: KeywordCandidate[] = [
  {
    id: "KW-SUG-001",
    keyword: "kitchen storage organizer",
    matchType: "broad",
    suggestedBid: 0.45,
  },
  {
    id: "KW-SUG-002",
    keyword: "cabinet organizer",
    matchType: "phrase",
    suggestedBid: 0.52,
  },
  {
    id: "KW-SUG-003",
    keyword: "under sink organizer",
    matchType: "exact",
    suggestedBid: 0.48,
  },
  {
    id: "KW-SUG-004",
    keyword: "pantry storage bins",
    matchType: "broad",
    suggestedBid: 0.38,
  },
  {
    id: "KW-SUG-005",
    keyword: "bathroom storage shelf",
    matchType: "phrase",
    suggestedBid: 0.41,
  },
];

const defaultMatchTypes: MatchType[] = ["broad"];

function CreateKeywordModal({
  open,
  currentCampaign,
  campaigns,
  adGroups,
  onCancel,
  onSubmit,
}: CreateKeywordModalProps) {
  const [campaignId, setCampaignId] = useState<string>();
  const [adGroupId, setAdGroupId] = useState<string>();
  const [activeInputMode, setActiveInputMode] = useState<
    "suggested" | "manual"
  >("suggested");
  const [bidMode, setBidMode] = useState<"suggested" | "custom">("suggested");
  const [matchTypes, setMatchTypes] = useState<MatchType[]>(defaultMatchTypes);
  const [keywordSearch, setKeywordSearch] = useState("");
  const [manualKeywords, setManualKeywords] = useState("");
  const [selectedKeywords, setSelectedKeywords] = useState<SelectedKeyword[]>(
    [],
  );

  const canLoadKeywords = Boolean(campaignId && adGroupId);

  const selectedKeywordIds = useMemo(
    () => new Set(selectedKeywords.map((keyword) => keyword.id)),
    [selectedKeywords],
  );

  const filteredKeywords = useMemo(() => {
    if (!canLoadKeywords) return [];

    const normalizedKeyword = keywordSearch.trim().toLowerCase();

    return keywordPool.filter((keyword) => {
      if (selectedKeywordIds.has(keyword.id)) return false;
      if (!matchTypes.includes(keyword.matchType)) return false;
      if (!normalizedKeyword) return true;
      return keyword.keyword.toLowerCase().includes(normalizedKeyword);
    });
  }, [canLoadKeywords, keywordSearch, matchTypes, selectedKeywordIds]);

  const resetModal = () => {
    setCampaignId(undefined);
    setAdGroupId(undefined);
    setActiveInputMode("suggested");
    setBidMode("suggested");
    setMatchTypes(defaultMatchTypes);
    setKeywordSearch("");
    setManualKeywords("");
    setSelectedKeywords([]);
  };

  const handleCancel = () => {
    resetModal();
    onCancel();
  };

  const handleCampaignChange = (value: string) => {
    setCampaignId(value);
    setAdGroupId(undefined);
    setKeywordSearch("");
    setSelectedKeywords([]);
  };

  const addKeyword = (keyword: KeywordCandidate) => {
    setSelectedKeywords((current) => {
      if (
        current.length >= maxSelectedKeywords ||
        current.some((item) => item.id === keyword.id)
      ) {
        return current;
      }

      return [
        ...current,
        {
          ...keyword,
          bid: bidMode === "suggested" ? keyword.suggestedBid : 0.45,
        },
      ];
    });
  };

  const addAllVisibleKeywords = () => {
    setSelectedKeywords((current) => {
      const currentIds = new Set(current.map((item) => item.id));
      const nextKeywords = filteredKeywords
        .filter((keyword) => !currentIds.has(keyword.id))
        .slice(0, Math.max(maxSelectedKeywords - current.length, 0))
        .map((keyword) => ({
          ...keyword,
          bid: bidMode === "suggested" ? keyword.suggestedBid : 0.45,
        }));

      return [...current, ...nextKeywords];
    });
  };

  const addManualKeywords = () => {
    if (!canLoadKeywords) return;

    const keywords = manualKeywords
      .split(/\n+/)
      .map((item) => item.trim())
      .filter(Boolean);

    setSelectedKeywords((current) => {
      const currentNames = new Set(
        current.map((item) => item.keyword.toLowerCase()),
      );
      const nextKeywords = keywords
        .filter((keyword) => !currentNames.has(keyword.toLowerCase()))
        .slice(0, Math.max(maxSelectedKeywords - current.length, 0))
        .map((keyword, index) => ({
          id: `KW-MANUAL-${Date.now()}-${index}`,
          keyword,
          matchType: matchTypes[0] ?? "broad",
          suggestedBid: 0.45,
          bid: 0.45,
        }));

      return [...current, ...nextKeywords];
    });

    setManualKeywords("");
  };

  const removeKeyword = (keywordId: string) => {
    setSelectedKeywords((current) =>
      current.filter((keyword) => keyword.id !== keywordId),
    );
  };

  const updateBid = (keywordId: string, bid: number | null) => {
    setSelectedKeywords((current) =>
      current.map((keyword) =>
        keyword.id === keywordId
          ? {
              ...keyword,
              bid: bid ?? 0,
            }
          : keyword,
      ),
    );
  };

  const handleMatchTypeChange =
    (type: MatchType) => (event: CheckboxChangeEvent) => {
      setMatchTypes((current) => {
        if (event.target.checked) {
          return Array.from(new Set([...current, type]));
        }

        return current.filter((item) => item !== type);
      });
    };

  const handleSubmit = () => {
    if (!campaignId || !adGroupId) return;

    onSubmit({
      campaignId,
      adGroupId,
      keywords: selectedKeywords,
    });

    resetModal();
  };

  const candidateColumns: ColumnsType<KeywordCandidate> = [
    {
      title: "关键词",
      dataIndex: "keyword",
      width: 240,
    },
    {
      title: "匹配方式",
      dataIndex: "matchType",
      width: 120,
      render: (value: MatchType) => matchTypeLabel[value],
    },
    {
      title: "建议竞价",
      dataIndex: "suggestedBid",
      width: 120,
      render: (value: number) => `$${value.toFixed(2)}`,
    },
    {
      title: "操作",
      key: "action",
      width: 90,
      render: (_, record) => (
        <Button type="link" onClick={() => addKeyword(record)}>
          添加
        </Button>
      ),
    },
  ];

  const selectedColumns: ColumnsType<SelectedKeyword> = [
    {
      title: "关键词",
      dataIndex: "keyword",
      width: 240,
    },
    {
      title: "匹配方式",
      dataIndex: "matchType",
      width: 120,
      render: (value: MatchType) => matchTypeLabel[value],
    },
    {
      title: (
        <Space size={4}>
          <span>建议竞价</span>
          <Typography.Text type="secondary">ⓘ</Typography.Text>
        </Space>
      ),
      dataIndex: "suggestedBid",
      width: 120,
      render: (value: number) => `$${value.toFixed(2)}`,
    },
    {
      title: "竞价",
      dataIndex: "bid",
      width: 140,
      render: (_, record) => (
        <Space.Compact className="create-keyword-modal__bid">
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
      title="创建关键词"
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
          disabled={!campaignId || !adGroupId || selectedKeywords.length === 0}
          onClick={handleSubmit}
        >
          保存
        </Button>,
      ]}
    >
      <div className="create-keyword-modal">
        <Card size="small" className="create-keyword-modal__section">
          <Typography.Title
            level={5}
            className="create-keyword-modal__section-title"
          >
            设置
          </Typography.Title>

          <div className="create-keyword-modal__settings-grid">
            <div className="create-keyword-modal__field-row">
              <span className="create-keyword-modal__required">*</span>
              <span className="create-keyword-modal__field-label">店铺：</span>
              <Input value={currentCampaign?.account ?? "--"} readOnly />
            </div>

            <div className="create-keyword-modal__field-row">
              <span className="create-keyword-modal__required">*</span>
              <span className="create-keyword-modal__field-label">
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

            <div className="create-keyword-modal__field-row">
              <span className="create-keyword-modal__required">*</span>
              <span className="create-keyword-modal__field-label">
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
                  setKeywordSearch("");
                  setSelectedKeywords([]);
                }}
              />
            </div>
          </div>
        </Card>

        <Card
          size="small"
          className="create-keyword-modal__section create-keyword-modal__keyword-section"
          title="添加关键词"
        >
          <div className="create-keyword-modal__keyword-layout">
            <div className="create-keyword-modal__keyword-pane">
              <Tabs
                activeKey={activeInputMode}
                onChange={(value) =>
                  setActiveInputMode(value as "suggested" | "manual")
                }
                items={[
                  { key: "suggested", label: "建议关键词" },
                  { key: "manual", label: "手动输入" },
                ]}
              />

              <div className="create-keyword-modal__filters">
                <Space align="center" wrap>
                  <span className="create-keyword-modal__field-label">
                    竞价：
                  </span>
                  <Select
                    value={bidMode}
                    className="create-keyword-modal__bid-mode"
                    options={[
                      { label: "建议竞价", value: "suggested" },
                      { label: "自定义竞价", value: "custom" },
                    ]}
                    onChange={setBidMode}
                  />
                </Space>

                <Space align="center" wrap>
                  <span className="create-keyword-modal__field-label">
                    匹配方式：
                  </span>
                  <Checkbox
                    checked={matchTypes.includes("broad")}
                    onChange={handleMatchTypeChange("broad")}
                  >
                    广泛
                  </Checkbox>
                  <Checkbox
                    checked={matchTypes.includes("phrase")}
                    onChange={handleMatchTypeChange("phrase")}
                  >
                    词组
                  </Checkbox>
                  <Checkbox
                    checked={matchTypes.includes("exact")}
                    onChange={handleMatchTypeChange("exact")}
                  >
                    精准
                  </Checkbox>
                </Space>
              </div>

              {activeInputMode === "suggested" ? (
                <>
                  <div className="create-keyword-modal__pane-toolbar">
                    <Input
                      allowClear
                      className="create-keyword-modal__search"
                      prefix={<SearchOutlined />}
                      placeholder="请输入关键词查询"
                      disabled={!canLoadKeywords}
                      value={keywordSearch}
                      onChange={(event) => setKeywordSearch(event.target.value)}
                    />
                    <Button
                      type="link"
                      disabled={!canLoadKeywords}
                      onClick={addAllVisibleKeywords}
                    >
                      全部添加
                    </Button>
                  </div>

                  <Table<KeywordCandidate>
                    rowKey="id"
                    size="small"
                    columns={candidateColumns}
                    dataSource={filteredKeywords}
                    locale={{
                      emptyText: canLoadKeywords ? (
                        <Empty description="暂无数据" />
                      ) : (
                        <Empty description="请选择广告活动和广告组后加载关键词" />
                      ),
                    }}
                    pagination={false}
                    scroll={{ x: 620, y: 360 }}
                  />
                </>
              ) : (
                <div className="create-keyword-modal__manual">
                  <Input.TextArea
                    rows={10}
                    disabled={!canLoadKeywords}
                    placeholder="一行一个关键词"
                    value={manualKeywords}
                    onChange={(event) => setManualKeywords(event.target.value)}
                  />
                  <Button
                    type="primary"
                    disabled={!canLoadKeywords || !manualKeywords.trim()}
                    onClick={addManualKeywords}
                  >
                    添加到右侧
                  </Button>
                </div>
              )}
            </div>

            <div className="create-keyword-modal__keyword-pane create-keyword-modal__keyword-pane--selected">
              <div className="create-keyword-modal__pane-toolbar">
                <Typography.Text>
                  已选择 <strong>{selectedKeywords.length}</strong> 个关键词
                  <Typography.Text type="secondary">
                    （最多可添加{maxSelectedKeywords}个）
                  </Typography.Text>
                </Typography.Text>
                <Button type="link" onClick={() => setSelectedKeywords([])}>
                  全部移除
                </Button>
              </div>

              <Table<SelectedKeyword>
                rowKey="id"
                size="small"
                columns={selectedColumns}
                dataSource={selectedKeywords}
                locale={{ emptyText: <Empty description="暂无数据" /> }}
                pagination={false}
                scroll={{ x: 700, y: 430 }}
              />
            </div>
          </div>
        </Card>
      </div>
    </Modal>
  );
}

export default CreateKeywordModal;

import {
  Button,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Radio,
  Select,
  Space,
  Switch,
} from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useEffect } from "react";

import type { AdsCampaign } from "../adsCampaignTypes";

import "./CampaignSettingsModal.css";

type BudgetType = "daily";
type BiddingStrategy = "dynamic" | "fixed";

export interface CampaignSettingsValues {
  name: string;
  startDate: string;
  endDate?: string;
  budgetType: BudgetType;
  dailyBudget: number;
  biddingStrategy: BiddingStrategy;
  placements: {
    searchIngrid: boolean;
    searchCarousel: boolean;
    itemBuybox: boolean;
    itemCarousel: boolean;
  };
  multipliers: {
    buyBox?: number;
    searchIngrid?: number;
    pc?: number;
    app?: number;
    mobile?: number;
  };
}

interface CampaignSettingsModalProps {
  open: boolean;
  campaign: AdsCampaign | null;
  onCancel: () => void;
  onSubmit: (values: CampaignSettingsValues) => void;
}

interface CampaignSettingsFormValues {
  name: string;
  startDate: Dayjs;
  endDate?: Dayjs;
  budgetType: BudgetType;
  dailyBudget: number;
  biddingStrategy: BiddingStrategy;
  placementSearchIngrid: boolean;
  placementSearchCarousel: boolean;
  placementItemBuybox: boolean;
  placementItemCarousel: boolean;
  multiplierBuyBox?: number;
  multiplierSearchIngrid?: number;
  multiplierPc?: number;
  multiplierApp?: number;
  multiplierMobile?: number;
}

const toInitialValues = (
  campaign: AdsCampaign | null,
): CampaignSettingsFormValues => ({
  name: campaign?.name ?? "",
  startDate: campaign?.startDate ? dayjs(campaign.startDate) : dayjs(),
  endDate:
    campaign?.endDate && campaign.endDate !== "--"
      ? dayjs(campaign.endDate)
      : undefined,
  budgetType: "daily",
  dailyBudget: campaign?.dailyBudget ?? 0,
  biddingStrategy: "fixed",
  placementSearchIngrid: true,
  placementSearchCarousel: true,
  placementItemBuybox: true,
  placementItemCarousel: true,
  multiplierBuyBox: undefined,
  multiplierSearchIngrid: 0,
  multiplierPc: undefined,
  multiplierApp: undefined,
  multiplierMobile: undefined,
});

export function CampaignSettingsModal({
  open,
  campaign,
  onCancel,
  onSubmit,
}: CampaignSettingsModalProps) {
  const [form] = Form.useForm<CampaignSettingsFormValues>();

  useEffect(() => {
    if (open) {
      form.setFieldsValue(toInitialValues(campaign));
    } else {
      form.resetFields();
    }
  }, [campaign, form, open]);

  const handleFinish = (values: CampaignSettingsFormValues) => {
    onSubmit({
      name: values.name,
      startDate: values.startDate.format("YYYY-MM-DD"),
      endDate: values.endDate?.format("YYYY-MM-DD"),
      budgetType: values.budgetType,
      dailyBudget: values.dailyBudget,
      biddingStrategy: values.biddingStrategy,
      placements: {
        searchIngrid: values.placementSearchIngrid,
        searchCarousel: values.placementSearchCarousel,
        itemBuybox: values.placementItemBuybox,
        itemCarousel: values.placementItemCarousel,
      },
      multipliers: {
        buyBox: values.multiplierBuyBox,
        searchIngrid: values.multiplierSearchIngrid,
        pc: values.multiplierPc,
        app: values.multiplierApp,
        mobile: values.multiplierMobile,
      },
    });
  };

  return (
    <Modal
      open={open}
      title="调整广告活动设置"
      width={1280}
      centered
      destroyOnClose
      onCancel={onCancel}
      footer={[
        <Button key="cancel" onClick={onCancel}>
          取消
        </Button>,
        <Button key="submit" type="primary" onClick={() => form.submit()}>
          保存
        </Button>,
      ]}
    >
      <Form<CampaignSettingsFormValues>
        form={form}
        layout="vertical"
        className="campaign-settings-modal"
        onFinish={handleFinish}
      >
        <div className="campaign-settings-modal__grid">
          <Form.Item
            className="campaign-settings-modal__field campaign-settings-modal__field--span-2"
            label="广告活动"
            name="name"
            rules={[{ required: true, message: "请输入广告活动名称" }]}
          >
            <Input maxLength={255} showCount placeholder="请输入广告活动名称" />
          </Form.Item>

          <Form.Item
            className="campaign-settings-modal__field"
            label="开始时间"
            name="startDate"
            rules={[{ required: true, message: "请选择开始时间" }]}
          >
            <DatePicker
              className="campaign-settings-modal__full"
              format="YYYY-MM-DD"
            />
          </Form.Item>

          <Form.Item
            className="campaign-settings-modal__field"
            label="结束时间"
            name="endDate"
          >
            <DatePicker
              className="campaign-settings-modal__full"
              format="YYYY-MM-DD"
              placeholder="无结束时间"
            />
          </Form.Item>

          <Form.Item
            className="campaign-settings-modal__field"
            label="预算类型"
            name="budgetType"
            rules={[{ required: true, message: "请选择预算类型" }]}
          >
            <Select options={[{ label: "每日预算", value: "daily" }]} />
          </Form.Item>

          <Form.Item
            className="campaign-settings-modal__field"
            label="每日预算上限"
            name="dailyBudget"
            rules={[{ required: true, message: "请输入每日预算上限" }]}
          >
            <Space.Compact className="campaign-settings-modal__budget">
              <Button disabled>$</Button>
              <InputNumber
                className="campaign-settings-modal__budget-input"
                min={0}
                controls={false}
                placeholder="请输入预算"
              />
            </Space.Compact>
          </Form.Item>
        </div>

        <Form.Item
          className="campaign-settings-modal__field"
          label="竞价策略"
          name="biddingStrategy"
          rules={[{ required: true, message: "请选择竞价策略" }]}
        >
          <Radio.Group className="campaign-settings-modal__radio-group">
            <Space direction="vertical" size={18}>
              <Radio value="dynamic">动态竞价</Radio>
              <Radio value="fixed">固定竞价</Radio>
            </Space>
          </Radio.Group>
        </Form.Item>

        <div className="campaign-settings-modal__section">
          <div className="campaign-settings-modal__section-label">展示位置</div>
          <div className="campaign-settings-modal__switch-row">
            <Form.Item
              name="placementSearchIngrid"
              valuePropName="checked"
              noStyle
            >
              <Switch />
            </Form.Item>
            <span>Search Ingrid</span>

            <Form.Item
              name="placementSearchCarousel"
              valuePropName="checked"
              noStyle
            >
              <Switch />
            </Form.Item>
            <span>Search Carousel</span>

            <Form.Item
              name="placementItemBuybox"
              valuePropName="checked"
              noStyle
            >
              <Switch />
            </Form.Item>
            <span>Item Buybox</span>

            <Form.Item
              name="placementItemCarousel"
              valuePropName="checked"
              noStyle
            >
              <Switch />
            </Form.Item>
            <span>Item Carousel</span>
          </div>
        </div>

        <div className="campaign-settings-modal__section">
          <div className="campaign-settings-modal__section-label">竞价倍数</div>
          <div className="campaign-settings-modal__multiplier-panel">
            <div className="campaign-settings-modal__multiplier-group">
              <div className="campaign-settings-modal__multiplier-title">
                广告位：
              </div>
              <div className="campaign-settings-modal__multiplier-row">
                <div className="campaign-settings-modal__multiplier-item">
                  <span>Buy-Box:</span>
                  <Space.Compact>
                    <Form.Item name="multiplierBuyBox" noStyle>
                      <InputNumber
                        min={0}
                        max={900}
                        controls={false}
                        placeholder="0-900"
                      />
                    </Form.Item>
                    <Button disabled>%</Button>
                  </Space.Compact>
                </div>

                <div className="campaign-settings-modal__multiplier-item">
                  <span>Search Ingrid:</span>
                  <Space.Compact>
                    <Form.Item name="multiplierSearchIngrid" noStyle>
                      <InputNumber
                        min={0}
                        max={900}
                        controls={false}
                        placeholder="0-900"
                      />
                    </Form.Item>
                    <Button disabled>%</Button>
                  </Space.Compact>
                </div>
              </div>
            </div>

            <div className="campaign-settings-modal__multiplier-group">
              <div className="campaign-settings-modal__multiplier-title">
                展示平台：
              </div>
              <div className="campaign-settings-modal__multiplier-row">
                <div className="campaign-settings-modal__multiplier-item">
                  <span>PC端:</span>
                  <Space.Compact>
                    <Form.Item name="multiplierPc" noStyle>
                      <InputNumber
                        min={0}
                        max={900}
                        controls={false}
                        placeholder="0-900"
                      />
                    </Form.Item>
                    <Button disabled>%</Button>
                  </Space.Compact>
                </div>

                <div className="campaign-settings-modal__multiplier-item">
                  <span>App:</span>
                  <Space.Compact>
                    <Form.Item name="multiplierApp" noStyle>
                      <InputNumber
                        min={0}
                        max={900}
                        controls={false}
                        placeholder="0-900"
                      />
                    </Form.Item>
                    <Button disabled>%</Button>
                  </Space.Compact>
                </div>

                <div className="campaign-settings-modal__multiplier-item">
                  <span>移动端:</span>
                  <Space.Compact>
                    <Form.Item name="multiplierMobile" noStyle>
                      <InputNumber
                        min={0}
                        max={900}
                        controls={false}
                        placeholder="0-900"
                      />
                    </Form.Item>
                    <Button disabled>%</Button>
                  </Space.Compact>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Form>
    </Modal>
  );
}

export default CampaignSettingsModal;

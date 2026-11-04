/** WFS 创建货件默认值: per source account, saved with a reason (ProForm). */
import { ProForm, ProFormDigit, ProFormRadio, ProFormSelect } from "@ant-design/pro-components";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Space, Tag, Typography, message } from "antd";
import { useState } from "react";
import { getCreationDefaults, settingsError, updateCreationDefaults, type CreationDefaults } from "../settingsApi";
import SettingsFormLayout from "./SettingsFormLayout";
import SettingsReasonModal, { type ReasonAsk } from "./SettingsReasonModal";
import { formatTime, settingsAccess, type SectionProps } from "./settingsShared";

const transportOptions = [
  { value: "LTL", label: "LTL 零担" },
  { value: "SMALL_PARCEL", label: "小包裹" },
  { value: "FTL", label: "FTL 整车" },
];

export default function CreationDefaultsSection({ page, scope, permissions }: SectionProps) {
  const qc = useQueryClient();
  const { canManage, writeHint } = settingsAccess(page, permissions);
  const defaults = useQuery({ queryKey: ["pmc-settings", scope, "defaults"], queryFn: ({ signal }) => getCreationDefaults(signal), retry: false });
  const [ask, setAsk] = useState<ReasonAsk>();
  const data = defaults.error ? undefined : defaults.data;
  return (
    <SettingsFormLayout page={page} source="数据来自新系统数据库 · 创建货件时预填" loading={defaults.isFetching}>
      {defaults.error && <Alert type="error" showIcon message={settingsError(defaults.error)} action={<Button onClick={() => void defaults.refetch()}>重试</Button>} />}
      {data && (
        <>
          <div className="pmc-settings__summary-row">
            <Typography.Text type="secondary">
              {data.saved ? `已保存 · ${data.updated_by ?? ""} ${formatTime(data.updated_at)}` : "尚未保存，显示的是 8088 默认值"}
            </Typography.Text>
            {!canManage && <Tag>{writeHint}</Tag>}
          </div>
          <ProForm<CreationDefaults>
            key={`${data.source_account_ref}-${data.updated_at ?? "seed"}`}
            layout="horizontal"
            labelCol={{ flex: "140px" }}
            disabled={!canManage}
            initialValues={data}
            submitter={{
              searchConfig: { submitText: "保存默认值" },
              resetButtonProps: false,
              render: (_, dom) => <Space>{dom}</Space>,
              submitButtonProps: { title: writeHint },
            }}
            onFinish={async (values) => {
              setAsk({ title: "修改创建默认值", run: (reason) => updateCreationDefaults({ ...values, reason }) });
              return true;
            }}
          >
            <ProFormSelect name="transport" label="运输方式" width="sm" options={transportOptions} />
            <ProFormDigit name="ship_date_offset" label="发货日 = 今天 +" width="sm" min={0} max={365} fieldProps={{ addonAfter: "天", precision: 0 }} />
            <ProFormDigit name="pallet_boxes" label="每托箱数" width="sm" min={1} max={999} fieldProps={{ precision: 0 }} />
            <ProFormDigit name="mixed_boxes" label="混装箱数" width="sm" min={0} max={999} fieldProps={{ precision: 0 }} />
            <ProFormRadio.Group name="carrier_opt" label="承运商" options={[{ value: "own", label: "自有承运商" }, { value: "wm", label: "Walmart 合作承运商" }]} />
          </ProForm>
        </>
      )}
      <SettingsReasonModal
        ask={ask}
        onClose={() => setAsk(undefined)}
        onSaved={() => { setAsk(undefined); void message.success("已保存"); void qc.invalidateQueries({ queryKey: ["pmc-settings", scope] }); }}
        onError={(e) => void message.error(settingsError(e))}
      />
    </SettingsFormLayout>
  );
}

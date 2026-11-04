/** WFS 店铺设置 (not connected yet, honest empty state) and WFS 通知与口径说明 (static notes). */
import { Card, Descriptions, Empty } from "antd";
import SettingsFormLayout from "./SettingsFormLayout";
import type { SectionProps } from "./settingsShared";

export function StoreSettingsSection({ page }: SectionProps) {
  return (
    <SettingsFormLayout page={page} source="未接入">
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="店铺设置等店铺来源 PR 合入主分支后接入（S1）。此页面暂不请求业务数据，也不提供业务操作。"
      />
    </SettingsFormLayout>
  );
}

export function SettingsNotesSection({ page }: SectionProps) {
  return (
    <SettingsFormLayout page={page} source="说明 · 不请求业务数据">
      <Card size="small">
        <Descriptions
          column={1}
          size="small"
          bordered
          items={[
            { key: "notify", label: "通知", children: "通知未接入：本期只保存「通知对象」文字，不发消息。" },
            { key: "buffer", label: "上架缓冲天数", children: "上架缓冲天数（10 天）引用「自动补货」的规则，这里只读显示，修改请到自动补货设置。" },
            { key: "version", label: "规则版本", children: "规则改动保存为新版本，从生效日起使用；生效日之前的看板与异常仍按旧版本计算。" },
            { key: "log", label: "修改留痕", children: "地区与默认值的修改立即生效，每次修改都要填原因并留修改记录。" },
            { key: "source", label: "外部系统", children: "PMC 设置不调用领星，也不写入 Walmart。" },
          ]}
        />
      </Card>
    </SettingsFormLayout>
  );
}

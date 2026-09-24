/** "更多筛选" drawer: ItemID attribution, quantity / unit-price ranges and WFS readiness. */
import { Button, Drawer, Form, InputNumber, Select, Space } from "antd";
import { useState } from "react";
import {
  emptyMoreFilters,
  purchaseBoardItemIdSourceOptions,
  type PurchaseBoardItemIdSource,
  type PurchaseBoardMoreFilters,
} from "@/pages/pmc/purchase-board/purchaseBoardTypes";

interface PurchaseBoardMoreFiltersDrawerProps {
  open: boolean;
  value: PurchaseBoardMoreFilters;
  onApply: (value: PurchaseBoardMoreFilters) => void;
  onClose: () => void;
}

const wfsOptions = [
  { value: "any", label: "不限" },
  { value: "true", label: "仅 WFS 未就绪" },
  { value: "false", label: "仅 WFS 已就绪" },
];

const toPriceString = (value: number | null) => (
  value === null || Number.isNaN(value) ? undefined : String(value)
);

function PurchaseBoardMoreFiltersDrawer({
  open,
  value,
  onApply,
  onClose,
}: PurchaseBoardMoreFiltersDrawerProps) {
  const [draft, setDraft] = useState<PurchaseBoardMoreFilters>(value);
  const [syncedOpen, setSyncedOpen] = useState(open);

  // Re-seed the draft from the committed value each time the drawer opens (derived state,
  // computed during render rather than in an effect).
  if (open !== syncedOpen) {
    setSyncedOpen(open);
    if (open) setDraft(value);
  }

  const rangeInvalid = (
    (draft.qtyMin !== undefined && draft.qtyMax !== undefined && draft.qtyMin > draft.qtyMax)
    || (
      draft.priceMin !== undefined && draft.priceMax !== undefined
      && draft.priceMin !== "" && draft.priceMax !== ""
      && Number(draft.priceMin) > Number(draft.priceMax)
    )
  );

  return (
    <Drawer
      title="更多筛选"
      open={open}
      width={380}
      onClose={onClose}
      destroyOnHidden
      footer={(
        <Space className="purchase-board__drawer-footer">
          <Button onClick={() => setDraft(emptyMoreFilters)}>清空</Button>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" disabled={rangeInvalid} onClick={() => onApply(draft)}>
            应用
          </Button>
        </Space>
      )}
    >
      <Form layout="vertical">
        <Form.Item label="ItemID 归属">
          <Select<PurchaseBoardItemIdSource[]>
            mode="multiple"
            aria-label="ItemID 归属"
            placeholder="不限"
            allowClear
            value={draft.itemIdSources}
            options={purchaseBoardItemIdSourceOptions}
            onChange={(itemIdSources) => setDraft({ ...draft, itemIdSources })}
          />
        </Form.Item>
        <Form.Item
          label="采购量（分配量）"
          validateStatus={draft.qtyMin !== undefined && draft.qtyMax !== undefined && draft.qtyMin > draft.qtyMax ? "error" : undefined}
          help={draft.qtyMin !== undefined && draft.qtyMax !== undefined && draft.qtyMin > draft.qtyMax ? "最小值不能大于最大值" : undefined}
        >
          <Space>
            <InputNumber
              aria-label="采购量最小值"
              min={0}
              precision={0}
              placeholder="最小"
              value={draft.qtyMin ?? null}
              onChange={(qtyMin) => setDraft({ ...draft, qtyMin: qtyMin ?? undefined })}
            />
            <span>~</span>
            <InputNumber
              aria-label="采购量最大值"
              min={0}
              precision={0}
              placeholder="最大"
              value={draft.qtyMax ?? null}
              onChange={(qtyMax) => setDraft({ ...draft, qtyMax: qtyMax ?? undefined })}
            />
          </Space>
        </Form.Item>
        <Form.Item label="单价">
          <Space>
            <InputNumber
              aria-label="单价最小值"
              min={0}
              placeholder="最小"
              value={draft.priceMin === undefined || draft.priceMin === "" ? null : Number(draft.priceMin)}
              onChange={(priceMin) => setDraft({ ...draft, priceMin: toPriceString(priceMin) })}
            />
            <span>~</span>
            <InputNumber
              aria-label="单价最大值"
              min={0}
              placeholder="最大"
              value={draft.priceMax === undefined || draft.priceMax === "" ? null : Number(draft.priceMax)}
              onChange={(priceMax) => setDraft({ ...draft, priceMax: toPriceString(priceMax) })}
            />
          </Space>
        </Form.Item>
        <Form.Item label="WFS 就绪">
          <Select
            aria-label="WFS 就绪"
            value={draft.wfsNotReady === undefined ? "any" : String(draft.wfsNotReady)}
            options={wfsOptions}
            onChange={(selected) => setDraft({
              ...draft,
              wfsNotReady: selected === "any" ? undefined : selected === "true",
            })}
          />
        </Form.Item>
      </Form>
    </Drawer>
  );
}

export default PurchaseBoardMoreFiltersDrawer;

import { Button, Empty, Modal, Spin } from "antd";
import { useState, type CSSProperties } from "react";
import type { CustomProductTag } from "@/components/product-tags/CustomTagManagerModal";
import "@/components/product-tags/ProductTagAssignmentModal.css";

interface ProductTagAssignmentModalProps {
  open: boolean;
  selectedProductCount: number;
  tags: CustomProductTag[];
  loading?: boolean;
  onCancel: () => void;
  onConfirm: (value: string[]) => void;
}

function ProductTagAssignmentModal({
  open,
  selectedProductCount,
  tags,
  loading = false,
  onCancel,
  onConfirm,
}: ProductTagAssignmentModalProps) {
  const [value, setValue] = useState<string[]>([]);
  const selected = new Set(value);

  const toggleTag = (tagName: string) => {
    setValue((current) => current.includes(tagName)
      ? current.filter((item) => item !== tagName)
      : [...current, tagName]);
  };

  return (
    <Modal
      rootClassName="product-tag-assignment-modal"
      width={520}
      centered
      open={open}
      destroyOnHidden
      title={(
        <div className="product-tag-assignment-modal__heading">
          <div className="product-tag-assignment-modal__title">设置标签</div>
          <div className="product-tag-assignment-modal__subtitle">
            已选择 {selectedProductCount} 个商品
          </div>
        </div>
      )}
      footer={(
        <div className="product-tag-assignment-modal__footer">
          <span className="product-tag-assignment-modal__count" aria-live="polite">
            已选择 <b>{value.length}</b> 个标签
          </span>
          <div className="product-tag-assignment-modal__actions">
            <Button onClick={onCancel}>取消</Button>
            <Button
              type="primary"
              disabled={loading || selectedProductCount === 0 || value.length === 0}
              onClick={() => onConfirm(value)}
            >
              确定
            </Button>
          </div>
        </div>
      )}
      afterOpenChange={(nextOpen) => {
        if (!nextOpen) setValue([]);
      }}
      onCancel={() => {
        setValue([]);
        onCancel();
      }}
    >
      <div className="product-tag-assignment-modal__section-head">
        <span className="product-tag-assignment-modal__section-title">选择标签</span>
        <span className="product-tag-assignment-modal__section-hint">支持多选</span>
      </div>
      <Spin spinning={loading}>
        <div className="product-tag-assignment-modal__scroller">
          {tags.length > 0 ? (
            <div className="product-tag-assignment-modal__grid">
              {tags.map((tag) => {
                const isSelected = selected.has(tag.name);
                return (
                  <button
                    key={tag.id}
                    type="button"
                    className={[
                      "product-tag-assignment-modal__option",
                      isSelected ? "product-tag-assignment-modal__option--selected" : "",
                    ].filter(Boolean).join(" ")}
                    style={{ "--product-tag-color": tag.color } as CSSProperties}
                    aria-pressed={isSelected}
                    onClick={() => toggleTag(tag.name)}
                  >
                    <span className="product-tag-assignment-modal__dot" aria-hidden="true" />
                    <span className="product-tag-assignment-modal__label">{tag.name}</span>
                  </button>
                );
              })}
            </div>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可用标签" />
          )}
        </div>
      </Spin>
    </Modal>
  );
}

export default ProductTagAssignmentModal;

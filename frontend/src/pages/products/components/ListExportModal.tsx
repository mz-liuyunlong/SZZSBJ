import { Button, Checkbox, Modal, Space, Typography } from "antd";
import { useEffect, useMemo, useState, type CSSProperties } from "react";

export interface ListExportColumnField {
  key: string;
  label: string;
}

export interface ListExportColumnGroup {
  title: string;
  fields: ListExportColumnField[];
}

interface ListExportModalProps {
  open: boolean;
  title?: string;
  subtitle?: string;
  columnGroups: ListExportColumnGroup[];
  defaultSelectedColumnKeys?: string[];
  exporting?: boolean;
  onClose: () => void;
  onExport: (columnKeys: string[]) => void | Promise<void>;
}

const modalStyles: {
  panel: CSSProperties;
  fieldGrid: CSSProperties;
  headerActions: CSSProperties;
  headerActionButton: CSSProperties;
  clearActionButton: CSSProperties;
} = {
  panel: {
    border: "1px solid #e8edf5",
    borderRadius: 12,
    background: "#fbfcfe",
  },
  fieldGrid: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  headerActions: {
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  headerActionButton: {
    height: 30,
    padding: "0 12px",
    borderRadius: 8,
    border: "1px solid #d9e2f2",
    background: "#ffffff",
    color: "#4e5969",
    fontSize: 13,
    fontWeight: 500,
    boxShadow: "none",
  },
  clearActionButton: {
    border: "1px solid #b7d4ff",
    background: "#f7fbff",
    color: "#1677ff",
  },
};

function ListExportModal({
  open,
  title = "导出数据",
  subtitle = "配置导出字段",
  columnGroups,
  defaultSelectedColumnKeys,
  exporting = false,
  onClose,
  onExport,
}: ListExportModalProps) {
  const allColumnKeys = useMemo(
    () => columnGroups.flatMap((group) => group.fields.map((field) => field.key)),
    [columnGroups],
  );

  const defaultKeys = useMemo(
    () => (
      defaultSelectedColumnKeys && defaultSelectedColumnKeys.length > 0
        ? defaultSelectedColumnKeys
        : allColumnKeys
    ),
    [allColumnKeys, defaultSelectedColumnKeys],
  );

  const [selectedColumns, setSelectedColumns] = useState<string[]>(defaultKeys);

  useEffect(() => {
    if (!open) return;
    queueMicrotask(() => setSelectedColumns(defaultKeys));
  }, [defaultKeys, open]);

  const selectedColumnSet = useMemo(() => new Set(selectedColumns), [selectedColumns]);
  const selectedCount = selectedColumns.length;
  const exportDisabled = exporting || selectedCount === 0;

  const toggleGroup = (group: ListExportColumnGroup, checked: boolean) => {
    const groupKeys = group.fields.map((field) => field.key);
    setSelectedColumns((current) => {
      const next = new Set(current);

      for (const key of groupKeys) {
        if (checked) next.add(key);
        else next.delete(key);
      }

      return allColumnKeys.filter((key) => next.has(key));
    });
  };

  const toggleColumn = (key: string, checked: boolean) => {
    setSelectedColumns((current) => {
      const next = new Set(current);

      if (checked) next.add(key);
      else next.delete(key);

      return allColumnKeys.filter((columnKey) => next.has(columnKey));
    });
  };

  return (
    <Modal
      title={(
        <Space size={12} align="baseline">
          <Typography.Text style={{ fontSize: 16, fontWeight: 700 }}>
            {title}
          </Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            {subtitle}
          </Typography.Text>
        </Space>
      )}
      open={open}
      width={1060}
      footer={null}
      centered
      onCancel={onClose}
      styles={{
        body: {
          padding: 18,
          background: "#fff",
        },
      }}
    >
      <Space direction="vertical" size={18} style={{ width: "100%" }}>
        <div style={{ ...modalStyles.panel, overflow: "hidden" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "14px 16px",
              borderBottom: "1px solid #eef2f7",
            }}
          >
            <Space size={10} align="baseline">
              <Typography.Text style={{ fontSize: 16, fontWeight: 700 }}>
                表头选择
              </Typography.Text>
            </Space>

            <div style={modalStyles.headerActions}>
              <Button
                type="default"
                size="small"
                disabled={exporting}
                onClick={() => {
                  setSelectedColumns(
                    selectedCount === allColumnKeys.length ? [] : allColumnKeys,
                  );
                }}
                style={{
                  ...modalStyles.headerActionButton,
                  ...(selectedCount === allColumnKeys.length
                    ? {}
                    : modalStyles.clearActionButton),
                }}
              >
                {selectedCount === allColumnKeys.length ? "取消全选" : "全选所有"}
              </Button>
            </div>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
            }}
          >
            {columnGroups.map((group, index) => {
              const groupKeys = group.fields.map((field) => field.key);
              const checkedCount = groupKeys.filter((key) => selectedColumnSet.has(key)).length;
              const checked = checkedCount === groupKeys.length;
              const indeterminate = checkedCount > 0 && checkedCount < groupKeys.length;

              return (
                <div
                  key={group.title}
                  style={{
                    minHeight: 126,
                    padding: "14px 16px",
                    borderRight: index % 2 === 0 ? "1px solid #f2f4f8" : "none",
                    borderBottom: index < columnGroups.length - 2 ? "1px solid #f2f4f8" : "none",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "flex-start",
                      alignItems: "center",
                      marginBottom: 10,
                    }}
                  >
                    <Space size={8}>
                      <Checkbox
                        checked={checked}
                        indeterminate={indeterminate}
                        disabled={exporting}
                        onChange={(event) => toggleGroup(group, event.target.checked)}
                      />
                      <Typography.Text strong style={{ fontSize: 17 }}>
                        {group.title}
                      </Typography.Text>
                      <Typography.Text type="secondary">
                        {checkedCount}/{group.fields.length}
                      </Typography.Text>
                    </Space>
                  </div>

                  <div style={modalStyles.fieldGrid}>
                    {group.fields.map((field) => {
                      const active = selectedColumnSet.has(field.key);

                      return (
                        <Checkbox
                          key={field.key}
                          checked={active}
                          disabled={exporting}
                          onChange={(event) => toggleColumn(field.key, event.target.checked)}
                          style={{
                            minHeight: 32,
                            width: "fit-content",
                            padding: "5px 9px",
                            border: "1px solid transparent",
                            borderRadius: 7,
                            background: active ? "#f9fbff" : "transparent",
                            color: active ? "#243044" : "#52627a",
                            fontWeight: 500,
                            display: "inline-flex",
                            alignItems: "center",
                            lineHeight: "20px",
                            whiteSpace: "nowrap",
                            boxShadow: "none",
                          }}
                        >
                          {field.label}
                        </Checkbox>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </Space>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          margin: "18px -18px -18px",
          padding: "12px 18px",
          borderTop: "1px solid #eef2f7",
          background: "#fff",
        }}
      >
        <Space size={6}>
          <Typography.Text type="secondary">已选</Typography.Text>
          <Typography.Text style={{ color: "#1677ff", fontSize: 16, fontWeight: 700 }}>
            {selectedCount}
          </Typography.Text>
          <Typography.Text type="secondary">项</Typography.Text>
        </Space>

        <Space size={12}>
          <Button disabled={exporting} onClick={onClose}>
            取消
          </Button>
          <Button
            type="primary"
            loading={exporting}
            disabled={exportDisabled}
            onClick={() => void onExport(selectedColumns)}
          >
            导出
          </Button>
        </Space>
      </div>
    </Modal>
  );
}

export default ListExportModal;

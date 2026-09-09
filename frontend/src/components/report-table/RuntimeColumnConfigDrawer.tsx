/** Edits visible report columns in memory; it never persists templates or user preferences. */
import {
  AppstoreOutlined,
  ArrowDownOutlined,
  ArrowUpOutlined,
  DatabaseOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { Button, Checkbox, Drawer, Input, Select, Space, Tag, Typography } from "antd";
import { useMemo, useState, type DragEvent } from "react";
import "@/components/report-table/reportTable.css";

export interface RuntimeColumnField {
  key: string;
  title: string;
}

export interface RuntimeColumnGroup {
  title: string;
  fields: RuntimeColumnField[];
}

interface RuntimeColumnConfigDrawerProps {
  open: boolean;
  groups: RuntimeColumnGroup[];
  fixedKeys: string[];
  defaultKeys: string[];
  appliedKeys: string[];
  onApply: (keys: string[]) => void;
  onClose: () => void;
  onSaveTemplate: () => void;
}

const withFixedColumns = (keys: string[], fixedKeys: string[]) => [
  ...fixedKeys,
  ...keys.filter((key) => !fixedKeys.includes(key)),
];

function RuntimeColumnConfigDrawer({
  open,
  groups,
  fixedKeys,
  defaultKeys,
  appliedKeys,
  onApply,
  onClose,
  onSaveTemplate,
}: RuntimeColumnConfigDrawerProps) {
  const [search, setSearch] = useState("");
  const [draftKeys, setDraftKeys] = useState(() => withFixedColumns(appliedKeys, fixedKeys));
  const [draggedKey, setDraggedKey] = useState<string>();
  const fields = useMemo(() => groups.flatMap((group) => group.fields), [groups]);
  const allKeys = useMemo(() => fields.map((field) => field.key), [fields]);
  const selectedFields = draftKeys.flatMap((key) => {
    const field = fields.find((item) => item.key === key);
    return field ? [field] : [];
  });
  const visibleGroups = groups
    .map((group) => ({
      ...group,
      fields: group.fields.filter((field) => field.title.includes(search.trim())),
    }))
    .filter((group) => group.fields.length > 0);

  const closeDrawer = () => {
    setDraftKeys(withFixedColumns(appliedKeys, fixedKeys));
    setSearch("");
    setDraggedKey(undefined);
    onClose();
  };

  const toggleColumn = (key: string, checked: boolean) => {
    if (fixedKeys.includes(key)) return;
    setDraftKeys((current) => withFixedColumns(
      checked ? [...current, key] : current.filter((item) => item !== key),
      fixedKeys,
    ));
  };

  const moveColumn = (key: string, offset: -1 | 1) => {
    if (fixedKeys.includes(key)) return;
    setDraftKeys((current) => {
      const from = current.indexOf(key);
      const to = from + offset;
      if (from < 0 || to < fixedKeys.length || to >= current.length) return current;
      const next = [...current];
      [next[from], next[to]] = [next[to], next[from]];
      return next;
    });
  };

  const dropColumn = (targetKey: string, event: DragEvent<HTMLLIElement>) => {
    event.preventDefault();
    if (!draggedKey || draggedKey === targetKey || fixedKeys.includes(targetKey)) return;
    setDraftKeys((current) => {
      const next = current.filter((key) => key !== draggedKey);
      next.splice(next.indexOf(targetKey), 0, draggedKey);
      return withFixedColumns(next, fixedKeys);
    });
    setDraggedKey(undefined);
  };

  return (
    <Drawer
      rootClassName="runtime-column-config"
      title="列配置"
      placement="right"
      size="large"
      open={open}
      destroyOnHidden
      footer={(
        <div className="runtime-column-config__footer">
          <Button onClick={() => setDraftKeys(withFixedColumns(defaultKeys, fixedKeys))}>恢复默认</Button>
          <Space>
            <Button onClick={closeDrawer}>取消</Button>
            <Button
              type="primary"
              onClick={() => {
                const nextKeys = withFixedColumns(draftKeys, fixedKeys);
                onApply(nextKeys);
                setDraftKeys(nextKeys);
                setSearch("");
                setDraggedKey(undefined);
                onClose();
              }}
            >
              保存并应用
            </Button>
          </Space>
        </div>
      )}
      onClose={closeDrawer}
    >
      <Typography.Paragraph className="runtime-column-config__description" type="secondary">
        选择并配置表格中显示的字段，支持调整字段顺序和固定列。
      </Typography.Paragraph>
      <div className="runtime-column-config__tools">
        <Typography.Text strong>选择模板</Typography.Text>
        <Select aria-label="选择模板" disabled placeholder="选择模板" options={[]} />
        <Button onClick={onSaveTemplate}>保存为新模板</Button>
      </div>
      <Input
        allowClear
        className="runtime-column-config__search"
        aria-label="搜索字段"
        placeholder="搜索字段（支持字段名称模糊搜索）"
        prefix={<SearchOutlined aria-hidden="true" />}
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      <div className="runtime-column-config__editor">
        <section className="runtime-column-config__panel runtime-column-config__available" aria-label="可选字段">
          <div className="runtime-column-config__panel-header">
            <Typography.Text strong>
              <AppstoreOutlined aria-hidden="true" /> 全部字段
            </Typography.Text>
            <Typography.Text type="secondary">共 {fields.length} 项</Typography.Text>
          </div>
          <Space className="runtime-column-config__select-actions" size={8}>
            <Button size="small" onClick={() => setDraftKeys(withFixedColumns(allKeys, fixedKeys))}>全选</Button>
            <Button size="small" onClick={() => setDraftKeys(fixedKeys)}>取消全选</Button>
          </Space>
          {visibleGroups.map((group) => (
            <div key={group.title} className="runtime-column-config__group">
              <Typography.Text strong>{group.title}</Typography.Text>
              <div className="runtime-column-config__checks">
                {group.fields.map((field) => (
                  <Checkbox
                    key={field.key}
                    aria-label={`显示列：${field.title}`}
                    checked={draftKeys.includes(field.key)}
                    disabled={fixedKeys.includes(field.key)}
                    onChange={(event) => toggleColumn(field.key, event.target.checked)}
                  >
                    {field.title}
                  </Checkbox>
                ))}
              </div>
            </div>
          ))}
        </section>
        <section className="runtime-column-config__panel" aria-labelledby="selected-columns-title">
          <div className="runtime-column-config__panel-header">
            <Typography.Text id="selected-columns-title" strong>
              <DatabaseOutlined aria-hidden="true" /> 已选字段
            </Typography.Text>
            <Typography.Text type="secondary">共 {selectedFields.length} 项</Typography.Text>
          </div>
          <ol className="runtime-column-config__selected">
            {selectedFields.map((field, index) => (
              <li
                key={field.key}
                draggable={!fixedKeys.includes(field.key)}
                aria-label={fixedKeys.includes(field.key)
                  ? `固定字段：${field.title}`
                  : `拖动字段：${field.title}`}
                onDragStart={() => setDraggedKey(field.key)}
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => dropColumn(field.key, event)}
                onDragEnd={() => setDraggedKey(undefined)}
              >
                <span className="runtime-column-config__selected-name">
                  <span className="runtime-column-config__selected-index">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  {field.title}
                </span>
                {fixedKeys.includes(field.key) ? (
                  <Tag>固定</Tag>
                ) : (
                  <Space size={0}>
                    <Button
                      type="text"
                      size="small"
                      disabled={index === fixedKeys.length}
                      aria-label={`上移字段：${field.title}`}
                      icon={<ArrowUpOutlined aria-hidden="true" />}
                      onClick={() => moveColumn(field.key, -1)}
                    />
                    <Button
                      type="text"
                      size="small"
                      disabled={index === selectedFields.length - 1}
                      aria-label={`下移字段：${field.title}`}
                      icon={<ArrowDownOutlined aria-hidden="true" />}
                      onClick={() => moveColumn(field.key, 1)}
                    />
                  </Space>
                )}
              </li>
            ))}
          </ol>
        </section>
      </div>
    </Drawer>
  );
}

export default RuntimeColumnConfigDrawer;

/** Edits explicit role data ranges without relying on preview-only configuration. */
import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { Alert, Button, Empty, Input, Select, Spin, Tag, Typography } from "antd";
import type {
  RoleDataScopeEntry,
  RoleDataScopeType,
} from "@/pages/settings/roleManagementTypes";

const scopeTypeOptions: { value: RoleDataScopeType; label: string }[] = [
  { value: "source_account", label: "数据源账号" },
  { value: "store", label: "店铺" },
  { value: "owner", label: "负责人" },
  { value: "sku", label: "SKU" },
  { value: "product", label: "产品" },
];

interface RoleDataScopeEditorProps {
  items: RoleDataScopeEntry[];
  loading: boolean;
  disabled: boolean;
  subjectLabel?: string;
  onChange: (items: RoleDataScopeEntry[]) => void;
}

function RoleDataScopeEditor({
  items,
  loading,
  disabled,
  subjectLabel = "角色",
  onChange,
}: RoleDataScopeEditorProps) {
  const updateItem = (index: number, next: Partial<RoleDataScopeEntry>) => {
    onChange(items.map((item, itemIndex) => (
      itemIndex === index ? { ...item, ...next } : item
    )));
  };

  const removeItem = (index: number) => {
    onChange(items.filter((_, itemIndex) => itemIndex !== index));
  };

  const addItem = () => {
    onChange([...items, { scopeType: "source_account", scopeValue: "" }]);
  };

  return (
    <div className="role-management__permission-scroll role-management__data-scope">
      <Alert
        type="info"
        showIcon
        message="数据权限与页面、功能权限相互独立"
        description="每行代表一个可访问范围；同类型多值按并集处理。值为 * 表示该类型全部范围。当前业务接口严格执行数据源账号范围；其他维度仅登记，接入服务端过滤前不得视为已生效隔离。"
      />
      <Spin spinning={loading}>
        <div className="role-management__data-scope-toolbar">
          <div>
            <Typography.Text strong>{subjectLabel}数据范围</Typography.Text>
            <Typography.Text type="secondary">
              未配置有效数据源账号范围时，受保护业务接口将拒绝访问。
            </Typography.Text>
          </div>
          <Button
            type="dashed"
            icon={<PlusOutlined />}
            disabled={disabled}
            onClick={addItem}
          >
            增加范围
          </Button>
        </div>
        {items.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={`当前${subjectLabel}没有单独配置的数据范围`}
          />
        ) : (
          <div className="role-management__data-scope-list">
            {items.map((item, index) => (
              <div
                className="role-management__data-scope-row"
                key={`${item.scopeType}-${index}`}
              >
                <Select
                  aria-label={`第${index + 1}条数据范围类型`}
                  value={item.scopeType}
                  options={scopeTypeOptions}
                  disabled={disabled}
                  onChange={(scopeType) => updateItem(index, { scopeType })}
                />
                <Input
                  aria-label={`第${index + 1}条数据范围值`}
                  value={item.scopeValue}
                  disabled={disabled}
                  placeholder="输入真实范围值；* 表示全部"
                  onChange={(event) => updateItem(index, {
                    scopeValue: event.target.value,
                  })}
                />
                {item.scopeValue.trim() === "*" && <Tag color="gold">全部范围</Tag>}
                <Button
                  type="text"
                  danger
                  aria-label={`删除第${index + 1}条数据范围`}
                  icon={<DeleteOutlined />}
                  disabled={disabled}
                  onClick={() => removeItem(index)}
                />
              </div>
            ))}
          </div>
        )}
      </Spin>
    </div>
  );
}

export default RoleDataScopeEditor;

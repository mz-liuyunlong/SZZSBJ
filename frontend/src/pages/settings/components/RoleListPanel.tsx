/** Role navigation panel with local search. */
import { Button, Input, Tag, Typography } from "antd";
import type { RoleManagementRow } from "@/pages/settings/roleManagementTypes";

interface RoleListPanelProps {
  roles: RoleManagementRow[];
  activeRoleId: string;
  keyword: string;
  onKeywordChange: (keyword: string) => void;
  onSelect: (roleId: string) => void;
  onAdd: () => void;
}

function RoleListPanel({
  roles,
  activeRoleId,
  keyword,
  onKeywordChange,
  onSelect,
  onAdd,
}: RoleListPanelProps) {
  const visibleRoles = roles.filter((role) => role.name.includes(keyword.trim()));

  return (
    <section className="role-management__role-panel" aria-label="角色列表">
      <div className="role-management__role-head">
        <Typography.Text strong>角色</Typography.Text>
        <Button size="small" aria-label="增加角色" onClick={onAdd}>+</Button>
      </div>
      <div className="role-management__role-search">
        <Input
          allowClear
          aria-label="搜索角色"
          placeholder="搜索角色"
          value={keyword}
          onChange={(event) => onKeywordChange(event.target.value)}
        />
      </div>
      <div className="role-management__role-list">
        {visibleRoles.map((role) => (
          <button
            key={role.id}
            type="button"
            className={role.id === activeRoleId
              ? "role-management__role-item role-management__role-item--active"
              : "role-management__role-item"}
            onClick={() => onSelect(role.id)}
          >
            <span>{role.name}</span>
            <Tag>{role.preset ? "预设" : "自定义"}</Tag>
          </button>
        ))}
      </div>
    </section>
  );
}

export default RoleListPanel;

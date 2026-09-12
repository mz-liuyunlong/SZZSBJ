/** Compact toolbar for user account filtering. */
import { Button, Input, Select } from "antd";
import ResetButton from "@/components/report-table/ResetButton";
import {
  userRoleOptions,
  userStatusOptions,
  type UserManagementFilters,
  type UserRoleName,
  type UserStatus,
} from "@/pages/settings/userManagementTypes";

interface UserManagementToolbarProps {
  filters: UserManagementFilters;
  onChange: (filters: UserManagementFilters) => void;
  onReset: () => void;
}

function UserManagementToolbar({ filters, onChange, onReset }: UserManagementToolbarProps) {
  const update = <Key extends keyof UserManagementFilters>(
    key: Key,
    value: UserManagementFilters[Key],
  ) => onChange({ ...filters, [key]: value });

  return (
    <div className="user-management__toolbar" role="search" aria-label="用户管理筛选">
      <Select
        className="report-filter-select"
        classNames={{ popup: { root: "report-filter-select-dropdown" } }}
        allowClear
        aria-label="状态筛选"
        placeholder="全部状态"
        value={filters.status}
        options={userStatusOptions.map((value) => ({ value, label: value }))}
        onChange={(value) => update("status", value as UserStatus | undefined)}
      />
      <Select
        className="report-filter-select"
        classNames={{ popup: { root: "report-filter-select-dropdown" } }}
        allowClear
        aria-label="角色筛选"
        placeholder="全部角色"
        value={filters.role}
        options={userRoleOptions.map((value) => ({ value, label: value }))}
        onChange={(value) => update("role", value as UserRoleName | undefined)}
      />
      <Input
        allowClear
        className="user-management__search"
        aria-label="搜索用户名、真实姓名或手机号"
        placeholder="搜索用户名 / 真实姓名 / 手机号"
        value={filters.keyword}
        onChange={(event) => update("keyword", event.target.value)}
        onPressEnter={() => onChange(filters)}
      />
      <Button type="primary" ghost onClick={() => onChange(filters)}>搜索</Button>
      <ResetButton onClick={onReset} />
    </div>
  );
}

export default UserManagementToolbar;

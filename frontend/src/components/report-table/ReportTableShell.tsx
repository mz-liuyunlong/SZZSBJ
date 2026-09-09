/** Provides the shared fixed-header, scrollable-body, fixed-footer frame for report tables. */
import { DownOutlined } from "@ant-design/icons";
import { Button, Dropdown, Typography, type MenuProps } from "antd";
import type { ReactNode } from "react";
import "@/components/report-table/reportTable.css";

interface ReportTableShellProps {
  label: string;
  className?: string;
  children: ReactNode;
}

function ReportTableShell({ label, className, children }: ReportTableShellProps) {
  return (
    <section
      className={["report-table-shell", className].filter(Boolean).join(" ")}
      aria-label={label}
    >
      {children}
    </section>
  );
}

export interface ReportTableBulkAction {
  key: string;
  label: ReactNode;
  danger?: boolean;
  disabled?: boolean;
  onClick: () => void;
}

export function ReportTableSelectionBar({
  selectedCount,
  actions,
}: {
  selectedCount: number;
  actions: ReportTableBulkAction[];
}) {
  if (selectedCount === 0) return null;

  const items: MenuProps["items"] = actions.map(({ key, label, danger, disabled }) => ({
    key,
    label,
    danger,
    disabled,
  }));

  return (
    <div className="report-table-selection-bar">
      <Typography.Text strong>已选择 {selectedCount} 项</Typography.Text>
      <Dropdown
        trigger={["click"]}
        placement="topLeft"
        menu={{
          items,
          onClick: ({ key }) => actions.find((action) => action.key === key)?.onClick(),
        }}
      >
        <Button size="small" disabled={actions.length === 0}>
          批量操作 <DownOutlined aria-hidden="true" />
        </Button>
      </Dropdown>
    </div>
  );
}

export default ReportTableShell;

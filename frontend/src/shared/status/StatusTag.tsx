import { Tag } from "antd";
import type { ReactNode } from "react";
import {
  resolveStatusTag,
  type StatusSemantic,
} from "@/shared/status/statusTagConfig";

export interface StatusTagProps {
  value?: string | boolean | null;
  label?: ReactNode;
  color?: string;
  semantic?: StatusSemantic;
  bordered?: boolean;
  className?: string;
}

function StatusTag({
  value,
  label,
  color,
  semantic,
  bordered = false,
  className,
}: StatusTagProps) {
  const resolved = resolveStatusTag({ value, label, color, semantic });

  return (
    <Tag color={resolved.color} bordered={bordered} className={className}>
      {resolved.label}
    </Tag>
  );
}

export default StatusTag;

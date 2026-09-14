import type { ReactNode } from "react";

export type StatusSemantic =
  | "success"
  | "processing"
  | "warning"
  | "error"
  | "default"
  | "disabled";

export interface StatusTagPreset {
  label: ReactNode;
  color: string;
  semantic?: StatusSemantic;
}

export const statusTagPresets: Record<string, StatusTagPreset> = {
  ready: { label: "已就绪", color: "green", semantic: "success" },
  enabled: { label: "已启用", color: "green", semantic: "success" },
  active: { label: "正常", color: "green", semantic: "success" },
  success: { label: "成功", color: "green", semantic: "success" },
  completed: { label: "已完成", color: "green", semantic: "success" },

  building: { label: "建设中", color: "blue", semantic: "processing" },
  running: { label: "运行中", color: "blue", semantic: "processing" },
  syncing: { label: "同步中", color: "blue", semantic: "processing" },
  pending: { label: "待处理", color: "gold", semantic: "warning" },
  waiting: { label: "等待中", color: "gold", semantic: "warning" },

  warning: { label: "预警", color: "orange", semantic: "warning" },
  abnormal: { label: "异常", color: "orange", semantic: "warning" },
  failed: { label: "失败", color: "red", semantic: "error" },
  error: { label: "错误", color: "red", semantic: "error" },

  disabled: { label: "已禁用", color: "default", semantic: "disabled" },
  hidden: { label: "隐藏", color: "default", semantic: "disabled" },
  planned: { label: "待建设", color: "default", semantic: "default" },
};

const semanticColorMap: Record<StatusSemantic, string> = {
  success: "green",
  processing: "blue",
  warning: "orange",
  error: "red",
  default: "default",
  disabled: "default",
};

export interface ResolveStatusTagOptions {
  value?: string | boolean | null;
  label?: ReactNode;
  color?: string;
  semantic?: StatusSemantic;
}

export function resolveStatusTag({
  value,
  label,
  color,
  semantic,
}: ResolveStatusTagOptions): StatusTagPreset {
  if (typeof value === "boolean") {
    return value
      ? { label: label ?? "是", color: color ?? "green", semantic: semantic ?? "success" }
      : { label: label ?? "否", color: color ?? "default", semantic: semantic ?? "disabled" };
  }

  const key = String(value ?? "").trim();
  const preset = statusTagPresets[key];

  if (preset) {
    return {
      label: label ?? preset.label,
      color: color ?? preset.color,
      semantic: semantic ?? preset.semantic,
    };
  }

  return {
    label: label ?? (key || "-"),
    color: color ?? semanticColorMap[semantic ?? "default"],
    semantic: semantic ?? "default",
  };
}

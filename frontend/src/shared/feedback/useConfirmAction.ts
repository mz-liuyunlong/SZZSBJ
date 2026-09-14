import type { ReactNode } from "react";
import useAppFeedback from "@/shared/feedback/useAppFeedback";

export interface ConfirmActionOptions {
  title: ReactNode;
  content?: ReactNode;
  danger?: boolean;
  confirmText?: ReactNode;
  cancelText?: ReactNode;
  onConfirm?: () => void | Promise<void>;
  onCancel?: () => void;
}

export function useConfirmAction() {
  const feedback = useAppFeedback();

  return ({
    title,
    content,
    danger = false,
    confirmText,
    cancelText,
    onConfirm,
    onCancel,
  }: ConfirmActionOptions) => feedback.confirmAction({
    title,
    content,
    danger,
    confirmText: confirmText ?? (danger ? "确认执行" : "确认"),
    cancelText: cancelText ?? "取消",
    onOk: onConfirm,
    onCancel,
  });
}

export default useConfirmAction;

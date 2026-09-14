import type { ReactNode } from "react";
import { Button, type ButtonProps } from "antd";
import useConfirmAction, {
  type ConfirmActionOptions,
} from "@/shared/feedback/useConfirmAction";

export interface ConfirmActionButtonProps
  extends Omit<ButtonProps, "title" | "content" | "onClick" | "danger" | "children">,
    ConfirmActionOptions {
  children: ReactNode;
}

export function ConfirmActionButton({
  title,
  content,
  danger = false,
  confirmText,
  cancelText,
  onConfirm,
  onCancel,
  children,
  ...buttonProps
}: ConfirmActionButtonProps) {
  const confirmAction = useConfirmAction();

  return (
    <Button
      {...buttonProps}
      danger={danger}
      onClick={() => confirmAction({
        title,
        content,
        danger,
        confirmText,
        cancelText,
        onConfirm,
        onCancel,
      })}
    >
      {children}
    </Button>
  );
}

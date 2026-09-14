import { Button, Tooltip, type ButtonProps, type TooltipProps } from "antd";
import type { ReactNode } from "react";

export interface DisabledReasonProps {
  disabled?: boolean;
  reason?: ReactNode;
  placement?: TooltipProps["placement"];
  children: ReactNode;
}

function DisabledReason({
  disabled = true,
  reason,
  placement = "top",
  children,
}: DisabledReasonProps) {
  if (!disabled || !reason) return children;

  return (
    <Tooltip title={reason} placement={placement}>
      <span style={{ display: "inline-flex", cursor: "not-allowed" }}>
        {children}
      </span>
    </Tooltip>
  );
}

export interface PermissionButtonProps extends ButtonProps {
  disabledReason?: ReactNode;
  tooltipPlacement?: TooltipProps["placement"];
}

export function PermissionButton({
  disabled,
  disabledReason,
  tooltipPlacement,
  children,
  ...buttonProps
}: PermissionButtonProps) {
  const shouldDisable = disabled || Boolean(disabledReason);

  const button = (
    <Button {...buttonProps} disabled={shouldDisable}>
      {children}
    </Button>
  );

  return (
    <DisabledReason
      disabled={shouldDisable}
      reason={disabledReason}
      placement={tooltipPlacement}
    >
      {button}
    </DisabledReason>
  );
}

export default DisabledReason;

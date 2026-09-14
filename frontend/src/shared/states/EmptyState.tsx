import { Button, Empty, Space } from "antd";
import type { ButtonProps } from "antd";
import type { ReactNode } from "react";
import "@/shared/states/EmptyState.css";

export interface EmptyStateAction {
  key: string;
  label: ReactNode;
  type?: ButtonProps["type"];
  disabled?: boolean;
  onClick?: () => void;
}

export interface EmptyStateProps {
  title?: ReactNode;
  description?: ReactNode;
  image?: ReactNode;
  compact?: boolean;
  actions?: EmptyStateAction[];
}

function EmptyState({
  title = "暂无数据",
  description = "当前没有可展示的内容。",
  image = Empty.PRESENTED_IMAGE_SIMPLE,
  compact = false,
  actions = [],
}: EmptyStateProps) {
  return (
    <div className={compact ? "app-empty-state app-empty-state--compact" : "app-empty-state"}>
      <div className="app-empty-state__content">
        <Empty
          image={image}
          description={(
            <span className="app-empty-state__text">
              <span className="app-empty-state__title">{title}</span>
              {description && (
                <span className="app-empty-state__description">{description}</span>
              )}
            </span>
          )}
        />
        {actions.length > 0 && (
          <Space size={8} wrap>
            {actions.map((action) => (
              <Button
                key={action.key}
                type={action.type}
                disabled={action.disabled}
                onClick={action.onClick}
              >
                {action.label}
              </Button>
            ))}
          </Space>
        )}
      </div>
    </div>
  );
}

export default EmptyState;

import { createContext, type ReactNode } from "react";
import { message, Modal } from "antd";

type MessageApi = ReturnType<typeof message.useMessage>[0];
type ModalApi = ReturnType<typeof Modal.useModal>[0];
type ConfirmConfig = Parameters<ModalApi["confirm"]>[0];

export interface ConfirmActionConfig extends Omit<ConfirmConfig, "okText" | "cancelText"> {
  danger?: boolean;
  confirmText?: ReactNode;
  cancelText?: ReactNode;
}

export interface AppFeedbackContextValue {
  message: MessageApi;
  modal: ModalApi;
  success: (content: ReactNode) => void;
  info: (content: ReactNode) => void;
  warning: (content: ReactNode) => void;
  error: (content: ReactNode) => void;
  confirmAction: (config: ConfirmActionConfig) => ReturnType<ModalApi["confirm"]>;
}

export const AppFeedbackContext = createContext<AppFeedbackContextValue | null>(null);

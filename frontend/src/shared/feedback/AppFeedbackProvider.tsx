import { useMemo, type ReactNode } from "react";
import { message, Modal } from "antd";
import {
  AppFeedbackContext,
  type AppFeedbackContextValue,
} from "@/shared/feedback/AppFeedbackContext";

interface AppFeedbackProviderProps {
  children: ReactNode;
}

function AppFeedbackProvider({ children }: AppFeedbackProviderProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [modalApi, modalContextHolder] = Modal.useModal();

  const value = useMemo<AppFeedbackContextValue>(() => ({
    message: messageApi,
    modal: modalApi,
    success: (content) => {
      void messageApi.success(content);
    },
    info: (content) => {
      void messageApi.info(content);
    },
    warning: (content) => {
      void messageApi.warning(content);
    },
    error: (content) => {
      void messageApi.error(content);
    },
    confirmAction: ({
      danger = false,
      confirmText,
      cancelText,
      okButtonProps,
      centered = true,
      ...config
    }) => modalApi.confirm({
      centered,
      okText: confirmText ?? "确认",
      cancelText: cancelText ?? "取消",
      okButtonProps: {
        ...okButtonProps,
        danger: danger || okButtonProps?.danger,
      },
      ...config,
    }),
  }), [messageApi, modalApi]);

  return (
    <AppFeedbackContext.Provider value={value}>
      {messageContextHolder}
      {modalContextHolder}
      {children}
    </AppFeedbackContext.Provider>
  );
}

export default AppFeedbackProvider;

/** Fictional notifications for the local UI shell; no production or customer data is represented. */
export interface MockNotification {
  key: string;
  title: string;
  description: string;
  time: string;
  unread: boolean;
  iconKey: "task" | "notice";
}

export const mockNotifications: MockNotification[] = [
  {
    key: "mock-task-complete",
    title: "演示任务已完成",
    description: "示例数据处理流程已完成，可用于界面检查。",
    time: "刚刚",
    unread: true,
    iconKey: "task",
  },
  {
    key: "mock-shell-notice",
    title: "界面演示通知",
    description: "这是一条本地 Mock 通知，不包含真实业务数据。",
    time: "10 分钟前",
    unread: false,
    iconKey: "notice",
  },
];

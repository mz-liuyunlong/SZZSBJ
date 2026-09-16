// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { NavigationPage } from "@/config/navigation";
import type { SyncTaskRow } from "@/pages/data-center/syncTaskTypes";

const messageError = vi.hoisted(() => vi.fn());

vi.mock("@ant-design/icons", () => ({ CalendarOutlined: () => null }));
vi.mock("antd", () => ({
  Button: ({ children, onClick }: { children?: ReactNode; onClick?: () => void }) => (
    <button type="button" onClick={onClick}>{children}</button>
  ),
  Spin: () => <span>loading</span>,
  Typography: {
    Title: ({ children }: { children?: ReactNode }) => <h1>{children}</h1>,
    Text: ({ children }: { children?: ReactNode }) => <p>{children}</p>,
  },
  message: {
    useMessage: () => [{ error: messageError, info: vi.fn(), warning: vi.fn() }, null],
  },
}));
vi.mock("@/components/page/PageShell", () => ({
  default: ({ children }: { children: ReactNode }) => <main>{children}</main>,
}));
vi.mock("@/pages/data-center/components/SyncTaskToolbar", () => ({
  default: ({ onRefresh }: { onRefresh: () => void }) => (
    <button type="button" onClick={onRefresh}>刷新任务</button>
  ),
}));
vi.mock("@/pages/data-center/components/SyncTaskSummaryCards", () => ({ default: () => null }));
vi.mock("@/pages/data-center/components/SyncTaskTable", () => ({
  default: ({ rows }: { rows: SyncTaskRow[] }) => (
    <div>{rows.map((row) => <span key={row.id}>{row.taskName}</span>)}</div>
  ),
}));
vi.mock("@/pages/data-center/components/SyncTaskConfigDrawer", () => ({ default: () => null }));
vi.mock("@/pages/data-center/components/SyncTaskLogDrawer", () => ({ default: () => null }));
vi.mock("@/pages/data-center/components/SyncTaskScheduleDrawer", () => ({ default: () => null }));
vi.mock("@/pages/data-center/integrationSyncTaskApi", () => ({
  listIntegrationSyncTasks: vi.fn(),
}));

import SyncTaskPage from "@/pages/data-center/SyncTaskPage";
import { listIntegrationSyncTasks } from "@/pages/data-center/integrationSyncTaskApi";

const page = {
  key: "data_center_sync_tasks",
  title: "同步任务管理",
  path: "/data-center/sync-tasks",
  phase: 1,
  status: "building",
  source: "new_postgres",
  sourceTables: [],
  readOnly: true,
  migrationMode: "native",
  permissionKey: "integrations:read",
  help: { enabled: true, title: "help", helpUrl: "/help", openInNewTab: true },
} as NavigationPage;

function renderSyncTaskPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        gcTime: 0,
        retry: false,
      },
      mutations: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <SyncTaskPage page={page} />
    </QueryClientProvider>,
  );
}

const task = {
  id: "synthetic-task",
  interfaceId: "synthetic-interface",
  taskName: "ProductInfo controlled sync",
  interfaceName: "batchGetProductInfo",
  provider: "synthetic-provider",
  source: null,
  taskType: "id_batch_page",
  status: "disabled",
  module: "商品",
  autoSync: false,
  frequency: "手动任务",
  lastStatus: "已停用",
  lastRunAt: null,
  lastRunFinishedAt: null,
  todaySuccess: 0,
  todayFailed: 0,
  description: "ProductInfo controlled sync",
  cycle: "手动任务",
  workItemsPlanned: 0,
  workItemsSucceeded: 0,
  workItemsFailed: 0,
  recordsSeen: 0,
  recordsWritten: 0,
  errorCode: null,
  dryRun: null,
  updatedAt: null,
  dailyRunCount: null,
  runTimes: [],
  weekDays: [],
  timeoutSeconds: null,
  maxFailureTimes: null,
  duplicatePolicy: null,
  retryEnabled: false,
  retryTimes: null,
  retryInterval: null,
  notificationScenes: [],
  notificationChannels: [],
  notificationTargets: null,
} satisfies SyncTaskRow;

beforeEach(() => {
  vi.mocked(listIntegrationSyncTasks).mockResolvedValue({ rows: [task], logs: [], schedules: [] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("SyncTaskPage", () => {
  it("loads governance state from the backend and refreshes it", async () => {
    renderSyncTaskPage();

    expect(await screen.findByText(task.taskName)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "刷新任务" }));
    await waitFor(() => expect(listIntegrationSyncTasks).toHaveBeenCalledTimes(2));
  });

  it("renders a safe backend failure without fallback rows", async () => {
    vi.mocked(listIntegrationSyncTasks).mockRejectedValueOnce(new Error("SAFE_BACKEND_ERROR"));
    renderSyncTaskPage();

    await waitFor(() => expect(messageError).toHaveBeenCalledWith("SAFE_BACKEND_ERROR"));
    expect(screen.queryByText(task.taskName)).not.toBeInTheDocument();
  });
});

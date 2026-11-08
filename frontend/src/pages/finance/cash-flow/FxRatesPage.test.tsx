// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { NavigationPage } from "@/config/navigation";
import FxRatesPage from "@/pages/finance/cash-flow/FxRatesPage";
import { diffFxRates, fxAdjacentYear, fxRateText, fxSyncDoneText, fxSyncErrorText, fxSyncFailedText, fxYearRows, fxYears } from "@/pages/finance/cash-flow/fxRates";
import { backendRequest, BackendRequestError } from "@/api/backendApi";
import { fetchCurrentUser } from "@/pages/auth/authApi";

const messages = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));

vi.mock("@/api/backendApi", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/api/backendApi")>()), backendRequest: vi.fn() }));
vi.mock("@/pages/auth/authApi", () => ({ fetchCurrentUser: vi.fn() }));
vi.mock("antd", () => ({
  message: { useMessage: () => [messages, null] },
  Button: ({ children, onClick, disabled, "aria-label": label }: { children?: ReactNode; onClick?: () => void; disabled?: boolean; "aria-label"?: string }) => (
    <button type="button" aria-label={label} disabled={disabled} onClick={onClick}>{children}</button>
  ),
  Select: ({ value, options }: { value: number; options: { value: number }[] }) => <output data-testid="year" data-options={options.map((item) => item.value).join(",")}>{value}</output>,
  Space: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Tooltip: ({ children, title }: { children?: ReactNode; title?: string }) => <div title={title}>{children}</div>,
  Card: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Tag: ({ children }: { children?: ReactNode }) => <span>{children}</span>,
  Drawer: () => null,
  Typography: Object.assign(({ children }: { children?: ReactNode }) => <div>{children}</div>, {
    Title: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
    Paragraph: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  }),
}));
vi.mock("@/components/page/RequestLoadingOverlay", () => ({ default: () => null }));
vi.mock("@/pages/finance/cash-flow/BoardTable", () => ({
  BoardTable: ({ rows, columns, emptyTitle }: { rows: Record<string, unknown>[]; columns: { dataIndex?: string; render?: (dom: unknown, row: unknown) => ReactNode }[]; emptyTitle: string }) => (
    rows.length === 0 ? <p>{emptyTitle}</p> : <div>{rows.map((row, index) => <div key={index} data-testid="row">{columns.map((column, cell) => <span key={cell}>{column.render ? column.render(null, row) : String(row[column.dataIndex ?? ""])}</span>)}</div>)}</div>
  ),
}));
vi.mock("@/components/page/PageShell", () => ({ default: ({ children, headerActions }: { children: ReactNode; headerActions?: ReactNode }) => <div>{headerActions}{children}</div> }));
vi.mock("@/pages/finance/cash-flow/journalApi", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/pages/finance/cash-flow/journalApi")>()), isCashLive: true }));

const YEAR = 2026;
const NEVER = { run_id: null, status: "never", error_code: null };

const serve = (handlers: { rates: () => unknown; syncGet?: () => unknown; syncPost?: () => unknown }) => {
  vi.mocked(backendRequest).mockImplementation((async (url: string, init?: { method?: string }) => {
    if (url.endsWith("/fx-rates")) return { data: handlers.rates() };
    if (init?.method === "POST") return { data: handlers.syncPost?.() };
    return { data: (handlers.syncGet ?? (() => NEVER))() };
  }) as never);
};

const showPage = () => render(
  <QueryClientProvider client={new QueryClient()}>
    <FxRatesPage page={{ key: "finance_fx_rates", title: "资金 汇率" } as NavigationPage} />
  </QueryClientProvider>,
);

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(YEAR, 10, 5));
  messages.success.mockClear();
  messages.error.mockClear();
  vi.mocked(backendRequest).mockReset();
  vi.mocked(fetchCurrentUser).mockReset().mockResolvedValue({ isSuperAdmin: false, permissions: ["action:finance:fx-rates:sync"] } as never);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("fxRateText", () => {
  it("shows two decimals, rounding on the string, and a dash when there is no rate", () => {
    expect(fxRateText("5.4300000000")).toBe("5.43");
    expect(fxRateText("7.1234567891")).toBe("7.12");
    expect(fxRateText("7.1250000000")).toBe("7.13");
    expect(fxRateText("1.0049999999")).toBe("1.00");
    expect(fxRateText("1.0050000000")).toBe("1.01");
    expect(fxRateText("9.9950000000")).toBe("10.00");
    expect(fxRateText("7")).toBe("7.00");
    expect(fxRateText("0.0100000000")).toBe("0.01");
    expect(fxRateText("12345678901234567.8912345678")).toBe("12345678901234567.89");
    expect(fxRateText(7.1)).toBe("7.10");
    expect(fxRateText(null)).toBe("—");
    expect(fxRateText("")).toBe("—");
    expect(fxRateText("0")).toBe("—");
    expect(fxRateText("0.0000000000")).toBe("—");
    expect(fxRateText("-7.1")).toBe("—");
    expect(fxRateText("abc")).toBe("—");
  });
});

describe("year paging", () => {
  it("always gives January to December, empty when there is no data", () => {
    const rows = fxYearRows([{ month: "2026-03", rate: "7" }, { month: "2025-03", rate: "6" }], 2026);
    expect(rows.map((row) => row.month)).toEqual(Array.from({ length: 12 }, (_, index) => `2026-${String(index + 1).padStart(2, "0")}`));
    expect(rows[2].rate).toBe("7");
    expect(rows.filter((row) => row.rate == null)).toHaveLength(11);
  });

  it("steps through the offered years only and stops at both ends", () => {
    expect(fxAdjacentYear([2026, 2024], 2026, "older")).toBe(2024);
    expect(fxAdjacentYear([2026, 2024], 2024, "newer")).toBe(2026);
    expect(fxAdjacentYear([2026, 2024], 2024, "older")).toBeNull();
    expect(fxAdjacentYear([2026, 2024], 2026, "newer")).toBeNull();
  });

  it("offers the current year plus every year with data, newest first", () => {
    expect(fxYears([], 2026)).toEqual([2026]);
    expect(fxYears([{ month: "2025-12", rate: "7" }, { month: "2026-01", rate: "7" }, { month: "2024-06", rate: null }], 2026)).toEqual([2026, 2025, 2024]);
  });
});

describe("diffFxRates", () => {
  it("counts added, updated and unchanged; months with no rate on both sides are ignored", () => {
    const before = [{ month: "2026-01", rate: "7.0000000000" }, { month: "2026-02", rate: "7" }, { month: "2026-03", rate: null }];
    const after = [
      { month: "2026-01", rate: "7" },
      { month: "2026-02", rate: "6.5" },
      { month: "2026-03", rate: "6.6" },
      { month: "2026-04", rate: "6.7" },
      { month: "2026-05", rate: null },
    ];
    expect(diffFxRates(before, after)).toEqual({ added: 2, updated: 1, unchanged: 1 });
    expect(diffFxRates([{ month: "2026-01", rate: "7.1234567891" }], [{ month: "2026-01", rate: "7.1234567892" }])).toEqual({ added: 0, updated: 1, unchanged: 0 });
    expect(diffFxRates([{ month: "2026-01", rate: "10.5000000000" }], [{ month: "2026-01", rate: "10.5" }])).toEqual({ added: 0, updated: 0, unchanged: 1 });
    expect(fxSyncDoneText({ added: 2, updated: 1, unchanged: 1 })).toBe("同步完成：新增 2 条，更新 1 条，未变 1 条");
  });
});

describe("failure text", () => {
  it("explains known codes, keeps unknown codes and maps status codes", () => {
    expect(fxSyncFailedText("SYNC_FX_ALL_MONTHS_EMPTY")).toContain("所有月份都没有返回汇率");
    expect(fxSyncFailedText("SOMETHING_ELSE")).toContain("SOMETHING_ELSE");
    expect(fxSyncFailedText(null)).toContain("同步失败");
    expect(fxSyncErrorText(new BackendRequestError(409, "X"))).toContain("还没打开");
    expect(fxSyncErrorText(new BackendRequestError(503, "X"))).toContain("任务队列");
    expect(fxSyncErrorText(new BackendRequestError(403, "X"))).toBe("当前角色没有汇率同步权限");
  });
});

describe("FxRatesPage", () => {
  it("shows twelve rows of the current year and pages to another year", async () => {
    serve({ rates: () => [{ month: "2026-10", my_rate: "7.5000000000" }, { month: "2025-12", my_rate: "7.2000000000" }] });
    showPage();
    expect(await screen.findByText("7.50")).toBeTruthy();
    expect(screen.getAllByTestId("row")).toHaveLength(12);
    expect(screen.getByText("2026-01")).toBeTruthy();
    expect(screen.getAllByText("领星·月汇率（我的汇率）")).toHaveLength(1);
    expect(screen.getAllByText("美元→人民币")).toHaveLength(12);
    expect(screen.queryByText("USD→CNY")).toBeNull();
    expect(screen.getByTestId("year").getAttribute("data-options")).toBe("2026,2025");
    expect((screen.getByLabelText("下一年") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText("上一年"));
    expect(await screen.findByText("7.20")).toBeTruthy();
    expect(screen.getByText("2025-01")).toBeTruthy();
    expect((screen.getByLabelText("上一年") as HTMLButtonElement).disabled).toBe(true);
  });

  it("jumps over a year with no data when paging", async () => {
    serve({ rates: () => [{ month: "2026-10", my_rate: "7.5000000000" }, { month: "2024-12", my_rate: "7.2000000000" }] });
    showPage();
    await screen.findByText("7.50");
    expect(screen.getByTestId("year").getAttribute("data-options")).toBe("2026,2024");
    fireEvent.click(screen.getByLabelText("上一年"));
    expect(await screen.findByText("7.20")).toBeTruthy();
    expect(screen.getByTestId("year").textContent).toBe("2024");
    expect((screen.getByLabelText("上一年") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText("下一年"));
    expect(await screen.findByText("7.50")).toBeTruthy();
    expect(screen.getByTestId("year").textContent).toBe("2026");
  });

  it("says there is no permission, not a read failure, when the backend answers 403", async () => {
    serve({ rates: () => { throw new BackendRequestError(403, "FORBIDDEN"); } });
    showPage();
    expect(await screen.findByText("没有权限")).toBeTruthy();
    expect(screen.queryByText("汇率读取失败")).toBeNull();
  });

  it("still calls other read errors a read failure", async () => {
    serve({ rates: () => { throw new BackendRequestError(500, "BOOM"); } });
    showPage();
    expect(await screen.findByText("汇率读取失败")).toBeTruthy();
  });

  it("greys out the sync button when the role has no sync permission, and says why", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue({ isSuperAdmin: false, permissions: [] } as never);
    const posts = vi.fn();
    serve({ rates: () => [], syncPost: posts });
    showPage();
    const button = await screen.findByRole("button", { name: "手动同步" });
    await waitFor(() => expect(button.parentElement?.getAttribute("title")).toBe("当前角色没有汇率同步权限"));
    expect((button as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(button);
    expect(posts).not.toHaveBeenCalled();
  });

  it("enables the sync button for a non-admin granted the sync action", async () => {
    serve({ rates: () => [] });
    showPage();
    await waitFor(() => expect((screen.getByRole("button", { name: "手动同步" }) as HTMLButtonElement).disabled).toBe(false));
    expect(screen.queryByTitle("当前角色没有汇率同步权限")).toBeNull();
  });

  it("says the same thing when the backend answers 403", async () => {
    serve({ rates: () => [], syncPost: () => { throw new BackendRequestError(403, "FORBIDDEN"); } });
    showPage();
    await waitFor(() => expect((screen.getByRole("button", { name: "手动同步" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "手动同步" }));
    await waitFor(() => expect(messages.error).toHaveBeenCalledWith("当前角色没有汇率同步权限"));
  });

  it("disables the button while syncing, then refreshes and reports the counts", async () => {
    let rates = [{ month: "2026-10", my_rate: "7.5" }, { month: "2026-09", my_rate: "7.1" }];
    let sync: Record<string, unknown> = NEVER;
    const posts = vi.fn(() => {
      sync = { run_id: "r1", status: "queued", error_code: null };
      return sync;
    });
    serve({ rates: () => rates, syncGet: () => sync, syncPost: posts });
    showPage();
    await screen.findByText("7.50");
    await waitFor(() => expect((screen.getByRole("button", { name: "手动同步" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "手动同步" }));
    const busy = await screen.findByRole("button", { name: "同步中" });
    expect((busy as HTMLButtonElement).disabled).toBe(true);
    expect(posts).toHaveBeenCalledTimes(1);

    rates = [{ month: "2026-11", my_rate: "6.6" }, { month: "2026-10", my_rate: "7.4" }, { month: "2026-09", my_rate: "7.1" }];
    sync = { run_id: "r1", status: "succeeded", error_code: null };
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 3100)); });
    await waitFor(() => expect(messages.success).toHaveBeenCalledWith("同步完成：新增 1 条，更新 1 条，未变 1 条"), { timeout: 2000 });
    expect(screen.getByText("7.40")).toBeTruthy();
    expect((screen.getByRole("button", { name: "手动同步" }) as HTMLButtonElement).disabled).toBe(false);
  }, 10000);

  it("shows the reason when the run fails", async () => {
    serve({
      rates: () => [],
      syncPost: () => ({ run_id: "r2", status: "failed", error_code: "SYNC_FX_RESPONSE_FAILED" }),
    });
    showPage();
    await waitFor(() => expect((screen.getByRole("button", { name: "手动同步" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "手动同步" }));
    await waitFor(() => expect(messages.error).toHaveBeenCalledWith(expect.stringContaining("领星返回了错误")));
    expect(messages.success).not.toHaveBeenCalled();
  });

  it("does not report an old finished run as this click's result", async () => {
    serve({
      rates: () => [],
      syncGet: () => ({ run_id: "old", status: "succeeded", error_code: null }),
    });
    showPage();
    await screen.findByRole("button", { name: "手动同步" });
    await waitFor(() => expect(vi.mocked(backendRequest).mock.calls.length).toBeGreaterThanOrEqual(2));
    expect(messages.success).not.toHaveBeenCalled();
    expect(messages.error).not.toHaveBeenCalled();
  });

  it("explains when the sync has not been turned on", async () => {
    serve({ rates: () => [], syncPost: () => { throw new BackendRequestError(409, "X"); } });
    showPage();
    await waitFor(() => expect((screen.getByRole("button", { name: "手动同步" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "手动同步" }));
    await waitFor(() => expect(messages.error).toHaveBeenCalledWith(expect.stringContaining("还没打开")));
  });
});

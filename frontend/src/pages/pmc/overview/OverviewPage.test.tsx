// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { navigation } from "@/config/navigation";
import OverviewPage from "@/pages/pmc/overview/OverviewPage";
import {
  getOverviewFilterOptions,
  getOverviewSummary,
  listOverviewItems,
} from "@/pages/pmc/overview/overviewApi";
import { syntheticRow, syntheticSummary } from "@/pages/pmc/overview/overviewFixtures";
import { clearPageStateCache } from "@/shared/page-state/pageStateCache";

vi.setConfig({ testTimeout: 30_000 });

vi.mock("@/pages/pmc/overview/overviewApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/pages/pmc/overview/overviewApi")>();
  return {
    ...actual,
    getOverviewSummary: vi.fn(),
    listOverviewItems: vi.fn(),
    getOverviewFilterOptions: vi.fn(),
    getOverviewItem: vi.fn(),
  };
});

const page = navigation.find((g) => g.key === "pmc")?.children.find((p) => p.key === "pmc_overview");

const renderPage = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><OverviewPage page={page!} /></QueryClientProvider>);
};

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

beforeEach(() => {
  clearPageStateCache();
  vi.mocked(getOverviewSummary).mockResolvedValue(syntheticSummary);
  vi.mocked(listOverviewItems).mockResolvedValue({ rows: [syntheticRow()], total: 1 });
  vi.mocked(getOverviewFilterOptions).mockResolvedValue({ stores: [], owners: ["Ann"], categories: [] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("OverviewPage", () => {
  it("is the first PMC page and read-only", () => {
    const pmc = navigation.find((g) => g.key === "pmc");
    expect(pmc?.children[0]).toMatchObject({ key: "pmc_overview", path: "/pmc/overview", readOnly: true });
  });

  it("shows the data day, cards and rows, and filters by card", async () => {
    renderPage();
    expect((await screen.findAllByText("2026-11-02")).length).toBeGreaterThan(0);
    expect(await screen.findByText("SKU-A")).toBeInTheDocument();
    expect(listOverviewItems).toHaveBeenLastCalledWith(expect.objectContaining({ onlyIssue: true, cats: [] }), 1, 50, expect.anything());

    fireEvent.click(screen.getByRole("button", { name: /^已断货：/ }));
    await waitFor(() => expect(listOverviewItems).toHaveBeenLastCalledWith(
      expect.objectContaining({ cats: ["已断货"], onlyIssue: true }), 1, 50, expect.anything(),
    ));

    fireEvent.click(screen.getByRole("button", { name: /^ItemID 总数：/ }));
    await waitFor(() => expect(listOverviewItems).toHaveBeenLastCalledWith(
      expect.objectContaining({ cats: [], onlyIssue: false }), 1, 50, expect.anything(),
    ));
  });

  it("says the snapshot is missing instead of showing sample data", async () => {
    vi.mocked(getOverviewSummary).mockRejectedValue({ status: 503, code: "PMC_OVERVIEW_NOT_READY" });
    vi.mocked(listOverviewItems).mockRejectedValue({ status: 503, code: "PMC_OVERVIEW_NOT_READY" });
    renderPage();
    expect((await screen.findAllByText(/总看板数据未就绪/)).length).toBeGreaterThan(0);
  });
});

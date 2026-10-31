// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ListingEvaluationMonitor from "./ListingEvaluationMonitor";

const backendRequest = vi.hoisted(() => vi.fn());
vi.mock("@/api/backendApi", () => ({ backendRequest }));

beforeEach(() => {
  backendRequest.mockReset();
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })),
  });
});
afterEach(cleanup);

const run = (publishedCount: number) => ({
  data: {
    items: [{
      id: "synthetic-run", schedule_date_cn: "2026-01-15", cutoff_date_la: "2026-01-14",
      status: "scoped_snapshots", rule_version: 1, total_listings: 1,
      processed_listings: 1, grade_candidate_count: 1,
      lifecycle_candidate_count: 0, blocked_count: 0, published_count: publishedCount,
    }],
    total: 1,
  },
});

it("keeps successful diagnostic records visible when follow-up loading fails", async () => {
  backendRequest.mockImplementation((path: string) => path.includes("evaluation-runs")
    ? Promise.resolve(run(0))
    : Promise.reject(new Error("synthetic follow-up failure")));

  render(<ListingEvaluationMonitor open onClose={() => undefined} />);

  expect(await screen.findByText("可见诊断快照")).toBeInTheDocument();
  expect(screen.getByText("C/D跟进加载失败。")).toBeInTheDocument();
  expect(screen.getByText("数据未全部加载，发布状态暂不能确认")).toBeInTheDocument();
  expect(screen.getByText("C/D跟进尚未加载")).toBeInTheDocument();
  expect(screen.queryByText("本次查询未发现已发布评级或正式跟进任务")).not.toBeInTheDocument();
});

it("shows publication separately from a diagnostic run status", async () => {
  backendRequest.mockImplementation((path: string) => Promise.resolve(
    path.includes("evaluation-runs") ? run(2) : { data: { items: [], total: 0 } },
  ));

  render(<ListingEvaluationMonitor open onClose={() => undefined} />);

  expect(await screen.findByText("可见诊断快照")).toBeInTheDocument();
  expect(screen.getByText("已查询到正式发布记录或C/D跟进任务")).toBeInTheDocument();
  expect(screen.queryByText("本次查询未发现已发布评级或正式跟进任务")).not.toBeInTheDocument();
});

it("keeps successful follow-ups visible when diagnostic loading fails", async () => {
  backendRequest.mockImplementation((path: string) => path.includes("evaluation-runs")
    ? Promise.reject(new Error("synthetic diagnostic failure"))
    : Promise.resolve({ data: { items: [{
      id: "synthetic-follow-up", item_id: "SYNTHETIC-ITEM", msku: null,
      grade: "C", cutoff_date_la: "2026-01-14", due_date_cn: "2026-01-15",
      owner_ref: null, status: "pending", resolution_note: null,
    }], total: 1 } }));

  render(<ListingEvaluationMonitor open onClose={() => undefined} />);

  expect(await screen.findByText("SYNTHETIC-ITEM")).toBeInTheDocument();
  expect(screen.getByText("计算记录加载失败。")).toBeInTheDocument();
  expect(screen.getByText("计算记录尚未加载")).toBeInTheDocument();
  expect(screen.getByText("已查询到正式发布记录或C/D跟进任务")).toBeInTheDocument();
});

it("does not show stale publication after a later request fails", async () => {
  backendRequest.mockImplementation((path: string) => Promise.resolve(
    path.includes("evaluation-runs") ? run(2) : { data: { items: [], total: 0 } },
  ));
  const { rerender } = render(<ListingEvaluationMonitor open onClose={() => undefined} />);
  expect(await screen.findByText("已查询到正式发布记录或C/D跟进任务")).toBeInTheDocument();

  rerender(<ListingEvaluationMonitor open={false} onClose={() => undefined} />);
  backendRequest.mockRejectedValue(new Error("synthetic retry failure"));
  rerender(<ListingEvaluationMonitor open onClose={() => undefined} />);

  expect(await screen.findByText("计算记录加载失败。 C/D跟进加载失败。")).toBeInTheDocument();
  expect(screen.getByText("数据未全部加载，发布状态暂不能确认")).toBeInTheDocument();
  expect(screen.queryByText("已查询到正式发布记录或C/D跟进任务")).not.toBeInTheDocument();
});

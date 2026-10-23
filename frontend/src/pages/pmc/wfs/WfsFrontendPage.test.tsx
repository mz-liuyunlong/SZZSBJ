// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { navigation } from "@/config/navigation";
import WfsFrontendPage from "./WfsFrontendPage";

const pages = navigation.find((group) => group.key === "pmc")!.children.filter((page) => page.sidebarSection === "pmc-wfs");

beforeEach(() => {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
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

afterEach(cleanup);

describe("WFS frontend pages", () => {
  it.each(pages)("renders $title", (page) => {
    const samples: Record<string, string> = {
      pmc_wfs_pending_packing: "PK261017-018",
      pmc_wfs_shipments: "WS261017-006",
      pmc_wfs_probe: "示例探测 A",
      pmc_wfs_create_board: "DEMO-CREATE-01",
      pmc_wfs_board: "3349164WFB",
      pmc_wfs_exceptions: "签收未回",
      pmc_wfs_settings: "上架缓冲天数",
    };
    render(<WfsFrontendPage page={page} />);
    expect(screen.getByRole("region", { name: page.title })).toBeInTheDocument();
    expect(screen.getByText(samples[page.key])).toBeInTheDocument();
    expect(screen.getByText(/不请求接口/)).toBeInTheDocument();
  });
});

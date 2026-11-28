// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import WooCommerceIntegrationPanel from "./WooCommerceIntegrationPanel";

const mocks = vi.hoisted(() => ({
  currentUser: vi.fn(),
  listStores: vi.fn(),
  createStore: vi.fn(),
  updateStore: vi.fn(),
  testStore: vi.fn(),
}));

vi.mock("@/pages/auth/authApi", () => ({
  fetchCurrentUser: mocks.currentUser,
}));

vi.mock("@/api/woocommerceConfigApi", () => ({
  listWooCommerceStores: mocks.listStores,
  createWooCommerceStore: mocks.createStore,
  updateWooCommerceStore: mocks.updateStore,
  testWooCommerceStore: mocks.testStore,
}));

const row = {
  id: "store-1",
  name: "RINIMA",
  store_url: "https://rinima.example.com",
  enabled: false,
  consumer_key_configured: true,
  consumer_secret_configured: true,
  last_test_at: null,
  last_test_ok: null,
  last_test_code: null,
  updated_at: "2026-11-28T00:00:00Z",
};

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
  mocks.currentUser.mockReset().mockResolvedValue({ isSuperAdmin: true });
  mocks.listStores.mockReset().mockResolvedValue([row]);
  mocks.createStore.mockReset().mockResolvedValue(row);
  mocks.updateStore.mockReset().mockResolvedValue(row);
  mocks.testStore.mockReset().mockResolvedValue({ ok: true, code: "OK" });
});

afterEach(cleanup);

describe("WooCommerce integration configuration", () => {
  it("loads configured stores without exposing credential values", async () => {
    render(<WooCommerceIntegrationPanel />);
    expect(await screen.findByText("RINIMA")).toBeInTheDocument();
    expect(screen.getByText("https://rinima.example.com")).toBeInTheDocument();
    expect(screen.queryByText(/ck_/)).not.toBeInTheDocument();
    expect(screen.queryByText(/cs_/)).not.toBeInTheDocument();
  });

  it("runs a connection test only after an explicit click", async () => {
    render(<WooCommerceIntegrationPanel />);
    const button = await screen.findByRole("button", { name: "\u6d4b\u8bd5\u8fde\u63a5" });
    expect(mocks.testStore).not.toHaveBeenCalled();
    fireEvent.click(button);
    await waitFor(() => expect(mocks.testStore).toHaveBeenCalledWith("store-1"));
  });

  it("hides write controls from non-super-admin users", async () => {
    mocks.currentUser.mockResolvedValue({ isSuperAdmin: false });
    render(<WooCommerceIntegrationPanel />);
    expect(await screen.findByText("\u53ea\u6709\u8d85\u7ea7\u7ba1\u7406\u5458\u53ef\u4ee5\u7ba1\u7406 WooCommerce \u5bc6\u94a5\u3002")).toBeInTheDocument();
    expect(mocks.listStores).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "\u65b0\u589e\u5e97\u94fa" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "\u7f16\u8f91" })).not.toBeInTheDocument();
  });
});

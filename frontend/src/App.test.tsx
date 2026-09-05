/** Verifies the App-level memory-only mock login and logout flow. */
// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { REMEMBERED_USERNAME_KEY } from "./pages/auth/LoginPage";

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
  localStorage.clear();
  sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

const logIn = async (remember = false) => {
  fireEvent.change(screen.getByLabelText("账号"), { target: { value: "admin" } });
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: "admin" } });
  if (remember) {
    fireEvent.click(screen.getByRole("checkbox", { name: "记住账号" }));
  }
  fireEvent.click(screen.getByRole("button", { name: "登录" }));
  await screen.findByRole("main", { name: "内容区" });
};

const openLogoutDialog = async () => {
  fireEvent.mouseEnter(screen.getByRole("button", { name: "用户菜单" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "退出" }));
  return screen.findByRole("dialog");
};

describe("App", () => {
  it("starts on the LoginPage and makes no network request", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(screen.getByRole("heading", { name: "欢迎回来 👋" })).toBeVisible();
    expect(screen.queryByRole("main", { name: "内容区" })).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("enters the default today-sales shell after active mock submission", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await logIn();

    expect(screen.getByRole("heading", { name: "当前页面" })).toHaveTextContent(
      "今日销售",
    );
    expect(screen.getByRole("navigation", { name: "面包屑" })).toHaveTextContent(
      "工作台",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps the current login after logout is cancelled or closed", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await logIn();

    await openLogoutDialog();
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(screen.getByRole("main", { name: "内容区" })).toBeInTheDocument();

    await openLogoutDialog();
    const closeButton = document.querySelector<HTMLButtonElement>(".ant-modal-close");
    if (!closeButton) throw new Error("Missing modal close button");
    fireEvent.click(closeButton);
    expect(screen.getByRole("main", { name: "内容区" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns to LoginPage after logout confirmation and keeps the remembered username", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await logIn(true);

    await openLogoutDialog();
    fireEvent.click(screen.getByRole("button", { name: "确认" }));
    expect(await screen.findByRole("heading", { name: "欢迎回来 👋" })).toBeVisible();
    expect(localStorage.getItem(REMEMBERED_USERNAME_KEY)).toBe("admin");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

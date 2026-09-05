/** Verifies the forgot-password mock stays local, uniform, and network-free. */
// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import ForgotPasswordPage from "./ForgotPasswordPage";

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
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function LocationProbe() {
  const location = useLocation();
  return (
    <output aria-label="当前路径">
      {location.pathname}{location.search}{location.hash}
    </output>
  );
}

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={["/forgot-password"]} useTransitions={false}>
      <Routes>
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/login" element={<div>登录页占位</div>} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  );

describe("ForgotPasswordPage", () => {
  it("shows the required mock notice and validates an empty name", async () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "忘记密码? 🙋🏻‍♂️" })).toBeVisible();
    expect(
      screen.getByText(
        "请输入真实飞书姓名，系统将向本人飞书发送密码重置卡片，请在卡片中设置新密码。",
      ),
    ).toBeVisible();
    expect(
      screen.getByText("当前为前端模拟流程，不会实际发送飞书卡片。"),
    ).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "发送重置卡片" }));
    expect(await screen.findByText("请输入你的真实姓名")).toBeInTheDocument();
  });

  it("returns the same local mock result for every non-empty name", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => undefined);
    renderPage();
    const nameInput = screen.getByPlaceholderText("请输入你的真实姓名");
    const submitButton = screen.getByRole("button", { name: "发送重置卡片" });
    expect(nameInput).toHaveAttribute("autocomplete", "off");

    fireEvent.change(nameInput, { target: { value: "测试用户" } });
    fireEvent.click(submitButton);
    expect(
      await screen.findByText("模拟提交成功：当前不会实际发送飞书卡片。"),
    ).toBeVisible();

    fireEvent.change(nameInput, { target: { value: "不存在的用户" } });
    fireEvent.click(submitButton);
    expect(
      await screen.findByText("模拟提交成功：当前不会实际发送飞书卡片。"),
    ).toBeVisible();
    expect(screen.getByLabelText("当前路径")).toHaveTextContent("/forgot-password");
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    expect(fetch).not.toHaveBeenCalled();
    expect(logSpy).not.toHaveBeenCalled();
  });

  it("returns explicitly to login", () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /返\s*回/ }));
    expect(screen.getByText("登录页占位")).toBeVisible();
    expect(screen.getByLabelText("当前路径")).toHaveTextContent("/login");
  });
});

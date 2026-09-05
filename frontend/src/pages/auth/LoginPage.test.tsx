/** Verifies the public frontend-only mock login and its storage boundary. */
// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import LoginPage, { REMEMBERED_USERNAME_KEY } from "./LoginPage";

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
});

const renderLogin = (onLogin = vi.fn()) =>
  render(
    <MemoryRouter initialEntries={["/login"]} useTransitions={false}>
      <Routes>
        <Route path="/login" element={<LoginPage onLogin={onLogin} />} />
        <Route path="/forgot-password" element={<div>忘记密码页占位</div>} />
      </Routes>
    </MemoryRouter>,
  );

const submitCredentials = (username: string, password: string) => {
  fireEvent.change(screen.getByLabelText("账号"), { target: { value: username } });
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "登录" }));
};

describe("LoginPage", () => {
  it("shows the mock disclaimer without logging in automatically", () => {
    const onLogin = vi.fn();
    renderLogin(onLogin);

    expect(
      screen.getByText("演示登录，仅用于前端界面验证，不提供真实身份认证。"),
    ).toBeVisible();
    expect(screen.getByLabelText("账号")).toHaveValue("admin");
    expect(screen.getByLabelText("密码")).toHaveValue("admin");
    expect(screen.getByRole("checkbox", { name: "记住账号" })).not.toBeChecked();
    expect(onLogin).not.toHaveBeenCalled();
  });

  it("accepts admin/admin and stores only a remembered username", async () => {
    const onLogin = vi.fn();
    renderLogin(onLogin);

    fireEvent.click(screen.getByRole("checkbox", { name: "记住账号" }));
    submitCredentials("admin", "admin");

    await waitFor(() => expect(onLogin).toHaveBeenCalledTimes(1));
    expect(localStorage.length).toBe(1);
    expect(localStorage.getItem(REMEMBERED_USERNAME_KEY)).toBe("admin");
    expect(localStorage.getItem("password")).toBeNull();
    expect(localStorage.getItem("token")).toBeNull();
    expect(localStorage.getItem("role")).toBeNull();
    expect(localStorage.getItem("permission")).toBeNull();
    expect(localStorage.getItem("auth")).toBeNull();
    expect(sessionStorage.length).toBe(0);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("shows one error for invalid credentials and removes an unchecked remembered username", async () => {
    const onLogin = vi.fn();
    renderLogin(onLogin);

    submitCredentials("admin", "wrong-password");
    expect(await screen.findByText("账号或密码错误")).toBeVisible();
    expect(onLogin).not.toHaveBeenCalled();

    cleanup();
    localStorage.setItem(REMEMBERED_USERNAME_KEY, "admin");
    renderLogin(onLogin);
    expect(screen.getByLabelText("账号")).toHaveValue("admin");
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "admin" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "记住账号" }));
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => expect(onLogin).toHaveBeenCalledTimes(1));
    expect(localStorage.getItem(REMEMBERED_USERNAME_KEY)).toBeNull();
    expect(sessionStorage.length).toBe(0);
  });

  it("navigates to the forgot-password route without storage or network activity", () => {
    renderLogin();

    fireEvent.click(screen.getByRole("link", { name: "忘记密码" }));

    expect(screen.getByText("忘记密码页占位")).toBeVisible();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    expect(fetch).not.toHaveBeenCalled();
  });
});

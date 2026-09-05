/** Verifies the public frontend-only mock login and its storage boundary. */
// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
});

const submitCredentials = (username: string, password: string) => {
  fireEvent.change(screen.getByLabelText("账号"), { target: { value: username } });
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "登录" }));
};

describe("LoginPage", () => {
  it("shows the brand and mock disclaimer without logging in automatically", () => {
    const onLogin = vi.fn();
    render(<LoginPage onLogin={onLogin} />);

    expect(screen.getByRole("heading", { name: "掌上便捷" })).toBeVisible();
    expect(screen.getByRole("img", { name: "掌上便捷标识" })).toHaveAttribute(
      "src",
      "/favicon.ico",
    );
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
    render(<LoginPage onLogin={onLogin} />);

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
  });

  it("shows one error for invalid credentials and removes an unchecked remembered username", async () => {
    const onLogin = vi.fn();
    render(<LoginPage onLogin={onLogin} />);

    submitCredentials("admin", "wrong-password");
    expect(await screen.findByText("账号或密码错误")).toBeVisible();
    expect(onLogin).not.toHaveBeenCalled();

    cleanup();
    localStorage.setItem(REMEMBERED_USERNAME_KEY, "admin");
    render(<LoginPage onLogin={onLogin} />);
    expect(screen.getByLabelText("账号")).toHaveValue("admin");
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "admin" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "记住账号" }));
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => expect(onLogin).toHaveBeenCalledTimes(1));
    expect(localStorage.getItem(REMEMBERED_USERNAME_KEY)).toBeNull();
    expect(sessionStorage.length).toBe(0);
  });

  it("keeps password recovery local", () => {
    render(<LoginPage onLogin={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "忘记密码" }));

    expect(screen.getByRole("status")).toHaveTextContent(
      "Mock 环境暂不提供密码找回",
    );
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});

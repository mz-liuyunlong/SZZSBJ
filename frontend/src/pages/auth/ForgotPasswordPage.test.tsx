/** Verifies the internal forgot-password flow requests a Feishu password setup notice. */
// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import ForgotPasswordPage from "@/pages/auth/ForgotPasswordPage";

interface JsonResponseBody {
  success: boolean;
  data: { message: string };
  error: null;
  meta: null;
  request_id: string;
}

function jsonResponse(body: JsonResponseBody) {
  return {
    ok: true,
    status: 200,
    url: "/api/auth/password-reset/request",
    headers: {
      get: (name: string) =>
        name.toLowerCase() === "content-type" ? "application/json" : null,
    },
    json: vi.fn().mockResolvedValue(body),
    text: vi.fn().mockResolvedValue(JSON.stringify(body)),
  } as unknown as Response;
}

const successBody: JsonResponseBody = {
  success: true,
  data: {
    message: "如果姓名匹配到在职员工，系统会通过飞书发送设置密码通知。",
  },
  error: null,
  meta: null,
  request_id: "test-request-id",
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
  localStorage.clear();
  sessionStorage.clear();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(successBody)));
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
      {location.pathname}
      {location.search}
      {location.hash}
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
  it("keeps the original forgot-password visual shell and validates an empty name", async () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "忘记密码? 🙋🏻‍♂️" })).toBeVisible();
    expect(
      screen.getByText("请输入真实飞书姓名，系统将向本人飞书发送设置登录密码通知。"),
    ).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "发送飞书设置密码通知" }));
    expect(await screen.findByText("请输入你的真实姓名")).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("submits a real name to request a Feishu password setup notice", async () => {
    renderPage();
    const nameInput = screen.getByRole("textbox", { name: "飞书姓名" });
    const submitButton = screen.getByRole("button", {
      name: "发送飞书设置密码通知",
    });

    expect(nameInput).toHaveAttribute("autocomplete", "name");

    fireEvent.change(nameInput, { target: { value: "刘云龙" } });
    fireEvent.click(submitButton);

    expect(
      await screen.findByText("如果姓名匹配到在职员工，系统会通过飞书发送设置密码通知。"),
    ).toBeVisible();
    expect(fetch).toHaveBeenCalledWith(
      "/api/auth/password-reset/request",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ real_name: "刘云龙" }),
      }),
    );
    expect(screen.getByLabelText("当前路径")).toHaveTextContent("/forgot-password");
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("returns explicitly to login", () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /返\s*回/ }));
    expect(screen.getByText("登录页占位")).toBeVisible();
    expect(screen.getByLabelText("当前路径")).toHaveTextContent("/login");
  });
});

// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import UserDataScopeModal from "@/pages/settings/components/UserDataScopeModal";
import type { UserManagementRow } from "@/pages/settings/userManagementTypes";

const user: UserManagementRow = {
  id: "41",
  username: "synthetic-user",
  realName: "Synthetic User",
  phone: "-",
  email: "-",
  status: "启用",
  roles: ["运营"],
  isSuperAdmin: false,
  createdAt: "2026-10-17 00:00",
  lastLoginAt: "-",
};

afterEach(cleanup);

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
});

describe("UserDataScopeModal", () => {
  it("shows whether the effective scope comes from the user or a role", () => {
    render(
      <UserDataScopeModal
        user={user}
        items={[]}
        effectiveItems={[
          { scopeType: "source_account", scopeValue: "account-a", source: "role" },
          { scopeType: "store", scopeValue: "store-a", source: "user" },
        ]}
        loading={false}
        saving={false}
        onChange={vi.fn()}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByText("角色：source_account=account-a")).toBeInTheDocument();
    expect(screen.getByText("用户：store=store-a")).toBeInTheDocument();
    expect(screen.getByText(/当前业务接口严格执行数据源账号范围/)).toBeInTheDocument();
  });
});

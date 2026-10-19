import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  saveUserDataScopes,
  updateUser,
  updateUserStatus,
} from "@/pages/settings/userManagementApi";
import type { UserFormValues } from "@/pages/settings/userManagementTypes";

const { backendRequestMock } = vi.hoisted(() => ({
  backendRequestMock: vi.fn(),
}));

vi.mock("@/api/backendApi", () => ({
  backendRequest: backendRequestMock,
}));

const formValues: UserFormValues = {
  username: "synthetic-user",
  realName: "Synthetic User",
  phone: "",
  email: "",
  password: "",
  status: "停用",
  roles: [],
  feishuName: "",
  feishuOpenId: "",
  feishuUserId: "",
  feishuUnionId: "",
  feishuEmployeeId: "",
  feishuDepartmentIds: [],
};

beforeEach(() => {
  backendRequestMock.mockReset();
  backendRequestMock.mockResolvedValue({ data: {} });
});

describe("user management action separation", () => {
  it("does not mix account status into the profile update request", async () => {
    await updateUser("41", formValues);

    const options = backendRequestMock.mock.calls[0]?.[1] as { body: string };
    expect(JSON.parse(options.body)).not.toHaveProperty("is_active");
  });

  it("uses the dedicated status-only request", async () => {
    await updateUserStatus("41", false);

    expect(backendRequestMock).toHaveBeenCalledWith("/api/settings/users/41", {
      method: "PATCH",
      body: JSON.stringify({ is_active: false }),
    });
  });
});

describe("user data scope API", () => {
  it("trims values and removes blank entries before saving", async () => {
    backendRequestMock.mockResolvedValue({
      data: {
        user_id: 41,
        items: [],
        role_items: [],
        effective_items: [],
      },
    });

    await saveUserDataScopes("41", [
      { scopeType: "source_account", scopeValue: " account-a " },
      { scopeType: "store", scopeValue: "  " },
    ]);

    expect(backendRequestMock).toHaveBeenCalledWith(
      "/api/settings/rbac/users/41/data-scopes",
      {
        method: "PUT",
        body: JSON.stringify({
          items: [{ scope_type: "source_account", scope_value: "account-a" }],
        }),
      },
    );
  });
});

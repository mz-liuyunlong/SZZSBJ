import { describe, expect, it } from "vitest";
import { formatSyncTaskOperationError } from "@/pages/data-center/syncTaskOperationMessages";

describe("formatSyncTaskOperationError", () => {
  it("maps authentication and permission errors to business friendly messages", () => {
    expect(formatSyncTaskOperationError({ status: 401, message: "BACKEND_REQUEST_FAILED" }))
      .toContain("未完成登录授权");
    expect(formatSyncTaskOperationError({ status: 403, message: "FORBIDDEN" }))
      .toContain("没有同步任务操作权限");
  });

  it("keeps backend error codes visible for unknown failures", () => {
    expect(formatSyncTaskOperationError(new Error("UNKNOWN_ERROR")))
      .toBe("同步操作失败：UNKNOWN_ERROR");
  });
});

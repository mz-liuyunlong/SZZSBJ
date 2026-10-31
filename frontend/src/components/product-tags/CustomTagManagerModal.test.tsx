// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CustomTagManagerModal from "./CustomTagManagerModal";

afterEach(cleanup);

describe("Listing tag account ownership", () => {
  it("requires an explicit account before a multi-account user creates a tag", async () => {
    const create = vi.fn().mockResolvedValue({
      id: "synthetic-tag", sourceAccountRef: "synthetic-b", name: "Review", color: "#1677FF", usage: 0,
    });
    render(
      <CustomTagManagerModal
        open
        onClose={() => undefined}
        accountRefs={["synthetic-a", "synthetic-b"]}
        initialTags={[{ id: "existing", sourceAccountRef: "synthetic-a", name: "Review", color: "#1677FF", usage: 1 }]}
        onCreateTag={create}
      />,
    );

    fireEvent.change(screen.getByLabelText("标签名称"), { target: { value: "Review" } });
    expect(screen.getByRole("button", { name: "添加" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("所属账号"), { target: { value: "synthetic-b" } });
    expect(screen.getByRole("button", { name: "添加" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "添加" }));
    await waitFor(() => expect(create).toHaveBeenCalledWith({
      name: "Review", color: "#1677FF", sourceAccountRef: "synthetic-b",
    }));
  });
});

// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ProductTagAssignmentModal from "@/components/product-tags/ProductTagAssignmentModal";

afterEach(cleanup);

describe("ProductTagAssignmentModal", () => {
  it("uses caller-provided tags and confirms the selected values", () => {
    const onConfirm = vi.fn();
    const props = {
      open: true,
      selectedProductCount: 3,
      tags: [
        { id: "tag-1", name: "主推产品", color: "#1677FF", usage: 2 },
        { id: "tag-2", name: "新品", color: "#7C5CFF", usage: 1 },
      ],
      loading: false,
      onCancel: vi.fn(),
      onConfirm,
    };

    render(<ProductTagAssignmentModal {...props} />);

    expect(screen.getByRole("dialog")).toHaveTextContent("已选择 3 个商品");
    expect(screen.getByRole("button", { name: /确\s*定/ })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "新品" }));
    const confirmButton = screen.getByRole("button", { name: /确\s*定/ });
    expect(confirmButton).toBeEnabled();

    fireEvent.click(confirmButton);
    expect(onConfirm).toHaveBeenCalledWith(["新品"]);
  });
});

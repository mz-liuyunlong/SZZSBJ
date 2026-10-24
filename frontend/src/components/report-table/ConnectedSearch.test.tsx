// @vitest-environment jsdom
/** Optional screenshot layout props must preserve existing search consumers by default. */
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ConnectedSearch from "./ConnectedSearch";

afterEach(cleanup);
const props = {
  typeAriaLabel: "类型", typeValue: "sku", typeOptions: [{ value: "sku", label: "SKU" }],
  inputAriaLabel: "关键词", inputValue: "", inputPlaceholder: "请输入 SKU",
  onTypeChange: vi.fn(), onInputChange: vi.fn(), onSearch: vi.fn(),
  batchControl: <button type="button">批量</button>,
};
describe("connected search layout", () => {
  it("keeps the existing search-before-batch order", () => {
    render(<ConnectedSearch {...props} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons.map((button) => button.getAttribute("aria-label") ?? button.textContent)).toEqual(["搜索", "批量"]);
  });
  it("can place batch first and show a text search button", () => {
    const onSearch = vi.fn();
    render(<ConnectedSearch {...props} onSearch={onSearch} batchPlacement="before-search" searchButtonText="搜索" />);
    expect(screen.getAllByRole("button")[0]).toHaveTextContent("批量");
    fireEvent.click(screen.getByRole("button", { name: "搜索" }));
    expect(onSearch).toHaveBeenCalledOnce();
    fireEvent.keyDown(screen.getByRole("textbox", { name: "关键词" }), { key: "Enter", code: "Enter" });
    expect(onSearch).toHaveBeenCalledTimes(2);
  });
});

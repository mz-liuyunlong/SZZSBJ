// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { Modal } from "antd";
import { afterEach, describe, expect, it, vi } from "vitest";
import ProductTagAssignmentModal from "./ProductTagAssignmentModal";

vi.mock("antd", () => {
  const MockModal = Object.assign(
    ({ open, children, title, footer }: { open: boolean; children: ReactNode; title: ReactNode; footer: ReactNode }) =>
      open ? <div>{title}{children}{footer}</div> : null,
    { confirm: vi.fn() },
  );
  return {
    Button: ({ children, onClick, disabled }: { children: ReactNode; onClick?: () => void; disabled?: boolean }) =>
      <button type="button" onClick={onClick} disabled={disabled}>{children}</button>,
    Empty: Object.assign(() => <div>暂无可用标签</div>, { PRESENTED_IMAGE_SIMPLE: "simple" }),
    Modal: MockModal,
    Radio: {
      Group: ({ options, onChange }: { options: Array<{ label: string; value: string }>; onChange: (event: { target: { value: string } }) => void }) =>
        <div>{options.map((option) => <button key={option.value} type="button" onClick={() => onChange({ target: { value: option.value } })}>{option.label}</button>)}</div>,
    },
    Spin: ({ children }: { children: ReactNode }) => <>{children}</>,
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("batch Listing tag assignment safety", () => {
  it("requires a second confirmation before clearing selected Listings", () => {
    const onConfirm = vi.fn();
    render(
      <ProductTagAssignmentModal
        open
        selectedProductCount={3}
        tags={[]}
        onCancel={() => undefined}
        onConfirm={onConfirm}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "替换（允许清空）" }));
    fireEvent.click(screen.getByRole("button", { name: "确定" }));
    expect(onConfirm).not.toHaveBeenCalled();
    const confirmation = vi.mocked(Modal.confirm).mock.calls[0][0] as {
      content: string;
      onOk: () => void;
    };
    expect(confirmation.content).toContain("清空已选 3 条 Listing");
    confirmation.onOk();
    expect(onConfirm).toHaveBeenCalledWith([], "replace");
  });
});

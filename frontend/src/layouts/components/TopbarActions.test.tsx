/** Verifies local topbar overlay, page callback, and logout-confirmation behavior. */
// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { navigation, type NavigationPage } from "../../config/navigation";
import TopbarActions from "./TopbarActions";

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

afterEach(cleanup);

const requiredPage = (key: string): NavigationPage => {
  for (const group of navigation) {
    const page = group.children.find((item) => item.key === key);
    if (page) return page;
  }
  throw new Error(`Missing navigation page: ${key}`);
};

const renderActions = () => {
  const callbacks = {
    onOpenPage: vi.fn(),
    onRequestOverlayClose: vi.fn(),
    onLogout: vi.fn(),
  };
  render(
    <TopbarActions
      aiAssistantPage={requiredPage("ai_center_assistant")}
      personalCenterPage={requiredPage("settings_personal_center")}
      documentationPage={requiredPage("data_center_documentation")}
      {...callbacks}
    />,
  );
  return callbacks;
};

describe("TopbarActions", () => {
  it("opens notifications on click, closes outside, and clears unread state", async () => {
    renderActions();
    const notificationButton = screen.getByRole("button", { name: "通知" });

    expect(screen.getByLabelText("有未读通知")).toBeInTheDocument();
    fireEvent.click(notificationButton);
    expect(notificationButton).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByRole("region", { name: "通知面板" })).toBeInTheDocument();

    fireEvent.mouseDown(document.body);
    fireEvent.click(document.body);
    await waitFor(() => expect(notificationButton).toHaveAttribute("aria-expanded", "false"));

    fireEvent.click(notificationButton);
    fireEvent.click(await screen.findByRole("button", { name: "清空" }));
    expect(await screen.findByText("暂无通知")).toBeInTheDocument();
    expect(screen.getByLabelText("无未读通知")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "查看所有消息" }));
    expect(screen.getByRole("status")).toHaveTextContent("通知中心将在后续接入");

    fireEvent.click(notificationButton);
    expect(notificationButton).toHaveAttribute("aria-expanded", "false");
  });

  it("keeps notification and user overlays mutually exclusive", async () => {
    renderActions();

    const notificationButton = screen.getByRole("button", { name: "通知" });
    const userButton = screen.getByRole("button", { name: "用户菜单" });
    fireEvent.click(userButton);
    expect(userButton).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(notificationButton);
    expect(notificationButton).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByRole("region", { name: "通知面板" })).toBeInTheDocument();
    fireEvent.mouseEnter(userButton);

    expect(userButton).toHaveAttribute("aria-expanded", "true");
    expect(notificationButton).toHaveAttribute("aria-expanded", "false");
    const userPanel = await screen.findByRole("region", { name: "用户菜单面板" });
    expect(userPanel).toBeInTheDocument();
    expect(screen.getByText("演示用户")).toBeInTheDocument();
    expect(screen.getByText("admin@example.local")).toBeInTheDocument();
    expect(screen.getByText("在线")).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: "演示用户头像" })).toHaveLength(2);
    for (const avatar of screen.getAllByRole("img", { name: "演示用户头像" })) {
      expect(avatar).toHaveAttribute("src", "/default-avatar.png");
    }

    fireEvent.mouseLeave(userButton);
    fireEvent.mouseEnter(userPanel);
    expect(userButton).toHaveAttribute("aria-expanded", "true");
    fireEvent.mouseLeave(userPanel);
    await waitFor(() => expect(userButton).toHaveAttribute("aria-expanded", "false"));

    fireEvent.mouseEnter(userButton);
    fireEvent.mouseDown(document.body);
    fireEvent.click(document.body);
    await waitFor(() => expect(userButton).toHaveAttribute("aria-expanded", "false"));
  });

  it("shows the text fallback when either local avatar image fails", async () => {
    renderActions();
    const userButton = screen.getByRole("button", { name: "用户菜单" });

    fireEvent.error(within(userButton).getByRole("img", { name: "演示用户头像" }));
    await waitFor(() => expect(userButton).toHaveTextContent("掌"));

    fireEvent.mouseEnter(userButton);
    const userPanel = await screen.findByRole("region", { name: "用户菜单面板" });
    fireEvent.error(
      within(userPanel).getByRole("img", { name: "演示用户头像" }),
    );
    await waitFor(() => expect(userPanel).toHaveTextContent("掌"));
  });

  it("opens on keyboard focus and closes when focus leaves the user menu", async () => {
    renderActions();
    const userButton = screen.getByRole("button", { name: "用户菜单" });
    const notificationButton = screen.getByRole("button", { name: "通知" });

    fireEvent.focus(userButton);
    expect(userButton).toHaveAttribute("aria-expanded", "true");
    const userPanel = await screen.findByRole("region", { name: "用户菜单面板" });
    const personalCenter = within(userPanel).getByRole("menuitem", {
      name: "个人中心",
    });

    fireEvent.blur(userButton, { relatedTarget: personalCenter });
    fireEvent.focus(personalCenter);
    expect(userButton).toHaveAttribute("aria-expanded", "true");

    fireEvent.blur(personalCenter, { relatedTarget: notificationButton });
    fireEvent.focus(notificationButton);
    await waitFor(() =>
      expect(userButton).toHaveAttribute("aria-expanded", "false"),
    );
    expect(notificationButton).toHaveAttribute("aria-expanded", "false");
  });

  it("sends navigation-derived page keys", async () => {
    const { onOpenPage, onRequestOverlayClose } = renderActions();

    fireEvent.click(screen.getByRole("button", { name: "AI助手" }));
    expect(onOpenPage).toHaveBeenLastCalledWith("ai_center_assistant");

    fireEvent.mouseEnter(screen.getByRole("button", { name: "用户菜单" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "个人中心" }));
    expect(onOpenPage).toHaveBeenLastCalledWith("settings_personal_center");

    fireEvent.mouseEnter(screen.getByRole("button", { name: "用户菜单" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "文档" }));
    expect(onOpenPage).toHaveBeenLastCalledWith("data_center_documentation");
    expect(onRequestOverlayClose).toHaveBeenCalled();
  });

  it("requires confirmation and emits logout only once", async () => {
    const { onLogout } = renderActions();
    const openLogout = async () => {
      fireEvent.mouseEnter(screen.getByRole("button", { name: "用户菜单" }));
      fireEvent.click(await screen.findByRole("menuitem", { name: "退出" }));
      return screen.findByRole("dialog");
    };

    await openLogout();
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(onLogout).not.toHaveBeenCalled();

    await openLogout();
    const closeButton = document.querySelector<HTMLButtonElement>(".ant-modal-close");
    if (!closeButton) throw new Error("Missing modal close button");
    fireEvent.click(closeButton);
    expect(onLogout).not.toHaveBeenCalled();

    await openLogout();
    fireEvent.click(screen.getByRole("button", { name: "确认" }));
    expect(onLogout).toHaveBeenCalledTimes(1);
  });
});

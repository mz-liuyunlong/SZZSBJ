/**
 * Provides local topbar overlays and callbacks; it does not own page state, authentication, or API calls.
 */
import {
  BellOutlined,
  CheckCircleOutlined,
  NotificationOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import {
  Avatar,
  Badge,
  Button,
  Empty,
  List,
  Modal,
  Popover,
  Space,
  Typography,
} from "antd";
import { useEffect, useRef, useState, type FocusEvent } from "react";
import type { NavigationPage } from "../../config/navigation";
import { mockCurrentUser } from "../../mocks/currentUser";
import {
  mockNotifications,
  type MockNotification,
} from "../../mocks/notifications";
import "./TopbarActions.css";

interface TopbarActionsProps {
  aiAssistantPage: NavigationPage;
  personalCenterPage: NavigationPage;
  documentationPage: NavigationPage;
  onOpenPage: (pageKey: string) => void;
  onRequestOverlayClose: () => void;
  onLogout: () => void;
}

function TopbarActions({
  aiAssistantPage,
  personalCenterPage,
  documentationPage,
  onOpenPage,
  onRequestOverlayClose,
  onLogout,
}: TopbarActionsProps) {
  const [notifications, setNotifications] =
    useState<MockNotification[]>(mockNotifications);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [logoutOpen, setLogoutOpen] = useState(false);
  const [showAllMessage, setShowAllMessage] = useState(false);
  const logoutConfirmed = useRef(false);
  const userButtonRef = useRef<HTMLButtonElement>(null);
  const userPanelRef = useRef<HTMLElement>(null);
  const hasUnread = notifications.some((item) => item.unread);

  useEffect(() => {
    if (!userMenuOpen) return;

    const closeUserMenuOutside = (event: Event) => {
      const target = event.target;
      if (
        !(target instanceof Node) ||
        userButtonRef.current?.contains(target) ||
        userPanelRef.current?.contains(target)
      ) {
        return;
      }
      setUserMenuOpen(false);
    };

    document.addEventListener("mousedown", closeUserMenuOutside);
    document.addEventListener("focusin", closeUserMenuOutside);
    return () => {
      document.removeEventListener("mousedown", closeUserMenuOutside);
      document.removeEventListener("focusin", closeUserMenuOutside);
    };
  }, [userMenuOpen]);

  const changeNotificationOpen = (open: boolean) => {
    setNotificationOpen(open);
    if (open) {
      setUserMenuOpen(false);
      onRequestOverlayClose();
    } else {
      setShowAllMessage(false);
    }
  };

  const changeUserMenuOpen = (open: boolean) => {
    setUserMenuOpen(open);
    if (open) {
      setNotificationOpen(false);
      setShowAllMessage(false);
      onRequestOverlayClose();
    }
  };

  const closeUserMenuOnBlur = (event: FocusEvent<HTMLElement>) => {
    const nextTarget = event.relatedTarget;
    if (
      nextTarget instanceof Node &&
      (userButtonRef.current?.contains(nextTarget) ||
        userPanelRef.current?.contains(nextTarget))
    ) {
      return;
    }
    setUserMenuOpen(false);
  };

  const openPage = (pageKey: string) => {
    setNotificationOpen(false);
    setUserMenuOpen(false);
    setShowAllMessage(false);
    onOpenPage(pageKey);
  };

  const showLogout = () => {
    setUserMenuOpen(false);
    logoutConfirmed.current = false;
    setLogoutOpen(true);
  };

  const confirmLogout = () => {
    if (logoutConfirmed.current) return;
    logoutConfirmed.current = true;
    setLogoutOpen(false);
    onLogout();
  };

  const notificationPanel = (
    <section className="topbar-actions__panel topbar-actions__notification-panel" aria-label="通知面板">
      <div className="topbar-actions__panel-title">
        <Typography.Text strong>通知</Typography.Text>
        <Typography.Text type="secondary">本地 Mock</Typography.Text>
      </div>
      <List
        className="topbar-actions__notification-list"
        dataSource={notifications}
        locale={{
          emptyText: (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无通知" />
          ),
        }}
        renderItem={(item) => (
          <List.Item className={item.unread ? "topbar-actions__notification--unread" : ""}>
            <div className="topbar-actions__notification-icon" aria-hidden="true">
              {item.iconKey === "task" ? <CheckCircleOutlined /> : <NotificationOutlined />}
            </div>
            <div className="topbar-actions__notification-copy">
              <div className="topbar-actions__notification-heading">
                <Typography.Text strong>{item.title}</Typography.Text>
                <Typography.Text type="secondary">{item.unread ? "未读" : "已读"}</Typography.Text>
              </div>
              <Typography.Text type="secondary">{item.description}</Typography.Text>
              <Typography.Text className="topbar-actions__notification-time" type="secondary">
                {item.time}
              </Typography.Text>
            </div>
          </List.Item>
        )}
      />
      {showAllMessage && (
        <Typography.Text className="topbar-actions__local-message" type="secondary" role="status">
          通知中心将在后续接入
        </Typography.Text>
      )}
      <div className="topbar-actions__panel-footer">
        <Button type="text" onClick={() => setNotifications([])}>
          清空
        </Button>
        <Button type="link" onClick={() => setShowAllMessage(true)}>
          查看所有消息
        </Button>
      </div>
    </section>
  );

  const userMenu = (
    <section
      ref={userPanelRef}
      className="topbar-actions__panel topbar-actions__user-panel"
      aria-label="用户菜单面板"
      onBlur={closeUserMenuOnBlur}
    >
      <div className="topbar-actions__user-summary">
        <Avatar
          size={40}
          src={mockCurrentUser.avatarSrc}
          alt="演示用户头像"
        >
          掌
        </Avatar>
        <div>
          <Typography.Text strong>{mockCurrentUser.displayName}</Typography.Text>
          <Typography.Text type="secondary">{mockCurrentUser.account}</Typography.Text>
          <Badge status={mockCurrentUser.online ? "success" : "default"} text="在线" />
        </div>
      </div>
      <div className="topbar-actions__user-menu" role="menu" aria-label="用户菜单选项">
        <Button type="text" role="menuitem" onClick={() => openPage(personalCenterPage.key)}>
          {personalCenterPage.title}
        </Button>
        <Button type="text" role="menuitem" onClick={() => openPage(documentationPage.key)}>
          {documentationPage.title}
        </Button>
        <Button danger type="text" role="menuitem" onClick={showLogout}>
          退出
        </Button>
      </div>
    </section>
  );

  return (
    <>
      <Space className="topbar-actions" size={4} role="group" aria-label="顶部操作">
        <Popover
          trigger="click"
          placement="bottomRight"
          arrow={false}
          open={notificationOpen}
          onOpenChange={changeNotificationOpen}
          content={notificationPanel}
          classNames={{ root: "topbar-actions__popover" }}
        >
          <Button
            className="topbar-actions__button"
            type="text"
            aria-label="通知"
            aria-expanded={notificationOpen}
          >
            <Badge
              dot={hasUnread}
              color="#52c41a"
              aria-label={hasUnread ? "有未读通知" : "无未读通知"}
            >
              <BellOutlined />
            </Badge>
          </Button>
        </Popover>

        <Button
          className="topbar-actions__button topbar-actions__ai-button"
          type="text"
          icon={<RobotOutlined aria-hidden="true" />}
          aria-label={aiAssistantPage.title}
          onClick={() => openPage(aiAssistantPage.key)}
        >
          {aiAssistantPage.title}
        </Button>

        <Popover
          trigger="hover"
          placement="bottomRight"
          arrow={false}
          mouseEnterDelay={0}
          mouseLeaveDelay={0.1}
          open={userMenuOpen}
          onOpenChange={changeUserMenuOpen}
          content={userMenu}
          classNames={{ root: "topbar-actions__popover" }}
        >
          <Button
            ref={userButtonRef}
            className="topbar-actions__avatar-button"
            type="text"
            aria-label="用户菜单"
            aria-expanded={userMenuOpen}
            aria-haspopup="menu"
            onFocus={() => changeUserMenuOpen(true)}
            onBlur={closeUserMenuOnBlur}
          >
            <Avatar
              size={28}
              src={mockCurrentUser.avatarSrc}
              alt="演示用户头像"
            >
              掌
            </Avatar>
          </Button>
        </Popover>
      </Space>

      <Modal
        title="提示"
        open={logoutOpen}
        onCancel={() => setLogoutOpen(false)}
        onOk={confirmLogout}
        cancelText="取消"
        okText="确认"
        cancelButtonProps={{ "aria-label": "取消" }}
        okButtonProps={{ "aria-label": "确认" }}
        width={400}
      >
        <Typography.Text>是否退出登录？</Typography.Text>
      </Modal>
    </>
  );
}

export default TopbarActions;

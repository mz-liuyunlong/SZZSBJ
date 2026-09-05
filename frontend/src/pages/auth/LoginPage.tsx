/**
 * Renders the frontend-only mock login experience; it does not provide authentication or authorization.
 */
import {
  Alert,
  Button,
  Checkbox,
  Form,
  Input,
  Typography,
  type FormProps,
} from "antd";
import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { useState } from "react";
import {
  isValidMockLogin,
  MOCK_PASSWORD,
  MOCK_USERNAME,
} from "../../mocks/auth";
import "./LoginPage.css";

export const REMEMBERED_USERNAME_KEY = "szzsbj_mock_username";

interface LoginValues {
  username: string;
  password: string;
  remember?: boolean;
}

interface LoginPageProps {
  onLogin: () => void;
}

function LoginPage({ onLogin }: LoginPageProps) {
  const [rememberedUsername] = useState(() =>
    localStorage.getItem(REMEMBERED_USERNAME_KEY),
  );
  const [loginError, setLoginError] = useState(false);
  const [forgotMessage, setForgotMessage] = useState(false);

  const submitLogin: FormProps<LoginValues>["onFinish"] = (values) => {
    setForgotMessage(false);
    if (!isValidMockLogin(values.username, values.password)) {
      setLoginError(true);
      return;
    }

    setLoginError(false);
    if (values.remember) {
      localStorage.setItem(REMEMBERED_USERNAME_KEY, values.username);
    } else {
      localStorage.removeItem(REMEMBERED_USERNAME_KEY);
    }
    onLogin();
  };

  return (
    <main className="login-page">
      <section className="login-page__visual" aria-label="掌上便捷品牌介绍">
        <div className="login-page__brand">
          <img src="/favicon.ico" alt="掌上便捷标识" width={36} height={36} />
          <Typography.Title level={4}>掌上便捷</Typography.Title>
        </div>
        <div className="login-page__illustration" aria-hidden="true">
          <svg viewBox="0 0 520 360" role="presentation">
            <defs>
              <linearGradient id="login-card-gradient" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stopColor="#ffffff" />
                <stop offset="1" stopColor="#dbeafe" />
              </linearGradient>
            </defs>
            <circle cx="260" cy="180" r="150" fill="#ffffff" opacity="0.42" />
            <rect x="92" y="74" width="336" height="220" rx="28" fill="url(#login-card-gradient)" />
            <rect x="128" y="112" width="128" height="18" rx="9" fill="#91caff" />
            <rect x="128" y="148" width="210" height="12" rx="6" fill="#d6e4ff" />
            <rect x="128" y="178" width="164" height="12" rx="6" fill="#d6e4ff" />
            <path d="M135 252 195 210 246 232 326 158 390 205" fill="none" stroke="#1677ff" strokeWidth="12" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx="195" cy="210" r="12" fill="#52c41a" />
            <circle cx="326" cy="158" r="12" fill="#1677ff" />
          </svg>
        </div>
        <div className="login-page__visual-copy">
          <Typography.Title level={2}>让运营管理更清晰</Typography.Title>
          <Typography.Text>统一工作入口，专注每天真正重要的数据。</Typography.Text>
        </div>
      </section>

      <section className="login-page__form-panel" aria-label="登录表单区域">
        <div className="login-page__form-card">
          <Typography.Title level={2}>欢迎回来 👋</Typography.Title>
          <Typography.Paragraph type="secondary">
            请输入您的账户信息以开始管理您的项目
          </Typography.Paragraph>

          <Alert
            className="login-page__disclaimer"
            type="info"
            showIcon
            message="演示登录，仅用于前端界面验证，不提供真实身份认证。"
          />

          <Form<LoginValues>
            name="mock-login"
            layout="vertical"
            requiredMark={false}
            initialValues={{
              username: rememberedUsername ?? MOCK_USERNAME,
              password: MOCK_PASSWORD,
              remember: rememberedUsername !== null,
            }}
            onFinish={submitLogin}
            onValuesChange={() => setLoginError(false)}
          >
            <Form.Item
              name="username"
              label="账号"
              rules={[{ required: true, message: "请输入账号" }]}
            >
              <Input
                size="large"
                prefix={<UserOutlined aria-hidden="true" />}
                placeholder="请输入账号"
                autoComplete="username"
              />
            </Form.Item>
            <Form.Item
              name="password"
              label="密码"
              rules={[{ required: true, message: "请输入密码" }]}
            >
              <Input.Password
                size="large"
                prefix={<LockOutlined aria-hidden="true" />}
                placeholder="请输入密码"
                autoComplete="current-password"
              />
            </Form.Item>

            {loginError && (
              <Alert
                className="login-page__feedback"
                type="error"
                showIcon
                message="账号或密码错误"
              />
            )}

            <div className="login-page__options">
              <Form.Item name="remember" valuePropName="checked" noStyle>
                <Checkbox>记住账号</Checkbox>
              </Form.Item>
              <Button
                type="link"
                htmlType="button"
                onClick={() => {
                  setLoginError(false);
                  setForgotMessage(true);
                }}
              >
                忘记密码
              </Button>
            </div>

            {forgotMessage && (
              <Typography.Text className="login-page__feedback" type="secondary" role="status">
                Mock 环境暂不提供密码找回
              </Typography.Text>
            )}

            <Button
              className="login-page__submit"
              type="primary"
              size="large"
              htmlType="submit"
              aria-label="登录"
              block
            >
              登录
            </Button>
          </Form>
        </div>
      </section>
    </main>
  );
}

export default LoginPage;

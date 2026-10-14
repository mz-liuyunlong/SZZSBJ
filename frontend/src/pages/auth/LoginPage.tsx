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
import { Link } from "react-router-dom";
import { loginWithPassword } from "@/pages/auth/authApi";
import type { AuthUser } from "@/pages/auth/authTypes";
import {
  authenticateMockLogin,
  MOCK_PASSWORD,
  MOCK_USERNAME,
  type MockAuthUser,
} from "@/mocks/auth";
import "@/pages/auth/LoginPage.css";

export const REMEMBERED_USERNAME_KEY = "login_remembered_username";

interface LoginValues {
  username: string;
  password: string;
  remember?: boolean;
}

interface LoginPageProps {
  onLogin: (user: AuthUser) => void;
}

const isFrontendTestMode = () => import.meta.env.MODE === "test";

function toTestAuthUser(user: MockAuthUser): AuthUser {
  return {
    id: user.username === "admin" ? 1 : 2,
    username: user.username,
    role: user.role,
    displayName: user.displayName,
    account: user.account,
    avatarSrc: user.avatarSrc,
    online: user.online,
    roleKeys: [user.role],
    roles: [user.role === "admin" ? "管理员" : "普通用户"],
    permissions: user.role === "admin" ? ["*"] : [],
  };
}

async function authenticateLogin(values: LoginValues): Promise<AuthUser> {
  if (isFrontendTestMode()) {
    const mockUser = authenticateMockLogin(values.username, values.password);
    if (!mockUser) throw new Error("mock login failed");
    return toTestAuthUser(mockUser);
  }

  return loginWithPassword({
    username: values.username.trim(),
    password: values.password,
  });
}

function LoginPage({ onLogin }: LoginPageProps) {
  const [rememberedUsername] = useState(() =>
    localStorage.getItem(REMEMBERED_USERNAME_KEY),
  );
  const [loginError, setLoginError] = useState<string>();
  const [submitting, setSubmitting] = useState(false);

  const submitLogin: FormProps<LoginValues>["onFinish"] = async (values) => {
    setSubmitting(true);
    setLoginError(undefined);

    try {
      const user = await authenticateLogin(values);

      if (values.remember) {
        localStorage.setItem(REMEMBERED_USERNAME_KEY, values.username.trim());
      } else {
        localStorage.removeItem(REMEMBERED_USERNAME_KEY);
      }

      onLogin(user);
    } catch {
      setLoginError(
        isFrontendTestMode()
          ? "账号或密码错误"
          : "账号或密码错误，或该账号已停用",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="login-page" aria-label="登录表单区域">
      <Typography.Title level={2}>欢迎回来 👋</Typography.Title>
      <Typography.Paragraph type="secondary">
        请输入您的账户信息以开始管理掌上便捷系统
      </Typography.Paragraph>

      <Form<LoginValues>
        name="login"
        layout="vertical"
        requiredMark={false}
        initialValues={{
          username: rememberedUsername ?? (isFrontendTestMode() ? MOCK_USERNAME : ""),
          password: isFrontendTestMode() ? MOCK_PASSWORD : "",
          remember: rememberedUsername !== null,
        }}
        onFinish={submitLogin}
        onValuesChange={() => setLoginError(undefined)}
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
            message={loginError}
          />
        )}

        <div className="login-page__options">
          <Form.Item name="remember" valuePropName="checked" noStyle>
            <Checkbox>记住账号</Checkbox>
          </Form.Item>
          <div>
            <Link className="login-page__forgot-link" to="/forgot-password">
              忘记密码
            </Link>
          </div>
        </div>

        <Button
          className="login-page__submit"
          type="primary"
          size="large"
          htmlType="submit"
          aria-label="登录"
          loading={submitting}
          block
        >
          登录
        </Button>
      </Form>
    </section>
  );
}

export default LoginPage;

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
import { Link } from "react-router-dom";
import {
  isValidMockLogin,
  MOCK_PASSWORD,
  MOCK_USERNAME,
} from "../../mocks/auth";
import "./LoginPage.css";

export const REMEMBERED_USERNAME_KEY = "mock_login_remembered_username";

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

  const submitLogin: FormProps<LoginValues>["onFinish"] = (values) => {
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
    <section className="login-page" aria-label="登录表单区域">
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
          <Link className="login-page__forgot-link" to="/forgot-password">
            忘记密码
          </Link>
        </div>

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
    </section>
  );
}

export default LoginPage;

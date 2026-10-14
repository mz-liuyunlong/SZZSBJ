import {
  Alert,
  Button,
  Form,
  Input,
  Result,
  Typography,
  type FormProps,
} from "antd";
import { LockOutlined } from "@ant-design/icons";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { confirmPasswordReset } from "@/pages/auth/authApi";
import "@/pages/auth/LoginPage.css";

interface PasswordSetupValues {
  password: string;
  confirmPassword: string;
}

function PasswordSetupPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [submitting, setSubmitting] = useState(false);
  const [succeeded, setSucceeded] = useState(false);
  const [error, setError] = useState<string>();

  const submitPassword: FormProps<PasswordSetupValues>["onFinish"] = async (values) => {
    if (!token) {
      setError("密码设置链接无效或已过期");
      return;
    }

    setSubmitting(true);
    setError(undefined);

    try {
      await confirmPasswordReset({
        token,
        newPassword: values.password,
      });
      setSucceeded(true);
    } catch {
      setError("密码设置失败，请重新发起忘记密码流程");
    } finally {
      setSubmitting(false);
    }
  };

  if (!token) {
    return (
      <section className="login-page" aria-label="设置密码链接失效">
        <Result
          status="warning"
          title="密码设置链接无效"
          subTitle="请回到登录页重新发起忘记密码流程。"
          extra={
            <Link to="/forgot-password">
              <Button type="primary">重新发起</Button>
            </Link>
          }
        />
      </section>
    );
  }

  if (succeeded) {
    return (
      <section className="login-page" aria-label="设置密码成功">
        <Result
          status="success"
          title="登录密码设置成功"
          subTitle="请使用新密码登录掌上便捷系统。"
          extra={
            <Link to="/login">
              <Button type="primary">返回登录</Button>
            </Link>
          }
        />
      </section>
    );
  }

  return (
    <section className="login-page" aria-label="设置密码表单区域">
      <Typography.Title level={2}>设置登录密码</Typography.Title>
      <Typography.Paragraph type="secondary">
        请设置你的掌上便捷系统登录密码。密码至少 12 位。
      </Typography.Paragraph>

      {error && (
        <Alert
          className="login-page__feedback"
          type="error"
          showIcon
          message={error}
        />
      )}

      <Form<PasswordSetupValues>
        name="password-setup"
        layout="vertical"
        requiredMark={false}
        onFinish={submitPassword}
        onValuesChange={() => setError(undefined)}
      >
        <Form.Item
          name="password"
          label="新密码"
          rules={[
            { required: true, message: "请输入新密码" },
            { min: 12, message: "密码至少 12 位" },
          ]}
        >
          <Input.Password
            size="large"
            prefix={<LockOutlined aria-hidden="true" />}
            placeholder="请输入至少 12 位新密码"
            autoComplete="new-password"
          />
        </Form.Item>

        <Form.Item
          name="confirmPassword"
          label="确认新密码"
          dependencies={["password"]}
          rules={[
            { required: true, message: "请再次输入新密码" },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue("password") === value) {
                  return Promise.resolve();
                }
                return Promise.reject(new Error("两次输入的密码不一致"));
              },
            }),
          ]}
        >
          <Input.Password
            size="large"
            prefix={<LockOutlined aria-hidden="true" />}
            placeholder="请再次输入新密码"
            autoComplete="new-password"
          />
        </Form.Item>

        <Button
          className="login-page__submit"
          type="primary"
          size="large"
          htmlType="submit"
          loading={submitting}
          block
        >
          提交设置
        </Button>
      </Form>
    </section>
  );
}

export default PasswordSetupPage;

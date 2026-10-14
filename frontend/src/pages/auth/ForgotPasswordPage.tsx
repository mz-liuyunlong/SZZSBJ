import { Alert, Button, Form, Input, Typography, type FormProps } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { requestPasswordReset } from "@/pages/auth/authApi";
import "@/pages/auth/ForgotPasswordPage.css";

interface ForgotPasswordValues {
  realName: string;
}

function ForgotPasswordPage() {
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const submitRequest: FormProps<ForgotPasswordValues>["onFinish"] = async (values) => {
    setSubmitting(true);

    try {
      await requestPasswordReset({ realName: values.realName.trim() });
      setSubmitted(true);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="forgot-password-page" aria-label="忘记密码表单区域">
      <Typography.Title level={2}>忘记密码? 🙋🏻‍♂️</Typography.Title>
      <Typography.Paragraph type="secondary">
        请输入真实飞书姓名，系统将向本人飞书发送设置登录密码通知。
      </Typography.Paragraph>

      <Form<ForgotPasswordValues>
        name="forgot-password"
        layout="vertical"
        requiredMark={false}
        onFinish={submitRequest}
        onValuesChange={() => setSubmitted(false)}
      >
        <Form.Item
          name="realName"
          label="飞书姓名"
          rules={[
            { required: true, whitespace: true, message: "请输入你的真实姓名" },
          ]}
        >
          <Input
            size="large"
            placeholder="请输入你的真实姓名"
            autoComplete="name"
          />
        </Form.Item>

        {submitted && (
          <Alert
            className="forgot-password-page__feedback"
            type="success"
            showIcon
            message="如果姓名匹配到在职员工，系统会通过飞书发送设置密码通知。"
            role="status"
          />
        )}

        <div className="forgot-password-page__actions">
          <Button
            type="primary"
            size="large"
            htmlType="submit"
            loading={submitting}
            block
          >
            发送飞书设置密码通知
          </Button>
          <Button
            size="large"
            htmlType="button"
            onClick={() => navigate("/login")}
            block
          >
            返回
          </Button>
        </div>
      </Form>
    </section>
  );
}

export default ForgotPasswordPage;

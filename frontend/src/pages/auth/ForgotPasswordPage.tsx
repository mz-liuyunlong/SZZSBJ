/** Provides a frontend-only password reset mock without API or identity lookup. */
import { Alert, Button, Form, Input, Typography } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import "./ForgotPasswordPage.css";

interface ForgotPasswordValues {
  name: string;
}

function ForgotPasswordPage() {
  const navigate = useNavigate();
  const [submitted, setSubmitted] = useState(false);

  return (
    <section className="forgot-password-page" aria-label="忘记密码表单区域">
      <Typography.Title level={2}>忘记密码? 🙋🏻‍♂️</Typography.Title>
      <Typography.Paragraph type="secondary">
        请输入真实飞书姓名，系统将向本人飞书发送密码重置卡片，请在卡片中设置新密码。
      </Typography.Paragraph>

      <Alert
        className="forgot-password-page__disclaimer"
        type="warning"
        showIcon
        message="当前为前端模拟流程，不会实际发送飞书卡片。"
      />

      <Form<ForgotPasswordValues>
        name="mock-forgot-password"
        layout="vertical"
        requiredMark={false}
        onFinish={() => setSubmitted(true)}
        onValuesChange={() => setSubmitted(false)}
      >
        <Form.Item
          name="name"
          label="飞书姓名"
          rules={[{ required: true, whitespace: true, message: "请输入你的真实姓名" }]}
        >
          <Input
            size="large"
            placeholder="请输入你的真实姓名"
            autoComplete="off"
          />
        </Form.Item>

        {submitted && (
          <Alert
            className="forgot-password-page__feedback"
            type="success"
            showIcon
            message="模拟提交成功：当前不会实际发送飞书卡片。"
            role="status"
          />
        )}

        <div className="forgot-password-page__actions">
          <Button type="primary" size="large" htmlType="submit" block>
            发送重置卡片
          </Button>
          <Button size="large" htmlType="button" onClick={() => navigate("/login")} block>
            返回
          </Button>
        </div>
      </Form>
    </section>
  );
}

export default ForgotPasswordPage;

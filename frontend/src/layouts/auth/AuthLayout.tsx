/** Provides the shared brand and responsive frame for frontend-only auth pages. */
import { Typography } from "antd";
import type { ReactNode } from "react";
import "./AuthLayout.css";

interface AuthLayoutProps {
  children: ReactNode;
}

function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <main className="auth-layout">
      <section className="auth-layout__visual" aria-label="掌上便捷品牌介绍">
        <div className="auth-layout__brand">
          <img src="/favicon.ico" alt="掌上便捷标识" width={36} height={36} />
          <Typography.Title level={4}>掌上便捷</Typography.Title>
        </div>
        <div className="auth-layout__illustration" aria-hidden="true">
          <svg viewBox="0 0 520 360" role="presentation">
            <defs>
              <linearGradient id="auth-card-gradient" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stopColor="#ffffff" />
                <stop offset="1" stopColor="#dbeafe" />
              </linearGradient>
            </defs>
            <circle cx="260" cy="180" r="150" fill="#ffffff" opacity="0.42" />
            <rect x="92" y="74" width="336" height="220" rx="28" fill="url(#auth-card-gradient)" />
            <rect x="128" y="112" width="128" height="18" rx="9" fill="#91caff" />
            <rect x="128" y="148" width="210" height="12" rx="6" fill="#d6e4ff" />
            <rect x="128" y="178" width="164" height="12" rx="6" fill="#d6e4ff" />
            <path d="M135 252 195 210 246 232 326 158 390 205" fill="none" stroke="#1677ff" strokeWidth="12" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx="195" cy="210" r="12" fill="#52c41a" />
            <circle cx="326" cy="158" r="12" fill="#1677ff" />
          </svg>
        </div>
        <div className="auth-layout__visual-copy">
          <Typography.Title level={2}>让运营管理更清晰</Typography.Title>
          <Typography.Text>统一工作入口，专注每天真正重要的数据。</Typography.Text>
        </div>
      </section>

      <section className="auth-layout__form-panel" aria-label="认证表单区域">
        <div className="auth-layout__form-content">{children}</div>
      </section>
    </main>
  );
}

export default AuthLayout;

/** 页面右上角「？帮助」：说明文字收在抽屉里，页面正文只留筛选 / 统计卡 / 表格（照 PMC 页面）。正式版可换成 /help/*.html。 */
import { Button, Drawer, Typography } from "antd";
import { useState, type ReactNode } from "react";

export interface HelpSection { title: string; body: ReactNode }

function HelpButton({ title, sections }: { title: string; sections: HelpSection[] }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>？帮助</Button>
      <Drawer open={open} width={560} title={`${title} · 帮助`} onClose={() => setOpen(false)}>
        <Typography>
          {sections.map((section) => (
            <div key={section.title}>
              <Typography.Title level={5}>{section.title}</Typography.Title>
              <Typography.Paragraph>{section.body}</Typography.Paragraph>
            </div>
          ))}
        </Typography>
      </Drawer>
    </>
  );
}

export default HelpButton;

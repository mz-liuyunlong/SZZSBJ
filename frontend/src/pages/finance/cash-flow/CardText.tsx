/** 审批单事由 / 明细：有银行卡号时默认只露后 4 位，点小眼睛切换全号（规则见 cardMask.ts）。 */
import { EyeInvisibleOutlined, EyeOutlined } from "@ant-design/icons";
import { Button, Tooltip } from "antd";
import { useState } from "react";
import { hasCard, maskCards } from "@/pages/finance/cash-flow/cardMask";

/** 带小眼睛的文字：有卡号时默认打码，点眼睛切换全号 / 打码；没有卡号原样显示。 */
export function CardText({ text }: { text: string }) {
  const [shown, setShown] = useState(false);
  if (!hasCard(text)) return <>{text}</>;
  const label = shown ? "隐藏卡号" : "显示完整卡号";
  return (
    <>
      {shown ? text : maskCards(text)}
      <Tooltip title={label}>
        <Button type="link" size="small" aria-label={label} icon={shown ? <EyeInvisibleOutlined /> : <EyeOutlined />} onClick={() => setShown((current) => !current)} />
      </Tooltip>
    </>
  );
}

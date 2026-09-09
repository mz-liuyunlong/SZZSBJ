/** Keeps report-page reset actions visually and semantically consistent. */
import { Button, type ButtonProps } from "antd";

function ResetButton(props: Omit<ButtonProps, "children">) {
  const className = ["report-table-reset-button", props.className]
    .filter(Boolean)
    .join(" ");
  return <Button {...props} className={className}>重置</Button>;
}

export default ResetButton;

/** Keeps report-page reset actions visually and semantically consistent. */
import { Button, type ButtonProps } from "antd";

function ResetButton(props: Omit<ButtonProps, "children">) {
  return <Button {...props}>重置</Button>;
}

export default ResetButton;

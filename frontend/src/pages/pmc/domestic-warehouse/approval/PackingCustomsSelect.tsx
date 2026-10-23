/** Display only the business result; untouched controls retain server-derived provenance. */
import { Select } from "antd";
import type { ApprovalCandidate } from "./packingApprovalApi";
import type { CustomsChoice } from "./packingCustoms";

interface Props {
  row?: ApprovalCandidate | null;
  value?: CustomsChoice;
  onChange?: (value: CustomsChoice) => void;
  disabled?: boolean;
  id?: string;
  size?: "small" | "middle" | "large";
  "aria-label"?: string;
}
export default function PackingCustomsSelect({ row, value = "default", onChange, ...rest }: Props) {
  const displayed = value === "default" ? row?.customs_default ? "declare" : "skip" : value;
  return <Select {...rest} className="domestic-approval__customs-select" value={displayed}
    options={[{ value: "declare", label: "报关" }, { value: "skip", label: "不报关" }]}
    onChange={(choice: "declare" | "skip") => onChange?.(choice)} />;
}

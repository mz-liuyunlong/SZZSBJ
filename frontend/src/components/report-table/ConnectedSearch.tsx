/** Shared connected search control for dense report toolbars. */
import { FilterOutlined, SearchOutlined } from "@ant-design/icons";
import { Button, Input, Select, Tooltip, type SelectProps } from "antd";
import type { ReactNode } from "react";
import "@/components/report-table/reportTable.css";

interface ConnectedSearchProps {
  className?: string;
  typeAriaLabel: string;
  typeOptions: SelectProps["options"];
  typeValue: string;
  inputAriaLabel: string;
  inputPlaceholder: string;
  inputValue: string;
  searchAriaLabel?: string;
  batchControl?: ReactNode;
  filterAction?: {
    ariaLabel: string;
    tooltip?: string;
    onClick: () => void;
  };
  onTypeChange: (value: string) => void;
  onInputChange: (value: string) => void;
  onSearch: () => void;
}

function ConnectedSearch({
  className,
  typeAriaLabel,
  typeOptions,
  typeValue,
  inputAriaLabel,
  inputPlaceholder,
  inputValue,
  searchAriaLabel = "搜索",
  batchControl,
  filterAction,
  onTypeChange,
  onInputChange,
  onSearch,
}: ConnectedSearchProps) {
  return (
    <div className={["report-table-connected-search", className].filter(Boolean).join(" ")}>
      <Select
        aria-label={typeAriaLabel}
        value={typeValue}
        options={typeOptions}
        onChange={onTypeChange}
      />
      <Input
        allowClear
        aria-label={inputAriaLabel}
        placeholder={inputPlaceholder}
        value={inputValue}
        onChange={(event) => onInputChange(event.target.value)}
        onPressEnter={onSearch}
      />
      <Button
        className="report-table-connected-search__search"
        aria-label={searchAriaLabel}
        icon={<SearchOutlined aria-hidden="true" />}
        onClick={onSearch}
      />
      {filterAction && (
        <Tooltip title={filterAction.tooltip}>
          <Button
            className="report-table-connected-search__filter"
            aria-label={filterAction.ariaLabel}
            icon={<FilterOutlined aria-hidden="true" />}
            onClick={filterAction.onClick}
          />
        </Tooltip>
      )}
      {batchControl}
    </div>
  );
}

export default ConnectedSearch;

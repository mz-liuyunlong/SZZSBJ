import { CheckOutlined } from "@ant-design/icons";
import { Button, Checkbox, Select, Space, Typography } from "antd";
import { useMemo, useState, type CSSProperties, type ReactNode } from "react";
import {
  mergeSelectedFilterOptions,
  selectedValuesFromFilterValue,
  type ReportFilterOption,
} from "@/shared/report-filters/filterOptions";
import "@/shared/report-filters/ReportFacetSelect.css";

export type ReportFacetSelectValue = string | string[] | undefined;

interface ReportFacetSelectProps {
  mode?: "multiple";
  ariaLabel: string;
  placeholder: string;
  value?: ReportFacetSelectValue;
  options: ReportFilterOption[];
  unit?: string;
  className?: string;
  optionCheckboxClassName?: string;
  triggerWidth?: number | string;
  popupWidth?: number;
  allowClear?: boolean;
  showSearch?: boolean;
  confirmOnMultiple?: boolean;
  renderOptionLabel?: (option: ReportFilterOption) => ReactNode;
  onChange: (value: ReportFacetSelectValue) => void;
}

const selectedLabel = (values: string[], unit: string, fallback: string) => {
  if (values.length === 0) return fallback;
  return `已选 ${values.length} ${unit}`;
};

const defaultReportFacetOptionLabel = (option: ReportFilterOption) => (
  <span className="report-facet-select__option">
    <span>{option.label}</span>
    {option.count !== undefined && (
      <Typography.Text type="secondary">（{option.count}）</Typography.Text>
    )}
  </span>
);

const normalizeMultipleValue = (value: ReportFacetSelectValue) => (
  selectedValuesFromFilterValue(value)
);

const cssSize = (value: number | string) => (
  typeof value === "number" ? `${value}px` : value
);

const estimateTextWidth = (text: string) => Array.from(text).reduce((width, char) => {
  if (/[\u4e00-\u9fff]/.test(char)) return width + 14;
  if (/[A-Z]/.test(char)) return width + 8;
  if (/[a-z0-9]/.test(char)) return width + 7;
  if (/\s/.test(char)) return width + 4;
  return width + 8;
}, 0);

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

function ReportFacetSelect({
  mode,
  ariaLabel,
  placeholder,
  value,
  options,
  unit = "项",
  className = "report-filter-select",
  optionCheckboxClassName,
  triggerWidth,
  popupWidth,
  allowClear = true,
  showSearch = true,
  confirmOnMultiple = true,
  renderOptionLabel = defaultReportFacetOptionLabel,
  onChange,
}: ReportFacetSelectProps) {
  const isMultiple = mode === "multiple";
  const shouldConfirm = isMultiple && confirmOnMultiple;
  const confirmedValues = useMemo(() => normalizeMultipleValue(value), [value]);
  const [open, setOpen] = useState(false);
  const [draftValues, setDraftValues] = useState<string[]>(confirmedValues);

  const activeValues = shouldConfirm && open ? draftValues : confirmedValues;
  const mergedOptions = mergeSelectedFilterOptions(activeValues, options);
  const selectableValues = mergedOptions
    .filter((option) => !option.disabled)
    .map((option) => option.value);

  const selectedValueSet = new Set(activeValues);
  const selectedSelectableCount = selectableValues.filter((item) => selectedValueSet.has(item)).length;
  const allChecked = selectableValues.length > 0 && selectedSelectableCount === selectableValues.length;
  const partiallyChecked = selectedSelectableCount > 0 && selectedSelectableCount < selectableValues.length;

  const maxSelectedText = selectedLabel(selectableValues, unit, placeholder);
  const maxDisplayText = [placeholder, maxSelectedText]
    .sort((left, right) => estimateTextWidth(right) - estimateTextWidth(left))[0];

  const autoTriggerWidth = `${clamp(estimateTextWidth(maxDisplayText) + 58, 104, 188)}px`;
  const fixedTriggerWidth = triggerWidth == null ? autoTriggerWidth : cssSize(triggerWidth);
  const resolvedPopupWidth = popupWidth ?? (isMultiple ? 360 : undefined);

  const selectStyle = {
    "--report-facet-select-width": fixedTriggerWidth,
    width: fixedTriggerWidth,
    minWidth: fixedTriggerWidth,
    maxWidth: fixedTriggerWidth,
    flex: `0 0 ${fixedTriggerWidth}`,
  } as CSSProperties & Record<"--report-facet-select-width", string>;

  const selectOptions = mergedOptions.map((option) => ({
    value: option.value,
    label: renderOptionLabel(option),
    searchLabel: option.label,
    disabled: option.disabled,
  }));

  const handleOpenChange = (nextOpen: boolean) => {
    if (nextOpen) {
      setDraftValues(confirmedValues);
    } else if (shouldConfirm) {
      setDraftValues(confirmedValues);
    }
    setOpen(nextOpen);
  };

  const handleChange = (nextValue: ReportFacetSelectValue) => {
    if (shouldConfirm) {
      setDraftValues(normalizeMultipleValue(nextValue));
      return;
    }

    onChange(nextValue);
  };

  const handleClear = () => {
    if (isMultiple) {
      setDraftValues([]);
      onChange([]);
      setOpen(false);
      return;
    }

    onChange(undefined);
  };

  const toggleSelectAll = (checked: boolean) => {
    setDraftValues(checked ? selectableValues : []);
  };

  const applyDraft = () => {
    onChange(draftValues);
    setOpen(false);
  };

  const cancelDraft = () => {
    setDraftValues(confirmedValues);
    setOpen(false);
  };

  const popupRender = shouldConfirm
    ? (originNode: ReactNode) => (
      <div className="report-facet-select__popup">
        <div
          className="report-facet-select__header"
          onMouseDown={(event) => event.preventDefault()}
        >
          <Checkbox
            checked={allChecked}
            indeterminate={partiallyChecked}
            disabled={selectableValues.length === 0}
            onChange={(event) => toggleSelectAll(event.target.checked)}
          >
            全选
          </Checkbox>
          <div className="report-facet-select__header-right">
            <Typography.Text type="secondary">
              可选 {selectableValues.length} {unit}
            </Typography.Text>
            <Button
              size="small"
              type="link"
              aria-label="清空"
              disabled={draftValues.length === 0}
              onClick={() => setDraftValues([])}
            >
              清空
            </Button>
          </div>
        </div>

        {originNode}

        <div
          className="report-facet-select__footer"
          onMouseDown={(event) => event.preventDefault()}
        >
          <Typography.Text type="secondary" className="report-facet-select__summary">
            {draftValues.length > 0 ? `已选 ${draftValues.length} ${unit}` : "未选择"}
          </Typography.Text>
          <Space size={8}>
            <Button size="small" aria-label="取消" onClick={cancelDraft}>取消</Button>
            <Button size="small" type="primary" aria-label="确定" onClick={applyDraft}>确定</Button>
          </Space>
        </div>
      </div>
    )
    : undefined;

  return (
    <Select
      mode={mode}
      allowClear={allowClear}
      showSearch={showSearch}
      optionFilterProp="searchLabel"
      menuItemSelectedIcon={isMultiple ? null : undefined}
      className={`report-facet-select ${className}`.trim()}
      classNames={{ popup: { root: "report-filter-select-dropdown" } }}
      aria-label={ariaLabel}
      placeholder={placeholder}
      value={isMultiple ? activeValues : value}
      style={selectStyle}
      maxTagCount={isMultiple ? 0 : undefined}
      maxTagPlaceholder={isMultiple ? () => selectedLabel(activeValues, unit, placeholder) : undefined}
      popupMatchSelectWidth={resolvedPopupWidth ? false : undefined}
      styles={resolvedPopupWidth ? {
        popup: {
          root: {
            width: resolvedPopupWidth,
            minWidth: resolvedPopupWidth,
            maxWidth: resolvedPopupWidth,
          },
        },
      } : undefined}
      open={shouldConfirm ? open : undefined}
      popupRender={popupRender}
      options={selectOptions}
      optionRender={(option) => {
        const optionValue = String(option.value ?? "");

        if (isMultiple) {
          return (
            <Checkbox
              className={optionCheckboxClassName}
              checked={activeValues.includes(optionValue)}
              aria-label={`${ariaLabel}选项：${optionValue}`}
              tabIndex={-1}
            >
              {option.label}
            </Checkbox>
          );
        }

        const checked = value === optionValue;
        return (
          <span className="report-facet-select__single-option">
            <span className="report-facet-select__single-option-label">{option.label}</span>
            {checked && <CheckOutlined aria-hidden="true" className="report-facet-select__single-option-check" />}
          </span>
        );
      }}
      onOpenChange={shouldConfirm ? handleOpenChange : undefined}
      onClear={handleClear}
      onChange={(nextValue) => handleChange(nextValue as ReportFacetSelectValue)}
    />
  );
}

export default ReportFacetSelect;

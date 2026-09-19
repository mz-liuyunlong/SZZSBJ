import { UnorderedListOutlined } from "@ant-design/icons";
import { Button, Input, Popover, Space, Typography, type SelectProps } from "antd";
import { useState } from "react";
import ConnectedSearch from "@/components/report-table/ConnectedSearch";

export interface CommittedSearchPayload {
  searchField: string;
  keyword: string;
}

interface BatchSearchConfig {
  ariaLabel: string;
  placeholder: string;
  unsupportedMessage?: string;
  isSupported?: (searchField: string) => boolean;
  onCommit: (values: string[], searchField: string) => void;
  onMessage: (content: string) => void;
}

interface CommittedSearchProps {
  className?: string;
  typeAriaLabel: string;
  typeOptions: SelectProps["options"];
  typeValue: string;
  inputAriaLabel: string;
  inputPlaceholder: string;
  inputValue: string;
  searchAriaLabel?: string;
  batch?: BatchSearchConfig;
  onCommit: (payload: CommittedSearchPayload) => void;
}

const parseBatchValues = (value: string) => (
  value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
);

function CommittedSearch({
  className,
  typeAriaLabel,
  typeOptions,
  typeValue,
  inputAriaLabel,
  inputPlaceholder,
  inputValue,
  searchAriaLabel = "搜索",
  batch,
  onCommit,
}: CommittedSearchProps) {
  const [draftType, setDraftType] = useState(typeValue);
  const [draftKeyword, setDraftKeyword] = useState(inputValue);
  const [lastSyncKey, setLastSyncKey] = useState(`${typeValue}\u0000${inputValue}`);
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchText, setBatchText] = useState("");

  const syncKey = `${typeValue}\u0000${inputValue}`;
  if (syncKey !== lastSyncKey) {
    setLastSyncKey(syncKey);
    setDraftType(typeValue);
    setDraftKeyword(inputValue);
  }

  const batchSupported = batch?.isSupported?.(draftType) ?? true;

  const submitKeyword = () => {
    onCommit({
      searchField: draftType,
      keyword: draftKeyword.trim(),
    });
  };

  const submitBatchSearch = () => {
    if (!batch) return;

    if (!batchSupported) {
      batch.onMessage(batch.unsupportedMessage ?? "当前搜索类型不支持批量搜索");
      return;
    }

    const values = parseBatchValues(batchText);
    if (values.length === 0) {
      batch.onMessage("请输入搜索内容");
      return;
    }
    if (values.length > 1000) {
      batch.onMessage("最多支持1000行");
      return;
    }

    batch.onCommit(values, draftType);
    setBatchOpen(false);
  };

  const batchControl = batch ? (
    <Popover
      trigger="click"
      placement="bottomRight"
      open={batchOpen}
      onOpenChange={(open) => {
        if (open && !batchSupported) {
          batch.onMessage(batch.unsupportedMessage ?? "当前搜索类型不支持批量搜索");
          return;
        }
        setBatchOpen(open);
      }}
      content={(
        <div className="report-committed-search__batch-popover" aria-label={batch.ariaLabel}>
          <Typography.Text strong>精确搜索，一行一项，最多支持1000行</Typography.Text>
          <Input.TextArea
            aria-label={`${batch.ariaLabel}内容`}
            placeholder={batch.placeholder}
            rows={8}
            value={batchText}
            onChange={(event) => setBatchText(event.target.value)}
          />
          <Space className="report-committed-search__batch-actions">
            <Button onClick={() => setBatchText("")}>清空</Button>
            <Button onClick={() => setBatchOpen(false)}>关闭</Button>
            <Button type="primary" onClick={submitBatchSearch}>搜索</Button>
          </Space>
        </div>
      )}
    >
      <Button
        className="report-table-connected-search__batch"
        aria-label={batch.ariaLabel}
        icon={<UnorderedListOutlined aria-hidden="true" />}
      />
    </Popover>
  ) : undefined;

  return (
    <ConnectedSearch
      className={className}
      typeAriaLabel={typeAriaLabel}
      typeOptions={typeOptions}
      typeValue={draftType}
      inputAriaLabel={inputAriaLabel}
      inputPlaceholder={inputPlaceholder}
      inputValue={draftKeyword}
      searchAriaLabel={searchAriaLabel}
      batchControl={batchControl}
      onTypeChange={setDraftType}
      onInputChange={setDraftKeyword}
      onSearch={submitKeyword}
    />
  );
}

export default CommittedSearch;

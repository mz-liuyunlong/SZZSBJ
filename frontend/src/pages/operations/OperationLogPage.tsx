import { FileTextOutlined, RobotOutlined } from "@ant-design/icons";
import { Button, Card, Input, message, Modal, Space, Typography } from "antd";
import { useMemo, useState, type Key } from "react";
import PageShell from "@/components/page/PageShell";
import RuntimeColumnConfigDrawer, {
  type RuntimeColumnGroup,
} from "@/components/report-table/RuntimeColumnConfigDrawer";
import {
  REPORT_TABLE_DEFAULT_PAGE_SIZE,
  normalizeReportTablePageSize,
} from "@/components/report-table/pagination";
import type { NavigationPage } from "@/config/navigation";
import OperationLogBatchModal from "@/pages/operations/components/OperationLogBatchModal";
import OperationLogLinkEditorModal from "@/pages/operations/components/OperationLogLinkEditorModal";
import OperationLogTable from "@/pages/operations/components/OperationLogTable";
import OperationLogToolbar from "@/pages/operations/components/OperationLogToolbar";
import {
  operationLogOwners,
  operationLogRows,
  operationLogStores,
  operationLogWorkTypeValues,
  operationSystemRecords,
} from "@/pages/operations/operationLogMockData";
import {
  createOperationLogInitialFilters,
  createSystemDraft,
  defaultOperationLogColumnWidths,
  filterOperationLogRows,
  fixedOperationLogColumnKeys,
  operationLogColumnFields,
  type OperationLogBatchWriteValues,
  type OperationLogFilters,
  type OperationLogLinkFormValues,
  type OperationLogRow,
} from "@/pages/operations/operationLogTypes";
import "@/pages/operations/OperationLogPage.css";

const TEMPLATE_PENDING = "列模板接口待接入";
const DOWNLOAD_PENDING = "下载接口待接入";

const columnGroups: RuntimeColumnGroup[] = [
  { title: "运营日志字段", fields: [...operationLogColumnFields] },
];

interface OperationLogPageProps {
  page: NavigationPage;
}

function OperationLogPage({ page }: OperationLogPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [rows, setRows] = useState(operationLogRows);
  const [filters, setFilters] = useState<OperationLogFilters>(createOperationLogInitialFilters);
  const [batchSearchOpen, setBatchSearchOpen] = useState(false);
  const [batchSearchText, setBatchSearchText] = useState("");
  const [batchModalOpen, setBatchModalOpen] = useState(false);
  const [columnConfigOpen, setColumnConfigOpen] = useState(false);
  const [appliedColumnKeys, setAppliedColumnKeys] = useState(operationLogColumnFields.map((field) => field.key));
  const [columnWidths, setColumnWidths] = useState(defaultOperationLogColumnWidths);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(REPORT_TABLE_DEFAULT_PAGE_SIZE);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [linkEditor, setLinkEditor] = useState<{
    row: OperationLogRow;
    entryType: "keyword" | "ad";
  }>();

  const resetPageAndSelection = () => {
    setCurrentPage(1);
    setSelectedRowKeys([]);
  };

  const updateFilters = (nextFilters: OperationLogFilters) => {
    setFilters(nextFilters);
    resetPageAndSelection();
  };

  const filteredRows = useMemo(() => filterOperationLogRows(rows, filters), [filters, rows]);

  const resetFilters = () => {
    setFilters(createOperationLogInitialFilters());
    setBatchSearchText("");
    resetPageAndSelection();
  };

  const updateRow = (productId: string, patch: Partial<OperationLogRow>) => {
    setRows((currentRows) => currentRows.map((row) => (
      row.productId === productId ? { ...row, ...patch } : row
    )));
  };

  const fillBySystem = () => {
    setRows((currentRows) => currentRows.map((row) => {
      const records = operationSystemRecords.filter((record) => record.productId === row.productId);
      return {
        ...row,
        manualLog: createSystemDraft(records),
        status: "草稿",
        workType: records.length ? "系统日志核对" : row.workType,
      };
    }));
    void messageApi.success("已根据系统日志生成草稿");
  };

  const markNoChange = () => {
    setRows((currentRows) => currentRows.map((row) => (
      row.manualLog.trim()
        ? row
        : { ...row, manualLog: "今日无需调整，数据正常。", workType: "无需调整", status: "草稿" }
    )));
    void messageApi.success("空白日志已填写“今日无需调整”");
  };

  const applyBatchSearch = () => {
    const values = batchSearchText
      .split(/\n+/)
      .map((item) => item.trim())
      .filter(Boolean)
      .slice(0, 1000);

    updateFilters({ ...filters, batchValues: values });
    setBatchSearchOpen(false);
    void messageApi.success(`已按 ${values.length} 项批量搜索`);
  };

  const applyBatchWrite = (values: OperationLogBatchWriteValues) => {
    if (values.productIds.length === 0) {
      void messageApi.warning("请先选择商品ID");
      return;
    }

    if (!values.logText.trim() && values.workTypes.length === 0) {
      void messageApi.warning("请填写日志内容或选择工作类型");
      return;
    }

    setRows((currentRows) => currentRows.map((row) => {
      if (!values.productIds.includes(row.productId)) return row;

      const nextLogText = values.logText.trim();
      let manualLog = row.manualLog;
      if (nextLogText) {
        if (values.writeMode === "replace") manualLog = nextLogText;
        else if (values.writeMode === "onlyBlank" && !row.manualLog.trim()) manualLog = nextLogText;
        else if (values.writeMode === "append") manualLog = `${row.manualLog.trim() ? `${row.manualLog.trim()}\n` : ""}${nextLogText}`;
      }

      return {
        ...row,
        manualLog,
        workType: values.workTypes[0] ?? row.workType,
        status: "草稿",
      };
    }));

    setBatchModalOpen(false);
    void messageApi.success(`已批量写入 ${values.productIds.length} 个商品ID`);
  };

  const saveEntry = (
    row: OperationLogRow,
    entryType: "keyword" | "ad",
    values: OperationLogLinkFormValues,
  ) => {
    updateRow(row.productId, {
      keywordEntryStatus: entryType === "keyword" ? "ok" : row.keywordEntryStatus,
      adEntryStatus: entryType === "ad" ? "ok" : row.adEntryStatus,
    });
    setLinkEditor(undefined);
    void messageApi.success(`${row.productId} 的${entryType === "keyword" ? "关键词" : "广告"}入口已保存并启用：${values.entryName}`);
  };

  const headerActions = (
    <Space size={8}>
      <Button icon={<RobotOutlined />} onClick={fillBySystem}>系统记录生成草稿</Button>
      <Button onClick={markNoChange}>空白填无需调整</Button>
      <Button className="operation-log__batch-write-button" type="primary" icon={<FileTextOutlined />} onClick={() => setBatchModalOpen(true)}>批量写日志</Button>
    </Space>
  );

  return (
    <PageShell page={page}>
      {messageContextHolder}
      <div className="operation-log">
        <div className="operation-log__page-header">
          <div>
            <Typography.Title level={3}>商品ID批量快填版</Typography.Title>
            <Typography.Paragraph>
              商品ID维度记录运营日志；每个商品ID旁边保留「词 / 广」快捷入口；缺失时可直接点击补录，不再只做提示。
            </Typography.Paragraph>
          </div>
        </div>

        <Card size="small" className="operation-log__toolbar-card">
          <OperationLogToolbar
            filters={filters}
            owners={operationLogOwners}
            stores={operationLogStores}
            workTypes={operationLogWorkTypeValues}
            onChange={updateFilters}
            onReset={resetFilters}
            onOpenBatchSearch={() => setBatchSearchOpen(true)}
            onOpenColumnConfig={() => setColumnConfigOpen(true)}
            onDownload={() => void messageApi.info(DOWNLOAD_PENDING)}
          />
        </Card>

        <OperationLogTable
          rows={filteredRows}
          systemRecords={operationSystemRecords}
          appliedColumnKeys={appliedColumnKeys}
          columnWidths={columnWidths}
          currentPage={currentPage}
          pageSize={pageSize}
          selectedRowKeys={selectedRowKeys}
          onColumnWidthChange={(key, width) => setColumnWidths((current) => ({
            ...current,
            [key]: width,
          }))}
          onCurrentPageChange={setCurrentPage}
          onPageSizeChange={(nextPageSize) => {
            setPageSize(normalizeReportTablePageSize(nextPageSize));
            resetPageAndSelection();
          }}
          onSelectionChange={setSelectedRowKeys}
          onCopy={(text) => void navigator.clipboard?.writeText(text)}
          onOpenProduct={(row) => void messageApi.info(`打开 ${row.productId} 诊断 / 写日志抽屉待接入`)}
          onOpenEntryEditor={(row, entryType) => setLinkEditor({ row, entryType })}
          onManualLogChange={(productId, manualLog) => updateRow(productId, { manualLog, status: "草稿" })}
          onSaveRow={(row) => {
            updateRow(row.productId, { status: "已保存" });
            void messageApi.success(`${row.productId} 日志已保存`);
          }}
          onBulkSaveDraft={() => void messageApi.success("已保存草稿")}
          onSubmitAll={() => void messageApi.success("已提交今日运营日志")}
          tableActions={headerActions}
        />

        <RuntimeColumnConfigDrawer
          open={columnConfigOpen}
          groups={columnGroups}
          fixedKeys={fixedOperationLogColumnKeys}
          defaultKeys={operationLogColumnFields.map((field) => field.key)}
          appliedKeys={appliedColumnKeys}
          onApply={setAppliedColumnKeys}
          onClose={() => setColumnConfigOpen(false)}
          onSaveTemplate={() => void messageApi.info(TEMPLATE_PENDING)}
        />

        <OperationLogBatchModal
          open={batchModalOpen}
          rows={filteredRows}
          onClose={() => setBatchModalOpen(false)}
          onApply={applyBatchWrite}
        />

        <OperationLogLinkEditorModal
          row={linkEditor?.row}
          entryType={linkEditor?.entryType}
          onClose={() => setLinkEditor(undefined)}
          onKeepMissing={(row, entryType) => {
            setLinkEditor(undefined);
            void messageApi.info(`${row.productId} 仍保留${entryType === "keyword" ? "关键词" : "广告"}缺失状态`);
          }}
          onSave={saveEntry}
        />

        <Modal
          open={batchSearchOpen}
          title="批量搜索商品ID"
          onCancel={() => setBatchSearchOpen(false)}
          onOk={applyBatchSearch}
          okText="搜索"
          cancelText="取消"
          destroyOnHidden
        >
          <Typography.Paragraph type="secondary">
            一行一个商品ID / SKU / 商品名 / 店铺 / 日期关键词，最多1000行。
          </Typography.Paragraph>
          <Input.TextArea
            value={batchSearchText}
            rows={8}
            placeholder={"WMT-80000001\nZS-KT-001\n美国一店\n2026-09-13"}
            onChange={(event) => setBatchSearchText(event.target.value)}
          />
        </Modal>
      </div>
    </PageShell>
  );
}

export default OperationLogPage;

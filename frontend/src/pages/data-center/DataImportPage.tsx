/** No-API data import page for file upload type selection, validation and recent records. */
import {
  CloudDownloadOutlined,
  InboxOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import {
  Button,
  Card,
  Input,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMemo, useState } from "react";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import { dataImportRecords, dataImportTypes } from "@/pages/data-center/dataImportMockData";
import {
  createInitialDataImportFilters,
  type DataImportFilters,
  type DataImportRecord,
  type DataImportStatus,
  type DataImportTypeOption,
} from "@/pages/data-center/dataImportTypes";
import "@/pages/data-center/DataImportPage.css";

interface DataImportPageProps {
  page: NavigationPage;
}

const statusColor: Record<DataImportStatus, string> = {
  成功: "success",
  部分失败: "warning",
  失败: "error",
};



function DataImportPage({ page }: DataImportPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [selectedType, setSelectedType] = useState<DataImportTypeOption>(dataImportTypes[2]);
  const [uploaded, setUploaded] = useState(false);
  const [currentFile, setCurrentFile] = useState("");
  const [filters, setFilters] = useState(createInitialDataImportFilters());

  const filteredRows = useMemo(() => {
    const keyword = filters.keyword.trim().toLocaleLowerCase();

    return dataImportRecords.filter((record) => (
      (!filters.startDate || record.uploadedAt.slice(0, 10) >= filters.startDate)
      && (!filters.endDate || record.uploadedAt.slice(0, 10) <= filters.endDate)
      && (!filters.typeName || record.typeName === filters.typeName)
      && (!filters.status || record.status === filters.status)
      && (!keyword
        || record.fileName.toLocaleLowerCase().includes(keyword)
        || record.operator.toLocaleLowerCase().includes(keyword))
    ));
  }, [filters]);

  const selectType = (type: DataImportTypeOption) => {
    setSelectedType(type);
    setUploaded(false);
    setCurrentFile("");
    void messageApi.success(`已选择：${type.name}`);
  };

  const simulateUpload = () => {
    setUploaded(true);
    setCurrentFile(`${selectedType.name}_示例文件.xlsx`);
    void messageApi.success("上传完成");
  };

  const confirmImport = () => {
    if (!uploaded) {
      void messageApi.warning("请先上传文件");
      return;
    }

    void messageApi.success(`已确认导入：${selectedType.name}`);
  };

  const downloadTemplate = () => {
    void messageApi.info("模板下载接口待接入");
  };

  const setFilter = <Key extends keyof DataImportFilters>(key: Key, value: DataImportFilters[Key]) => {
    setFilters((current) => ({ ...current, [key]: value }));
  };

  const columns: ColumnsType<DataImportRecord> = [
    {
      title: "上传时间",
      dataIndex: "uploadedAt",
      width: 150,
      fixed: "left",
    },
    {
      title: "数据类型",
      dataIndex: "typeName",
      width: 170,
    },
    {
      title: "文件名",
      dataIndex: "fileName",
      width: 210,
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 110,
      render: (value: DataImportStatus) => <Tag color={statusColor[value]}>{value}</Tag>,
    },
    {
      title: "总行数",
      dataIndex: "totalRows",
      width: 100,
    },
    {
      title: "成功",
      dataIndex: "successRows",
      width: 100,
    },
    {
      title: "失败",
      dataIndex: "failedRows",
      width: 100,
    },
    {
      title: "操作人",
      dataIndex: "operator",
      width: 100,
    },
    {
      title: "下载",
      key: "download",
      width: 210,
      fixed: "right",
      render: (_, record) => (
        <Space size={6}>
          <Button size="small">原文件</Button>
          <Button size="small">结果</Button>
          {record.failedRows > 0 && <Button size="small">错误</Button>}
        </Space>
      ),
    },
  ];

  const uploadHasWarning = uploaded && ["keywords", "auto_ads"].includes(selectedType.id);

  return (
    <PageShell page={page}>
      {messageContextHolder}
      <div className="data-import">
        <section className="data-import__head">
          <div>
            <Typography.Title level={3}>数据导入</Typography.Title>
            <Typography.Paragraph type="secondary">
              先选择上传的数据类型，再上传文件。页面使用自然高度，不强制铺满屏幕。
            </Typography.Paragraph>
          </div>
          <Space>
            <Button icon={<CloudDownloadOutlined aria-hidden="true" />} onClick={downloadTemplate}>下载模板</Button>
            <Button type="primary" onClick={confirmImport}>确认导入</Button>
          </Space>
        </section>

        <Card
          className="data-import__card"
          title="① 选择上传的数据类型"
          extra={<Typography.Text type="secondary">选中后，下面上传区自动切换字段要求</Typography.Text>}
        >
          <div className="data-import__type-grid">
            {dataImportTypes.map((type) => (
              <button
                key={type.id}
                type="button"
                className={`data-import__type-card${selectedType.id === type.id ? " data-import__type-card--active" : ""}`}
                onClick={() => selectType(type)}
              >
                <span className="data-import__type-icon">{type.icon}</span>
                <span className="data-import__type-text">
                  <strong>{type.name}</strong>
                  <small>{type.shortName}</small>
                </span>
              </button>
            ))}
          </div>
        </Card>

        <Card
          className="data-import__card"
          title="② 上传与校验"
          extra={<Typography.Text type="secondary">上传区自然高度，不拉伸、不挤压</Typography.Text>}
        >
          <div className="data-import__upload-grid">
            <div className="data-import__info-panel">
              <div className="data-import__info-top">
                <span className="data-import__info-icon">{selectedType.icon}</span>
                <span>
                  <strong>{selectedType.name}</strong>
                  <small>{selectedType.shortName}</small>
                </span>
              </div>
              <div className="data-import__tags">
                {selectedType.fields.map((field) => <Tag key={field}>{field}</Tag>)}
              </div>
              <div className="data-import__hint">
                选择类型后上传容器已开启。上传完成会显示成功或说明具体问题。
              </div>
            </div>

            <div className="data-import__upload-panel">
              <InboxOutlined className="data-import__upload-icon" />
              <Typography.Title level={4}>上传 {selectedType.name}</Typography.Title>
              <Typography.Text type="secondary">支持 Excel / CSV</Typography.Text>
              <Space className="data-import__upload-actions">
                <Button type="primary" icon={<UploadOutlined aria-hidden="true" />} onClick={simulateUpload}>选择文件</Button>
                <Button onClick={downloadTemplate}>模板</Button>
              </Space>
              <Typography.Text strong type={currentFile ? undefined : "secondary"}>
                {currentFile || "未选择文件"}
              </Typography.Text>
            </div>

            <div className="data-import__result-panel">
              <strong>上传结果</strong>
              {!uploaded ? (
                <div className="data-import__result-empty">
                  上传完成后，这里显示状态、成功/失败条数、错误说明和下载。
                </div>
              ) : (
                <>
                  <Tag color={uploadHasWarning ? "warning" : "success"}>
                    {uploadHasWarning ? "部分失败" : "成功"}
                  </Tag>
                  <div className="data-import__result-stats">
                    <div><small>总行数</small><strong>1280</strong></div>
                    <div><small>成功</small><strong>{uploadHasWarning ? "1268" : "1280"}</strong></div>
                    <div><small>失败</small><strong>{uploadHasWarning ? "12" : "0"}</strong></div>
                  </div>
                  <div className={`data-import__hint${uploadHasWarning ? " data-import__hint--error" : ""}`}>
                    {uploadHasWarning
                      ? "发现 12 行异常：缺少关键词、搜索量为空或建议出价格式不正确。"
                      : "校验通过，可以确认导入。"}
                  </div>
                </>
              )}
            </div>
          </div>
        </Card>

        <Card
          className="data-import__card data-import__records-card"
          title="③ 最近上传记录"
          extra={<Typography.Text type="secondary">{filteredRows.length} 条</Typography.Text>}
        >
          <div className="data-import__filter-bar">
            <Select
              value={filters.typeName}
              style={{ width: 160 }}
              options={[{ label: "全部数据类型", value: "" }, ...dataImportTypes.map((type) => ({ label: type.name, value: type.name }))]}
              onChange={(value) => setFilter("typeName", value)}
            />
            <Select
              value={filters.status}
              style={{ width: 130 }}
              options={[
                { label: "全部状态", value: "" },
                { label: "成功", value: "成功" },
                { label: "部分失败", value: "部分失败" },
                { label: "失败", value: "失败" },
              ]}
              onChange={(value) => setFilter("status", value as DataImportFilters["status"])}
            />
            <Input
              value={filters.keyword}
              placeholder="搜索文件名 / 操作人"
              style={{ width: 220 }}
              onChange={(event) => setFilter("keyword", event.target.value)}
            />
            <span className="data-import__filter-spacer" />
          </div>

          <Table
            rowKey="id"
            size="small"
            columns={columns}
            dataSource={filteredRows}
            pagination={false}
            scroll={{ x: 1320, y: 240 }}
          />

          <div className="data-import__card-foot">
            <Typography.Text type="secondary">最近上传记录表格内部滚动，后续接入滚动懒加载。</Typography.Text>
          </div>
        </Card>
      </div>
    </PageShell>
  );
}

export default DataImportPage;

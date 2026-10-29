/** System shipment drafts. Headers only until the write API is connected. */
import { Select } from "antd";
import { useState } from "react";
import type { NavigationPage } from "@/config/navigation";
import WfsQueryPage from "./WfsQueryPage";

const columns = [
  { title: "草稿", dataIndex: "draft", width: 150 },
  { title: "操作类型", dataIndex: "action", width: 160 },
  { title: "店铺", dataIndex: "store", width: 220 },
  { title: "计划号 / 货件", dataIndex: "plan", width: 240 },
  { title: "状态", dataIndex: "status", width: 140 },
  { title: "执行结果", dataIndex: "result", width: 320 },
  { title: "操作", dataIndex: "ops", width: 160 },
];

export default function SystemShipmentPage({ page }: { page: NavigationPage }) {
  const [store, setStore] = useState<string>();
  const [status, setStatus] = useState("all");
  const [keyword, setKeyword] = useState("");
  const reset = () => { setStore(undefined); setStatus("all"); setKeyword(""); };
  return (
    <WfsQueryPage
      page={page}
      title="货件草稿与审批（0 条）"
      tableLabel="系统货件表格"
      emptyText="当前条件下暂无货件草稿"
      searchAriaLabel="搜索系统货件"
      inputAriaLabel="搜索系统货件关键字"
      inputPlaceholder="草稿号 / 计划号 / 货件号 / PK"
      typeAriaLabel="系统货件搜索类型"
      typeOptions={[{ value: "all", label: "草稿 / 货件" }]}
      columns={columns}
      scrollX={1400}
      loadingLabel="正在加载系统货件，请稍候"
      keyword={keyword}
      onSearch={setKeyword}
      onReset={reset}
      filters={(
        <>
          <Select allowClear showSearch aria-label="店铺" className="report-filter-select" placeholder="全部店铺" style={{ width: 220 }} value={store} onChange={setStore} options={[]} />
          <Select
            aria-label="货件草稿状态"
            className="report-filter-select"
            style={{ width: 160 }}
            value={status}
            onChange={setStatus}
            options={[
              { value: "all", label: "全部" },
              { value: "pending", label: "待批准" },
              { value: "approved", label: "待执行" },
              { value: "done", label: "已执行" },
              { value: "failed", label: "失败" },
            ]}
          />
        </>
      )}
    />
  );
}

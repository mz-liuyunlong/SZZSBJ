import { Button, Checkbox, Input, Modal, Select, Space, Tag } from "antd";
import { useMemo, useState } from "react";
import {
  operationLogWorkTypes,
  type OperationLogBatchWriteValues,
  type OperationLogRow,
  type OperationLogWorkType,
} from "@/pages/operations/operationLogTypes";

interface OperationLogBatchModalProps {
  open: boolean;
  rows: OperationLogRow[];
  onClose: () => void;
  onApply: (values: OperationLogBatchWriteValues) => void;
}

const templates = [
  { title: "无需调整", text: "今日无需调整，数据正常。", workTypes: ["无需调整"] as OperationLogWorkType[] },
  { title: "系统记录转草稿", text: "已根据系统广告调整记录生成日志草稿，请继续观察转化率和广告占比变化。", workTypes: ["系统日志核对", "广告调整"] as OperationLogWorkType[] },
  { title: "广告调价", text: "已调整广告出价/预算，观察3天转化和广告占比。", workTypes: ["广告调整"] as OperationLogWorkType[] },
  { title: "Listing优化", text: "已优化Listing标题、卖点、关键词和图片，观察7天点击率和转化率。", workTypes: ["Listing优化"] as OperationLogWorkType[] },
  { title: "价格调整", text: "已调整销售价，观察3天售价变化后的转化率和毛利率。", workTypes: ["销售价调整"] as OperationLogWorkType[] },
  { title: "人工补录", text: "后台手动调整，系统暂无抓取记录，已人工补录。", workTypes: ["其他"] as OperationLogWorkType[] },
];

function OperationLogBatchModal({
  open,
  rows,
  onClose,
  onApply,
}: OperationLogBatchModalProps) {
  const [keyword, setKeyword] = useState("");
  const [selectedProductIds, setSelectedProductIds] = useState<string[]>([]);
  const [workTypes, setWorkTypes] = useState<OperationLogWorkType[]>([]);
  const [observeDays, setObserveDays] = useState("观察 3 天");
  const [writeMode, setWriteMode] = useState<OperationLogBatchWriteValues["writeMode"]>("append");
  const [logText, setLogText] = useState("");

  const filteredRows = useMemo(() => {
    const normalized = keyword.trim().toLocaleLowerCase();
    if (!normalized) return rows;

    return rows.filter((row) => [
      row.productId,
      row.sku,
      row.productName,
      row.store,
      row.owner,
      row.date,
    ].some((value) => value.toLocaleLowerCase().includes(normalized)));
  }, [keyword, rows]);

  const allVisibleSelected = filteredRows.length > 0 && filteredRows.every((row) => selectedProductIds.includes(row.productId));

  const toggleVisible = (checked: boolean) => {
    if (checked) {
      setSelectedProductIds((current) => Array.from(new Set([...current, ...filteredRows.map((row) => row.productId)])));
      return;
    }

    setSelectedProductIds((current) => current.filter((productId) => !filteredRows.some((row) => row.productId === productId)));
  };

  const applyTemplate = (template: (typeof templates)[number]) => {
    setLogText(template.text);
    setWorkTypes(template.workTypes);
  };

  return (
    <Modal
      open={open}
      width="min(1180px, calc(100vw - 40px))"
      title={(
        <div>
          <strong>批量填写运营日志</strong>
          <span className="operation-log-batch-modal__sub">弹窗内选择商品ID、批量搜索、批量设置工作类型和日志内容</span>
        </div>
      )}
      className="operation-log-batch-modal"
      onCancel={onClose}
      destroyOnHidden
      footer={(
        <div className="operation-log-batch-modal__footer">
          <span>
            已选 <strong>{selectedProductIds.length}</strong> 个商品ID · 工作类型：
            <strong>{workTypes.length ? workTypes.join(" / ") : "未选"}</strong>
          </span>
          <Space>
            <Button onClick={onClose}>取消</Button>
            <Button onClick={() => setLogText(rows.slice(0, 5).map((row) => `${row.productId}：系统记录已带入，继续观察。`).join("\n"))}>
              带入系统记录
            </Button>
            <Button
              type="primary"
              onClick={() => onApply({
                productIds: selectedProductIds,
                workTypes,
                observeDays,
                writeMode,
                logText,
              })}
            >
              批量写入
            </Button>
          </Space>
        </div>
      )}
    >
      <div className="operation-log-batch-modal__body">
        <section className="operation-log-batch-modal__panel">
          <div className="operation-log-batch-modal__panel-head">
            <div>
              <h3>选择商品ID</h3>
              <p>列表高度自动占满，支持批量搜索后直接勾选。</p>
            </div>
            <Tag color="blue">{selectedProductIds.length} 已选</Tag>
          </div>
          <div className="operation-log-batch-modal__picker-toolbar">
            <Input.Search
              value={keyword}
              placeholder="搜索商品ID / SKU / 商品名 / 店铺 / 运营 / 日期"
              allowClear
              onChange={(event) => setKeyword(event.target.value)}
            />
            <Space wrap>
              <Button onClick={() => setSelectedProductIds(filteredRows.map((row) => row.productId))}>选当前列表</Button>
              <Button onClick={() => setSelectedProductIds(rows.filter((row) => !row.manualLog.trim()).map((row) => row.productId))}>选空白日志</Button>
              <Button onClick={() => setSelectedProductIds(rows.filter((row) => row.systemLogCount > 0).map((row) => row.productId))}>选有系统日志</Button>
              <Button onClick={() => setSelectedProductIds([])}>清空</Button>
            </Space>
          </div>
          <div className="operation-log-batch-modal__list-head">
            <Checkbox checked={allVisibleSelected} onChange={(event) => toggleVisible(event.target.checked)}>
              全选当前列表
            </Checkbox>
            <span>当前 {filteredRows.length} / 共 {rows.length} 条</span>
          </div>
          <div className="operation-log-batch-modal__list">
            {filteredRows.map((row) => (
              <label
                className={`operation-log-batch-modal__row${selectedProductIds.includes(row.productId) ? " operation-log-batch-modal__row--active" : ""}`}
                key={row.productId}
              >
                <Checkbox
                  checked={selectedProductIds.includes(row.productId)}
                  onChange={(event) => {
                    if (event.target.checked) {
                      setSelectedProductIds((current) => [...current, row.productId]);
                      return;
                    }
                    setSelectedProductIds((current) => current.filter((productId) => productId !== row.productId));
                  }}
                />
                <span>
                  <strong>{row.productId}</strong>
                  <small>{row.sku} · {row.productName} · {row.store}</small>
                </span>
              </label>
            ))}
          </div>
        </section>

        <section className="operation-log-batch-modal__panel">
          <div className="operation-log-batch-modal__panel-head">
            <div>
              <h3>填写内容</h3>
              <p>先选模板，再批量设置工作类型；也可以手动改日志内容。</p>
            </div>
          </div>
          <div className="operation-log-batch-modal__work-box">
            <div>
              <div className="operation-log-batch-modal__section-label">快速模板</div>
              <div className="operation-log-batch-modal__template-grid">
                {templates.map((template) => (
                  <button type="button" key={template.title} onClick={() => applyTemplate(template)}>
                    <strong>{template.title}</strong>
                    <span>{template.text}</span>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="operation-log-batch-modal__section-label">工作类型批量填写</div>
              <Checkbox.Group
                className="operation-log-batch-modal__work-type-grid"
                options={operationLogWorkTypes.map((workType) => ({ label: workType, value: workType }))}
                value={workTypes}
                onChange={(nextValues) => setWorkTypes(nextValues as OperationLogWorkType[])}
              />
            </div>

            <div className="operation-log-batch-modal__form-grid">
              <Select
                aria-label="观察周期"
                value={observeDays}
                options={["观察 3 天", "观察 7 天", "观察 14 天", "不需要观察"].map((value) => ({ label: value, value }))}
                onChange={setObserveDays}
              />
              <Select
                aria-label="写入方式"
                value={writeMode}
                options={[
                  { label: "追加到原日志", value: "append" },
                  { label: "仅写入空白日志", value: "onlyBlank" },
                  { label: "覆盖原日志", value: "replace" },
                ]}
                onChange={setWriteMode}
              />
            </div>

            <Input.TextArea
              aria-label="批量日志内容"
              value={logText}
              rows={6}
              placeholder="输入批量运营日志内容；也可以点击上方模板快速生成"
              onChange={(event) => setLogText(event.target.value)}
            />

            <div className="operation-log-batch-modal__note">
              这里写入的是运营日志，不会删除系统抓取的广告调整记录；系统广告记录仍可在主表「系统日志」处鼠标悬浮查看详情。
            </div>
          </div>
        </section>
      </div>
    </Modal>
  );
}

export default OperationLogBatchModal;

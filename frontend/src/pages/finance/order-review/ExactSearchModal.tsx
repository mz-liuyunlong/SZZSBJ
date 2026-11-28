/** 精确搜索弹层：按 ItemID / SKU / MSKU / 订单号 模糊找候选（最多 1000 行），勾选后作为精确多选条件。 */
import { Checkbox, Input, Modal, Space, Typography } from "antd";
import { useEffect, useState } from "react";
import { LOOKUP_LABEL, errorText, lookup, type LookupKind } from "./orderReviewApi";

function ExactSearchModal({ kind, open, value, onClose, onApply }: {
  kind: LookupKind; open: boolean; value: string[]; onClose: () => void; onApply: (values: string[]) => void;
}) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<string[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [picked, setPicked] = useState<string[]>(value);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const search = async (text: string) => {
    setBusy(true);
    try {
      const result = await lookup(kind, text);
      setItems(result.items);
      setTruncated(result.truncated);
      setError(undefined);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  // 弹层每次打开都是重新挂载（父组件按 kind 条件渲染），所以只在挂载时拉一次候选
  useEffect(() => {
    const timer = window.setTimeout(() => void search(""), 0);
    return () => window.clearTimeout(timer);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const shown = items.filter((item) => item.toLowerCase().includes(q.toLowerCase()));
  return (
    <Modal open={open} title={`精确搜索 · ${LOOKUP_LABEL[kind]}`} okText={`应用（${picked.length}）`} onOk={() => { onApply(picked); onClose(); }} onCancel={onClose} width={560} destroyOnHidden>
      <Space direction="vertical" style={{ width: "100%" }}>
        <Input.Search placeholder={`输入${LOOKUP_LABEL[kind]}关键字`} value={q} onChange={(e) => setQ(e.target.value)} onSearch={(text) => void search(text)} loading={busy} allowClear />
        {error && <Typography.Text type="danger">{error}</Typography.Text>}
        <Typography.Text type="secondary">候选 {shown.length} 条{truncated ? "（超过 1000 条，只显示前 1000，请缩小关键字）" : ""}；已选 {picked.length}</Typography.Text>
        <Space size={8}>
          <a onClick={() => setPicked(Array.from(new Set([...picked, ...shown])))}>全选当前候选</a>
          <a onClick={() => setPicked([])}>清空</a>
        </Space>
        <div style={{ maxHeight: 360, overflow: "auto", border: "1px solid #f0f0f0", padding: 8 }}>
          <Checkbox.Group value={picked} onChange={(values) => setPicked(values as string[])} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {shown.map((item) => <Checkbox key={item} value={item}>{item}</Checkbox>)}
          </Checkbox.Group>
        </div>
      </Space>
    </Modal>
  );
}

export default ExactSearchModal;

/** WFS settings · per-store Walmart creation settings (owner decisions 2026-10-31). */
import { Alert, Button, Card, Input, Space, Switch, Table, Tag, Typography, message } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { NavigationPage } from "@/config/navigation";
import PageShell from "@/components/page/PageShell";
import { listStoreSettings, saveStoreSetting, settingsError, type StoreSetting } from "./storeSettingsApi";

const stateTag: Record<StoreSetting["mapping_state"], { color: string; text: string }> = {
  unset: { color: "default", text: "未设置" },
  ok: { color: "success", text: "与服务器映射一致" },
  unreviewed: { color: "processing", text: "服务器未审核映射" },
  conflict: { color: "error", text: "与服务器映射冲突" },
};

type Draft = { code: string; its: boolean; creation: boolean; note: string };

export default function WfsStoreSettingsPage({ page, canManage = true }: { page: NavigationPage; canManage?: boolean }) {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["wfs-store-settings"], queryFn: ({ signal }) => listStoreSettings(signal), retry: false });
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const save = useMutation({
    mutationFn: ({ row, draft }: { row: StoreSetting; draft: Draft }) =>
      saveStoreSetting(row.store_id, {
        source_account_ref: row.source_account_ref,
        walmart_store_code: draft.code.trim().toUpperCase(),
        its_enabled: draft.its,
        creation_enabled: draft.creation,
        note: draft.note.trim() || null,
      }),
    onSuccess: (_data, { row }) => {
      message.success(`已保存 ${row.store_name ?? row.store_id}`);
      setDrafts((old) => { const next = { ...old }; delete next[row.store_id]; return next; });
      void client.invalidateQueries({ queryKey: ["wfs-store-settings"] });
    },
    onError: (error) => message.error(settingsError(error)),
  });
  const draftOf = (row: StoreSetting): Draft =>
    drafts[row.store_id] ?? { code: row.walmart_store_code ?? row.suggested_code ?? "", its: row.its_enabled, creation: row.creation_enabled, note: row.note ?? "" };
  const setDraft = (row: StoreSetting, patch: Partial<Draft>) => setDrafts((old) => ({ ...old, [row.store_id]: { ...draftOf(row), ...patch } }));
  const dirty = (row: StoreSetting) => {
    const d = draftOf(row);
    return d.code !== (row.walmart_store_code ?? "") || d.its !== row.its_enabled || d.creation !== row.creation_enabled || d.note !== (row.note ?? "");
  };
  const items = query.data?.data.items ?? [];
  return (
    <PageShell page={page}>
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <Alert
          showIcon
          type="info"
          message="店铺 Walmart 创建设置"
          description="每个领星店铺对应一个 Walmart 店铺代码；「ITS 可用」需在 Seller Center 确认后勾选，否则创建默认走 ITS 会被拒绝；「允许创建」是该店的总开关。修改即时生效并记录操作人。"
        />
        {query.isError && <Alert type="error" showIcon message={settingsError(query.error)} />}
        <Card title={`店铺（${items.length}）`} size="small">
          <Table<StoreSetting>
            size="small"
            rowKey="store_id"
            loading={query.isLoading}
            pagination={false}
            dataSource={items}
            locale={{ emptyText: "当前账号范围内没有店铺" }}
            columns={[
              { title: "领星店铺", dataIndex: "store_name", render: (_, r) => <span>{r.store_name ?? r.store_id}<br /><Typography.Text type="secondary">{r.store_id}</Typography.Text></span> },
              { title: "Walmart 店铺代码", width: 180, render: (_, r) => <Input aria-label={`店铺代码 ${r.store_id}`} value={draftOf(r).code} maxLength={6} disabled={!canManage || save.isPending} placeholder={r.suggested_code ?? "HK0000"} onChange={(e) => setDraft(r, { code: e.target.value })} /> },
              { title: "映射状态", width: 170, render: (_, r) => <Tag color={stateTag[r.mapping_state].color}>{stateTag[r.mapping_state].text}{r.reviewed_code && r.mapping_state === "conflict" ? `（服务器：${r.reviewed_code}）` : ""}</Tag> },
              { title: "ITS 可用", width: 100, render: (_, r) => <Switch aria-label={`ITS ${r.store_id}`} checked={draftOf(r).its} disabled={!canManage || save.isPending} onChange={(v) => setDraft(r, { its: v })} /> },
              { title: "允许创建", width: 100, render: (_, r) => <Switch aria-label={`允许创建 ${r.store_id}`} checked={draftOf(r).creation} disabled={!canManage || save.isPending} onChange={(v) => setDraft(r, { creation: v })} /> },
              { title: "备注", render: (_, r) => <Input aria-label={`备注 ${r.store_id}`} value={draftOf(r).note} maxLength={500} disabled={!canManage || save.isPending} onChange={(e) => setDraft(r, { note: e.target.value })} /> },
              { title: "最后修改", width: 170, render: (_, r) => r.updated_at ? <span>{r.actor_uid}<br /><Typography.Text type="secondary">{new Date(r.updated_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}</Typography.Text></span> : "—" },
              { title: "", width: 90, render: (_, r) => <Button size="small" type="primary" disabled={!canManage || !dirty(r) || !/^(HK|CN)\d{4}$/.test(draftOf(r).code.trim().toUpperCase())} loading={save.isPending && save.variables?.row.store_id === r.store_id} onClick={() => save.mutate({ row: r, draft: draftOf(r) })}>保存</Button> },
            ]}
          />
        </Card>
        <Card title="看板阈值（待第三步异常规则定稿后接入）" size="small">
          <Typography.Paragraph type="secondary">短收门槛、在途超期天数、收货中超长天数等阈值将在异常中心规则上线时迁到这里；目前只在设计稿中。</Typography.Paragraph>
        </Card>
      </Space>
    </PageShell>
  );
}

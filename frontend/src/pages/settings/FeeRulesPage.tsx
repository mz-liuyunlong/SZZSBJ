import {
  message as antdMessage,
  Modal,
  Alert,
  Button,
  Card,
  DatePicker,
  Drawer,
  Form,
  Input,
  InputNumber,
  Radio,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs, { type Dayjs } from "dayjs";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { NavigationPage } from "@/config/navigation";
import {
  deactivateStoreCommission,
  listStoreCommissions,
  recalculateStoreCommission,
  saveStoreCommission,
  type CommissionRuleScope,
  type StoreCommissionApplyScope,
  type BusinessRuleOperationLog,
  type StoreCommissionRecord,
} from "@/pages/settings/storeCommissionApi";
import "./FeeRulesPage.css";

interface FeeRulesPageProps {
  page: NavigationPage;
}

interface RuleFormValues {
  sourceAccountRef: string;
  storeId: string;
  ruleScope: CommissionRuleScope;
  itemIdsText?: string;
  priceMinAmount?: number | null;
  priceMaxAmount?: number | null;
  commissionPercent: number;
  priority: number;
  applyScope: StoreCommissionApplyScope;
  effectiveFrom?: Dayjs | null;
  changeReason: string;
}

const ALL_DATES_START = "1900-01-01";

const ruleScopeLabel: Record<CommissionRuleScope, string> = {
  store: "店铺默认",
  item: "指定商品ID",
  price_range: "售价区间",
};

const splitIds = (text: string | undefined) => {
  const raw = (text ?? "")
    .replaceAll("，", "\n")
    .replaceAll(",", "\n")
    .replaceAll(" ", "\n")
    .split(/\n+/g);

  const ids: string[] = [];
  const seen = new Set<string>();
  for (const value of raw) {
    const id = value.trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    ids.push(id);
  }
  return ids;
};

const formatPercent = (value: number) => `${value.toFixed(2)}%`;

const sourceTag = (source: StoreCommissionRecord["source"]) => {
  if (source === "store_rule") return <Tag color="success">规则</Tag>;
  return <Tag>默认15%</Tag>;
};

const ruleTypeTag = (scope: CommissionRuleScope) => {
  if (scope === "item") return <Tag color="purple">指定商品</Tag>;
  if (scope === "price_range") return <Tag color="orange">售价区间</Tag>;
  return <Tag color="blue">店铺默认</Tag>;
};

const priceRangeText = (row: StoreCommissionRecord) => {
  if (row.ruleScope !== "price_range") return "—";
  const min = row.priceMinAmount == null ? "不限" : `$${row.priceMinAmount}`;
  const max = row.priceMaxAmount == null ? "不限" : `$${row.priceMaxAmount}`;
  return `${min} ~ ${max}`;
};

function FeeRulesPage({ page }: FeeRulesPageProps) {
  const [messageApi, messageContextHolder] = antdMessage.useMessage();
  const [modalApi, modalContextHolder] = Modal.useModal();
  const [storeRules, setStoreRules] = useState<StoreCommissionRecord[]>([]);
  const [specialRules, setSpecialRules] = useState<StoreCommissionRecord[]>([]);
  const [operationLogs, setOperationLogs] = useState<BusinessRuleOperationLog[]>([]);
  const [logOpen, setLogOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [onlyCustom, setOnlyCustom] = useState(false);
  const [editing, setEditing] = useState<StoreCommissionRecord | null>(null);
  const [creatingScope, setCreatingScope] = useState<CommissionRuleScope | null>(null);
  const [saving, setSaving] = useState(false);
  const [workingRuleId, setWorkingRuleId] = useState<string | null>(null);
  const [form] = Form.useForm<RuleFormValues>();
  const watchedRuleScope = Form.useWatch("ruleScope", form);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await listStoreCommissions();
      setStoreRules(result.storeRules);
      setSpecialRules(result.specialRules);
      setOperationLogs(result.operationLogs);
    } catch (error) {
      console.error(error);
      messageApi.error("佣金规则加载失败");
    } finally {
      setLoading(false);
    }
  }, [messageApi]);

  useEffect(() => {
    let cancelled = false;

    const loadInitial = async () => {
      try {
        const result = await listStoreCommissions();
        if (!cancelled) {
          setStoreRules(result.storeRules);
          setSpecialRules(result.specialRules);
          setOperationLogs(result.operationLogs);
      setOperationLogs(result.operationLogs);
        }
      } catch (error) {
        console.error(error);
        if (!cancelled) messageApi.error("佣金规则加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void loadInitial();

    return () => {
      cancelled = true;
    };
  }, [messageApi]);

  const activeStoreIds = useMemo(() => {
    const ids = new Set<string>();
    for (const log of operationLogs) {
      if (
        log.operation_type === "commission_recalculate"
        && (log.status === "queued" || log.status === "running")
        && log.store_id
      ) {
        ids.add(log.store_id);
      }
    }
    return ids;
  }, [operationLogs]);

  useEffect(() => {
    if (activeStoreIds.size === 0) return undefined;

    const timer = window.setInterval(() => {
      void load();
    }, 5000);

    return () => window.clearInterval(timer);
  }, [activeStoreIds.size, load]);

  const isStoreLocked = (row: StoreCommissionRecord) => activeStoreIds.has(row.storeId);

  const filteredStoreRules = useMemo(
    () => storeRules.filter((row) => !onlyCustom || row.source === "store_rule"),
    [onlyCustom, storeRules],
  );

  const storeOptions = useMemo(
    () => storeRules.map((row) => ({
      value: `${row.sourceAccountRef}::${row.storeId}`,
      label: `${row.storeName ?? row.storeId} / ${row.storeId}`,
      row,
    })),
    [storeRules],
  );

  const openStoreEdit = (row: StoreCommissionRecord) => {
    setEditing(row);
    setCreatingScope(null);
    form.setFieldsValue({
      sourceAccountRef: row.sourceAccountRef,
      storeId: row.storeId,
      ruleScope: "store",
      commissionPercent: Number(row.commissionPercent.toFixed(2)),
      priority: row.priority || 100,
      applyScope: "all_dates",
      effectiveFrom: dayjs(row.effectiveFrom ?? ALL_DATES_START),
      changeReason: row.source === "store_rule"
        ? `调整店铺 ${row.storeId} 默认佣金`
        : `设置店铺 ${row.storeId} 默认佣金`,
    });
  };

  const openSpecialCreate = (scope: "item" | "price_range") => {
    const firstStore = storeRules[0];
    setEditing(null);
    setCreatingScope(scope);
    form.resetFields();
    form.setFieldsValue({
      sourceAccountRef: firstStore?.sourceAccountRef ?? "primary",
      storeId: firstStore?.storeId ?? "",
      ruleScope: scope,
      commissionPercent: 12,
      priority: scope === "item" ? 10 : 50,
      applyScope: "all_dates",
      effectiveFrom: dayjs(ALL_DATES_START),
      changeReason: scope === "item" ? "新增指定商品佣金规则" : "新增售价区间佣金规则",
    });
  };

  const openSpecialEdit = (row: StoreCommissionRecord) => {
    setEditing(row);
    setCreatingScope(null);
    form.setFieldsValue({
      sourceAccountRef: row.sourceAccountRef,
      storeId: row.storeId,
      ruleScope: row.ruleScope,
      itemIdsText: row.itemId ?? "",
      priceMinAmount: row.priceMinAmount,
      priceMaxAmount: row.priceMaxAmount,
      commissionPercent: Number(row.commissionPercent.toFixed(2)),
      priority: row.priority || 100,
      applyScope: "all_dates",
      effectiveFrom: dayjs(row.effectiveFrom ?? ALL_DATES_START),
      changeReason: `调整${ruleScopeLabel[row.ruleScope]}佣金规则`,
    });
  };

  const closeDrawer = () => {
    setEditing(null);
    setCreatingScope(null);
    form.resetFields();
  };

  const save = async (values: RuleFormValues) => {
    const ruleScope = values.ruleScope;
    const itemIds = ruleScope === "item" ? splitIds(values.itemIdsText) : [];
    if (ruleScope === "item" && itemIds.length === 0) {
      messageApi.warning("请填写至少一个商品 ID");
      return;
    }

    if (
      ruleScope === "price_range"
      && values.priceMinAmount == null
      && values.priceMaxAmount == null
    ) {
      messageApi.warning("售价区间至少填写最小值或最大值");
      return;
    }

    setSaving(true);
    try {
      const effectiveFrom = values.applyScope === "all_dates"
        ? ALL_DATES_START
        : values.effectiveFrom?.format("YYYY-MM-DD") ?? ALL_DATES_START;

      await saveStoreCommission({
        sourceAccountRef: values.sourceAccountRef,
        platformCode: "walmart",
        storeId: values.storeId,
        ruleScope,
        itemIds,
        priceMinAmount: values.priceMinAmount == null ? null : String(values.priceMinAmount),
        priceMaxAmount: values.priceMaxAmount == null ? null : String(values.priceMaxAmount),
        priority: values.priority || 100,
        commissionRate: (Number(values.commissionPercent) / 100).toFixed(6),
        applyScope: values.applyScope,
        effectiveFrom,
        effectiveTo: null,
        changeReason: values.changeReason,
        replaceRuleId: editing?.id ?? null,
      });

      messageApi.success("佣金规则已保存，利润数据需要重算后生效");
      closeDrawer();
      await load();
    } catch (error) {
      console.error(error);
      messageApi.error("佣金规则保存失败");
    } finally {
      setSaving(false);
    }
  };

  const recalculate = async (row: StoreCommissionRecord) => {
    modalApi.confirm({
      title: "确认重算利润数据？",
      content: (
        <div>
          <p>规则类型：{ruleScopeLabel[row.ruleScope]}</p>
          <p>店铺ID：{row.storeId}</p>
          {row.ruleScope === "item" ? <p>商品ID：{row.itemId}</p> : null}
          {row.ruleScope === "price_range" ? <p>售价区间：{priceRangeText(row)}</p> : null}
          <p>重算后，每日销售和订单利润里的佣金、利润、利润率、ROI 会变化。</p>
        </div>
      ),
      okText: "确认重算",
      cancelText: "取消",
      okButtonProps: { danger: true },
      centered: true,
      async onOk() {
        setWorkingRuleId(row.id ?? `${row.storeId}-${row.ruleScope}`);
        try {
          await recalculateStoreCommission({
            sourceAccountRef: row.sourceAccountRef,
            storeId: row.storeId,
            ruleScope: row.ruleScope,
            itemIds: row.itemId ? [row.itemId] : [],
            priceMinAmount: row.priceMinAmount == null ? null : String(row.priceMinAmount),
            priceMaxAmount: row.priceMaxAmount == null ? null : String(row.priceMaxAmount),
            confirmAllDates: true,
          });

          messageApi.success("重算任务已创建，后台执行中");
          await load();
        } catch (error) {
          console.error(error);
          messageApi.error("重算失败");
        } finally {
          setWorkingRuleId(null);
        }
      },
    });
  };

  const deactivate = async (row: StoreCommissionRecord) => {
    if (!row.id) return;
    modalApi.confirm({
      title: row.ruleScope === "store" ? "恢复默认15%？" : "停用该特殊规则？",
      content: "停用后需要重算利润数据才会影响历史页面。",
      okText: "确认停用",
      cancelText: "取消",
      okButtonProps: { danger: true },
      centered: true,
      async onOk() {
        setWorkingRuleId(row.id);
        try {
          await deactivateStoreCommission(row.sourceAccountRef, row.id!);
          messageApi.success("规则已停用，利润数据需要重算后生效");
          await load();
        } catch (error) {
          console.error(error);
          messageApi.error("停用规则失败");
        } finally {
          setWorkingRuleId(null);
        }
      },
    });
  };

  const storeColumns: ColumnsType<StoreCommissionRecord> = [
    {
      title: "平台",
      width: 90,
      render: () => <Tag color="blue">Walmart</Tag>,
    },
    { title: "店铺ID", dataIndex: "storeId", width: 180 },
    {
      title: "店铺名称",
      dataIndex: "storeName",
      width: 200,
      render: (value: string | null) => value || "—",
    },
    {
      title: "当前佣金",
      dataIndex: "commissionPercent",
      width: 120,
      render: (_: number, row) => (
        <span className={row.source === "store_rule" ? "fee-rules-page__rate fee-rules-page__rate--custom" : "fee-rules-page__rate"}>
          {formatPercent(row.commissionPercent)}
        </span>
      ),
    },
    { title: "来源", dataIndex: "source", width: 110, render: sourceTag },
    {
      title: "生效日期",
      dataIndex: "effectiveFrom",
      width: 120,
      render: (value: string | null) => value ?? "默认",
    },
    {
      title: "失效日期",
      dataIndex: "effectiveTo",
      width: 120,
      render: (value: string | null) => value ?? "长期有效",
    },
    {
      title: "规则版本",
      dataIndex: "ruleVersion",
      width: 260,
      ellipsis: true,
      render: (value: string | null) => value ?? "—",
    },
    {
      title: "重算状态",
      dataIndex: "needsRecalculate",
      width: 110,
      render: (value: boolean) => value ? <Tag color="warning">需重算</Tag> : <Tag color="success">已同步</Tag>,
    },
    {
      title: "操作",
      key: "actions",
      width: 180,
      fixed: "right",
      render: (_, row) => (
        <Space size={4}>
          <Button type="link" disabled={isStoreLocked(row)} onClick={() => openStoreEdit(row)}>编辑</Button>
          {row.id ? <Button type="link" danger disabled={isStoreLocked(row)} onClick={() => deactivate(row)}>恢复默认</Button> : null}
          <Button
            type="link"
            danger
            disabled={isStoreLocked(row)}
            loading={isStoreLocked(row) || workingRuleId === (row.id ?? `${row.storeId}-${row.ruleScope}`)}
            onClick={() => recalculate(row)}
          >
            {isStoreLocked(row) ? "重算中" : "重算"}
          </Button>
        </Space>
      ),
    },
  ];

  const specialColumns: ColumnsType<StoreCommissionRecord> = [
    {
      title: "平台",
      width: 90,
      render: () => <Tag color="blue">Walmart</Tag>,
    },
    { title: "店铺ID", dataIndex: "storeId", width: 180 },
    {
      title: "店铺名称",
      dataIndex: "storeName",
      width: 180,
      render: (value: string | null) => value || "—",
    },
    {
      title: "规则类型",
      dataIndex: "ruleScope",
      width: 120,
      render: ruleTypeTag,
    },
    {
      title: "商品ID",
      dataIndex: "itemId",
      width: 170,
      render: (value: string | null) => value || "—",
    },
    {
      title: "售价区间",
      width: 160,
      render: (_, row) => priceRangeText(row),
    },
    {
      title: "佣金",
      dataIndex: "commissionPercent",
      width: 100,
      render: (value: number) => <span className="fee-rules-page__rate fee-rules-page__rate--custom">{formatPercent(value)}</span>,
    },
    { title: "优先级", dataIndex: "priority", width: 90 },
    {
      title: "生效日期",
      dataIndex: "effectiveFrom",
      width: 120,
      render: (value: string | null) => value ?? "默认",
    },
    {
      title: "规则版本",
      dataIndex: "ruleVersion",
      width: 260,
      ellipsis: true,
      render: (value: string | null) => value ?? "—",
    },
    {
      title: "操作",
      key: "actions",
      width: 180,
      fixed: "right",
      render: (_, row) => (
        <Space size={4}>
          <Button type="link" disabled={isStoreLocked(row)} onClick={() => openSpecialEdit(row)}>编辑</Button>
          <Button type="link" danger disabled={isStoreLocked(row)} onClick={() => deactivate(row)}>停用</Button>
          <Button
            type="link"
            danger
            disabled={isStoreLocked(row)}
            loading={isStoreLocked(row) || workingRuleId === row.id}
            onClick={() => recalculate(row)}
          >
            {isStoreLocked(row) ? "重算中" : "重算"}
          </Button>
        </Space>
      ),
    },
  ];

  const drawerOpen = Boolean(editing || creatingScope);

  return (
    <>
      {messageContextHolder}
      {modalContextHolder}
      <section className="fee-rules-page" aria-label={page.title}>
      <header className="fee-rules-page__header">
        <div>
          <h1 className="fee-rules-page__title">费用规则</h1>
          <p className="fee-rules-page__desc">
            店铺内佣金规则引擎：指定商品 ID &gt; 售价区间 &gt; 店铺默认 &gt; 系统默认 15%。保存规则后，需要重算利润数据才会影响页面结果。
          </p>
        </div>
        <div className="fee-rules-page__toolbar">
          <Switch
            checked={onlyCustom}
            checkedChildren="只看已配置"
            unCheckedChildren="全部"
            onChange={setOnlyCustom}
          />
          <Button onClick={() => setLogOpen(true)}>日志</Button>
          <Button onClick={() => void load()}>刷新</Button>
        </div>
      </header>

      <Card className="fee-rules-page__content">
        <Tabs
          items={[
            {
              key: "store",
              label: "店铺默认佣金",
              children: (
                <Table<StoreCommissionRecord>
                  rowKey={(row) => `${row.sourceAccountRef}:${row.storeId}:store`}
                  loading={loading}
                  columns={storeColumns}
                  dataSource={filteredStoreRules}
                  size="small"
                  scroll={{ x: 1500, y: "calc(100vh - 330px)" }}
                  pagination={{ pageSize: 50, showSizeChanger: true }}
                />
              ),
            },
            {
              key: "special",
              label: "店铺特殊佣金规则",
              children: (
                <>
                  <div className="fee-rules-page__tab-actions">
                    <Button type="primary" onClick={() => openSpecialCreate("item")}>
                      新增指定商品规则
                    </Button>
                    <Button onClick={() => openSpecialCreate("price_range")}>
                      新增售价区间规则
                    </Button>
                  </div>
                  <Table<StoreCommissionRecord>
                    rowKey={(row) => row.id ?? `${row.storeId}:${row.ruleScope}:${row.itemId}`}
                    loading={loading}
                    columns={specialColumns}
                    dataSource={specialRules}
                    size="small"
                    scroll={{ x: 1500, y: "calc(100vh - 380px)" }}
                    pagination={{ pageSize: 50, showSizeChanger: true }}
                  />
                </>
              ),
            },
          ]}
        />
      </Card>

      <Drawer
        title="费用规则操作日志"
        width={720}
        open={logOpen}
        destroyOnHidden
        onClose={() => setLogOpen(false)}
        extra={<Button onClick={() => void load()}>刷新</Button>}
      >
        <Table<BusinessRuleOperationLog>
          rowKey="id"
          size="small"
          dataSource={operationLogs}
          pagination={{ pageSize: 20 }}
          columns={[
            {
              title: "状态",
              dataIndex: "status",
              width: 90,
              render: (value) => value === "running" || value === "queued" ? <Tag color="processing">重算中</Tag> : value === "succeeded" ? <Tag color="success">完成</Tag> : <Tag color="error">失败</Tag>,
            },
            { title: "操作人", dataIndex: "actor_ref", width: 120 },
            { title: "店铺ID", dataIndex: "store_id", width: 180 },
            {
              title: "规则类型",
              dataIndex: "rule_scope",
              width: 110,
              render: (value) => value ? ruleScopeLabel[value as CommissionRuleScope] : "—",
            },
            {
              title: "开始时间",
              dataIndex: "started_at",
              width: 170,
              render: (value) => value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "—",
            },
            {
              title: "完成时间",
              dataIndex: "finished_at",
              width: 170,
              render: (value) => value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "—",
            },
            {
              title: "结果",
              width: 220,
              render: (_, row) => row.status === "succeeded"
                ? `${row.days_recalculated}天 / DS ${row.daily_sales_rows} / OP ${row.order_profit_rows}`
                : row.error_message || row.message || "—",
            },
          ]}
        />
      </Drawer>

      <Drawer
        title={editing ? "编辑佣金规则" : "新增佣金规则"}
        width={540}
        open={drawerOpen}
        destroyOnHidden
        onClose={closeDrawer}
        extra={(
          <Space>
            <Button onClick={closeDrawer}>取消</Button>
            <Button type="primary" loading={saving} onClick={() => form.submit()}>
              保存
            </Button>
          </Space>
        )}
      >
        <Alert
          className="fee-rules-page__drawer-note"
          type="warning"
          showIcon
          message="佣金规则保存后不会直接改历史结果，需要重算后 Daily Sales / Order Profit 才会变化。"
        />

        <Form<RuleFormValues>
          form={form}
          layout="vertical"
          onFinish={save}
          initialValues={{
            ruleScope: "store",
            applyScope: "all_dates",
            priority: 100,
            effectiveFrom: dayjs(ALL_DATES_START),
          }}
        >
          <Form.Item label="规则类型" name="ruleScope">
            <Radio.Group
              disabled={Boolean(editing)}
              options={[
                { label: "店铺默认", value: "store" },
                { label: "指定商品ID", value: "item" },
                { label: "售价区间", value: "price_range" },
              ]}
            />
          </Form.Item>

          <Form.Item label="店铺" required>
            <Form.Item name="sourceAccountRef" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="storeId" noStyle rules={[{ required: true, message: "请选择店铺" }]}>
              <Select
                showSearch
                disabled={Boolean(editing)}
                placeholder="选择店铺"
                options={storeOptions}
                optionFilterProp="label"
                onChange={(_, option) => {
                  const selected = Array.isArray(option) ? option[0] : option;
                  if (selected?.row) {
                    form.setFieldValue("sourceAccountRef", selected.row.sourceAccountRef);
                    form.setFieldValue("storeId", selected.row.storeId);
                  }
                }}
              />
            </Form.Item>
          </Form.Item>

          {watchedRuleScope === "item" ? (
            <Form.Item
              label="商品 ID"
              name="itemIdsText"
              tooltip="支持批量：一行一个、逗号分隔、空格分隔都可以"
              rules={[{ required: true, message: "请填写商品 ID" }]}
            >
              <Input.TextArea rows={5} placeholder={"例如：\n20257773836\n20263805742\n或用逗号分隔"} />
            </Form.Item>
          ) : null}

          {watchedRuleScope === "price_range" ? (
            <Space.Compact block className="fee-rules-page__range-inputs">
              <Form.Item label="售价最小值" name="priceMinAmount" className="fee-rules-page__range-item">
                <InputNumber min={0} precision={2} addonBefore="$" style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item label="售价最大值" name="priceMaxAmount" className="fee-rules-page__range-item">
                <InputNumber min={0} precision={2} addonBefore="$" style={{ width: "100%" }} />
              </Form.Item>
            </Space.Compact>
          ) : null}

          <Form.Item
            label="佣金比例"
            name="commissionPercent"
            rules={[{ required: true, message: "请输入佣金比例" }]}
          >
            <InputNumber min={0} max={99.9999} precision={2} addonAfter="%" style={{ width: "100%" }} />
          </Form.Item>

          <Form.Item label="优先级" name="priority" tooltip="同类型规则内排序，数字越小越优先">
            <InputNumber min={1} max={9999} precision={0} style={{ width: "100%" }} />
          </Form.Item>

          <Form.Item label="生效范围" name="applyScope">
            <Radio.Group
              options={[
                { label: "全部日期", value: "all_dates" },
                { label: "从指定日期开始", value: "from_date" },
              ]}
            />
          </Form.Item>

          <Form.Item shouldUpdate noStyle>
            {({ getFieldValue }) => (
              getFieldValue("applyScope") === "from_date" ? (
                <Form.Item label="生效日期" name="effectiveFrom" rules={[{ required: true, message: "请选择生效日期" }]}>
                  <DatePicker style={{ width: "100%" }} />
                </Form.Item>
              ) : (
                <Form.Item label="生效日期">
                  <Input value={ALL_DATES_START} disabled />
                </Form.Item>
              )
            )}
          </Form.Item>

          <Form.Item label="修改原因" name="changeReason" rules={[{ required: true, message: "请填写修改原因" }]}>
            <Input.TextArea rows={4} maxLength={500} showCount />
          </Form.Item>
        </Form>
      </Drawer>
      </section>
    </>
  );
}

export default FeeRulesPage;

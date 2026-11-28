import { ApiOutlined, PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Modal,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { useCallback, useEffect, useState } from "react";
import { BackendRequestError } from "@/api/backendApi";
import { fetchCurrentUser } from "@/pages/auth/authApi";
import {
  createWooCommerceStore,
  listWooCommerceStores,
  testWooCommerceStore,
  updateWooCommerceStore,
  type WooCommerceStore,
  type WooCommerceStoreWrite,
} from "@/api/woocommerceConfigApi";

interface StoreFormValues {
  name: string;
  store_url: string;
  consumer_key?: string;
  consumer_secret?: string;
}

function testFailureMessage(code: string): string {
  const messages: Record<string, string> = {
    WOO_DNS_FAILED: "域名解析失败，请检查店铺域名。",
    WOO_HOST_NOT_PUBLIC: "域名解析到了非公网地址，为安全起见已拒绝连接。",
    WOO_CONNECTION_FAILED: "网络连接失败或超时。",
    WOO_AUTH_FAILED: "Consumer Key 或 Consumer Secret 不正确。",
    WOO_PERMISSION_DENIED: "API 密钥没有读取商品的权限，请确认密钥为读/写。",
    WOO_API_NOT_FOUND: "未找到 WooCommerce REST API，请确认网站已启用 WooCommerce。",
    WOO_REDIRECT_BLOCKED: "网站发生跳转，请填写最终 HTTPS 站点域名。",
    WOO_RATE_LIMITED: "WooCommerce 返回请求频率限制，请稍后重试。",
    WOO_UPSTREAM_ERROR: "WooCommerce 服务器暂时异常。",
    WOO_RESPONSE_INVALID: "WooCommerce 返回格式不符合预期。",
    WOO_RESPONSE_TOO_LARGE: "返回数据超过连接测试的安全大小。",
  };
  return messages[code] ?? `连接失败（${code || "UNKNOWN"}）。`;
}

function requestFailureMessage(error: unknown): string {
  if (error instanceof BackendRequestError) {
    if (error.code === "WOO_TEST_REQUIRED") {
      return "请先保存并测试当前域名和密钥，测试通过后才能启用。";
    }
    if (error.status === 403) return "当前账号需要超级管理员权限。";
    if (error.code === "WOO_STORE_DOMAIN_EXISTS") return "这个店铺域名已经配置。";
    return `请求未完成（${error.code ?? "BACKEND_ERROR"}）。`;
  }
  return "服务器请求失败，请检查后端服务。";
}

function validStoreUrl(value: string): boolean {
  try {
    const parsed = new URL(value.trim());
    return parsed.protocol === "https:"
      && Boolean(parsed.hostname)
      && !parsed.username
      && !parsed.password
      && !parsed.search
      && !parsed.hash
      && (parsed.pathname === "/" || parsed.pathname === "")
      && (!parsed.port || parsed.port === "443");
  } catch {
    return false;
  }
}

function testStatus(row: WooCommerceStore): { label: string; color: string } {
  if (row.last_test_ok === true) return { label: "连接正常", color: "success" };
  if (row.last_test_ok === false) return { label: "连接失败", color: "error" };
  return { label: "尚未测试", color: "default" };
}

function WooCommerceIntegrationPanel() {
  const [form] = Form.useForm<StoreFormValues>();
  const [messageApi, messageContextHolder] = message.useMessage();
  const [stores, setStores] = useState<WooCommerceStore[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [canManage, setCanManage] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<WooCommerceStore | null>(null);
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setStores(await listWooCommerceStores());
      setLoadError(false);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void fetchCurrentUser()
      .then((user) => {
        if (!active) return;
        const allowed = Boolean(user?.isSuperAdmin);
        setCanManage(allowed);
        if (!allowed) {
          setLoading(false);
          setLoadError(false);
          return;
        }
        void listWooCommerceStores()
          .then((rows) => {
            if (active) {
              setStores(rows);
              setLoadError(false);
            }
          })
          .catch(() => {
            if (active) setLoadError(true);
          })
          .finally(() => {
            if (active) setLoading(false);
          });
      })
      .catch(() => {
        if (active) {
          setCanManage(false);
          setLoading(false);
          setLoadError(false);
        }
      });
    return () => { active = false; };
  }, []);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ name: "", store_url: "", consumer_key: "", consumer_secret: "" });
    setModalOpen(true);
  };

  const openEdit = (row: WooCommerceStore) => {
    setEditing(row);
    form.resetFields();
    form.setFieldsValue({
      name: row.name,
      store_url: row.store_url,
      consumer_key: "",
      consumer_secret: "",
    });
    setModalOpen(true);
  };

  const closeModal = () => {
    if (saving) return;
    setModalOpen(false);
    setEditing(null);
    form.resetFields();
  };

  const save = async () => {
    let values: StoreFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }

    const key = values.consumer_key?.trim() ?? "";
    const secret = values.consumer_secret?.trim() ?? "";
    if (editing && values.store_url.trim() !== editing.store_url && (!key || !secret)) {
      messageApi.warning("修改店铺域名时，请重新输入 Consumer Key 和 Consumer Secret。");
      return;
    }
    const changedConnection = Boolean(
      editing && (
        values.store_url.trim() !== editing.store_url
        || key
        || secret
      ),
    );
    const payload: WooCommerceStoreWrite = {
      name: values.name.trim(),
      store_url: values.store_url.trim(),
      enabled: editing ? (changedConnection ? false : editing.enabled) : false,
      ...(key ? { consumer_key: key } : {}),
      ...(secret ? { consumer_secret: secret } : {}),
    };

    setSaving(true);
    try {
      if (editing) {
        await updateWooCommerceStore(editing.id, payload);
        messageApi.success("店铺配置已保存；如修改了域名或密钥，需要重新测试连接。");
      } else {
        await createWooCommerceStore({
          ...payload,
          consumer_key: key,
          consumer_secret: secret,
        });
        messageApi.success("店铺已保存，密钥已加密保存。");
      }
      setModalOpen(false);
      setEditing(null);
      form.resetFields();
      await refresh();
    } catch (error) {
      messageApi.error(requestFailureMessage(error));
    } finally {
      setSaving(false);
    }
  };

  const runTest = async (row: WooCommerceStore) => {
    setTestingId(row.id);
    try {
      const result = await testWooCommerceStore(row.id);
      if (result.ok) messageApi.success("WooCommerce 连接测试通过。");
      else messageApi.error(testFailureMessage(result.code));
      await refresh();
    } catch (error) {
      messageApi.error(requestFailureMessage(error));
    } finally {
      setTestingId(null);
    }
  };

  const toggleEnabled = async (row: WooCommerceStore, enabled: boolean) => {
    setUpdatingId(row.id);
    try {
      await updateWooCommerceStore(row.id, {
        name: row.name,
        store_url: row.store_url,
        enabled,
      });
      messageApi.success(enabled ? "店铺已启用。" : "店铺已停用。");
      await refresh();
    } catch (error) {
      messageApi.error(requestFailureMessage(error));
      await refresh();
    } finally {
      setUpdatingId(null);
    }
  };

  const columns: ColumnsType<WooCommerceStore> = [
    {
      title: "店铺名称",
      dataIndex: "name",
      width: 150,
      render: (value: string) => <Typography.Text strong>{value}</Typography.Text>,
    },
    {
      title: "店铺域名",
      dataIndex: "store_url",
      ellipsis: true,
      render: (value: string) => <Typography.Text copyable={{ text: value }}>{value}</Typography.Text>,
    },
    {
      title: "密钥配置",
      key: "credentials",
      width: 130,
      render: (_, row) => row.consumer_key_configured && row.consumer_secret_configured
        ? <Tag color="success">{"已配置"}</Tag>
        : <Tag color="warning">{"未完整"}</Tag>,
    },
    {
      title: "连接状态",
      key: "test",
      width: 130,
      render: (_, row) => {
        const state = testStatus(row);
        return (
          <Tooltip title={row.last_test_code && row.last_test_ok === false ? testFailureMessage(row.last_test_code) : undefined}>
            <Tag color={state.color}>{state.label}</Tag>
          </Tooltip>
        );
      },
    },
    {
      title: "店铺状态",
      dataIndex: "enabled",
      width: 110,
      render: (enabled: boolean, row) => (
        <Switch
          size="small"
          checked={enabled}
          loading={updatingId === row.id}
          disabled={!canManage || (!enabled && row.last_test_ok !== true)}
          checkedChildren="启用"
          unCheckedChildren="停用"
          onChange={(checked) => void toggleEnabled(row, checked)}
        />
      ),
    },
    {
      title: "最近测试",
      dataIndex: "last_test_at",
      width: 155,
      render: (value: string | null) => value && dayjs(value).isValid()
        ? dayjs(value).format("YYYY-MM-DD HH:mm")
        : "—",
    },
    {
      title: "操作",
      key: "actions",
      width: 170,
      render: (_, row) => canManage ? (
        <Space size={4}>
          <Button
            type="link"
            size="small"
            loading={testingId === row.id}
            disabled={!row.consumer_key_configured || !row.consumer_secret_configured || updatingId === row.id}
            onClick={() => void runTest(row)}
          >
            {"测试连接"}
          </Button>
          <Button type="link" size="small" onClick={() => openEdit(row)}>
            {"编辑"}
          </Button>
        </Space>
      ) : null,
    },
  ];

  return (
    <>
      {messageContextHolder}
      <Card
        title={(
          <Space>
            <ApiOutlined />
            <span>WooCommerce</span>
            <Tag>REST API v3</Tag>
          </Space>
        )}
        extra={(
          <Space>
            <Button
              icon={<ReloadOutlined />}
              loading={loading}
              disabled={!canManage}
              onClick={() => void refresh()}
            >
              {"刷新"}
            </Button>
            {canManage ? (
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                {"新增店铺"}
              </Button>
            ) : null}
          </Space>
        )}
      >
        {!canManage ? (
          <Alert
            style={{ marginTop: 16 }}
            type="warning"
            showIcon
            message="只有超级管理员可以管理 WooCommerce 密钥。"
          />
        ) : null}
        {loadError ? (
          <Alert
            style={{ marginTop: 16 }}
            type="error"
            showIcon
            message="店铺配置读取失败"
            description="请检查后端 API、本地数据库迁移和读取权限。页面不会使用测试数据替代真实配置。"
            action={<Button size="small" onClick={() => void refresh()}>重试</Button>}
          />
        ) : null}
        <div style={{ marginTop: 16 }}>
          <Table<WooCommerceStore>
            rowKey="id"
            size="small"
            loading={loading}
            dataSource={stores}
            columns={columns}
            pagination={{ pageSize: 10, showSizeChanger: false }}
            locale={{ emptyText: <Empty description={loadError ? "店铺列表读取失败" : !canManage ? "暂无访问权限" : "尚未添加 WooCommerce 店铺"} /> }}
            scroll={{ x: 950 }}
          />
        </div>
      </Card>

      <Modal
        title={editing ? "编辑 WooCommerce 店铺" : "新增 WooCommerce 店铺"}
        open={modalOpen}
        centered
        width={620}
        destroyOnHidden
        maskClosable={!saving}
        closable={!saving}
        onCancel={closeModal}
        footer={(
          <Space>
            <Button disabled={saving} onClick={closeModal}>{"取消"}</Button>
            <Button type="primary" loading={saving} onClick={() => void save()}>
              {"保存配置"}
            </Button>
          </Space>
        )}
      >
        <Alert
          type="info"
          showIcon
          message="密钥仅在服务端加密保存，不回显。域名或密钥变更后需重新测试。"
          description={editing
            ? "密钥不会回显。如果不需要轮换密钥，两个密钥输入框都留空即可保留原值。"
            : "创建后店铺默认停用，连接测试通过后才能启用。"}
        />
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="name"
            label="店铺名称"
            rules={[{ required: true, whitespace: true, max: 100, message: "请填写店铺名称" }]}
          >
            <Input maxLength={100} placeholder="例如：RINIMA" />
          </Form.Item>
          <Form.Item
            name="store_url"
            label="店铺域名"
            rules={[
              { required: true, message: "请填写 HTTPS 店铺域名" },
              {
                validator: async (_, value: string | undefined) => {
                  if (value && !validStoreUrl(value)) {
                    throw new Error("请填写 HTTPS 域名，不含路径、参数或端口");
                  }
                },
              },
            ]}
          >
            <Input placeholder="https://www.example.com" autoComplete="url" />
          </Form.Item>
          <Form.Item
            name="consumer_key"
            label="Consumer Key"
            rules={!editing ? [{ required: true, message: "请填写 Consumer Key" }] : []}
          >
            <Input.Password autoComplete="new-password" placeholder={editing ? "留空保留已保存的 Key" : "ck_..."} />
          </Form.Item>
          <Form.Item
            name="consumer_secret"
            label="Consumer Secret"
            rules={!editing ? [{ required: true, message: "请填写 Consumer Secret" }] : []}
          >
            <Input.Password autoComplete="new-password" placeholder={editing ? "留空保留已保存的 Secret" : "cs_..."} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}

export default WooCommerceIntegrationPanel;

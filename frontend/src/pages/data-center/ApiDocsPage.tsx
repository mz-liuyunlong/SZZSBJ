/** API documentation No-API page: module matrix, detail reader and response model. */
import {
  CloudDownloadOutlined,
  CopyOutlined,
  ReloadOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Button, Card, Drawer, Input, Modal, Space, Tag, Typography, message } from "antd";
import { useMemo, useState } from "react";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import { apiDocModules } from "@/pages/data-center/apiDocsMockData";
import {
  filterApiDocs,
  flattenApiDocs,
  getApiCount,
  getMethodColor,
  type ApiDocItem,
  type ApiDocModule,
} from "@/pages/data-center/apiDocsTypes";
import "@/pages/data-center/ApiDocsPage.css";

interface ApiDocsPageProps {
  page: NavigationPage;
}

const CONFIG_PENDING = "API文档配置接口待接入";
const EXPORT_PENDING = "API文档导出接口待接入";
const DEBUG_PENDING = "在线调试接口待接入";

const findFirstApi = (modules: ApiDocModule[]) => modules[0]?.levels[0]?.apis[0];
const findModule = (modules: ApiDocModule[], key: string) => modules.find((module) => module.key === key) ?? modules[0];
const findLevel = (module: ApiDocModule | undefined, levelName?: string) => module?.levels.find((level) => level.name === levelName) ?? module?.levels[0];

function FieldTable({ rows }: { rows: ApiDocItem["queryParams"] }) {
  if (!rows.length) return <Typography.Text type="secondary">无参数</Typography.Text>;

  return (
    <table className="api-docs__field-table">
      <thead><tr><th>字段</th><th>类型</th><th>必填</th><th>说明</th></tr></thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.name}>
            <td>{row.name}</td>
            <td>{row.type}</td>
            <td>{row.required ? "是" : "否"}</td>
            <td>{row.description}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CodeBlock({ value }: { value: unknown }) {
  return <pre className="api-docs__code">{JSON.stringify(value, null, 2)}</pre>;
}

function ApiDocsPage({ page }: ApiDocsPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [keyword, setKeyword] = useState("");
  const [activeModuleKey, setActiveModuleKey] = useState(apiDocModules[0].key);
  const [activeLevelName, setActiveLevelName] = useState(apiDocModules[0].levels[0].name);
  const [selectedApiId, setSelectedApiId] = useState(apiDocModules[0].levels[0].apis[0].id);
  const [configOpen, setConfigOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [debugOpen, setDebugOpen] = useState(false);

  const filteredModules = useMemo(() => filterApiDocs(apiDocModules, keyword), [keyword]);
  const currentModule = findModule(filteredModules, activeModuleKey);
  const currentLevel = findLevel(currentModule, activeLevelName);
  const allFilteredApis = useMemo(() => flattenApiDocs(filteredModules), [filteredModules]);
  const matrixApis = currentLevel?.apis ?? [];
  const selectedApi = allFilteredApis.find((api) => api.id === selectedApiId)
    ?? matrixApis[0]
    ?? findFirstApi(filteredModules)
    ?? apiDocModules[0].levels[0].apis[0];

  const selectModule = (module: ApiDocModule) => {
    const firstLevel = module.levels[0];
    const firstApi = firstLevel.apis[0];
    setActiveModuleKey(module.key);
    setActiveLevelName(firstLevel.name);
    if (firstApi) setSelectedApiId(firstApi.id);
  };

  const selectLevel = (levelName: string) => {
    const level = currentModule?.levels.find((item) => item.name === levelName);
    const firstApi = level?.apis[0];
    setActiveLevelName(levelName);
    if (firstApi) setSelectedApiId(firstApi.id);
  };

  const resetSearch = () => {
    setKeyword("");
    const module = apiDocModules[0];
    setActiveModuleKey(module.key);
    setActiveLevelName(module.levels[0].name);
    setSelectedApiId(module.levels[0].apis[0].id);
  };

  const headerActions = (
    <>
      <Button icon={<SettingOutlined aria-hidden="true" />} onClick={() => setConfigOpen(true)}>显示配置</Button>
      <Button icon={<CloudDownloadOutlined aria-hidden="true" />} onClick={() => setExportOpen(true)}>导出</Button>
      <Button type="primary" onClick={() => setDebugOpen(true)}>在线调试</Button>
      <Button
        type="text"
        shape="circle"
        aria-label="刷新API文档"
        icon={<ReloadOutlined aria-hidden="true" />}
        onClick={() => void messageApi.info("API文档接口待接入")}
      />
    </>
  );

  return (
    <PageShell page={page} headerActions={headerActions}>
      {messageContextHolder}
      <div className="api-docs">
        <section className="api-docs__page-head" aria-label="API文档页面说明">
          <div>
            <Typography.Title level={3}>接口详情矩阵导航结合版</Typography.Title>
            <Typography.Paragraph type="secondary">
              把接口详情阅读器和权限返回模型矩阵合到一页：先选一级模块，再选二级业务，快速查看接口用途、请求方式和成功返回。
            </Typography.Paragraph>
          </div>
          <Space>
            <Input.Search
              aria-label="接口文档搜索"
              className="api-docs__search"
              value={keyword}
              placeholder="搜索模块 / 二级业务 / 接口 / Path"
              allowClear
              onChange={(event) => setKeyword(event.target.value)}
              onSearch={(value) => setKeyword(value)}
            />
            <Button onClick={resetSearch}>重置</Button>
            <Button type="primary" icon={<CloudDownloadOutlined aria-hidden="true" />} onClick={() => setExportOpen(true)}>导出文档</Button>
          </Space>
        </section>

        <section className="api-docs__layout" aria-label="接口详情矩阵">
          <Card size="small" className="api-docs__module-nav" title="一级模块导航" extra={<Tag>必选</Tag>}>
            {filteredModules.map((module) => (
              <button
                key={module.key}
                type="button"
                className={`api-docs__module-button${module.key === currentModule?.key ? " api-docs__module-button--active" : ""}`}
                onClick={() => selectModule(module)}
              >
                <span className="api-docs__module-button-top">
                  <strong>{module.icon} {module.name}</strong>
                  <Tag>{getApiCount(module)} 个接口</Tag>
                </span>
                <span>{module.desc}</span>
              </button>
            ))}
          </Card>

          <div className="api-docs__main-doc">
            <Card size="small" className="api-docs__level-nav">
              {currentModule?.levels.map((level) => (
                <button
                  key={level.name}
                  type="button"
                  className={`api-docs__level-chip${level.name === currentLevel?.name ? " api-docs__level-chip--active" : ""}`}
                  onClick={() => selectLevel(level.name)}
                >
                  <strong>二级：{level.name}</strong>
                  <Tag>{level.apis.length}</Tag>
                  <span>{level.desc}</span>
                </button>
              ))}
            </Card>

            <Card
              size="small"
              className="api-docs__matrix-card"
              title={`${currentModule?.name ?? "模块"} / ${currentLevel?.name ?? "二级业务"}：接口矩阵`}
              extra={<Typography.Text type="secondary">点击接口后，下方阅读器和右侧模型同步切换</Typography.Text>}
            >
              <div className="api-docs__matrix-scroll">
                <table className="api-docs__matrix-table">
                  <thead>
                    <tr>
                      <th>一级</th>
                      <th>二级</th>
                      <th>Method</th>
                      <th>接口名称</th>
                      <th>Path</th>
                      <th>这个接口干嘛</th>
                      <th>怎么请求</th>
                      <th>成功返回</th>
                    </tr>
                  </thead>
                  <tbody>
                    {matrixApis.map((api) => (
                      <tr
                        key={api.id}
                        className={api.id === selectedApi.id ? "api-docs__matrix-row--active" : ""}
                        onClick={() => setSelectedApiId(api.id)}
                      >
                        <td>{api.moduleName}</td>
                        <td>{api.levelName}</td>
                        <td><Tag color={getMethodColor(api.method)}>{api.method}</Tag></td>
                        <td>{api.title}</td>
                        <td><code>{api.path}</code></td>
                        <td>{api.purpose}</td>
                        <td>{api.requestMode}</td>
                        <td>{api.successReturn}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card
              size="small"
              className="api-docs__detail-reader"
              title="接口详情阅读器"
              extra={<Typography.Text type="secondary">用途 / 请求 / 参数 / 返回</Typography.Text>}
            >
              <div className="api-docs__detail-body">
                <div className="api-docs__breadcrumb-strip">
                  <Tag color="blue">{selectedApi.moduleName}</Tag>
                  <span>/</span>
                  <Tag color="green">{selectedApi.levelName}</Tag>
                  <span>/</span>
                  <Tag color={getMethodColor(selectedApi.method)}>{selectedApi.method}</Tag>
                  <code>{selectedApi.path}</code>
                </div>
                <div className="api-docs__detail-head">
                  <div>
                    <Typography.Title level={4}>{selectedApi.title}</Typography.Title>
                    <Typography.Paragraph type="secondary">{selectedApi.scenario}</Typography.Paragraph>
                  </div>
                  <Space>
                    <Button icon={<CopyOutlined aria-hidden="true" />} onClick={() => void messageApi.info("复制Path接口待接入")}>复制Path</Button>
                    <Button type="primary" onClick={() => setDebugOpen(true)}>调试接口</Button>
                  </Space>
                </div>
                <div className="api-docs__detail-grid">
                  <section className="api-docs__doc-section">
                    <h3>这个接口干嘛的</h3>
                    <p>{selectedApi.purpose}</p>
                  </section>
                  <section className="api-docs__doc-section">
                    <h3>我要怎么请求</h3>
                    <p>使用 {selectedApi.method} 请求 <code>{selectedApi.path}</code>，需要权限 <code>{selectedApi.authScope}</code>。</p>
                  </section>
                </div>
                <section className="api-docs__doc-section">
                  <h3>Query 参数</h3>
                  <FieldTable rows={selectedApi.queryParams} />
                </section>
                <section className="api-docs__doc-section">
                  <h3>Body 参数</h3>
                  <FieldTable rows={selectedApi.bodyParams} />
                </section>
              </div>
            </Card>
          </div>

          <Card size="small" className="api-docs__right-model" title="权限与返回模型" extra={<Button onClick={() => setDebugOpen(true)}>调试</Button>}>
            <div className="api-docs__model-body">
              <Space className="api-docs__quick-actions">
                <Button block onClick={() => void messageApi.info("复制Path接口待接入")}>复制 Path</Button>
                <Button block onClick={() => void messageApi.info("复制cURL接口待接入")}>复制 cURL</Button>
              </Space>
              <section className="api-docs__schema-card">
                <b>接口定位</b>
                <div className="api-docs__breadcrumb-strip">
                  <Tag color="blue">一级：{selectedApi.moduleName}</Tag>
                  <Tag color="green">二级：{selectedApi.levelName}</Tag>
                </div>
                <Typography.Text type="secondary">{selectedApi.levelDesc}</Typography.Text>
              </section>
              <section className="api-docs__schema-card">
                <b>权限 Scope</b>
                <code>{selectedApi.authScope}</code>
              </section>
              <section className="api-docs__schema-card">
                <b>请求对象</b>
                <CodeBlock value={selectedApi.requestExample} />
              </section>
              <section className="api-docs__schema-card">
                <b>返回字段模型</b>
                <FieldTable rows={selectedApi.returnFields} />
              </section>
            </div>
          </Card>
        </section>
      </div>

      <Drawer
        open={configOpen}
        title="接口文档显示配置"
        width={540}
        onClose={() => setConfigOpen(false)}
        footer={(
          <Space>
            <Button onClick={() => setConfigOpen(false)}>取消</Button>
            <Button type="primary" onClick={() => { void messageApi.info(CONFIG_PENDING); setConfigOpen(false); }}>保存</Button>
          </Space>
        )}
      >
        <Card size="small" title="导航结构">
          正式页面固定为：左侧一级模块导航，上方二级业务导航，中间接口矩阵，下方接口详情，右侧权限和返回模型。
        </Card>
      </Drawer>

      <Modal
        open={exportOpen}
        title="导出 API 文档"
        onCancel={() => setExportOpen(false)}
        onOk={() => { void messageApi.info(EXPORT_PENDING); setExportOpen(false); }}
        okText="开始导出"
        cancelText="取消"
      >
        <div className="api-docs__export-options">
          <Card size="small">导出当前一级模块</Card>
          <Card size="small">导出二级业务接口</Card>
          <Card size="small">导出请求/返回示例</Card>
          <Card size="small">导出 OpenAPI JSON</Card>
        </div>
      </Modal>

      <Modal
        open={debugOpen}
        title="接口调试预览"
        onCancel={() => setDebugOpen(false)}
        onOk={() => void messageApi.info(DEBUG_PENDING)}
        okText="发送请求"
        cancelText="关闭"
        width={760}
      >
        <Typography.Paragraph type="secondary">当前调试接口：{selectedApi.method} {selectedApi.path}</Typography.Paragraph>
        <CodeBlock value={selectedApi.requestExample} />
      </Modal>
    </PageShell>
  );
}

export default ApiDocsPage;

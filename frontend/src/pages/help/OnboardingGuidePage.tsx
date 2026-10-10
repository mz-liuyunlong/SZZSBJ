import {
  ApartmentOutlined,
  CheckCircleOutlined,
  CompassOutlined,
  DatabaseOutlined,
  HomeOutlined,
  ProfileOutlined,
  QuestionCircleOutlined,
  SafetyCertificateOutlined,
  TeamOutlined,
  ToolOutlined,
  UsergroupAddOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Collapse,
  Divider,
  message,
  Row,
  Space,
  Steps,
  Tag,
  Typography,
} from "antd";
import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { DEFAULT_BUSINESS_PATH } from "@/router/routeResolver";
import "@/pages/help/OnboardingGuidePage.css";

const GUIDE_PATH = "/help/onboarding";

const sectionNav = [
  { id: "company", label: "公司资料", icon: <ApartmentOutlined /> },
  { id: "map", label: "系统地图", icon: <CompassOutlined /> },
  { id: "sop", label: "岗位 SOP", icon: <ProfileOutlined /> },
  { id: "seven-days", label: "新人 7 天", icon: <UsergroupAddOutlined /> },
  { id: "metrics", label: "数据口径", icon: <DatabaseOutlined /> },
  { id: "rules", label: "工作红线", icon: <SafetyCertificateOutlined /> },
  { id: "faq", label: "常见问题", icon: <QuestionCircleOutlined /> },
  { id: "support", label: "负责人支持", icon: <TeamOutlined /> },
];

const companyMaterials = [
  {
    title: "公司介绍",
    description: "公司业务、团队目标、主要平台、核心品类和经营方向。",
  },
  {
    title: "业务模式",
    description: "Amazon、Walmart、TEMU 等平台的产品、运营、广告、售后协同方式。",
  },
  {
    title: "组织结构",
    description: "老板、运营主管、运营、财务、仓库、采购、产品负责人的协作关系。",
  },
  {
    title: "公司制度",
    description: "账号安全、数据使用、客户响应、异常反馈、离职交接等基础制度。",
  },
];

const systemModules = [
  { name: "工作台", desc: "销售、利润、广告、退款、库存、Review、Listing 异常总览" },
  { name: "产品", desc: "产品资料、Listing、认领中心、新品分析、生命周期、等级" },
  { name: "销售", desc: "每日销售、订单利润、Review、补货建议、发货计划、趋势" },
  { name: "广告", desc: "广告活动、关键词、排名、否定词、搜索词、调价记录" },
  { name: "售后", desc: "退款、退货、客户消息、Case、索赔、负面反馈" },
  { name: "仓库", desc: "库存明细、库存预警、WFS、仓储费、入库、库龄" },
  { name: "财务", desc: "利润中心、现金利润、结算对账、广告账单、业绩报表" },
  { name: "运营", desc: "运营日志、运营计划、运营待办、运营日历" },
];

const roleProfiles = {
  operator: {
    label: "运营",
    title: "运营 SOP",
    summary: "运营负责产品、Listing、广告、销售、售后和运营日志，是产品日常经营动作的主要执行人。",
    focus: ["产品状态", "Listing 异常", "广告花费", "销售利润", "退款售后", "运营日志"],
    tasks: [
      "每天先看工作台，确认销售、利润、广告、退款、库存、Review、Listing 是否有异常。",
      "检查产品管理和 Listing 管理，重点关注资料完整、购物车、评分、跟卖、划线价异常。",
      "跟进广告表现，重点看花费、点击、订单、关键词和异常搜索词。",
      "按 SKU 记录运营日志，广告调整、链接修改、图片、开发和异常处理都要有记录。",
    ],
  },
  supervisor: {
    label: "运营主管",
    title: "运营主管 SOP",
    summary: "运营主管关注团队效率、异常闭环、任务分配和重点产品经营质量。",
    focus: ["团队待办", "异常闭环", "运营计划", "日志质量", "广告异常", "断货风险"],
    tasks: [
      "查看角色工作台和运营看板，确认团队今日是否有未完成事项。",
      "关注广告异常、Listing 异常、退款异常、库存断货风险。",
      "检查运营日志质量，确认关键 SKU 是否有动作、有结果、有复盘。",
      "安排运营计划和待办，跟踪延期、未处理和重复异常。",
    ],
  },
  finance: {
    label: "财务",
    title: "财务 SOP",
    summary: "财务负责利润、现金利润、结算对账、广告费用和异常成本核对。",
    focus: ["利润中心", "订单利润", "广告费用", "结算对账", "返还明细", "异常成本"],
    tasks: [
      "查看利润中心、订单利润和单品现金利润。",
      "核对广告费用、广告账单、结算对账和沃尔玛返还明细。",
      "关注退款、赔付、仓储费、WFS 费用异常对利润的影响。",
      "发现成本、佣金、回款异常先记录并反馈，不直接改生产数据。",
    ],
  },
  warehouse: {
    label: "仓库",
    title: "仓库 SOP",
    summary: "仓库负责库存、补货、库龄、入库差异、WFS 异常和断货风险。",
    focus: ["库存明细", "库存预警", "补货建议", "入库差异", "库龄", "WFS 异常"],
    tasks: [
      "查看库存明细、库存预警和补货建议。",
      "跟进入库运输、入库差异、库龄、移除/弃置和 WFS 费用异常。",
      "与采购、运营确认断货风险和建议采购数量。",
      "异常先记录和反馈，不直接修改业务数据。",
    ],
  },
  purchase: {
    label: "采购",
    title: "采购 SOP",
    summary: "采购负责采购计划、采购单、交期、供应商、断货风险和审核周期。",
    focus: ["采购计划", "采购单", "交期", "供应商", "审核周期", "断货风险"],
    tasks: [
      "查看采购计划和采购单，确认 SKU 采购进度。",
      "关注采购量、采购金额、交期和供应商响应。",
      "跟进异常采购单，避免影响产品断货。",
      "与运营、仓库确认建议采购数量和到货节奏。",
    ],
  },
  owner: {
    label: "老板",
    title: "老板视角",
    summary: "老板关注整体经营结果、利润质量、风险异常和团队执行情况。",
    focus: ["销售趋势", "利润质量", "广告占比", "退款风险", "库存风险", "团队执行"],
    tasks: [
      "先看数据驾驶舱和角色工作台，掌握销售、利润、广告、退款和库存风险。",
      "关注异常趋势：利润下滑、广告失控、退款升高、断货风险、Listing 异常。",
      "查看财务报表和运营执行情况，判断团队动作是否有效。",
      "重点问题进入对应模块追踪，不在表格外单独做口径。",
    ],
  },
} as const;

type RoleKey = keyof typeof roleProfiles;


const sevenDayPlan = [
  {
    title: "第 1 天：账号和系统结构",
    description: "完成密码设置、登录系统，了解公司业务、系统结构、常用模块和基础规则。",
  },
  {
    title: "第 2 天：产品和 Listing",
    description: "熟悉产品管理、Listing 管理、资料完整度、购物车、评分、跟卖和划线价异常。",
  },
  {
    title: "第 3 天：销售和利润",
    description: "熟悉每日销售、订单利润、Review、补货建议和销售趋势。",
  },
  {
    title: "第 4 天：广告数据",
    description: "熟悉广告花费、点击、订单、关键词、搜索词、否定词和调价记录。",
  },
  {
    title: "第 5 天：售后和客户消息",
    description: "熟悉退款、退货、客户消息、Case、索赔和负面反馈处理规则。",
  },
  {
    title: "第 6 天：运营日志和待办",
    description: "熟悉运营日志、运营计划、运营待办和运营日历，知道每天动作如何留痕。",
  },
  {
    title: "第 7 天：负责人检查",
    description: "由负责人确认是否能独立完成基础工作，并补充岗位 SOP 中的细节。",
  },
];

const metricItems = [
  "销售额",
  "销量",
  "利润",
  "利润率",
  "广告花费",
  "广告占比",
  "退款金额",
  "库存预警",
  "WFS 费用异常",
  "单品现金利润",
  "结算对账",
  "订单利润",
];

const rules = [
  "不允许私自修改生产数据",
  "不允许外传账号密码",
  "不允许绕过系统私下记录关键运营动作",
  "不允许未授权操作店铺后台",
  "不允许删除或覆盖历史数据",
  "发现异常必须截图并反馈",
];

const supportItems = [
  { title: "账号权限", owner: "系统管理员 / 运营主管" },
  { title: "产品资料", owner: "产品负责人" },
  { title: "广告问题", owner: "运营主管" },
  { title: "售后问题", owner: "客服 / 售后负责人" },
  { title: "库存问题", owner: "仓库 / 采购" },
  { title: "财务数据", owner: "财务负责人" },
];

const faqItems = [
  {
    key: "login",
    label: "登录不了怎么办？",
    children: "先确认账号是否已启用、密码是否设置完成。忘记密码时，通过飞书密码设置卡片重新设置。",
  },
  {
    key: "permission",
    label: "没有菜单权限怎么办？",
    children: "截图当前页面和账号信息，反馈给直属负责人或系统管理员确认角色权限。",
  },
  {
    key: "empty-data",
    label: "页面数据为空怎么办？",
    children: "先确认筛选条件、日期范围和负责店铺。如果仍然为空，截图反馈，不要自行修改数据。",
  },
  {
    key: "diff",
    label: "系统数据和平台后台不一致怎么办？",
    children: "先记录平台、日期、SKU、截图和差异口径，反馈负责人核对同步时间和统计口径。",
  },
];

function getSafeReturnTo(search: string): string {
  const params = new URLSearchParams(search);
  const returnTo = params.get("returnTo");

  if (!returnTo || !returnTo.startsWith("/") || returnTo.startsWith("//")) {
    return DEFAULT_BUSINESS_PATH;
  }

  if (returnTo === GUIDE_PATH) {
    return DEFAULT_BUSINESS_PATH;
  }

  return returnTo;
}

function scrollToGuideSection(sectionId: string) {
  document.getElementById(sectionId)?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

function OnboardingGuidePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [messageApi, messageContextHolder] = message.useMessage();
  const [activeSection, setActiveSection] = useState(sectionNav[0].id);
  const [activeRole, setActiveRole] = useState<RoleKey>("operator");
  const [confirmed, setConfirmed] = useState(false);
  const safeReturnTo = useMemo(() => getSafeReturnTo(location.search), [location.search]);
  const activeRoleProfile = roleProfiles[activeRole];

  useEffect(() => {
    document.documentElement.classList.add("onboarding-guide-html");
    document.body.classList.add("onboarding-guide-body");

    return () => {
      document.documentElement.classList.remove("onboarding-guide-html");
      document.body.classList.remove("onboarding-guide-body");
    };
  }, []);

  const returnToSystem = () => {
    navigate(safeReturnTo, { replace: true });
  };

  const openWorkspace = () => {
    navigate(DEFAULT_BUSINESS_PATH, { replace: true });
  };

  const openPlaceholder = (title: string) => {
    void messageApi.info(`${title}后续接入详细资料。`);
  };

  const openSection = (sectionId: string) => {
    setActiveSection(sectionId);
    scrollToGuideSection(sectionId);
  };

  const openRoleSop = (role: RoleKey) => {
    setActiveRole(role);
    openSection("sop");
  };

  return (
    <main className="onboarding-guide-page" aria-label="掌上便捷入职指引">
      {messageContextHolder}

      <header className="onboarding-guide-page__topbar">
        <button
          type="button"
          className="onboarding-guide-page__brand"
          aria-label="打开默认工作台"
          onClick={openWorkspace}
        >
          <img src="/favicon.ico" alt="掌上便捷标识" />
          <span>掌上便捷</span>
        </button>

        <div className="onboarding-guide-page__top-title">
          <Typography.Text strong>帮助中心 / 入职指引</Typography.Text>
          <Typography.Text type="secondary">公司资料、岗位 SOP、系统地图、工作规则</Typography.Text>
        </div>

        <Space className="onboarding-guide-page__top-actions">
          <Button icon={<HomeOutlined aria-hidden="true" />} onClick={openWorkspace}>
            打开工作台
          </Button>
          <Button type="primary" onClick={returnToSystem}>
            返回系统
          </Button>
        </Space>
      </header>

      <section className="onboarding-guide-page__shell">
        <aside className="onboarding-guide-page__sidebar" aria-label="入职指引目录">
          <div className="onboarding-guide-page__sidebar-title">目录</div>
          <nav className="onboarding-guide-page__side-nav" aria-label="入职指引目录导航">
            {sectionNav.map((item) => (
              <button
                key={item.id}
                type="button"
                className={item.id === activeSection ? "is-active" : ""}
                aria-current={item.id === activeSection ? "page" : undefined}
                onClick={() => openSection(item.id)}
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            ))}
          </nav>

          <Card className="onboarding-guide-page__sidebar-card">
            <Typography.Text strong>新人建议</Typography.Text>
            <Typography.Paragraph type="secondary">
              第一次进入系统前，先看完公司资料、系统地图和自己岗位的 SOP。
            </Typography.Paragraph>
          </Card>
        </aside>

        <div className="onboarding-guide-page__content">
          <section className="onboarding-guide-page__hero">
            <Tag color="blue">新人入职 / 系统帮助 / SOP 入口</Tag>
            <Typography.Title level={1}>掌上便捷入职指引</Typography.Title>
            <Typography.Paragraph>
              这是掌上便捷内部帮助中心的入口页。新人可以从这里了解公司、系统、岗位工作内容和基础规则；
              老员工也可以通过右上角“帮助”随时回来查看 SOP、数据口径和负责人支持。
            </Typography.Paragraph>

            <div className="onboarding-guide-page__hero-actions">
              <Button type="primary" size="large" onClick={() => openSection("sop")}>
                查看岗位 SOP
              </Button>
              <Button size="large" onClick={() => openSection("seven-days")}>
                查看新人 7 天路径
              </Button>
            </div>
          </section>

          <section id="company" className="onboarding-guide-page__section">
            <div className="onboarding-guide-page__section-heading">
              <ApartmentOutlined aria-hidden="true" />
              <div>
                <Typography.Title level={2}>公司资料</Typography.Title>
                <Typography.Paragraph type="secondary">
                  后续这里会接入公司详细介绍、业务模式、组织结构和制度文档。
                </Typography.Paragraph>
              </div>
            </div>

            <Row gutter={[16, 16]}>
              {companyMaterials.map((item) => (
                <Col xs={24} md={12} key={item.title}>
                  <Card className="onboarding-guide-page__entry-card">
                    <Typography.Title level={4}>{item.title}</Typography.Title>
                    <Typography.Paragraph>{item.description}</Typography.Paragraph>
                    <Button type="link" onClick={() => openPlaceholder(item.title)}>
                      查看资料
                    </Button>
                  </Card>
                </Col>
              ))}
            </Row>
          </section>

          <section id="map" className="onboarding-guide-page__section">
            <div className="onboarding-guide-page__section-heading">
              <CompassOutlined aria-hidden="true" />
              <div>
                <Typography.Title level={2}>系统地图</Typography.Title>
                <Typography.Paragraph type="secondary">
                  先理解每个模块是干嘛的，再进入具体页面操作。
                </Typography.Paragraph>
              </div>
            </div>

            <div className="onboarding-guide-page__module-grid">
              {systemModules.map((module) => (
                <article key={module.name} className="onboarding-guide-page__module-card">
                  <strong>{module.name}</strong>
                  <span>{module.desc}</span>
                </article>
              ))}
            </div>
          </section>

          <section id="sop" className="onboarding-guide-page__section">
            <div className="onboarding-guide-page__section-heading">
              <ProfileOutlined aria-hidden="true" />
              <div>
                <Typography.Title level={2}>岗位 SOP</Typography.Title>
                <Typography.Paragraph type="secondary">
                  未来每个岗位会继续接入详细 SOP：每日工作、每周工作、异常处理、常见错误和考核重点。
                </Typography.Paragraph>
              </div>
            </div>

            <div className="onboarding-guide-page__role-shortcuts">
              {(Object.keys(roleProfiles) as RoleKey[]).map((role) => (
                <button
                  key={role}
                  type="button"
                  className={role === activeRole ? "is-active" : ""}
                  onClick={() => openRoleSop(role)}
                >
                  <span>{roleProfiles[role].label}</span>
                  <small>{roleProfiles[role].title}</small>
                </button>
              ))}
            </div>

            <Card className="onboarding-guide-page__sop-card">

              <div className="onboarding-guide-page__role-panel" aria-live="polite">
                <div>
                  <Typography.Title level={3}>{activeRoleProfile.title}</Typography.Title>
                  <Typography.Paragraph>{activeRoleProfile.summary}</Typography.Paragraph>
                  <div className="onboarding-guide-page__focus-tags">
                    {activeRoleProfile.focus.map((item) => (
                      <Tag key={item}>{item}</Tag>
                    ))}
                  </div>
                </div>

                <ul>
                  {activeRoleProfile.tasks.map((task) => (
                    <li key={task}>{task}</li>
                  ))}
                </ul>
              </div>
            </Card>
          </section>

          <section id="seven-days" className="onboarding-guide-page__section">
            <div className="onboarding-guide-page__section-heading">
              <UsergroupAddOutlined aria-hidden="true" />
              <div>
                <Typography.Title level={2}>新人 7 天上手路径</Typography.Title>
                <Typography.Paragraph type="secondary">
                  让新人知道第一周每天要熟悉什么，而不是直接面对一堆菜单。
                </Typography.Paragraph>
              </div>
            </div>

            <Card className="onboarding-guide-page__timeline-card">
              <Steps direction="vertical" current={sevenDayPlan.length - 1} items={sevenDayPlan} />
            </Card>
          </section>

          <section id="metrics" className="onboarding-guide-page__section">
            <div className="onboarding-guide-page__section-heading">
              <DatabaseOutlined aria-hidden="true" />
              <div>
                <Typography.Title level={2}>数据口径</Typography.Title>
                <Typography.Paragraph type="secondary">
                  后续这里会解释销售额、利润、广告占比、退款、库存、WFS 等指标的计算口径。
                </Typography.Paragraph>
              </div>
            </div>

            <div className="onboarding-guide-page__metric-grid">
              {metricItems.map((item) => (
                <button key={item} type="button" onClick={() => openPlaceholder(`${item}口径`)}>
                  <DatabaseOutlined aria-hidden="true" />
                  <span>{item}</span>
                </button>
              ))}
            </div>
          </section>

          <section id="rules" className="onboarding-guide-page__section">
            <div className="onboarding-guide-page__section-heading">
              <SafetyCertificateOutlined aria-hidden="true" />
              <div>
                <Typography.Title level={2}>工作红线</Typography.Title>
                <Typography.Paragraph type="secondary">
                  这部分是新人必须先知道的规则，比具体页面操作更重要。
                </Typography.Paragraph>
              </div>
            </div>

            <Alert
              type="warning"
              showIcon
              icon={<WarningOutlined />}
              message="禁止直接修改生产数据，发现异常先截图反馈。"
              description="系统数据、店铺后台、广告、库存、财务口径都需要按权限和流程处理。"
            />

            <Row gutter={[12, 12]} className="onboarding-guide-page__rules-grid">
              {rules.map((rule) => (
                <Col xs={24} md={12} key={rule}>
                  <div className="onboarding-guide-page__rule">
                    <CheckCircleOutlined aria-hidden="true" />
                    <span>{rule}</span>
                  </div>
                </Col>
              ))}
            </Row>
          </section>

          <section id="faq" className="onboarding-guide-page__section">
            <div className="onboarding-guide-page__section-heading">
              <QuestionCircleOutlined aria-hidden="true" />
              <div>
                <Typography.Title level={2}>常见问题</Typography.Title>
                <Typography.Paragraph type="secondary">
                  新人反复会问的问题，后续可以继续扩展成完整 FAQ。
                </Typography.Paragraph>
              </div>
            </div>

            <Collapse className="onboarding-guide-page__faq" items={faqItems} />
          </section>

          <section id="support" className="onboarding-guide-page__section">
            <div className="onboarding-guide-page__section-heading">
              <TeamOutlined aria-hidden="true" />
              <div>
                <Typography.Title level={2}>负责人支持</Typography.Title>
                <Typography.Paragraph type="secondary">
                  反馈模板不放在页面里。新人只需要知道不同问题应该找谁。
                </Typography.Paragraph>
              </div>
            </div>

            <Row gutter={[12, 12]}>
              {supportItems.map((item) => (
                <Col xs={24} md={12} xl={8} key={item.title}>
                  <Card className="onboarding-guide-page__support-card">
                    <ToolOutlined aria-hidden="true" />
                    <strong>{item.title}</strong>
                    <span>{item.owner}</span>
                  </Card>
                </Col>
              ))}
            </Row>
          </section>

          <section className="onboarding-guide-page__complete" aria-label="完成阅读操作">
            <div>
              <Typography.Title level={3}>阅读完成后再进入系统</Typography.Title>
              <Typography.Paragraph>
                后续正式版可以在这里记录 onboarding_completed_at，首次登录后只强制阅读一次。
              </Typography.Paragraph>
              <Checkbox checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)}>
                我已阅读并理解基础规则
              </Checkbox>
            </div>

            <Divider type="vertical" />

            <Space direction="vertical" className="onboarding-guide-page__complete-actions">
              <Button
                block
                type="primary"
                disabled={!confirmed}
                aria-label="我已了解，返回系统"
                onClick={returnToSystem}
              >
                我已了解，返回系统
              </Button>
              <Button block onClick={openWorkspace}>
                打开默认工作台
              </Button>
            </Space>
          </section>
        </div>
      </section>
    </main>
  );
}

export default OnboardingGuidePage;

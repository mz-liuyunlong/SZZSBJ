# Playwright E2E 测试规则

## 1. 文件用途

本文件定义 本项目 前端 E2E 测试规则。Playwright 只用于浏览器级页面验收，不替代 Vitest、TypeScript 类型检查、ESLint、后端 pytest 或人工业务验收。

---

## 2. 工具定位

```text
Vitest：前端组件、函数、工具方法测试
Playwright：真实浏览器页面流程测试
Pytest：后端 API / service / repository 测试
Ruff / Pyright：Python 质量检查
ESLint / tsc：前端质量检查
CI：所有检查的合并门禁
```

Playwright 的定位是验证：

```text
页面真的能打开
用户真的能点击
权限真的能挡住
帮助入口真的能跳转
关键表单和流程真的能跑通
```

---

## 3. 安装规则

前端初始化完成后，在 `frontend/` 中安装：

```bash
cd frontend
npm i -D @playwright/test
npx playwright install
```

禁止在根目录全局散装 Playwright 依赖。第一阶段不强制安装 Playwright MCP，也不要求安装全局 Playwright CLI。

---

## 4. 目录规则

Playwright 文件必须放在前端目录中：

```text
frontend/
├─ e2e/
│  ├─ navigation.spec.ts
│  ├─ page-shell.spec.ts
│  ├─ help-link.spec.ts
│  ├─ api-docs.spec.ts
│  └─ permissions.spec.ts
├─ playwright.config.ts
└─ package.json
```

---

## 5. package.json 脚本

前端 `package.json` 建议增加：

```json
{
  "scripts": {
    "test:e2e": "playwright test",
    "test:e2e:ui": "playwright test --ui",
    "test:e2e:headed": "playwright test --headed",
    "test:e2e:report": "playwright show-report"
  }
}
```

---

## 6. 第一阶段必须覆盖的 E2E 场景

第一阶段还没有真实业务数据，Playwright 重点验收前端框架稳定性：

```text
1. 首页能打开。
2. 左侧一级导航完整显示。
3. 所有二级菜单能点击。
4. 每个页面进入 ComingSoon 占位页。
5. PageShell 显示页面标题。
6. PageShell 显示 status / source / readOnly / migrationMode。
7. 每个正式页面右上角存在 ? 帮助按钮。
8. 点击 ? 帮助按钮，新标签页打开对应 helpUrl。
9. 数据中心 > API文档 页面入口存在。
10. 无权限用户不应看到 API文档入口。
```

---

## 7. 功能 ready 前的 E2E 要求

每个标记为 `ready` 的页面，至少必须有一个 Playwright E2E 测试。

高危功能必须增加完整流程测试，例如：

```text
费用规则新增 / 版本化 / 冲突提示 / 影响预览
角色管理页面权限 / 动作权限 / 数据权限保存
导入任务预览 / 失败行展示 / 回滚入口
API文档页面权限控制 / 接口列表展示
AI Token 配置脱敏 / 测试连接 / 预算提示
飞书通知配置脱敏 / 测试发送 / 失败提示
```

---

## 8. 选择器规则

优先使用稳定且贴近用户体验的定位方式：

```ts
page.getByRole('button', { name: '保存' })
page.getByRole('link', { name: '每日销售' })
page.getByLabel('开始日期')
page.getByText('数据范围')
```

规则：

```text
优先 getByRole / getByLabel / getByText。
禁止依赖不稳定 CSS class。
必要时才使用 data-testid。
如果使用 data-testid，必须语义化命名。
```

---

## 9. 测试数据规则

```text
local 默认使用 mock 数据。
staging 使用脱敏数据。
E2E 不允许依赖生产数据库。
E2E 不允许调用真实外部平台 API。
E2E 不允许使用真实 Token / Secret。
```

权限类 E2E 可以使用测试账号或 mock auth state，但必须明确：

```text
admin-like 测试账号
普通用户测试账号
无权限测试账号
```

禁止把真实账号密码写进测试文件。

---

## 10. CI 规则

前端初始化完成并安装 Playwright 后，CI 必须支持：

```bash
npm run test:e2e
```

建议 CI 步骤：

```yaml
- name: Install Playwright browsers
  working-directory: frontend
  run: npx playwright install --with-deps

- name: Run Playwright E2E
  working-directory: frontend
  run: npm run test:e2e
```

规则：

```text
Playwright 失败，不允许合并 ready 页面相关 PR。
框架阶段可以只跑导航壳 E2E。
业务阶段必须按功能补充 E2E。
```

---

## 11. Codex 完成报告要求

Codex 完成功能时必须说明：

```text
是否新增 Playwright E2E 测试
新增了哪些 spec 文件
覆盖了哪些页面/流程
是否运行 npm run test:e2e
如果未运行，必须说明原因
```

未新增 E2E 的 `ready` 页面，不允许声称完成。

---

## 12. 禁止事项

```text
禁止用 Playwright 替代后端 pytest。
禁止用 Playwright 替代单元测试。
禁止依赖生产账号、生产数据库、真实外部 API。
禁止在测试中写入真实 Token、密码、Webhook。
禁止把失败的 E2E 当作通过。
禁止因为 E2E 不稳定就删除测试，必须修复选择器或测试数据。
```
